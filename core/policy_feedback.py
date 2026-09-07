import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class PolicyCardStore:
    SCHEMA_VERSION = 1

    def __init__(self, data_dir: Any):
        self.data_dir = Path(data_dir)
        self.cards_path = self.data_dir / "policy_cards.json"

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _tokens(*values: Any) -> List[str]:
        tokens: List[str] = []
        for value in values:
            text = str(value or "").lower()
            for token in re.findall(r"[a-z0-9_]+", text):
                if len(token) > 2 and token not in tokens:
                    tokens.append(token)
            for sequence in re.findall(r"[\u4e00-\u9fff]+", text):
                for size in range(2, min(4, len(sequence)) + 1):
                    for start in range(len(sequence) - size + 1):
                        token = sequence[start:start + size]
                        if token not in tokens:
                            tokens.append(token)
        return tokens

    @classmethod
    def _card_id(cls, task_id: str, receipt: Dict[str, Any]) -> str:
        canonical = json.dumps(
            {
                "task_id": task_id,
                "result_ref": receipt.get("result_ref", ""),
                "verification_ref": receipt.get("verification_ref", ""),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "POL-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def _load(self) -> List[Dict[str, Any]]:
        if not self.cards_path.exists():
            return []
        try:
            value = json.loads(self.cards_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return []
        return value.get("cards", []) if isinstance(value, dict) and isinstance(value.get("cards"), list) else []

    def _save(self, cards: List[Dict[str, Any]]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.cards_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"schema_version": self.SCHEMA_VERSION, "cards": cards},
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.cards_path)

    @classmethod
    def _eligible_receipt(cls, receipt: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(receipt, dict) or receipt.get("status") != "VERIFIED":
            return None
        refs = []
        for ref in receipt.get("evidence_refs", []):
            text = cls._text(ref)
            if text and text not in refs:
                refs.append(text)
        try:
            groups = int(receipt.get("independent_evidence_groups", 0))
        except (TypeError, ValueError):
            groups = 0
        if len(refs) < 2 or groups < 2:
            return None
        if not cls._text(receipt.get("result_ref")) or not cls._text(receipt.get("verification_ref")):
            return None
        return {**receipt, "evidence_refs": refs, "independent_evidence_groups": groups}

    def project(self, task: Any) -> Optional[Dict[str, Any]]:
        outputs = getattr(task, "outputs", None)
        receipt = self._eligible_receipt(
            outputs.get("verified_outcome_receipt") if isinstance(outputs, dict) else None
        )
        if receipt is None:
            return None
        task_id = self._text(getattr(task, "task_id", ""))
        if not task_id:
            return None
        if self._text(receipt.get("task_id")) != task_id:
            return None
        title = self._text(getattr(task, "title", ""))
        hypothesis = self._text(getattr(task, "hypothesis", ""))
        tags = [self._text(tag) for tag in getattr(task, "tags", []) if self._text(tag)]
        card_id = self._card_id(task_id, receipt)
        card = {
            "schema_version": self.SCHEMA_VERSION,
            "card_id": card_id,
            "status": "active",
            "source_receipt": task_id,
            "source_task_id": task_id,
            "context_signature": " ".join(self._tokens(title, hypothesis, tags)),
            "action": f"research:{title.lower()}",
            "outcome": self._text(getattr(task, "result", "")),
            "evidence_refs": receipt["evidence_refs"],
            "independent_evidence_groups": receipt["independent_evidence_groups"],
            "rank_boost": 0.1,
            "applicability": tags,
            "failure_conditions": ["requires matching task context", "requires future independent verification"],
            "source_result_ref": receipt["result_ref"],
            "source_verification_ref": receipt["verification_ref"],
            "verified_at": self._text(receipt.get("verified_at")),
        }
        cards = self._load()
        for existing in cards:
            if isinstance(existing, dict) and existing.get("card_id") == card_id:
                return existing
        cards.append(card)
        self._save(cards)
        return card

    def list_cards(self) -> List[Dict[str, Any]]:
        return [dict(card) for card in self._load() if isinstance(card, dict) and card.get("status") == "active"]

    def rank_candidates(self, task: Any, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        context = set(
            self._tokens(
                getattr(task, "title", ""),
                getattr(task, "hypothesis", ""),
                getattr(task, "tags", []),
            )
        )
        ranked = []
        for index, candidate in enumerate(candidates):
            value = dict(candidate)
            candidate_tokens = set(self._tokens(value.get("hypothesis", ""), value.get("keywords", [])))
            matches = []
            for card in self.list_cards():
                card_tokens = set(self._tokens(card.get("context_signature", ""), card.get("applicability", [])))
                if context & card_tokens and candidate_tokens & card_tokens:
                    matches.append({
                        "card_id": card["card_id"],
                        "source_receipt": card["source_receipt"],
                        "evidence_refs": list(card["evidence_refs"]),
                    })
            if matches:
                value["policy_feedback"] = matches
                rank_boost = sum(
                    float(card.get("rank_boost", 0.0))
                    for card in self.list_cards()
                    if any(match["card_id"] == card.get("card_id") for match in matches)
                )
                value["confidence"] = min(1.0, float(value.get("confidence", 0.0)) + rank_boost)
            ranked.append((value, index))
        ranked.sort(
            key=lambda item: (
                0 if item[0].get("policy_feedback") else 1,
                -float(item[0].get("confidence", 0.0)),
                item[1],
            )
        )
        return [candidate for candidate, _ in ranked]
