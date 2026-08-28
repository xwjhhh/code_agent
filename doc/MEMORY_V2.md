# V2 持久化经验记忆

## 目标

V1 只在一次运行内通过 `模型 -> Bash -> pytest -> 修复` 学习。V2 增加第二个闭环：

```text
已验证运行 -> Experience Extractor -> Memory Node -> Embedding -> SQLite
新任务 -> Query Analyzer -> Embedding Retrieval -> Reranker -> Agent 上下文
pytest 失败 -> Recovery Retrieval -> Agent 上下文
```

这里的 Memory 不是历史题目或完整旧轨迹，而是从成功运行中提炼出的、带适用条件和动作的经验。第一阶段只写入本地测试验证成功的运行，避免把未经验证的错误方案传播到后续任务。

## Memory Node

每条记忆包含：

- `category`: `strategy`、`recovery` 或 `optimization`；
- `granularity`: `task` 或 `subtask`；
- `trigger`: 什么时候适用；
- `content`: 可复用的知识；
- `steps`: 模型可以执行的动作；
- `negative_example`: 应避免的模式；
- 问题类型、算法标签、约束、优先级和质量分数；
- `source_run_id`、`source_verified` 等来源信息；
- `embedding_text`、Embedding 模型和向量。

Embedding 是检索索引，不是记忆正文。正文和 metadata 在 SQLite 中独立保存，向量用于本地余弦相似度召回。

## Embedding API

实现位于 `src/code_agent/memory/embedding.py`，直接调用硅基流动 OpenAI 兼容接口：

```text
POST https://api.siliconflow.cn/v1/embeddings
Authorization: Bearer <key>
```

项目固定使用 `Qwen/Qwen3-Embedding-8B`。它支持最长 32768 token，且可以返回 64 到 4096 维向量；当前请求不指定 `dimensions`，由服务返回默认维度。请求使用文档规定的 `model`、`input` 和 `encoding_format: float` 字段。批量文本会在一次请求中发送，返回向量按 `index` 排序。Embedding Key 优先读取 `SILICONFLOW_EMBEDDING_API_KEY`，缺失时回退到 `OPENAI_API_KEY`。`GLM-5.2` 是对话模型，不能作为 Embeddings 模型发送。

## 读取路径

`QueryAnalyzer` 将题目改写成一个 task query 和最多三个 subtask query，并提取问题类型、算法标签。每个 query 分别向量化，按粒度和类别过滤后进行候选合并。向量只负责 Candidate Recall；候选超过上限时交给 `MemoryReranker` 让模型按适用性、具体性、质量、重复和冲突筛选。最终最多注入 4 条经验，而且固定声明经验只是参考，当前题目和权威测试优先。

pytest 失败时，查询内容会增加当前题目、失败输出和最近动作，并只召回 `recovery` 记忆。这是 Coding Agent 特有的第二次检索时机。

## 写入路径

Reviewer 完成后，`ExperienceExtractor` 读取题目、trajectory、最终代码、pytest 输出和评审意见，要求模型输出结构化 JSON。提炼时去掉样例值、变量名、文件行号和原始叙述，只保留“什么时候适用、为什么、下一步怎么做”。每个候选 Memory Node 先生成完整 embedding template，再调用硅基流动 Embeddings API。相同类别和粒度下余弦相似度达到 `0.96` 的记录视为重复，不重复写入。

## 代码入口

- `memory/schemas.py`: MemoryNode、MemoryQuery、RetrievedMemory；
- `memory/embedding.py`: 硅基流动 Embeddings HTTP 客户端；
- `memory/store.py`: SQLite CRUD 与余弦召回；
- `memory/query_analyzer.py`: 任务多粒度查询；
- `memory/extractor.py`: 已验证轨迹到可复用经验；
- `memory/reranker.py`: 候选二阶段筛选；
- `memory/formatter.py`: 经验上下文格式化；
- `memory/manager.py`: 统筹任务检索、失败检索和学习；
- `memory/factory.py`: 从 YAML 和环境变量构建服务。

运行数据存放在 `memory_store/memory.sqlite3`，该目录已加入 Git 忽略，不会把本地记忆或凭据提交到仓库。
