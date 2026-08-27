项目名称：算法题编程智能体

Git 仓库：https://github.com/xwjhhh/code_agent

项目说明：
用户输入一道 Python 算法题，智能体调用大语言模型，通过唯一的 Bash 工具在本地工作目录中创建 solution.py 和 test_solution.py。测试文件由模型根据题目生成，包含具体测试输入及对应期望输出。系统使用 Git Bash 执行 pytest，将真实输出反馈给模型；测试失败时继续修改和测试，只有本地测试通过并提交后才进行最终代码评审。

运行环境：Python 3.10+、Git for Windows、可用的大模型 API。

安装：
python -m pip install -e .

配置：复制 .env.example 为 .env，填写 CODE_AGENT_MODEL、对应模型 API Key 和 CODE_AGENT_BASH_PATH。API Key 只通过环境变量或本地未入库配置提供。

运行：
code-agent --task-file problem.txt

每次运行会在 workspace/<run_id> 保存题解和测试，在 trajectories/<run_id> 保存对话轨迹及评审结果。
