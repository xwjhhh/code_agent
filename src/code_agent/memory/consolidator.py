"""Semantic consolidation for the memory bank."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from code_agent.memory.query_analyzer import TextModel, parse_json_object
from code_agent.memory.schemas import MemoryNode, RetrievedMemory
from code_agent.memory.store import MemoryStore


@dataclass(frozen=True)
class DuplicateJudgment:
    duplicate: bool
    matched_id: str | None = None
    reason: str = ""
    fallback: bool = False


class MemoryConsolidator:
    """Use vectors for candidate recall and an LLM for semantic duplicate judgment."""

    def __init__(
        self,
        store: MemoryStore,
        model: TextModel | None = None,
        duplicate_threshold: float = 0.96,
        candidate_threshold: float = 0.55,
    ):
        self.store = store
        self.model = model
        self.duplicate_threshold = duplicate_threshold
        self.candidate_threshold = candidate_threshold
        self.last_judgment: DuplicateJudgment | None = None

    def is_duplicate(self, node: MemoryNode) -> bool:
        """Return whether an incoming node duplicates an existing same-type node."""
        candidates = self.store.search(
            node.embedding,
            experience_type=node.experience_type,
            # Never let quarantined legacy/speculative rows suppress a new
            # evidence-backed experience.
            verified_only=True,
            limit=8,
            min_similarity=self.candidate_threshold,
            query_text=node.embedding_text,
        )
        if not candidates:
            self.last_judgment = DuplicateJudgment(False, reason="没有相似候选")
            return False

        if self.model is not None:
            judgment = self._judge(node, candidates)
            if judgment is not None:
                self.last_judgment = judgment
                return judgment.duplicate

        best = max(candidates, key=lambda item: item.similarity)
        self.last_judgment = DuplicateJudgment(
            best.similarity >= self.duplicate_threshold,
            matched_id=best.node.id,
            reason=f"向量相似度 {best.similarity:.3f}",
            fallback=True,
        )
        return best.similarity >= self.duplicate_threshold

    def _judge(self, node: MemoryNode, candidates: list[RetrievedMemory]) -> DuplicateJudgment | None:
        compact = [
            {
                "id": item.node.id,
                "experience_type": item.node.experience_type,
                "trigger": item.node.trigger,
                "content": item.node.content,
                "steps": item.node.steps,
                "failure": item.node.failure,
                "fix": item.node.fix,
                "similarity": round(item.similarity, 3),
            }
            for item in candidates[:8]
        ]
        prompt = f"""判断待写入的 reasoning memory 是否与候选 memory 表达同一个可迁移经验。

不要仅凭关键词或相似算法名称判断。只有在适用条件、核心因果关系和行动建议基本相同，
且不会丢失重要约束时，才判定为 duplicate。成功经验和失败经验永远不能互相去重；
不同的算法或相反的遍历方向也不能去重。

待写入 memory:
{_compact_node(node)}

候选 memories:
{compact}

只返回 JSON：{{"duplicate": true|false, "matched_id": "候选 id 或 null", "reason": "简短中文理由"}}"""
        try:
            response = self.model.query_text(
                [
                    {"role": "system", "content": "You are a strict semantic duplicate judge for reasoning memories. Return JSON only."},
                    {"role": "user", "content": prompt},
                ]
            )
            data = parse_json_object(response)
            duplicate = data.get("duplicate")
            if not isinstance(duplicate, bool):
                return None
            matched_id = data.get("matched_id")
            if not isinstance(matched_id, str) or matched_id not in {item.node.id for item in candidates}:
                matched_id = None
            return DuplicateJudgment(
                duplicate=duplicate,
                matched_id=matched_id,
                reason=str(data.get("reason", "")).strip(),
            )
        except Exception:
            return None


def _compact_node(node: MemoryNode) -> dict[str, Any]:
    return {
        "experience_type": node.experience_type,
        "trigger": node.trigger,
        "content": node.content,
        "steps": node.steps,
        "failure": node.failure,
        "fix": node.fix,
    }
