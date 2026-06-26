import type { ExplainResponse } from "../types";

const RISK_LEVEL_COLORS: Record<string, string> = {
  low: "#52c41a",
  medium: "#faad14",
  high: "#ff4d4f",
  prohibited: "#ff4d4f",
};

export default function ExplanationView({ data, query }: { data: ExplainResponse; query: string }) {
  return (
    <div className="explanation-view">
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
    </div>
  );
}
