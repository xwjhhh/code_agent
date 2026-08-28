项目名称：算法题编程智能体

Git 仓库：https://github.com/xwjhhh/code_agent

项目说明：
用户输入一道 Python 算法题，并手动填写测试输入/输出，或让 GLM-5.2 根据题目生成测试用例。系统保存权威的 test_cases.json，并固定生成 test_solution.py；编程模型只通过唯一的 Bash 工具创建和修改 solution.py。系统使用 Git Bash 执行 pytest，将真实输出反馈给模型；测试失败时继续修改和测试，测试通过并提交后才进行最终代码评审。验证成功且评审完成后，系统会提炼可复用经验并保存到本地记忆库。

运行环境：Python 3.10+、Git for Windows、可用的大模型 API。

安装：
python -m pip install -e .

配置：复制 .env.example 为 .env，填写 GLM-5.2 的 API Key 和 CODE_AGENT_BASH_PATH。Embedding 固定使用 Qwen/Qwen3-Embedding-8B。API Key 只通过环境变量或本地未入库配置提供。

运行：
code-agent --task-file problem.txt

每次运行会在 workspace/<run_id> 保存 solution.py、test_cases.json 和 test_solution.py，在 trajectories/<run_id> 保存对话轨迹及评审结果；验证成功的经验保存在 memory_store/memory.sqlite3。
