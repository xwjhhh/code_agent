算法题编程智能体

Git 仓库：https://github.com/xwjhhh/code_agent

项目说明：
这是一个面向 Python 算法题的本地自主编程智能体。用户输入题目和标准输入输出用例后，模型通过唯一的 Bash 工具在独立工作目录中编写 solution.py、执行 pytest，并根据真实错误信息循环修复。测试文件由系统生成并保护，只有测试真实通过后才允许提交；随后由只读 Reviewer 分析算法、复杂度和边界情况。验证过的成功策略与失败修复会提炼为经验，使用 Embedding + SQLite 为后续题目检索。项目还提供 FastAPI + Next.js + SSE 实时工作台和 CLI。

运行环境：Python 3.10+、Node.js 18+、Git for Windows（Git Bash）和可用的大模型 API。

安装后端：
python -m pip install -e .

配置：复制 .env.example 为 .env，填写 API Key 和 CODE_AGENT_BASH_PATH。凭据只通过环境变量或未入库配置文件提供。

启动 Web：
python -m uvicorn code_agent.api:app --app-dir src --host 127.0.0.1 --port 8000
cd frontend；npm install；npm run dev
浏览器访问 http://localhost:3000。

命令行：
code-agent --task-file problem.txt --model openai/deepseek-ai/DeepSeek-V4-Flash

本地测试通过仅代表通过当前用例，不保证在线判题隐藏测试一定通过。
