import type { Evidence } from "../types";

const SOURCE_TYPE_LABELS: Record<string, string> = {
  paper_en: "英文论文",
  paper_cn: "中文论文",
  meeting: "医学会议",
  guide: "临床指南",
  trial: "临床试验",
  package_insert: "药品说明书",
  unknown: "未知",
};

const EVIDENCE_LEVEL_COLORS: Record<string, string> = {
  high: "#52c41a",
  moderate: "#faad14",
  low: "#ff7875",
  very_low: "#bfbfbf",
};

export default function EvidenceList({ evidences }: { evidences: Evidence[] }) {
  return (
    <div className="evidence-list">
      <h2>检索到的证据 ({evidences.length} 条)</h2>
      {evidences.map((ev) => (
        <div key={ev.id} className="evidence-card">
          <div className="evidence-header">
            <span className="evidence-source">{SOURCE_TYPE_LABELS[ev.source_type] || ev.source_type}</span>
            {ev.evidence_level && (
              <span
                className="evidence-level"
                style={{ backgroundColor: EVIDENCE_LEVEL_COLORS[ev.evidence_level] || "#999" }}
              >
                {ev.evidence_level}
              </span>
            )}
          </div>
          <h3 className="evidence-title">
            {ev.url ? (
              <a href={ev.url} target="_blank" rel="noopener noreferrer">
                {ev.title}
              </a>
            ) : (
              ev.title
            )}
          </h3>
          {ev.authors && <p className="evidence-authors">{ev.authors}</p>}
          {ev.abstract && <p className="evidence-abstract">{ev.abstract.slice(0, 300)}...</p>}
          <div className="evidence-footer">
            {ev.pmid && <span className="evidence-id">PMID: {ev.pmid}</span>}
            {ev.doi && <span className="evidence-id">DOI: {ev.doi}</span>}
            {ev.publish_date && <span className="evidence-date">{ev.publish_date}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
