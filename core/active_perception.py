"""
Active Perception Layer（主动感知层）

核心职责：
- 在发现任何碎片时，自动提取线索
- 主动扫描碎片中提及的新位置
- 形成"发现→提取线索→扩展扫描→发现更多线索"的正向循环

线索类型：
- 关键词（人名、项目名、技术术语）
- 文件路径引用
- 项目名/仓库名
- GitHub URL
- Telegram消息ID
- 时间戳
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Set
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Clue:
    """线索"""
    type: str  # keyword/path/project/url/mention/telegram_id
    value: str
    source_file: str = ""
    source_context: str = ""  # 出现时的上下文
    discovered_at: str = ""


@dataclass
class PerceptionResult:
    """感知结果"""
    original_file: str
    clues: List[Clue] = field(default_factory=list)
    expanded_paths: List[str] = field(default_factory=list)
    new_artifacts: List[str] = field(default_factory=list)


class ActivePerceptionLayer:
    """
    主动感知层

    工作流程：
    1. 接收一个文件/碎片
    2. 自动提取其中的线索
    3. 主动扫描线索指向的新位置
    4. 返回新发现的线索和文件
    """

    def __init__(self, ace_runtime_dir: str):
        """
        初始化主动感知层

        Args:
            ace_runtime_dir: ACE Runtime根目录
        """
        self.ace_runtime_dir = Path(ace_runtime_dir)
        self.telegram_archive_dir = self.ace_runtime_dir / "telegram_archive"
        self.mine_seed_dir = self.ace_runtime_dir.parent / "mine-seed"

        # 已扫描过的路径（避免重复扫描）
        self._scanned_paths: Set[str] = set()

        # 线索数据库
        self.clues_db_file = self.ace_runtime_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "perception_clues.jsonl"

    def perceive(self, file_path: str, content: str = None) -> PerceptionResult:
        """
        对一个文件进行主动感知

        Args:
            file_path: 文件路径
            content: 文件内容（如果已知）

        Returns:
            感知结果，包含提取的线索和扩展扫描发现的新文件
        """
        logger.info(f"主动感知: {file_path}")

        result = PerceptionResult(original_file=file_path)

        # 1. 读取文件内容
        if content is None:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.warning(f"读取文件失败: {file_path} - {e}")
                return result

        # 2. 提取线索
        clues = self._extract_clues(file_path, content)
        result.clues = clues
        logger.info(f"提取到 {len(clues)} 个线索")

        # 3. 根据线索扩展扫描
        for clue in clues:
            if clue.type == "path":
                # 尝试扫描引用的文件路径
                expanded = self._try_scan_path(clue.value)
                if expanded:
                    result.expanded_paths.extend(expanded)

            elif clue.type == "project":
                # 尝试扫描项目目录
                expanded = self._try_scan_project(clue.value)
                if expanded:
                    result.expanded_paths.extend(expanded)

            elif clue.type == "url":
                # 记录URL但不主动访问
                logger.info(f"发现URL引用: {clue.value}")

        # 4. 扫描同一目录下的相关文件
        related = self._scan_related_files(file_path)
        result.new_artifacts.extend(related)

        # 5. 保存发现的线索
        self._save_clues(result)

        return result

    def _extract_clues(self, file_path: str, content: str) -> List[Clue]:
        """从内容中提取线索"""
        clues = []

        # 1. 提取文件路径引用
        path_patterns = [
            r'["\']([a-zA-Z]:[/\\][^\"\']+\.(md|py|json|yaml|yml|txt))["\']',  # 带引号的路径
            r'(?:from|import)\s+["\']([^"\']+)["\']',  # Python import
            r'(?:href|src)=\["\']([^"\']+)["\']',  # HTML/CSS引用
        ]

        for pattern in path_patterns:
            for match in re.finditer(pattern, content):
                path = match.group(1).strip()
                if Path(path).exists() or self._is_relative_path(path):
                    clue = Clue(
                        type="path",
                        value=path,
                        source_file=file_path,
                        source_context=self._get_context(content, match.start()),
                    )
                    clues.append(clue)

        # 2. 提取项目名/仓库名
        project_patterns = [
            r'(?:project|repo|repository)[:\s]+([a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)',
            r'github\.com/([a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)',
            r'(?:mine-seed|r1-archaeology|ace_runtime|ace_core)[a-zA-Z0-9_-]*',
        ]

        for pattern in project_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                project = match.group(1).strip()
                if project:
                    clue = Clue(
                        type="project",
                        value=project,
                        source_file=file_path,
                        source_context=self._get_context(content, match.start()),
                    )
                    clues.append(clue)

        # 3. 提取人名/用户名
        mention_patterns = [
            r'@[a-zA-Z0-9_-]+',  # @username
            r'(?:by|author|from)[:\s]+([A-Z][a-z]+)',  # by xxx
        ]

        for pattern in mention_patterns:
            for match in re.finditer(pattern, content):
                mention = match.group(1).strip()
                if mention and len(mention) > 2:
                    clue = Clue(
                        type="mention",
                        value=mention,
                        source_file=file_path,
                        source_context=self._get_context(content, match.start()),
                    )
                    clues.append(clue)

        # 4. 提取URL
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        for match in re.finditer(url_pattern, content):
            url = match.group(0)
            if any(domain in url for domain in ["github.com", "t.me", "telegram.me"]):
                clue = Clue(
                    type="url",
                    value=url,
                    source_file=file_path,
                    source_context=self._get_context(content, match.start()),
                )
                clues.append(clue)

        # 5. 提取技术术语（连续大写的词）
        tech_terms = re.findall(r'\b[A-Z]{2,}[A-Z0-9]*\b', content)
        for term in set(tech_terms):
            if len(term) >= 3 and term not in ["API", "URL", "ID", "TODO"]:
                clue = Clue(
                    type="keyword",
                    value=term,
                    source_file=file_path,
                    source_context=self._get_context(content, content.find(term)),
                )
                clues.append(clue)

        # 6. 提取Telegram消息ID
        tg_id_pattern = r'(?:t\.me/|tg://|message_)?(\d{8,})'
        for match in re.finditer(tg_id_pattern, content):
            msg_id = match.group(1)
            if len(msg_id) >= 8:
                clue = Clue(
                    type="telegram_id",
                    value=msg_id,
                    source_file=file_path,
                    source_context=self._get_context(content, match.start()),
                )
                clues.append(clue)

        return clues

    def _get_context(self, content: str, position: int, window: int = 50) -> str:
        """获取匹配位置的上下文"""
        start = max(0, position - window)
        end = min(len(content), position + window)
        return content[start:end].replace('\n', ' ').strip()

    def _is_relative_path(self, path: str) -> bool:
        """判断是否是相对路径"""
        return not path.startswith('/') and not path.startswith('\\') and ':' not in path[:2]

    def _try_scan_path(self, path: str) -> List[str]:
        """尝试扫描一个路径"""
        found = []

        # 尝试多种路径组合
        base_dirs = [
            self.ace_runtime_dir,
            self.telegram_archive_dir,
            self.mine_seed_dir,
            self.ace_runtime_dir.parent,
        ]

        for base in base_dirs:
            if self._is_relative_path(path):
                full_path = base / path
            else:
                full_path = Path(path)

            if full_path.exists() and str(full_path) not in self._scanned_paths:
                self._scanned_paths.add(str(full_path))

                if full_path.is_file():
                    found.append(str(full_path))
                elif full_path.is_dir():
                    # 扫描目录下的相关文件
                    for ext in ['.md', '.json', '.py', '.yaml']:
                        found.extend([str(f) for f in full_path.rglob(f'*{ext}')])

        return found

    def _try_scan_project(self, project_name: str) -> List[str]:
        """尝试扫描一个项目目录"""
        found = []

        # 常见的项目位置
        search_dirs = [
            self.ace_runtime_dir.parent,
            self.telegram_archive_dir,
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            # 精确匹配
            project_path = search_dir / project_name
            if project_path.exists():
                self._scanned_paths.add(str(project_path))
                found.append(str(project_path))

            # 模糊匹配
            for item in search_dir.iterdir():
                if item.is_dir() and project_name.lower() in item.name.lower():
                    self._scanned_paths.add(str(item))
                    found.append(str(item))

        return found

    def _scan_related_files(self, file_path: str) -> List[str]:
        """扫描同一目录下的相关文件"""
        related = []

        path = Path(file_path)
        if not path.parent.exists():
            return related

        # 扫描同一目录
        for ext in ['.md', '.json', '.py']:
            siblings = list(path.parent.glob(f'*{ext}'))
            for sibling in siblings:
                if sibling.name != path.name and str(sibling) not in self._scanned_paths:
                    self._scanned_paths.add(str(sibling))
                    related.append(str(sibling))

        # 扫描父目录
        if path.parent.name != path.parent.parent.name:
            for ext in ['.md', '.json']:
                siblings = list(path.parent.parent.glob(f'*{ext}'))
                for sibling in siblings:
                    if str(sibling) not in self._scanned_paths:
                        self._scanned_paths.add(str(sibling))
                        related.append(str(sibling))

        return related

    def _save_clues(self, result: PerceptionResult):
        """保存发现的线索到数据库"""
        try:
            import json
            self.clues_db_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.clues_db_file, "a", encoding="utf-8") as f:
                for clue in result.clues:
                    record = {
                        "type": clue.type,
                        "value": clue.value,
                        "source_file": clue.source_file,
                        "source_context": clue.source_context,
                        "discovered_at": datetime.now().isoformat(),
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

        except Exception as e:
            logger.warning(f"保存线索失败: {e}")

    def get_recent_clues(self, limit: int = 50) -> List[Dict]:
        """获取最近发现的线索"""
        clues = []

        if not self.clues_db_file.exists():
            return clues

        try:
            with open(self.clues_db_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines[-limit:]:
                try:
                    clues.append(json.loads(line.strip()))
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"读取线索失败: {e}")

        return clues

    def reset_scanned_paths(self):
        """重置已扫描路径记录"""
        self._scanned_paths.clear()
