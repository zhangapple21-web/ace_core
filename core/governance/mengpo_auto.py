"""
孟婆自动触发器 (Mengpo AutoTrigger)

自动触发条件：
  1. 词库新增概念数达到阈值（每20个新概念触发一次轻量清理）
  2. 词库污染率超过阈值（>15% 触发全面清理）
  3. 每日低温时间（凌晨3点）触发全面清理
  4. 新概念重复率过高（>30%）触发去重

设计原则：
  - 永远先备份，再操作
  - 不删除，只归档到 graveyard
  - 保守触发，宁可少清不可误删
  - 每次操作都有记录，可追溯
"""

import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class MengpoAutoTrigger:
    """
    孟婆自动触发器
    
    监控词库和经验库的熵增情况，
    达到阈值时自动触发遗忘清理。
    """

    # 触发阈值
    LIGHT_CLEANUP_NEW_CONCEPTS = 20     # 每新增20个概念触发轻量清理
    FULL_CLEANUP_POLLUTION_RATE = 0.15  # 污染率>15%触发全面清理
    LIGHT_CLEANUP_THRESHOLD = 0.7       # 轻量清理：清污染度>0.7的
    FULL_CLEANUP_THRESHOLD = 0.55       # 全面清理：清污染度>0.55的
    DAILY_CLEANUP_HOUR = 3              # 每日凌晨3点全面清理
    MAX_CLEANUP_PER_DAY = 3             # 每天最多清理3次
    MIN_INTERVAL_SECONDS = 3600         # 两次清理最少间隔1小时

    def __init__(self, lexicon_path: Path, data_dir: Path):
        self.lexicon_path = Path(lexicon_path)
        self.data_dir = Path(data_dir)
        self.graveyard_dir = self.data_dir / "graveyard"
        self.records_path = self.data_dir / "mengpo_auto_records.jsonl"
        self.state_path = self.data_dir / "mengpo_state.json"

        self.graveyard_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """加载状态"""
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # 初始状态：用当前词库大小初始化，避免第一次就触发
        initial_count = 0
        if self.lexicon_path.exists():
            try:
                with open(self.lexicon_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    initial_count = len(data.get("concepts", {}))
            except Exception:
                pass
        return {
            "last_concept_count": initial_count,
            "last_cleanup_time": None,
            "today_cleanup_count": 0,
            "last_cleanup_date": None,
            "total_cleanups": 0,
            "total_concepts_removed": 0,
            "last_pollution_rate": 0.0,
        }

    def _save_state(self):
        """保存状态"""
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _record(self, action: str, details: Dict[str, Any]):
        """记录操作"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details,
        }
        with open(self.records_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _load_lexicon(self) -> Dict[str, Any]:
        """加载词库"""
        with open(self.lexicon_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_lexicon(self, data: Dict[str, Any]):
        """保存词库"""
        with open(self.lexicon_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _backup_lexicon(self) -> Path:
        """备份词库"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.lexicon_path.parent / f"lexicon_backup_mengpo_{timestamp}.json"
        shutil.copy2(self.lexicon_path, backup_path)
        return backup_path

    # 核心保护列表 — 这些概念即使满足污染条件也不会被清理
    PROTECTED_CONCEPTS = {
        "身体", "灵魂", "结构", "约束", "协议", "记忆", "路由",
        "经验", "词库", "考古", "种子", "演化", "生存", "治理",
        "老张", "零号原则", "笨者生存",
    }

    # 核心分类 — 这些分类的概念自动保护
    PROTECTED_CATEGORIES = {
        "核心原则", "核心概念", "元概念", "核心公理",
        "架构分层", "核心机制",
    }

    def calculate_pollution(self, concept_name: str, info: Dict[str, Any]) -> float:
        """
        计算单个概念的污染度 0.0-1.0
        
        污染来源：
        1. 概念名太短（<=2字符）
        2. 来源是自动提取（concept_miner:eco）
        3. 定义太短（<30字符）且来源可疑
        4. 定义包含代码/JSON片段
        5. 孤立概念（无related）
        6. importance 与实际价值不匹配
        """
        # 先检查保护列表
        if concept_name in self.PROTECTED_CONCEPTS:
            return 0.0

        category = info.get("category", "")
        if category in self.PROTECTED_CATEGORIES:
            return 0.0

        # 核心概念特征：有完整定义 + 有related + 来源可靠
        definition = info.get("definition", "")
        source = info.get("source", "")
        related = info.get("related", [])
        importance = info.get("importance", 0)

        # 如果有完整定义(>50字符) + 有related(>2) + 来源不是自动提取
        # 即使短也不算污染
        if len(definition) > 50 and len(related) >= 2 and "concept_miner" not in source:
            return 0.0

        score = 0.0

        # 1. 短概念（<=2字符）
        if len(concept_name) <= 2:
            score += 0.4

        # 2. 自动提取来源
        if "concept_miner:eco:narrative_ecology" in source:
            score += 0.3
        elif "concept_miner" in source:
            score += 0.2

        # 3. 定义太短
        if len(definition) < 30:
            if "concept_miner" in source:
                score += 0.2
            else:
                score += 0.1

        # 4. 定义包含代码片段
        if '"' in definition and '{' in definition:
            score += 0.2
        if '\\n' in definition or '\\r' in definition:
            score += 0.2
        if definition.count('"') > 4:
            score += 0.1

        # 5. 孤立概念
        if len(related) == 0 and len(definition) < 50:
            score += 0.1

        # 6. importance 异常高
        if importance >= 95 and len(concept_name) <= 2:
            score += 0.2  # 高重要性的短概念，明显是污染

        return min(score, 1.0)

    def scan_pollution(self) -> Dict[str, Any]:
        """
        扫描词库污染情况
        
        返回：
        - total_concepts: 总概念数
        - polluted_count: 污染概念数（>0.6）
        - pollution_rate: 污染率
        - high_pollution: 高污染概念列表（>0.8）
        - medium_pollution: 中污染概念列表（0.6-0.8）
        """
        data = self._load_lexicon()
        concepts = data.get("concepts", {})

        high_pollution = []  # >0.8
        medium_pollution = []  # 0.6-0.8

        for name, info in concepts.items():
            pollution = self.calculate_pollution(name, info)
            if pollution > 0.8:
                high_pollution.append((name, pollution))
            elif pollution >= 0.6:
                medium_pollution.append((name, pollution))

        high_pollution.sort(key=lambda x: x[1], reverse=True)
        medium_pollution.sort(key=lambda x: x[1], reverse=True)

        polluted_count = len(high_pollution) + len(medium_pollution)
        pollution_rate = polluted_count / max(1, len(concepts))

        return {
            "total_concepts": len(concepts),
            "polluted_count": polluted_count,
            "pollution_rate": pollution_rate,
            "high_pollution_count": len(high_pollution),
            "medium_pollution_count": len(medium_pollution),
            "high_pollution": high_pollution[:20],  # 只返回前20个
            "medium_pollution": medium_pollution[:20],
            "scanned_at": datetime.now().isoformat(),
        }

    def should_trigger(self) -> Tuple[bool, str, str]:
        """
        检查是否应该触发清理
        
        返回：(是否触发, 触发类型, 原因)
        触发类型：light / full / daily / none
        """
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        # 重置今日计数
        if self.state.get("last_cleanup_date") != today:
            self.state["today_cleanup_count"] = 0
            self.state["last_cleanup_date"] = today

        # 检查频率限制
        if self.state["today_cleanup_count"] >= self.MAX_CLEANUP_PER_DAY:
            return False, "none", "今日清理次数已达上限"

        last_cleanup = self.state.get("last_cleanup_time")
        if last_cleanup:
            last_dt = datetime.fromisoformat(last_cleanup)
            if (now - last_dt).total_seconds() < self.MIN_INTERVAL_SECONDS:
                return False, "none", "距离上次清理太近"

        # 扫描污染
        scan = self.scan_pollution()
        current_count = scan["total_concepts"]
        pollution_rate = scan["pollution_rate"]
        self.state["last_pollution_rate"] = pollution_rate

        # 触发条件1：污染率过高（全面清理）
        if pollution_rate >= self.FULL_CLEANUP_POLLUTION_RATE:
            return True, "full", f"污染率 {pollution_rate:.1%} 超过阈值 {self.FULL_CLEANUP_POLLUTION_RATE:.0%}"

        # 触发条件2：新增概念数过多（轻量清理）
        last_count = self.state.get("last_concept_count", 0)
        new_concepts = current_count - last_count
        if new_concepts >= self.LIGHT_CLEANUP_NEW_CONCEPTS:
            return True, "light", f"新增 {new_concepts} 个概念，达到阈值 {self.LIGHT_CLEANUP_NEW_CONCEPTS}"

        # 触发条件3：每日低温时间（全面清理）
        if now.hour == self.DAILY_CLEANUP_HOUR:
            last_date = self.state.get("last_cleanup_date")
            if last_date != today:
                return True, "daily", f"每日低温时间 {self.DAILY_CLEANUP_HOUR}:00 清理"

        # 触发条件4：高污染概念数过多
        if scan["high_pollution_count"] >= 10:
            return True, "light", f"高污染概念 {scan['high_pollution_count']} 个，超过10个"

        return False, "none", "未达到触发条件"

    def run_cleanup(self, cleanup_type: str = "light") -> Dict[str, Any]:
        """
        执行清理
        
        cleanup_type: light / full
        """
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        # 1. 备份
        backup_path = self._backup_lexicon()

        # 2. 加载词库
        data = self._load_lexicon()
        concepts = data.get("concepts", {})

        # 3. 确定阈值
        if cleanup_type == "full":
            threshold = self.FULL_CLEANUP_THRESHOLD
        else:  # light
            threshold = self.LIGHT_CLEANUP_THRESHOLD

        # 4. 识别要移除的概念
        to_remove = []
        for name, info in concepts.items():
            pollution = self.calculate_pollution(name, info)
            if pollution >= threshold:
                to_remove.append((name, pollution))

        to_remove.sort(key=lambda x: x[1], reverse=True)

        # 5. 归档到 graveyard
        if to_remove:
            graveyard_file = self.graveyard_dir / f"lexicon_batch_{now.strftime('%Y%m%d_%H%M%S')}.json"
            graveyard_data = {
                "archived_at": now.isoformat(),
                "cleanup_type": cleanup_type,
                "count": len(to_remove),
                "threshold": threshold,
                "backup_file": str(backup_path),
                "concepts": {
                    name: {**concepts[name], "pollution_score": pollution}
                    for name, pollution in to_remove
                },
            }
            with open(graveyard_file, "w", encoding="utf-8") as f:
                json.dump(graveyard_data, f, ensure_ascii=False, indent=2)

        # 6. 从词库中移除
        clean_concepts = {k: v for k, v in concepts.items()
                         if k not in {name for name, _ in to_remove}}

        # 7. 更新分类
        new_categories = {}
        for name, info in clean_concepts.items():
            cat = info.get("category", "待分类")
            if cat not in new_categories:
                new_categories[cat] = []
            new_categories[cat].append(name)

        # 8. 保存
        data["concepts"] = clean_concepts
        data["categories"] = new_categories
        data["concept_count"] = len(clean_concepts)
        data["category_count"] = len(new_categories)
        data["updated_at"] = now.isoformat()
        data["last_mengpo_cleanup"] = {
            "timestamp": now.isoformat(),
            "type": cleanup_type,
            "removed_count": len(to_remove),
            "threshold": threshold,
            "graveyard_file": str(graveyard_file) if to_remove else None,
            "backup_file": str(backup_path),
        }
        self._save_lexicon(data)

        # 9. 更新状态
        self.state["last_concept_count"] = len(clean_concepts)
        self.state["last_cleanup_time"] = now.isoformat()
        self.state["last_cleanup_date"] = today
        self.state["today_cleanup_count"] = self.state.get("today_cleanup_count", 0) + 1
        self.state["total_cleanups"] = self.state.get("total_cleanups", 0) + 1
        self.state["total_concepts_removed"] = self.state.get("total_concepts_removed", 0) + len(to_remove)
        self.state["last_pollution_rate"] = 0.0  # 清理后重置
        self._save_state()

        # 10. 记录
        result = {
            "cleanup_type": cleanup_type,
            "threshold": threshold,
            "removed_count": len(to_remove),
            "before_count": len(concepts),
            "after_count": len(clean_concepts),
            "backup_file": str(backup_path),
            "graveyard_file": str(graveyard_file) if to_remove else None,
            "removed_top10": [(name, round(p, 2)) for name, p in to_remove[:10]],
        }
        self._record("cleanup", result)

        return result

    def check_and_run(self) -> Dict[str, Any]:
        """
        检查并自动运行（主入口）
        
        每次主循环调用一次这个方法。
        """
        should_trigger, trigger_type, reason = self.should_trigger()

        result = {
            "triggered": should_trigger,
            "trigger_type": trigger_type,
            "reason": reason,
            "cleanup_result": None,
        }

        if should_trigger:
            logger.info(f"孟婆触发: {trigger_type} - {reason}")
            cleanup_result = self.run_cleanup(trigger_type)
            result["cleanup_result"] = cleanup_result
        else:
            # 即使不触发，也更新一下概念数
            data = self._load_lexicon()
            self.state["last_concept_count"] = len(data.get("concepts", {}))
            self._save_state()

        return result
