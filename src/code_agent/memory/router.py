"""LLM decisions used by the agentic memory-retrieval flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from code_agent.memory.query_analyzer import TextModel, parse_json_object
from code_agent.memory.schemas import RetrievedMemory


MemoryRouteAction = Literal["retrieve", "skip"]


@dataclass(frozen=True)
class MemoryRoute:
    """Whether the current task should consult long-term memory."""

    action: MemoryRouteAction
    query: str
    reason: str
    fallback: bool = False


@dataclass(frozen=True)
class MemoryRelevance:
    """LLM assessment of whether retrieved memories are useful for a task."""

    relevant: bool
    reason: str
    score: float | None = None
    fallback: bool = False


class MemoryRouter:
    """Choose retrieval, and rewrite a weak query using structured JSON."""

    def __init__(self, model: TextModel):
        self.model = model

    def decide(self, task: str) -> MemoryRoute:
        try:
            response = self.model.query_text(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是编程 Agent 的记忆检索路由器。只返回 JSON。"
                            "记忆库包含已验证的算法策略、失败修复和性能优化经验。"
                            "只有历史经验可能提供可执行帮助时才选择 retrieve；"
                            "全新问题或明显不需要历史经验时选择 skip。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"""判断是否需要检索历史编程经验。

问题：
{task[:12000]}

严格返回：
{{"action":"retrieve|skip","query":"用于检索的简短查询","reason":"一句话说明原因"}}

query 在 action=skip 时可以为空。不要解题，不要输出 Markdown。""",
                    },
                ]
            )
            data = parse_json_object(response)
            action = str(data.get("action", "")).strip().lower()
            if action not in {"retrieve", "skip"}:
                raise ValueError("invalid memory route action")
            query = str(data.get("query", "")).strip()
            reason = str(data.get("reason", "")).strip()
            return MemoryRoute(action, query or task, reason or "模型未提供原因")
        except Exception:
            # Retrieval is advisory. On a routing failure, retain the old
            # behavior and retrieve instead of silently losing useful memory.
            return MemoryRoute(
                action="retrieve",
                query=task,
                reason="记忆路由不可用，使用兼容性回退策略",
                fallback=True,
            )

    def rewrite(self, task: str, previous_query: str, reason: str) -> str:
        try:
            response = self.model.query_text(
                [
                    {
                        "role": "system",
                        "content": "你负责改写编程经验检索查询。只返回 JSON，不要解题。",
                    },
                    {
                        "role": "user",
                        "content": f"""原始问题：
{task[:10000]}

上一次检索查询：
{previous_query[:4000]}

结果不足的原因：
{reason[:2000]}

返回一个更具体、能召回可复用算法或调试经验的查询：
{{"query":"..."}}""",
                    },
                ]
            )
            data = parse_json_object(response)
            query = data.get("query")
            if isinstance(query, str) and query.strip():
                return query.strip()
        except Exception:
            pass
        return ""


class MemoryRelevanceGrader:
    """Ask an LLM whether selected memories are applicable, not merely similar."""

    def __init__(self, model: TextModel):
        self.model = model

    def grade(self, task: str, memories: list[RetrievedMemory]) -> MemoryRelevance:
        if not memories:
            return MemoryRelevance(False, "没有召回可供判断的历史经验", score=0.0)

        compact: list[dict[str, Any]] = [
            {
                "experience_type": item.node.experience_type,
                "category": item.node.category,
                "trigger": item.node.trigger,
                "content": item.node.content,
                "steps": item.node.steps,
                "failure": item.node.failure,
                "fix": item.node.fix,
                "verification": item.node.verification,
                "similarity": round(item.similarity, 3),
                "quality_score": item.node.quality_score,
            }
            for item in memories[:8]
        ]
        try:
            response = self.model.query_text(
                [
                    {
                        "role": "system",
                        "content": "你是编程 Agent 的历史经验相关性评估器。只返回 JSON。",
                    },
                    {
                        "role": "user",
                        "content": f"""当前问题：
{task[:12000]}

召回经验：
{compact}

至少一条经验只有同时满足以下条件才算 relevant：
1. 问题类型或约束相同或高度相近；
2. 经验中的方法可以用于当前问题；
3. 经验包含可执行的策略或修复动作。

严格返回：
{{"relevant":true|false,"score":0.0,"reason":"简短原因"}}""",
                    },
                ]
            )
            data = parse_json_object(response)
            value = data.get("relevant", data.get("binary_score"))
            if isinstance(value, str):
                value = value.strip().lower() in {"true", "yes", "是", "1"}
            if not isinstance(value, bool):
                raise ValueError("invalid relevance value")
            score = data.get("score")
            try:
                parsed_score = float(score) if score is not None else None
            except (TypeError, ValueError):
                parsed_score = None
            return MemoryRelevance(
                relevant=value,
                reason=str(data.get("reason", "模型未提供原因")).strip() or "模型未提供原因",
                score=parsed_score,
            )
        except Exception:
            # A grader outage must not remove already-recalled advisory context.
            return MemoryRelevance(
                relevant=True,
                reason="相关性评估不可用，保留已召回经验",
                score=max(item.similarity for item in memories),
                fallback=True,
            )
