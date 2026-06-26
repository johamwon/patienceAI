# 患癌知光

面向患者的疑难杂症科研动态检索与通俗化解释 Agent

## 快速启动

### 方式一：一键启动（推荐）

**Windows (PowerShell):**
```powershell
.\start.ps1
```

**Windows (CMD):**
```cmd
start.bat
```

**Mac / Linux / WSL:**
```bash
bash start.sh
```

首次运行会自动：
1. 创建 Python 虚拟环境并安装后端依赖
2. 安装前端依赖
3. 启动后端服务（端口 8000）
4. 启动前端服务（端口 3000）

### 方式二：手动启动

**1. 克隆仓库**
```bash
git clone <repo-url>
cd patienceAI
```

**2. 配置环境变量**
```bash
cp .env.example .env
# 编辑 .env，填入你的硅基流动 API Key
```

**3. 安装后端依赖**
```bash
python -m venv backend/venv
# Windows:
backend\venv\Scripts\activate
# Mac/Linux:
source backend/venv/bin/activate

pip install -r backend/requirements.txt
```

**4. 安装前端依赖**
```bash
cd frontend
npm install
cd ..
```

**5. 启动服务**

终端 1 - 后端：
```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

终端 2 - 前端：
```bash
cd frontend
npm run dev
```

### 访问地址

- **前端页面**：http://localhost:3000
- **后端 API**：http://localhost:8000
- **API 文档**：http://localhost:8000/docs

## 环境变量

见 `.env.example`，主要配置：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `LLM_API_KEY` | 硅基流动 API Key（必填） | - |
| `LLM_BASE_URL` | LLM 接口地址 | `https://api.siliconflow.cn/v1` |
| `LLM_MODEL` | 模型名称 | `Qwen/Qwen2.5-7B-Instruct` |
| `KNOWS_API_KEY` | KnowS AI API Key（可选，匿名调用限流 3 req/s） | 留空 |

## 项目结构

```
patienceAI/
├── backend/                 # Python FastAPI 后端
│   ├── app/
│   │   ├── api/            # API 路由 (search, explain, evaluate)
│   │   ├── models/         # Pydantic 数据模型
│   │   └── services/       # 业务服务 (KnowS AI, LLM, 意图识别)
│   └── requirements.txt
├── frontend/               # React + TypeScript 前端
│   ├── src/
│   │   ├── components/     # 组件 (EvidenceList, ExplanationView)
│   │   ├── pages/          # 页面
│   │   ├── api/            # API 调用
│   │   └── types/          # TypeScript 类型
├── agents/                 # ★ 多智能体通俗化引擎
│   ├── core/
│   │   └── simplification_loop.py # 五位一体 Simplification Loop
│   └── prompts/
│       └── system_prompts.py       # 智能体系统提示词
├── eval/                   # 评测数据集与脚本
│   ├── datasets/           # L1/L2/L3 评测数据
│   └── scripts/run_eval.py # 自动化评测脚本
├── start.bat               # Windows 一键启动 (CMD)
├── start.ps1               # Windows 一键启动 (PowerShell)
├── start.sh                # Mac/Linux/WSL 一键启动
└── IMPLEMENTATION_PLAN_v2.md  # 实施计划
```

## 核心功能

1. **多源医学证据检索** — 通过 KnowS AI 检索 6 类权威医学证据
2. **五位一体通俗化引擎** — Layperson → Medical Expert → Simplifier → Language Clarifier → Redundancy Checker
3. **三层结构化输出** — 一句话结论 + 证据卡片 + 患者通俗解释
4. **四级风险路由** — 低/中/高/禁止四级风险分类与分流
5. **幻觉防御** — 证据锁定生成 + Schema 约束 + 可读性检验

## 技术栈

- **后端**：Python FastAPI
- **前端**：React + TypeScript + Vite
- **LLM**：硅基流动 SiliconFlow（默认 Qwen2.5-7B）
- **检索**：KnowS AI 结构化医学证据 API
- **部署**：本地一键启动脚本

## License

MIT
