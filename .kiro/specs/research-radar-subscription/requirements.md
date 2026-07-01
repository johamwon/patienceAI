# Requirements Document

## Introduction

本规格定义"医语桥"（面向重症/罕见病/疑难杂症患者及家属的循证医学检索 + 通俗化解释 + 情绪陪伴 AI Agent，吉祥物人格"小光"）的新功能：**研究雷达订阅（Research Radar Subscription）**。该功能让产品从"一次性检索工具"升级为"长期陪伴者"——用户查询某病症并获得通俗化解释后，小光主动询问是否订阅该病症的最新研究动态；用户**显式同意**后，系统每日巡检该病症的新证据，当出现高质量新进展（新指南 / 新 RCT / 新临床试验 / 突破性研究）时，生成通俗化摘要并通过站内消息、邮件、微信三种渠道推送给用户。

本功能构建在现有能力之上：检索（search）、三层结构化通俗化解释（explain）、就医准备包（visit-prep）、情绪感知与陪伴暖场白、罕见病/重症研究进展标注、临床试验卡片、研究阶段分级、轻量会话记忆。合规定位为 Clinical-Ops AI（科普教育级），严守"不诊断、不开方、不替代医生"红线，并遵守 PIPL（个人信息保护法）对敏感个人信息的要求。

**贯穿全局的核心设计张力（必须诚实标注并处理）**：本功能同时追求两个相互制衡的目标——既要提供"长期陪伴价值"（主动推送、多渠道触达），又要严守"敏感信息最小化保护"（健康数据与联系方式的物理隔离）。二者存在真实张力：

- 决策 A（邮件 / 微信推送）需要存储邮箱、微信 openid，二者均属联系方式类 PII。
- 决策 B（核心订阅库只存匿名信息）要求核心订阅数据完全无 PII。

**解决原则（沿用现有"生克隔离"设计）**：
- **核心订阅库**只存匿名 user_id + 订阅病症关键词，无任何 PII，满足决策 B。
- **推送渠道逐渠道显式授权**：站内推送零 PII；邮件 / 微信渠道仅当用户主动开启时，才在**物理隔离的联系方式存储**中存最小化的 email / openid，且与健康数据（订阅了什么病）**禁止交叉索引**——任何单一存储都无法推出"某邮箱订阅了什么病"。

当陪伴价值与隐私保护冲突时，**隐私最小化与用户可控（同意/撤回/删除）优先**；陪伴价值只能在合规边界内实现。

## Glossary

- **System（系统）**: 医语桥后端及前端整体应用。
- **Radar_Service（研究雷达服务）**: 负责订阅生命周期、每日巡检调度、新进展判定与推送编排的后端服务。
- **Subscription（订阅）**: 一条"匿名 user_id + 订阅病症关键词"的记录，代表用户对某病症研究动态的长期关注。
- **Subscription_Store（核心订阅库）**: 存储 Subscription 记录的持久化存储，仅含匿名 user_id、病症关键词及订阅元数据，不含任何 PII。
- **Anonymous_User_Id（匿名用户标识）**: 系统生成的轻量、非实名标识，不绑定手机号、真实姓名或身份证件，用于关联同一用户的订阅与渠道授权。
- **Contact_Store（联系方式存储）**: 与 Subscription_Store 物理隔离的独立存储，仅在用户开启邮件或微信渠道时存储最小化的 email / openid；禁止与健康数据交叉索引。
- **Delivery_Channel（推送渠道）**: 推送触达方式，取值范围为 {站内消息, 邮件, 微信}。
- **In_App_Channel（站内消息渠道）**: 零 PII 的渠道，推送以匿名 user_id 关联的站内消息形式送达。
- **Email_Channel（邮件渠道）**: 需要用户提供并授权 email 的推送渠道。
- **WeChat_Channel（微信渠道）**: 经由 openclaw 推送、需要 openid 的推送渠道。
- **Channel_Consent（渠道授权）**: 用户针对某一 Delivery_Channel 的显式开启授权记录。
- **Daily_Patrol（每日巡检任务）**: 每日定时针对所有活跃 Subscription 的病症关键词检索新证据的任务。
- **New_Progress（新进展）**: 满足新进展判定条件（质量与新鲜度阈值）且未曾推送过的研究证据项。
- **Progress_Fingerprint（进展指纹）**: 用于去重的证据唯一标识，基于证据的稳定标识字段（如 NCT 编号 / DOI / 标题+来源+发表时间）计算。
- **Delivered_Log（已推送记录）**: 记录某订阅已推送过的 Progress_Fingerprint 集合，用于去重。
- **Push_Digest（推送摘要）**: 针对一条或多条 New_Progress 生成的群体层面通俗化研究进展摘要，含 Research_Stage 标注与不确定性提示。
- **Research_Stage（研究阶段标签）**: 对研究进展的阶段性标注，区分"突破性 RCT / 早期临床试验 / 动物实验-临床前"等（复用现有能力）。
- **Evidence_Level（证据等级）**: 证据可信度分级（high / moderate / low / very_low）（复用现有能力）。
- **Demo_Mode（演示态）**: 可注入模拟"已有新进展"以展示完整推送效果的运行模式。
- **Explain_Service（解释服务）**: 现有通俗化解释服务，对应端点 `/api/v1/explain`。
- **KnowS_API**: 外部 KnowS AI 医学证据检索 API。
- **Compliance_Guard（合规守卫）**: 现有的面向患者输出合规约束机制（不诊断、不开方、群体证据不冒充个体建议、保留风险提示）。

## Requirements

### Requirement 1: 订阅创建（解释后主动询问 + 显式同意）

**User Story:** 作为患者，我希望在小光为我解释完某个病症后，它主动问我要不要持续关注这个病的最新研究，让我不用自己反复来查。

#### Acceptance Criteria

1. WHEN 一次 Explain_Service 解释针对某病症完成，THE System SHALL 生成一段询问用户是否订阅该病症研究动态的邀约文本。
2. THE System SHALL 从已完成的解释上下文中提取该病症的订阅关键词，并在订阅创建时使用该关键词。
3. WHEN 用户对订阅邀约作出显式同意操作，THE Radar_Service SHALL 创建一条 Subscription 记录，包含 Anonymous_User_Id、订阅病症关键词与创建时间。
4. IF 用户未作出显式同意操作，THEN THE Radar_Service SHALL 不创建任何 Subscription 记录。
5. THE Radar_Service SHALL 对每条 Subscription 采用逐订阅单独显式同意（single opt-in per subscription），不得由一次同意批量订阅多个病症。
6. WHEN 针对同一 Anonymous_User_Id 与同一病症关键词的活跃 Subscription 已存在，THE Radar_Service SHALL 不重复创建订阅并返回已存在的订阅标识。
7. THE Subscription_Store SHALL 仅存储 Anonymous_User_Id、病症关键词及订阅元数据，不得存储 email、openid、手机号、真实姓名或其他 PII。

### Requirement 2: 匿名身份管理

**User Story:** 作为注重隐私的患者，我希望使用订阅功能时不必提供真实姓名或手机号，我的关注内容不被实名关联。

#### Acceptance Criteria

1. WHEN 用户首次需要一个订阅身份，THE System SHALL 生成一个 Anonymous_User_Id，且该标识不绑定手机号、真实姓名或身份证件。
2. THE System SHALL 使用 Anonymous_User_Id 作为关联同一用户的 Subscription 记录与 Channel_Consent 的唯一键。
3. THE System SHALL 不要求用户提供实名信息作为创建 Subscription 的前置条件。
4. IF 某功能需要 email 或 openid（邮件/微信渠道），THEN THE System SHALL 仅在对应渠道被用户显式开启时收集该信息，并存储于 Contact_Store 而非 Subscription_Store。

### Requirement 3: 推送渠道管理与联系方式隔离

**User Story:** 作为患者，我希望自己决定通过哪种方式接收推送，并且知道我的邮箱或微信不会和我关注了什么病被关联在一起。

#### Acceptance Criteria

1. THE System SHALL 支持 {站内消息, 邮件, 微信} 三种 Delivery_Channel。
2. THE In_App_Channel SHALL 以 Anonymous_User_Id 关联的站内消息形式送达，不收集任何 PII。
3. WHEN 用户开启 Email_Channel，THE System SHALL 要求用户提供 email 并作出针对该渠道的显式 Channel_Consent，随后将最小化的 email 存储于 Contact_Store。
4. WHEN 用户开启 WeChat_Channel，THE System SHALL 要求获取 openid 并作出针对该渠道的显式 Channel_Consent，随后将最小化的 openid 存储于 Contact_Store。
5. THE System SHALL 将 Contact_Store 与 Subscription_Store 物理隔离，且不得建立可从单一存储推出"某 email 或 openid 订阅了哪些病症"的交叉索引。
6. IF 用户未开启某 Delivery_Channel，THEN THE System SHALL 不通过该未开启渠道推送，同时仍通过其余已开启渠道推送，且不在 Contact_Store 中为该未开启渠道存储联系方式。
7. WHERE WeChat_Channel 的外部对接依赖（openclaw / 公众号绑定）在当前环境不可用，THE System SHALL 降级为仅提供站内消息与邮件渠道，并保留微信渠道的接口占位。【开放问题 2】

### Requirement 4: 每日巡检任务

**User Story:** 作为已订阅的患者，我希望系统每天替我盯着我关注的病症有没有新研究，而不用我自己天天来查。

#### Acceptance Criteria

1. THE Daily_Patrol SHALL 按每日定时的调度周期执行，对所有活跃 Subscription 的病症关键词发起新证据检索。
2. WHEN Daily_Patrol 执行对某订阅病症的检索，THE Radar_Service SHALL 通过 KnowS_API 检索该病症关键词的证据。
3. IF KnowS_API 在一次巡检检索中调用失败或超时，THEN THE Radar_Service SHALL 记录该次失败、跳过该订阅并继续处理其余订阅，且即使失败记录本身写入失败也继续巡检，不中断整体巡检。
4. THE Daily_Patrol SHALL 对已撤销或已删除的 Subscription 不执行巡检检索。
5. THE Radar_Service SHALL 提供可配置的巡检频率参数，默认值为每日一次。【开放问题 3】

### Requirement 5: 新进展判定与去重

**User Story:** 作为已订阅的患者，我希望只在真的有值得关注的新研究时才收到推送，而不是被重复的、无关紧要的信息打扰。

#### Acceptance Criteria

1. WHEN 巡检检索返回一批证据，THE Radar_Service SHALL 依据可配置的质量阈值（Evidence_Level 与来源类型）与新鲜度阈值（发表时间）筛选出候选 New_Progress。
2. THE Radar_Service SHALL 为每条候选 New_Progress 计算 Progress_Fingerprint，用于去重。
3. WHEN 某候选 New_Progress 的 Progress_Fingerprint 已存在于该订阅的 Delivered_Log，THE Radar_Service SHALL 判定其为已推送并不再推送。
4. WHEN 一条 New_Progress 完成推送，THE Radar_Service SHALL 将其 Progress_Fingerprint 写入该订阅的 Delivered_Log。
5. IF 一次巡检未筛选出任何满足阈值且未推送过的 New_Progress，THEN THE Radar_Service SHALL 不生成任何推送或状态通知。
6. THE Radar_Service SHALL 将新进展判定的质量阈值与新鲜度阈值作为可配置参数。【开放问题 3】

### Requirement 6: 通俗化推送内容生成

**User Story:** 作为已订阅的患者，我希望收到的推送是我能看懂的、诚实标注研究阶段的通俗摘要，而不是看不懂的论文摘要或让我误以为有了特效药。

#### Acceptance Criteria

1. WHEN 存在待推送的 New_Progress，THE Radar_Service SHALL 复用现有通俗化解释能力为其生成 Push_Digest。
2. THE Push_Digest SHALL 为每条纳入的 New_Progress 标注 Research_Stage 与 Evidence_Level。
3. WHEN 一条 New_Progress 处于早期临床试验或动物实验/临床前阶段，THE Push_Digest SHALL 显式说明该结果尚未证实对患者个体有效。
4. THE Push_Digest SHALL 以群体层面的研究进展摘要呈现，不得包含针对用户个体的诊断结论、处方剂量或个体化治疗建议。
5. THE Radar_Service SHALL 使 Push_Digest 通过 Compliance_Guard 的面向患者输出合规约束。
6. WHEN 陪伴/希望表达与证据不确定性标注发生冲突，THE Radar_Service SHALL 在 Push_Digest 中优先呈现不确定性标注与风险提示。

### Requirement 7: 推送投递

**User Story:** 作为已订阅的患者，我希望推送能按我开启的渠道送到我这里，如果某个渠道发送失败也不影响其他渠道。

#### Acceptance Criteria

1. WHEN 一条 Push_Digest 生成完成，THE Radar_Service SHALL 将其投递到该订阅用户已开启 Channel_Consent 的每一个 Delivery_Channel。
2. THE Radar_Service SHALL 通过 In_App_Channel 使用 Anonymous_User_Id 投递而不访问 Contact_Store。
3. WHEN 通过 Email_Channel 或 WeChat_Channel 投递，THE Radar_Service SHALL 从 Contact_Store 读取对应联系方式，且仅用于本次投递。
4. IF 某一 Delivery_Channel 的投递失败，THEN THE Radar_Service SHALL 记录该次失败并主动继续完成其余已开启渠道的投递。
5. THE Radar_Service SHALL 不向用户未开启 Channel_Consent 的渠道投递。

### Requirement 8: 订阅管理界面（查看/撤销/删除/管理渠道）

**User Story:** 作为患者，我希望能随时看到我订阅了哪些病、管理我的推送渠道，并且能撤销订阅、删除我的联系方式，完全掌控我的信息。

#### Acceptance Criteria

1. THE System SHALL 提供界面展示当前 Anonymous_User_Id 名下的所有活跃 Subscription 及其订阅病症关键词。
2. THE System SHALL 提供界面展示各 Delivery_Channel 的开启状态与对应 Channel_Consent。
3. WHEN 用户撤销某条 Subscription，THE Radar_Service SHALL 将该订阅标记为已撤销并停止对其的巡检与推送。
4. WHEN 用户删除某条 Subscription，THE Radar_Service SHALL 从 Subscription_Store 删除该订阅记录及其 Delivered_Log。
5. WHEN 用户关闭某一 Delivery_Channel 或撤回其 Channel_Consent，THE System SHALL 停止通过该渠道推送并从 Contact_Store 删除该渠道对应的联系方式。
6. WHEN 用户请求删除其全部数据，THE System SHALL 从 Subscription_Store 与 Contact_Store 分别删除该 Anonymous_User_Id 关联的所有记录。
7. THE System SHALL 使撤销、删除与撤回同意操作对用户始终可用，不设置额外前置条件。

### Requirement 9: 演示态（模拟新进展触发推送）

**User Story:** 作为演示者，我希望能在演示环境中模拟"出现了新进展"，直接展示从订阅到推送的完整效果，而不必等待真实的后台定时抓取。

#### Acceptance Criteria

1. WHERE Demo_Mode 启用，THE System SHALL 提供一个手动触发入口，可为指定 Subscription 注入模拟的 New_Progress。
2. WHEN Demo_Mode 下注入了模拟 New_Progress，THE Radar_Service SHALL 执行与真实巡检一致的新进展判定、Push_Digest 生成、去重与投递流程。
3. THE System SHALL 在 Demo_Mode 产生的 Push_Digest 中标明其为演示内容。
4. IF Demo_Mode 未启用，THEN THE System SHALL 不暴露模拟新进展注入入口。
5. THE System SHALL 使 Demo_Mode 的推送同样通过 Compliance_Guard 的合规约束。

### Requirement 10: 持久化存储、数据分级与保留

**User Story:** 作为患者和合规方，我希望即使系统为了长期陪伴而持久化存储数据，也遵循最小化、加密与可删除原则，符合 PIPL 与数据安全法要求。

#### Acceptance Criteria

1. THE Subscription_Store SHALL 对存储的数据实行最小化，仅保留 Anonymous_User_Id、病症关键词及必要订阅元数据。
2. THE Contact_Store SHALL 对存储的 email 与 openid 实行最小化，且对联系方式采用加密存储。
3. THE System SHALL 对 Subscription_Store 与 Contact_Store 中的记录设定可配置的数据保留期，并在保留期届满或用户删除时移除相应记录。
4. THE System SHALL 支持对 Subscription_Store 与 Contact_Store 分别执行删除操作，且删除其中一方不依赖另一方的可用性。
5. WHERE 采用轻量本地持久化方案，THE System SHALL 满足上述最小化、隔离、加密与可删除要求。【开放问题 1】
6. THE System SHALL 不建立跨 Subscription_Store 与 Contact_Store 的关联索引，以防止从联系方式反查健康数据。

### Requirement 11: 全局合规与"陪伴价值 vs 敏感信息保护"张力约束

**User Story:** 作为患者和合规方，我希望研究雷达订阅在提供长期陪伴价值的同时，始终守住不诊断红线与敏感信息最小化保护，当二者冲突时以隐私和用户可控优先。

#### Acceptance Criteria

1. THE System SHALL 在所有推送相关的面向患者输出（订阅邀约、Push_Digest、站内/邮件/微信内容）中不包含诊断结论、处方剂量或个体化治疗指令。
2. THE System SHALL 在所有推送内容中不将群体层面的研究证据表述为针对该患者个体的诊疗建议。
3. THE System SHALL 使任一 Subscription 的创建以用户显式同意为前置条件，并使撤回同意随时可用。
4. WHEN 陪伴价值（主动推送、多渠道触达）与敏感信息最小化保护发生冲突，THE System SHALL 优先采用满足隐私最小化与用户可控（同意/撤回/删除）的方案。
5. THE System SHALL 保证核心订阅数据（Subscription_Store）在任何运行路径下均不含 PII。
6. WHERE 任一推送渠道处理 PII，THE System SHALL 将该 PII 限定于 Contact_Store 并与健康数据保持不可交叉索引。
7. IF 一次推送同时涉及研究希望表达与不确定性/风险提示，THEN THE System SHALL 同时呈现二者，且不得用希望表达替代不确定性与风险提示。

## Open Questions

以下为待产品与技术决策确认的开放问题，已在相关需求中以占位符标注：

1. **持久化存储选型（关联 Requirement 10）**：核心订阅库与联系方式存储采用 SQLite / 文件 / Redis 中的哪种？MVP 倾向轻量本地方案（如 SQLite），需满足最小化、物理隔离、加密与可删除要求。选型影响后续设计与保留期实现方式。
2. **微信 openclaw 推送对接方式（关联 Requirement 3）**：是否需要公众号/服务号？用户如何完成 openid 绑定？该渠道可能引入外部依赖，MVP 是否降级为"仅站内 + 邮件"、微信仅留接口占位？
3. **巡检频率与新进展阈值参数（关联 Requirement 4、5）**：每日巡检的具体时间与频率、新进展判定的质量阈值（Evidence_Level / 来源类型）与新鲜度阈值（发表时间窗口）的具体取值。
