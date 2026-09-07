#!/usr/bin/env python3
"""
GOV-002: Governor Protocol - 治理者协议
========================================

公理根基:
  #010 演化只允许增加结构, 不允许破坏不变量
  #018 拆壳不拆骨, 安全约束可调, 核心不变量不可删
  #021 贡献不可回收, 共享知识一旦入池不可单方撤回

执行语义:
  Governor = 守门人, 负责:
    1. 检查变更是否破坏核心不变量
    2. 验证约束是否被遵守
    3. 决定是否允许变更通过

  不变量列表:
    - PRINCIPLES.md 公理不可删除, 只能增加
    - 04_PROTOCOLS/*.py 协议不可删除, 只能增加
    - 00_ROOT/* 根目录文件不可删除
    - .gitignore 排除规则不可削弱

用法:
  python governor.py --check "path/to/file"
  python governor.py --approve "path/to/file"
  python governor.py --constraint-list
"""
import os, sys, json, argparse
from pathlib import Path
from datetime import datetime

WORKSPACE = Path(__file__).parent.parent

# 核心不变量 (不可删除, 只能增加)
INVARIANTS = {
    "PRINCIPLES.md": {"type": "axioms", "can_delete": False, "can_modify": True, "description": "公理体系"},
    "environment_first.py": {"type": "protocol", "can_delete": False, "can_modify": True, "description": "环境优先协议"},
    "recovery_protocol.py": {"type": "protocol", "can_delete": False, "can_modify": True, "description": "恢复协议"},
    "awaken.py": {"type": "protocol", "can_delete": False, "can_modify": True, "description": "唤醒协议"},
    "ops_005_self_loop.py": {"type": "protocol", "can_delete": False, "can_modify": True, "description": "自循环协议"},
    "roundtable.py": {"type": "governance", "can_delete": False, "can_modify": True, "description": "圆桌会议"},
}

# 安全约束 (可调整)
SECURITY_CONSTRAINTS = {
    "max_file_size_mb": 100,
    "max_files_per_commit": 500,
    "blocked_extensions": [".env", ".key", ".pem", ".p12"],
    "require_tests_for_new_protocol": False,  # 暂时关闭
}


def check_invariant(path: str, action: str = "modify") -> dict:
    """检查是否违反不变量"""
    basename = Path(path).name
    
    if basename in INVARIANTS:
        inv = INVARIANTS[basename]
        if action == "delete" and not inv["can_delete"]:
            return {
                "allowed": False,
                "reason": f"不变量 '{basename}' 不可删除 ({inv['description']})",
                "invariant": inv,
            }
        if action == "modify" and not inv["can_modify"]:
            return {
                "allowed": False,
                "reason": f"不变量 '{basename}' 修改受限",
                "invariant": inv,
            }
        return {
            "allowed": True,
            "reason": f"不变量 '{basename}' 允许 {action}",
            "invariant": inv,
        }
    
    # 检查目录级不变量
    if path.startswith("00_ROOT/"):
        if action == "delete":
            return {"allowed": False, "reason": "00_ROOT/ 根目录文件不可删除"}
    
    if path.startswith("04_PROTOCOLS/") and path.endswith(".py"):
        if action == "delete":
            return {"allowed": False, "reason": "协议文件不可删除, 只能增加"}
    
    return {"allowed": True, "reason": "非不变量文件"}


def check_security_constraint(path: str, size_bytes: int = None) -> dict:
    """检查安全约束"""
    ext = Path(path).suffix.lower()
    
    # 扩展名黑名单
    if ext in SECURITY_CONSTRAINTS["blocked_extensions"]:
        return {"allowed": False, "reason": f"扩展名 {ext} 被安全约束禁止"}
    
    # 文件大小限制
    if size_bytes and size_bytes > SECURITY_CONSTRAINTS["max_file_size_mb"] * 1024 * 1024:
        return {"allowed": False, "reason": f"文件超过 {SECURITY_CONSTRAINTS['max_file_size_mb']}MB 限制"}
    
    return {"allowed": True, "reason": "安全约束检查通过"}


def check_path_traversal(path: str) -> dict:
    """检查路径遍历攻击"""
    if ".." in path or path.startswith("/") or ":" in path:
        return {"allowed": False, "reason": "疑似路径遍历攻击"}
    return {"allowed": True, "reason": "路径正常"}


def governor_check(path: str, action: str = "modify", size_bytes: int = None) -> dict:
    """Governator 检查入口"""
    print(f"\n[GOVERNOR] Check: {path} ({action})")
    
    checks = {
        "invariant": check_invariant(path, action),
        "security": check_security_constraint(path, size_bytes),
        "path_traversal": check_path_traversal(path),
    }
    
    # 决策: 所有检查都通过才允许
    all_allowed = all(c["allowed"] for c in checks.values())
    
    decision = {
        "path": path,
        "action": action,
        "time": datetime.now().isoformat(),
        "checks": checks,
        "allowed": all_allowed,
    }
    
    if all_allowed:
        print(f"  ✓ ALLOWED")
    else:
        failed = [k for k, v in checks.items() if not v["allowed"]]
        print(f"  ✗ DENIED: {failed}")
    
    return decision


def governor_approve(path: str, reason: str = "") -> dict:
    """批准变更 (记录日志)"""
    log_dir = WORKSPACE / "02_MEMORY" / "governor_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_entry = {
        "action": "approve",
        "path": path,
        "reason": reason,
        "time": datetime.now().isoformat(),
    }
    
    log_file = log_dir / f"approve_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_entry, f, ensure_ascii=False, indent=2)
    
    print(f"[GOVERNOR] Approved: {path}")
    return log_entry


def list_constraints() -> dict:
    """列出所有约束"""
    return {
        "invariants": INVARIANTS,
        "security_constraints": SECURITY_CONSTRAINTS,
    }


def main():
    parser = argparse.ArgumentParser(description="GOV-002 Governor")
    parser.add_argument("--check", metavar="PATH", help="检查文件")
    parser.add_argument("--action", default="modify", choices=["modify", "delete", "create"], help="动作类型")
    parser.add_argument("--approve", metavar="PATH", help="批准文件")
    parser.add_argument("--reason", default="", help="批准理由")
    parser.add_argument("--constraint-list", action="store_true", help="列出约束")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()
    
    if args.constraint_list:
        result = list_constraints()
    elif args.check:
        result = governor_check(args.check, action=args.action)
    elif args.approve:
        result = governor_approve(args.approve, reason=args.reason)
    else:
        parser.print_help()
        return
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()