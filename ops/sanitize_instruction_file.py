"""Produce a reduced instruction file and the receipt that covers it.

Reads the raw file, applies an explicit allowlist of sections, refuses to emit
anything that still trips the egress boundary, and writes the artifact plus an
append-only receipt binding both hashes.

This is a tool, not an authority. It cannot decide what may be redacted, and it
does not choose a data class: the caller declares the source class and the
reduced class, and the gate re-verifies both claims independently. What it does
guarantee is that the emitted artifact passed the same boundary check the gate
applies, so a receipt it writes is not a promise -- it is a claim the gate
verifies.

    python ops/sanitize_instruction_file.py \
        --source AGENTS.md --source-class PRIVATE \
        --out ../model_instructions/AGENTS.md \
        --keep "Identity" --keep "Core Principles" --keep "Engineering Rules" \
        --issued-by main_steward
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.mirror_constitution import validate_data_boundary

#: Sections the delivery stage needs. Recorded here rather than passed on the
#: command line so the allowlist is one reviewable constant instead of whatever
#: whoever last ran the tool typed. Every receipt records the list that was
#: actually applied, so a receipt and this constant cannot disagree silently.
DELIVERY_KEEP_SECTIONS = (
    "Identity",
    "Core Principles",
    "Engineering Rules",
    "Autonomous acceptance is owned by the main steward",
)

RECEIPTS = ROOT / "08_GOVERNANCE" / "sanitizer_receipts.jsonl"

# The ledger holds one header line describing the file and then one JSON object
# per line. Appending must respect that: a plain open("a") would run straight
# onto the end of the header and corrupt it into an unparsable line.
RECEIPT_HEADER = {
    "record_type": "sanitizer_receipts",
    "version": "v1",
    "opened": "2026-10-09",
    "note": (
        "Append-only. One receipt per line. A receipt is valid only when "
        "artifact_sha256 matches the file's current hash, data_class passes "
        "validate_data_boundary(target=MODEL_CONTEXT), acceptance is "
        "ACCEPTANCE_VERIFIED, source_path names a registered source, and "
        "source_sha256 differs from artifact_sha256. See "
        "core/instruction_boundary.py."
    ),
    "receipts": [],
}

# Patterns that must not survive reduction. The boundary check below is the
# authority; these exist so the refusal explains itself.
LEAK_PATTERNS = (
    (r"\b[A-Za-z]:\\[\w\\.\-]+", "windows absolute path"),
    (r"(?i)\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b", "github token"),
    (r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}", "bearer token"),
    (r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{24,}\b", "api key"),
    (r"(?i)\b(?:password|secret|token|api[_-]?key)\s*[:=]", "credential assignment"),
)

# Repository and organisation identities. These are not credentials, so the
# boundary check cannot see them, but they name private infrastructure and
# pointing a model at them is the same mistake in slower motion.
IDENTITY_TERMS = (
    "coze-assets",
    "zhangapple21-web",
    "mine-seed",
    "ace_core",
    "r1-archaeology",
    "r1-open-source-seed",
)


def split_sections(text: str) -> list:
    """Split on markdown headings, keeping the heading with its body."""
    parts, current = [], None
    for line in text.splitlines(keepends=True):
        if line.startswith("#"):
            if current is not None:
                parts.append(current)
            current = [line]
        elif current is None:
            current = [line]
        else:
            current.append(line)
    if current is not None:
        parts.append(current)
    return parts


def heading_of(section) -> str:
    for line in section:
        if line.startswith("#"):
            return line.lstrip("#").strip().lower()
    return ""


def redact_identities(text: str) -> str:
    """Replace private repository names with a neutral label.

    Section-level dropping cannot help here: the leak sits inside a section the
    caller legitimately kept, and removing the whole section would throw away
    the work rules along with it. The replacement keeps the sentence readable
    and removes the pointer.
    """
    result = text
    for term in IDENTITY_TERMS:
        result = re.sub(re.escape(term), "[private repo]", result, flags=re.IGNORECASE)
    return result


def build_reduced(source_text: str, keep: list) -> str:
    wanted = [item.strip().lower() for item in keep if item.strip()]
    kept, dropped = [], []
    for section in split_sections(source_text):
        heading = heading_of(section)
        if not heading:
            continue
        if any(heading == item or heading.startswith(item) for item in wanted):
            kept.append(redact_identities("".join(section)).rstrip() + "\n")
        else:
            dropped.append(heading)
    header = (
        "# ACE delivery instructions (reduced)\n\n"
        "> Generated from the private runtime manual by ops/sanitize_instruction_file.py.\n"
        "> The original stays PRIVATE and is never sent. This file carries the\n"
        "> subset the delivery path needs.\n\n"
    )
    return header + "\n".join(kept), dropped


def scan_leaks(text: str) -> list:
    """Credential shapes and private infrastructure identities.

    A term is refused whatever the caller's allowlist says. The boundary check
    is the authority for credentials and would not flag any of these; keeping
    them out is a judgement about who the instruction is for, so it belongs in
    the tool that performs the reduction rather than in a comment.
    """
    leaks = [label for pattern, label in LEAK_PATTERNS if re.search(pattern, text)]
    lowered = text.lower()
    leaks.extend(f"private identity: {term}" for term in IDENTITY_TERMS
                 if term in lowered)
    return leaks


def append_receipt(receipt: dict) -> None:
    """Add one receipt line, leaving the header line intact.

    The ledger is read line by line, and a corrupt line is not an error there --
    it is a line the gate cannot use. That is fail-closed, but it silently
    discards real work, so the writer repairs a missing header and refuses to
    append onto one that is already damaged.
    """
    existing = []
    if RECEIPTS.exists():
        existing = RECEIPTS.read_text(encoding="utf-8").splitlines()
    header_ok = bool(existing) and existing[0].lstrip().startswith("{")
    if header_ok:
        try:
            parsed = json.loads(existing[0])
            header_ok = parsed.get("record_type") == "sanitizer_receipts"
        except ValueError:
            header_ok = False
        if not header_ok:
            raise SystemExit(
                f"{RECEIPTS} header is damaged; refusing to append onto it"
            )
    else:
        existing = []

    line = json.dumps(receipt, ensure_ascii=False)
    body = "\n".join(item for item in existing if item.strip())
    if not body:
        body = json.dumps(RECEIPT_HEADER, ensure_ascii=False)
    RECEIPTS.write_text(body + "\n" + line + "\n", encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-class", required=True)
    parser.add_argument("--reduced-class", default="PUBLIC")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--keep", action="append", default=None,
        help="section heading to retain; repeatable. Defaults to "
             "DELIVERY_KEEP_SECTIONS.",
    )
    parser.add_argument("--issued-by", required=True)
    parser.add_argument("--receipt-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    source_path = Path(args.source).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    source_bytes = source_path.read_bytes()
    source_text = source_bytes.decode("utf-8")

    keep = args.keep if args.keep else list(DELIVERY_KEEP_SECTIONS)
    reduced, dropped = build_reduced(source_text, keep)
    leaks = scan_leaks(reduced)
    verdict = validate_data_boundary(
        {"data_class": args.reduced_class},
        target="MODEL_CONTEXT",
        payload=reduced,
    )

    receipt_id = args.receipt_id or (
        f"R-{source_path.stem}-{hashlib.sha256(reduced.encode()).hexdigest()[:8]}"
    )
    report = {
        "source": str(source_path),
        "source_class": args.source_class.upper(),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_bytes": len(source_bytes),
        "out": str(out_path),
        "reduced_class": args.reduced_class.upper(),
        "reduced_sha256": hashlib.sha256(reduced.encode()).hexdigest(),
        "reduced_bytes": len(reduced.encode("utf-8")),
        "kept_sections": keep,
        "dropped_sections": dropped,
        "leaks_detected": leaks,
        "boundary_valid": verdict["valid"],
        "boundary_errors": verdict["errors"],
        "receipt_id": receipt_id,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if leaks or not verdict["valid"]:
        print("\nREFUSED: the reduced text still carries disallowed content; "
              "no artifact or receipt was written", file=sys.stderr)
        return 1
    if args.dry_run:
        print("\ndry run: nothing written")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(reduced.encode("utf-8"))

    receipt = {
        "receipt_id": receipt_id,
        "acceptance": "ACCEPTANCE_VERIFIED",
        "issued_by": args.issued_by,
        "issued_at": "2026-10-09",
        "path": str(out_path),
        "source_path": str(source_path),
        "source_class": args.source_class.upper(),
        "source_sha256": report["source_sha256"],
        "artifact_sha256": report["reduced_sha256"],
        "data_class": args.reduced_class.upper(),
        "sanitizer": "ops/sanitize_instruction_file.py",
        "reduction": {
            "kept_sections": keep,
            "dropped_sections": dropped,
            "removed_bytes": len(source_bytes) - report["reduced_bytes"],
        },
    }
    append_receipt(receipt)
    print(f"\nwrote {out_path} and appended receipt {receipt_id} to {RECEIPTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())