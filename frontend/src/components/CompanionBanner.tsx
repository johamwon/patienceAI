/**
 * CompanionBanner（暖场白 / "小光对你说" 对话气泡区）— R3.1
 *
 * 在回答最顶部展示小光的共情暖场白（companion_message）。
 * 视觉上整合 Mascot 头像 + 对话气泡，营造"小光对你说"的陪伴感。
 * message 为空（undefined / 空串）时不渲染。
 */
import type { EmotionState } from "../types";
import Mascot from "./Mascot";

type CompanionBannerProps = {
  /** 后端生成的暖场白文案（companion_message）。为空时不渲染。 */
  message?: string | null;
  /** 情绪状态，用于联动小光头像表情（缺失回退 calm）。 */
  emotion?: EmotionState | string;
};

export default function CompanionBanner({ message, emotion }: CompanionBannerProps) {
  const text = message?.trim();
  if (!text) return null;

  return (
    <div className="companion-banner" role="note" aria-label="小光对你说">
      <div className="companion-banner-avatar" aria-hidden="true">
        <Mascot emotion={emotion} size={64} showBubble={false} withContainer={false} />
      </div>
      <div className="companion-banner-body">
        <span className="companion-banner-name">小光对你说</span>
        <p className="companion-banner-text">{text}</p>
      </div>
    </div>
  );
}
