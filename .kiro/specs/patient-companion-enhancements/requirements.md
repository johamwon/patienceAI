# Requirements Document

## Introduction

本规格定义"患癌知光"（一个面向重症/罕见病/疑难杂症患者及家属的循证医学检索与通俗化解释 AI Agent）的三项陪伴增强能力。在现有的检索（search）、解释（explain）、意图/风险分类、缓存、三层结构化输出和四级风险路由基础上，新增：

1. **就医准备包（Visit Prep Pack）**：基于患者查询、检索证据与情绪状态，生成结构化的医患沟通清单，定位为"患者-医生沟通桥梁"。
2. **罕见病/重症最新研究进展模块**：增加罕见病/重症意图标记、升级检索路由、提供临床试验卡片，并在严格证据分级前提下呈现研究希望。
3. **Agent 拟人化 + 情绪感知 + 陪伴**：统一人格"小光"，识别查询情绪信号，生成共情暖场白，提供轻量会话记忆，并在前端切换吉祥物表情与气泡。

实施顺序为方向一→二→三的文档编号，但建议交付顺序为：就医准备包 → 罕见病/重症进展 → 拟人化陪伴（合规分寸最难的放最后）。

**贯穿全局的核心设计原则（合规张力）**：本系统的所有增强能力必须同时满足两条相互制衡的目标——既要提供情绪陪伴与希望，又要诚实标注不确定性。当二者冲突时，诚实标注与风险提示优先；温度只能体现在表达方式上，绝不能用乐观语气掩盖坏证据、不得把群体证据冒充个体建议、不得为体验牺牲风险提示。系统始终守住"不诊断、不开方、不替代医生"的红线。

## Glossary

- **System（系统）**: 患癌知光后端及前端整体应用。
- **Companion_Engine（陪伴引擎）**: 负责人格注入、情绪感知与陪伴话语生成的后端模块。
- **Emotion_Detector（情绪感知层）**: 识别查询中情绪信号的子模块，采用规则与 LLM 混合策略。
- **Persona（人格"小光"）**: 统一的 Agent 人格，特征为温柔、诚实、懂医学但不端着；注入所有面向患者的 LLM 输出。
- **Companion_Message（暖场白）**: 回答开头根据情绪状态调整的共情陪伴话语。
- **Session_Memory（会话记忆）**: 以 session_id 关联的最近 N 轮查询上下文存储。
- **Visit_Prep_Service（就医准备包服务）**: 生成结构化医患沟通清单的后端服务，对应端点 `/api/v1/visit-prep`。
- **Visit_Prep_Pack（就医准备包）**: 包含"该问医生的问题、该主动告知的信息、该索取的检查、该确认的治疗选项"四类条目的结构化数据。
- **Intent_Classifier（意图分类器）**: 现有的查询意图与风险等级判定模块。
- **Rare_Disease_Flag（罕见病标记）**: 意图分类输出中标识查询涉及罕见病的布尔标记。
- **Severe_Condition_Flag（重症标记）**: 意图分类输出中标识查询涉及重症的布尔标记。
- **Search_Router（检索路由）**: 根据意图与标记选择 KnowS AI 检索源及排序策略的逻辑。
- **Trial_Card（临床试验卡片）**: 呈现临床试验关键信息的结构化卡片，含 NCT 编号、招募状态、阶段、入排标准、地点。
- **Evidence_Level（证据等级）**: 证据的可信度分级（high / moderate / low / very_low）。
- **Research_Stage（研究阶段标签）**: 对研究进展的阶段性标注，区分"突破性 RCT / 早期临床试验 / 动物实验"等。
- **Risk_Level（风险等级）**: 现有四级风险路由（low / medium / high / prohibited）。
- **Mascot（吉祥物）**: 前端展示的"小光"形象组件。
- **KnowS_API**: 外部 KnowS AI 医学证据检索 API。
- **Mascot_State（吉祥物状态）**: 驱动前端表情与气泡文案的情绪状态枚举值。

## Requirements

### Requirement 1: 统一人格"小光"注入

**User Story:** 作为患者，我希望与一个有温度、一致、诚实的助手"小光"对话，让我在查询医学信息时感到被理解而不是面对冷冰冰的机器。

#### Acceptance Criteria

1. THE Companion_Engine SHALL 在生成所有面向患者的输出文本（一句话结论、患者通俗解释、暖场白）时注入 Persona 人格特征定义。
2. THE Persona SHALL 在系统中以单一、集中定义的人格描述（人格提示词）存在，供所有面向患者的生成环节复用。
3. WHEN 任意一次患者可见的文本生成完成，THE Companion_Engine SHALL 保持 Persona 的语气特征（温柔、诚实、不端着）在该次输出的全部文本中一致。
4. THE Companion_Engine SHALL 在人格表达与证据陈述冲突时，优先保留证据的原始结论与不确定性，不得为维持温柔语气修改、弱化或省略证据中的负面结论。
5. WHERE 输出文本包含医学结论，THE Companion_Engine SHALL 保留现有三层结构化输出中的免责声明文本。

### Requirement 2: 情绪感知层

**User Story:** 作为患者，我希望小光能感知到我提问时的情绪状态，从而用合适的方式回应我，而不是对恐慌和平静求知一视同仁。

#### Acceptance Criteria

1. WHEN 系统接收到一条患者查询，THE Emotion_Detector SHALL 输出一个情绪状态分类，取值范围为 {恐慌, 焦虑, 绝望, 急症倾向, 平静求知}。
2. THE Emotion_Detector SHALL 采用规则匹配与 LLM 判定相结合的混合策略产出情绪状态分类。
3. IF LLM 判定不可用或调用失败，THEN THE Emotion_Detector SHALL 回退到规则匹配结果并返回一个情绪状态分类。
4. WHEN Emotion_Detector 识别出"急症倾向"情绪状态，THE System SHALL 将该查询的处理与现有 high 或 prohibited 风险路由一并触发就医提示。
5. THE Emotion_Detector SHALL 在每次查询的处理结果中附带所识别的情绪状态字段，供陪伴话语层与前端使用。
6. IF 一条查询无法匹配任何情绪信号，THEN THE Emotion_Detector SHALL 返回"平静求知"作为默认情绪状态。

### Requirement 3: 陪伴话语层

**User Story:** 作为患者，我希望小光在回答开头先理解我的处境，即使要告诉我坏消息也先共情再说明，并给我下一步的出口，而不是直接抛给我冰冷的结论。

#### Acceptance Criteria

1. WHEN 系统生成一次面向患者的回答，THE Companion_Engine SHALL 在回答开头生成一段 Companion_Message 暖场白。
2. THE Companion_Engine SHALL 根据 Emotion_Detector 输出的情绪状态选择对应的暖场白基调。
3. WHEN 检索证据包含负面或不利结论，THE Companion_Engine SHALL 在 Companion_Message 中先表达共情，随后照实陈述该结论，并提供一个可执行的下一步出口（例如建议就医沟通的方向），无论 Emotion_Detector 识别出何种情绪状态均先表达共情。
4. THE Companion_Engine SHALL 在 Companion_Message 中不使用乐观语气掩盖、淡化或回避证据中的负面结论。
5. THE Companion_Message SHALL 不包含诊断结论、处方建议或个体化治疗指令。
6. WHERE 检索证据强烈指向某一情况，THE Companion_Engine SHALL 可在不作正式诊断的前提下陈述证据所呈现的模式，但不得将其表述为对该患者的确诊结论。
7. WHERE Risk_Level 为 high 或 prohibited，THE Companion_Engine SHALL 在 Companion_Message 中包含引导用户咨询主治医生或前往正规医疗机构的内容。

### Requirement 4: 轻量会话记忆

**User Story:** 作为患者，我希望小光能记得我在同一次会话中之前问过的内容，这样我追问时不必重复说明背景。

#### Acceptance Criteria

1. WHEN 一次查询请求携带 session_id，THE Session_Memory SHALL 将该查询及其情绪状态追加到对应会话的上下文记录中。
2. THE Session_Memory SHALL 为每个 session_id 保留最近 N 轮查询上下文，其中 N 为可配置参数，默认值为 5。
3. WHEN 生成回答时存在同一 session_id 的历史上下文，THE Companion_Engine SHALL 将最近 N 轮上下文提供给生成环节作为参考。
4. WHERE 一次查询请求未携带 session_id，THE System SHALL 在不使用历史上下文的情况下完成本次回答。
5. THE Session_Memory SHALL 将会话上下文存储于进程内存中（MVP 不持久化），并在服务重启后清空。【开放问题 1：未来是否引入持久化存储，见下文】
6. WHEN 某个 session_id 的上下文记录超过 N 轮，THE Session_Memory SHALL 丢弃最早的记录以保持最多 N 轮。

### Requirement 5: 前端吉祥物情绪联动

**User Story:** 作为患者，我希望屏幕上的小光能根据我的情绪变化表情和说的话，让我感到陪伴是真实的。

#### Acceptance Criteria

1. WHEN 前端接收到包含情绪状态字段的回答，THE Mascot SHALL 根据该情绪状态切换为对应的 Mascot_State 表情。
2. THE Mascot SHALL 为 {恐慌, 焦虑, 绝望, 急症倾向, 平静求知} 每个情绪状态提供一个对应的表情与气泡文案。
3. WHEN 情绪状态字段缺失或无法识别，THE Mascot SHALL 显示默认（平静求知）表情与默认气泡文案。
4. THE Mascot SHALL 在气泡文案中不显示诊断结论或个体化治疗建议。

### Requirement 6: 就医准备包数据模型

**User Story:** 作为患者，我希望系统能为我整理一份结构化的就医准备清单，让我去见医生时知道该问什么、该说什么、该查什么。

#### Acceptance Criteria

1. THE Visit_Prep_Pack SHALL 包含四类条目：该问医生的关键问题、该主动告知医生的信息点、该索取的检查或化验项、该确认的治疗方案选项。
2. THE Visit_Prep_Pack SHALL 为每一类条目以列表形式组织，列表中每个条目为一条可独立勾选的文本项。
3. THE Visit_Prep_Pack SHALL 在数据结构中包含一段定位说明文本，表明该清单为患者-医生沟通辅助，最终诊疗以医生判断为准。
4. THE Visit_Prep_Service SHALL 输出符合 Visit_Prep_Pack 结构的结果，且每个条目文本不包含诊断结论或处方剂量。

### Requirement 7: 就医准备包生成与端点

**User Story:** 作为患者，我希望能针对我的具体问题单独获取一份就医准备包，并且这个能力可以独立触发和缓存以加快响应。

#### Acceptance Criteria

1. THE System SHALL 提供一个独立的 API 端点 `/api/v1/visit-prep` 用于生成 Visit_Prep_Pack。
2. WHEN `/api/v1/visit-prep` 接收到一条患者查询，THE Visit_Prep_Service SHALL 基于该查询、检索到的证据与该查询的情绪状态生成 Visit_Prep_Pack。
3. WHEN 同一查询的 Visit_Prep_Pack 已存在于缓存且未过期，THE Visit_Prep_Service SHALL 返回缓存结果而不重新生成。
4. WHEN 一次 Visit_Prep_Pack 生成完成，THE Visit_Prep_Service SHALL 将结果写入缓存供后续请求复用。
5. IF 针对某查询未检索到任何证据，THEN THE Visit_Prep_Service SHALL 基于查询本身生成通用就医准备问题，将生成结果报告为成功，并在返回结果中标明未找到针对性证据。
6. IF Visit_Prep_Pack 生成过程发生错误，THEN THE Visit_Prep_Service SHALL 返回描述性错误信息且 HTTP 状态码为 5xx。

### Requirement 8: 就医准备包前端交互

**User Story:** 作为患者，我希望能在界面上勾选准备包中的条目，并把它打印或截图带去医院。

#### Acceptance Criteria

1. THE System SHALL 在前端展示 Visit_Prep_Pack 的四类条目，每个条目附带可勾选控件。
2. WHEN 用户勾选或取消勾选某条目，THE System SHALL 更新该条目的勾选状态显示。
3. THE System SHALL 提供一个将 Visit_Prep_Pack 导出为可打印视图的操作入口。
4. THE System SHALL 在 Visit_Prep_Pack 展示视图中显示其定位说明文本（沟通辅助，诊疗以医生为准）。
5. 【开放问题 2：就医准备包作为独立功能页还是嵌入解释结果，见下文】WHERE 产品决策确定为嵌入解释结果，THE System SHALL 在解释结果视图内渲染 Visit_Prep_Pack。

### Requirement 9: 罕见病与重症意图标记

**User Story:** 作为罕见病或重症患者，我希望系统能识别出我的查询属于罕见病或重症，从而采用更有针对性的检索策略。

#### Acceptance Criteria

1. WHEN Intent_Classifier 处理一条查询，THE Intent_Classifier SHALL 输出 Rare_Disease_Flag 与 Severe_Condition_Flag 两个布尔标记。
2. WHEN 查询匹配罕见病判定条件，THE Intent_Classifier SHALL 将 Rare_Disease_Flag 置为 true。
3. WHEN 查询匹配重症判定条件，THE Intent_Classifier SHALL 将 Severe_Condition_Flag 置为 true。
4. IF 罕见病或重症的匹配逻辑失败或判定结果不确定，THEN THE Intent_Classifier SHALL 将对应标记默认置为 false。
5. WHEN Rare_Disease_Flag 或 Severe_Condition_Flag 为 true，THE System SHALL 触发罕见病/重症专门检索策略。
6. THE Intent_Classifier SHALL 在罕见病或重症判定为 true 时仍按现有规则独立判定 Risk_Level。
7. 【开放问题 3：罕见病聚焦病种范围，见下文】

### Requirement 10: 罕见病/重症检索路由升级

**User Story:** 作为罕见病或重症患者，我希望系统优先给我最新的临床试验和研究进展，并按时间把最新的排在前面。

#### Acceptance Criteria

1. WHEN Rare_Disease_Flag 或 Severe_Condition_Flag 为 true，THE Search_Router SHALL 优先选择 trial、meeting、paper_en 三类检索源。
2. WHEN 检索结果用于罕见病或重症查询，THE Search_Router SHALL 按证据发表时间降序排序结果，将最新发表的排在前面。
3. WHERE 罕见病/重症检索策略生效，THE Search_Router SHALL 在选择检索源时保留至少一类指南或权威综述源用于交叉佐证。
4. IF 罕见病/重症专门检索源未返回结果，THEN THE Search_Router SHALL 回退到现有默认检索源集合并返回可得结果。

### Requirement 11: 临床试验卡片

**User Story:** 作为罕见病或重症患者，我希望看到临床试验的关键信息卡片，让我知道有哪些试验、是否在招募、在哪里参加。

#### Acceptance Criteria

1. WHEN 一条证据的来源类型为 trial 且包含 NCT 编号，THE System SHALL 将该证据渲染为 Trial_Card。
2. THE System SHALL 在渲染 Trial_Card 前校验 NCT 编号与来源证据一致，校验不通过时不渲染该卡片。
3. THE Trial_Card SHALL 显示以下字段：NCT 编号、招募状态、试验阶段、入排标准、地点。
4. IF Trial_Card 的某个字段在证据数据中缺失，THEN THE System SHALL 将该字段显示为"信息未提供"而不隐藏整张卡片。
5. THE Trial_Card SHALL 在卡片中包含提示文本，说明是否符合入组需经临床医生评估确认。
6. THE Trial_Card SHALL 不将"正在招募"状态表述为对该患者疗效或入组资格的承诺。

### Requirement 12: 研究希望表达与证据分级标注

**User Story:** 作为重症或罕见病患者，我希望看到最新研究进展带来的希望，但我也需要清楚每条进展处在什么研究阶段，不被误导。

#### Acceptance Criteria

1. WHEN 系统呈现一条研究进展，THE System SHALL 为该进展标注 Research_Stage，至少区分"突破性 RCT 证据"、"早期临床试验"、"动物实验/临床前研究"三类。
2. THE System SHALL 将每条研究进展的 Research_Stage 标签与其 Evidence_Level 一并展示给患者。
3. WHEN 一条研究进展处于早期临床试验或动物实验阶段，THE System SHALL 在呈现该进展时显式说明该结果尚未证实对患者个体有效。
4. THE System SHALL 在表达研究希望时不将早期阶段研究结论表述为已确立的临床获益。
5. WHERE 研究进展呈现模块被启用，THE System SHALL 在希望表达文本中同时保留对不确定性的诚实标注，二者冲突时以不确定性标注优先。
6. THE System SHALL 不依据研究进展为患者个体给出是否采用某项治疗的建议。

### Requirement 13: 全局合规与诚实-希望张力约束

**User Story:** 作为患者和监管合规方，我希望无论系统增加多少陪伴和希望表达能力，它始终守住不诊断、不开方、不替代医生的红线，并诚实呈现不确定性。

#### Acceptance Criteria

1. THE System SHALL 在所有新增的面向患者输出（暖场白、就医准备包、研究进展、试验卡片）中不包含诊断结论、处方剂量或个体化治疗指令。
2. WHEN 情绪陪伴或希望表达与证据的不确定性标注发生冲突，THE System SHALL 优先呈现不确定性标注与风险提示。
3. THE System SHALL 在所有新增的面向患者输出中不将群体层面的研究证据表述为针对该患者个体的建议。
4. WHERE 任一新增功能生成面向患者的医学内容，THE System SHALL 保留现有 Risk_Level 风险提示机制并按风险等级输出对应提示。
5. IF 一次输出同时触发陪伴话语与 high 或 prohibited 风险提示，THEN THE System SHALL 同时呈现共情话语与就医/风险提示，且不得用共情话语替代风险提示。

## Open Questions

以下为待产品与技术决策确认的开放问题，已在相关需求中以占位符标注：

1. **会话记忆持久化（关联 Requirement 4）**：MVP 采用进程内存、重启即失忆。是否在后续版本引入持久化存储（如 Redis / 数据库）？若引入，需补充数据保留期限、隐私与患者数据合规要求。
2. **就医准备包形态（关联 Requirement 8）**：作为独立功能页，还是嵌入现有解释结果视图？影响前端信息架构与导航设计。
3. **罕见病聚焦病种范围（关联 Requirement 9）**：采用"窄切口打深井"（聚焦少数病种做深）还是"宽覆盖"（广泛识别罕见病）？影响 Rare_Disease_Flag 的判定词表与检索策略调优范围。
