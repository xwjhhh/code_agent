算法题编程智能体
Git 仓库：https://github.com/xwjhhh/code_agent
说明
面向 Python 算法题的编程智能体。用户提交题目与用例，系统在独立工作区调用大模型，通过 Bash 编写 solution.py、运行 pytest 并按失败结果修复；通过后由 Reviewer 评审。
特色功能
1. Agent 闭环：仅开放 Bash，实现调用解析、上下文、执行、超时、限步和停止条件。
2. 可信测试：用例可手动或模型生成，保存 test_cases.json 并生成 test_solution.py。测试文件受保护，模型只能修改 solution.py；python -m pytest -q 通过后才能提交评审。
3. Agentic RAG：从验证轨迹按证据提取经验，进行 Embedding 召回、LLM 重排、故障检索和语义去重，最多注入 4 条，保存于 SQLite。
4. 可观测工作台：FastAPI + Next.js + SSE 展示模型调用、命令、文件、测试、评审和记忆事件，并提供 CLI。
运行环境
Python 3.10+、Node.js 18+、Git for Windows（Git Bash）和大模型 API。
安装配置
python -m pip install -e .
复制 .env.example 为 .env，填写 API Key 和 CODE_AGENT_BASH_PATH；密钥不要提交仓库。
启动 Web
python -m uvicorn code_agent.api:app --app-dir src --host 127.0.0.1 --port 8000
cd frontend；npm install；npm run dev。访问 http://localhost:3000。
命令行
code-agent --task-file problem.txt
运行产物
workspace/<run_id>/ 保存题解和测试；trajectories/<run_id>/ 保存轨迹与评审；memory_store/memory.sqlite3 保存经验。
验证
python -m pytest -q
cd frontend；npm run build
本地测试通过不代表在线隐藏测试全部通过。
