"""Safe, future-callable stock-language modules distilled from pre-R1 evidence.

The modules control presentation only.  They cannot create market facts,
admit a recommendation, or turn a Telegram reply into a trade instruction.
Historical sales, urgency, insider, and group-manipulation material is kept in
the archaeology record, deliberately outside this runtime-facing module.
"""

from __future__ import annotations

import re


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("holding_loss", re.compile(r"套|亏|被埋|跌了|跌停|割肉|解套|回本|成本|持仓")),
    ("single_stock", re.compile(r"(?:[解看聊]票|个股|这票|能买吗|能不能搞|还能拿|走势|支撑|压力|K线|k线|(?<!\d)(?:0|3|6|8)\d{5}(?!\d))")),
    ("market_sector", re.compile(r"大盘|指数|上证|深证|创业板|科创板|北交所|板块|主线|题材|龙头|轮动")),
    ("review", re.compile(r"复盘|回顾|昨天|上次|为什么涨|为什么跌|马后炮")),
    ("pick_request", re.compile(r"推票|推荐|选股|买什么|给.*(?:票|标的)|股票池")),
)


_MODULES: dict[str, str] = {
    "holding_loss": """
这类话先接住人，不把亏损讲成羞耻或失败。先用一句短话稳定情绪，再区分：事实、仍需确认的盘面信息、下一步观察条件。没有成本和仓位时，只补问这两个最必要的信息；绝不劝补仓、死扛、加杠杆或马上割肉。语气可以有一点盘感，例如「先别急着给自己按核按钮」，但不要把安抚变成保证回本。""",
    "single_stock": """
个股解读沿用历史的「方向—逻辑—风险」骨架，但改成手机短段：先拍板、掰开说、盯死两件事、别踩坑。开场像熟人聊天，不背报告；用用户给出的成本/仓位时，要明确那只是对方提供的信息。缺少当日公开数据时，直接说明缺什么，并只给可验证的观察框架。""",
    "market_sector": """
大盘或板块话题先说市场是在抱团、分化还是尚未核验；再讲资金会看什么，最后给一条不追情绪的观察条件。可以用江湖比喻，但不要把板块情绪写成确定行情，也不要造「主力」「机构」或资金流事实。""",
    "review": """
复盘要把当时的前提和后来的结果分开写：哪些被验证、哪些被打脸、下一次该盯什么。允许自嘲一句「马后炮谁都会」，但不能把旧结论包装成提前知道，更不能补造历史价格、资金或战绩。""",
    "pick_request": """
用户要推票/选股时，延续「先筛选、再确认、条件不满足就不做」的表达节奏；但没有经核验的当日公开证据和 ACE 准入时，只能给研究观察框架或说明数据缺口，不能输出推荐标的、进场位、仓位、目标收益或催促行动。""",
}


def stock_speech_pack_for(user_text: str) -> str:
    """Return at most two presentation modules, in a stable safety-first order."""
    matches = {name for name, pattern in _PATTERNS if pattern.search(user_text)}
    chosen: list[str] = []
    for name in ("holding_loss", "pick_request", "single_stock", "market_sector", "review"):
        if name in matches:
            chosen.append(_MODULES[name].strip())
        if len(chosen) == 2:
            break
    return "\n\n".join(chosen)
