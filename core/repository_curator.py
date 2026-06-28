"""
Repository Curator — 仓库馆长

职责边界（唯一有权决定同步的 Agent）：
  ✓ 审查 Researcher 和 Engineering Agent 的产出
  ✓ 计算价值评分
  ✓ 相似度检测
  ✓ 决定：放哪里、更新哪个、是否重复、是否覆盖、是否拆分
  ✓ 生成同步计划（Sync Plan）
  ✓ 调用 SyncManager 执行
  ✗ 不生产知识
  ✗ 不写代码
  ✗ 不执行同步（委托给 SyncManager）

触发时机：每天任务结束后自动唤醒（Today's Work Finished）
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .value_scorer import ValueScorer, ArtifactScore

logger = logging.getLogger(__name__)


# 馆长权限矩阵
PERMISSION_MATRIX = {
    "Research Agent": {
        "create": True,
        "modify": True,
        "sync": False,   # 禁止！只能交付给馆长
        "git_push": False,
    },
    "Engineering Agent": {
        "code": True,
        "test": True,
        "sync": False,   # 禁止！只能交付给馆长
        "git_push": False,
    },
    "Repository Curator": {
        "compare": True,
        "merge": True,
        "split": True,
        "archive": True,
        "git_push": True,  # 唯一有权
        "backup": True,
        "repo_review": True,
    },
}


@dataclass
class ArtifactDecision:
    """产物决策"""
    artifact_id: str
    artifact: Dict[str, Any]  # 原始产物
    score: ArtifactScore
    action: str = "create"  # create / update / merge / discard / split
    target_repo: str = ""
    target_path: str = ""
    similar_existing: Optional[Dict] = None  # 最相似的已有文档
    split_parts: List[Dict] = field(default_factory=list)  # 拆分建议
    reason: str = ""
    override: bool = False  # 是否人工覆盖默认决策


@dataclass
class SyncPlan:
    """同步计划"""
    created_at: str = ""
    total_artifacts: int = 0
    decisions: List[ArtifactDecision] = field(default_factory=list)
    create_list: List[Dict] = field(default_factory=list)
    update_list: List[Dict] = field(default_factory=list)
    merge_list: List[Dict] = field(default_factory=list)
    discard_list: List[Dict] = field(default_factory=list)
    split_list: List[Dict] = field(default_factory=list)
    summary: str = ""


class RepositoryCurator:
    """
    Repository Curator — 仓库馆长
    
    唯一有权决定同步的 Agent
    """
    
    # 产物目录扫描配置
    ARTIFACT_DIRS = [
        "08_ARCHAEOLOGY",
        "09_KNOWLEDGE",
        "04_PROTOCOLS",
        "02_MEMORY",
        "06_RUNTIME",
    ]
    
    def __init__(
        self,
        ace_runtime_dir: str,
        mine_seed_dir: str,
        ace_core_dir: str,
        similarity_engine: Any = None,  # SimilarityEngine
        value_scorer: Optional[ValueScorer] = None,
        sync_manager: Any = None,  # SyncManager
        data_dir: Optional[str] = None,
    ):
        """
        初始化 Repository Curator
        
        Args:
            ace_runtime_dir: ace_runtime 根目录
            mine_seed_dir: mine_seed 目录
            ace_core_dir: ace_core 目录
            similarity_engine: 相似度引擎实例
            value_scorer: 价值评分器实例
            sync_manager: 同步管理器实例
            data_dir: 数据存储目录
        """
        self.ace_runtime_dir = Path(ace_runtime_dir)
        self.mine_seed_dir = Path(mine_seed_dir)
        self.ace_core_dir = Path(ace_core_dir)
        
        # 数据目录
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = self.ace_runtime_dir / "06_RUNTIME" / "ace" / "data" / "curator"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 子目录
        self.archive_dir = self.data_dir / "archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        # 组件
        self.similarity_engine = similarity_engine
        self.value_scorer = value_scorer or ValueScorer(data_dir=self.data_dir)
        self.sync_manager = sync_manager
        
        # 运行状态
        self._last_run: Optional[datetime] = None
        self._run_count: int = 0
        
        # 加载历史记录
        self._history: List[Dict] = self._load_history()
    
    def wakeup(self, triggered_by: str = "scheduled") -> Dict[str, Any]:
        """
        馆长唤醒入口
        
        Args:
            triggered_by: "scheduled" / "manual" / "task_complete"
        
        Returns:
            执行结果报告
        """
        logger.info(f"Repository Curator 唤醒 (triggered_by={triggered_by})")
        
        start_time = datetime.now()
        
        try:
            result = self.run_daily_curation()
            
            result["triggered_by"] = triggered_by
            result["started_at"] = start_time.isoformat()
            result["finished_at"] = datetime.now().isoformat()
            result["duration_seconds"] = (datetime.now() - start_time).total_seconds()
            
            # 保存运行记录
            self._save_run_record(result)
            
            self._last_run = start_time
            self._run_count += 1
            
            return result
            
        except Exception as e:
            logger.exception("馆长执行失败")
            return {
                "status": "error",
                "error": str(e),
                "triggered_by": triggered_by,
                "started_at": start_time.isoformat(),
                "finished_at": datetime.now().isoformat(),
            }
    
    def run_daily_curation(self) -> Dict[str, Any]:
        """
        每日馆长流程
        
        Returns:
            {
                "artifacts_scanned": int,
                "decisions": List[ArtifactDecision],
                "sync_plan": SyncPlan,
                "duplicates_found": List,
                "split_candidates": List,
                "summary": str,
            }
        """
        logger.info("开始每日馆长流程")
        
        # 1. 收集今日产物
        artifacts = self._collect_today_artifacts()
        logger.info(f"收集到 {len(artifacts)} 个产物")
        
        # 2. 扫描目标仓库
        existing_docs = self._scan_target_repos()
        logger.info(f"目标仓库有 {len(existing_docs)} 个已有文档")
        
        # 3. 对每个产物做决策
        decisions = self._make_decisions(artifacts, existing_docs)
        logger.info(f"生成 {len(decisions)} 个决策")
        
        # 4. 生成同步计划
        sync_plan = self._generate_sync_plan(decisions)
        
        # 5. 提取需要关注的项
        duplicates = [d for d in decisions if d.action in ("update", "merge")]
        splits = [d for d in decisions if d.action == "split"]

        # 6. 生成带签名的同步计划并执行
        if self.sync_manager and sync_plan.create_list:
            try:
                # 序列化决策为可传递的 dict
                plan_dict = sync_plan.__dict__.copy()
                plan_dict["decisions"] = [
                    {"action": d.action, "artifact_id": d.artifact_id,
                     "source_path": d.artifact.get("path", ""),
                     "target_repo": d.target_repo, "target_path": d.target_path}
                    for d in decisions if d.action in ("create", "update", "merge")
                ]
                # 生成签名
                import hashlib
                plan_hash = hashlib.md5(json.dumps(plan_dict, sort_keys=True).encode()).hexdigest()
                timestamp = datetime.now().isoformat()
                raw_sig = f"{self.sync_manager.curator_id}:{timestamp}:{plan_hash}:{self.sync_manager.curator_secret}"
                signature = hashlib.sha256(raw_sig.encode()).hexdigest()[:16]
                plan_dict["curator_signature"] = signature
                plan_dict["timestamp"] = timestamp
                plan_dict["plan_hash"] = plan_hash

                sync_results = self.sync_manager.execute_plan(plan_dict)
                sync_plan.summary += f"\n同步执行: {len([r for r in sync_results if r.success])}/{len(sync_results)} 成功"
            except Exception as e:
                logger.error(f"同步执行失败: {e}")
                sync_plan.summary += f"\n同步执行失败: {e}"
        
        return {
            "artifacts_scanned": len(artifacts),
            "decisions": [self._decision_to_dict(d) for d in decisions],
            "sync_plan_summary": sync_plan.summary,
            "duplicates_found": [self._decision_to_dict(d) for d in duplicates],
            "split_candidates": [self._decision_to_dict(d) for d in splits],
            "summary": sync_plan.summary,
        }

    def _decision_to_dict(self, decision: ArtifactDecision) -> Dict:
        """将 ArtifactDecision 转换为可序列化字典"""
        return {
            "artifact_id": decision.artifact_id,
            "action": decision.action,
            "target_repo": decision.target_repo,
            "target_path": decision.target_path,
            "reason": decision.reason,
            "title": decision.artifact.get("title", "") if decision.artifact else "",
        }
    
    def _collect_today_artifacts(self) -> List[Dict[str, Any]]:
        """
        收集今日新产物
        
        扫描 ace_runtime 中的产物目录：
        - 08_ARCHAEOLOGY/ (考古报告)
        - 09_KNOWLEDGE/ (经验)
        - 04_PROTOCOLS/ (协议)
        - 02_MEMORY/ (记忆)
        - core/ (代码)
        """
        artifacts = []
        today = datetime.now().strftime("%Y-%m-%d")
        
        for dir_name in self.ARTIFACT_DIRS:
            artifact_dir = self.ace_runtime_dir / dir_name
            if not artifact_dir.exists():
                continue
            
            # 扫描所有文件
            for filepath in artifact_dir.rglob("*"):
                if not filepath.is_file():
                    continue
                
                # 跳过非产物文件
                if filepath.suffix not in (".md", ".json", ".py", ".yaml", ".yml"):
                    continue
                
                try:
                    # 获取文件元数据
                    stat = filepath.stat()
                    mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
                    
                    # 只处理今天的文件（简化版：实际应该用日期比较）
                    # 这里暂时处理所有文件，用于初始化
                    
                    content = ""
                    if filepath.suffix in (".md", ".py", ".yaml", ".yml"):
                        content = filepath.read_text(encoding="utf-8")
                    elif filepath.suffix == ".json":
                        try:
                            json.loads(filepath.read_text(encoding="utf-8"))
                        except Exception:
                            continue
                    
                    # 提取标题（从文件名或内容）
                    title = filepath.stem
                    if filepath.suffix == ".md":
                        # 尝试从内容提取标题
                        first_line = content.split("\n")[0] if content else ""
                        if first_line.startswith("# "):
                            title = first_line[2:].strip()
                    
                    # 推断作者（从路径或注释）
                    author = self._infer_author(filepath, content)
                    
                    artifact = {
                        "path": str(filepath),
                        "title": title,
                        "content": content[:5000] if content else "",  # 限制长度
                        "author": author,
                        "type": filepath.suffix[1:],  # 去掉点
                        "size": stat.st_size,
                        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "similar_docs": [],
                    }
                    
                    artifacts.append(artifact)
                    
                except Exception as e:
                    logger.warning(f"处理文件失败 {filepath}: {e}")
                    continue
        
        return artifacts
    
    def _infer_author(self, filepath: Path, content: str) -> str:
        """推断作者身份"""
        # 从文件路径推断
        path_str = str(filepath).lower()
        
        if "archaeology" in path_str:
            return "archaeology_agent"
        elif "knowledge" in path_str:
            return "research_agent"
        elif "protocol" in path_str:
            return "protocol_agent"
        elif "memory" in path_str:
            return "memory_agent"
        elif "runtime" in path_str or "core" in path_str:
            return "engineering_agent"
        
        # 从内容注释推断
        if content:
            first_lines = content.split("\n")[:5]
            for line in first_lines:
                if "author:" in line.lower():
                    return line.split("author:")[-1].strip()
                if "@author" in line.lower():
                    return line.split("@author")[-1].strip()
        
        return "unknown"
    
    def _scan_target_repos(self) -> List[Dict[str, Any]]:
        """
        扫描目标仓库，生成文档索引
        
        扫描 mine_seed 和 ace_core 中的现有文档
        """
        existing_docs = []
        
        # 扫描目标目录
        target_dirs = [
            (self.mine_seed_dir, "mine_seed"),
            (self.ace_core_dir, "ace_core"),
        ]
        
        for base_dir, repo_name in target_dirs:
            if not base_dir.exists():
                continue
            
            for dir_name in self.ARTIFACT_DIRS:
                doc_dir = base_dir / dir_name
                if not doc_dir.exists():
                    continue
                
                for filepath in doc_dir.rglob("*.md"):
                    try:
                        content = filepath.read_text(encoding="utf-8")
                        
                        # 提取标题
                        title = filepath.stem
                        first_line = content.split("\n")[0] if content else ""
                        if first_line.startswith("# "):
                            title = first_line[2:].strip()
                        
                        doc = {
                            "path": str(filepath),
                            "title": title,
                            "content": content[:3000],  # 限制长度
                            "repo": repo_name,
                            "category": dir_name,
                            "type": "md",
                        }
                        
                        existing_docs.append(doc)
                        
                    except Exception as e:
                        logger.warning(f"扫描文档失败 {filepath}: {e}")
                        continue
        
        # 相似度引擎索引（如果支持的话）
        if self.similarity_engine and hasattr(self.similarity_engine, "index_documents"):
            try:
                self.similarity_engine.index_documents(existing_docs)
            except Exception as e:
                logger.warning(f"相似度索引建立失败: {e}")
        
        return existing_docs
    
    def _make_decisions(self, artifacts: List[Dict], existing_docs: List[Dict]) -> List[ArtifactDecision]:
        """
        对每个产物做出决策
        """
        decisions = []
        
        for artifact in artifacts:
            # 1. 相似度检测
            similar_docs = []
            if self.similarity_engine and existing_docs:
                try:
                    similar_docs = self.similarity_engine.find_similar(
                        artifact.get("content", ""),
                        existing_docs,
                        threshold=0.7,
                        top_k=3,
                    )
                except Exception as e:
                    logger.warning(f"相似度检测失败: {e}")
            
            artifact["similar_docs"] = similar_docs
            
            # 2. 评分
            score = self.value_scorer.score(artifact)
            
            # 3. 获取最相似的已有文档
            similar_existing = similar_docs[0] if similar_docs else None
            
            # 4. 构建决策
            decision = ArtifactDecision(
                artifact_id=self._generate_artifact_id(artifact),
                artifact=artifact,
                score=score,
                action=score.action,
                target_repo=score.target_repo,
                target_path=score.target_path,
                similar_existing=similar_existing,
                split_parts=score.split_candidates,
                reason=score.reason,
            )
            
            decisions.append(decision)
        
        return decisions
    
    def _generate_sync_plan(self, decisions: List[ArtifactDecision]) -> SyncPlan:
        """
        生成同步计划
        """
        plan = SyncPlan(
            created_at=datetime.now().isoformat(),
            total_artifacts=len(decisions),
            decisions=decisions,
        )
        
        for decision in decisions:
            item = {
                "artifact_id": decision.artifact_id,
                "artifact": decision.artifact,
                "target_repo": decision.target_repo,
                "target_path": decision.target_path,
                "reason": decision.reason,
            }
            
            if decision.action == "create":
                plan.create_list.append(item)
            elif decision.action == "update":
                plan.update_list.append(item)
            elif decision.action == "merge":
                plan.merge_list.append(item)
            elif decision.action == "discard":
                plan.discard_list.append(item)
            elif decision.action == "split":
                plan.split_list.append(item)
        
        # 生成摘要
        summary_parts = []
        if plan.create_list:
            summary_parts.append(f"新增: {len(plan.create_list)}")
        if plan.update_list:
            summary_parts.append(f"更新: {len(plan.update_list)}")
        if plan.merge_list:
            summary_parts.append(f"合并: {len(plan.merge_list)}")
        if plan.discard_list:
            summary_parts.append(f"丢弃: {len(plan.discard_list)}")
        if plan.split_list:
            summary_parts.append(f"拆分: {len(plan.split_list)}")
        
        plan.summary = " | ".join(summary_parts) if summary_parts else "无变更"
        
        return plan
    
    def _generate_artifact_id(self, artifact: Dict) -> str:
        """生成产物唯一ID"""
        path = artifact.get("path", "")
        title = artifact.get("title", "")
        
        # 使用路径的哈希作为ID基础
        import hashlib
        content = f"{path}:{title}"
        hash_val = hashlib.md5(content.encode()).hexdigest()[:8]
        
        return f"artifact_{hash_val}"
    
    def _load_history(self) -> List[Dict]:
        """加载历史记录"""
        history_file = self.data_dir / "curation_history.json"
        
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        
        return []
    
    def _save_run_record(self, result: Dict[str, Any]):
        """保存运行记录"""
        history_file = self.data_dir / "curation_history.json"
        
        self._history.append({
            "timestamp": datetime.now().isoformat(),
            "run_count": self._run_count,
            "status": result.get("status", "unknown"),
            "artifacts_scanned": result.get("artifacts_scanned", 0),
            "summary": result.get("summary", ""),
        })
        
        # 只保留最近100条记录
        if len(self._history) > 100:
            self._history = self._history[-100:]
        
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"历史记录保存失败: {e}")
    
    def get_permission(self, agent_name: str, action: str) -> bool:
        """
        查询权限
        
        Args:
            agent_name: Agent 名称
            action: 操作类型
        
        Returns:
            是否允许
        """
        agent_perms = PERMISSION_MATRIX.get(agent_name, {})
        return agent_perms.get(action, False)
    
    def check_permissions(self) -> Dict[str, bool]:
        """
        检查馆长自身权限
        
        Returns:
            权限状态字典
        """
        return PERMISSION_MATRIX.get("Repository Curator", {})
    
    def archive_artifacts(self, artifacts: List[Dict], reason: str = "") -> bool:
        """
        归档产物（逻辑删除）
        
        Args:
            artifacts: 要归档的产物列表
            reason: 归档原因
        
        Returns:
            是否成功
        """
        if not artifacts:
            return True
        
        archive_manifest = {
            "archived_at": datetime.now().isoformat(),
            "reason": reason,
            "count": len(artifacts),
            "artifacts": [],
        }
        
        for artifact in artifacts:
            src_path = Path(artifact.get("path", ""))
            if not src_path.exists():
                continue
            
            # 移动到归档目录
            archive_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{src_path.name}"
            dst_path = self.archive_dir / archive_name
            
            try:
                # 复制到归档目录
                import shutil
                shutil.copy2(src_path, dst_path)
                
                archive_manifest["artifacts"].append({
                    "original_path": str(src_path),
                    "archive_path": str(dst_path),
                    "title": artifact.get("title", ""),
                })
                
            except Exception as e:
                logger.error(f"归档失败 {src_path}: {e}")
        
        # 保存归档清单
        manifest_file = self.archive_dir / f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(archive_manifest, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"归档清单保存失败: {e}")
            return False
