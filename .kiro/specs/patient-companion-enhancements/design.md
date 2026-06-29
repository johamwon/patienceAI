# Design Document

## Overview

本设计在"患癌知光"现有架构（FastAPI 后端 + React/TS 前端 + KnowS AI 检索 + 多智能体 Simplification Loop）之上，新增三组能力：

1. **就医准备包（Visit Prep Pack）**——独立端点 `/api/v1/visit-prep`，基于查询+证据+情绪生成结构化医患沟通清单，前端可勾选/打印，并可嵌入解释结果视图。
2. **罕见病/重症研究进展**——意图分类新增 `rare_disease`/`severe_condition` 标记，检索路由升级（优先 trial+meeting+paper_en、按时间降序、保留指南交叉佐证），新增临床试验卡片与研究阶段标注。
3. **拟人化情绪陪伴**——统一人格"小光"、情绪感知层（规则+LLM 混合）、陪伴暖场白、轻量会话记忆、前端吉祥物情绪联动。

### 设计目标与原则

- **最小侵入、复用现有模式**：沿用现有 `Pydantic schema + service 单例 + APIRouter` 后端模式，和 `组件 + types + api/index.ts` 前端模式。新增能力以新模块为主，对现有 `explain.py` / `intent_classifier.py` / `search.py` 做增量修改。
- **诚实-希望张力的代码化**：把"冲突时不确定性优先"从口号变成可执行约束——通过①集中式人格/合规提示词常量、②生成后的合规校验函数（`compliance_guard`）、③免责声明与风险提示的强制注入点，三道闸门保证。
- **降级永不阻塞主流程**：所有新增 LLM 调用都有规则回退；情绪识别、陪伴话语、就医准备包任一失败都不应让 `/explain` 主流程崩溃，而是退化到"无情绪/无陪伴/通用包"的安全态。

### 三个开放问题的设计决策

| 开放问题 | 决策 | 理由 |
|---|---|---|
| OQ1 会话记忆持久化 | MVP 进程内存；定义 `SessionStore` 抽象基类，内存实现 `InMemorySessionStore`，预留 `RedisSessionStore` 扩展点 | 重启即失忆对 MVP 可接受；抽象层让未来替换零成本，且隔离患者数据持久化的合规评估 |
| OQ2 就医准备包形态 | 独立端点 `/api/v1/visit-prep`（可单独触发+缓存）+ 前端在解释结果视图内嵌入展示 | 端点独立便于复用/缓存/单测；嵌入展示降低患者操作成本，二者不矛盾 |
| OQ3 罕见病病种范围 | 窄切口打深井：词表聚焦少数代表病种（SMA、ALS/渐冻症、DMD 等罕见病）+ 高发重症癌种（胶质母细胞瘤、胰腺癌等） | 深度做透优于宽而浅；词表可配置，后续可扩展 |

## Architecture

### 数据流（增强后）

```
                         患者查询 (query, session_id?)
                                  │
                                  ▼
         ┌────────────────────────────────────────────────┐
         │          请求预处理 (explain.py / visit_prep.py) │
         └────────────────────────────────────────────────┘
                                  │
         ┌────────────────┬───────┴────────┬────────────────┐
         ▼                ▼                ▼                ▼
   Intent_Classifier  Emotion_Detector  Session_Memory   (缓存查找)
   intent/risk/       emotion_state     最近 N 轮上下文
   rare/severe flags  (规则+LLM)
         │                │                │
         └────────┬───────┴────────────────┘
                  ▼
         ┌────────────────────────┐
         │   Search_Router         │  rare/severe → [trial, meeting, paper_en]
         │   (search.py)           │  + 至少一类 guide；按 publish_date 降序
         └────────────────────────┘
                  │  evidences[]
                  ▼
         ┌────────────────────────────────────────────────┐
         │      生成层（注入 Persona 人格 + 上下文）         │
         │  ┌──────────────┐ ┌──────────────┐ ┌──────────┐ │
         │  │Simplification│ │Companion     │ │VisitPrep │ │
         │  │Loop(三层输出)│ │Engine(暖场白)│ │Generator │ │
         │  └──────────────┘ └──────────────┘ └──────────┘ │
         │         研究进展 Research_Stage 标注              │
         └────────────────────────────────────────────────┘
                  │
                  ▼
         ┌────────────────────────┐
         │  compliance_guard 合规闸 │  剥离诊断/处方语句；强制保留免责+风险提示
         └────────────────────────┘
                  │  ExplainResponse / VisitPrepResponse
                  ▼
         ┌────────────────────────────────────────────────┐
         │  前端：Mascot(情绪联动) · ExplanationView ·       │
         │        CompanionBanner · VisitPrepView · TrialCard│
         └────────────────────────────────────────────────┘
```

### 模块清单

| 类型 | 文件 | 说明 |
|---|---|---|
| 新增 | `agents/prompts/persona.py` | 集中式人格"小光"定义 + 全局合规约束提示词 |
| 新增 | `backend/app/services/emotion_detector.py` | 情绪感知层（规则+LLM 混合） |
| 新增 | `backend/app/services/session_memory.py` | 会话记忆抽象 + 内存实现 |
| 新增 | `backend/app/services/companion_engine.py` | 陪伴暖场白生成 + 人格注入 + 合规闸门 |
| 新增 | `agents/core/visit_prep_generator.py` | 就医准备包生成器 |
| 新增 | `backend/app/api/visit_prep.py` | `/api/v1/visit-prep` 路由 |
| 新增 | `backend/app/services/research_stage.py` | 研究阶段标注 + NCT 校验工具 |
| 修改 | `backend/app/services/intent_classifier.py` | 增加 rare_disease/severe_condition 标记 |
| 修改 | `backend/app/api/search.py` | 检索路由升级（罕见病/重症策略） |
| 修改 | `backend/app/models/schemas.py` | 新增数据模型 |
| 修改 | `backend/app/api/explain.py` | 编排：情绪+陪伴+会话+研究阶段 |
| 修改 | `backend/app/main.py` | 注册 visit_prep 路由 |
| 新增 | `frontend/src/components/CompanionBanner.tsx` | 暖场白展示条 |
| 新增 | `frontend/src/components/VisitPrepView.tsx` | 就医准备包（可勾选+可打印） |
| 新增 | `frontend/src/components/TrialCard.tsx` | 临床试验卡片 |
| 修改 | `frontend/src/components/Mascot.tsx` | 情绪状态联动表情/气泡 |
| 修改 | `frontend/src/components/ExplanationView.tsx` | 集成暖场白 + 研究阶段标签 + 嵌入准备包入口 |
| 修改 | `frontend/src/pages/SearchPage.tsx` | 传递 emotion_state / session_id；触发就医准备包 |
| 修改 | `frontend/src/api/index.ts` + `types/index.ts` | 新增 API 调用与类型 |

## Components and Interfaces

### 1. Persona 与全局合规（`agents/prompts/persona.py`）— R1, R13

集中定义，所有面向患者的生成环节复用：

```python
PERSONA_NAME = "小光"

PERSONA_PROMPT = """\
你是"小光"，患癌知光的陪伴助手。你的人格特征：
- 温柔：用平实、有温度的语言，像一个懂医学的朋友。
- 诚实：只说证据支持的话；不确定就说不确定；坏消息不掩盖、不美化。
- 不端着：不堆砌术语，不居高临下。
你不是医生，不做诊断，不开处方，不替代就医。"""

# 全局合规约束 —— 注入所有患者可见生成；冲突时不确定性优先
COMPLIANCE_CONSTRAINTS = """\
硬性约束（违反即不合格）：
1. 不得给出诊断结论（如"你患了X""这就是癌症复发"）。
2. 不得给出处方、剂量、用药增减的个体化指令。
3. 不得把群体研究证据表述为对该患者个体的建议。
4. 当温暖表达与证据的不确定性冲突时，优先如实陈述不确定性与风险。
5. 早期/动物实验阶段研究不得表述为已确立的临床获益。"""

def with_persona(task_prompt: str, include_compliance: bool = True) -> str:
    """把人格与合规约束拼接到任务提示词前。"""
```

合规校验函数（生成后兜底，R13.1/13.2）：

```python
# 诊断/处方类禁用模式（正则），命中则触发改写或剥离
DIAGNOSIS_PATTERNS = [r"你(患|得)了", r"确诊为", r"建议你服用", r"每[日天].*(mg|毫克|片)"]

def compliance_guard(text: str) -> tuple[str, list[str]]:
    """返回 (清洗后文本, 命中的违规项列表)。命中诊断/处方语句时做安全替换。"""
```

### 2. Emotion_Detector（`emotion_detector.py`）— R2

```python
class EmotionState(str, Enum):
    PANIC = "panic"          # 恐慌
    ANXIETY = "anxiety"      # 焦虑
    DESPAIR = "despair"      # 绝望
    URGENT = "urgent"        # 急症倾向
    CALM = "calm"            # 平静求知（默认）

# 规则词表（粗筛）
EMOTION_KEYWORDS = {
    EmotionState.URGENT: ["快死了", "喘不过气", "大出血", "晕倒", "救命", "急"],
    EmotionState.PANIC:  ["好怕", "吓死", "怎么办啊", "崩溃", "扛不住"],
    EmotionState.DESPAIR:["没救了", "不想活", "放弃", "绝望", "等死"],
    EmotionState.ANXIETY:["担心", "焦虑", "睡不着", "是不是很严重", "会不会"],
}

def detect_emotion(query: str, llm_client=None) -> EmotionState:
    """
    混合策略：
    1. URGENT/DESPAIR 等高危情绪先用规则命中（保证不漏，R2.4）。
    2. 其余调用 LLM 精判强度（with_persona 提示词，要求只输出枚举值）。
    3. LLM 不可用/失败 → 回退规则结果（R2.3）。
    4. 全不命中 → CALM（R2.6）。
    """
```

- **R2.4 急症联动**：`detect_emotion` 返回 `URGENT` 时，`explain.py` 强制把 `risk_level` 提升至至少 `high` 并注入就医提示（与现有 high/prohibited 路由合流）。
- LLM 调用走现有 `llm_client.chat`，`temperature=0.0`，强约束"仅输出五个枚举之一"，解析失败按 R2.3 回退。

### 3. Session_Memory（`session_memory.py`）— R4

```python
@dataclass
class SessionTurn:
    query: str
    emotion: str
    timestamp: str

class SessionStore(ABC):                       # 抽象层，预留 Redis（OQ1）
    @abstractmethod
    def append(self, session_id: str, turn: SessionTurn) -> None: ...
    @abstractmethod
    def recent(self, session_id: str, n: int) -> list[SessionTurn]: ...

class InMemorySessionStore(SessionStore):
    """dict[session_id -> deque(maxlen=N)]，线程锁保护；重启清空（R4.5）。"""

SESSION_MAX_TURNS = int(os.getenv("SESSION_MAX_TURNS", "5"))   # R4.2 可配置
session_store = InMemorySessionStore()
```

- `deque(maxlen=N)` 天然满足 R4.6（超过 N 轮丢弃最早）。
- 无 `session_id` → 不读不写，主流程照常（R4.4）。

### 4. Companion_Engine（`companion_engine.py`）— R1, R3, R13

```python
async def generate_companion_message(
    query: str,
    emotion: EmotionState,
    evidences: list[dict],
    risk_level: str,
    risk_message: str | None,
    history: list[SessionTurn],
    llm_client,
) -> str:
    """
    生成暖场白：
    - 根据 emotion 选择基调（R3.2），但无论何种情绪都先共情（R3.3）。
    - 证据含负面结论时：先共情 → 照实陈述 → 给可执行出口（R3.3/3.4）。
    - risk_level in {high, prohibited}：必须含就医引导（R3.7/R13.5）。
    - 经 compliance_guard 清洗（R3.5/R13.1）。
    - LLM 失败 → 返回按 emotion 预置的安全模板（保证主流程不崩）。
    """
```

预置安全模板（LLM 失败回退）：每个 `EmotionState` 一段中性共情话术，high/prohibited 额外拼接就医提示。

### 5. Visit_Prep_Generator（`visit_prep_generator.py`）+ 路由（`visit_prep.py`）— R6, R7, R8, R13

```python
async def generate_visit_prep(
    query: str, evidences: list[dict], emotion: EmotionState, llm_client,
) -> dict:
    """
    产出 VisitPrepPack 四类条目。
    - 有证据：基于证据生成针对性问题（R7.2）。
    - 无证据：生成通用就医准备问题，标记 evidence_based=False（R7.5）。
    - 每条经 compliance_guard，剥离诊断/剂量（R6.4/R13.1）。
    - 失败 → 抛异常，路由层转 5xx（R7.6）。
    """
```

路由复用现有 `cache_service`（R7.3/7.4）：

```python
@router.post("/visit-prep", response_model=VisitPrepResponse)
async def visit_prep(req: VisitPrepRequest):
    cached = cache_service.get(f"visitprep::{req.query}")   # 命名空间前缀避免与 explain 缓存冲突
    if cached: return VisitPrepResponse(**cached)
    parsed = parse_query(req.query)
    emotion = detect_emotion(req.query, llm_client)
    evidences = knows_client.search_multi(...) or demo fallback
    pack = await generate_visit_prep(req.query, evidences, emotion, llm_client)
    resp = VisitPrepResponse(visit_prep_pack=pack, evidence_based=bool(evidences), ...)
    cache_service.set(f"visitprep::{req.query}", resp.model_dump())
    return resp
```

> 缓存键加 `visitprep::` 前缀：现有 `cache_service._make_key` 对 query 取 hash，加前缀确保就医准备包与 explain 结果不互相覆盖。

### 6. Research_Stage 标注 + NCT 校验（`research_stage.py`）— R11, R12

```python
class ResearchStage(str, Enum):
    BREAKTHROUGH_RCT = "breakthrough_rct"   # 突破性 RCT 证据
    EARLY_TRIAL = "early_trial"             # 早期临床试验
    PRECLINICAL = "preclinical"             # 动物实验/临床前

def infer_research_stage(evidence: dict) -> ResearchStage:
    """基于 source_type/evidence_level/标题关键词（如 'phase I', '小鼠', 'in vitro'）推断阶段。"""

NCT_PATTERN = re.compile(r"^NCT\d{8}$")

def validate_nct(evidence: dict) -> bool:
    """R11.2：校验 nct_id 格式且与证据来源一致，不一致不渲染。"""
```

- R12.3：`EARLY_TRIAL`/`PRECLINICAL` 阶段的进展，在通俗化输出与卡片中显式拼接"该结果尚未在患者身上证实有效"。
- 阶段标签 + evidence_level 一并下发前端（R12.2）。

### 7. Intent_Classifier 升级（`intent_classifier.py`）— R9

```python
RARE_DISEASE_KEYWORDS = ["sma", "脊髓性肌萎缩", "渐冻症", "als", "肌萎缩侧索硬化",
                         "dmd", "杜氏肌营养不良", "戈谢病", "法布雷", "血友病", ...]
SEVERE_CONDITION_KEYWORDS = ["胶质母细胞瘤", "胰腺癌", "晚期", "转移", "复发",
                             "iv期", "终末期", "白血病", ...]

def detect_rare_disease(query: str) -> bool: ...      # R9.2；匹配失败/不确定 → False (R9.4)
def detect_severe_condition(query: str) -> bool: ...  # R9.3

# parse_query 返回值新增 rare_disease / severe_condition 两个布尔字段（R9.1）
# risk_level 判定逻辑保持独立不变（R9.6）
```

### 8. Search_Router 升级（`search.py`）— R10

```python
def select_sources(parsed: dict) -> list[str]:
    if parsed["rare_disease"] or parsed["severe_condition"]:
        # R10.1 优先前沿源 + R10.3 至少一类 guide 交叉佐证
        return ["trial", "meeting", "paper_en", "guide"]
    return INTENT_TO_SOURCES.get(parsed["intent"], DEFAULT_SOURCES)

def sort_evidences(evidences, parsed) -> list:
    if parsed["rare_disease"] or parsed["severe_condition"]:
        # R10.2 按 publish_date 降序（最新在前）
        return sorted(evidences, key=lambda e: e.get("publish_date") or "", reverse=True)
    return evidences   # 默认保留现有来源优先级排序

# R10.4：专门源无结果 → 回退默认源集合
```

## Data Models

### 后端 Pydantic（`schemas.py` 新增/修改）

```python
class EmotionState(str, Enum):
    PANIC="panic"; ANXIETY="anxiety"; DESPAIR="despair"; URGENT="urgent"; CALM="calm"

class TrialCard(BaseModel):              # R11
    nct_id: str
    recruitment_status: str = "信息未提供"
    phase: str = "信息未提供"
    eligibility: str = "信息未提供"
    location: str = "信息未提供"
    note: str = "是否符合入组需经临床医生评估确认。"  # R11.5

class ResearchProgress(BaseModel):       # R12
    summary: str
    research_stage: Literal["breakthrough_rct","early_trial","preclinical"]
    evidence_level: str
    uncertainty_note: str | None = None  # 早期/临床前阶段必填（R12.3）
    source_id: str | None = None

class VisitPrepPack(BaseModel):          # R6
    questions_for_doctor: list[str]
    info_to_tell_doctor: list[str]
    tests_to_request: list[str]
    treatment_options_to_confirm: list[str]
    positioning_note: str = "本清单用于辅助你和医生沟通，最终诊疗以医生判断为准。"

class VisitPrepRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None

class VisitPrepResponse(BaseModel):
    visit_prep_pack: VisitPrepPack
    evidence_based: bool = True          # R7.5
    note: str | None = None

# ExplainRequest 增量：session_id（R4）
# ExplainResponse 增量：
#   companion_message: str | None        (R3)
#   emotion_state: str = "calm"          (R2.5)
#   trial_cards: list[TrialCard] = []    (R11)
#   research_progress: list[ResearchProgress] = []  (R12)
```

### 前端 TypeScript（`types/index.ts`）

```typescript
export type EmotionState = "panic" | "anxiety" | "despair" | "urgent" | "calm";

export type TrialCard = {
  nct_id: string; recruitment_status: string; phase: string;
  eligibility: string; location: string; note: string;
};
export type ResearchProgress = {
  summary: string;
  research_stage: "breakthrough_rct" | "early_trial" | "preclinical";
  evidence_level: string; uncertainty_note?: string; source_id?: string;
};
export type VisitPrepPack = {
  questions_for_doctor: string[]; info_to_tell_doctor: string[];
  tests_to_request: string[]; treatment_options_to_confirm: string[];
  positioning_note: string;
};
// ExplainResponse 增量: companion_message?, emotion_state, trial_cards, research_progress
```

## Prompt Design

| 环节 | 提示词要点 | 关联需求 |
|---|---|---|
| 人格注入 | `with_persona()` 前缀拼接到所有患者可见生成 | R1.1/1.2 |
| 情绪判定 | 仅输出五枚举之一；temperature=0；高危情绪规则先行 | R2 |
| 陪伴暖场白 | 先共情→（如有坏消息）照实说→给出口；high/prohibited 含就医引导；禁诊断处方 | R3 |
| 就医准备包 | 四类条目；问句形式；禁诊断/剂量；无证据走通用模板 | R6/R7 |
| 研究希望表达 | 标注阶段；早期/临床前显式说"尚未在患者身上证实"；不确定性优先 | R12 |

所有生成后统一过 `compliance_guard`（R13）。

## Error Handling & Fallback

| 场景 | 处理 |
|---|---|
| 情绪 LLM 失败 | 回退规则结果（R2.3）；全不命中→CALM |
| 陪伴话语 LLM 失败 | 回退 emotion 预置安全模板（不阻塞 explain） |
| 就医准备包 LLM 失败 | 路由抛 5xx + 描述性错误（R7.6） |
| 无证据（explain/visit-prep） | explain 走现有 demo/空结果；visit-prep 生成通用包 evidence_based=False（R7.5） |
| 检索专门源无结果 | 回退默认源集合（R10.4） |
| NCT 校验失败 | 不渲染该 TrialCard（R11.2） |
| compliance_guard 命中违规 | 安全替换违规句；记录命中项 |
| 缓存 | visit-prep 复用 cache_service，键加 `visitprep::` 前缀（R7.3/7.4） |

## Compliance & "诚实-希望张力" 实现策略（R13）

三道闸门，逐层收口：

1. **入口闸**：`COMPLIANCE_CONSTRAINTS` 注入每个患者可见生成提示词，从源头约束模型（明确"冲突时不确定性优先"）。
2. **结构闸**：数据模型层面强制——`ResearchProgress.uncertainty_note` 对早期/临床前阶段必填；`VisitPrepPack.positioning_note`、`TrialCard.note`、`PatientExplanation.disclaimer` 为带默认值的常量字段，不依赖模型生成。
3. **出口闸**：`compliance_guard` 正则兜底剥离诊断/处方语句；`explain.py` 在汇总响应时，若 `risk_level in {high, prohibited}` 强制保留 `risk_message` 且不被 `companion_message` 替代（R13.5）。

## Testing Strategy

优先对**纯逻辑、可确定性验证**的部分做单元/属性测试（不依赖真实 LLM/网络）：

| 测试对象 | 类型 | 关键用例 |
|---|---|---|
| `detect_emotion` 规则回退 | 单元 | URGENT/DESPAIR 关键词必命中；LLM=None 时走规则；空输入→CALM（R2.3/2.6） |
| `InMemorySessionStore` | 属性 | 任意追加序列后 `recent(n)` 长度≤N 且为最近 N 条、顺序正确（R4.2/4.6） |
| `validate_nct` | 单元 | 合法 NCT 通过；格式错/不一致拒绝（R11.2） |
| `infer_research_stage` | 单元 | phase I→early_trial；小鼠/in vitro→preclinical（R12.1） |
| `compliance_guard` | 单元 | 诊断/剂量句被剥离/替换；正常句不误伤（R13.1） |
| `select_sources`/`sort_evidences` | 单元 | rare/severe→含 trial+guide；按 publish_date 降序；空→回退（R10） |
| `cache` 命中（visit-prep） | 单元 | 同 query 第二次走缓存；前缀隔离不污染 explain（R7.3/7.4） |
| `detect_rare_disease`/`detect_severe_condition` | 单元 | 命中词表→True；无关→False（R9.2/9.3/9.4） |

LLM 相关生成（暖场白、准备包内容、研究希望文案）以**契约测试**为主：mock `llm_client` 返回固定文本，验证编排顺序、回退路径、合规闸调用，而非验证生成质量（生成质量由演示与人工抽检覆盖）。

测试框架：后端用 `pytest`（现有 requirements.txt 未含，需补充 `pytest` 到依赖），属性测试用 `hypothesis`。前端组件以手动/演示验证为主，MVP 不强制引入前端测试框架。
