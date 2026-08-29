# 算法题编程智能体：架构说明

## 1. 总体数据流

```text
用户输入题目
    |
    +-- 人工填写输入/输出 ----------+
    |                               |
    +-- DeepSeek-V4-Flash 生成输入/输出 -------+
                                    v
                             test_cases.json
                                    |
                          任务记忆检索（可选）
                                    |
                   +----------------+----------------+
                   |                                 |
                   v                                 v
          编程模型读取该文件                test_solution.py 读取该文件
                   |                                 |
                   v                                 v
             编写 solution.py                 执行 pytest
                   |                                 |
                   +---------- 测试结果 --------------+
                                    |
                         失败：反馈给 Agent 继续
                         通过：允许提交并进入 Reviewer
                                    |
                                    v
                              Reviewer 完成
                                    |
                         提炼、向量化并持久化经验
                                    |
                                    v
                               FinalResult
```

编程循环的核心消息闭环是：

```text
Messages -> Model -> Bash Action -> LocalEnvironment -> Observation -> Messages
```

测试用例在编程循环之前准备。`test_cases.json` 是编程模型、pytest 和 Reviewer 共用的权威输入输出文件；Agent 不能通过修改测试答案来规避失败。Memory 是辅助上下文，当前题目和权威测试始终优先。

## 2. 每次运行的文件

```text
workspace/<run_id>/
├── test_cases.json
├── test_solution.py
└── solution.py
```

`test_cases.json` 的结构示例：

```json
{
  "version": 1,
  "source": "manual",
  "problem": "题目文本",
  "cases": [
    {
      "name": "题目样例",
      "input": "ab4f35gr#a6",
      "expected_output": "abfgr#a4356",
      "source": "manual"
    }
  ]
}
```

`input` 和 `expected_output` 都是完整文本，可以包含多行。题解模型必须在 `solution.py` 中提供：

```python
def solve(input_text: str) -> str:
    ...
```

`test_solution.py` 由系统固定生成，读取 JSON 后逐个调用 `solve()` 比较输出。两个测试文件在 Agent 运行期间受保护，模型修改后会被 Environment 恢复并将命令标记为失败。

## 3. 后端目录和职责

```text
src/code_agent/
├── __init__.py
├── api.py
├── exceptions.py
├── test_cases.py
├── reviewer.py
├── storage.py
├── agents/
│   └── default.py
├── models/
│   ├── __init__.py
│   ├── litellm_model.py
│   └── utils/actions.py
├── environments/
│   └── local.py
├── memory/
│   ├── __init__.py
│   ├── schemas.py
│   ├── embedding.py
│   ├── store.py
│   ├── query_analyzer.py
│   ├── extractor.py
│   ├── reranker.py
│   ├── formatter.py
│   ├── consolidator.py
│   ├── manager.py
│   └── factory.py
├── run/
│   └── main.py
└── config/
    └── default.yaml
```

### `src/code_agent/__init__.py`

定义 Model、Environment、Agent 三类协议和项目版本，为其他模块提供稳定接口。

### `src/code_agent/api.py`

FastAPI 桥接层。接收浏览器提交的题目、模型、运行参数和测试用例，启动后台 Agent，并通过 SSE 返回真实执行事件。

- `POST /api/test-cases/generate`：调用 DeepSeek-V4-Flash 生成测试用例。
- `POST /api/runs`：创建工作区并启动 Agent。
- `GET /api/runs`：返回当前进程内的运行列表。
- `GET /api/runs/{id}`：返回任务、测试、结果、评审、Memory 状态和事件。
- `GET /api/runs/{id}/files`：返回三个工作区文件。
- `GET /api/runs/{id}/events`：以 SSE 实时发送事件。
- `GET /api/memories`：读取本地 SQLite 记忆库中的结构化经验。

### `src/code_agent/test_cases.py`

统一测试数据层。输入是人工用例或测试生成模型的 JSON，输出是规范化用例、权威 `test_cases.json` 和固定 `test_solution.py`。它负责字段校验、JSON 解析、文件生成以及给编程模型的测试文件说明。

### `src/code_agent/models/litellm_model.py`

模型适配层。输入是 messages，输出是标准 assistant message 和解析后的 Bash action。项目固定使用硅基流动 `openai/deepseek-ai/DeepSeek-V4-Flash`；LiteLLM 只负责 API 调用，不负责 Agent 循环、工具执行或完成判断。`query()` 使用原生 tool calling，`query_text()` 用于测试生成、Reviewer 和 Memory 文本任务。

### `src/code_agent/models/utils/actions.py`

定义唯一的 Bash 工具，解析模型的 `tool_calls`，并把 Environment 结果转换成带相同 `tool_call_id` 的 tool observation。

### `src/code_agent/environments/local.py`

本地执行器。输入是 Bash action，输出统一包含 `output`、`returncode` 和 `exception_info`。Windows 下使用 Git Bash，处理超时和系统错误，并恢复被保护的测试文件。

### `src/code_agent/agents/default.py`

Agent 控制核心。它保存 messages、调用模型、执行 Bash、回传 observation、记录步骤和发送事件。只有精确执行 `python -m pytest -q` 并真实通过，且三个工作区文件存在时，才记录本地验证成功；之后模型发出精确提交命令，Agent 才结束并允许 Reviewer 运行。达到调用上限或出现模型错误时受控终止。

### `src/code_agent/reviewer.py`

只读代码评审器。输入是题目、题解、测试文件和 pytest 结果，输出算法正确性、复杂度、边界情况、测试充分性和可读性分析。只有本地验证成功后才调用，不执行命令也不修改文件。

### `src/code_agent/storage.py`

运行持久化模块，将 Agent 序列化数据和 Reviewer 结果保存为 `trajectory.json` 与 `review.json`。

### `src/code_agent/memory/`

持久化经验记忆子系统。它不保存完整旧对话，而是从本地验证成功且 Reviewer 完成的运行中提炼 Strategy、Recovery、Optimization 经验。

- `schemas.py`：定义 `MemoryNode`、`MemoryQuery`、`RetrievedMemory`。
- `embedding.py`：调用硅基流动 `/v1/embeddings`，固定使用 `Qwen/Qwen3-Embedding-8B`。
- `store.py`：负责 SQLite 建表、增删查和本地余弦相似度搜索。
- `query_analyzer.py`：把新题目改写为 task/subtask 检索查询，并提取题型和算法标签。
- `extractor.py`：从已验证运行的题目、轨迹、题解、pytest 输出和 Reviewer 结果中提炼结构化经验。
- `reranker.py`：使用 DeepSeek-V4-Flash 从向量召回候选中筛选少量高价值经验。
- `formatter.py`：将选中的经验格式化为注入编程模型上下文的参考文本。
- `consolidator.py`：按向量相似度抑制近重复经验。
- `manager.py`：统筹任务检索、pytest 失败后的 Recovery 检索、经验学习和事件通知。
- `factory.py`：读取 YAML 和环境变量，构建记忆服务和 Embedding 客户端。

写入记忆时，经验正文和 metadata 保存在 SQLite，Embedding 仅用于检索索引。新任务开始时进行 task/subtask 召回；pytest 失败时追加失败输出和最近动作进行 Recovery 召回；Reviewer 完成后才提炼并写入新经验。

### `src/code_agent/run/main.py`

命令行入口。读取题目和参数，生成权威测试，启动与 Web 相同的 Agent、Reviewer 和 Memory 流程，并输出运行产物路径。

### `src/code_agent/config/default.yaml`

保存 Agent 系统提示词、任务模板、调用上限、环境超时、DeepSeek-V4-Flash 默认参数和 Memory 配置。提示词要求模型先读 `test_cases.json`，只修改 `solution.py` 并按固定命令测试。

### `src/code_agent/exceptions.py`

定义工具格式错误、步骤上限、模型调用错误和 Memory 服务错误等异常。

## 4. 前端目录和职责

```text
frontend/
├── app/
│   ├── page.tsx
│   ├── task/new/page.tsx
│   ├── run/[id]/page.tsx
│   ├── history/page.tsx
│   └── history/[id]/page.tsx
├── components/
│   ├── app-shell.tsx
│   ├── dashboard.tsx
│   ├── run-history.tsx
│   ├── new-task-form.tsx
│   ├── run-workspace.tsx
│   ├── run-detail.tsx
│   ├── problem-panel.tsx
│   ├── code-editor.tsx
│   ├── terminal-panel.tsx
│   ├── test-panel.tsx
│   ├── trace-timeline.tsx
│   ├── memory-graph.tsx
│   ├── reviewer-card.tsx
│   └── status-badge.tsx
└── lib/
    ├── api.ts
    ├── trace.ts
    └── data.ts
```

`dashboard.tsx` 展示真实运行列表和后端连接；`new-task-form.tsx` 收集题目、人工用例或 AI 生成用例；`run-workspace.tsx` 订阅 SSE 并刷新文件、终端、测试、轨迹和评审；`run-detail.tsx` 展示历史运行结果。

`problem-panel.tsx` 展示题目和用例；`code-editor.tsx` 只读展示代码；`terminal-panel.tsx` 展示真实 Bash 输出；`test-panel.tsx` 展示输入输出用例和 pytest 状态；`trace-timeline.tsx` 将 SSE 事件转换为可展开时间线；`reviewer-card.tsx` 展示 Reviewer 文本；`app-shell.tsx` 提供导航和 FastAPI 健康状态。

当前运行页右侧默认展示 Memory Graph，Trace 作为可切换的次级视图；后端已经提供 `/api/memories` 查询接口，但尚未提供独立的全局记忆库页面。

`memory-graph.tsx` 只使用四种视觉规则：Task-level 为大节点、Subtask-level 为小节点、Strategy/Recovery/Optimization 使用不同图标、关系使用实线或虚线。点击节点后才显示相似度、来源和完整行动步骤等详情。

`lib/api.ts` 封装 FastAPI 请求、运行/Memory 类型和 SSE URL；`lib/trace.ts` 将事件转换为时间线和终端行；`lib/data.ts` 保存前端共享类型。

## 5. SSE 事件

```text
test_cases_ready
memory_retrieval_started
memory_retrieval_finished
memory_context_injected
agent_started
model_thinking
model_response
command_started
command_finished
file_changed
test_started
test_failed / test_passed
memory_learning_started
memory_learning_finished
agent_submitted
agent_finished
review_started
review_finished
run_finished
```

异常时发送 `memory_error`、`model_error` 或 `run_error`。每个事件有递增 ID；SSE 通过 `Last-Event-ID` 支持断线重连，前端按 ID 去重，并在收到 `run_finished` 后关闭连接。

## 6. 完成条件

只有同时满足以下条件，才算本地验证成功：

1. `solution.py`、`test_cases.json`、`test_solution.py` 都存在；
2. 模型执行的命令恰好是 `python -m pytest -q`；
3. 命令返回码为 0，输出包含实际通过数量；
4. 测试通过后没有继续修改题解；
5. 模型发出精确的完成提交命令。

满足后 Agent 停止循环并启动 Reviewer；Reviewer 完成后才允许 Memory 学习阶段提炼经验。

## 7. 运行产物

```text
workspace/<run_id>/
├── solution.py
├── test_cases.json
└── test_solution.py

trajectories/<run_id>/
├── trajectory.json
└── review.json

memory_store/
└── memory.sqlite3
```

`memory_store/`、`workspace/` 和 `trajectories/` 中的本地运行数据已被 Git 忽略；公开仓库只包含代码、配置示例和文档，不包含 API Key 或个人运行数据。
