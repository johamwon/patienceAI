# 医语桥

面向患者的循证医学检索与通俗化解释 Agent

## ModelScope 展示说明

### 1. 项目简介与医疗场景

- **一句话描述**：医语桥是一个面向患者和家属的循证医学检索与通俗化解释 Agent，帮助用户检索医学证据、理解专业文献，并生成就医沟通准备。
- **解决的痛点**：患者常常看不懂医学文献、检查报告和新药/新疗法信息，也难以判断网上医疗信息是否可靠；同时，医生门诊时间有限，患者缺少结构化的问题清单和沟通准备。
- **目标受众**：患者、患者家属、医学科普工作者，以及需要快速理解医学证据的医生助理和医学研究人员。

### 2. 功能特性

- 支持多源医学证据检索，覆盖英文论文、中文论文、临床指南、临床试验、医学会议和药品说明书等来源。
- 支持智能查询重写与意图识别，将患者自然语言问题转化为更适合医学检索的关键词。
- 支持逐题追问，在问题信息不足时先追问分期、用药、治疗目标等关键信息，再生成答案。
- 支持三层结构化输出：一句话核心回答、证据卡片、患者通俗解释。
- 支持研究阶段标注，对临床试验、早期研究、临床前研究等进行不确定性提示。
- 支持就医准备包，自动生成“该问医生什么、该主动告知什么、该索取哪些检查、该确认哪些治疗选项”。
- 支持情绪感知与风险提示，对焦虑、恐慌、急症倾向等场景进行分流和安全提示。
- 支持研究雷达订阅，持续关注特定疾病关键词的新研究进展。

### 3. 魔搭社区运行/部署指南

- **魔搭展示链接**：[https://modelscope.cn/studios/johamwon/patienceai](https://modelscope.cn/studios/johamwon/patienceai)
- **在线体验链接**：[https://johamwon-patienceai.ms.show](https://johamwon-patienceai.ms.show)

本地运行步骤：

```bash
# 1. 安装后端依赖
pip install -r backend/requirements.txt

# 2. 安装前端依赖并构建
cd frontend
npm install
npm run build
cd ..

# 3. 配置环境变量
# 参考 .env.example，至少配置 LLM_API_KEY
# 如需完整医学检索能力，配置 KNOWS_API_KEY

# 4. 启动后端服务
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

也可以使用项目内置脚本：

```powershell
.\start.ps1
```

### 4. 演示与输入输出示例

- **输入示例**：

```text
朋友父亲得了阿尔兹海默症，有没有最新的治疗方案？
```

- **系统追问示例**：

```text
1. 目前诊断处于轻度、中度还是重度？是否还属于轻度认知障碍阶段？
2. 现在是否正在使用多奈哌齐、美金刚、仑卡奈单抗等药物？
3. 你更想了解已获批治疗、临床试验机会，还是日常照护和就医沟通？
```

- **预期输出**：

```text
系统会结合用户补充信息，优先检索最新指南、临床试验、医学会议和近年论文，
生成面向患者家属的通俗解释，并说明：
- 当前公开证据支持哪些治疗方向
- 哪些属于已获批治疗，哪些仍处于研究或试验阶段
- 与医生沟通时应重点确认哪些问题
- 哪些情况需要及时就医
```

API 请求示例：

```bash
curl -X POST https://johamwon-patienceai.ms.show/api/v1/clarify \
  -H "Content-Type: application/json" \
  -d '{"query":"朋友父亲得了阿尔兹海默症，有没有最新的治疗方案"}'
```

### 5. 局限性与未来规划

- 目前版本不提供诊断、处方、剂量调整或个体化治疗决策，所有内容仅用于医学信息理解和就医沟通准备。
- 检索质量依赖外部医学证据源和 API 可用性，部分疾病或非常新的研究可能存在覆盖不足。
- 对复杂病例的理解仍依赖用户补充的信息，若缺少分期、病理、既往治疗、检查结果等，回答只能保持在一般信息层面。
- 研究进展类内容需要持续更新和核验，不能将早期研究直接理解为已经确立的临床疗效。

未来规划：

- 增强对肿瘤、罕见病、神经退行性疾病等重点疾病的专病问答能力。
- 增加更多权威数据源和指南数据库支持。
- 优化研究雷达，提供更稳定的新进展追踪和摘要推送。
- 增加医生端视图，帮助医生快速了解患者关注点和沟通需求。
- 完善评测体系，持续评估事实一致性、引用准确性、可读性和安全合规性。

### 6. 团队与致谢

- **项目负责人**：负责产品设计、医疗场景定义、功能规划与整体交付。
- **后端开发**：负责 FastAPI 服务、医学检索、查询重写、证据重排、缓存和研究雷达。
- **前端开发**：负责 React + TypeScript 前端、交互流程、逐题追问、解释结果展示和就医准备包界面。
- **AI/算法设计**：负责通俗化解释、多智能体回答生成、情绪识别、风险分流和合规约束。

致谢：

- 感谢 FastAPI、React、Vite、Pydantic 等开源项目。
- 感谢医学文献检索与大语言模型相关生态提供的基础能力。
- 感谢魔搭社区 ModelScope 提供创空间部署与在线展示环境。

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
