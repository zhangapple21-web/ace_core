"""
Contract Layer — 契约层

职责：
- 在知识进入Repository之前进行多层验证
- 记录每个契约的accept/reject/delay/split/merge决策
- 确保知识符合治理规范

5个契约：
1. Evidence Contract - 证据验证
2. Authority Contract - 权限验证
3. Curator Contract - 馆长决策
4. Repository Contract - 仓库验证
5. Publication Contract - 发布验证

设计原则：
- append-only：所有契约记录永久保留
- 可追溯：每条记录包含完整的决策过程
- 不可绕过：进入Repository必须经过所有契约
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ContractDecision(Enum):
    """契约决策类型"""
    ACCEPT = "accept"
    REJECT = "reject"
    DELAY = "delay"
    SPLIT = "split"
    MERGE = "merge"


class ContractType(Enum):
    """契约类型"""
    EVIDENCE = "evidence"
    AUTHORITY = "authority"
    CURATOR = "curator"
    REPOSITORY = "repository"
    PUBLICATION = "publication"


@dataclass
class ContractRecord:
    """契约记录"""
    contract_type: str
    artifact_id: str
    decision: str
    decision_reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    operator: str = "system"


@dataclass
class EvidenceLevel:
    """证据等级"""
    LEVEL_0 = "no_evidence"      # 无证据
    LEVEL_1 = "weak"             # 弱证据（单一来源）
    LEVEL_2 = "moderate"         # 中等证据（多个来源一致）
    LEVEL_3 = "strong"           # 强证据（多方验证）
    LEVEL_4 = "conclusive"       # 结论性证据（无可争议）


class EvidenceContract:
    """
    证据契约

    验证知识是否有足够的证据支撑：
    - 来源是否可靠
    - 证据链是否完整
    - 是否有交叉验证
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.records_file = self.data_dir / "contracts" / "evidence_contracts.jsonl"
        self.records_file.parent.mkdir(parents=True, exist_ok=True)

    def validate(self, artifact: Dict[str, Any]) -> ContractRecord:
        """
        验证证据

        Args:
            artifact: 待验证的知识产物

        Returns:
            ContractRecord，包含决策结果
        """
        evidence = artifact.get("evidence", [])
        source = artifact.get("source", "")
        confidence = artifact.get("confidence", 0)
        status = artifact.get("status", "HYPOTHESIS")

        issues = []

        # 1. 检查证据是否存在
        if not evidence or (isinstance(evidence, list) and len(evidence) == 0):
            issues.append("无证据支持")

        # 2. 检查来源是否可靠
        if not source:
            issues.append("来源未知")
        elif source.lower() in ["unknown", "undefined"]:
            issues.append("来源不可靠")

        # 3. 根据状态检查证据要求
        if status == "FACT":
            if not evidence or confidence < 0.9:
                issues.append("FACT状态需要高置信度(>=0.9)和充足证据")
        elif status == "VALIDATED":
            if not evidence or confidence < 0.7:
                issues.append("VALIDATED状态需要置信度(>=0.7)")

        # 4. 检查证据链是否完整
        if isinstance(evidence, list):
            for item in evidence:
                if isinstance(item, dict):
                    if not item.get("source") or not item.get("timestamp"):
                        issues.append(f"证据项缺少来源或时间戳: {item}")

        # 做出决策
        if issues:
            decision = ContractDecision.REJECT.value
            reason = "; ".join(issues)
        elif status == "HYPOTHESIS":
            decision = ContractDecision.ACCEPT.value
            reason = "假说无需严格证据，允许进入研究阶段"
        elif confidence >= 0.7:
            decision = ContractDecision.ACCEPT.value
            reason = "证据充足，置信度达标"
        else:
            decision = ContractDecision.DELAY.value
            reason = "证据不足，需要进一步验证"

        record = ContractRecord(
            contract_type=ContractType.EVIDENCE.value,
            artifact_id=artifact.get("id", ""),
            decision=decision,
            decision_reason=reason,
            metadata={
                "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
                "confidence": confidence,
                "status": status,
                "source": source,
            },
            timestamp=datetime.now().isoformat(),
        )

        self._save_record(record)
        return record

    def _save_record(self, record: ContractRecord):
        """保存契约记录"""
        try:
            with open(self.records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "contract_type": record.contract_type,
                    "artifact_id": record.artifact_id,
                    "decision": record.decision,
                    "decision_reason": record.decision_reason,
                    "metadata": record.metadata,
                    "timestamp": record.timestamp,
                    "operator": record.operator,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存证据契约记录失败: {e}")


class AuthorityContract:
    """
    权限契约

    验证操作是否具有权限：
    - 角色权限检查
    - 操作范围检查
    - 安全约束检查
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.records_file = self.data_dir / "contracts" / "authority_contracts.jsonl"
        self.records_file.parent.mkdir(parents=True, exist_ok=True)

        # 权限矩阵
        self.permissions = {
            "research_agent": ["create", "modify", "research"],
            "engineering_agent": ["code", "modify"],
            "repository_curator": ["create", "modify", "delete", "archive", "sync", "govern"],
            "validator": ["validate", "compare"],
            "archivist": ["record", "archive"],
            "system": ["*"],
        }

    def validate(self, artifact: Dict[str, Any], operator: str = "system") -> ContractRecord:
        """
        验证权限

        Args:
            artifact: 待验证的知识产物
            operator: 操作执行者

        Returns:
            ContractRecord，包含决策结果
        """
        action = artifact.get("action", "create")
        artifact_type = artifact.get("type", "")

        issues = []

        # 获取操作者权限
        allowed_actions = self.permissions.get(operator, [])

        # 检查权限
        if "*" not in allowed_actions and action not in allowed_actions:
            issues.append(f"操作者 {operator} 没有 {action} 权限")

        # 特殊约束
        if action == "delete":
            if artifact_type in ["constraint", "axiom", "core_principle"]:
                issues.append("核心约束/公理/原则不允许删除")

        if action == "sync":
            if operator != "repository_curator":
                issues.append("只有Repository Curator有权同步")

        # 做出决策
        if issues:
            decision = ContractDecision.REJECT.value
            reason = "; ".join(issues)
        else:
            decision = ContractDecision.ACCEPT.value
            reason = f"操作者 {operator} 有权执行 {action}"

        record = ContractRecord(
            contract_type=ContractType.AUTHORITY.value,
            artifact_id=artifact.get("id", ""),
            decision=decision,
            decision_reason=reason,
            metadata={
                "operator": operator,
                "action": action,
                "artifact_type": artifact_type,
            },
            timestamp=datetime.now().isoformat(),
            operator=operator,
        )

        self._save_record(record)
        return record

    def _save_record(self, record: ContractRecord):
        """保存契约记录"""
        try:
            with open(self.records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "contract_type": record.contract_type,
                    "artifact_id": record.artifact_id,
                    "decision": record.decision,
                    "decision_reason": record.decision_reason,
                    "metadata": record.metadata,
                    "timestamp": record.timestamp,
                    "operator": record.operator,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存权限契约记录失败: {e}")


class CuratorContract:
    """
    馆长契约

    Repository Curator的决策契约：
    - 价值评估
    - 重复检测
    - 冲突检测
    - 最终决策
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.records_file = self.data_dir / "contracts" / "curator_contracts.jsonl"
        self.records_file.parent.mkdir(parents=True, exist_ok=True)

    def validate(self, artifact: Dict[str, Any], curator_decision: Dict) -> ContractRecord:
        """
        验证馆长决策

        Args:
            artifact: 待验证的知识产物
            curator_decision: 馆长的决策

        Returns:
            ContractRecord，包含决策结果
        """
        decision_type = curator_decision.get("decision", "accept")
        reason = curator_decision.get("reason", "")
        score = curator_decision.get("score", {})

        # 验证决策是否有效
        if decision_type not in ["accept", "reject", "delay", "split", "merge"]:
            decision_type = "reject"
            reason = f"无效决策类型: {decision_type}"

        # 检查决策是否有理由
        if not reason and decision_type != "accept":
            reason = "未提供决策理由"

        record = ContractRecord(
            contract_type=ContractType.CURATOR.value,
            artifact_id=artifact.get("id", ""),
            decision=decision_type,
            decision_reason=reason,
            metadata={
                "score": score,
                "curator_decision": curator_decision,
            },
            timestamp=datetime.now().isoformat(),
            operator="repository_curator",
        )

        self._save_record(record)
        return record

    def _save_record(self, record: ContractRecord):
        """保存契约记录"""
        try:
            with open(self.records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "contract_type": record.contract_type,
                    "artifact_id": record.artifact_id,
                    "decision": record.decision,
                    "decision_reason": record.decision_reason,
                    "metadata": record.metadata,
                    "timestamp": record.timestamp,
                    "operator": record.operator,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存馆长契约记录失败: {e}")


class RepositoryContract:
    """
    仓库契约

    验证知识是否符合仓库规范：
    - 格式检查
    - 元数据完整性
    - 血缘关系检查
    - 引用关系检查
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.records_file = self.data_dir / "contracts" / "repository_contracts.jsonl"
        self.records_file.parent.mkdir(parents=True, exist_ok=True)

    def validate(self, artifact: Dict[str, Any]) -> ContractRecord:
        """
        验证仓库规范

        Args:
            artifact: 待验证的知识产物

        Returns:
            ContractRecord，包含决策结果
        """
        required_fields = ["id", "title", "status", "confidence", "created", "source"]

        issues = []

        # 1. 检查必填字段
        for field in required_fields:
            if field not in artifact or not artifact[field]:
                issues.append(f"缺少必填字段: {field}")

        # 2. 检查status是否合法
        valid_statuses = ["FACT", "EVIDENCE", "HYPOTHESIS", "VALIDATED", "REJECTED", "SUPERSEDED"]
        status = artifact.get("status", "")
        if status not in valid_statuses:
            issues.append(f"无效状态: {status}")

        # 3. 检查confidence范围
        confidence = artifact.get("confidence", 0)
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            issues.append(f"置信度超出范围[0,1]: {confidence}")

        # 4. 检查引用关系
        references = artifact.get("references", [])
        derived_from = artifact.get("derived_from", [])

        # 5. 检查血缘关系
        if "lineage" not in artifact and status in ["VALIDATED", "FACT"]:
            issues.append("VALIDATED/FACT状态需要血缘关系")

        # 做出决策
        if issues:
            decision = ContractDecision.REJECT.value
            reason = "; ".join(issues)
        else:
            decision = ContractDecision.ACCEPT.value
            reason = "符合仓库规范"

        record = ContractRecord(
            contract_type=ContractType.REPOSITORY.value,
            artifact_id=artifact.get("id", ""),
            decision=decision,
            decision_reason=reason,
            metadata={
                "missing_fields": [f for f in required_fields if f not in artifact],
                "references_count": len(references) if isinstance(references, list) else 0,
                "derived_from_count": len(derived_from) if isinstance(derived_from, list) else 0,
            },
            timestamp=datetime.now().isoformat(),
        )

        self._save_record(record)
        return record

    def _save_record(self, record: ContractRecord):
        """保存契约记录"""
        try:
            with open(self.records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "contract_type": record.contract_type,
                    "artifact_id": record.artifact_id,
                    "decision": record.decision,
                    "decision_reason": record.decision_reason,
                    "metadata": record.metadata,
                    "timestamp": record.timestamp,
                    "operator": record.operator,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存仓库契约记录失败: {e}")


class PublicationContract:
    """
    发布契约

    验证知识是否可以发布：
    - 所有前置契约是否通过
    - 是否符合发布标准
    - 是否需要延迟发布
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.records_file = self.data_dir / "contracts" / "publication_contracts.jsonl"
        self.records_file.parent.mkdir(parents=True, exist_ok=True)

    def validate(
        self,
        artifact: Dict[str, Any],
        contract_records: List[ContractRecord]
    ) -> ContractRecord:
        """
        验证发布条件

        Args:
            artifact: 待验证的知识产物
            contract_records: 前置契约记录列表

        Returns:
            ContractRecord，包含决策结果
        """
        issues = []

        # 1. 检查所有前置契约是否通过
        for record in contract_records:
            if record.decision != ContractDecision.ACCEPT.value:
                issues.append(f"{record.contract_type}契约未通过: {record.decision_reason}")

        # 2. 检查状态是否允许发布
        status = artifact.get("status", "")
        if status in ["REJECTED", "SUPERSEDED"]:
            issues.append(f"{status}状态不允许发布")

        # 3. 检查置信度
        confidence = artifact.get("confidence", 0)
        if confidence < 0.5:
            issues.append(f"置信度过低({confidence})，建议延迟发布")

        # 做出决策
        if issues:
            decision = ContractDecision.DELAY.value
            reason = "; ".join(issues)
        else:
            decision = ContractDecision.ACCEPT.value
            reason = "所有契约通过，符合发布标准"

        record = ContractRecord(
            contract_type=ContractType.PUBLICATION.value,
            artifact_id=artifact.get("id", ""),
            decision=decision,
            decision_reason=reason,
            metadata={
                "status": status,
                "confidence": confidence,
                "contract_count": len(contract_records),
            },
            timestamp=datetime.now().isoformat(),
        )

        self._save_record(record)
        return record

    def _save_record(self, record: ContractRecord):
        """保存契约记录"""
        try:
            with open(self.records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "contract_type": record.contract_type,
                    "artifact_id": record.artifact_id,
                    "decision": record.decision,
                    "decision_reason": record.decision_reason,
                    "metadata": record.metadata,
                    "timestamp": record.timestamp,
                    "operator": record.operator,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存发布契约记录失败: {e}")


class ContractManager:
    """
    契约管理器

    协调所有契约的执行流程：
    Evidence → Authority → Curator → Repository → Publication
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.evidence_contract = EvidenceContract(str(self.data_dir))
        self.authority_contract = AuthorityContract(str(self.data_dir))
        self.curator_contract = CuratorContract(str(self.data_dir))
        self.repository_contract = RepositoryContract(str(self.data_dir))
        self.publication_contract = PublicationContract(str(self.data_dir))

    def execute_contracts(
        self,
        artifact: Dict[str, Any],
        operator: str = "system",
        curator_decision: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        执行完整的契约流程

        Args:
            artifact: 待验证的知识产物
            operator: 操作执行者
            curator_decision: 馆长决策（可选）

        Returns:
            契约执行结果
        """
        results = {
            "artifact_id": artifact.get("id", ""),
            "contracts": [],
            "all_passed": False,
            "final_decision": "reject",
        }

        contract_records = []

        # 1. Evidence Contract
        record = self.evidence_contract.validate(artifact)
        contract_records.append(record)
        results["contracts"].append({
            "type": "evidence",
            "decision": record.decision,
            "reason": record.decision_reason,
        })

        if record.decision != ContractDecision.ACCEPT.value:
            results["all_passed"] = False
            results["final_decision"] = record.decision
            return results

        # 2. Authority Contract
        authority_artifact = artifact.copy()
        authority_artifact["operator"] = operator
        record = self.authority_contract.validate(authority_artifact, operator)
        contract_records.append(record)
        results["contracts"].append({
            "type": "authority",
            "decision": record.decision,
            "reason": record.decision_reason,
        })

        if record.decision != ContractDecision.ACCEPT.value:
            results["all_passed"] = False
            results["final_decision"] = record.decision
            return results

        # 3. Curator Contract
        if curator_decision is None:
            curator_decision = {"decision": "accept", "reason": "默认接受"}
        record = self.curator_contract.validate(artifact, curator_decision)
        contract_records.append(record)
        results["contracts"].append({
            "type": "curator",
            "decision": record.decision,
            "reason": record.decision_reason,
        })

        if record.decision != ContractDecision.ACCEPT.value:
            results["all_passed"] = False
            results["final_decision"] = record.decision
            return results

        # 4. Repository Contract
        record = self.repository_contract.validate(artifact)
        contract_records.append(record)
        results["contracts"].append({
            "type": "repository",
            "decision": record.decision,
            "reason": record.decision_reason,
        })

        if record.decision != ContractDecision.ACCEPT.value:
            results["all_passed"] = False
            results["final_decision"] = record.decision
            return results

        # 5. Publication Contract
        record = self.publication_contract.validate(artifact, contract_records)
        contract_records.append(record)
        results["contracts"].append({
            "type": "publication",
            "decision": record.decision,
            "reason": record.decision_reason,
        })

        if record.decision == ContractDecision.ACCEPT.value:
            results["all_passed"] = True
            results["final_decision"] = "accept"
        else:
            results["all_passed"] = False
            results["final_decision"] = record.decision

        return results
