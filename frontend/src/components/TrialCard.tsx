import type { TrialCard as TrialCardData } from "../types";

const FIELD_FALLBACK = "信息未提供";
// 入组提示为合规必备文本，缺失时回退到默认提示而非"信息未提供"（R11.5）。
const NOTE_FALLBACK = "是否符合入组需经临床医生评估确认。";

// 任一字段缺失/为空时回退到"信息未提供"，确保整张卡片不被隐藏（R11.4）。
// 后端模型已对缺失字段给默认值"信息未提供"，这里再兜底处理空字符串。
function display(value?: string): string {
  const trimmed = (value ?? "").trim();
  return trimmed.length > 0 ? trimmed : FIELD_FALLBACK;
}

// 招募状态仅作为客观信息展示，措辞中性，不暗示对患者的疗效或入组承诺（R11.6）。
export default function TrialCard({ trial }: { trial: TrialCardData }) {
  return (
    <div className="trial-card">
      <div className="trial-card-header">
        <span className="trial-card-tag">临床试验</span>
        <span className="trial-card-nct">{display(trial.nct_id)}</span>
      </div>

      <dl className="trial-card-fields">
        <div className="trial-card-field">
          <dt>招募状态</dt>
          <dd>{display(trial.recruitment_status)}</dd>
        </div>
        <div className="trial-card-field">
          <dt>试验阶段</dt>
          <dd>{display(trial.phase)}</dd>
        </div>
        <div className="trial-card-field">
          <dt>入排标准</dt>
          <dd>{display(trial.eligibility)}</dd>
        </div>
        <div className="trial-card-field">
          <dt>地点</dt>
          <dd>{display(trial.location)}</dd>
        </div>
      </dl>

      {/* 提示文本：是否符合入组需经临床医生评估确认（R11.5） */}
      <p className="trial-card-note">
        {(trial.note ?? "").trim() || NOTE_FALLBACK}
      </p>
    </div>
  );
}
