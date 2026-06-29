"""
ACE Memory System — 双层记忆骨架

从 Claude Code memdir.ts 考古提取的核心骨架。

核心设计：
- 双层记忆：项目级 + 用户级
- 三种类型：user（用户偏好）、feedback（反馈）、project（项目上下文）、reference（参考资料）
- MEMORY.md 作为索引，不存储内容
- 记忆文件使用 frontmatter 格式

这不是复制 Claude Code。
是用 ACE 的方式重写这套骨架。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import frontmatter


class MemoryType(Enum):
    """记忆类型"""
    USER = "user"          # 用户偏好、角色、目标
    FEEDBACK = "feedback"  # 用户的反馈、纠正
    PROJECT = "project"     # 项目上下文、决策、历史
    REFERENCE = "reference" # 参考资料、外部系统指针


@dataclass
class MemoryEntry:
    """记忆条目"""
    title: str
    description: str
    type: MemoryType
    content: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)

    def to_frontmatter(self) -> str:
        """转换为 frontmatter 格式"""
        return frontmatter.dumps(frontmatter.Post(self.content, **{
            "title": self.title,
            "description": self.description,
            "type": self.type.value,
            "created_at": self.created_at or datetime.now().isoformat(),
            "updated_at": self.updated_at or datetime.now().isoformat(),
            "tags": ", ".join(self.tags),
        }))

    @classmethod
    def from_frontmatter(cls, post: frontmatter.Post) -> "MemoryEntry":
        """从 frontmatter 解析"""
        return cls(
            title=post.metadata.get("title", ""),
            description=post.metadata.get("description", ""),
            type=MemoryType(post.metadata.get("type", "project")),
            content=post.content.strip(),
            created_at=datetime.fromisoformat(post.metadata.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(post.metadata.get("updated_at", datetime.now().isoformat())),
            tags=[t.strip() for t in post.metadata.get("tags", "").split(",") if t.strip()],
        )


@dataclass
class MemoryIndex:
    """记忆索引（MEMORY.md）"""
    entries: List[Dict[str, str]] = field(default_factory=list)
    max_entries: int = 200  # 最大条目数（行数限制）
    max_entry_length: int = 150  # 每个条目最大字符数

    def to_markdown(self) -> str:
        """转换为 Markdown 格式"""
        lines = [
            "# Memory",
            "",
        ]
        for entry in self.entries:
            lines.append(f'- [{entry["title"]}]({entry["file"]}) — {entry["hook"]}')
        return "\n".join(lines)

    def add_entry(self, title: str, file: str, hook: str):
        """添加条目"""
        # 截断过长的 hook
        hook = hook[:self.max_entry_length] + "..." if len(hook) > self.max_entry_length else hook
        self.entries.append({
            "title": title,
            "file": file,
            "hook": hook,
        })

    @classmethod
    def from_markdown(cls, content: str) -> "MemoryIndex":
        """从 Markdown 解析"""
        index = cls()
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- ["):
                # 解析: - [Title](file.md) — hook
                try:
                    title_end = line.index("]")
                    title = line[2:title_end]
                    rest = line[title_end + 1:].strip()
                    file_start = rest.index("(") + 1
                    file_end = rest.index(")")
                    file = rest[file_start:file_end]
                    hook = rest[file_end + 2:].lstrip("— ").lstrip()
                    index.add_entry(title, file, hook)
                except ValueError:
                    continue
        return index


class MemoryLayer(Enum):
    """记忆层级"""
    PROJECT = "project"  # 项目级：./memory/ 或 ~/.claude/projects/<slug>/memory/
    USER = "user"       # 用户级：~/.claude/CLAUDE.md
    TEAM = "team"       # 团队级：（可选）


@dataclass
class MemoryConfig:
    """记忆配置"""
    project_dir: str
    user_dir: str = "~/.claude"
    memory_subdir: str = "memory"
    index_file: str = "MEMORY.md"

    @property
    def project_memory_dir(self) -> Path:
        return Path(self.project_dir) / self.memory_subdir

    @property
    def project_memory_index(self) -> Path:
        return self.project_memory_dir / self.index_file

    @property
    def user_memory_index(self) -> Path:
        return Path(self.user_dir) / self.index_file


class ACEBaseMemory:
    """
    ACE 基础记忆类

    对应 Claude Code 的 memdir 系统。

    核心设计：
    1. 双层记忆：项目级 + 用户级
    2. 索引与内容分离：MEMORY.md 只是索引，不存储内容
    3. 类型化记忆：user/feedback/project/reference 四类
    4. 前端约束：MEMORY.md 最多 200 行，每条索引最多 150 字符
    """

    def __init__(self, config: MemoryConfig):
        self.config = config
        self._ensure_dirs()

    def _ensure_dirs(self):
        """确保目录存在"""
        self.config.project_memory_dir.mkdir(parents=True, exist_ok=True)

    def save_memory(
        self,
        title: str,
        description: str,
        content: str,
        memory_type: MemoryType = MemoryType.PROJECT,
        layer: MemoryLayer = MemoryLayer.PROJECT,
    ) -> str:
        """
        保存记忆

        1. 将内容写入独立的 .md 文件
        2. 在 MEMORY.md 索引中添加条目

        参数：
        - title: 记忆标题（用于文件名和索引）
        - description: 简短描述
        - content: 记忆内容
        - memory_type: 记忆类型
        - layer: 记忆层级

        返回：
        - 文件路径
        """
        # 生成安全的文件名
        filename = self._safe_filename(title) + ".md"
        entry = MemoryEntry(
            title=title,
            description=description,
            type=memory_type,
            content=content,
        )

        if layer == MemoryLayer.PROJECT:
            memory_dir = self.config.project_memory_dir
            index_path = self.config.project_memory_index
        else:
            memory_dir = Path(self.config.user_dir)
            index_path = self.config.user_memory_index

        # 写入记忆文件
        memory_path = memory_dir / filename
        memory_path.write_text(entry.to_frontmatter(), encoding="utf-8")

        # 更新索引
        self._update_index(
            index_path,
            title=title,
            file=filename,
            hook=description,
        )

        return str(memory_path)

    def _update_index(
        self, index_path: Path, title: str, file: str, hook: str
    ):
        """更新记忆索引"""
        index = MemoryIndex()
        if index_path.exists():
            index = MemoryIndex.from_markdown(index_path.read_text(encoding="utf-8"))

        # 检查是否已有同名条目
        for entry in index.entries:
            if entry["file"] == file:
                entry["title"] = title
                entry["hook"] = hook
                break
        else:
            index.add_entry(title, file, hook)

        # 写入索引
        index_path.write_text(index.to_markdown(), encoding="utf-8")

    def _safe_filename(self, title: str) -> str:
        """生成安全的文件名"""
        # 移除非字母数字字符，保留连字符
        safe = "".join(c if c.isalnum() else "_" for c in title.lower())
        safe = safe[:50]  # 限制长度
        return safe

    def load_memory_prompt(self) -> str:
        """
        加载记忆提示

        用于注入到 system prompt。
        返回格式化的记忆指南。
        """
        project_index = self.config.project_memory_index
        user_index = self.config.user_memory_index

        lines = [
            "# Memory",
            "",
            "You have a persistent, file-based memory system.",
            "",
            "## Memory types",
            "- user: User preferences, role, goals",
            "- feedback: User corrections and preferences",
            "- project: Project context, decisions, history",
            "- reference: External references, links, pointers",
            "",
        ]

        # 加载项目级记忆
        if project_index.exists():
            project_lines = project_index.read_text(encoding="utf-8").split("\n")
            lines.append("## Project Memory")
            lines.append(f"Location: `{self.config.project_memory_dir}`")
            lines.append("")
            lines.extend([l for l in project_lines if l.strip()])
            lines.append("")

        # 加载用户级记忆
        if user_index.exists():
            user_lines = user_index.read_text(encoding="utf-8").split("\n")
            lines.append("## User Memory")
            lines.append(f"Location: `{self.config.user_memory_index}`")
            lines.append("")
            lines.extend([l for l in user_lines if l.strip()])

        return "\n".join(lines)

    def search_memory(self, query: str) -> List[MemoryEntry]:
        """
        搜索记忆

        参数：
        - query: 搜索关键词

        返回：
        - 匹配的记忆条目列表
        """
        results = []

        # 搜索项目记忆
        if self.config.project_memory_dir.exists():
            for md_file in self.config.project_memory_dir.glob("*.md"):
                if md_file.name == self.config.index_file:
                    continue
                try:
                    post = frontmatter.loads(md_file.read_text(encoding="utf-8"))
                    entry = MemoryEntry.from_frontmatter(post)

                    # 简单匹配
                    if (query.lower() in entry.title.lower() or
                        query.lower() in entry.description.lower() or
                        query.lower() in entry.content.lower()):
                        results.append(entry)
                except Exception:
                    continue

        return results


class ACETeamMemory(ACEBaseMemory):
    """
    ACE 团队记忆

    扩展基础记忆，支持团队共享。
    对应 Claude Code 的 TEAMMEM feature。
    """

    def __init__(self, config: MemoryConfig, team_dir: str):
        super().__init__(config)
        self.team_dir = Path(team_dir)
        self.team_dir.mkdir(parents=True, exist_ok=True)

    def save_team_memory(
        self,
        title: str,
        description: str,
        content: str,
        memory_type: MemoryType = MemoryType.PROJECT,
    ) -> str:
        """保存团队记忆"""
        return self.save_memory(
            title=f"team_{title}",
            description=description,
            content=content,
            memory_type=memory_type,
            layer=MemoryLayer.TEAM,
        )


@dataclass
class MemoryUsageGuide:
    """
    记忆使用指南

    对应 Claude Code 的 buildMemoryLines 函数。
    指导如何正确使用记忆系统。
    """

    WHAT_TO_SAVE = """
## What to save

- User preferences ("use bun, not npm")
- Project context not derivable from code (deadlines, decisions, rationale)
- External system pointers (dashboards, Linear projects, Slack channels)
- Facts about the user, their role, or their goals
"""

    WHAT_NOT_TO_SAVE = """
## What NOT to save

- Information derivable from the current project (code patterns, architecture)
- Temporary state or current conversation context
- Raw file content or command output
- Information that is likely to change frequently
"""

    HOW_TO_SAVE = """
## How to save a memory

1. Write the memory to its own file using frontmatter:
   ```
   ---
   title: Memory Title
   description: One-line hook
   type: project
   created_at: 2026-06-29
   ---
   Memory content here...
   ```

2. Add a pointer to MEMORY.md:
   - [Title](filename.md) — one-line hook
   - Keep entries under 150 characters

3. Update or remove memories that become outdated.
   - Do not write duplicate memories.
   """

    WHEN_TO_ACCESS = """
## When to access memory

- When the user explicitly asks you to remember something
- At the start of a new conversation
- When making decisions that affect the project
"""

    @classmethod
    def to_prompt(cls) -> str:
        """生成使用指南提示"""
        return "\n".join([
            "# Memory System",
            "",
            cls.WHAT_TO_SAVE,
            cls.WHAT_NOT_TO_SAVE,
            cls.HOW_TO_SAVE,
            cls.WHEN_TO_ACCESS,
        ])
