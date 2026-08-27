# Code Agent

一个面向 Python 算法题的轻量级编程智能体。用户输入自然语言题目后，模型会在本地工作目录中生成 `solution.py` 和 `test_solution.py`，执行测试，并根据真实测试结果迭代修改。只有本地测试通过后，系统才会执行最终代码评审。

## 工作流程

```text
题目 + 对话历史
    -> 模型生成 Bash 动作
    -> 本地环境写代码、写测试或执行 pytest
    -> 执行结果反馈给模型
    -> 测试失败则继续修改
    -> 测试通过后提交
    -> Reviewer 评审
```

模型根据题目生成测试输入和期望输出，本地环境负责真实执行。`pytest` 通过表示“本地验证通过”，不代表保证通过在线判题的全部隐藏测试。

## 环境要求

- Python 3.10+
- Windows 上安装 Git for Windows，并提供 `bin\bash.exe`
- 可用的大语言模型 API

安装项目：

```powershell
python -m pip install -e .
```

复制 `.env.example` 为不入库的 `.env`，设置模型名称、API Key 和 Git Bash 路径。例如：

```text
CODE_AGENT_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=your-key
CODE_AGENT_BASH_PATH=C:\Program Files\Git\bin\bash.exe
```

## 运行

直接输入题目：

```powershell
code-agent --task "实现最长不重复子串，函数接收字符串并返回最长长度"
```

从 UTF-8 文件读取题目：

```powershell
code-agent --task-file problem.txt
```

可以显式覆盖模型或 Git Bash 路径：

```powershell
code-agent --task-file problem.txt --model openai/gpt-4o-mini --bash-path "C:\Program Files\Git\bin\bash.exe"
```

每次运行生成两个目录：

```text
workspace/<run_id>/solution.py
workspace/<run_id>/test_solution.py
trajectories/<run_id>/trajectory.json
trajectories/<run_id>/review.json
```

## 测试项目

```powershell
python -m pytest -q
```

需求与架构说明位于 `doc/`。
