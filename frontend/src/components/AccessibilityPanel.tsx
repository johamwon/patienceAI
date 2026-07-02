/**
 * AccessibilityPanel — 无障碍控制面板
 *
 * 面向中老年用户群体，提供：
 * - 字号调节（小/中/大，默认中）
 * - 高对比度模式
 * - 调节状态持久化到 localStorage
 *
 * 以 body data 属性控制全局样式，CSS 通过 [data-font-size] 和 [data-high-contrast] 选择器生效。
 */

import { useState, useEffect, useCallback } from "react";

type FontSize = "small" | "medium" | "large";

const FONT_SIZE_KEY = "yiyuqiao_font_size";
const HIGH_CONTRAST_KEY = "yiyuqiao_high_contrast";

function loadFontSize(): FontSize {
  try {
    const stored = localStorage.getItem(FONT_SIZE_KEY);
    if (stored === "small" || stored === "medium" || stored === "large") return stored;
  } catch {
    // ignore
  }
  return "medium";
}

function saveFontSize(size: FontSize) {
  try {
    localStorage.setItem(FONT_SIZE_KEY, size);
  } catch {
    // ignore
  }
}

function loadHighContrast(): boolean {
  try {
    return localStorage.getItem(HIGH_CONTRAST_KEY) === "true";
  } catch {
    return false;
  }
}

function saveHighContrast(enabled: boolean) {
  try {
    localStorage.setItem(HIGH_CONTRAST_KEY, String(enabled));
  } catch {
    // ignore
  }
}

const FONT_SIZE_LABELS: Record<FontSize, string> = {
  small: "小",
  medium: "中",
  large: "大",
};

export default function AccessibilityPanel() {
  const [fontSize, setFontSize] = useState<FontSize>(loadFontSize);
  const [highContrast, setHighContrast] = useState(loadHighContrast);

  // 同步到 body data 属性
  useEffect(() => {
    document.body.setAttribute("data-font-size", fontSize);
    saveFontSize(fontSize);
  }, [fontSize]);

  useEffect(() => {
    if (highContrast) {
      document.body.setAttribute("data-high-contrast", "true");
    } else {
      document.body.removeAttribute("data-high-contrast");
    }
    saveHighContrast(highContrast);
  }, [highContrast]);

  const cycleFontSize = useCallback(() => {
    const order: FontSize[] = ["medium", "large", "small"];
    const idx = order.indexOf(fontSize);
    setFontSize(order[(idx + 1) % order.length]);
  }, [fontSize]);

  return (
    <div className="accessibility-panel" role="toolbar" aria-label="无障碍调节">
      <button
        type="button"
        className="a11y-btn"
        onClick={cycleFontSize}
        aria-label={`字号：${FONT_SIZE_LABELS[fontSize]}，点击切换`}
        title={`当前字号：${FONT_SIZE_LABELS[fontSize]}（点击切换）`}
      >
        {FONT_SIZE_LABELS[fontSize]}A
      </button>
      <button
        type="button"
        className={`a11y-btn${highContrast ? " active" : ""}`}
        onClick={() => setHighContrast((v) => !v)}
        aria-label={`高对比度模式：${highContrast ? "已开启" : "已关闭"}，点击切换`}
        aria-pressed={highContrast}
        title="高对比度模式"
      >
        ◐
      </button>
    </div>
  );
}
