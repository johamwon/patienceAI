import React from "react";

const Mascot: React.FC = () => {
  return (
    <div className="mascot-container">
      <svg
        className="mascot-svg"
        viewBox="0 0 200 200"
        width="120"
        height="120"
        aria-label="患癌知光吉祥物：小光"
      >
        {/* 光环/光晕 - 代表希望和知识 */}
        <defs>
          <radialGradient id="haloGradient" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#FFF7E6" stopOpacity="0.9" />
            <stop offset="70%" stopColor="#FFE4B5" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#FFD4A3" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="bodyGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#E8F4FD" />
            <stop offset="100%" stopColor="#B3D9F7" />
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

        {/* 眼睛 - 大大的可爱眼睛 */}
        <ellipse cx="82" cy="75" rx="8" ry="10" fill="#333" />
        <ellipse cx="118" cy="75" rx="8" ry="10" fill="#333" />
        {/* 眼睛高光 */}
        <circle cx="85" cy="72" r="3" fill="white" />
        <circle cx="121" cy="72" r="3" fill="white" />

        {/* 腮红 */}
        <ellipse cx="70" cy="88" rx="10" ry="6" fill="url(#cheekGradient)" />
        <ellipse cx="130" cy="88" rx="10" ry="6" fill="url(#cheekGradient)" />

        {/* 微笑 */}
        <path d="M 85 95 Q 100 108 115 95" stroke="#FF6B9D" strokeWidth="3" fill="none" strokeLinecap="round" />

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

        {/* 文字气泡 */}
        <g>
          <rect x="55" y="155" width="90" height="22" rx="11" fill="white" stroke="#E0E0E0" strokeWidth="1" />
          <text x="100" y="169" textAnchor="middle" fontSize="10" fill="#666" fontFamily="Arial, sans-serif">
            我在听呢~
          </text>
        </g>
      </svg>
    </div>
  );
};

export default Mascot;
