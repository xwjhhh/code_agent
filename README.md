# Code Agent

**Code Agent** 是一个面向 Python 算法题的本地自主编程智能体。

它不是只调用一次大模型生成代码，而是让模型在真实执行环境中完成：

**理解题目 → 编写代码 → 执行测试 → 分析错误 → 自动修复 → 验证结果 → 代码评审 → 经验沉淀**

用户输入自然语言题目以及输入输出测试用例后，Agent 会在独立工作目录中编写 `solution.py`，通过 `pytest` 执行真实测试，并根据失败信息持续修改代码，直到测试通过或达到运行限制。

项目同时提供 **Reviewer、持久化经验记忆、Web 实时运行轨迹以及 CLI**。

GitHub：

`https://github.com/xwjhhh/code_agent`

在线静态展示：

`https://xwjhhh.github.io/code_agent/`

---

## Features

### Autonomous Coding Loop

Code Agent 会在真实本地环境中完成完整的编程循环：

```text
Problem
   ↓
Test Cases
   ↓
test_cases.json
   ↓
Agent writes solution.py
   ↓
pytest
   ↓
Pass? ── No ──→ Execution Error
   ↑                 ↓
   └──── Modify Code ┘
   ↓ Yes
Reviewer
   ↓
Memory Extraction
```

模型通过 Bash 工具操作独立工作目录，可以：

* 阅读题目和测试数据；
* 编写和修改 `solution.py`；
* 执行固定的 `pytest`；
* 获取真实 stdout、stderr 和 traceback；
* 根据测试失败继续修复代码。

这使 Code Agent 不只是进行代码生成，而是能够基于真实程序执行结果进行迭代式 Debug。

---

## Reliable Test Loop

测试用例统一保存在：

```text
test_cases.json
```

它是以下模块共享的权威输入输出数据源：

```text
Programming Agent
pytest
Reviewer
```

测试流程为：

```text
人工输入测试用例
        │
        ├──────────────┐
        │              │
模型生成测试用例        │
        │              │
        └──────→ test_cases.json
                       │
                       ↓
                 solution.py
                       │
                       ↓
              test_solution.py
                       │
                       ↓
                    pytest
                       │
              ┌────────┴────────┐
              │                 │
            Failed             Passed
              │                 │
              ↓                 ↓
        Agent receives        Reviewer
        real errors
              │
              ↓
        Modify solution.py
```

`test_solution.py` 在 Agent 循环中受到保护。

模型不能通过修改测试文件或期望输出绕过失败，只能修改自己的解题代码。

需要注意：

> 本地测试通过只表示代码通过当前提供的测试用例，并不保证一定通过在线判题平台的隐藏测试。

---

## Reviewer

当代码通过本地 pytest 后，系统会进入独立的 Reviewer 阶段。

Reviewer 会分析：

* 算法思路；
* 时间复杂度；
* 空间复杂度；
* 边界情况；
* 潜在风险；
* 代码质量。

Reviewer 与编程阶段分离，避免只用“测试通过”作为唯一评价标准。

---

## Persistent Experience Memory

Code Agent 支持持久化的轨迹经验记忆。

完成一次经过验证的任务后，系统会从运行轨迹中提炼两类经验：

```text
Successful Strategies
Debugging / Recovery Experience
```

例如：

```text
Problem
   ↓
Verified Run
   ↓
Trajectory Analysis
   ↓
Reusable Experience
   ↓
Embedding
   ↓
SQLite Memory Store
```

新任务开始时，系统会根据当前题目进行语义检索，将少量相关经验提供给 Agent。

如果 pytest 执行失败，还会触发 **Recovery Retrieval**，检索过去类似错误和修复经验，辅助下一轮修改。

因此，Agent 可以从过去经过验证的任务中积累经验，而不是每次完全从零开始。

当前 Embedding 模型：

```text
Qwen/Qwen3-Embedding-8B
```

向量和经验数据保存在本地 SQLite：

```text
memory_store/memory.sqlite3
```

`memory_store/` 已加入 `.gitignore`，不会提交到 GitHub。

详细设计：

```text
doc/MEMORY_V2.md
```
---

## Model

项目当前使用：

```text
DeepSeek-V4-Flash
```

作为主要对话模型，负责：

* 任务分析；
* Bash 工具调用；
* solution.py 编写；
* 测试用例生成；
* Reviewer；
* Memory 分析。

模型通过硅基流动提供的 OpenAI-compatible API 调用。

项目使用 LiteLLM 统一模型 API。

需要强调的是：

> LiteLLM 只负责模型厂商 API 调用，Agent Loop、工具调用逻辑、测试执行、Reviewer、Memory 和工作区管理均由本项目实现。

---

# Quick Start

## Requirements

后端：

```text
Python 3.10+
```

前端：

```text
Node.js 18+
```

Windows 环境需要安装：

```text
Git for Windows
```

并确保存在：

```text
C:\Program Files\Git\bin\bash.exe
```

---

## Install Backend

在项目根目录运行：

```powershell
python -m pip install -e .
```

---

## Configure Environment

建议将硅基流动 API Key 保存在 Windows 环境变量中：

```text
SILICONFLOW_API_KEY
```

项目根目录创建未提交到 Git 的 `.env`：

```text
OPENAI_API_KEY=${SILICONFLOW_API_KEY}
SILICONFLOW_EMBEDDING_API_KEY=${SILICONFLOW_API_KEY}

OPENAI_API_BASE=https://api.siliconflow.cn/v1

CODE_AGENT_MODEL=openai/deepseek-ai/DeepSeek-V4-Flash
CODE_AGENT_BASH_PATH=C:\Program Files\Git\bin\bash.exe
```

不要将真实 API Key：

* 写入仓库；
* 提交到 Git；
* 写入前端代码；
* 导出到 GitHub Pages 数据中。

---

# Web Application

项目提供 FastAPI 后端和 Next.js 前端。

## Start Backend

在项目根目录运行：

```powershell
python -m uvicorn code_agent.api:app --app-dir src --host 127.0.0.1 --port 8000
```

后端地址：

```text
http://127.0.0.1:8000
```

---

## Start Frontend

另开一个终端：

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开：

```text
http://localhost:3000
```

Web 页面支持：

* 查看真实 FastAPI 运行记录；
* 手工输入多组标准输入 / 期望输出；
* 调用模型自动生成测试用例；
* SSE 实时查看 Agent 运行轨迹；
* 查看 `solution.py`；
* 查看 `test_solution.py`；
* 查看 `test_cases.json`；
* 查看真实 Bash 命令输出；
* 查看 pytest 结果；
* 查看 Reviewer 结果。

---

# CLI

Code Agent 同样支持命令行运行。

准备题目文件：

```text
problem.txt
```

运行：

```powershell
code-agent --task-file problem.txt --model openai/deepseek-ai/DeepSeek-V4-Flash
```

如果需要手工指定 Git Bash：

```powershell
code-agent `
  --task-file problem.txt `
  --model openai/deepseek-ai/DeepSeek-V4-Flash `
  --bash-path "C:\Program Files\Git\bin\bash.exe"
```

CLI 会先生成 `test_cases.json`，然后运行与 Web 版本相同的 Agent 编程闭环。

---

# Runtime Artifacts

每次任务都有独立的 `run_id`。

工作目录：

```text
workspace/<run_id>/
```

主要文件：

```text
workspace/<run_id>/solution.py
workspace/<run_id>/test_cases.json
workspace/<run_id>/test_solution.py
```

运行轨迹：

```text
trajectories/<run_id>/trajectory.json
```

Reviewer 结果：

```text
trajectories/<run_id>/review.json
```

这种设计可以让每次 Agent 执行彼此隔离，同时保留完整运行轨迹用于 Debug、Reviewer 和 Memory 分析。

---

# GitHub Pages Showcase

仓库中的：

```text
docs/index.html
```

提供一个静态项目展示页面。

它用于展示：

* 历史运行快照；
* Agent 执行结果；
* Reviewer 信息；
* 中文经验知识图谱。

GitHub Pages **不会直接连接本地 FastAPI，也不会调用模型或执行代码**。

展示数据由本地数据库和运行轨迹导出。

更新本机运行记录或 Memory 后，在项目根目录执行：

```powershell
python scripts/export_showcase_data.py
```

脚本会读取：

```text
trajectories/
memory_store/memory.sqlite3
```

并生成：

```text
docs/data/runs.json
docs/data/memories.json
```

导出过程会排除：

* Embedding 向量；
* 模型原始消息；
* 本地工作区路径；
* API Key 等敏感信息。

确认数据后提交：

```text
docs/data/runs.json
docs/data/memories.json
```

推送到 `main` 后：

```text
.github/workflows/pages.yml
```

会自动部署 `docs/` 到 GitHub Pages。

展示地址：

```text
https://xwjhhh.github.io/code_agent/
```

如果 Pages 尚未启用：

```text
GitHub Repository
→ Settings
→ Pages
→ Source
→ GitHub Actions
```

---

# Project Philosophy

普通代码生成流程通常是：

```text
Problem
   ↓
LLM
   ↓
Code
```

Code Agent 希望实现的是：

```text
Problem
   ↓
Reasoning
   ↓
Coding
   ↓
Execution
   ↓
Feedback
   ↓
Self-Correction
   ↓
Verification
   ↓
Review
   ↓
Experience Memory
   ↓
Future Tasks
```

核心目标不是单次生成一个看起来合理的答案，而是让模型能够：

**执行代码、观察结果、修复错误、验证输出，并把经过验证的经验用于未来任务。**

---

# Validation

运行后端测试：

```powershell
python -m pytest -q
```

验证前端：

```powershell
cd frontend
npm run build
```

---

# Documentation

更多需求说明、模块设计和逐文件架构说明位于：

```text
doc/
```

其中 Memory V2 设计：

```text
doc/MEMORY_V2.md
```
