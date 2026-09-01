"""Seed the coding agent memory with reusable LeetCode Hot 100 guidance.

The seed is deliberately separate from trajectory learning.  It reads the
canonical question JSON files, creates one reusable strategy per question,
and creates a second set of common recovery patterns.  Re-running the script
replaces only rows whose ``source_run_id`` starts with ``seed:leetcode100:``.

Curated success guidance and the requested initial failure patterns are trusted
as reference material.  The failure seeds are marked verified by default so
they can participate in recovery retrieval immediately; ``--unverified-failures``
is available when strict Memory V3 episode evidence is required.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS_DIR = PROJECT_ROOT.parents[2] / "机试" / "力扣100" / "questions"
DATABASE_PATH = PROJECT_ROOT / "memory_store" / "memory.sqlite3"
SEED_PREFIX = "seed:leetcode100:"
LOCAL_DIMENSIONS = 256

# ``src`` is not installed when this file is invoked directly from a checkout.
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from code_agent.memory.embedding import (  # noqa: E402
    EMBEDDING_MODEL_NAME,
    SiliconFlowEmbeddingClient,
    SiliconFlowEmbeddingConfig,
)
from code_agent.memory.schemas import MemoryNode  # noqa: E402
from code_agent.memory.store import MemoryStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions-dir",
        type=Path,
        default=DEFAULT_QUESTIONS_DIR,
        help="Directory containing the 100 *-question.json files.",
    )
    parser.add_argument("--success-count", type=int, default=81)
    parser.add_argument("--failure-count", type=int, default=32)
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Do not call the embedding API; use deterministic local vectors.",
    )
    failure_group = parser.add_mutually_exclusive_group()
    failure_group.add_argument(
        "--verify-failures",
        dest="verify_failures",
        action="store_true",
        default=True,
        help="Trust seeded failure patterns (the default).",
    )
    failure_group.add_argument(
        "--unverified-failures",
        dest="verify_failures",
        action="store_false",
        help="Keep seeded failure patterns out of verified-only recovery retrieval.",
    )
    return parser.parse_args()


def load_questions(directory: Path) -> list[dict[str, Any]]:
    paths = sorted(directory.glob("*-question.json"), key=_rank_from_path)
    if not paths:
        raise FileNotFoundError(f"No *-question.json files found in {directory}")
    questions: list[dict[str, Any]] = []
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            continue
        value["_path"] = str(path)
        questions.append(value)
    return questions


def _rank_from_path(path: Path) -> int:
    match = re.match(r"(\d+)-", path.name)
    return int(match.group(1)) if match else 10**9


def question_title(question: dict[str, Any]) -> str:
    return str(question.get("translated_title") or question.get("title") or "未命名题目").strip()


def question_tags(question: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for item in question.get("topic_tags", []):
        if not isinstance(item, dict):
            continue
        tag = str(item.get("translated_name") or item.get("name") or "").strip()
        if tag and tag != "None" and tag not in tags:
            tags.append(tag)
    return tags


def question_text(question: dict[str, Any]) -> str:
    raw = str(question.get("translated_content") or question.get("content") or "")
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1800]


def primary_recipe(tags: list[str], group: str) -> tuple[str, list[str], str]:
    joined = " ".join(tags)
    if "滑动窗口" in joined:
        return (
            "维护窗口不变量，用右端扩张、左端收缩；只有窗口满足题目条件时更新答案。",
            ["明确窗口何时有效", "移动右指针并增量更新计数", "按不变量收缩左指针", "在正确时机记录最优值"],
            "窗口边界和计数更新必须保持同步，避免遗漏重复字符或多算元素。",
        )
    if "动态规划" in joined or "记忆化" in joined:
        return (
            "先定义状态的确切含义和转移，再确定初始化、遍历顺序及滚动数组是否安全。",
            ["写出状态定义", "从最小子问题推导转移", "覆盖边界状态并初始化", "按依赖顺序迭代或记忆化搜索"],
            "只凭样例猜转移，或把可重复使用的状态误写成一次性选择。",
        )
    if "二分查找" in joined:
        return (
            "把搜索空间和判定条件写成闭区间不变量，统一使用一种开闭区间并验证终止条件。",
            ["定义答案所在区间", "选择单调判定条件", "计算中点并排除一半", "单独检查空区间和边界返回值"],
            "混用 [left,right] 与 [left,right) 导致死循环、越界或漏掉首尾元素。",
        )
    if "回溯" in joined:
        return (
            "用路径状态进行深度优先搜索，在递归返回前撤销选择；通过剪枝减少不可能分支。",
            ["确定选择列表和终止条件", "做选择后递归", "必要时按排序或约束剪枝", "返回前撤销状态"],
            "忘记撤销路径、重复元素去重位置错误，造成答案串联或重复。",
        )
    if "树" in joined or "二叉树" in joined:
        return (
            "递归函数只返回一个清晰的子树语义；需要全局最优时在回溯阶段更新答案。",
            ["明确空节点返回值", "先处理左右子树", "根据题意合并子树结果", "用极端树形验证单节点和偏斜树"],
            "把节点数量、边数量和深度混为一谈，或在空节点上直接访问属性。",
        )
    if "链表" in joined:
        return (
            "先画出指针变化，再用哨兵节点或快慢指针统一处理头节点、尾节点和空链表。",
            ["明确每个指针的前后关系", "需要删除或插入时优先使用哨兵", "操作前保存后继指针", "检查空链表和单节点"],
            "修改 next 前没有保存后继，导致链表断裂或形成意外环。",
        )
    if "贪心" in joined:
        return (
            "先说明局部选择为何不会损害最优性，再按能维护的边界或剩余资源贪心推进。",
            ["找出可维护的最优边界", "证明局部选择的交换或支配关系", "线性扫描更新边界", "验证无法推进和最后一个元素"],
            "只因样例有效就采用贪心，没有确认选择具有单调性或交换性质。",
        )
    if "栈" in joined or "单调栈" in joined:
        return (
            "让栈始终保持题目要求的单调关系，在元素破坏关系时集中结算被弹出的元素。",
            ["确定栈内元素代表的未解决状态", "维护单调性", "弹出时计算贡献和边界", "补充哨兵处理栈内剩余元素"],
            "弹栈时使用错误的左右边界，或忘记清算最后一批元素。",
        )
    if "图" in joined or "拓扑排序" in joined or "并查集" in joined:
        return (
            "先选择与图性质匹配的表示和遍历：连通性用 DFS/BFS/并查集，依赖关系用拓扑排序。",
            ["明确节点和边的方向", "初始化访问或入度状态", "遍历所有连通分量", "对环、重复边和孤立点做检查"],
            "只从一个起点遍历，或把有向边当成无向边，导致漏解或错误判环。",
        )
    if "哈希" in joined or "哈希表" in joined:
        return (
            "用哈希表记录已经扫描的信息，把查找或计数从重复遍历降到均摊 O(1)。",
            ["确定键对应的状态", "扫描时先查询再更新（或按题意反过来）", "处理重复键和首次出现", "检查返回下标或计数的约定"],
            "更新哈希表的时机错误，把当前元素重复使用或覆盖了更早的有效状态。",
        )
    if "排序" in joined or "数组" in joined:
        return (
            "先排序或建立前缀/计数结构，再利用有序性减少枚举；明确是否允许修改输入数组。",
            ["分析排序后的单调关系", "选择双指针、前缀或分治边界", "跳过无效或重复状态", "用最小规模和重复值验证"],
            "忽略题目要求的下标、稳定性或原数组不可修改约束。",
        )
    return (
        f"围绕{group or '题目'}的输入输出不变量设计线性或近线性算法，先验证边界再优化实现。",
        ["提取输入输出契约", "写出核心不变量", "实现最小正确版本", "用边界和极端数据复核"],
        "只覆盖示例输入，未验证空值、单元素、重复值和最大约束。",
    )


def make_success(question: dict[str, Any]) -> MemoryNode:
    title = question_title(question)
    tags = question_tags(question)
    group = str(question.get("group_name") or "算法题").strip()
    recipe, steps, pitfall = primary_recipe(tags, group)
    difficulty = str(question.get("difficulty") or "Medium").lower()
    priority = 1 if difficulty == "hard" else 2 if difficulty == "medium" else 3
    node = MemoryNode(
        id=stable_id("success", question),
        category="strategy",
        experience_type="success",
        trigger=f"解决《{title}》这类{group}问题，标签：{'、'.join(tags[:5]) or '通用算法'}。",
        content=recipe,
        purpose=f"在满足《{title}》约束的同时保持实现清晰，并优先达到题目要求的复杂度。",
        steps=steps,
        negative_example=pitfall,
        problem_family=[group, title],
        algorithm_tags=tags[:8],
        constraints=[f"题目难度：{question.get('difficulty', '未知')}", "以题目给出的边界和输入输出格式为准"],
        priority=priority,
        quality_score=0.86,
        source_run_id=f"{SEED_PREFIX}success:{int(question.get('rank', 0)):03d}",
        source_verified=True,
        source_task=f"LeetCode Hot 100 #{question.get('rank')}: {title}\n{question_text(question)}",
        evidence=["LeetCode Hot 100 题目标签与通用算法不变量整理"],
    )
    return with_embedding_text(node)


def failure_recipe(tags: list[str]) -> tuple[str, str, str, list[str]]:
    joined = " ".join(tags)
    if "链表" in joined:
        return (
            "指针操作后链表结构损坏，测试出现断链、环或头节点遗漏。",
            "使用哨兵节点，修改 next 前保存后继，并在每次操作后检查链表长度和终点。",
            "重新运行原失败用例及空链表、单节点、双节点用例；pytest 应全部通过。",
            ["定位失败输出中的链表结构", "保存后继指针", "用哨兵统一头部处理", "重新运行 pytest"],
        )
    if "树" in joined or "二叉树" in joined:
        return (
            "空节点或偏斜树触发递归基例错误，深度、路径或遍历结果不正确。",
            "先固定空节点返回值，再分别测试空树、单节点、全左链和全右链。",
            "补齐边界测试并重新执行 pytest，确认递归返回语义与题目定义一致。",
            ["读取失败树形", "修正空节点基例", "覆盖偏斜树", "重新运行 pytest"],
        )
    if "回溯" in joined:
        return (
            "递归分支之间共享了未撤销的路径或选择，结果出现串联或重复。",
            "把撤销操作放在递归调用之后，并在同一层按题意去重；不要修改测试期望。",
            "用空输入、重复元素和最小规模输入复跑 pytest，确认每条路径独立。",
            ["比较失败结果与期望", "补充撤销状态", "调整同层去重", "重新运行 pytest"],
        )
    if "二分查找" in joined:
        return (
            "二分循环在首尾边界上漏掉答案或无法终止，导致错误下标或超时。",
            "统一采用闭区间或左闭右开区间，写出循环不变量并验证中点更新必然缩小区间。",
            "增加空数组、单元素、首尾命中和不存在目标用例后重新运行 pytest。",
            ["打印每轮区间", "统一区间约定", "修正中点更新", "重新运行 pytest"],
        )
    if "动态规划" in joined or "记忆化" in joined:
        return (
            "状态初始化或遍历顺序错误，边界输入返回默认值或重复使用了不允许的状态。",
            "重新写出状态含义、转移依赖和初始化，按依赖方向遍历并单独验证最小状态。",
            "补充最小、最大、全相等和无解输入，原失败 pytest 用例应通过。",
            ["定位错误状态", "核对转移依赖", "修正初始化", "重新运行 pytest"],
        )
    if "滑动窗口" in joined:
        return (
            "窗口收缩条件或计数更新不同步，导致有效窗口被跳过或答案包含无效元素。",
            "明确窗口有效条件，扩张和收缩时分别更新计数，并只在有效时记录答案。",
            "用重复字符、空串和目标不存在输入重新运行 pytest。",
            ["复现窗口边界", "修正计数时机", "覆盖空和重复输入", "重新运行 pytest"],
        )
    if "哈希" in joined or "哈希表" in joined:
        return (
            "哈希表先后更新顺序错误，当前元素被重复配对或前缀计数少算一次。",
            "根据题意决定先查询后写入还是先写入后查询，并用重复值和首元素用例验证。",
            "增加重复、负数、零和单元素输入后重新执行 pytest。",
            ["检查查询更新顺序", "修正计数", "覆盖重复和负数", "重新运行 pytest"],
        )
    if "栈" in joined or "单调栈" in joined:
        return (
            "栈内剩余元素没有结算，或弹出时使用了错误的左右边界。",
            "加入哨兵元素触发清算，明确每个栈元素的未解决区间并逐项验证宽度。",
            "用单调、全相等和末尾递减输入复跑 pytest。",
            ["检查栈剩余项", "加入哨兵", "修正边界宽度", "重新运行 pytest"],
        )
    return (
        "实现只覆盖了示例路径，边界输入或格式差异导致 pytest 输出不匹配。",
        "先按空输入、单元素、重复值、极值和多行空白建立边界清单，再修正解析或核心逻辑。",
        "保留失败用例，修改 solution.py 后重新运行同一 pytest 命令并确认通过。",
        ["读取完整失败输出", "列出边界假设", "修正解析或逻辑", "重新运行 pytest"],
    )


def make_failure(question: dict[str, Any], *, verified: bool) -> MemoryNode:
    title = question_title(question)
    tags = question_tags(question)
    group = str(question.get("group_name") or "算法题").strip()
    failure, fix, verification, steps = failure_recipe(tags)
    node = MemoryNode(
        id=stable_id("failure", question),
        category="recovery",
        experience_type="failure",
        trigger=f"《{title}》或相似{group}题在 pytest 反馈中出现边界/实现错误。",
        content=f"遇到该类失败时，先保留失败输出并定位不变量，再按恢复步骤修复；不要修改权威测试。{fix}",
        purpose=f"快速修复《{title}》类题目的常见错误，并用原失败用例证明修复没有回归。",
        steps=steps,
        negative_example="忽略 pytest 真实输出，直接重写测试用例或只针对示例打补丁。",
        problem_family=[group, title],
        algorithm_tags=tags[:8],
        constraints=(
            [
                "本批种子失败模式按用户确认作为已验证的初始恢复经验",
                "后续真实 pytest episode 可补充更具体的失败与修复证据",
            ]
            if verified
            else [
                "失败经验必须由真实 pytest 失败-修改-通过事件升级为已验证",
            ]
        ),
        priority=2,
        quality_score=0.48,
        source_run_id=f"{SEED_PREFIX}failure:{int(question.get('rank', 0)):03d}",
        source_verified=verified,
        source_task=f"LeetCode Hot 100 #{question.get('rank')}: {title}\n{question_text(question)}",
        evidence=(
            ["初始失败模式种子；尚无真实 pytest episode 证据"]
            if not verified
            else ["用户确认作为已验证的初始恢复经验"]
        ),
        failure=failure,
        fix=fix,
        verification=verification,
    )
    return with_embedding_text(node)


def stable_id(kind: str, question: dict[str, Any]) -> str:
    key = f"leetcode100:{kind}:{question.get('rank')}:{question.get('question_id')}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def with_embedding_text(node: MemoryNode) -> MemoryNode:
    node.embedding_text = node.build_embedding_text()
    return node


def local_embedding(text: str) -> list[float]:
    """Create a stable lexical vector for offline bootstrap/reproducibility."""
    values = [0.0] * LOCAL_DIMENSIONS
    normalized = re.sub(r"\s+", " ", text.casefold()).strip()
    features = normalized.split(" ")
    features.extend(normalized[index : index + 2] for index in range(max(0, len(normalized) - 1)))
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % LOCAL_DIMENSIONS
        sign = 1.0 if digest[4] & 1 else -1.0
        values[index] += sign
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def remote_embeddings(nodes: list[MemoryNode]) -> tuple[list[list[float]], list[list[float]], str]:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    api_key = os.getenv("SILICONFLOW_EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("SILICONFLOW_EMBEDDING_API_KEY/OPENAI_API_KEY is not configured")
    client = SiliconFlowEmbeddingClient(
        SiliconFlowEmbeddingConfig(
            api_key=api_key,
            model=EMBEDDING_MODEL_NAME,
            api_base=os.getenv("OPENAI_API_BASE") or "https://api.siliconflow.cn/v1",
            timeout=30,
            max_retries=2,
        )
    )
    vectors: list[list[float]] = []
    task_vectors: list[list[float]] = []
    texts = [node.embedding_text for node in nodes]
    task_texts = [node.source_task for node in nodes]
    for start in range(0, len(texts), 32):
        vectors.extend(client.embed(texts[start : start + 32]))
        task_vectors.extend(client.embed(task_texts[start : start + 32]))
    return vectors, task_vectors, EMBEDDING_MODEL_NAME


def replace_seed_rows(database_path: Path, nodes: Iterable[MemoryNode]) -> None:
    store = MemoryStore(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM memories WHERE source_run_id LIKE ?", (SEED_PREFIX + "%",))
        connection.commit()
    for node in nodes:
        store.add(node)


def main() -> None:
    args = parse_args()
    if args.success_count < 0 or args.failure_count < 0:
        raise SystemExit("success/failure counts must be non-negative")
    questions = load_questions(args.questions_dir)
    if args.success_count > len(questions):
        raise SystemExit(
            f"success-count={args.success_count} exceeds the {len(questions)} available questions"
        )
    if args.failure_count and not questions:
        raise SystemExit("failure memories require at least one question")
    success_questions = questions[: args.success_count]
    failure_questions = [questions[index % len(questions)] for index in range(args.failure_count)]
    nodes = [make_success(question) for question in success_questions]
    nodes.extend(make_failure(question, verified=args.verify_failures) for question in failure_questions)

    embedding_model = "local-hash-256"
    task_vectors: list[list[float]]
    if not args.local_only:
        try:
            vectors, task_vectors, embedding_model = remote_embeddings(nodes)
        except Exception as error:
            print(f"Embedding API unavailable ({error}); using local deterministic vectors.", file=sys.stderr)
            vectors = [local_embedding(node.embedding_text) for node in nodes]
            task_vectors = [local_embedding(node.source_task) for node in nodes]
    else:
        vectors = [local_embedding(node.embedding_text) for node in nodes]
        task_vectors = [local_embedding(node.source_task) for node in nodes]
    if len(vectors) != len(nodes):
        raise RuntimeError("embedding count does not match generated memory count")
    if len(task_vectors) != len(nodes):
        raise RuntimeError("source-task embedding count does not match generated memory count")
    for node, vector, task_vector in zip(nodes, vectors, task_vectors, strict=True):
        node.embedding = vector
        node.embedding_model = embedding_model
        # Source-task vectors use the same embedding model and dimensionality,
        # so weighted task retrieval works immediately for seed rows.
        node.source_task_embedding = task_vector

    replace_seed_rows(DATABASE_PATH, nodes)
    success_count = sum(node.experience_type == "success" for node in nodes)
    failure_count = sum(node.experience_type == "failure" for node in nodes)
    verified_count = sum(node.source_verified for node in nodes)
    print(
        f"Seeded {len(nodes)} memories into {DATABASE_PATH}: "
        f"success={success_count}, failure={failure_count}, verified={verified_count}, "
        f"embedding={embedding_model}"
    )


if __name__ == "__main__":
    main()
