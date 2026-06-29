/**
 * CompanionBanner（暖场白展示条）— R3.1
 *
 * 在回答最顶部展示小光的共情暖场白（companion_message）。
 * 视觉上像小光说的一句陪伴话，温暖柔和。
 * message 为空（undefined / 空串）时不渲染。
 */
type CompanionBannerProps = {
  /** 后端生成的暖场白文案（companion_message）。为空时不渲染。 */
  message?: string | null;
};

export default function CompanionBanner({ message }: CompanionBannerProps) {
  const text = message?.trim();
  if (!text) return null;

  return (
    <div className="companion-banner" role="note" aria-label="小光的陪伴话">
      <span className="companion-banner-avatar" aria-hidden="true">
        💛
      </span>
      <p className="companion-banner-text">{text}</p>
    </div>
  );
}
