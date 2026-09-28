"""JSON command-line port for the weak-worker capsule (ACE-QWEN-FIELD-01).

A weak model must not have to write Python or read a protocol document to use
ACE.  This adapter exposes exactly the existing lifecycle calls -- ``ace_start``,
``render_task_capsule``, ``renew_lease``, ``submit_task_capsule_result``,
``fail_task``, plus a read-only ``list-pending`` -- as one-shot commands that
print a single JSON line and set a shell-testable exit code.

It owns no state and no loop: it opens the pool named by ``--pool`` for one
command and exits.  ``--payload-file`` exists because quoting a JSON object
through a shell is the first thing a weak worker gets wrong.

    py -3.11 -m ops.worker_capsule_cli --pool <dir> list-pending
    py -3.11 -m ops.worker_capsule_cli --pool <dir> start --task-id RQ-... --owner w1
    py -3.11 -m ops.worker_capsule_cli --pool <dir> render --task-id RQ-... --claim <id> --token 1
    py -3.11 -m ops.worker_capsule_cli --pool <dir> submit --task-id RQ-... --claim <id> \
        --token 1 --actor w1 --payload-file p.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.ace_start import ace_start  # noqa: E402
from core.task import TaskPool  # noqa: E402
from core.worker_capsule import render_task_capsule, submit_task_capsule_result  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 3
EXIT_USAGE = 4

# Capsule text is Chinese; a worker whose shell is on the ANSI codepage would
# otherwise receive mojibake and act on a garbled brief.
try:  # pragma: no cover - depends on the host stdio
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def _emit(payload: Dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    status = str(payload.get("status", ""))
    if status in {"CAPSULE_READY", "SUBMITTED", "STARTED", "RENEWED", "FAILED_RECORDED", "LISTED"}:
        return EXIT_OK
    if status in {"REFUSED", "REJECTED"}:
        return EXIT_REFUSED
    return EXIT_USAGE


def _pool(args: argparse.Namespace) -> TaskPool:
    return TaskPool(str(Path(args.pool).expanduser().resolve()))


def _credentials(args: argparse.Namespace) -> Dict[str, Any]:
    return {"claim_id": args.claim, "fencing_token": args.token}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pool", required=True, help="TaskPool directory (production or scratch)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-pending", help="read-only: claimable tasks, least fields needed to pick one")

    for name in ("start", "render", "renew", "submit", "fail"):
        command = sub.add_parser(name)
        command.add_argument("--task-id", required=True)
        if name in {"render", "renew", "submit", "fail"}:
            command.add_argument("--claim", required=True)
            command.add_argument("--token", required=True, type=int)
        if name == "start":
            command.add_argument("--owner", required=True)
            command.add_argument("--lease", type=int, default=300)
        if name == "renew":
            command.add_argument("--owner", required=True)
            command.add_argument("--lease", type=int, default=300)
        if name == "submit":
            command.add_argument("--actor", required=True)
            command.add_argument("--payload-file", help="path to a JSON object")
            command.add_argument("--payload", help="inline JSON object (prefer --payload-file)")
            command.add_argument("--capsule-hash", default="")
        if name == "fail":
            command.add_argument("--actor", required=True)
            command.add_argument("--reason", required=True)
            command.add_argument("--type", default="retryable", dest="failure_type")

    args = parser.parse_args(argv)

    if args.command == "list-pending":
        pool = _pool(args)
        rows = [
            {
                "task_id": task.task_id,
                "title": task.title,
                "priority": task.priority,
                "complexity": (task.outputs.get("execution_discipline") or {}).get("complexity"),
                "retry_count": task.retry_count,
            }
            for task in pool.list_tasks(status="pending", limit=20)
        ]
        return _emit({"status": "LISTED", "count": len(rows), "pending": rows})

    if args.command == "start":
        pool = _pool(args)
        return _emit(ace_start(pool, args.task_id, args.owner, lease_seconds=args.lease))

    if args.command == "render":
        pool = _pool(args)
        return _emit(render_task_capsule(pool, args.task_id, **_credentials(args)))

    if args.command == "renew":
        pool = _pool(args)
        task = pool.load_task(args.task_id)
        if task is None:
            return _emit({"status": "REFUSED", "reason": "task_not_found", "task_id": args.task_id, "runtime_mutation": False})
        renewed = pool.renew_lease(args.task_id, args.owner, args.claim, lease_seconds=args.lease)
        if renewed is None:
            return _emit(
                {
                    "status": "REFUSED",
                    "reason": "renew_rejected_owner_claim_or_expired",
                    "task_id": args.task_id,
                    "runtime_mutation": False,
                }
            )
        return _emit(
            {
                "status": "RENEWED",
                "task_id": args.task_id,
                "claim_id": renewed.claim_id,
                "fencing_token": renewed.fencing_token,
                "lease_expires_at": renewed.lease_expires_at,
                "runtime_mutation": True,
            }
        )

    if args.command == "submit":
        pool = _pool(args)
        if bool(args.payload_file) == bool(args.payload):
            return _emit(
                {
                    "status": "REFUSED",
                    "reason": "submit_requires_exactly_one_of_payload_file_or_payload",
                    "task_id": args.task_id,
                    "runtime_mutation": False,
                }
            )
        try:
            raw = (
                Path(args.payload_file).expanduser().read_text(encoding="utf-8")
                if args.payload_file
                else args.payload
            )
            payload = json.loads(raw)
        except (OSError, ValueError) as error:
            # A weak worker cannot debug a parser exception.  Point at the exact
            # character position and name the file so one edit fixes it.
            detail = {"error_type": type(error).__name__, "message": str(error)[:300]}
            line = getattr(error, "lineno", None)
            column = getattr(error, "colno", None)
            position = getattr(error, "pos", None)
            if line is not None:
                detail.update({"line": line, "column": column, "character_offset": position})
                try:
                    offending = raw.splitlines()[line - 1]
                    detail["offending_line"] = offending[:200]
                    detail["caret"] = (" " * max(0, int(column or 1) - 1)) + "^"
                except (NameError, IndexError, TypeError, ValueError):
                    pass
            detail["fix_hint"] = (
                "payload 必须是单个 JSON object；用 --payload-file 指向一个 UTF-8 文件最稳，"
                "注意字符串结尾的引号与逗号"
            )
            return _emit(
                {
                    "status": "REFUSED",
                    "reason": f"payload_unreadable:{type(error).__name__}",
                    "task_id": args.task_id,
                    "detail": detail,
                    "runtime_mutation": False,
                }
            )
        if not isinstance(payload, dict):
            return _emit(
                {
                    "status": "REFUSED",
                    "reason": f"payload_must_be_json_object_not_{type(payload).__name__}",
                    "task_id": args.task_id,
                    "runtime_mutation": False,
                }
            )
        return _emit(
            submit_task_capsule_result(
                pool,
                args.task_id,
                actor=args.actor,
                payload=payload,
                seen_capsule_hash=args.capsule_hash,
                **_credentials(args),
            )
        )

    # fail
    pool = _pool(args)
    task = pool.load_task(args.task_id)
    if task is None:
        return _emit({"status": "REFUSED", "reason": "task_not_found", "task_id": args.task_id, "runtime_mutation": False})
    moved = pool.fail_task(args.task_id, args.reason, actor=args.actor, failure_type=args.failure_type)
    if moved is None:
        return _emit(
            {
                "status": "REFUSED",
                "reason": "fail_task_rejected",
                "task_id": args.task_id,
                "runtime_mutation": False,
            }
        )
    return _emit(
        {
            "status": "FAILED_RECORDED",
            "task_id": args.task_id,
            "failure_type": args.failure_type,
            "stored_status": moved.status,
            "retry_count": moved.retry_count,
            "retry_after": moved.retry_after,
            "runtime_mutation": True,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
