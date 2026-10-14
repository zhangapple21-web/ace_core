"""Ruin Smelter最小实现 — 复用现有Task重试字段，不另起调度器.

复用锅:
- core/task.py: retry_count/rework_count/unchanged_review_count/consecutive_rework_claims/failure_reason/block_type
- core/task_roles.py: non_convergent_disposition + terminal_non_convergent
- core/execution_discipline.py: observe→clarify→plan→route→execute→verify→review→stop
- Validator/Guardian/TaskPool状态转换：唯一变更生产状态的通道

规则（用户定稿）:
- 证据不足→补全，不重复提交相同论证（evidence_signature未变不得重进）
- 假设错误→退回研究修正假设
- 架构冲突→判官组织边界/依赖检查，最小验证
- 执行失败→区分code/env/model/external选修复路径
- 持续不收敛→熔断manual_gate_blocked，生成修复方向，必要时判官/高推理仲裁，
  仅证据/方法/假设实质变化才允许重进；禁止只重置计数或换ID。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict


def _text(v: Any) -> str:
    return str(v or "").strip()


def _hash(v: Any) -> str:
    return hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def evidence_signature(task: Any) -> str:
    ev = getattr(task, "evidence", []) or []
    outs = getattr(task, "outputs", {}) or {}
    last = outs.get("last_validator_result", {}) if isinstance(outs, dict) else {}
    sig_src = outs.get("last_validated_evidence_signature") or last.get("evidence_signature", "")
    if sig_src:
        return str(sig_src)[:32]
    return _hash([str(e.get("content", "")[:200]) if isinstance(e, dict) else str(e)[:200] for e in ev[:5]])


def classify(task: Any) -> Dict[str, Any]:
    """失败分类，纯函数，不改状态."""
    rework = int(getattr(task, "rework_count", 0) or 0)
    retry = int(getattr(task, "retry_count", 0) or 0)
    unchanged = int(getattr(task, "unchanged_review_count", 0) or 0)
    consec = int(getattr(task, "consecutive_rework_claims", 0) or 0)
    fail = (_text(getattr(task, "failure_reason", "")) + " " + _text(getattr(task, "blocked_reason", ""))).lower()
    outs = getattr(task, "outputs", {}) or {}
    last = outs.get("last_validator_result", {}) if isinstance(outs, dict) else {}
    objections = last.get("objections", []) if isinstance(last, dict) else []
    # 执行失败子类
    if any(k in fail for k in ("timeout", "超时", "connection", "env", "环境", "disk", "权限")):
        sub = "env"
    elif any(k in fail for k in ("traceback", "exception", "null", " traceback", "代码", "bug", "returncode")):
        sub = "code"
    elif any(k in fail for k in ("429", "quota", "rate limit", "model", "模型")):
        sub = "model"
    elif any(k in fail for k in ("external", "外部", "upstream", "上游", "api")):
        sub = "external"
    else:
        sub = "unknown"
    # 主类
    if consec >= 2 or rework >= 5 or (unchanged >= 3 and rework >= 2):
        main = "non_convergent"
    elif objections and retry == 0 and rework >= 1:
        main = "evidence_insufficient"
    elif "假设" in fail or "hypothesis" in fail:
        main = "hypothesis_wrong"
    elif "冲突" in fail or "边界" in fail or "依赖" in fail or "arch" in fail:
        main = "arch_conflict"
    elif retry >= 1 or sub != "unknown":
        main = "exec_failure"
    else:
        main = "evidence_insufficient"
    return {"class": main, "sub": sub, "rework": rework, "retry": retry,
            "unchanged": unchanged, "consec": consec, "objections": len(objections)}


def substantive_change(task: Any, new_evidence_hash: str = "", new_method: str = "", new_hypothesis: str = "") -> Dict[str, Any]:
    """只有证据/方法/假设实质变化才允许重进同一验证循环."""
    old_sig = evidence_signature(task)
    old_hyp = _text(getattr(task, "hypothesis", ""))
    outs = getattr(task, "outputs", {}) or {}
    old_method = _text((outs.get("execution_discipline", {}) or {}).get("last_event", ""))
    changed = []
    if _text(new_evidence_hash) and _text(new_evidence_hash)[:32] != old_sig[:32]:
        changed.append("evidence")
    if _text(new_method) and _text(new_method) != old_method:
        changed.append("method")
    if _text(new_hypothesis) and _text(new_hypothesis) != old_hyp:
        changed.append("hypothesis")
    return {"changed": changed, "allowed": len(changed) > 0, "old_sig": old_sig}


def fuse(task: Any, new_evidence_hash: str = "", new_method: str = "", new_hypothesis: str = "") -> Dict[str, Any]:
    """熔炼决策：返回动作+最小验证+修复方向，不直接改生产状态."""
    cls = classify(task)
    chg = substantive_change(task, new_evidence_hash, new_method, new_hypothesis)
    at = datetime.now(timezone.utc).isoformat()
    if cls["class"] == "non_convergent":
        if not chg["allowed"]:
            return {"action": "circuit_break", "block_type": "manual_gate_blocked",
                    "reason": "相同证据/方法/假设重复验证，禁止重进；需实质变化或人工/外部新证据",
                    "repair_direction": "换方法或补新证据后走reopen_task，判官仲裁最小验证",
                    "need_judge": True, "at": at, "class": cls, "change": chg}
        return {"action": "reopen_with_new_proof", "block_type": "",
                "reason": f"检测到实质变化{chg['changed']}，允许经reopen重进一次",
                "need_judge": True, "at": at, "class": cls, "change": chg}
    if cls["class"] == "evidence_insufficient":
        return {"action": "supplement_evidence", "reason": "补全证据，不重复提交相同论证",
                "next_verify": "evidence_signature变化后重验", "at": at, "class": cls, "change": chg}
    if cls["class"] == "hypothesis_wrong":
        return {"action": "back_to_research", "reason": "退回研究修正假设后再验证",
                "at": at, "class": cls, "change": chg}
    if cls["class"] == "arch_conflict":
        return {"action": "judge_arbitration", "reason": "判官组织边界/依赖检查，形成最小验证",
                "next_verify": "最小验证通过后经Validator/Guardian", "need_judge": True,
                "at": at, "class": cls, "change": chg}
    # exec_failure
    fix_map = {"code": "修代码分支回归", "env": "修环境/重试退避", "model": "换模型fallback",
               "external": "等外部或降级", "unknown": "先补日志证据再定路径"}
    return {"action": "fix_path", "fix": fix_map.get(cls["sub"], "先补日志证据再定路径"),
            "at": at, "class": cls, "change": chg}


def memory_envelope_compat(old_entry: Dict[str, Any]) -> Dict[str, Any]:
    """MLP兼容：旧格式不擅自把未知标成事实；缺字段补UNKNOWN不过期删除治理证据."""
    out = dict(old_entry or {})
    out.setdefault("fact", out.get("summary", "") or "")
    out.setdefault("inference", "")
    out.setdefault("unknown", "UNKNOWN")
    out.setdefault("authority", "observation")
    out.setdefault("scope", "task-local")
    out.setdefault("retention_days", 30)
    out.setdefault("counterevidence", "")
    # 治理/失败复盘/权限证据永不过期删除，只可标记过期不再参与常规检索
    tags = [str(t).lower() for t in (out.get("tags", []) or [])]
    is_audit = any(k in " ".join(tags) for k in ("govern", "guardian", "lesson", "audit", "权限", "复盘"))
    out["audit_preserve"] = bool(is_audit)
    return out


def should_retrieve(entry: Dict[str, Any], now_iso: str = "") -> bool:
    """短保留临时错误到期不再参与常规检索；审计证据保留可查."""
    try:
        created = str(entry.get("created_at", "") or entry.get("at", ""))
        ret = int(entry.get("retention_days", 30))
        if not created:
            return True
        from datetime import datetime as _dt
        c = _dt.fromisoformat(created.replace("Z", "+00:00"))
        n = _dt.fromisoformat(now_iso.replace("Z", "+00:00")) if now_iso else _dt.now(timezone.utc)
        expired = (n - c).days > ret
        if not expired:
            return True
        return bool(entry.get("audit_preserve"))
    except Exception:
        return True
