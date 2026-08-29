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

硅基流动凭据只放在 Windows 环境变量和未入库的 `.env` 中。假设系统变量名为 `glm_api` 和 `deepseek_api`，项目根目录的 `.env` 写为：

```text
OPENAI_API_KEY=${GLM_API}
SILICONFLOW_DEEPSEEK_API_KEY=${DEEPSEEK_API}
OPENAI_API_BASE=https://api.siliconflow.cn/v1
CODE_AGENT_MODEL=openai/zai-org/GLM-5.2
CODE_AGENT_BASH_PATH=C:\Program Files\Git\bin\bash.exe
```

Windows 环境变量查找不区分大小写，所以系统设置中的 `glm_api` 和 `deepseek_api` 可分别由 `.env` 通过 `${GLM_API}` 与 `${DEEPSEEK_API}` 引用。不要把真实 Key 写入仓库或前端代码。

项目固定使用硅基流动的 `GLM-5.2` 作为唯一对话模型，负责任务分析、Bash 工具调用、测试生成、Reviewer 和记忆分析。

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

## GitHub 项目展示

仓库内的 [`docs/index.html`](docs/index.html) 是一个独立的只读展示页，只呈现历史运行快照和中文知识图谱，不连接 FastAPI、不调用模型，也不会创建或执行任务。

推送到 `main` 后，`.github/workflows/pages.yml` 会自动将 `docs/` 部署到 GitHub Pages。仓库 `xwjhhh/code_agent` 的展示地址为：

`https://xwjhhh.github.io/code_agent/`

若仓库尚未启用 Pages，请在仓库 Settings → Pages 中将 Source 设为 GitHub Actions。页面中的“查看仓库”链接仍指向源码仓库，便于面试或项目演示时切换查看。

所有运行均使用 LiteLLM 调用所选模型。LiteLLM 只负责厂商 API 调用，Agent 循环和本地工具仍由本项目实现。

## 命令行运行

```powershell
code-agent --task-file problem.txt --model openai/zai-org/GLM-5.2
```

也可以覆盖 Git Bash 路径：

```powershell
code-agent --task-file problem.txt --model openai/zai-org/GLM-5.2 --bash-path "C:\Program Files\Git\bin\bash.exe"
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

## V2 持久化经验记忆

项目已加入可选的轨迹经验记忆：验证成功的运行会提炼 Strategy、Recovery、Optimization 经验，调用硅基流动 Embeddings API 建立向量索引，并保存到本地 SQLite。新任务开始前进行 task/subtask 多粒度检索，pytest 失败后进行 Recovery 检索，最多把少量筛选后的经验作为参考注入编程模型。详细设计见 [`doc/MEMORY_V2.md`](doc/MEMORY_V2.md)。

Embedding 固定使用 `Qwen/Qwen3-Embedding-8B`。可在 `.env` 中设置 `SILICONFLOW_EMBEDDING_API_KEY`；未设置时回退到 `OPENAI_API_KEY`，Base URL 仍为 `https://api.siliconflow.cn/v1`。记忆库目录 `memory_store/` 已被 Git 忽略。

## 验证

```powershell
python -m pytest -q
cd frontend
npm run build
```

需求和逐文件架构说明位于 `doc/`。
