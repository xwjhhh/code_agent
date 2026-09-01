"""Format selected memories as advisory context for the coding model."""

from __future__ import annotations

from code_agent.memory.schemas import RetrievedMemory


def format_memory_context(memories: list[RetrievedMemory]) -> str:
    if not memories:
        return ""
    sections = [
        "Relevant past experience is advisory reference material.",
        "Use it only when it applies. Do not copy old solutions. The current problem statement, repository state, and authoritative tests always take precedence.",
        "",
        "Relevant Past Experience:",
    ]
    for item in memories:
        node = item.node
        title = f"[{node.experience_type.upper()}]"
        sections.extend(
            [
                title,
                f"When applicable: {node.trigger}",
                f"Guidance: {node.content}",
            ]
        )
        if node.steps:
            sections.append("Actions: " + " -> ".join(node.steps))
        if node.negative_example:
            sections.append("Avoid: " + node.negative_example)
        if node.failure:
            sections.append("Observed failure: " + node.failure)
        if node.fix:
            sections.append("Repair: " + node.fix)
        if node.verification:
            sections.append("Verification: " + node.verification)
        if node.evidence:
            sections.append("Evidence: " + " | ".join(node.evidence[:4]))
        sections.append("")
    return "\n".join(sections).strip()
