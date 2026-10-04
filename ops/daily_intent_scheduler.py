#!/usr/bin/env python3
"""ACE 外部意志调度器：从意志候选池中挑一条值得今天执行的意志，注入 TaskPool。

这不是第二个任务调度器。它只做四件事：

1. 读 ``intents/daily_queue.jsonl``（意志候选池，不是任务清单）。
2. 判断每条意志当前的真实生命周期状态（靠 TaskPool 里带 tag 的任务反查）。
3. 在满足容量与可交付性门槛时，**最多选一条**注入；不满足就返回
   ``NO_VALID_INTENT`` / ``HEALTHY_IDLE``，绝不硬凑。
4. 把选择依据、注入回执、状态迁移写进 ``intents/intent_state.json``。

核心约束：**粮仓，不是喂食器。** 队列空了、ACE 忙了、意志已失效，都必须能安静地
什么都不做。

用法：
    python ops/daily_intent_scheduler.py            # 评估并至多注入一条
    python ops/daily_intent_scheduler.py --status   # 只报告，不注入
    python ops/daily_intent_scheduler.py --capacity 2
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
# Two independent guards. Guarding them as one pair meant that whenever the repo
# root was already importable -- which is always true inside ace_daemon -- the
# ops/ directory was never added, so "from inject_target import ..." raised
# ModuleNotFoundError and the whole evening turn failed.
for _path in (ROOT, ROOT / "ops"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.task import TaskPool  # noqa: E402

try:  # importable both as a script (ops/ on sys.path) and as ops.daily_intent_scheduler
    from inject_target import inject, validate_target  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - exercised by the daemon import path
    from ops.inject_target import inject, validate_target  # noqa: E402

QUEUE_PATH = ROOT / "intents" / "daily_queue.jsonl"
STATE_PATH = ROOT / "intents" / "intent_state.json"

PROTOCOL = "ace.intent.pool.v1"

REQUIRED_FIELDS = ("intent_id", "question", "why_now", "expected_result", "verification_method")
DELIVERY_METHODS = {"file_exists_nonempty", "schema_valid_json", "tests_pass", "user_accepted"}

#: 意志生命周期。``blocked`` 不是终态——有新证据时允许回到 candidate。
LIFECYCLE_STATES = (
    "candidate",
    "injected",
    "active",
    "verified",
    "fulfilled",
    "archived",
    "blocked",
    "withdrawn",
)

TERMINAL_STATES = {"fulfilled", "archived", "withdrawn"}

#: Order matters only for speed; the scan covers terminal states on purpose so a
#: consumed intent can never be re-injected.
SEARCH_ORDER = ("pending", "active", "review", "approved", "blocked", "archived", "rejected", "graveyard")
SEARCH_LIMIT = 100000

#: Ordered from oldest work to most recent, so a tag scan that matches an intent
#: twice returns the task that was created *last*. SEARCH_ORDER is grouped by
#: status, which made it return whichever archived task happened to sort first
#: -- a different answer from the recorded task_id, and the disagreement is what
#: let a consumed will look like a candidate again.
NEWEST_FIRST = (
    "active", "review", "approved", "pending", "blocked",
    "graveyard", "rejected", "archived",
)


def _now() -> str:
    return datetime.now().isoformat()


def load_queue(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    if path is None:
        path = QUEUE_PATH
    if not path.exists():
        return []
    intents: List[Dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = raw.strip()
        if not raw or raw.startswith("//"):
            continue
        try:
            intents.append(json.loads(raw))
        except json.JSONDecodeError:
            print(f"[intent] 跳过第 {line_no} 行：不是合法 JSON", file=sys.stderr)
    return intents


def validate_intent(intent: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(intent, dict):
        return ["intent_must_be_object"]
    for field in REQUIRED_FIELDS:
        if not str(intent.get(field) or "").strip():
            errors.append(f"{field}_required")
    method = str(intent.get("verification_method") or "").strip()
    if method and method not in DELIVERY_METHODS:
        errors.append("verification_method_not_deliverable")
    state = str(intent.get("state") or "candidate").strip()
    if state not in LIFECYCLE_STATES:
        errors.append("state_unknown")
    if method in DELIVERY_METHODS and not str(intent.get("delivery_path") or "").strip():
        errors.append("delivery_path_required_for_deliverable_verification")
    return errors


def load_state(path: Optional[Path] = None) -> Dict[str, Any]:
    if path is None:
        path = STATE_PATH
    if not path.exists():
        return {"protocol": PROTOCOL, "intents": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"protocol": PROTOCOL, "intents": {}}


def save_state(state: Dict[str, Any], path: Optional[Path] = None) -> None:
    if path is None:
        path = STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def intent_tag(intent_id: str) -> str:
    return f"intent:{intent_id}"


def _task_id_order(task_id: str) -> tuple:
    """Sortable key for a task id whose tail is a zero-padded daily counter."""
    parts = str(task_id or "").rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return (parts[0], int(parts[1]))
    return (str(task_id or ""), -1)


def find_intent_task(pool: TaskPool, intent_id: str) -> Optional[Dict[str, Any]]:
    """Reverse-lookup the task a given intent produced, newest first.

    Terminal states are searched too: without them a consumed intent reads back
    as ``candidate`` and gets injected a second time. Newest-first ordering
    matters when the same intent somehow produced more than one task.
    """
    tag = intent_tag(intent_id)
    best: Optional[Dict[str, Any]] = None
    best_key: Optional[tuple] = None
    for status in NEWEST_FIRST:
        for task in pool.list_tasks(status=status, limit=SEARCH_LIMIT):
            if tag not in (task.tags or []):
                continue
            # Prefer creation time, fall back to the task id. Task ids embed a
            # zero-padded daily counter, so the numeric part orders same-day
            # tasks correctly; comparing them as plain strings would order
            # "RQ-...-09" above "RQ-...-10".
            key = (str(task.created_at or ""), _task_id_order(task.task_id))
            if best_key is None or key > best_key:
                best_key = key
                best = {"task_id": task.task_id, "status": task.status}
    return best


def _delivery_verified(task: Any) -> Optional[bool]:
    """True/False when the delivery gate reached a verdict, None if never ran."""
    outputs = getattr(task, "outputs", None)
    if not isinstance(outputs, dict):
        return None
    delivery = outputs.get("delivery")
    if not isinstance(delivery, dict):
        return None
    verification = delivery.get("verification")
    if not isinstance(verification, dict):
        return None
    return verification.get("satisfied") is True


def locate_intent_task(
    pool: TaskPool, intent_id: str, state: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Find the task an intent produced, including terminal ones.

    The recorded ``task_id`` is authoritative and cheap. The tag scan is only a
    fallback for a lost state file -- and it must cover archived and graveyard
    tasks too. When it did not, an intent whose task had already been archived
    read back as ``candidate`` and got injected a second time, which is exactly
    the blind re-injection this layer exists to prevent.
    """
    record = (state or {}).get("intents", {}).get(intent_id) or {}
    task_id = str(record.get("task_id") or "").strip()
    if task_id:
        task = pool.load_task(task_id)
        if task is not None:
            return {"task_id": task.task_id, "status": task.status, "delivery_verified": _delivery_verified(task)}
    found = find_intent_task(pool, intent_id)
    if found is None:
        return None
    task = pool.load_task(found["task_id"])
    found["delivery_verified"] = _delivery_verified(task) if task else None
    return found


def derive_state(
    intent: Dict[str, Any], pool: TaskPool, state: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Resolve the truthful lifecycle state of one intent from the live pool."""
    intent_id = str(intent.get("intent_id") or "")
    declared = str(intent.get("state") or "candidate").strip()
    if declared in TERMINAL_STATES:
        return {"state": declared, "reason": "declared_terminal_in_queue"}

    linked = locate_intent_task(pool, intent_id, state)
    if linked is None:
        return {"state": "candidate", "reason": "no_task_created_yet", "task": None}

    task_status = linked["status"]
    if task_status == "archived":
        if linked.get("delivery_verified") is False:
            # Archived without the promised artifact. Do not call it fulfilled;
            # the intent stays open so a later round can retry with new evidence.
            return {"state": "blocked", "reason": "archived_without_delivery", "task": linked}
        return {"state": "fulfilled", "reason": "task_archived", "task": linked}
    if task_status == "blocked":
        return {"state": "blocked", "reason": "task_blocked", "task": linked}
    if task_status in {"pending", "active", "review", "approved"}:
        return {"state": "active", "reason": f"task_{task_status}", "task": linked}
    if task_status in {"graveyard", "rejected"}:
        return {"state": "withdrawn", "reason": f"task_{task_status}", "task": linked}
    return {"state": "injected", "reason": f"task_{task_status}", "task": linked}


def build_target(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Map one intent onto the existing ace.target.inject.v1 payload shape."""
    return {
        "protocol": "ace.target.inject.v1",
        "title": str(intent["question"])[:200],
        "hypothesis": str(intent.get("why_now", "")),
        "expected_output": str(intent["delivery_path"]),
        "success_metric": str(intent["verification_method"]),
        "priority": str(intent.get("priority", "medium")),
        "domain": str(intent.get("domain", "document")),
        "why_now": str(intent.get("why_now", "external_intent")),
        "tags": list(intent.get("tags", [])) + [intent_tag(str(intent["intent_id"]))],
    }


def rank_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Oldest worth-first, then declared priority. Deterministic, no randomness."""
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(
        candidates,
        key=lambda item: (
            order.get(str(item["intent"].get("priority", "medium")), 9),
            str(item["intent"].get("added_at", "")),
        ),
    )


def count_external_in_flight(pool: TaskPool) -> Dict[str, Any]:
    """In-flight work that can actually deliver something.

    Self-observation tasks occupy ``pending`` but by construction can never
    produce a physical artifact. Counting them against external capacity is how
    ACE ends up full of its own noise while no external will ever get a slot.
    """
    total = 0
    external = 0
    for status in ("pending", "active", "review"):
        for task in pool.list_tasks(status=status, limit=200):
            total += 1
            tags = task.tags or []
            outputs = task.outputs if isinstance(task.outputs, dict) else {}
            delivery = outputs.get("delivery")
            if isinstance(delivery, dict) and str(delivery.get("required_path") or "").strip():
                external += 1
            elif any(str(tag).startswith("intent:") for tag in tags):
                external += 1
    return {"in_flight": total, "external_in_flight": external}


def assess(
    pool: TaskPool,
    queue: List[Dict[str, Any]],
    capacity: int,
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    stats = pool.get_stats()
    by_status = stats.get("by_status", {})
    load = count_external_in_flight(pool)

    evaluated: List[Dict[str, Any]] = []
    eligible: List[Dict[str, Any]] = []
    for intent in queue:
        errors = validate_intent(intent)
        if errors:
            evaluated.append({"intent_id": intent.get("intent_id"), "eligible": False, "errors": errors})
            continue
        resolved = derive_state(intent, pool, state)
        record = {
            "intent_id": str(intent["intent_id"]),
            "question": str(intent["question"]),
            "state": resolved["state"],
            "state_reason": resolved["reason"],
            "task": resolved.get("task"),
            "eligible": resolved["state"] == "candidate",
        }
        evaluated.append(record)
        if record["eligible"]:
            eligible.append({"intent": intent, "resolved": resolved})

    return {
        "protocol": PROTOCOL,
        "evaluated_at": _now(),
        "pool": {
            "pending": by_status.get("pending", 0),
            "active": by_status.get("active", 0),
            "review": by_status.get("review", 0),
            "approved": by_status.get("approved", 0),
            "blocked": by_status.get("blocked", 0),
            "in_flight": load["in_flight"],
            "external_in_flight": load["external_in_flight"],
            "capacity": capacity,
        },
        "evaluated": evaluated,
        "eligible": eligible,
        "in_flight": load["external_in_flight"],
    }


def decide(report: Dict[str, Any]) -> Dict[str, Any]:
    if report["in_flight"] >= report["pool"]["capacity"]:
        return {
            "outcome": "HEALTHY_IDLE",
            "reason": "external_backlog_at_capacity",
            "external_in_flight": report["in_flight"],
        }
    if not report["eligible"]:
        return {
            "outcome": "NO_VALID_INTENT",
            "reason": "no_intent_in_candidate_state",
            "evaluated": len(report["evaluated"]),
        }
    ranked = rank_candidates(report["eligible"])[0]
    intent = ranked["intent"]
    return {
        "outcome": "INJECT",
        "reason": "highest_priority_candidate_intent",
        "intent_id": str(intent["intent_id"]),
        "question": str(intent["question"]),
        "why_now": str(intent.get("why_now", "")),
        "priority": str(intent.get("priority", "medium")),
    }


def inject_selected(intent: Dict[str, Any], pool: TaskPool, state: Dict[str, Any]) -> Dict[str, Any]:
    intent_id = str(intent["intent_id"])

    # Last line of defence against blind re-injection. The assess() pass should
    # already have made this unreachable; if it ever fires, the recorded state
    # and the live pool disagree and we stop rather than create a twin task.
    existing = locate_intent_task(pool, intent_id, state)
    if existing is not None:
        return {
            "outcome": "REFUSED_ALREADY_INJECTED",
            "intent_id": intent_id,
            "reason": "a_task_already_carries_this_intent",
            "task": existing,
        }

    target = build_target(intent)
    errors = validate_target(target)
    if errors:
        return {"outcome": "INVALID_TARGET", "errors": errors, "intent_id": intent_id}

    # Inject into the caller's pool, not inject_target's production default:
    # the daemon holds a pool already, and a test must never write to the real
    # task_pool just because it exercised the scheduler.
    receipt = inject(target, pool=pool)
    prior = (state.get("intents", {}) or {}).get(intent_id) or {}
    history = list(prior.get("history", []))
    history.append({"state": "injected", "at": _now(), "task_id": receipt["task_id"]})
    state.setdefault("intents", {})[intent_id] = {
        "state": "injected",
        "question": str(intent["question"]),
        "delivery_path": str(intent["delivery_path"]),
        "verification_method": str(intent["verification_method"]),
        "task_id": receipt["task_id"],
        "injected_at": _now(),
        "history": history,
    }
    return {"outcome": "INJECTED", "intent_id": intent_id, "receipt": receipt}


#: Progress order. An observation may move an intent forward along this ladder,
#: never backward. Without it a single `candidate` observation could overwrite a
#: recorded `fulfilled` and the next run would re-inject an already-consumed will.
STATE_RANK = {
    "candidate": 0,
    "injected": 1,
    "active": 2,
    "blocked": 2,
    "verified": 3,
    "fulfilled": 4,
    "archived": 5,
    "withdrawn": 5,
}


def record_observations(state: Dict[str, Any], report: Dict[str, Any]) -> None:
    """Persist each intent's observed lifecycle state so history accumulates.

    Two guards make this safe to call repeatedly:

    * A stale observation can never demote a recorded state. This mattered in
      practice: an intent whose task was already archived read back as
      ``candidate`` for one pass, and writing that over ``fulfilled`` made the
      next pass re-inject an already-consumed will.
    * ``task_id`` is never blanked by an observation that carries no task, so a
      lost link cannot erase the only pointer to the task that carried the will.
    """
    for item in report["evaluated"]:
        intent_id = item.get("intent_id")
        if not intent_id or item.get("errors"):
            continue
        record = state.setdefault("intents", {}).setdefault(intent_id, {"history": []})
        record["question"] = item.get("question") or record.get("question", "")
        task = item.get("task") or {}
        observed = str(item["state"])
        prior = str(record.get("state") or "candidate")
        # Keep the recorded task_id when this observation has none.
        record["task_id"] = task.get("task_id") or record.get("task_id")
        history = record.setdefault("history", [])
        regress = STATE_RANK.get(observed, 0) < STATE_RANK.get(prior, 0)
        if regress:
            # Demotion: keep the truth, record why the observation was rejected.
            # Guarded on ``prior``, not on history being non-empty: a state file
            # whose history was trimmed must still refuse to go backwards.
            history.append(
                {
                    "state": observed,
                    "reason": item["state_reason"],
                    "task_id": task.get("task_id"),
                    "at": _now(),
                    "rejected": f"would_demote_from_{prior}",
                }
            )
            continue
        if history and history[-1].get("state") == observed:
            continue
        history.append(
            {
                "state": observed,
                "reason": item["state_reason"],
                "task_id": task.get("task_id"),
                "at": _now(),
            }
        )
        record["state"] = observed
        if item.get("state_reason") == "task_archived":
            record.setdefault("delivery_path", record.get("delivery_path"))
            record["archived_at"] = _now()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the ACE intent pool and inject at most one intent.")
    parser.add_argument("--status", action="store_true", help="report only, never inject")
    parser.add_argument("--capacity", type=int, default=3, help="max in-flight tasks ACE should hold")
    parser.add_argument("--queue", default=str(QUEUE_PATH))
    parser.add_argument("--state", default=str(STATE_PATH))
    args = parser.parse_args(argv)

    pool = TaskPool(str(ROOT / "task_pool"))
    queue = load_queue(Path(args.queue))
    state = load_state(Path(args.state))

    report = assess(pool, queue, args.capacity, state)
    decision = decide(report)

    output = {
        "protocol": PROTOCOL,
        "outcome": decision["outcome"],
        "reason": decision["reason"],
        "pool": report["pool"],
        "intents": [
            {
                "intent_id": item.get("intent_id"),
                "state": item.get("state"),
                "state_reason": item.get("state_reason"),
                "task": item.get("task"),
                "errors": item.get("errors"),
                "eligible": bool(item.get("eligible")),
            }
            for item in report["evaluated"]
        ],
    }

    # Observations describe the pool as assess() saw it, which is before any
    # injection. Record them first, or the "injected" entry gets overwritten by
    # a stale "candidate" and the state file trails the truth.
    record_observations(state, report)

    if decision["outcome"] == "INJECT" and not args.status:
        chosen = next(
            item["intent"]
            for item in report["eligible"]
            if str(item["intent"]["intent_id"]) == decision["intent_id"]
        )
        injection = inject_selected(chosen, pool, state)
        output["injection"] = injection
        if injection["outcome"] == "INJECTED":
            output["outcome"] = "INJECTED"

    save_state(state, Path(args.state))

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())