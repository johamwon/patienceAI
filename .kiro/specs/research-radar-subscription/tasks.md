# Implementation Plan

本任务清单基于 `requirements.md`（R1–R11）与 `design.md`（Radar 子系统、SQLite 两库物理隔离、渠道抽象、API、Testing Strategy）拆解为可增量交付的编码/测试任务。任务按依赖分组：数据模型 → 存储层 → 纯逻辑 → digest → 渠道 → 服务/巡检 → API → explain 挂钩 → 前端 → 贯穿校验。测试沿用 pytest + hypothesis（已在 `backend/requirements.txt`）。

- [x] 1. 数据模型与类型定义
  - [x] 1.1 后端 Pydantic 模型
    - 在 `backend/app/models/schemas.py` 新增 `Subscription`、`SubscribeRequest`、`ChannelSetRequest`、`PushDigestItem`、`PushDigest`、`InAppMessage`、`SubscriptionOffer` 模型；为 `ExplainResponse` 增加可选字段 `subscription_offer: Optional[SubscriptionOffer]`。
    - _Requirements: R1.1, R1.3, R3.1, R6.2, R6.3, R7.2, R9.3_
  - [x] 1.2 前端 TypeScript 类型
    - 在 `frontend/src/types/index.ts` 新增 `Subscription`、`PushDigestItem`、`PushDigest`、`InAppMessage` 类型，并为 `ExplainResponse` 增加可选 `subscription_offer` 字段。
    - _Requirements: R1.1, R6.2, R7.2, R8.1_

- [x] 2. 存储层（SQLite 两库物理隔离）
  - [x] 2.1 订阅库抽象基类 + SQLite 实现
    - 新增 `backend/app/services/radar/subscription_store.py`：定义 `SubscriptionStore(ABC)`（沿用 session_memory 抽象模式）与 `SQLiteSubscriptionStore`（`subscriptions.db`，threading.Lock 保护）。实现 `subscriptions`/`delivered_log`/`channel_consent`/`inapp_messages` 表建表；方法：`create`（UNIQUE(anon_user_id,disease_keyword) 幂等）、`list_active`、`list_all_active`、`revoke`、`delete`（连带删 delivered_log）、`is_delivered`、`mark_delivered`、渠道 consent 读写、按 anon_user_id 删除、保留期清理。写入接口在类型层面不接受任何 PII。
    - _Requirements: R1.3, R1.6, R1.7, R4.4, R5.3, R5.4, R8.3, R8.4, R10.1, R10.3, R11.5_
  - [x] 2.2 联系方式库（隔离 + 加密）
    - 新增 `backend/app/services/radar/contact_store.py`：独立 `contacts.db`、独立连接，`contacts(anon_user_id, channel, encrypted_value, consented_at)` 表；集中加/解密逻辑，密钥取自 `RADAR_SECRET_KEY`；方法 `set_contact`、`get_contact`（解密）、`delete_contact`、`delete_all`（按 anon_user_id）、保留期清理。禁止任何跨库 JOIN/联合查询。
    - 引入 `cryptography>=43.0.0`（Fernet 对称加密）到 `backend/requirements.txt`。
    - _Requirements: R2.4, R3.5, R8.5, R8.6, R10.2, R10.4, R10.6, R11.6_
  - [x] 2.3 站内消息存储
    - 新增 `backend/app/services/radar/inapp_store.py`（或在 subscription_store 内实现 inapp_messages 读写）：以 `anon_user_id` 关联写入/读取 `digest_json`、标记已读，零 PII。
    - _Requirements: R7.2, R11.5_
  - [x] 2.4 存储层单元测试（隔离/加密/删除）
    - 新增 `backend/tests/test_radar_stores.py`：验证 subscriptions.db 记录不含联系方式字段；contact 存密文、读回明文、密文≠明文；`delete_all` 分别删两库且删一库不依赖/不影响另一库；delete 订阅连带删 Delivered_Log；channel_consent 与 contacts 分离（订阅库拿不到邮箱）。用临时 db 文件 fixture。
    - _Requirements: R1.7, R3.5, R8.4, R8.6, R10.4, R10.6, R11.5, R11.6_

- [x] 3. 新进展判定与去重（纯逻辑）
  - [x] 3.1 fingerprint 与新进展判定
    - 新增 `backend/app/services/radar/fingerprint.py`：`progress_fingerprint(evidence)`（优先 nct_id/doi/pmid，缺失时 sha1(title|source_type|publish_date)）与 `is_new_progress(evidence, now=None)`（质量阈值 evidence_level∈{high,moderate} 或 source_type∈{guide,trial,meeting}，且新鲜度在近 `RADAR_FRESH_DAYS`(默认30) 天内）；阈值参数化。
    - _Requirements: R5.1, R5.2, R5.6_
  - [x] 3.2 fingerprint 属性测试 + is_new_progress 单元测试
    - 新增 `backend/tests/test_radar_fingerprint.py`：属性测试（hypothesis）——同证据幂等同键、nct/doi/pmid 优先、缺失走标题指纹；单元测试——高/中等级或指南/试验/会议通过、过旧（超 N 天）拒绝、低质量拒绝。
    - _Requirements: R5.1, R5.2, R5.6_
  - [x] 3.3 去重幂等单元测试
    - 新增 `backend/tests/test_radar_dedup.py`：已 delivered 的 fingerprint 不再推；`mark_delivered` 后 `is_delivered=True`；同一进展重复巡检不重复推送。
    - _Requirements: R5.3, R5.4_

- [x] 4. Push_Digest 生成
  - [x] 4.1 digest_generator 实现
    - 新增 `backend/app/services/radar/digest_generator.py`：`generate_push_digest(disease_keyword, new_evidences, llm_client)` 复用 `SimplificationLoop` 通俗化 + `research_stage` 标注 Research_Stage/Evidence_Level + 早期/临床前附 `uncertainty_note` + `compliance_guard` 出口清洗；群体层面呈现，不含诊断/处方/个体化建议；冲突时不确定性优先；返回 `PushDigest` 结构含 `is_demo`。
    - _Requirements: R6.1, R6.2, R6.3, R6.4, R6.5, R6.6, R11.1, R11.2, R11.7_
  - [x] 4.2 digest 合规契约测试
    - 新增 `backend/tests/test_radar_digest.py`：mock llm_client，验证 digest 出口经 compliance_guard（无诊断/处方/个体化建议）；早期/临床前阶段必带 uncertainty_note；希望表达与不确定性同时呈现。
    - _Requirements: R6.3, R6.4, R6.5, R6.6, R11.1, R11.7_

- [x] 5. 投递渠道
  - [x] 5.1 渠道抽象基类
    - 新增 `backend/app/services/radar/delivery/base.py`：`DeliveryChannel(ABC)` 含 `name`、`is_available()`、`deliver(anon_user_id, digest)`。
    - _Requirements: R3.1, R7.1_
  - [x] 5.2 站内渠道
    - 新增 `backend/app/services/radar/delivery/in_app.py`：写 inapp_messages，只用 anon_user_id，不访问 Contact_Store。
    - _Requirements: R3.2, R7.2_
  - [x] 5.3 邮件渠道
    - 新增 `backend/app/services/radar/delivery/email.py`：从 contact_store 解密读取 email，仅本次投递用；SMTP 配置从 env；发信失败抛异常供上层隔离。
    - _Requirements: R3.3, R7.3_
  - [x] 5.4 微信渠道占位
    - 新增 `backend/app/services/radar/delivery/wechat.py`：`is_available()` 返回 False（MVP 降级），`deliver` 降级跳过并保留接口占位。
    - _Requirements: R3.4, R3.7_
  - [x] 5.5 投递失败隔离契约测试
    - 新增 `backend/tests/test_radar_delivery.py`：mock 一渠道抛异常，验证其余渠道仍完成投递并记录失败；未授权（无 consent）渠道不投递；微信不可用时降级跳过、站内不受影响。
    - _Requirements: R3.6, R7.4, R7.5, R3.7_

- [x] 6. Radar 服务与巡检
  - [x] 6.1 RadarService 编排
    - 新增 `backend/app/services/radar/radar_service.py`：`subscribe`（幂等）、`list_subscriptions`、`revoke`、`delete`、`set_channel`（开启+存联系方式）、`unset_channel`（关闭+删联系方式）、`delete_all`（两库分别删）、`run_patrol_once`、`process_subscription`（判定→去重→digest→投递编排：遍历已授权渠道逐个 deliver，单渠道异常隔离）、`inject_demo_progress`（演示态）。撤销/删除/撤回随时可用无前置条件。
    - _Requirements: R1.3, R1.5, R1.6, R3.3, R3.4, R3.6, R7.1, R7.4, R7.5, R8.3, R8.4, R8.5, R8.6, R8.7, R9.2, R11.3, R11.4_
  - [x] 6.2 每日巡检 daemon
    - 新增 `backend/app/services/radar/patrol.py`：`start_daily_patrol()` 参考 `cache_service.start_background_refresh` 的 daemon 线程，按 `RADAR_PATROL_INTERVAL_HOURS`(默认24) 周期调 `run_patrol_once`；`run_patrol_once` 遍历 `list_all_active`，对每订阅调 `knows_client.search_multi_queries`，单订阅 try/except 隔离（失败记录并继续，即便日志写入失败也继续）；已撤销/删除的（status≠active）不巡检；巡检频率参数化。
    - _Requirements: R4.1, R4.2, R4.3, R4.4, R4.5_
  - [x] 6.3 订阅幂等/撤销删除/演示态测试
    - 新增 `backend/tests/test_radar_service.py`：同 (user,disease) 重复 subscribe 返回同一条；revoke 后不进巡检、delete 连带删 Delivered_Log；无新进展时不生成 digest/不发通知；Demo_Mode 关闭时 trigger 不可用、开启时走完整流程且 is_demo=True；巡检中单订阅 KnowS 失败被隔离、其余继续。
    - _Requirements: R1.6, R4.3, R4.4, R5.5, R8.3, R8.4, R9.1, R9.2, R9.4, R9.5_

- [x] 7. API 路由与集成
  - [x] 7.1 Radar API 路由
    - 新增 `backend/app/api/radar.py`（prefix `/api/v1/radar`）实现 10 个端点：`POST /subscribe`、`GET /subscriptions`、`POST /subscriptions/{id}/revoke`、`DELETE /subscriptions/{id}`、`GET /channels`、`POST /channels`、`DELETE /channels/{channel}`、`DELETE /user/{anon_user_id}`、`GET /messages`、`POST /demo/trigger`（仅 Demo_Mode，否则 404/403）。
    - _Requirements: R1.3, R3.3, R3.4, R7.2, R8.1, R8.2, R8.3, R8.4, R8.5, R8.6, R9.1, R9.4_
  - [x] 7.2 注册路由并启动巡检线程
    - 修改 `backend/app/main.py`：注册 radar 路由；启动时调用 `start_daily_patrol()` 启动巡检 daemon。
    - _Requirements: R4.1_
  - [x] 7.3 API 路由测试
    - 新增 `backend/tests/test_radar_router.py`：subscribe 显式同意创建/幂等；channels 开启/关闭；user 全量删除两库；demo trigger 在关闭态返回不可用；messages 拉取站内消息。
    - _Requirements: R1.3, R1.4, R8.1, R8.5, R8.6, R9.4_

- [x] 8. explain 挂钩订阅邀约
  - [x] 8.1 explain 响应增加订阅邀约
    - 修改 `backend/app/api/explain.py`：解释完成后从疾病主题（复用 visit_prep 的 `_extract_disease_topic` 或实体提取）提取 `disease_keyword`，生成经 compliance_guard 的小光口吻邀约文案，填入 `subscription_offer`；用户未同意不创建订阅。
    - _Requirements: R1.1, R1.2, R1.4, R11.1_

- [x] 9. 前端集成
  - [x] 9.1 API 客户端 + 匿名身份
    - 修改 `frontend/src/api/index.ts`：新增 radar 端点调用；匿名 user_id 首访生成 uuid 存 localStorage 并随请求携带（非实名）。
    - _Requirements: R2.1, R2.2, R2.3_
  - [x] 9.2 订阅邀约组件
    - 新增 `frontend/src/components/SubscribePrompt.tsx`：展示小光邀约文案，显式同意后调用 subscribe（逐订阅单独同意）。
    - _Requirements: R1.1, R1.3, R1.5, R11.3_
  - [x] 9.3 订阅管理组件
    - 新增 `frontend/src/components/SubscriptionManager.tsx`：展示活跃订阅、各渠道开启状态；支持撤销/删除订阅、开启/关闭渠道（含联系方式）、删除全部数据；操作始终可用。
    - _Requirements: R8.1, R8.2, R8.3, R8.4, R8.5, R8.6, R8.7_
  - [x] 9.4 站内消息中心
    - 新增 `frontend/src/components/MessageCenter.tsx`：拉取并展示 Push_Digest（含 Research_Stage/Evidence_Level/uncertainty_note、演示内容标记）。
    - _Requirements: R7.2, R6.2, R6.3, R9.3_
  - [x] 9.5 ExplanationView / SearchPage 集成 + 演示态触发
    - 修改 `frontend/src/components/ExplanationView.tsx` 集成 SubscribePrompt 入口；修改 `frontend/src/pages/SearchPage.tsx` 管理 anon_user_id、挂载 SubscriptionManager/MessageCenter，并在 Demo_Mode 下提供演示态触发按钮。
    - _Requirements: R1.1, R9.1, R9.4_

- [x] 10. 合规与隔离贯穿校验
  - [x] 10.1 生克隔离与合规集成测试
    - 新增 `backend/tests/test_radar_isolation_compliance.py`：端到端验证任一运行路径下 subscriptions.db 零 PII；两库不可交叉索引（无法从联系方式反查病症）；所有面向患者输出（邀约/digest/站内/邮件内容）无诊断/处方/个体化建议且群体证据不冒充个体建议；冲突时隐私最小化与用户可控优先、不确定性优先。
    - _Requirements: R11.1, R11.2, R11.4, R11.5, R11.6, R11.7, R10.6_

