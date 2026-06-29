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
  // 就医准备包（OQ2：嵌入解释结果视图，按需触发）
  visitPrep?: VisitPrepResponse | null;
  visitPrepLoading?: boolean;
  visitPrepError?: string | null;
  onGenerateVisitPrep?: () => void;
};

export default function ExplanationView({
  data,
  query,
  visitPrep,
  visitPrepLoading = false,
  visitPrepError = null,
  onGenerateVisitPrep,
}: ExplanationViewProps) {
  return (
    <div className="explanation-view">
      {/* 暖场白：回答最顶部展示小光的共情陪伴话（R3.1） */}
      <CompanionBanner message={data.companion_message} />

      {/* 风险提示 */}
      {data.risk_message && (
        <div className="risk-banner" style={{ borderColor: RISK_LEVEL_COLORS[data.risk_level] }}>
          <strong>风险提示</strong>
          <p>{data.risk_message}</p>
        </div>
      )}

      {/* 第一层：一句话结论 */}
      <section className="layer layer-1">
        <h2>📌 一句话结论</h2>
        <p className="conclusion-text">{data.layer1_conclusion.text}</p>
        {data.layer1_conclusion.citations.length > 0 && (
          <p className="citations">
            参考：{data.layer1_conclusion.citations.map((c) => `PMID:${c}`).join(", ")}
          </p>
        )}
      </section>

      {/* 第二层：证据卡片 */}
      {data.layer2_evidence_cards.length > 0 && (
        <section className="layer layer-2">
          <h2>📊 证据卡片</h2>
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
        </section>
      )}

      {/* 第三层：患者通俗解释 */}
      <section className="layer layer-3">
        <h2>💡 患者通俗解释</h2>

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

      {/* 研究进展（R12.1/R12.2/R12.3/R12.4）：阶段标签 + 证据等级，早期阶段显式提示不确定性 */}
      {data.research_progress.length > 0 && (
        <section className="layer research-progress">
          <h2>🔬 研究进展</h2>
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
        </section>
      )}

      {/* 临床试验卡片（R11 展示侧）：紧随研究进展 */}
      {data.trial_cards.length > 0 && (
        <section className="layer trial-cards">
          <h2>🧪 临床试验</h2>
          {data.trial_cards.map((trial, idx) => (
            <TrialCard key={trial.nct_id || idx} trial={trial} />
          ))}
        </section>
      )}

      {/* 就医准备包入口（OQ2：嵌入解释结果，按需展开/加载，避免阻塞主流程） */}
      {onGenerateVisitPrep && (
        <section className="layer visit-prep-entry">
          {!visitPrep && (
            <div className="visit-prep-cta">
              <button
                type="button"
                className="visit-prep-generate-btn"
                onClick={onGenerateVisitPrep}
                disabled={visitPrepLoading}
              >
                {visitPrepLoading ? "正在生成就医准备包..." : "📋 生成我的就医准备包"}
              </button>
              <p className="visit-prep-hint">
                根据「{query}」为你整理该问医生的问题、该告知的信息、该索取的检查与该确认的治疗选项。
              </p>
            </div>
          )}

          {visitPrepError && (
            <div className="error-message">{visitPrepError}</div>
          )}

          {visitPrep && <VisitPrepView response={visitPrep} />}
        </section>
      )}
    </div>
  );
}
