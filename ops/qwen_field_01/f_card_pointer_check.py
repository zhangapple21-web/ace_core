"""Verify the claim in section 十一 item 2: every pointer this window's F-family
queue cards cite resolves to a real object on disk (LIVE, not a dead anchor).

Ruler shape (and the trap it already fell into once):
- Cards cite paths as ABSOLUTE strings `C:/tmp/ace_core/<rel>`; a naive regex that
  looks for `core/...` matches the tail of `ace_core/...` and reports 50 false DEADs.
  So: absolute pointers are taken verbatim; only explicit relative forms are joined.
- Positive control is mandatory: a pointer known to be LIVE (this ruler's own path,
  plus ace_core's `core/worker_capsule.py`) must pass the same ruler before any
  negative result is believed. Exit 2 if the control fails -- that means the ruler is
  broken, not the cards.
- Ruler bug logged so it is not repeated: extension alternations must list the LONGER
  form first -- `(?:json|jsonl)` matched ".json" inside ".jsonl" and reported two false
  DEAD pointers in cards F01/F04 on this file's first run.
"""
import glob
import os
import re
import sys

CORE = "C:/tmp/ace_core"
QUEUE = "C:/轻量项目/ace_task_queue"

ABS_RE = re.compile(r"C:/tmp/ace_core/[A-Za-z_0-9./\-]+\.(?:py|jsonl|json|md|yaml)")
OTHER_ABS_RE = re.compile(r"C:/轻量项目/[^\s`'\",()]+?\.(?:py|jsonl|json|md|yaml)")
REL_RE = re.compile(r"(?<![\w./-])((?:core|ops|08_GOVERNANCE)/[A-Za-z_0-9./\-]+\.(?:py|jsonl|json|md|yaml))")
RECEIPT_RE = re.compile(r"([A-Za-z_0-9]{6,}_20260928[A-Za-z_0-9]*\.(?:jsonl|json))")

CONTROL = ["core/worker_capsule.py", "ops/qwen_field_01/f_card_pointer_check.py"]


def resolve_abs(p):
    return os.path.exists(p)


def resolve_rel(p):
    return os.path.exists(os.path.join(CORE, p))


def resolve_receipt(name):
    return bool(glob.glob(os.path.join(CORE, "08_GOVERNANCE", "evidence", "**", name), recursive=True))


def cards():
    out = []
    for f in glob.glob(os.path.join(QUEUE, "**", "*.yaml"), recursive=True):
        if re.match(r"^\d{8}T\d{4}_F_F0\d__", os.path.basename(f)):
            out.append(f)
    return sorted(out)


# ---- positive control first ----
ctrl_bad = [p for p in CONTROL if not resolve_rel(p)]
if ctrl_bad:
    print("CONTROL FAILED (ruler is broken, do not trust any DEAD below):", ctrl_bad)
    sys.exit(2)
print("control ok:", CONTROL)

dead = []
rows = []
n_live = 0
for c in cards():
    text = open(c, encoding="utf-8").read()
    refs = set()
    for m in ABS_RE.findall(text):
        refs.add(("abs", m))
    for m in OTHER_ABS_RE.findall(text):
        refs.add(("abs", m))
    for m in REL_RE.findall(text):
        refs.add(("rel", m))
    for m in RECEIPT_RE.findall(text):
        refs.add(("receipt", m))
    ok = 0
    for kind, val in sorted(refs):
        if kind == "abs" and resolve_abs(val):
            ok += 1
        elif kind == "rel" and resolve_rel(val):
            ok += 1
        elif kind == "receipt" and resolve_receipt(val):
            ok += 1
        else:
            dead.append((os.path.basename(c), kind, val))
    n_live += ok
    rows.append((os.path.relpath(c, QUEUE), len(refs), ok))

print("F cards found:", len(rows))
for r, total, ok in rows:
    print("  live=%-3d refs=%-3d %s" % (ok, total, r))
print("total live pointers:", n_live, "| dead:", len(dead))
for d in dead:
    print("DEAD:", d)
sys.exit(1 if (dead or len(rows) != 8) else 0)
