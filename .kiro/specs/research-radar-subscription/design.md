# Design Document

## Overview

研究雷达订阅（Research Radar Subscription）让"医语桥"从一次性检索工具升级为长期陪伴者：用户在 explain 获得某病症解释后，小光主动邀约订阅；用户显式同意后，系统每日巡检该病症新证据，出现高质量新进展时生成通俗化摘要并按已授权渠道推送。

本设计在现有架构（FastAPI + React/TS + KnowS + LLM + SimplificationLoop + compliance_guard + research_stage）之上新增一个独立的 Radar 子系统，**最大化复用现有通俗化与合规能力**，并把需求中的"陪伴价值 vs 敏感信息保护"张力落成可执行的**生克隔离**存储架构。

### 三个开放问题的设计决策

| 开放问题 | 决策 | 理由 |
|---|---|---|
| OQ1 存储选型 | **SQLite（标准库 sqlite3），两个物理隔离的 .db 文件** | 零外部依赖；两库分文件天然满足"物理隔离/分别删除/删除一方不依赖另一方"；沿用 session_memory 的抽象基类模式，未来可换 Redis |
| OQ2 微信渠道 | **预留接口，MVP 只实现站内+邮件**；WeChatChannel 占位（不可用时降级跳过），演示态可模拟 | 真实微信推送需公众号资质+openid 绑定，当前环境无法跑通；用统一 DeliveryChannel 抽象隔离，后续接入零改动上层 |
| OQ3 巡检频率/阈值 | 默认每日一次；新进展阈值 = (evidence_level ∈ {high, moderate} 或 source_type ∈ {guide, trial, meeting}) 且 发表时间在近 `RADAR_FRESH_DAYS`(默认30) 天内。全部环境变量可配 | 平衡召回与噪声；参数化便于调优与测试 |

### 设计原则

- **生克隔离（核心合规）**：`Subscription_Store`（订阅.db，零 PII）与 `Contact_Store`（联系方式.db，加密 PII）分文件、无外键、无交叉索引。任一库单独存在都无法推出"某邮箱订阅了什么病"。
- **复用而非重写**：Push_Digest 复用 `SimplificationLoop` + `research_stage` + `compliance_guard`；巡检检索复用 `knows_client`；后台调度复用 `cache_service` 的 daemon 线程模式。
- **降级永不阻塞**：单订阅巡检失败不中断整体；单渠道投递失败不影响其他渠道；微信不可用自动降级。
- **隐私优先**：冲突时以最小化 + 用户可控（同意/撤回/删除）优先。

## Architecture

### 数据流

```
            explain 完成
                │  (病症关键词 + anon_user_id)
                ▼
      ┌───────────────────────┐   用户显式同意
      │  订阅邀约(小光询问)     │──────────────┐
      └───────────────────────┘              ▼
                                   POST /api/v1/radar/subscribe
                                              │
                                              ▼
                                   ┌──────────────────────┐
                                   │  Subscription_Store   │  subscriptions.db（零 PII）
                                   │  anon_user_id + 病症   │
                                   └──────────────────────┘

  每日巡检（daemon 线程，参考 cache_service.start_background_refresh）
                │  遍历活跃 Subscription
                ▼
      knows_client.search_multi_queries(病症关键词)   ← 并行检索
                │  evidences[]
                ▼
      新进展判定（质量+新鲜度阈值）→ Progress_Fingerprint 去重(比对 Delivered_Log)
                │  new_progress[]（未推过的）
                ▼
      Push_Digest 生成：SimplificationLoop 通俗化 + research_stage 阶段标注
                        + compliance_guard 合规清洗
                │
                ▼
      投递编排：遍历该用户已授权渠道
        ├─ InAppChannel   → 站内消息表(anon_user_id, 不碰 Contact_Store)
        ├─ EmailChannel   → 从 Contact_Store 读 email（仅本次用）→ 发信
        └─ WeChatChannel  → 占位/降级（演示态可模拟）
                │
                ▼
      写 Delivered_Log(fingerprint) → 下次不重复推送
```

### 模块清单

| 类型 | 文件 | 说明 |
|---|---|---|
| 新增 | `backend/app/services/radar/subscription_store.py` | 订阅库抽象基类 + SQLite 实现（零 PII） |
| 新增 | `backend/app/services/radar/contact_store.py` | 联系方式库（隔离 .db + 加密） |
| 新增 | `backend/app/services/radar/inapp_store.py` | 站内消息存储（零 PII） |
| 新增 | `backend/app/services/radar/fingerprint.py` | Progress_Fingerprint 计算 + 新进展判定（纯函数） |
| 新增 | `backend/app/services/radar/delivery/base.py` | DeliveryChannel 抽象 |
| 新增 | `backend/app/services/radar/delivery/in_app.py` | 站内渠道 |
| 新增 | `backend/app/services/radar/delivery/email.py` | 邮件渠道 |
| 新增 | `backend/app/services/radar/delivery/wechat.py` | 微信渠道占位 |
| 新增 | `backend/app/services/radar/radar_service.py` | 订阅生命周期 + 巡检编排 + 投递编排 + 演示态 |
| 新增 | `backend/app/services/radar/patrol.py` | 每日巡检 daemon 线程（start_daily_patrol） |
| 新增 | `backend/app/services/radar/digest_generator.py` | Push_Digest 生成（复用 SimplificationLoop/research_stage/compliance_guard） |
| 新增 | `backend/app/api/radar.py` | Radar API 路由 |
| 修改 | `backend/app/main.py` | 注册 radar 路由 + 启动巡检线程 |
| 修改 | `backend/app/models/schemas.py` | 新增 Radar 相关 Pydantic 模型 |
| 修改 | `backend/app/api/explain.py` | explain 响应增加订阅邀约字段 |
| 新增 | `frontend/src/components/SubscribePrompt.tsx` | 小光订阅邀约 |
| 新增 | `frontend/src/components/SubscriptionManager.tsx` | 订阅管理页（查看/撤销/删除/渠道开关） |
| 新增 | `frontend/src/components/MessageCenter.tsx` | 站内消息中心（展示 Push_Digest） |
| 修改 | `frontend/src/components/ExplanationView.tsx` | 集成订阅邀约入口 |
| 修改 | `frontend/src/pages/SearchPage.tsx` | anon_user_id 管理 + 演示态触发 |
| 修改 | `frontend/src/api/index.ts` + `types/index.ts` | Radar API 调用与类型 |

## Storage Design（生克隔离）

两个独立 SQLite 文件，**无跨库外键、无联合查询**：

### subscriptions.db（零 PII，R1.7/R10.1/R11.5）
```sql
CREATE TABLE subscriptions (
    id            TEXT PRIMARY KEY,        -- uuid4
    anon_user_id  TEXT NOT NULL,           -- 匿名标识，非实名
    disease_keyword TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',  -- active | revoked
    created_at    TEXT NOT NULL,
    UNIQUE(anon_user_id, disease_keyword)  -- R1.6 幂等
);
CREATE TABLE delivered_log (              -- 去重（R5.3/R5.4）
    subscription_id TEXT NOT NULL,
    fingerprint     TEXT NOT NULL,
    delivered_at    TEXT NOT NULL,
    PRIMARY KEY (subscription_id, fingerprint)
);
CREATE TABLE channel_consent (            -- 渠道授权（只记开关，不存联系方式）
    anon_user_id TEXT NOT NULL,
    channel      TEXT NOT NULL,           -- in_app | email | wechat
    consented_at TEXT NOT NULL,
    PRIMARY KEY (anon_user_id, channel)
);
CREATE TABLE inapp_messages (             -- 站内消息（零 PII）
    id           TEXT PRIMARY KEY,
    anon_user_id TEXT NOT NULL,
    digest_json  TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    read         INTEGER NOT NULL DEFAULT 0
);
```

### contacts.db（隔离 + 加密，R3.5/R10.2/R11.6）
```sql
CREATE TABLE contacts (
    anon_user_id     TEXT NOT NULL,
    channel          TEXT NOT NULL,       -- email | wechat
    encrypted_value  TEXT NOT NULL,       -- 加密后的 email / openid
    consented_at     TEXT NOT NULL,
    PRIMARY KEY (anon_user_id, channel)
);
```

- **隔离**：两库是不同文件、不同连接，代码层面禁止任何 JOIN/跨库查询（R10.6/R11.6）。`channel_consent`（在订阅库，只记"开了哪个渠道"的布尔事实）与 `contacts`（在联系方式库，存加密值）分离——即便拿到订阅库也只知道"该匿名用户开了邮件渠道"，拿不到邮箱；拿到联系方式库也不知道该邮箱订阅了什么病。
- **加密**：`encrypted_value` 用对称加密。MVP 用标准库实现的简单方案（如基于 `RADAR_SECRET_KEY` 环境变量的 Fernet 风格；若不引入 cryptography 依赖，则用 hashlib+hmac 派生密钥 + base64 存储的可逆方案并在文档标注为 MVP 级）。**推荐引入 `cryptography` 库用 Fernet**（对称加密，成熟）；作为设计决策列出，实现任务确认依赖。
- **可删除（R8.4/8.5/8.6/R10.3/10.4）**：按 anon_user_id 分别 DELETE，两库独立，删一方不依赖另一方可用。保留期用 `created_at + RADAR_RETENTION_DAYS` 定期清理。

### 存储抽象（沿用 session_memory 模式）
```python
class SubscriptionStore(ABC):          # 便于未来换 Redis
    @abstractmethod
    def create(self, anon_user_id, disease_keyword) -> Subscription: ...
    @abstractmethod
    def list_active(self, anon_user_id) -> list[Subscription]: ...
    @abstractmethod
    def list_all_active(self) -> list[Subscription]: ...   # 巡检用
    @abstractmethod
    def revoke(self, sub_id) -> None: ...
    @abstractmethod
    def delete(self, sub_id) -> None: ...
    @abstractmethod
    def is_delivered(self, sub_id, fingerprint) -> bool: ...
    @abstractmethod
    def mark_delivered(self, sub_id, fingerprint) -> None: ...

class SQLiteSubscriptionStore(SubscriptionStore): ...   # threading.Lock 保护
subscription_store = SQLiteSubscriptionStore()
```

## Components and Interfaces

### 1. 新进展判定与去重（`fingerprint.py`）— R5

```python
def progress_fingerprint(evidence: dict) -> str:
    """稳定去重键：优先 nct_id/doi/pmid；缺失时用 sha1(title|source_type|publish_date)。"""

RADAR_MIN_LEVELS = {"high", "moderate"}
RADAR_FRESH_SOURCES = {"guide", "trial", "meeting"}
RADAR_FRESH_DAYS = int(os.getenv("RADAR_FRESH_DAYS", "30"))

def is_new_progress(evidence: dict, now=None) -> bool:
    """质量阈值(evidence_level∈high/moderate 或 source_type∈guide/trial/meeting)
       且 新鲜度(publish_date 在近 RADAR_FRESH_DAYS 天内)。纯函数，便于单测。"""
```
- 去重：候选进展算 fingerprint → `subscription_store.is_delivered` 命中则跳过；推送后 `mark_delivered`。**幂等**：同一进展重复巡检不会重复推送。

### 2. Push_Digest 生成（`digest_generator.py`）— R6
```python
async def generate_push_digest(disease_keyword, new_evidences, llm_client) -> dict:
    """
    复用能力：
    - SimplificationLoop 生成通俗化摘要
    - research_stage.to_research_progress 标注 Research_Stage + Evidence_Level（R6.2）
    - 早期/临床前阶段附 uncertainty_note（R6.3）
    - compliance_guard 清洗，禁诊断/处方/个体化建议（R6.4/R6.5）
    - 冲突时不确定性优先（R6.6）
    返回 PushDigest dict：{disease_keyword, items:[{summary, research_stage,
      evidence_level, uncertainty_note, source_id}], generated_at, is_demo}
    """
```

### 3. 投递渠道抽象（`delivery/`）— R7
```python
class DeliveryChannel(ABC):
    name: str
    @abstractmethod
    def is_available(self) -> bool: ...
    @abstractmethod
    def deliver(self, anon_user_id: str, digest: dict) -> bool: ...

class InAppChannel:   # 写 inapp_messages 表，只用 anon_user_id，不碰 Contact_Store（R7.2）
class EmailChannel:   # 从 contact_store 读解密 email，仅本次投递用（R7.3）；SMTP 配置从 env
class WeChatChannel:  # is_available()→False（MVP），deliver 抛 NotImplemented/降级跳过（R3.7/OQ2）
```
- 投递编排：遍历用户 `channel_consent` 开启的渠道，逐个 `deliver`；单渠道异常捕获记录、继续其余（R7.4）；未授权渠道不投递（R7.5）。

### 4. Radar 服务（`radar_service.py`）
```python
class RadarService:
    def subscribe(anon_user_id, disease_keyword) -> Subscription   # R1（幂等 R1.6）
    def list_subscriptions(anon_user_id) -> list[Subscription]     # R8.1
    def revoke(sub_id); def delete(sub_id)                         # R8.3/8.4
    def set_channel(anon_user_id, channel, contact=None) -> None   # 开启渠道+存联系方式 R3
    def unset_channel(anon_user_id, channel) -> None               # 关闭+删联系方式 R8.5
    def delete_all(anon_user_id) -> None                           # R8.6 两库分别删
    async def run_patrol_once() -> PatrolReport                    # 巡检一轮（R4）
    async def process_subscription(sub, evidences=None)            # 单订阅：判定→去重→digest→投递
    async def inject_demo_progress(sub_id, fake_evidences)         # 演示态 R9
```

### 5. 每日巡检（`patrol.py`）— R4
- 参考 `cache_service.start_background_refresh` 的 daemon 线程：`start_daily_patrol()` 启动后台线程，按 `RADAR_PATROL_INTERVAL_HOURS`(默认24) 周期调用 `radar_service.run_patrol_once()`。
- `run_patrol_once`：`list_all_active()` 遍历；对每个订阅调 `knows_client.search_multi_queries` 检索；单订阅 try/except 隔离，失败记录并继续（R4.3），即便日志写入失败也继续（R4.3）。已撤销/删除的不巡检（R4.4，靠 status=active 过滤）。

### 6. explain 挂钩订阅邀约 — R1.1/R1.2
- `ExplainResponse` 增加 `subscription_offer`：`{disease_keyword: str, prompt_text: str} | None`。
- explain 编排末尾：从 parsed 的疾病主题（复用 visit_prep 的 `_extract_disease_topic` 或 query rewrite 的实体）提取 `disease_keyword`；生成邀约文案（小光口吻，经 compliance_guard）；填入响应。前端据此展示 SubscribePrompt。

## Data Models

### 后端 Pydantic（schemas.py 新增）
```python
class Subscription(BaseModel):
    id: str; anon_user_id: str; disease_keyword: str
    status: str = "active"; created_at: str

class SubscribeRequest(BaseModel):
    anon_user_id: str; disease_keyword: str = Field(min_length=1, max_length=100)

class ChannelSetRequest(BaseModel):
    anon_user_id: str
    channel: Literal["in_app", "email", "wechat"]
    contact: Optional[str] = None   # email/openid；in_app 时为空

class PushDigestItem(BaseModel):
    summary: str
    research_stage: Literal["breakthrough_rct","early_trial","preclinical"]
    evidence_level: str
    uncertainty_note: Optional[str] = None
    source_id: Optional[str] = None

class PushDigest(BaseModel):
    disease_keyword: str
    items: list[PushDigestItem]
    generated_at: str
    is_demo: bool = False

class InAppMessage(BaseModel):
    id: str; digest: PushDigest; created_at: str; read: bool = False

# ExplainResponse 增量：subscription_offer: Optional[SubscriptionOffer]
class SubscriptionOffer(BaseModel):
    disease_keyword: str
    prompt_text: str
```

### 前端 TypeScript（types/index.ts）
```typescript
export type Subscription = { id:string; disease_keyword:string; status:string; created_at:string };
export type PushDigestItem = { summary:string; research_stage:"breakthrough_rct"|"early_trial"|"preclinical"; evidence_level:string; uncertainty_note?:string; source_id?:string };
export type PushDigest = { disease_keyword:string; items:PushDigestItem[]; generated_at:string; is_demo:boolean };
export type InAppMessage = { id:string; digest:PushDigest; created_at:string; read:boolean };
// ExplainResponse 增量: subscription_offer?: { disease_keyword:string; prompt_text:string }
```

## API Endpoints（`radar.py`，prefix /api/v1/radar）

| 方法 | 路径 | 说明 | 需求 |
|---|---|---|---|
| POST | `/radar/subscribe` | 创建订阅（显式同意，幂等） | R1 |
| GET | `/radar/subscriptions?anon_user_id=` | 列出订阅 | R8.1 |
| POST | `/radar/subscriptions/{id}/revoke` | 撤销 | R8.3 |
| DELETE | `/radar/subscriptions/{id}` | 删除订阅+Delivered_Log | R8.4 |
| GET | `/radar/channels?anon_user_id=` | 渠道开启状态 | R8.2 |
| POST | `/radar/channels` | 开启渠道(+联系方式) | R3.3/3.4 |
| DELETE | `/radar/channels/{channel}?anon_user_id=` | 关闭渠道+删联系方式 | R8.5 |
| DELETE | `/radar/user/{anon_user_id}` | 删除全部数据（两库） | R8.6 |
| GET | `/radar/messages?anon_user_id=` | 拉取站内消息 | R7.2 |
| POST | `/radar/demo/trigger` | 演示态：注入模拟新进展（仅 Demo_Mode） | R9 |

匿名 user_id：前端首访生成 uuid 存 localStorage（与现有 session_id 类似），随请求带上。非实名（R2）。

## Compliance & 生克隔离 实现策略（R10/R11）

1. **核心库零 PII**：`subscription_store` 的写入接口在类型层面就不接受 email/openid；联系方式只经 `contact_store`。代码审查点：任何 subscriptions.db 的 INSERT 不含联系方式字段。
2. **两库不可交叉索引**：不同 .db 文件、不同连接对象，代码中禁止把两库数据在同一查询/JOIN 中关联；投递时先从订阅库拿 consent（开了哪些渠道），再单独去联系方式库按 (anon_user_id, channel) 取值。
3. **加密**：contacts.encrypted_value 加解密集中在 contact_store，密钥来自 `RADAR_SECRET_KEY`。
4. **显式同意 + 可撤回/删除**：subscribe 必须带用户操作触发；revoke/delete/unset_channel/delete_all 无前置条件随时可用（R8.7）。
5. **推送内容合规**：digest_generator 出口过 compliance_guard；早期/临床前必带 uncertainty_note；不确定性优先（R6/R11.7）。
6. **演示态标记**：Demo_Mode（env `RADAR_DEMO_MODE`）下 digest.is_demo=True，前端显式标"演示内容"；未启用则 `/radar/demo/trigger` 返回 404/403（R9.4）。

## Error Handling & Fallback

| 场景 | 处理 |
|---|---|
| 巡检中单订阅 KnowS 失败 | try/except 跳过该订阅，继续其余（R4.3） |
| 失败日志写入也失败 | 吞掉异常继续巡检（R4.3） |
| 单渠道投递失败 | 记录、继续其余渠道（R7.4） |
| 微信渠道不可用 | is_available()=False，跳过并降级（R3.7） |
| 无新进展 | 不生成 digest、不发任何通知（R5.5） |
| digest LLM 失败 | 复用 SimplificationLoop 现有 fallback；本轮无法生成则跳过该订阅本次推送（不崩） |
| contact 解密失败 | 记录、跳过该渠道，不影响站内 |

## Testing Strategy

优先对可确定性纯逻辑做单元/属性测试（不依赖真实 LLM/网络/SMTP）：

| 对象 | 类型 | 关键用例 |
|---|---|---|
| `progress_fingerprint` | 属性 | 同证据幂等同键；nct/doi/pmid 优先；缺失走标题指纹 |
| `is_new_progress` | 单元 | 高/中等级或指南/试验/会议通过；过旧(超N天)拒绝；低质量拒绝 |
| 去重幂等 | 单元 | 已 delivered 的 fingerprint 不再推；mark 后 is_delivered=True |
| 两库隔离 | 单元 | subscriptions.db 无联系方式；delete_all 分别删两库；删一库不影响另一库 |
| contact 加密 | 单元 | 存密文、读回明文；密文≠明文 |
| 渠道投递失败隔离 | 契约 | mock 一渠道抛异常，其余仍投递；未授权渠道不投递 |
| 订阅幂等 | 单元 | 同 (user,disease) 重复 subscribe 返回同一条 |
| 撤销/删除 | 单元 | revoke 后不进巡检；delete 连带删 Delivered_Log |
| digest 合规 | 契约 | mock LLM，验证出口过 compliance_guard、早期阶段带 uncertainty_note |
| 演示态 | 单元 | Demo 关闭时 trigger 不可用；开启时走完整流程且 is_demo=True |

digest 生成质量（LLM 相关）以契约测试为主（mock llm_client），生成质量靠演示与人工抽检。SMTP 邮件发送用 mock，不真实发信。测试框架沿用 pytest + hypothesis。
