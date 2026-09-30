"""
任务账本（value ledger）— 每笔计数变更一行，带活指针 + 操作后快照。

来源：OpenStall 考古候选 C4。它解决的具体问题：TaskPool 里
retry_count / rework_count / starvation_age / fencing_token / reference_count
这些可数计数器一直"就地自增"，落盘后没有任何一行能解释"当前值为什么是这个数"。
OpenStall 钱包反面地证明了正确做法：每笔 money op 一行，带 referenceId（活指针）
+ 操作后余额（快照），7 行明细可对账回快照。

三条硬规则：
1. 禁止"只写值不写来源" —— 公开入账口必须带可解析的 ref，ref 解析失败即拒绝入账。
2. 每行 after 快照必须等于 前行 after + 本行 deltas —— 重放可复算（verify_chain）。
3. 落盘前计数器实值必须能被账本重放复现 —— 复现不了即 drift。

旧数据兼容：存量任务没有 ledger，首次接触时种 kind="baseline" 行
（reason="pre_ledger_migration"，after 取落盘前旧值，ref 指向任务文件自身）。
基线之前的历史永久标记为"来源不可审"，由只读对账器单独计数，
不与基线之后的漂移混为一谈。

写口模式（环境变量 ACE_TASK_LEDGER_MODE）：
  off      —— 完全不介入
  shadow   —— 默认。检出未登记漂移时补一行 kind="drift"（记录而非阻断）：
              重放因此始终自洽，漂移变成可数、可审计的产物。
  enforce  —— 检出未登记漂移直接抛 LedgerDriftError，写出失败。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LEDGER_COUNTERS = (
    "reference_count",
    "review_count",
    "retry_count",
    "rework_count",
    "unchanged_review_count",
    "consecutive_rework_claims",
    "starvation_age",
    "fencing_token",
)

LEDGER_KINDS = (
    "baseline",   # 迁移种行：历史值来源不可审
    "event",      # 生命周期 / 领取等带来源的变更
    "consume",    # 消耗型（重试、重做、被引用）
    "hold",       # 占用（与 release/refund 成对）
    "release",    # 释放
    "refund",     # 回补
    "adjust",     # 显式人工修正
    "drift",      # 写口检出但没人登记的漂移
)

REF_TYPES = ("file", "line", "task", "pool_file", "self", "command")

MODES = ("off", "shadow", "enforce")


class LedgerError(ValueError):
    pass


class LedgerDriftError(LedgerError):
    def __init__(self, task_id: str, drift: Dict[str, Dict[str, Any]]):
        self.task_id = task_id
        self.drift = drift
        detail = ", ".join(
            f"{name}: expected={info['expected']} actual={info['actual']}"
            for name, info in sorted(drift.items())
        )
        super().__init__(f"task_ledger_drift:{task_id}:{detail}")


def ledger_mode() -> str:
    mode = str(os.environ.get("ACE_TASK_LEDGER_MODE") or "shadow").strip().lower()
    return mode if mode in MODES else "shadow"


def counter_values(task: Any) -> Dict[str, int]:
    values: Dict[str, int] = {}
    for name in LEDGER_COUNTERS:
        raw = getattr(task, name, None)
        values[name] = int(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else 0
    return values


def prior_counters(path: Path) -> Optional[Dict[str, int]]:
    """读落盘前的旧快照，拿到计数器的历史值。文件不存在 = 新任务。"""
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    out: Dict[str, int] = {}
    for name in LEDGER_COUNTERS:
        raw = record.get(name)
        out[name] = int(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else 0
    return out


def _safe_statuses(pool_dir: Path) -> List[str]:
    try:
        return [entry.name for entry in pool_dir.iterdir() if entry.is_dir()]
    except OSError:
        return []


def resolve_ref(ref: Dict[str, Any], pool_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """活指针必须当场可解析；解析不了就不许入账。"""
    if not isinstance(ref, dict):
        return False, "ledger_ref_required"
    kind = str(ref.get("type") or "")
    if kind not in REF_TYPES:
        return False, f"ledger_ref_type_unknown:{kind}"
    if kind in ("file", "line"):
        raw_path = str(ref.get("path") or "")
        if not raw_path:
            return False, "ledger_ref_path_missing"
        path = Path(raw_path)
        if not path.exists():
            return False, f"ledger_ref_dead:{raw_path}"
        if kind == "line":
            count = int(ref.get("line") or 0)
            if count <= 0:
                return False, "ledger_ref_line_missing"
            try:
                total = sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))
            except OSError:
                return False, f"ledger_ref_unreadable:{raw_path}"
            if count > total:
                return False, f"ledger_ref_line_out_of_range:{count}>{total}"
        return True, ""
    if kind in ("task", "pool_file"):
        if kind == "pool_file":
            raw_path = str(ref.get("path") or "")
            if not raw_path:
                return False, "ledger_ref_path_missing"
            return (True, "") if Path(raw_path).exists() else (False, f"ledger_ref_dead:{raw_path}")
        task_id = str(ref.get("task_id") or "")
        if not task_id:
            return False, "ledger_ref_task_id_missing"
        if pool_dir is None:
            return True, ""
        for status in _safe_statuses(pool_dir):
            if (pool_dir / status / f"{task_id}.json").exists():
                return True, ""
        return False, f"ledger_ref_task_absent:{task_id}"
    if kind == "command":
        if not str(ref.get("argv") or "").strip():
            return False, "ledger_ref_command_missing"
        return True, ""
    # self：指向任务自身，写出后必然存在
    return True, ""


def _self_ref(task: Any, path: Path) -> dict:
    """行内自指针：用 task_id 而不是文件路径，任务换状态目录后指针仍然活着。"""
    task_id = str(getattr(task, "task_id", "") or "")
    if task_id:
        return {"type": "task", "task_id": task_id, "file": str(path)}
    return {"type": "pool_file", "path": str(path)}


def next_entry_id(task: Any) -> int:
    seq = int(getattr(task, "ledger_seq", 0) or 0)
    rows = getattr(task, "ledger", None) or []
    return max(seq, len(rows)) + 1


def _rows(task: Any) -> List[Dict[str, Any]]:
    rows = getattr(task, "ledger", None)
    if rows is None:
        rows = []
        setattr(task, "ledger", rows)
    return rows


def _push(task: Any, row: Dict[str, Any]) -> Dict[str, Any]:
    rows = _rows(task)
    row["entry_id"] = next_entry_id(task)
    rows.append(row)
    setattr(task, "ledger_seq", row["entry_id"])
    return row


def replay(task: Any) -> Dict[str, int]:
    """重放账本 → 每个计数器应有的当前值。"""
    expected: Dict[str, int] = {}
    for row in getattr(task, "ledger", None) or []:
        if not isinstance(row, dict):
            continue
        for name, value in (row.get("after") or {}).items():
            try:
                expected[name] = int(value)
            except (TypeError, ValueError):
                continue
    return expected


def ensure_baseline(task: Any, path: Path, prior: Optional[Dict[str, int]] = None) -> Optional[Dict[str, Any]]:
    """把尚未入账的计数器补成基线行；旧值优先取落盘前快照。"""
    expected = replay(task)
    missing = [name for name in LEDGER_COUNTERS if name not in expected]
    if not missing:
        return None
    values = counter_values(task)
    if prior:
        values.update({name: int(prior.get(name, 0) or 0) for name in missing if name in prior})
    row = {
        "entry_id": 0,
        "kind": "baseline",
        "actor": "task_ledger",
        "at": datetime.now().isoformat(),
        "reason": "pre_ledger_migration",
        "ref": _self_ref(task, path),
        "deltas": {},
        "after": {name: int(values[name]) for name in missing},
    }
    return _push(task, row)


def append_entry(
    task: Any,
    kind: str,
    actor: str,
    deltas: Dict[str, int],
    reason: str,
    ref: Dict[str, Any],
    pool_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """公开入账口：必须带可解析 ref；after 由 前行快照 + delta 算出并须与实值相符。"""
    if kind not in LEDGER_KINDS:
        raise LedgerError(f"ledger_kind_unknown:{kind}")
    if not isinstance(deltas, dict):
        raise LedgerError("ledger_deltas_required")
    if not deltas and kind not in ("release", "refund"):
        # 平账行可以不值数（它只负责与 hold 成对），其余种类必须带数
        raise LedgerError("ledger_deltas_required")
    if not str(reason or "").strip():
        raise LedgerError("ledger_reason_required")
    ok, error = resolve_ref(ref, pool_dir)
    if not ok:
        raise LedgerError(error)
    expected = replay(task)
    actual = counter_values(task)
    snapshot: Dict[str, int] = {}
    for name, delta in deltas.items():
        if name not in LEDGER_COUNTERS:
            raise LedgerError(f"ledger_counter_unknown:{name}")
        if name not in expected:
            raise LedgerError(f"ledger_counter_unbaselined:{name}")
        delta = int(delta)
        computed = int(expected[name]) + delta
        if computed != int(actual[name]):
            raise LedgerError(f"ledger_provenance_mismatch:{name}:replay={computed} actual={actual[name]}")
        snapshot[name] = computed
    row = {
        "entry_id": 0,
        "kind": kind,
        "actor": str(actor or ""),
        "at": datetime.now().isoformat(),
        "reason": str(reason),
        "ref": dict(ref),
        "deltas": {name: int(value) for name, value in deltas.items()},
        "after": snapshot,
    }
    return _push(task, row)


def verify_chain(task: Any) -> List[Dict[str, Any]]:
    """逐行校验 after == 前行 after + deltas（快照与流水不得脱钩）。"""
    broken: List[Dict[str, Any]] = []
    running: Dict[str, int] = {}
    for row in getattr(task, "ledger", None) or []:
        if not isinstance(row, dict):
            broken.append({"entry_id": None, "error": "ledger_row_not_object"})
            continue
        for name, delta in (row.get("deltas") or {}).items():
            base = running.get(name)
            after_value = (row.get("after") or {}).get(name)
            if base is not None and after_value is not None:
                if int(base) + int(delta) != int(after_value):
                    broken.append({
                        "entry_id": row.get("entry_id"),
                        "counter": name,
                        "error": f"ledger_chain_break:{base}+{delta}!={after_value}",
                    })
        for name, value in (row.get("after") or {}).items():
            try:
                running[name] = int(value)
            except (TypeError, ValueError):
                continue
    return broken


def reconcile(task: Any) -> Dict[str, Dict[str, Any]]:
    """计数器实值 vs 账本重放值 的差异表；空表 = 账实相符。"""
    expected = replay(task)
    actual = counter_values(task)
    drift: Dict[str, Dict[str, Any]] = {}
    for name, value in actual.items():
        if expected.get(name) != value:
            drift[name] = {"expected": expected.get(name), "actual": value}
    return drift


def _hold_key(row: Dict[str, Any]) -> str:
    ref = row.get("ref") or {}
    claim_id = ref.get("claim_id") if isinstance(ref, dict) else None
    if claim_id:
        return f"claim:{claim_id}"
    return json.dumps(ref, sort_keys=True, ensure_ascii=False)


def unclosed_holds(task: Any) -> List[Dict[str, Any]]:
    """hold 没配对 release/refund = 未平仓（对标 OpenStall delivered 冻结态）。"""
    open_holds: Dict[str, Dict[str, Any]] = {}
    for row in getattr(task, "ledger", None) or []:
        if not isinstance(row, dict):
            continue
        key = _hold_key(row)
        if row.get("kind") == "hold":
            open_holds[key] = row
        elif row.get("kind") in ("release", "refund"):
            open_holds.pop(key, None)
    return list(open_holds.values())


def record_drift(task: Any, path: Path, drift: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """shadow 模式：给未登记的漂移补一行，保证重放自洽且漂移可数。"""
    added = []
    for name, info in sorted(drift.items()):
        expected = int(info.get("expected") or 0)
        actual = int(info.get("actual") or 0)
        row = {
            "entry_id": 0,
            "kind": "drift",
            "actor": "write_port",
            "at": datetime.now().isoformat(),
            "reason": "unregistered_counter_change",
            "ref": _self_ref(task, path),
            "deltas": {name: actual - expected},
            "after": {name: actual},
        }
        added.append(_push(task, row))
    return added


def write_port_gate(task: Any, path: Path, pool_dir: Optional[Path] = None) -> Dict[str, Any]:
    """唯一落盘口的账本检查：先补基线，再对账；shadow 补行、enforce 抛出、off 直通。"""
    mode = ledger_mode()
    if mode == "off":
        return {"mode": mode, "action": "skip"}
    ensured = ensure_baseline(task, Path(path), prior=prior_counters(Path(path)))
    drift = reconcile(task)
    if not drift:
        return {"mode": mode, "action": "baseline_seeded" if ensured else "clean"}
    if mode == "enforce":
        raise LedgerDriftError(getattr(task, "task_id", "?"), drift)
    record_drift(task, Path(path), drift)
    return {"mode": mode, "action": "drift_recorded", "drift": drift}
