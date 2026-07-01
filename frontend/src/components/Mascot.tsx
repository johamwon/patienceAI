import React from "react";
import type { EmotionState } from "../types";

/**
 * 情绪 → 表情/气泡配置（R5.2）
 *
 * 每个情绪状态提供：
 *  - bubbleText: 气泡文案（仅情绪陪伴话术，不含诊断结论或个体化治疗建议，R5.4）
 *  - mouthPath:  SVG 嘴型路径，用于辨识表情差异
 *  - bodyStart/bodyEnd: 身体渐变色基调，区分整体情绪氛围
 *  - cheekOpacity: 腮红可见度（关切/严肃情绪下淡化）
 *  - browPath:    可选眉毛路径，用于强化关切/严肃表情（urgent/panic）
 */
type EmotionVisual = {
  bubbleText: string;
  mouthPath: string;
  bodyStart: string;
  bodyEnd: string;
  cheekOpacity: number;
  browPath?: string;
};

const EMOTION_CONFIG: Record<EmotionState, EmotionVisual> = {
  // 平静求知（默认）：友好微笑
  calm: {
    bubbleText: "我在听呢~",
    mouthPath: "M 85 95 Q 100 108 115 95",
    bodyStart: "#E8F4FD",
    bodyEnd: "#B3D9F7",
    cheekOpacity: 1,
  },
  // 恐慌：关切表情 + 安抚
  panic: {
    bubbleText: "别怕，我陪着你~",
    mouthPath: "M 88 100 Q 100 96 112 100",
    bodyStart: "#FDEFE8",
    bodyEnd: "#F7D4B3",
    cheekOpacity: 0.7,
    browPath: "M 74 62 Q 82 58 90 62 M 110 62 Q 118 58 126 62",
  },
  // 焦虑：温和表情 + 安定
  anxiety: {
    bubbleText: "我们慢慢来~",
    mouthPath: "M 86 98 Q 100 104 114 98",
    bodyStart: "#F2F0FB",
    bodyEnd: "#D8CFF0",
    cheekOpacity: 0.85,
  },
  // 绝望：温柔表情 + 托住
  despair: {
    bubbleText: "我一直在你身边~",
    mouthPath: "M 87 99 Q 100 103 113 99",
    bodyStart: "#EAF6F0",
    bodyEnd: "#C2E6D5",
    cheekOpacity: 0.9,
  },
  // 急症倾向：关切/严肃表情 + 强调安全/就医
  urgent: {
    bubbleText: "你的安全最重要",
    mouthPath: "M 88 101 L 112 101",
    bodyStart: "#FDEAEA",
    bodyEnd: "#F5C2C2",
    cheekOpacity: 0.5,
    browPath: "M 74 60 Q 82 57 90 61 M 110 61 Q 118 57 126 60",
  },
};

const DEFAULT_EMOTION: EmotionState = "calm";

/**
 * 将任意输入归一化为已知情绪状态；缺失或无法识别 → calm（R5.3）。
 */
function resolveEmotion(emotion?: EmotionState | string): EmotionVisual {
  if (emotion && Object.prototype.hasOwnProperty.call(EMOTION_CONFIG, emotion)) {
    return EMOTION_CONFIG[emotion as EmotionState];
  }
  return EMOTION_CONFIG[DEFAULT_EMOTION];
}

type MascotProps = {
  /** 情绪状态，缺失或无法识别时回退为 calm（R5.1 / R5.3） */
  emotion?: EmotionState | string;
  /** 尺寸（像素），默认 120。用于在对话气泡区作为小头像复用。 */
  size?: number;
  /** 是否显示内置文字气泡，默认 true。作为头像复用时设为 false。 */
  showBubble?: boolean;
  /** 是否包裹默认的浮动容器，默认 true。作为内联头像时设为 false。 */
  withContainer?: boolean;
};

const Mascot: React.FC<MascotProps> = ({
  emotion,
  size = 120,
  showBubble = true,
  withContainer = true,
}) => {
  const visual = resolveEmotion(emotion);

  const svg = (
      <svg
        className="mascot-svg"
        viewBox="0 0 200 200"
        width={size}
        height={size}
        aria-label={`医语桥吉祥物：小光（${visual.bubbleText}）`}
      >
        {/* 光环/光晕 - 代表希望和知识 */}
        <defs>
          <radialGradient id="haloGradient" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#FFF7E6" stopOpacity="0.9" />
            <stop offset="70%" stopColor="#FFE4B5" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#FFD4A3" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="bodyGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={visual.bodyStart} />
            <stop offset="100%" stopColor={visual.bodyEnd} />
          </linearGradient>
          <linearGradient id="cheekGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FFB6C1" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#FFC0CB" stopOpacity="0.3" />
          </linearGradient>
        </defs>

        {/* 光晕背景 */}
        <circle cx="100" cy="100" r="95" fill="url(#haloGradient)" />

        {/* 身体 - 圆润的胶囊形状 */}
        <ellipse cx="100" cy="115" rx="55" ry="60" fill="url(#bodyGradient)" stroke="#87CEEB" strokeWidth="2.5" />

        {/* 头部 */}
        <circle cx="100" cy="75" r="45" fill="#F0F8FF" stroke="#87CEEB" strokeWidth="2.5" />

        {/* 头发/发髻 - 像博士帽的小圆顶 */}
        <circle cx="100" cy="35" r="15" fill="#5B9BD5" />
        <rect x="95" y="25" width="10" height="15" rx="5" fill="#5B9BD5" />

        {/* 眉毛 - 仅在关切/严肃情绪下显示，强化表情差异 */}
        {visual.browPath && (
          <path d={visual.browPath} stroke="#5B7B9B" strokeWidth="2.5" fill="none" strokeLinecap="round" />
        )}

        {/* 眼睛 - 大大的可爱眼睛 */}
        <ellipse cx="82" cy="75" rx="8" ry="10" fill="#333" />
        <ellipse cx="118" cy="75" rx="8" ry="10" fill="#333" />
        {/* 眼睛高光 */}
        <circle cx="85" cy="72" r="3" fill="white" />
        <circle cx="121" cy="72" r="3" fill="white" />

        {/* 腮红 */}
        <ellipse cx="70" cy="88" rx="10" ry="6" fill="url(#cheekGradient)" opacity={visual.cheekOpacity} />
        <ellipse cx="130" cy="88" rx="10" ry="6" fill="url(#cheekGradient)" opacity={visual.cheekOpacity} />

        {/* 嘴型 - 随情绪状态变化 */}
        <path d={visual.mouthPath} stroke="#FF6B9D" strokeWidth="3" fill="none" strokeLinecap="round" />

        {/* 听诊器 - 代表医疗 */}
        <path d="M 60 100 Q 50 120 55 135" stroke="#5B9BD5" strokeWidth="3" fill="none" strokeLinecap="round" />
        <circle cx="55" cy="140" r="8" fill="#FF6B9D" stroke="#5B9BD5" strokeWidth="2" />
        <path d="M 140 100 Q 150 120 145 135" stroke="#5B9BD5" strokeWidth="3" fill="none" strokeLinecap="round" />
        <circle cx="145" cy="140" r="8" fill="#FF6B9D" stroke="#5B9BD5" strokeWidth="2" />

        {/* 手中的小星星 - 代表希望 */}
        <g transform="translate(155, 60) rotate(15)">
          <polygon
            points="0,-10 3,-3 10,-3 5,2 7,10 0,6 -7,10 -5,2 -10,-3 -3,-3"
            fill="#FFD700"
            stroke="#FFA500"
            strokeWidth="1"
          />
        </g>

        {/* 文字气泡 - 随情绪状态变化（作为内联头像时可隐藏） */}
        {showBubble && (
          <g>
            <rect x="40" y="155" width="120" height="22" rx="11" fill="white" stroke="#E0E0E0" strokeWidth="1" />
            <text x="100" y="169" textAnchor="middle" fontSize="10" fill="#666" fontFamily="Arial, sans-serif">
              {visual.bubbleText}
            </text>
          </g>
        )}
      </svg>
  );

  if (!withContainer) {
    return svg;
  }

  return <div className="mascot-container">{svg}</div>;
};

export default Mascot;
