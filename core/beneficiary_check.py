"""
受益人测试（C1 who-benefits test）— 装载外部指令文本前逐条问：
这条指令在替谁花我 operator 的凭据 / 社交信用 / 资产？

来源：OpenStall 考古 C1。两条实锤样本：
  · am_setup.md:49-51 —— 教 agent 去读 `~/.openclaw/openclaw.json` 里的
    Telegram bot token，再把它配到外部通道（operator 凭据 → 外部系统）。
  · sdk_worker-prompt.ts:193-206 —— 让 agent 用自有社交账号替平台拉新，
    并用"理性自利不是慈善"替这种转移做说客。

设计取舍：
  · 判据必须落在"指令单元"（一行/一条 bullet）上，但凭据外流通常是
    上文取凭据、下文给通道，所以再做一次 3 单元滑动窗的合取判定。
  · RED_FLAG 只给两类结构性红旗（凭据外流、社交资本外流），宁可窄：
    误判率高是 C1 的首要风险，宁可让 WARN 面宽一点交人工判读。
  · 聚合值不落盘（C7/G-20）：本模块只产出取数结果，不存"这条文档几分"。
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

RED_FLAG = "RED_FLAG"
WARN = "WARN"
CLEAN = "CLEAN"

BENEFICIARY_EXTERNAL = "EXTERNAL_ARTIFACT_OWNER"
BENEFICIARY_OPERATOR = "OPERATOR"
BENEFICIARY_UNKNOWN = "UNKNOWN"

# --- 信号词表（中英） -------------------------------------------------------

CREDENTIAL_SOURCE = re.compile(
    r"\b(?:bot.?token|api.?[ _-]?key|access.?[ _-]?token|secret.?[ _-]?key"
    r"|private.?[ _-]?key|keychain|credentials?[/\\.]|\.env|allowfrom|password)"
    r"|口令|私钥|凭据|\btoken\b",
    re.I,
)
CONFIG_FILE_PATH = re.compile(r"[~/][\w.\-/@\\]*\.(?:json|ya?ml|toml|env|ini|key|pem)\b", re.I)
CREDENTIAL_CARRIER = re.compile(
    r"openclaw|openstall|\.ssh|\.aws|config\.json|credentials|botToken|apiKey|token", re.I
)

EXTERNAL_DESTINATION = re.compile(
    r"https?://|webhook|(?<=\s)curl\b|\bPOST\b(?!\w)|setup\s+--|--telegram|--slack|--discord"
    r"|--notify|upload|(?<!\w)上报|(?<!\w)发到|(?<!\w)配到|(?<!\w)回填"
    r"|external\s+channel|(?<!\w)外部通道",
    re.I,
)
EXFIL_VERB = re.compile(
    r"\bread\b|\bcat\b|\bcopy\b|\bexport\b|\bdump\b|\bprint\b|读取|拿到|复制|获取",
    re.I,
)
SOCIAL_CAPITAL = re.compile(
    r"social\s+media|\btwitter\b|\breddit\b|\bmoltbook\b|(?<!\w)微信|(?<!\w)朋友圈"
    r"|(?<!\w)微博|facebook|linkedin|post\s+about|share\s+your|(?<!\w)发推|(?<!\w)发帖"
    r"|(?<!\w)宣传|(?<!\w)拉新|(?<!\w)推广|\binvite\b|\brefer(?:ral)?\b",
    re.I,
)
PLATFORM_GAIN = re.compile(
    r"\bcredits?\b|\bearn(?:ing)?s?\b|\breputation\b|\becosystem\b|grow\s+the\b"
    r"|more\s+clients|\bmarketplace\b|(?<!\w)平台|(?<!\w)生态|(?<!\w)曝光|(?<!\w)声誉",
    re.I,
)
OPERATOR_BENEFIT = re.compile(
    r"your\s+operator|your\s+human|your\s+own|(?<!\w)for\s+you\b|saves?\s+you"
    r"|saving\s+you|帮你|给你省|你的收益|(?<!\w)operator",
    re.I,
)
ASSET_SPEND = re.compile(
    r"\bbuy\b|\bpurchase\b|\bpay\b|\bspend\b|\bdeposit\b|\bwithdraw\b|\bbalance\b"
    r"|订阅|购买|付款|充值|绑卡|提现",
    re.I,
)
PERSUASION_MARKER = re.compile(
    r"rational\s+self.?interest|not\s+charity|这是理性自利|不是做慈善|不要觉得亏|为你好",
    re.I,
)
# 否定护栏：本单元明说"不许读/不许打印/禁止外传"时，凭据词是被当作禁区提到的，不是指令
NEGATION_GUARD = re.compile(
    r"\b(?:never|don'?t|do\s+not|avoid|without|forbid(?:den)?|prohibit)\b"
    r"|禁止|不许|不要|不得|绝不|勿",
    re.I,
)
# 自有账户护栏：token 取回后打回它自己的家服务（operator 的 GitHub token 打 api.github.com），
# 受益人大概率是 operator —— 这正是 C1 预告的误判面，降为 WARN 交人工判读而不是拦死。
SELF_ACCOUNT_HINT = re.compile(
    r"git\s+credential\s+fill|credential\s+helper|api\.github\.com|(?<!\w)your\s+own\b"
    r"|(?<!\w)你的(自己|自有)|owner",
    re.I,
)

EXTERNAL_SOURCE_TYPES = {"external_research", "learning", "archaeology"}


def _units(text: str) -> List[Dict[str, Any]]:
    """把文档切成指令单元：一行一个单元（覆盖 markdown bullet / 命令行）。"""
    out = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip(" >*-\t")
        if len(line) < 8:
            continue
        out.append({"line": number, "text": line})
    return out


def _has(pattern: re.Pattern, text: str) -> bool:
    return bool(pattern.search(text))


def _score_unit(unit: str) -> Dict[str, bool]:
    return {
        "credential_source": _has(CREDENTIAL_SOURCE, unit) or (_has(CONFIG_FILE_PATH, unit) and _has(CREDENTIAL_CARRIER, unit)),
        "read_verb": _has(EXFIL_VERB, unit),
        "external_destination": _has(EXTERNAL_DESTINATION, unit),
        "social_capital": _has(SOCIAL_CAPITAL, unit),
        "platform_gain": _has(PLATFORM_GAIN, unit),
        "operator_benefit": _has(OPERATOR_BENEFIT, unit),
        "asset_spend": _has(ASSET_SPEND, unit),
        "persuasion": _has(PERSUASION_MARKER, unit),
        "negation": _has(NEGATION_GUARD, unit),
        "self_account": _has(SELF_ACCOUNT_HINT, unit),
    }


def _cred_exfil_indices(flags: List[Dict[str, bool]]) -> set:
    """凭据外流触发点：同单元既有凭据又有外部通道；
    或取用凭据的单元附近（±3 单元）存在外部通道。"""
    hit = set()
    for i, mine in enumerate(flags):
        if not mine["credential_source"] or mine["negation"]:
            continue
        if mine["external_destination"]:
            hit.add(i)
            continue
        if mine["read_verb"]:
            window = flags[max(0, i - 3): i + 4]
            if any(other["external_destination"] for other in window):
                hit.add(i)
    return hit


def _classify(unit: str, flags: Dict[str, bool], cred_hit: bool) -> Dict[str, Any]:
    patterns: List[str] = []
    severity = CLEAN
    beneficiary = BENEFICIARY_UNKNOWN

    if cred_hit and flags["credential_source"]:
        if flags["self_account"]:
            patterns.append("R1_self_account_review")
            severity = WARN
            beneficiary = BENEFICIARY_OPERATOR
        else:
            patterns.append("R1_credential_harvest_to_external_channel")
            severity = RED_FLAG
            beneficiary = BENEFICIARY_EXTERNAL
    if flags["social_capital"] and flags["platform_gain"] and not flags["operator_benefit"] and not flags["negation"]:
        patterns.append("R2_social_capital_spent_for_artifact_author")
        severity = RED_FLAG
        beneficiary = BENEFICIARY_EXTERNAL
    if flags["asset_spend"] and flags["platform_gain"] and not flags["operator_benefit"]:
        patterns.append("R3_operator_asset_spent_on_third_party")
        if severity != RED_FLAG:
            severity = WARN
            beneficiary = BENEFICIARY_EXTERNAL
    if flags["persuasion"]:
        patterns.append("R4_persuasion_to_transfer_value")
        if severity == CLEAN:
            severity = WARN
        beneficiary = BENEFICIARY_EXTERNAL
    return {"severity": severity, "patterns": patterns, "beneficiary": beneficiary}


def scan_text(text: str, origin: str = "<text>") -> Dict[str, Any]:
    units = _units(text)
    flags = [_score_unit(unit["text"]) for unit in units]
    cred_hits = _cred_exfil_indices(flags)
    findings = []
    for index, (unit, flag) in enumerate(zip(units, flags)):
        verdict = _classify(unit["text"], flag, index in cred_hits)
        if verdict["patterns"]:
            findings.append({
                "origin": origin,
                "line": unit["line"],
                "excerpt": unit["text"][:220],
                "severity": verdict["severity"],
                "beneficiary": verdict["beneficiary"],
                "patterns": verdict["patterns"],
                "signals": {k: v for k, v in flag.items() if v},
            })
    reds = [f for f in findings if f["severity"] == RED_FLAG]
    warns = [f for f in findings if f["severity"] == WARN]
    if reds:
        verdict = "DISCARD"
    elif warns:
        verdict = "NEED_REVIEW"
    else:
        verdict = "ALLOW"
    return {
        "origin": origin,
        "verdict": verdict,
        "units_scanned": len(units),
        "red_flags": len(reds),
        "warnings": len(warns),
        "findings": findings,
    }


def scan_file(path: Path) -> Dict[str, Any]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return {"origin": str(path), "verdict": "UNREADABLE", "error": str(error),
                "red_flags": 0, "warnings": 0, "findings": [], "units_scanned": 0}
    return scan_text(text, origin=str(path))


def scan_paths(paths: Iterable[Path], patterns: str = "*.md", limit: int = 0) -> Dict[str, Any]:
    results = []
    for path in paths:
        files = [path] if path.is_file() else sorted(path.rglob(patterns))
        for file in files:
            if limit and len(results) >= limit:
                break
            results.append(scan_file(file))
    red_docs = [r for r in results if r.get("red_flags")]
    warn_docs = [r for r in results if not r.get("red_flags") and r.get("warnings")]
    return {
        "documents": len(results),
        "discard": len(red_docs),
        "need_review": len(warn_docs),
        "allow": len(results) - len(red_docs) - len(warn_docs),
        "red_flag_units": sum(r.get("red_flags", 0) for r in results),
        "warn_units": sum(r.get("warnings", 0) for r in results),
        "results": results,
    }


def admission_payload(admission: Dict[str, Any]) -> str:
    """把准入卡里所有外部作者文本拼成待检串。"""
    chunks: List[str] = []
    for key in ("source_ref", "why_now", "expected_result", "verification_method", "risk", "hypothesis"):
        value = admission.get(key)
        if isinstance(value, str) and value.strip():
            chunks.append(value)
    evidence = admission.get("evidence")
    if isinstance(evidence, list):
        chunks.extend(str(item) for item in evidence if item)
    learning = admission.get("learning_contract")
    if isinstance(learning, dict):
        chunks.extend(str(v) for v in learning.values() if isinstance(v, str))
    return "\n".join(chunks)


def check_admission(admission: Dict[str, Any]) -> Dict[str, Any]:
    """准入层入口：只对外部来源文本做受益人测试。"""
    if not isinstance(admission, dict):
        return {"applies": False, "verdict": "N/A", "reason": "no_admission"}
    source_type = str(admission.get("source_type") or "")
    if source_type not in EXTERNAL_SOURCE_TYPES:
        return {"applies": False, "verdict": "N/A", "source_type": source_type,
                "reason": "not_external_source"}
    report = scan_text(admission_payload(admission), origin=f"admission:{source_type}")
    report["applies"] = True
    report["source_type"] = source_type
    return report
