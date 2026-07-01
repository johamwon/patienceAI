import { useState } from "react";
import type { ExplainResponse, ResearchProgress, VisitPrepResponse } from "../types";
import VisitPrepView from "./VisitPrepView";
import TrialCard from "./TrialCard";
import CompanionBanner from "./CompanionBanner";

const RISK_LEVEL_COLORS: Record<string, string> = {
  low: "#52c41a",
  medium: "#faad14",
  high: "#ff4d4f",
  prohibited: "#ff4d4f",
};

// 研究阶段标签：中文名称 + 徽章样式（R12.1/R12.2）。
// 突破性 RCT 用稳重色；早期临床试验/临床前研究用提示色，以视觉上提示不确定性（R12.3/R12.4）。
const RESEARCH_STAGE_META: Record<
  ResearchProgress["research_stage"],
  { label: string; badgeClass: string }
> = {
  breakthrough_rct: { label: "突破性RCT证据", badgeClass: "research-stage-badge breakthrough" },
  early_trial: { label: "早期临床试验", badgeClass: "research-stage-badge early" },
  preclinical: { label: "动物实验/临床前研究", badgeClass: "research-stage-badge preclinical" },
};

// 早期临床试验/临床前研究阶段需显式展示不确定性说明，避免患者误读为已确立的临床获益（R12.3/R12.4）。
const UNCERTAIN_STAGES: ResearchProgress["research_stage"][] = ["early_trial", "preclinical"];

const DEFAULT_UNCERTAINTY_NOTE = "该结果尚未在患者身上证实有效，不能作为已确立的临床获益。";

type ExplanationViewProps = {
  data: ExplainResponse;
  query: string;
  // 就医准备包（OQ2/方案A：自动前置，作为展示态嵌入解释结果）
  visitPrep?: VisitPrepResponse | null;
  visitPrepLoading?: boolean;
  visitPrepError?: string | null;
};

export default function ExplanationView({
  data,
  query,
  visitPrep,
  visitPrepLoading = false,
  visitPrepError = null,
}: ExplanationViewProps) {
  // 折叠证据区：默认折叠，想深究的人才展开（任务1第6位）
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  // 核心回答兜底：layer1_conclusion.text 为空时，用 layer3 的 what_is_it 首段兜底
  const conclusionText =
    data.layer1_conclusion.text?.trim() ||
    data.layer3_patient_explanation.what_is_it?.split(/\n|。/)[0]?.trim() ||
    "";

  // 折叠证据区计数：证据卡片 + 研究进展 + 临床试验
  const evidenceCount =
    data.layer2_evidence_cards.length +
    data.research_progress.length +
    data.trial_cards.length;

  return (
    <div className="explanation-view">
      {/* 1. 暖场白：「小光对你说」对话气泡区（R3.1） */}
      <CompanionBanner message={data.companion_message} emotion={data.emotion_state} />

      {/* 2. 风险提示 */}
      {data.risk_message && (
        <div className="risk-banner" style={{ borderColor: RISK_LEVEL_COLORS[data.risk_level] }}>
          <span className="risk-banner-icon" aria-hidden="true">⚠️</span>
          <div className="risk-banner-body">
            <strong>风险提示</strong>
            <p>{data.risk_message}</p>
          </div>
        </div>
      )}

      {/* 3. 核心回答区：视觉焦点（大字号 + 柔和高亮背景 + 左侧色条） */}
      {conclusionText && (
        <section className="core-answer">
          <div className="core-answer-label">
            <span className="core-answer-icon" aria-hidden="true">💬</span>
            <h2>给你的回答</h2>
          </div>
          <p className="core-answer-text">{conclusionText}</p>
          {data.layer1_conclusion.citations.length > 0 && (
            <p className="core-answer-citations">
              参考：{data.layer1_conclusion.citations.map((c) => `PMID:${c}`).join("、")}
            </p>
          )}
        </section>
      )}

      {/* 4. 患者通俗解释：紧随核心回答，是患者要看的主体内容 */}
      <section className="layer layer-3">
        <h2>💡 给你的通俗解释</h2>

        <div className="explanation-section">
          <h3>这是什么？</h3>
          <p>{data.layer3_patient_explanation.what_is_it}</p>
        </div>

        <div className="explanation-section">
          <h3>证据说明了什么？</h3>
          <p>{data.layer3_patient_explanation.what_evidence_says}</p>
        </div>

        <div className="explanation-section">
          <h3>对你意味着什么？</h3>
          <p>{data.layer3_patient_explanation.what_it_means_for_you}</p>
        </div>

        <div className="explanation-section warning">
          <h3>⚠️ 何时需要立即就医</h3>
          <p>{data.layer3_patient_explanation.when_to_see_doctor}</p>
        </div>

        <div className="disclaimer">
          <p>{data.layer3_patient_explanation.disclaimer}</p>
        </div>
      </section>

      {/* 5. 就医准备包：方案A 自动前置，展示态嵌入（不再需要点击按钮触发） */}
      <section className="visit-prep-entry">
        {visitPrepLoading && !visitPrep && (
          <div className="visit-prep-loading">
            <span className="spinner spinner-inline" aria-hidden="true"></span>
            <p>正在为你整理就医准备清单...</p>
          </div>
        )}

        {/* 出错时小提示，不阻塞主答案 */}
        {visitPrepError && !visitPrep && (
          <div className="visit-prep-soft-error">
            就医准备包暂时无法生成，不影响上面的回答。
          </div>
        )}

        {visitPrep && <VisitPrepView response={visitPrep} />}
      </section>

      {/* 6. 可折叠的「查看支撑证据」区：证据卡片 + 研究进展 + 临床试验，默认折叠 */}
      {evidenceCount > 0 && (
        <section className="evidence-accordion">
          <button
            type="button"
            className="evidence-accordion-toggle"
            aria-expanded={evidenceOpen}
            onClick={() => setEvidenceOpen((v) => !v)}
          >
            <span className="evidence-accordion-title">
              📚 查看支撑证据（{evidenceCount} 条）
            </span>
            <span className={`evidence-accordion-chevron${evidenceOpen ? " open" : ""}`} aria-hidden="true">
              ⌄
            </span>
          </button>

          {evidenceOpen && (
            <div className="evidence-accordion-body">
              {/* 证据卡片 layer2 */}
              {data.layer2_evidence_cards.length > 0 && (
                <div className="evidence-group">
                  <h3 className="evidence-group-title">📊 证据卡片</h3>
                  {data.layer2_evidence_cards.map((card, idx) => (
                    <div key={idx} className="evidence-card-detail">
                      <div className="card-header">
                        <span className="study-type">{card.study_type}</span>
                        <span className={`evidence-level-badge ${card.evidence_level}`}>
                          {card.evidence_level}
                        </span>
                      </div>
                      {card.sample_size && <p><strong>样本量：</strong>{card.sample_size}</p>}
                      {card.intervention && <p><strong>干预：</strong>{card.intervention}</p>}
                      {card.outcome && <p><strong>主要结局：</strong>{card.outcome}</p>}
                      {card.limitations && <p><strong>局限性：</strong>{card.limitations}</p>}
                      {card.source_id && (
                        <p className="source-link">
                          来源：<a href={`https://pubmed.ncbi.nlm.nih.gov/${card.source_id}`} target="_blank" rel="noopener noreferrer">
                            {card.source_id}
                          </a>
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* 研究进展（R12.1/R12.2/R12.3/R12.4） */}
              {data.research_progress.length > 0 && (
                <div className="evidence-group">
                  <h3 className="evidence-group-title">🔬 研究进展</h3>
                  {data.research_progress.map((item, idx) => {
                    const meta = RESEARCH_STAGE_META[item.research_stage];
                    const isUncertain = UNCERTAIN_STAGES.includes(item.research_stage);
                    return (
                      <div key={idx} className="research-progress-item">
                        <div className="research-progress-header">
                          <span className={meta.badgeClass}>{meta.label}</span>
                          <span className="research-evidence-level">证据等级：{item.evidence_level}</span>
                        </div>
                        <p className="research-progress-summary">{item.summary}</p>
                        {isUncertain && (
                          <p className="research-uncertainty-note" role="note">
                            ⚠️ {item.uncertainty_note?.trim() || DEFAULT_UNCERTAINTY_NOTE}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* 临床试验卡片（R11 展示侧） */}
              {data.trial_cards.length > 0 && (
                <div className="evidence-group">
                  <h3 className="evidence-group-title">🧪 临床试验</h3>
                  {data.trial_cards.map((trial, idx) => (
                    <TrialCard key={trial.nct_id || idx} trial={trial} />
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
