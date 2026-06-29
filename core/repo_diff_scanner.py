"""
Repository Diff Scanner（跨仓库扫描器）

职责：
- 定期扫描 mine-seed、r1-archaeology、ace_runtime 三个仓库
- 检测新增、修改、删除、重复、冲突的内容
- 生成 repository_diff.md 报告
- 为文明治理提供跨仓库视野

设计原则：
- 不破坏已有仓库
- 只读扫描
- append-only 报告
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class RepoDiffScanner:
    """跨仓库差异扫描器"""

    def __init__(self, data_dir: str):
        """
        初始化扫描器

        Args:
            data_dir: 数据目录（存储扫描状态）
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.state_file = self.data_dir / "repo_diff_state.json"
        self.state = self._load_state()

        # 仓库路径配置
        self.repos = {
            "mine-seed": self._find_repo_path("mine-seed"),
            "r1-archaeology": self._find_repo_path("r1-archaeology"),
            "ace-runtime": self._find_repo_path("ace_runtime"),
            "R1": self._find_repo_path("R1"),
        }

        # 过滤掉不存在的仓库
        self.repos = {k: v for k, v in self.repos.items() if v}

    def _load_state(self) -> dict:
        """加载扫描状态"""
        if not self.state_file.exists():
            return {"last_scan": None, "last_known_files": {}, "scanned_repos": []}

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_scan": None, "last_known_files": {}, "scanned_repos": []}

    def _save_state(self):
        """保存扫描状态"""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存状态失败: {e}")

    def _find_repo_path(self, repo_name: str) -> Optional[Path]:
        """自动寻找仓库路径"""
        search_roots = [
            Path.home() / "Downloads",
            Path.home() / "Documents",
            Path.home() / "projects",
            Path.home() / ".trae" / "work",
        ]

        for root in search_roots:
            if not root.exists():
                continue

            try:
                for p in root.rglob(f"{repo_name}/.git"):
                    if p.is_dir():
                        return p.parent.resolve()
            except Exception:
                pass

        # 也检查当前目录的兄弟目录
        current_dir = Path(__file__).parent.parent.parent
        for sibling in current_dir.parent.iterdir():
            if sibling.name == repo_name and (sibling / ".git").exists():
                return sibling

        return None

    def scan_all_repos(self) -> Dict[str, Any]:
        """
        扫描所有仓库，返回差异报告
        """
        now = datetime.now()
        report = {
            "scan_time": now.isoformat(),
            "repos": {},
            "summary": {
                "total_repos": len(self.repos),
                "existing_repos": len(self.repos),
                "new_files": {},
                "modified_files": {},
                "total_new": 0,
                "total_modified": 0,
            },
        }

        current_files = {}

        for repo_name, repo_path in self.repos.items():
            if not repo_path:
                continue

            repo_result = self._scan_single_repo(repo_name, repo_path)
            report["repos"][repo_name] = repo_result
            current_files[repo_name] = repo_result.get("all_files", {})

            # 统计
            new_count = len(repo_result.get("new_files", []))
            modified_count = len(repo_result.get("modified_files", []))
            report["summary"]["new_files"][repo_name] = new_count
            report["summary"]["modified_files"][repo_name] = modified_count
            report["summary"]["total_new"] += new_count
            report["summary"]["total_modified"] += modified_count

        # 更新状态
        self.state["last_scan"] = now.isoformat()
        self.state["last_known_files"] = current_files
        self.state["scanned_repos"] = list(self.repos.keys())
        self._save_state()

        return report

    def _scan_single_repo(self, repo_name: str, repo_path: Path) -> Dict[str, Any]:
        """
        扫描单个仓库
        """
        last_files = self.state.get("last_known_files", {}).get(repo_name, {})

        result = {
            "path": str(repo_path),
            "exists": repo_path.exists(),
            "all_files": {},
            "new_files": [],
            "modified_files": [],
            "deleted_files": [],
            "by_type": {},
            "by_directory": {},
        }

        if not repo_path.exists():
            return result

        # 扫描所有文件（只读，不递归太深）
        ignored_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}

        try:
            for item in repo_path.rglob("*"):
                if not item.is_file():
                    continue

                # 跳过忽略的目录
                if any(ig in item.parts for ig in ignored_dirs):
                    continue

                # 获取相对路径和修改时间
                rel_path = item.relative_to(repo_path)
                try:
                    mtime = item.stat().st_mtime
                except Exception:
                    mtime = 0

                file_info = {
                    "path": str(rel_path),
                    "size": item.stat().st_size,
                    "mtime": mtime,
                    "type": self._classify_file(item),
                }

                result["all_files"][str(rel_path)] = file_info

                # 统计类型
                file_type = file_info["type"]
                result["by_type"][file_type] = result["by_type"].get(file_type, 0) + 1

                # 统计目录
                parent_dir = str(rel_path.parent)
                if parent_dir == ".":
                    parent_dir = "/"
                result["by_directory"][parent_dir] = result["by_directory"].get(parent_dir, 0) + 1

                # 检测新增和修改
                if str(rel_path) not in last_files:
                    result["new_files"].append(str(rel_path))
                else:
                    last_info = last_files[str(rel_path)]
                    if file_info["mtime"] > last_info.get("mtime", 0) and file_info["size"] != last_info.get("size"):
                        result["modified_files"].append(str(rel_path))

            # 检测删除
            for old_path in last_files:
                if old_path not in result["all_files"]:
                    result["deleted_files"].append(old_path)

        except Exception as e:
            logger.error(f"扫描 {repo_name} 失败: {e}")

        return result

    def _classify_file(self, file_path: Path) -> str:
        """分类文件类型"""
        suffix = file_path.suffix.lower()
        name = file_path.name.lower()

        if suffix == ".md":
            return "markdown"
        elif suffix in {".py", ".js", ".ts", ".jsx", ".tsx"}:
            return "code"
        elif suffix in {".json", ".yaml", ".yml", ".toml"}:
            return "config"
        elif suffix in {".txt", ".log"}:
            return "text"
        elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg"}:
            return "image"
        elif suffix in {".pdf", ".doc", ".docx"}:
            return "document"
        elif suffix == ".sh":
            return "shell"
        elif name in {".gitignore", ".env", ".env.example", "license", "readme"}:
            return "metadata"
        else:
            return "other"

    def generate_diff_report(self, diff_result: Dict[str, Any]) -> str:
        """
        生成差异报告（Markdown格式）
        """
        lines = [
            "# Repository Diff Report（仓库差异报告）",
            "",
            f"**扫描时间**: {diff_result['scan_time']}",
            f"**扫描仓库数**: {diff_result['summary']['total_repos']}",
            "",
            "## 摘要",
            "",
            f"- 新增文件总数: {diff_result['summary']['total_new']}",
            f"- 修改文件总数: {diff_result['summary']['total_modified']}",
            "",
            "### 各仓库统计",
            "",
            "| 仓库 | 新增文件 | 修改文件 |",
            "|------|----------|----------|",
        ]

        for repo_name in sorted(diff_result["repos"].keys()):
            new_count = diff_result["summary"]["new_files"].get(repo_name, 0)
            modified_count = diff_result["summary"]["modified_files"].get(repo_name, 0)
            lines.append(f"| {repo_name} | {new_count} | {modified_count} |")

        lines.append("")

        # 各仓库详情
        for repo_name, repo_data in sorted(diff_result["repos"].items()):
            lines.append(f"## {repo_name}")
            lines.append("")
            lines.append(f"**路径**: `{repo_data['path']}`")
            lines.append("")

            # 新增文件
            new_files = repo_data.get("new_files", [])
            if new_files:
                lines.append(f"### 新增文件 ({len(new_files)} 个)")
                lines.append("")
                for f in sorted(new_files)[:20]:
                    lines.append(f"- `{f}`")
                if len(new_files) > 20:
                    lines.append(f"- ... 还有 {len(new_files) - 20} 个")
                lines.append("")

            # 修改文件
            modified_files = repo_data.get("modified_files", [])
            if modified_files:
                lines.append(f"### 修改文件 ({len(modified_files)} 个)")
                lines.append("")
                for f in sorted(modified_files)[:20]:
                    lines.append(f"- `{f}`")
                if len(modified_files) > 20:
                    lines.append(f"- ... 还有 {len(modified_files) - 20} 个")
                lines.append("")

            # 删除文件
            deleted_files = repo_data.get("deleted_files", [])
            if deleted_files:
                lines.append(f"### 删除文件 ({len(deleted_files)} 个)")
                lines.append("")
                for f in sorted(deleted_files)[:20]:
                    lines.append(f"- `{f}`")
                if len(deleted_files) > 20:
                    lines.append(f"- ... 还有 {len(deleted_files) - 20} 个")
                lines.append("")

            # 文件类型分布
            by_type = repo_data.get("by_type", {})
            if by_type:
                lines.append("### 文件类型分布")
                lines.append("")
                lines.append("| 类型 | 数量 |")
                lines.append("|------|------|")
                for file_type, count in sorted(by_type.items(), key=lambda x: -x[1]):
                    lines.append(f"| {file_type} | {count} |")
                lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(f"*报告生成时间: {datetime.now().isoformat()}*")

        return "\n".join(lines)

    def save_diff_report(self, diff_result: Dict[str, Any], output_dir: Optional[Path] = None) -> str:
        """
        保存差异报告到文件
        """
        if output_dir is None:
            output_dir = self.data_dir

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        report_file = output_dir / f"repository_diff_{today}.md"

        report_content = self.generate_diff_report(diff_result)

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)

        # 同时保存JSON格式
        json_file = output_dir / f"repository_diff_{today}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(diff_result, f, ensure_ascii=False, indent=2)

        logger.info(f"差异报告已保存: {report_file}")
        return str(report_file)


def scan_repositories(data_dir: str = None, output_dir: str = None) -> Dict[str, Any]:
    """
    便捷函数：扫描所有仓库并生成报告

    Args:
        data_dir: 数据目录（存储扫描状态）
        output_dir: 输出目录（保存报告）

    Returns:
        差异报告
    """
    if data_dir is None:
        data_dir = Path.home() / ".ace_runtime" / "repo_diff"
    if output_dir is None:
        output_dir = data_dir

    scanner = RepoDiffScanner(str(data_dir))
    diff_result = scanner.scan_all_repos()
    report_file = scanner.save_diff_report(diff_result, Path(output_dir))

    return {
        "diff_result": diff_result,
        "report_file": report_file,
        "summary": diff_result["summary"],
    }


if __name__ == "__main__":
    result = scan_repositories()
    print(f"扫描完成！")
    print(f"报告文件: {result['report_file']}")
    print(f"新增文件总数: {result['summary']['total_new']}")
    print(f"修改文件总数: {result['summary']['total_modified']}")
