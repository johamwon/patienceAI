import type { GateResult } from "../types";

type Props = {
  gate: GateResult;
};

const STATUS_ICONS: Record<string, string> = {
  block_diagnosis: "\u{1F3E5}",   // hospital
  block_emergency: "\u{1F6A8}",   // siren
  block_off_topic: "\u{1F4CB}",   // clipboard
  redirect_companion: "\u{1FA90}", // ring buoy
  redirect_clarify: "\u{2753}",    // question mark
};

const STATUS_TITLES: Record<string, string> = {
  block_diagnosis: "请咨询专业医生",
  block_emergency: "请立即就医",
  block_off_topic: "我能帮你的方向",
  redirect_companion: "我在这里陪你",
  redirect_clarify: "需要更多信息",
};

export default function GateBlock({ gate }: Props) {
  const icon = STATUS_ICONS[gate.status] || "\u2139";
  const title = STATUS_TITLES[gate.status] || "提示";

  const messageLines = gate.user_message.split("\n").filter(Boolean);

  return (
    <div className={`gate-block gate-${gate.status}`} role="alert">
      <div className="gate-icon">{icon}</div>
      <h3 className="gate-title">{title}</h3>
      <div className="gate-body">
        {messageLines.map((line, i) => (
          <p key={i}>{line}</p>
        ))}
      </div>
      {gate.status === "redirect_companion" && (
        <div className="gate-companion-note">
          我听到了你的担忧。如果你愿意，可以告诉我更多，我会尽力帮你找到可靠的医学信息。
        </div>
      )}
      {gate.status === "block_diagnosis" && (
        <div className="gate-actions">
          <a
            href="https://www.114yygh.com"
            target="_blank"
            rel="noopener noreferrer"
            className="gate-action-btn"
          >
            预约挂号指引
          </a>
        </div>
      )}
    </div>
  );
}
