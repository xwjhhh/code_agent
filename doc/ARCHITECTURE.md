# 算法题编程智能体：架构说明

## 1. 总体闭环

```text
用户输入题目
    |
    +-- 人工填写输入/输出 ----------+
    |                               |
    +-- 测试生成模型生成输入/输出 ---+
                                    v
                             test_cases.json
                                    |
                   +----------------+----------------+
                   |                                 |
                   v                                 v
          编程模型先读取该文件              test_solution.py 读取该文件
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
                               FinalResult
```

运行中的核心循环是：

```text
Messages -> Model -> Bash Action -> LocalEnvironment -> Observation -> Messages
```

测试用例准备发生在编程循环之前。Agent 不负责随意改测试答案，只负责基于已经确定的输入输出编写并修正题解。

## 2. 核心文件约定

每次运行拥有独立的 `workspace/<run_id>/`：

```text
workspace/<run_id>/
├── test_cases.json
├── test_solution.py
└── solution.py
```

`test_cases.json` 是唯一权威测试数据，结构如下：

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

`input` 与 `expected_output` 都是完整文本，可以包含多行。编程模型必须提供统一接口：

```python
def solve(input_text: str) -> str:
    ...
```

`test_solution.py` 由系统固定生成。它读取 JSON，对每个用例调用 `solve()` 并比较输出。`test_cases.json` 和 `test_solution.py` 在 Agent 运行期间受保护，模型若修改它们，Environment 会恢复原内容并将本次命令标记为失败。

## 3. 后端目录与职责

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
│   ├── litellm_model.py
│   ├── demo_model.py
│   └── utils/actions.py
├── environments/
│   └── local.py
├── run/
│   └── main.py
└── config/
    └── default.yaml
```

### `src/code_agent/__init__.py`

定义 Model、Environment、Agent 三类协议和项目版本。输入是实现类的方法签名，输出是其他模块可以依赖的稳定接口。

### `src/code_agent/api.py`

FastAPI 前后端桥接层。输入是浏览器提交的题目、模型、运行参数和测试用例；输出是运行 ID、运行状态、工作区文件以及 SSE 事件。

它负责：

- `POST /api/test-cases/generate`：调用所选模型生成测试用例；
- `POST /api/runs`：创建后台线程并启动 Agent；
- `GET /api/runs`：返回当前后端进程内的运行列表；
- `GET /api/runs/{id}`：返回任务、用例、结果、评审和事件；
- `GET /api/runs/{id}/files`：返回三个工作区文件；
- `GET /api/runs/{id}/events`：通过 SSE 实时发送运行事件。

### `src/code_agent/test_cases.py`

统一测试数据层。输入是人工用例或测试生成模型的 JSON 文本；输出是规范化用例、`test_cases.json` 和固定 `test_solution.py`。

它负责：

- 统一用例字段和名称；
- 构造测试生成提示词并解析 JSON；
- 保存权威测试文件；
- 生成编程模型必须遵守的测试文件说明。

### `src/code_agent/models/litellm_model.py`

模型调用适配层。输入是 Agent 的 messages；输出是标准 assistant message 和解析后的 Bash actions。LiteLLM 只负责把请求发送到不同模型厂商，本项目自己的 Agent 循环、工具执行、完成判断都不在 LiteLLM 中。

`query()` 使用模型原生 tool calling；`query_text()` 用于测试生成和 Reviewer 的纯文本调用。

### `src/code_agent/models/demo_model.py`

无需 API Key 的确定性演示模型。输入仍是正常 Agent messages，输出仍是标准 Bash tool call，因此会真实经过 Agent、Git Bash、文件写入和 pytest，而不是前端假数据。

### `src/code_agent/models/utils/actions.py`

定义唯一的 Bash 工具并解析模型工具调用。输入是模型原生 `tool_calls`；输出为：

```python
{"command": "python -m pytest -q", "tool_call_id": "call_123"}
```

它还把 Environment 的执行结果转换成带相同 `tool_call_id` 的 tool observation，供下一轮模型读取。

### `src/code_agent/environments/local.py`

本地命令执行器。输入是 Bash action；输出统一包含 `output`、`returncode` 和 `exception_info`。

它使用 Windows Git Bash 执行命令、处理超时和系统错误，并在每次命令后检查受保护测试文件是否被修改。

### `src/code_agent/agents/default.py`

整个系统的控制核心。输入是题目、模型、Environment 和提示词；输出是最终状态、验证结果、文件路径、消息历史和步骤记录。

它负责：

- 保存 messages 和模型调用次数；
- 调用 Model 并执行 Bash action；
- 将 observation 加回 messages；
- 只认固定命令 `python -m pytest -q` 的真实成功结果；
- 测试通过后才接受提交命令；
- 发出前端需要的运行事件；
- 达到步骤上限或模型错误时终止。

### `src/code_agent/reviewer.py`

只读评审器。输入是原题、`solution.py`、固定测试脚本、`test_cases.json` 和 pytest 输出；输出是中文算法评审。它只在本地验证通过后运行，不执行命令也不改文件。

### `src/code_agent/storage.py`

运行持久化模块。输入是 Agent 的序列化数据和 Reviewer 结果；输出是 `trajectory.json` 与 `review.json`。

### `src/code_agent/run/main.py`

命令行入口。输入是命令行题目、模型名、Git Bash 路径等参数；输出是终端结果和运行产物。CLI 会先让模型生成权威测试文件，再启动与 Web 相同的 Agent 闭环。

### `src/code_agent/config/default.yaml`

保存 Agent 系统提示词、任务模板、步骤上限、环境超时和模型默认参数。提示词要求模型先读取 `test_cases.json`，只能修改题解并按固定命令运行测试。

### `src/code_agent/exceptions.py`

定义格式错误、步骤上限和模型调用错误等异常，用于把失败转成可控的 Agent 状态。

## 4. 前端目录与职责

```text
frontend/
├── app/
│   ├── page.tsx
│   ├── task/new/page.tsx
│   ├── run/[id]/page.tsx
│   ├── history/page.tsx
│   └── history/[id]/page.tsx
├── components/
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
│   └── reviewer-card.tsx
└── lib/
    ├── api.ts
    ├── trace.ts
    └── data.ts
```

### 页面组件

- `dashboard.tsx`：调用运行列表和健康检查接口，展示真实任务状态。
- `run-history.tsx`：展示全部运行记录，并链接到每条运行的详情页。
- `new-task-form.tsx`：收集题目、人工输入输出或 AI 生成用例，然后创建运行。
- `run-workspace.tsx`：读取初始状态并订阅 SSE，实时展示文件、终端、测试、轨迹和评审。
- `run-detail.tsx`：读取某次运行的最终文件、指标、测试结果和 Reviewer。

### 展示组件

- `problem-panel.tsx`：展示题目、模型和当前权威用例样例。
- `code-editor.tsx`：用只读 Monaco 展示 Python 或 JSON 文件。
- `terminal-panel.tsx`：用只读 xterm.js 展示真实 Bash 命令及输出。
- `test-panel.tsx`：展示真实用例来源、输入输出和 pytest 状态。
- `trace-timeline.tsx`：将 SSE 事件展示成可展开时间线。
- `reviewer-card.tsx`：展示真实 Reviewer 文本。
- `app-shell.tsx`：全局导航并调用健康检查显示后端连接状态。

### 数据模块

- `lib/api.ts`：封装 FastAPI 请求、响应类型和 SSE URL。
- `lib/trace.ts`：把后端事件转换为时间线和终端输出。
- `lib/data.ts`：只保留前端共享状态类型，不包含演示运行数据。

## 5. SSE 事件

后端会按真实执行顺序发出：

```text
test_cases_ready
agent_started
model_thinking
model_response
command_started
command_finished
file_changed
test_started
test_failed / test_passed
agent_submitted
agent_finished
review_started
review_finished
```

异常时发出 `model_error` 或 `run_error`。前端先获取已有事件数量，再用 cursor 订阅后续事件，避免重复显示。

## 6. 完成条件

只有同时满足以下条件才算本地验证成功：

1. `solution.py`、`test_cases.json`、`test_solution.py` 都存在；
2. 模型执行的命令恰好是 `python -m pytest -q`；
3. 命令返回码为 0，输出包含实际通过数量；
4. 测试通过后没有再修改题解；
5. 模型主动发出完成提交命令。

满足后 Agent 才停止循环并启动 Reviewer。

## 7. 运行产物

```text
workspace/<run_id>/
├── solution.py
├── test_cases.json
└── test_solution.py

trajectories/<run_id>/
├── trajectory.json
└── review.json
```

前端当前运行列表由 FastAPI 进程内状态提供；文件和轨迹会保存在磁盘中。
