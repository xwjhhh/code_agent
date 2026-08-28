# Code Agent

面向 Python 算法题的本地编程智能体。用户提交自然语言题目和输入输出用例后，模型通过 Bash 在独立工作目录中编写 `solution.py`、执行 pytest、根据真实失败信息迭代修改，并在测试通过后执行独立代码评审。

仓库：https://github.com/xwjhhh/code_agent

## 数据闭环

```text
人工输入测试用例 或 模型生成测试用例
    -> test_cases.json
    -> 编程模型读取输入输出格式
    -> 编写 solution.py
    -> 固定 test_solution.py 读取同一份 JSON
    -> pytest
    -> 失败则继续修改题解
    -> 通过后 Reviewer
```

`test_cases.json` 是编程模型、pytest 和 Reviewer 共用的权威输入输出文件。测试文件在 Agent 循环中受保护，模型不能通过修改期望输出规避失败。

## 环境要求

- Python 3.10+
- Node.js 18+
- Windows 安装 Git for Windows，并提供 `bin\bash.exe`
- 使用真实模型时配置对应厂商的 API Key

安装后端：

```powershell
python -m pip install -e .
```

凭据只放在环境变量或未入库的 `.env` 中：

```text
CODE_AGENT_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=your-key
CODE_AGENT_BASH_PATH=C:\Program Files\Git\bin\bash.exe
```

## 启动 Web 应用

项目根目录启动 FastAPI：

```powershell
python -m uvicorn code_agent.api:app --app-dir src --host 127.0.0.1 --port 8000
```

另开终端启动 Next.js：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://localhost:3000`。页面提供：

- 真实 FastAPI 运行列表；
- 手工输入多组标准输入/期望输出；
- 调用所选模型生成测试用例；
- SSE 实时运行轨迹；
- `solution.py`、`test_solution.py`、`test_cases.json` 文件展示；
- 真实命令输出、pytest 结果和 Reviewer。

选择“演示模型”无需 API Key，也会真实执行 Agent 循环、Git Bash、文件写入和 pytest。选择 LiteLLM 模型时由 LiteLLM 负责厂商 API 调用，Agent 循环和本地工具仍由本项目实现。

## 命令行运行

```powershell
code-agent --task-file problem.txt --model openai/gpt-4o-mini
```

也可以覆盖 Git Bash 路径：

```powershell
code-agent --task-file problem.txt --model openai/gpt-4o-mini --bash-path "C:\Program Files\Git\bin\bash.exe"
```

CLI 会先调用模型生成 `test_cases.json`，然后运行与 Web 相同的编程闭环。

## 运行产物

```text
workspace/<run_id>/solution.py
workspace/<run_id>/test_cases.json
workspace/<run_id>/test_solution.py
trajectories/<run_id>/trajectory.json
trajectories/<run_id>/review.json
```

本地测试通过只表示通过当前输入输出用例，不保证通过在线判题隐藏测试。

## 验证

```powershell
python -m pytest -q
cd frontend
npm run build
```

需求和逐文件架构说明位于 `doc/`。
