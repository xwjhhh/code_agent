1.前端手工填写测试用例
        │
        └── 或调用 POST /api/test-cases/generate
                ↓
        AI 生成默认测试用例
        ├── 典型样例
        ├── 边界情况
        └── 特殊输入情况
                ↓
POST /api/runs
        ↓
api.py::_run_agent()
        ↓
判断 request.test_cases 是否为空
        ├── 不为空：使用手工用例
        │       ↓
        │   normalize_cases()
        │
        └── 为空：调用 generate_test_cases()
                ↓
        normalize_cases()
                ↓
        统一转换为字符串格式
                ↓
save_test_files()
        ├── test_cases.json
        └── test_solution.py
1.1 手工填写和 AI 生成
手工填写输入和预期输出或者让ai生成默认六个测试用例包括不同的测试边界（模型自行判断）以及输入和预期输出

对测试文件的保护：每次模型执行命令后：
- 如果文件被修改或删除，就恢复原内容；

编程模型的系统提示词也明确要求先读取 test_cases.json，只能修改 solution.py，并且必须执行：
python -m pytest -q

2.大模型与工具适配层
api.py::_build_model()
        ↓
读取 default.yaml 中的模型配置
        ↓
创建 LitellmModel
        ↓
读取 API Key、API Base、超时时间
        ↓
DefaultAgent.query()
        ↓
LitellmModel.query(messages)
        ↓
调用 LiteLLM / DeepSeek V4 Flash
        ↓
向模型注册唯一工具：bash
        ↓
模型返回一个 Bash Tool Call
        ↓
parse_tool_calls()
        ↓
校验工具调用格式
        ├── 必须是 bash
        ├── 每轮只能一个调用
        ├── command 必须是非空字符串
        └── 必须存在 tool_call_id
        ↓
转换为内部 action
        ↓
交给 LocalEnvironment 执行

3.核心 Agent 编排层
POST /api/runs
        ↓
api.py::create_run()
        ├── 校验请求参数
        ├── 创建 run_id
        ├── 创建独立 workspace
        ├── 创建 trajectory 存储目录
        └── 启动后台线程 _run_agent()
        │
        ↓
api.py::_run_agent()
        ├── 加载 default.yaml
        ├── 初始化模型
        ├── 初始化 Memory
        ├── 选择测试用例
        │     ├── 手工用例：normalize_cases()
        │     └── 无手工用例：generate_test_cases()
        ├── save_test_files()
        │     ├── test_cases.json
        │     └── test_solution.py
        ├── 检索当前任务相关记忆
        ├── 创建 LocalEnvironment
        └── 创建 DefaultAgent
        │
        ↓
DefaultAgent.run()
        ↓
初始化对话上下文
        ├── system_prompt
        ├── task_template + 当前题目
        └── task memory
        │
        ↓
循环执行，直到 success / max_steps / model_error
        │
        ├── query()
        │     └── 模型根据 messages 思考
        │           并生成一个 Bash 工具调用
        │
        ├── parse_tool_calls()
        │     └── 检查是否只有一个合法 bash 命令
        │
        ├── LocalEnvironment.execute()
        │     └── Git Bash 执行命令
        │
        ├── 返回 stdout / stderr / returncode
        │
        ├── 将执行结果追加回 messages
        │
        ├── 如果是 pytest：
        │     ├── 判断是否通过
        │     ├── 检查 solution.py
        │     ├── 检查 test_solution.py
        │     └── 检查 test_cases.json
        │
        ├── pytest 失败：
        │     └── 检索 Recovery Memory 并继续修复
        │
        └── pytest 通过后：
              └── 等待模型执行提交命令
        │
        ↓
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
        ↓
检查 verified == True
        ├── 是：Agent 状态变为 success
        └── 否：拒绝提交，继续让模型修复
        │
        ↓
Reviewer
        ├── 读取 solution.py
        ├── 读取 test_solution.py
        ├── 读取 test_cases.json
        ├── 读取 pytest 输出
        └── 生成只读代码评审结果
        │
        ↓
保存 trajectory、review、memory
        ↓
发送 run_finished 事件
        ↓
前端通过 SSE 获取完整执行过程


4.本地执行环境层
DefaultAgent.execute_actions()
        ↓
LocalEnvironment.execute(action)
        ↓
解析 Bash 路径
        ├── 配置文件中的 bash_path
        ├── CODE_AGENT_BASH_PATH
        └── Windows 常见 Git Bash 路径
        ↓
subprocess.run()
        ├── 使用 Git Bash
        ├── cwd = 当前 run 的 workspace
        ├── 执行 bash -lc command
        ├── 设置超时时间
        └── 捕获 stdout、stderr、returncode
        ↓
合并执行输出
        ↓
恢复受保护文件
        ├── 文件未变化：返回正常结果
        └── 文件被修改：恢复文件并返回失败
        ↓
返回 observation

5.测试验证与代码评审层
模型生成 solution.py
        ↓
执行 python -m pytest -q
        ↓
test_solution.py 被 pytest 加载
        ↓
读取 test_cases.json
        ↓
调用 solution.solve(input_text)
        ↓
比较实际输出和期望输出
        ↓
返回 pytest 结果
        ├── 失败：继续修复
        └── 成功：设置 verified=True
        ↓
检查必要文件是否存在
        ↓
模型执行提交命令
        ↓
DefaultAgent 状态变为 success
        ↓
Reviewer.review()

6.持久化经验记忆层
启动任务
        ↓
build_memory_manager()
        ├── 检查 memory.enabled
        ├── 检查 Embedding API Key
        └── 初始化 SQLite MemoryStore
        ↓
任务开始前检索
        ↓
QueryAnalyzer 分析当前题目
        ↓
生成 task / subtask 查询
        ↓
Embedding 模型生成向量
        ↓
SQLite 中进行余弦相似度搜索
        ↓
按相似度、质量和优先级排序
        ↓
LLM Reranker 选择少量高价值记忆
        ↓
format_memory_context()
        ↓
注入 DefaultAgent 初始 messages

7.后端 API 与运行数据持久化层
前端 POST /api/runs
        ↓
api.py::create_run()
        ├── 校验题目、模型、步数、测试用例
        ├── 创建 run_id
        ├── 创建 workspace
        ├── 创建 RunStorage
        ├── 写入内存 RUNS
        └── 启动后台线程 _run_agent()
        ↓
立即返回 HTTP 202
        └── {run_id, status, events_url}
        ↓
后台线程执行 Agent
        ↓
RunState.emit()
        ├── 记录事件序号
        ├── 记录事件类型
        ├── 记录事件数据
        ├── 记录时间戳
        └── 通知等待中的前端连接
        ↓
前端 GET /api/runs/{run_id}/events
        ↓
SSE 持续接收事件
        ├── model_thinking
        ├── command_started
        ├── command_finished
        ├── test_passed
        ├── test_failed
        ├── review_finished
        └── run_finished
        ↓
任务结束
        ├── state.done = True
        ├── 保存 trajectory.json
        ├── 保存 review.json
        └── SSE 流结束