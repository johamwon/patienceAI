# 医语桥

面向患者的循证医学检索与通俗化解释 Agent

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
│   │   ├── api/            # API 路由 (search/clarify/explain/visit_prep/evaluate/radar)
│   │   ├── models/         # Pydantic 数据模型
│   │   └── services/       # 业务服务
│   │       ├── knows_client.py       # KnowS AI 检索
│   │       ├── intent_classifier.py  # 8 类意图 + 四级风险
│   │       ├── query_rewriter.py     # 查询重写
│   │       ├── answer_alignment.py   # 答案对齐与证据重排
│   │       ├── emotion_detector.py   # 情绪感知
│   │       ├── companion_engine.py   # 陪伴暖场白
│   │       ├── research_stage.py     # 研究阶段标注
│   │       ├── cache_service.py      # 缓存策略
│   │       └── radar/               # 研究雷达（patrol/digest/subscription/delivery）
│   └── requirements.txt
├── frontend/               # React + TypeScript 前端
│   ├── src/
│   │   ├── components/     # 组件（ExplanationView/EvidenceList/VisitPrepView/Mascot/CompanionBanner/SubscribePrompt 等）
│   │   ├── pages/          # 页面（SearchPage）
│   │   ├── api/            # API 调用
│   │   └── types/          # TypeScript 类型
├── agents/                 # ★ 多智能体通俗化引擎
│   ├── core/
│   │   ├── simplification_loop.py  # 通俗化引擎
│   │   └── visit_prep_generator.py # 就医准备包
│   ├── prompts/
│   │   └── persona.py              # 人格与合规约束
│   └── demo_scenarios.py           # 演示场景
├── eval/                   # 评测数据集与脚本
│   ├── datasets/           # L1/L2/L3 评测数据
│   └── scripts/run_eval.py # 自动化评测脚本
├── start.bat               # Windows 一键启动 (CMD)
├── start.ps1               # Windows 一键启动 (PowerShell)
├── start.sh                # Mac/Linux/WSL 一键启动
└── IMPLEMENTATION_PLAN_v2.md  # 实施计划
```

## 核心叙事

**找得到、看得懂、能核验、敢上线** —— 不是"一次性检索框"，而是"长期陪伴的医学文献翻译官"。

## 核心功能

### 检索与理解
1. **多源医学证据检索** — 通过 KnowS AI 检索 6 类权威医学证据（英文论文/中文论文/临床指南/临床试验/医学会议/药品说明书）
2. **智能查询处理** — 意图识别（8 类）+ 查询重写 + 逐题追问，帮助非专业用户表达清楚"他到底想问什么"
3. **四级风险路由** — 低/中/高/禁止四级风险分类与分流，急症自动提升风险等级并注入就医提示

### 解释与核验
4. **通俗化引擎** — 将专业医学文献转化为日常中文，让患者"看得懂"
5. **三层结构化输出** — 核心回答 + 证据卡片 + 患者通俗解释，信息递进不吓人
6. **可核验** — 每条回答可追溯到具体文献（PMID/DOI/NCT），研究进展标注研究阶段与不确定性

### 陪伴（差异化能力）
7. **就医准备包** 🏆 — "该问医生什么 / 该说什么 / 该查什么 / 该确认什么"四类沟通清单，可勾选、可复制、可打印
8. **情绪感知陪伴** — 感知患者焦虑/恐慌/紧迫情绪，小光吉祥物+暖场白对话气泡，先安抚再回答
9. **研究雷达** — 订阅疾病关键词，自动追踪最新研究进展，站内消息推送，标注研究阶段与不确定性
10. **临床试验推荐** — 自动匹配相关招募中试验，展示入组标准/地点/注意事项

## 技术栈

- **后端**：Python FastAPI（端口 8000），单容器同时托管前端 dist
- **前端**：React + TypeScript + Vite（端口 3000）
- **LLM**：硅基流动 SiliconFlow（默认 Qwen2.5-7B）
- **检索**：KnowS AI 结构化医学证据 API（6 类源）
- **部署**：Dockerfile + docker-compose.yml + 一键启动脚本（bat/ps1/sh）
- **评测**：L1/L2/L3 评测数据集 + 自动化脚本

## License

MIT
