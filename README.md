<div align="center">

# Code Agent

### An autonomous coding agent that writes, tests, debugs and reviews Python solutions.

自然语言题目 → 生成测试 → 编写 `solution.py` → `pytest` → 按失败修复 → Reviewer

[🚀 Live Demo](https://xwjhhh.github.io/code_agent/) · [📖 Architecture](doc/ARCHITECTURE.md) · [⭐ GitHub](https://github.com/xwjhhh/code_agent)

<br>

**打开 Demo，点击 `Run Agent`，查看一条真实本地运行轨迹的交互式回放。**

</div>

![GitHub Pages deployment](https://github.com/xwjhhh/code_agent/actions/workflows/pages.yml/badge.svg)

## 项目亮点

Code Agent 是一个面向 Python 算法题的 local-first 编程智能体。它让模型只能通过受控的 Bash 工具修改隔离工作区，再用真实的 `pytest` 输出驱动下一轮修复；测试通过后才进入独立的 Reviewer，并将可复用经验沉淀到本地记忆库。

GitHub Pages 是一个零后端的项目展示页：它读取仓库中的 `docs/data/*.json` 快照，默认展示 Agent Demo，按时间线回放分析、测试、编码和验证过程。回放不会连接 FastAPI、不会调用模型，也不会暴露 API Key，因此任何人打开链接都能直接体验。

## Demo 回放

| 阶段 | 页面展示 |
| --- | --- |
| Analyze | 解析输入输出格式、约束和边界条件 |
| Generate tests | 展示导出的测试用例数量和 `test_cases.json` |
| Write code | 展示 Agent 通过 Bash 写入的 `solution.py` |
| Run pytest | 回放真实快照里的命令输出和通过/失败状态 |
| Verify | 进入 Reviewer，展示最终验证结果 |

线上展示：<https://xwjhhh.github.io/code_agent/>

## 本地运行

环境要求：Python 3.10+、Node.js 18+、Windows Git Bash（需要 `bin\\bash.exe`）。真实模型运行还需要对应厂商的 API Key。

```powershell
python -m pip install -e .

# 启动 FastAPI
python -m uvicorn code_agent.api:app --app-dir src --host 127.0.0.1 --port 8000

# 另开终端启动 Next.js 工作台
cd frontend
npm install
npm run dev
```

打开 <http://localhost:3000>。工作台提供实时 SSE 轨迹、测试用例、终端输出、代码文件、Reviewer 和记忆图谱。

也可以直接使用 CLI 运行一条任务：

```powershell
code-agent --task-file problem.txt --model openai/deepseek-ai/DeepSeek-V4-Flash
```

需要覆盖 Git Bash 路径时追加 `--bash-path "C:\Program Files\Git\bin\bash.exe"`。

### 环境变量

将密钥只放在系统环境变量或未入库的 `.env` 中。以硅基流动为例：

```text
OPENAI_API_KEY=your_key
SILICONFLOW_EMBEDDING_API_KEY=your_key
OPENAI_API_BASE=https://api.siliconflow.cn/v1
CODE_AGENT_MODEL=openai/deepseek-ai/DeepSeek-V4-Flash
CODE_AGENT_BASH_PATH=C:\\Program Files\\Git\\bin\\bash.exe
```

不要把真实 Key 写入 Git、README 或前端代码。Embedding 固定使用 `Qwen/Qwen3-Embedding-8B`；没有 Embedding Key 时会回退到 `OPENAI_API_KEY`。

## 导出 Pages 快照

运行完成后，在项目根目录执行：

```powershell
python scripts/export_showcase_data.py
```

脚本从 `trajectories/` 和本地 `memory_store/memory.sqlite3` 生成：

- `docs/data/runs.json`：题目、状态、测试输出、模型调用次数和公开的 `solution.py`。
- `docs/data/memories.json`：知识节点及其关系。

导出过程会排除向量、模型消息、工作区路径、环境配置和密钥。检查快照内容后提交并推送，GitHub Actions 会自动将 `docs/` 部署到 Pages。仓库 Settings → Pages 的 Source 需要设置为 **GitHub Actions**。

## 架构概览

```text
自然语言题目 + 输入/输出用例
        │
        ▼
  FastAPI / SSE ──▶ Agent loop ──▶ 受控 Bash ──▶ workspace/<run_id>
        │                 │                 │
        │                 └── pytest ◀──────┘
        │                         │
        └── trajectory.json ◀─────┴── Reviewer / Memory
                                      │
                                      ▼
                              docs/data/*.json
                                      │
                                      ▼
                              GitHub Pages Replay
```

更多设计取舍见 [`doc/ARCHITECTURE.md`](doc/ARCHITECTURE.md)、[`doc/REQUIREMENTS.md`](doc/REQUIREMENTS.md) 和 [`doc/MEMORY_V2.md`](doc/MEMORY_V2.md)。

## 目录结构

```text
src/code_agent/       Agent、模型、环境、Reviewer 与记忆实现
frontend/              本地 Next.js 运行工作台
scripts/               批量运行与 Pages 快照导出
trajectories/          本地运行轨迹（默认不提交具体任务数据）
docs/                  GitHub Pages 静态展示和公开快照
tests/                 Python 单元测试
```

## 验证

```powershell
python -m pytest -q
cd frontend
npm run build
```

本地测试只验证当前输入输出用例，不能替代线上题目的隐藏测试。静态 Pages 只展示已导出的快照，不会在访问者浏览器中执行任意 Python 代码。
