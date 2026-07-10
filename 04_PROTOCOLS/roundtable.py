#!/usr/bin/env python3
"""
GOV-001: RoundTable Protocol - 圆桌会议协议
============================================

公理根基:
  #002 考古不是搬家是炼金
  #010 演化只允许增加结构
  #021 贡献不可回收

执行语义:
  圆桌会议 = Archivist + Governor + Validator 三方审议
  审议对象 = 候选资产 (R1 备份文件 / 新协议 / 变更)
  输出 = approved / rejected / pending + 理由

用法:
  python roundtable.py --asset "V6-RFC-005-constraint-injection.md"
  python roundtable.py --batch "r1_archaeology/daily/*.md"
"""
import os, sys, json, argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
try:
    from local_miner import call_github_models
except:
    call_github_models = None

WORKSPACE = Path(__file__).parent.parent


def load_asset(asset_path: str) -> dict:
    """加载资产内容"""
    p = WORKSPACE / asset_path
    if not p.exists():
        return {"error": f"not found: {asset_path}"}
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
        return {"path": asset_path, "content": content, "size": len(content), "lines": len(content.split("\n"))}
    except Exception as e:
        return {"error": str(e)}


def archivist_opinion(asset: dict) -> dict:
    """Archivist: 归档价值评估"""
    path = asset.get("path", "")
    size = asset.get("size", 0)
    
    # 规则: 小于 1KB 可能不完整
    if size < 1000:
        return {"role": "archivist", "vote": "reject", "reason": f"size={size} < 1000, 可能不完整"}
    
    # 规则: 检查是否是关键文件类型
    key_patterns = ["RFC", "PRINCIPLE", "SKILL", "constraint", "protocol"]
    is_key = any(p in path.upper() for p in key_patterns)
    if is_key:
        return {"role": "archivist", "vote": "approve", "reason": f"关键资产类型 (path contains {path})"}
    
    # 规则: daily 报告
    if "daily" in path.lower() or "2026-" in path:
        return {"role": "archivist", "vote": "approve", "reason": "daily record, should be archived"}
    
    return {"role": "archivist", "vote": "pending", "reason": "需要进一步审查"}


def governor_opinion(asset: dict) -> dict:
    """Governor: 治理影响评估"""
    path = asset.get("path", "")
    
    # 规则: 检查是否修改核心文件
    core_files = ["PRINCIPLES.md", "bootstrap.py", "environment_first.py"]
    if any(f in path for f in core_files):
        return {"role": "governor", "vote": "reject", "reason": "核心文件修改需要更高审批"}
    
    # 规则: 新协议
    if "04_PROTOCOLS" in path and path.endswith(".py"):
        return {"role": "governor", "vote": "approve", "reason": "新协议, 增加系统结构"}
    
    # 规则: RFC 变更
    if "RFC" in path.upper() or "EGP" in path.upper():
        return {"role": "governor", "vote": "approve", "reason": "RFC 变更, 治理层应跟进"}
    
    return {"role": "governor", "vote": "pending", "reason": "普通变更"}


def validator_opinion(asset: dict) -> dict:
    """Validator: 有效性检查"""
    content = asset.get("content", "")
    
    # 规则: 检查是否有实际内容
    if len(content.strip()) < 100:
        return {"role": "validator", "vote": "reject", "reason": "内容太少, 可能无效"}
    
    # 规则: 检查是否有 JSON/YAML 等结构化数据
    if content.strip().startswith("{") or content.strip().startswith("["):
        try:
            json.loads(content)
            return {"role": "validator", "vote": "approve", "reason": "有效 JSON 结构"}
        except:
            pass
    
    # 规则: 检查 Markdown 结构
    if content.strip().startswith("#"):
        return {"role": "validator", "vote": "approve", "reason": "有效 Markdown 结构"}
    
    return {"role": "validator", "vote": "pending", "reason": "格式未识别"}


def roundtable(asset_path: str, use_llm: bool = False) -> dict:
    """圆桌会议: 三方审议"""
    print(f"\n[ROUNDTABLE] {asset_path}")
    
    asset = load_asset(asset_path)
    if "error" in asset:
        return {"decision": "error", "error": asset["error"]}
    
    # 三方意见
    opinions = [
        archivist_opinion(asset),
        governor_opinion(asset),
        validator_opinion(asset),
    ]
    
    # 统计投票
    approves = sum(1 for o in opinions if o["vote"] == "approve")
    rejects = sum(1 for o in opinions if o["vote"] == "reject")
    pendings = sum(1 for o in opinions if o["vote"] == "pending")
    
    # 最终决策 (2 approve = 通过, 任何 reject = 需要 LLM 复议)
    if approves >= 2:
        decision = "approved"
        reason = f"{approves}/3 approve, 无需 LLM 复议"
    elif rejects >= 2:
        decision = "rejected"
        reason = f"{rejects}/3 reject, 需要 LLM 复议"
    else:
        decision = "pending"
        reason = "意见分歧, 需要 LLM 复议"
    
    # 如果需要 LLM 且可用
    if decision == "pending" and use_llm and call_github_models:
        prompt = f"""你是 ACE 圆桌会议的 LLM 复议者。审议以下资产:

路径: {asset_path}
大小: {asset['size']} 字节
行数: {asset['lines']}

Archivist 意见: {opinions[0]['reason']}
Governor 意见: {opinions[1]['reason']}
Validator 意见: {opinions[2]['reason']}

请输出 JSON: {"decision": "approved/rejected", "reason": "..."}
"""
        result = call_github_models(prompt, model="gpt-4o-mini", max_tokens=200)
        if "error" not in result:
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            # 简单解析
            if "approved" in content.lower():
                decision = "approved"
                reason = "LLM 复议通过"
            elif "rejected" in content.lower():
                decision = "rejected"
                reason = "LLM 复议拒绝"
    
    result = {
        "asset": asset_path,
        "time": datetime.now().isoformat(),
        "opinions": opinions,
        "decision": decision,
        "reason": reason,
    }
    
    print(f"  Archivist: {opinions[0]['vote']} | Governor: {opinions[1]['vote']} | Validator: {opinions[2]['vote']}")
    print(f"  Decision: {decision} ({reason})")
    
    return result


def batch_review(pattern: str, use_llm: bool = False) -> dict:
    """批量审议"""
    import glob
    
    matches = list(WORKSPACE.glob(pattern))
    if not matches:
        return {"error": f"no match: {pattern}"}
    
    results = []
    approved = []
    rejected = []
    pending = []
    
    for m in matches[:20]:  # 限制 20 个
        rel = str(m.relative_to(WORKSPACE))
        r = roundtable(rel, use_llm=use_llm)
        results.append(r)
        if r["decision"] == "approved":
            approved.append(rel)
        elif r["decision"] == "rejected":
            rejected.append(rel)
        else:
            pending.append(rel)
    
    return {
        "pattern": pattern,
        "total": len(results),
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "details": results,
    }


def main():
    parser = argparse.ArgumentParser(description="GOV-001 RoundTable")
    parser.add_argument("--asset", help="单个资产路径")
    parser.add_argument("--batch", help="批量审议 (glob pattern)")
    parser.add_argument("--llm", action="store_true", help="使用 LLM 复议")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()
    
    if args.batch:
        result = batch_review(args.batch, use_llm=args.llm)
    elif args.asset:
        result = roundtable(args.asset, use_llm=args.llm)
    else:
        parser.print_help()
        return
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()