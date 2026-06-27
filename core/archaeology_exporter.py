"""
考古产物导出器 — 把 ACE 的挖矿产物导出到 mine-seed 仓库

导出内容：
- 词库快照（latest + 每日）
- 记忆索引快照（latest + 每日）
- 守护进程状态（挖矿进度）
- 每日考古摘要（markdown）
- eco_layer 分析产物
- 切片分析产物
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


class ArchaeologyExporter:
    """考古产物导出器"""

    def __init__(
        self,
        ace_base_dir: Path,
        mine_seed_path: str,
        target_subdir: str = "03_DATA/research/r1_archaeology",
    ):
        self.ace_base_dir = Path(ace_base_dir)
        self.mine_seed_path = Path(mine_seed_path)
        self.target_dir = self.mine_seed_path / target_subdir
        self.target_dir.mkdir(parents=True, exist_ok=True)

    def export_all(
        self,
        lexicon_data: Dict[str, Any],
        memory_index_data: Dict[str, Any],
        daemon_state: Dict[str, Any],
        daily_summary: Optional[str] = None,
        eco_stats: Optional[Dict] = None,
        slice_results: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """一键导出所有考古产物"""
        results = {
            "exported_at": datetime.now().isoformat(),
            "files": [],
            "target_dir": str(self.target_dir),
        }

        try:
            f = self.export_lexicon(lexicon_data)
            results["files"].extend(f)
        except Exception as e:
            results["lexicon_error"] = str(e)

        try:
            f = self.export_memory_index(memory_index_data)
            results["files"].extend(f)
        except Exception as e:
            results["memory_error"] = str(e)

        try:
            f = self.export_daemon_state(daemon_state)
            results["files"].extend(f)
        except Exception as e:
            results["state_error"] = str(e)

        if daily_summary:
            try:
                f = self.export_daily_summary(daily_summary)
                results["files"].extend(f)
            except Exception as e:
                results["summary_error"] = str(e)

        if eco_stats:
            try:
                f = self.export_eco_stats(eco_stats)
                results["files"].extend(f)
            except Exception as e:
                results["eco_error"] = str(e)

        if slice_results:
            try:
                f = self.export_slice_results(slice_results)
                results["files"].extend(f)
            except Exception as e:
                results["slice_error"] = str(e)

        results["total_files"] = len(results["files"])
        return results

    def export_lexicon(self, lexicon_data: Dict[str, Any]) -> list:
        """导出词库快照"""
        lex_dir = self.target_dir / "lexicon"
        lex_dir.mkdir(exist_ok=True)

        today = datetime.now().strftime("%Y%m%d")
        files = []

        latest_path = lex_dir / "lexicon_latest.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(lexicon_data, f, ensure_ascii=False, indent=2)
        files.append(str(latest_path))

        daily_path = lex_dir / f"lexicon_{today}.json"
        shutil.copy2(latest_path, daily_path)
        files.append(str(daily_path))

        return files

    def export_memory_index(self, memory_data: Dict[str, Any]) -> list:
        """导出记忆索引快照"""
        mem_dir = self.target_dir / "memory_index"
        mem_dir.mkdir(exist_ok=True)

        today = datetime.now().strftime("%Y%m%d")
        files = []

        latest_path = mem_dir / "memory_index_latest.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)
        files.append(str(latest_path))

        daily_path = mem_dir / f"memory_index_{today}.json"
        shutil.copy2(latest_path, daily_path)
        files.append(str(daily_path))

        return files

    def export_daemon_state(self, state: Dict[str, Any]) -> list:
        """导出守护进程状态（挖矿进度）"""
        files = []
        state_path = self.target_dir / "daemon_state.json"
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        files.append(str(state_path))
        return files

    def export_daily_summary(self, content: str) -> list:
        """导出每日考古摘要（markdown）"""
        daily_dir = self.target_dir / "daily"
        daily_dir.mkdir(exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        files = []

        md_path = daily_dir / f"{today}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# 每日考古摘要 - {today}\n\n")
            f.write(content)
            f.write(f"\n\n---\n*自动生成于 {datetime.now().isoformat()}*\n")
        files.append(str(md_path))
        return files

    def export_eco_stats(self, eco_stats: Dict) -> list:
        """导出 eco_layer 分析数据"""
        eco_dir = self.target_dir / "eco_layer"
        eco_dir.mkdir(exist_ok=True)
        files = []

        stats_path = eco_dir / "layer_stats.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(eco_stats, f, ensure_ascii=False, indent=2)
        files.append(str(stats_path))

        return files

    def export_slice_results(self, slice_results: Dict) -> list:
        """导出切片分析结果"""
        slice_dir = self.target_dir / "slices"
        slice_dir.mkdir(exist_ok=True)
        files = []

        for key, data in slice_results.items():
            path = slice_dir / f"{key}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            files.append(str(path))

        return files
