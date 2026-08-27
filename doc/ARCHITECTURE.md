# 算法题编程智能体：第一版架构设计

## 1. 设计目标

第一版实现一个面向算法题的轻量级编程智能体。用户输入自然语言题目后，智能体调用大语言模型，让模型通过 Bash 工具在本地编写题解和测试、运行测试，并根据测试输出不断修改代码。测试通过后，系统再对最终代码进行一次独立评审并保存结果。

项目采用清晰的三层结构：

- Agent 负责控制循环和维护对话历史；
- Model 负责调用大语言模型并解析工具调用；
- Environment 负责在本地执行模型提出的命令。

第一版只实现一条清晰的主链路，不同时设计多套工具系统。

## 2. 总体流程

```text
用户输入题目
    |
    v
run/main.py
    |
    v
DefaultAgent.run(task)
    |
    v
LitellmModel.query(messages)
    |
    v
大模型返回 Bash tool call
    |
    v
actions.py 解析 command
    |
    v
LocalEnvironment.execute(action)
    |
    v
stdout / returncode / exception
    |
    v
转换成 observation message
    |
    +----------------------> 加入 messages，继续循环
                                |
                                v
                         本地 pytest 通过
                                |
                                v
                         模型提交完成请求
                                |
                                v
                            Reviewer
                                |
                                v
                         保存并展示最终结果
```

整个系统最重要的数据闭环是：

```text
Messages -> Model -> Action -> Environment -> Observation -> Messages
```

模型只负责决定下一步做什么，程序负责真实执行和判断本地测试是否成功。

## 3. 项目目录

```text
code_agent/
├── src/
│   └── code_agent/
│       ├── __init__.py
│       ├── exceptions.py
│       ├── agents/
│       │   ├── __init__.py
│       │   └── default.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── litellm_model.py
│       │   └── utils/
│       │       ├── __init__.py
│       │       └── actions.py
│       ├── environments/
│       │   ├── __init__.py
│       │   └── local.py
│       ├── reviewer.py
│       ├── storage.py
│       ├── run/
│       │   ├── __init__.py
│       │   └── main.py
│       └── config/
│           └── default.yaml
├── doc/
│   ├── REQUIREMENTS.md
│   └── ARCHITECTURE.md
├── tests/
│   ├── test_actions.py
│   ├── test_local_environment.py
│   └── test_agent.py
├── workspace/
├── trajectories/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

`workspace/` 存放智能体生成的题解和测试。`trajectories/` 存放每次运行的对话与结果。这两个目录中的运行产物不直接提交到 Git。

## 4. 核心数据约定

各层之间使用结构固定的字典传递数据，避免 Model、Agent 和 Environment 各自理解不同的数据格式。

### 4.1 Action

Model 从大模型响应中解析出的动作：

```python
{
    "command": "python -m pytest -q",
    "tool_call_id": "call_123"
}
```

### 4.2 Environment Output

Environment 执行命令后的统一结果：

```python
{
    "output": "8 passed in 0.05s",
    "returncode": 0,
    "exception_info": ""
}
```

命令失败或超时时仍返回相同结构，只是 `returncode` 非零，并在 `output` 或 `exception_info` 中描述错误。

### 4.3 Model Message

Model 返回给 Agent 的消息：

```python
{
    "role": "assistant",
    "content": "现在运行测试。",
    "tool_calls": [...],
    "extra": {
        "actions": [
            {
                "command": "python -m pytest -q",
                "tool_call_id": "call_123"
            }
        ]
    }
}
```

`extra` 是程序内部字段，下一轮请求模型前需要移除；`tool_calls` 是模型 API 所需的原始消息字段，必须保留在对话历史中。

### 4.4 Observation Message

命令结果反馈给模型时，需要和原工具调用 ID 对应：

```python
{
    "role": "tool",
    "tool_call_id": "call_123",
    "content": "returncode: 0\noutput:\n8 passed in 0.05s"
}
```

这条对应关系非常重要。缺少 `tool_call_id`，模型 API 会认为工具调用没有得到响应。

## 5. 各文件职责

### 5.1 `src/code_agent/__init__.py`

这是项目核心接口的定义位置。

它负责声明：

- Model 应提供 `query()` 和 observation 格式化能力；
- Environment 应提供 `execute()`；
- Agent 应提供 `run()` 和 `save()`。

输入：无业务输入。

输出：供其他模块引用的接口定义和版本信息。

它不调用模型、不执行命令，也不控制 Agent 循环。

### 5.2 `src/code_agent/exceptions.py`

这是流程中的特殊信号定义位置。

第一版包含：

- `FormatError`：模型没有返回合法的 Bash 工具调用；
- `Submitted`：模型请求提交最终结果；
- `LimitsExceeded`：达到最大模型调用次数；
- `ModelError`：模型请求无法完成。

输入：错误信息或需要加入历史的消息。

输出：由 Agent 捕获的异常对象。

这些异常用于明确结束或修正循环，不包含具体业务逻辑。

### 5.3 `src/code_agent/models/utils/actions.py`

这是 Bash 工具定义和动作解析位置。

它负责向模型声明唯一工具：

```text
bash(command: string)
```

还负责把模型返回的 tool call 解析成 Action，并检查：

- 工具名是否为 `bash`；
- 参数是否为合法 JSON；
- 是否存在 `command`；
- `command` 是否为字符串。

输入：模型响应中的 `tool_calls`。

输出：Action 列表，或抛出 `FormatError`。

它只负责定义和解析动作，不执行 Bash。

### 5.4 `src/code_agent/models/litellm_model.py`

这是模型适配层。

它负责：

1. 接收 Agent 的完整 `messages`；
2. 删除消息中的内部 `extra` 字段；
3. 通过 LiteLLM 调用指定大模型；
4. 向模型传递 `bash` 工具定义；
5. 调用 `actions.py` 解析 tool call；
6. 返回带有 `extra.actions` 的统一 assistant message；
7. 把 Environment Output 转换成 observation message。

输入：

```python
messages: list[dict]
```

输出：

```python
assistant_message: dict
```

它不执行 Bash，也不判断任务是否成功。

第一版中的 LiteLLM 仅作为模型 API 调用层，不提供 Agent 循环和代码执行能力。

### 5.5 `src/code_agent/environments/local.py`

这是本地执行层。

它负责：

- 从 Action 中取得 `command`；
- 在当前任务的 `workspace` 中执行命令；
- 收集标准输出、标准错误和返回码；
- 处理命令超时和启动失败；
- 返回统一的 Environment Output。

输入：

```python
{"command": "python -m pytest -q", "tool_call_id": "call_123"}
```

输出：

```python
{"output": "8 passed", "returncode": 0, "exception_info": ""}
```

Windows 第一版明确调用 Git Bash：

```text
C:\Program Files\Git\bin\bash.exe -lc <command>
```

程序应执行 `bash.exe`，而不是用于打开终端窗口的 `git-bash.exe`。Git Bash 路径由配置提供，也可以通过 PATH 查找。

Environment 不调用大模型，也不决定下一轮做什么。

### 5.6 `src/code_agent/agents/default.py`

这是整个项目的核心控制器。

它保存：

- 当前对话历史 `messages`；
- 已调用模型的次数；
- 最近一次命令结果；
- 本地测试是否通过；
- 当前任务的工作目录。

它负责执行以下循环：

```text
初始化 system 和 user message
    -> 查询 Model
    -> 保存 assistant message
    -> 取得 actions
    -> 调用 Environment
    -> 保存 observation message
    -> 更新本地验证状态
    -> 继续下一轮
```

输入：自然语言题目及任务工作目录。

输出：包含执行状态、验证状态、题解路径、测试结果和消息历史的结果字典。

建议提供三个主要方法：

- `run(task)`：初始化并持续运行，直到任务结束；
- `query()`：调用 Model 并保存模型消息；
- `execute_actions(message)`：执行消息中的动作并保存观察结果。

Agent 不直接调用 LiteLLM，也不直接调用 `subprocess`，它只负责组织 Model 和 Environment。

### 5.7 `src/code_agent/config/default.yaml`

这是默认运行配置和提示词的位置。

主要包含：

- system prompt；
- 用户任务模板；
- 模型名称；
- 最大模型调用次数；
- Git Bash 路径；
- 工作目录；
- 命令超时时间；
- 固定的本地测试命令。

第一版约定模型在工作目录中生成：

```text
solution.py
test_solution.py
```

并使用：

```text
python -m pytest -q
```

进行本地验证。

提示词要求模型：

1. 分析题目；
2. 创建题解代码；
3. 根据题目生成样例和边界测试；
4. 实际运行测试；
5. 测试失败后根据输出继续修改；
6. 测试通过后立即提交完成请求。

### 5.8 `src/code_agent/reviewer.py`

这是主循环结束后的独立代码审查模块。

它读取：

- 原始算法题；
- `solution.py`；
- `test_solution.py`；
- 最后一次本地测试结果。

然后进行一次无工具的模型调用，输出：

- 算法思路分析；
- 时间复杂度和空间复杂度；
- 可能遗漏的边界情况；
- 当前测试覆盖情况；
- 代码质量和潜在风险。

Reviewer 不执行 Bash、不修改代码，也不参与 Agent 主循环。

这里的结论应表述为“本地验证通过”和“潜在正确性分析”，不能声称一定通过 LeetCode 的全部隐藏测试。

### 5.9 `src/code_agent/storage.py`

这是运行记录的保存模块。

它负责将可序列化结果写入 JSON，包括：

- 原始题目；
- Agent 退出状态；
- 是否通过本地验证；
- 完整消息历史；
- 每次 Bash 动作和执行结果；
- 最终测试输出；
- Reviewer 评审结果。

输入：Agent 结果和 Reviewer 结果。

输出：

```text
trajectories/<task_id>/trajectory.json
trajectories/<task_id>/review.json
```

题解代码和测试代码仍保存在：

```text
workspace/<task_id>/solution.py
workspace/<task_id>/test_solution.py
```

### 5.10 `src/code_agent/run/main.py`

这是命令行入口和对象组装位置。

它负责：

1. 接收题目和模型名称；
2. 加载 `default.yaml`；
3. 创建 `LitellmModel`；
4. 为本次任务创建独立 workspace；
5. 创建 `LocalEnvironment`；
6. 创建 `DefaultAgent`；
7. 调用 `agent.run(task)`；
8. 成功后调用 Reviewer；
9. 调用 Storage 保存结果；
10. 在终端展示最终文件位置、测试结果和评审。

输入示例：

```powershell
python -m code_agent.run.main --task "实现最长不重复子串"
```

输出示例：

```text
Status: SUCCESS
Local verification: PASS
Solution: workspace/<task_id>/solution.py
Tests: 8 passed
Review: trajectories/<task_id>/review.json
```

`main.py` 不包含模型调用细节、Agent 循环或命令执行代码。

## 6. 本地测试与完成条件

第一版由编程 Agent 根据题目自动生成 `test_solution.py`，测试内容至少覆盖题目样例和模型识别出的边界情况。Environment 使用真实的 `pytest` 命令执行测试。

系统不能仅凭模型说“已经完成”就返回成功。成功需要满足：

1. 模型实际调用约定测试命令 `python -m pytest -q`；
2. Environment 返回 `returncode == 0`；
3. 模型随后请求提交完成；
4. Agent 检查最近一次有效测试确实通过。

第一版可以要求测试通过后，模型下一步必须立即提交。如果测试通过后又执行了其他修改命令，Agent 将验证状态恢复为未验证，并要求重新运行测试。

完成信号可以使用固定的 Bash 提交方式：

```bash
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
```

如果模型在测试尚未通过时提交，Agent 不结束任务，而是将“必须先运行并通过本地测试”的观察消息反馈给模型。

## 7. 一次完整运行

以“实现最大子数组和”为例：

1. Runner 创建本次任务的 workspace，并启动 Agent。
2. Agent 将 system prompt 和题目加入 `messages`。
3. Model 调用大模型，模型请求用 Bash 创建 `solution.py`。
4. Environment 通过 Git Bash 执行命令并返回写入结果。
5. Agent 把结果作为 observation 加入 `messages`。
6. 模型根据题目创建 `test_solution.py`。
7. 模型执行 `python -m pytest -q`。
8. 如果测试失败，Environment 将断言错误反馈给 Agent，模型继续修改代码。
9. 模型再次运行测试，Environment 返回 `returncode == 0`。
10. Agent 记录本地验证通过。
11. 模型发送完成命令，Agent 检查验证状态后结束主循环。
12. Reviewer 读取题目、代码、测试和测试结果并给出评审。
13. Storage 保存 trajectory 和 review，Runner 展示最终结果。
