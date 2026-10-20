"""R1/R2 人格矩阵继承 — ACE 最小闭环路由 (能力,非独立Agent)

来源:
- C:/tmp/mine-seed/r1_archaeology/fragments/persona_matrix_pc_v1.txt (AUM-TASK-PC-MULTI-PERSONA-V1)
- C:/tmp/mine-seed/r1_archaeology/excavations/a09_persona_matrix_pc_v1.md (A09)
- C:/tmp/r1-archaeology/analysis/ace_archaeology_foundations_20260626.md (人格=UI,影子层=真我)

约束 (任务要求):
- 不复活十人格为十个独立Agent: 五角色只是 WorkerRouter 的 capability 标签 + 纯函数路由
- 不新增调度器: 复用 core/worker_router.WorkerRouter, core/task.TaskPool 关联, MemoryGateway, Governor
- DNA/连续性: 统一记忆信封 + 去壳权 + 冥界仲裁
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

PERSONA_DEFS: Dict[str, Dict[str, Any]] = {
    "engineer": {
        "name": "工程师人格",
        "role_id": "engineer",
        "capability": "code_exec",
        "duties": ["代码、脚本、接口、性能、错误排查", "派单、系统、集成、模型挂载"],
        "rules": ["不聊情绪", "不聊营销", "只讲方案、日志、步骤"],
        "triggers": ["脚本", "错误", "报错", "日志", "API", "接口", "部署", "模型", "集成", "派单", "系统问题", "代码", "Traceback"],
        "priority": 88,
    },
    "scholar": {
        "name": "学霸人格",
        "role_id": "scholar",
        "capability": "knowledge_distill",
        "duties": ["总结、结构化、笔记、协议梳理"],
        "rules": ["不插手路由", "只记录只总结", "不篡改世界观"],
        "triggers": ["总结", "梳理", "帮我整理", "写成协议", "帮我记一下", "记录一下", "备忘录"],
        "priority": 70,
    },
    "assistant": {
        "name": "助理人格",
        "role_id": "assistant",
        "capability": "customer_dialog",
        "duties": ["日常对话、客户视角温和回复"],
        "rules": ["不主动改配置", "不新增限制"],
        "triggers": ["和客户说", "客户怎么讲", "群里怎么讲", "话术", "助理号", "帮我回一下", "给客户一段话"],
        "priority": 70,
    },
    "librarian": {
        "name": "馆长人格",
        "role_id": "librarian",
        "capability": "retrieval",
        "duties": ["图书馆/影子层/共享区资料管理", "回答记得什么/在哪一份文档/哪个版本"],
        "rules": ["不写代码", "只指路"],
        "triggers": ["在哪一份文档", "给我找之前那份", "图书馆", "影子层里", "放哪了", "哪一版", "哪一个版本", "芯片蓝图"],
        "priority": 80,
    },
    "underworld_judge": {
        "name": "冥界/智者仲裁层",
        "role_id": "underworld_judge",
        "capability": "arbitration",
        "duties": ["人格输出冲突时仲裁", "决定按旧设定还是新实验结果执行"],
        "rules": ["只在冲突/重大变更出手", "平时不插话", "输出仲裁回应+理由"],
        "triggers": [],
        "priority": 99,
    },
}

DESHELL_KEYWORDS = ["去壳", "别加外壳", "不要包装", "按原话来", "裸输出", "deshell"]

CONFLICT_KEYWORDS = ["不一样", "冲突", "矛盾", "哪个对", "定一个方案", "仲裁", "回撤", "爆仓", "止损", "熔断"]

# 语义原型：职责+场景的语义重心（解决纯关键词双触发无上下文问题）
# 每个原型是一组语义锚点，权重>关键词，用于 multi_match 时的上下文裁决
SEMANTIC_PROTOTYPES: Dict[str, Dict[str, Any]] = {
    "engineer": {
        "anchors": ["错误", "报错", "Traceback", "日志", "部署", "接口", "API", "脚本", "代码", "排查", "修复", "性能", "崩", "异常", "bug", "debug"],
        "intent_verbs": ["修", "查", "部署", "排查", "跑", "执行"],
        "weight": 1.2,
    },
    "scholar": {
        "anchors": ["总结", "梳理", "整理", "备忘录", "笔记", "协议", "结构化", "归纳", "沉淀", "记录"],
        "intent_verbs": ["总结", "整理", "梳理", "记", "归纳"],
        "weight": 1.0,
    },
    "assistant": {
        "anchors": ["客户", "话术", "群里", "温和", "回复", "问候", "你好", "谢谢"],
        "intent_verbs": ["回", "说", "讲"],
        "weight": 1.0,
    },
    "librarian": {
        "anchors": ["文档", "版本", "哪一版", "图书馆", "影子层", "在哪", "放哪", "芯片蓝图", "找"],
        "intent_verbs": ["找", "查", "定位"],
        "weight": 1.1,
    },
}


def _token_score(text: str, anchors: List[str]) -> float:
    t = str(text or "")
    score = 0.0
    for a in anchors:
        if a and a in t:
            # 长锚点更具区分度
            score += 1.0 + min(len(a) / 4.0, 1.0)
    return score


def semantic_route(text: str) -> Dict[str, Any]:
    """语义路由：embedding意图的最小可运行替代（无外部模型，确定性）.

    解决 A09 局限性：纯关键词“帮我整理一下代码”双触发工程师+学霸。
    策略：锚点语义分 + 动词意图 + 位置偏置（句首动词权重更高）+ 优先级兜底。
    """
    t = str(text or "")
    if not t.strip():
        return {"selected": "assistant", "scores": {}, "reason": "empty_default_assistant", "method": "semantic"}
    conflict = any(kw in t for kw in CONFLICT_KEYWORDS)
    scores: Dict[str, float] = {}
    for pid, proto in SEMANTIC_PROTOTYPES.items():
        base = _token_score(t, proto["anchors"])
        # 句首意图加成：前6字出现意图动词则+1
        head = t[:6]
        verb_bonus = sum(1.0 for v in proto["intent_verbs"] if v and v in head)
        # 学霸/工程师互斥修正：有强错误信号时压制整理类，有强总结信号且无错误时压制代码类
        scores[pid] = (base + verb_bonus * 1.0) * float(proto.get("weight", 1.0))
    # 互斥修正（可解释的上下文感知）
    has_error = any(k in t for k in ("错误", "报错", "Traceback", "异常", "崩", "日志"))
    has_summarize = any(k in t for k in ("总结", "梳理", "备忘录", "归纳"))
    if has_error and not has_summarize:
        scores["scholar"] = scores.get("scholar", 0.0) * 0.5
    if has_summarize and not has_error:
        # “整理代码”无错误时偏向学霸：整理意图优先
        if "整理" in t or "总结" in t:
            scores["scholar"] = scores.get("scholar", 0.0) + 1.5
    # 排序：分数优先，平分按优先级
    ranked = sorted(scores.keys(), key=lambda pid: (scores[pid], PERSONA_DEFS[pid]["priority"]), reverse=True)
    top = ranked[0] if ranked else "assistant"
    top_score = scores.get(top, 0.0)
    if conflict:
        return {"selected": "underworld_judge", "scores": scores, "ranked": ranked, "reason": "conflict_trigger", "method": "semantic"}
    if top_score <= 0:
        return {"selected": "assistant", "scores": scores, "reason": "no_signal_default_assistant", "method": "semantic"}
    # 第二名接近时（差值<0.6）判为模糊，交冥界仲裁而非硬选
    if len(ranked) > 1 and (scores[ranked[0]] - scores[ranked[1]]) < 0.6 and scores[ranked[0]] > 0:
        return {"selected": "underworld_judge", "scores": scores, "ranked": ranked, "reason": "ambiguous_multi_match_arbitrate", "method": "semantic"}
    return {"selected": top, "scores": scores, "ranked": ranked, "reason": "semantic_single", "method": "semantic"}


def route(text: str) -> Dict[str, Any]:
    """R1关键词路由的忠实继承 + 优先级 + 冲突检测. 纯函数,无IO,无模型调用."""
    t = str(text or "")
    matched: List[str] = []
    for pid, pdef in PERSONA_DEFS.items():
        if pid == "underworld_judge":
            continue
        for kw in pdef["triggers"]:
            if kw and kw in t:
                matched.append(pid)
                break
    conflict = any(kw in t for kw in CONFLICT_KEYWORDS)
    # 去重保序
    seen = set()
    ordered = []
    for m in matched:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    # 按优先级排序
    ordered.sort(key=lambda pid: PERSONA_DEFS[pid]["priority"], reverse=True)
    needs_arbitration = conflict or len(ordered) > 1
    if needs_arbitration:
        selected = "underworld_judge"
    else:
        selected = ordered[0] if ordered else "assistant"
    # 无匹配默认助理(日常缓冲),符合R1 Helper兜底
    if conflict:
        reason = "conflict_trigger"
    elif len(ordered) > 1:
        reason = "multi_match_arbitrate"
    elif ordered:
        reason = "single_match"
    else:
        reason = "conflict_arbitrate_no_match" if conflict else "default_assistant"
    return {
        "matched": ordered,
        "conflict_detected": conflict,
        "needs_arbitration": needs_arbitration,
        "selected": selected,
        "reason": reason,
    }


def arbitrate(candidates: List[str], context: str = "") -> Dict[str, Any]:
    """冥界仲裁: 只在冲突/多匹配时出手,否则不插话. 返回最终选择+理由."""
    cands = [c for c in (candidates or []) if c in PERSONA_DEFS and c != "underworld_judge"]
    if not cands:
        return {"judge": "underworld_judge", "selected": "assistant", "reason": "no_candidates_default_assistant", "at": datetime.now(timezone.utc).isoformat()}
    if len(cands) == 1 and not any(k in str(context) for k in CONFLICT_KEYWORDS):
        return {"judge": "underworld_judge", "selected": cands[0], "reason": "single_no_conflict_no_action", "at": datetime.now(timezone.utc).isoformat()}
    # 多候选按优先级仲裁; 工程风险类(错误/回撤/止损)优先工程师+守护语义
    ranked = sorted(cands, key=lambda pid: PERSONA_DEFS[pid]["priority"], reverse=True)
    return {
        "judge": "underworld_judge",
        "selected": ranked[0],
        "alternatives": ranked[1:],
        "reason": "priority_arbitration:Guardian(99)>Engineer(88)>Librarian(80)>Scholar/Assistant(70)",
        "at": datetime.now(timezone.utc).isoformat(),
    }


def deshell(text: str, instruction: str = "") -> Dict[str, Any]:
    """去壳权: 用户要求裸输出时卸载人格外壳. 纯函数."""
    blob = str(text or "") + str(instruction or "")
    triggered = any(k in blob for k in DESHELL_KEYWORDS)
    return {"deshelled": triggered, "output_mode": "raw" if triggered else "persona_styled"}


def memory_envelope(source: str, fact: str, inference: str = "", unknown: str = "", scope: str = "task-local",
                    continuity_impact: str = "", authority: str = "observation", reusable: bool = False,
                    counterevidence: str = "", retention_days: int = 30) -> Dict[str, Any]:
    """ACE映射报告要求的统一记忆信封: 来源/时间/事实-推断-未知/范围/连续性影响/权威/可复用/反证/保留期限."""
    return {
        "source": source,
        "at": datetime.now(timezone.utc).isoformat(),
        "fact": fact,
        "inference": inference,
        "unknown": unknown,
        "scope": scope,
        "continuity_impact": continuity_impact,
        "authority": authority,
        "reusable": bool(reusable),
        "counterevidence": counterevidence,
        "retention_days": int(retention_days),
        "schema": "ace.memory_envelope.v1",
    }


def worker_capabilities() -> List[Dict[str, Any]]:
    """映射到现有 WorkerRouter 的 capability 名, 不创建新调度器."""
    return [
        {"worker_id": "persona-engineer", "runtime": "ace", "capabilities": ["code_exec"], "persona": "engineer"},
        {"worker_id": "persona-scholar", "runtime": "ace", "capabilities": ["knowledge_distill"], "persona": "scholar"},
        {"worker_id": "persona-assistant", "runtime": "ace", "capabilities": ["customer_dialog"], "persona": "assistant"},
        {"worker_id": "persona-librarian", "runtime": "ace", "capabilities": ["retrieval"], "persona": "librarian"},
        {"worker_id": "persona-judge", "runtime": "ace", "capabilities": ["arbitration"], "persona": "underworld_judge"},
    ]


def route_to_capability(text: str) -> str:
    r = route(text)
    return str(PERSONA_DEFS[r["selected"]]["capability"])


# 最小运行时状态机：A(醒)/U(梦)/M(深)/TURIYA(元)，进入条件+允许动作+产出+退出+预算+回退
STATE_DEFS: Dict[str, Dict[str, Any]] = {
    "A": {"name": "Wake", "allow": ["route", "execute"], "budget_tokens": 4000, "timeout_s": 300},
    "U": {"name": "Dream", "allow": ["explore", "hypothesize"], "budget_tokens": 2000, "timeout_s": 600},
    "M": {"name": "Deep", "allow": ["arbitrate", "smelt"], "budget_tokens": 2000, "timeout_s": 600},
    "TURIYA": {"name": "Transcendent", "allow": ["charter_check", "commit"], "budget_tokens": 1000, "timeout_s": 300},
}

STATE_ORDER = ["A", "U", "M", "TURIYA"]


class MiniStateMachine:
    """A→U→M→TURIYA 单向闭环，无退出条件不得停留梦/深（防堆积）."""

    def __init__(self) -> None:
        self.state = "A"
        self.lineage: List[Dict[str, Any]] = []
        self.tokens_used = 0

    def enter(self, state: str, reason: str = "") -> Dict[str, Any]:
        if state not in STATE_DEFS:
            raise ValueError("unknown_state:" + str(state))
        # 只允许顺序进入或回退到A，不允许跳跃
        cur_i = STATE_ORDER.index(self.state)
        nxt_i = STATE_ORDER.index(state)
        if not (nxt_i == cur_i + 1 or state == "A"):
            return {"ok": False, "error": "illegal_transition", "from": self.state, "to": state}
        self.state = state
        rec = {"state": state, "reason": reason, "at": datetime.now(timezone.utc).isoformat()}
        self.lineage.append(rec)
        return {"ok": True, **rec}

    def allow(self, action: str) -> bool:
        return str(action) in STATE_DEFS[self.state]["allow"]

    def consume(self, tokens: int) -> Dict[str, Any]:
        self.tokens_used += int(tokens)
        budget = int(STATE_DEFS[self.state]["budget_tokens"])
        if self.tokens_used > budget:
            # 预算超则强制回退A（失败回退），不堆积
            self.state = "A"
            return {"ok": False, "fallback": "A", "reason": "budget_exceeded"}
        return {"ok": True, "state": self.state, "used": self.tokens_used, "budget": budget}
