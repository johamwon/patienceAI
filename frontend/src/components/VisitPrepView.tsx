import { useState, useCallback } from "react";
import type { VisitPrepPack, VisitPrepResponse } from "../types";

type VisitPrepCategory = {
  key: keyof Pick<
    VisitPrepPack,
    | "questions_for_doctor"
    | "info_to_tell_doctor"
    | "tests_to_request"
    | "treatment_options_to_confirm"
  >;
  title: string;
  icon: string;
  eyebrow: string;
  description: string;
  tone: "ask" | "tell" | "test" | "plan";
};

const CATEGORIES: VisitPrepCategory[] = [
  {
    key: "questions_for_doctor",
    title: "问医生",
    icon: "？",
    eyebrow: "门诊核心问题",
    description: "把最重要的问题提前放在前面，避免见到医生时漏问。",
    tone: "ask",
  },
  {
    key: "info_to_tell_doctor",
    title: "主动告知",
    icon: "i",
    eyebrow: "医生需要知道",
    description: "这些信息能帮助医生更快判断背景和风险。",
    tone: "tell",
  },
  {
    key: "tests_to_request",
    title: "检查确认",
    icon: "＋",
    eyebrow: "带着结果沟通",
    description: "不是要求你自行检查，而是提醒你向医生确认是否需要。",
    tone: "test",
  },
  {
    key: "treatment_options_to_confirm",
    title: "方案确认",
    icon: "✓",
    eyebrow: "下一步怎么走",
    description: "把治疗、观察、复查和转诊等选项问清楚。",
    tone: "plan",
  },
];

type VisitPrepViewProps = {
  // 既可直接接收整个 VisitPrepResponse，也可拆开传字段
  response?: VisitPrepResponse;
  visit_prep_pack?: VisitPrepPack;
  evidence_based?: boolean;
  note?: string;
};

export default function VisitPrepView(props: VisitPrepViewProps) {
  const pack = props.response?.visit_prep_pack ?? props.visit_prep_pack;
  const evidenceBased = props.response?.evidence_based ?? props.evidence_based ?? true;
  const note = props.response?.note ?? props.note;

  // 勾选状态：以 "categoryKey::index" 为唯一键
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  if (!pack) {
    return null;
  }

  const toggle = (itemKey: string) => {
    setChecked((prev) => ({ ...prev, [itemKey]: !prev[itemKey] }));
  };

  // 导出功能：打包成纯文本
  const buildExportText = useCallback(() => {
    const lines: string[] = [];
    lines.push("就医准备包");
    lines.push("=".repeat(36));
    lines.push("");

    for (const category of CATEGORIES) {
      const items = pack[category.key] ?? [];
      if (items.length === 0) continue;
      lines.push(`【${category.title}】${category.description}`);
      lines.push("");
      items.forEach((item, idx) => {
        lines.push(`  ${idx + 1}. ${item}`);
      });
      lines.push("");
    }

    lines.push("-".repeat(36));
    lines.push(pack.positioning_note);
    return lines.join("\n");
  }, [pack]);

  const handleCopy = async () => {
    const text = buildExportText();
    try {
      await navigator.clipboard.writeText(text);
      alert("已复制到剪贴板，可直接粘贴到备忘录或发给家人。");
    } catch {
      // 降级方案：创建临时 textarea
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      alert("已复制到剪贴板。");
    }
  };

  const handleDownload = () => {
    const text = buildExportText();
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "就医准备包.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handlePrint = () => {
    window.print();
  };

  const totalItems = CATEGORIES.reduce((sum, category) => {
    return sum + (pack[category.key]?.length ?? 0);
  }, 0);
  const checkedCount = Object.values(checked).filter(Boolean).length;

  return (
    <div className="visit-prep-view">
      <section className="layer visit-prep-layer">
        <div className="visit-prep-header">
          <div>
            <span className="visit-prep-kicker">就诊前 5 分钟准备</span>
            <h2>就医准备包</h2>
            <p>把焦虑变成一张能带进诊室的沟通清单。</p>
          </div>
          <div className="visit-prep-actions">
            <button type="button" className="visit-prep-btn" onClick={handleCopy} aria-label="复制到剪贴板">
              📋 复制
            </button>
            <button type="button" className="visit-prep-btn" onClick={handleDownload} aria-label="下载为文本文件">
              💾 下载
            </button>
            <button type="button" className="visit-prep-print-btn" onClick={handlePrint} aria-label="打印">
              🖨 打印
            </button>
          </div>
        </div>

        <div className="visit-prep-overview">
          <div className="visit-prep-overview-main">
            <strong>{checkedCount}/{totalItems}</strong>
            <span>已整理</span>
          </div>
          <div className="visit-prep-overview-copy">
            <p>建议先勾选最贴近你情况的条目，门诊时按顺序给医生看。</p>
            <small>所有内容只用于帮助沟通，具体检查和治疗由医生判断。</small>
          </div>
        </div>

        {/* 无针对性证据提示 */}
        {!evidenceBased && (
          <div className="visit-prep-note">
            {note ?? "未找到针对你问题的针对性证据，以下为通用就医准备建议。"}
          </div>
        )}

        <div className="visit-prep-grid">
          {CATEGORIES.map((category) => {
            const items = pack[category.key] ?? [];
            if (items.length === 0) {
              return null;
            }
            return (
              <section
                key={category.key}
                className={`visit-prep-category visit-prep-category-${category.tone}`}
              >
                <div className="visit-prep-category-head">
                  <span className="visit-prep-category-icon">{category.icon}</span>
                  <div>
                    <span>{category.eyebrow}</span>
                    <h3>{category.title}</h3>
                    <p>{category.description}</p>
                  </div>
                </div>
                <ul className="visit-prep-list">
                  {items.map((item, idx) => {
                    const itemKey = `${category.key}::${idx}`;
                    const isChecked = !!checked[itemKey];
                    return (
                      <li
                        key={itemKey}
                        className={`visit-prep-item${isChecked ? " checked" : ""}`}
                      >
                        <label>
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => toggle(itemKey)}
                          />
                          <span className="visit-prep-item-index">{idx + 1}</span>
                          <span className="visit-prep-item-text">{item}</span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>

        {/* 定位说明 */}
        <div className="visit-prep-positioning">
          <p>{pack.positioning_note}</p>
        </div>
      </section>
    </div>
  );
}
