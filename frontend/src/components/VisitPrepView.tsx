import { useState } from "react";
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
};

const CATEGORIES: VisitPrepCategory[] = [
  { key: "questions_for_doctor", title: "该问医生的问题", icon: "❓" },
  { key: "info_to_tell_doctor", title: "该主动告知的信息", icon: "🗣️" },
  { key: "tests_to_request", title: "该索取的检查", icon: "🔬" },
  { key: "treatment_options_to_confirm", title: "该确认的治疗选项", icon: "💊" },
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

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="visit-prep-view">
      <section className="layer visit-prep-layer">
        <div className="visit-prep-header">
          <h2>🩺 就医准备包</h2>
          <button type="button" className="visit-prep-print-btn" onClick={handlePrint}>
            🖨️ 打印 / 导出
          </button>
        </div>

        {/* 无针对性证据提示 */}
        {!evidenceBased && (
          <div className="visit-prep-note">
            {note ?? "未找到针对你问题的针对性证据，以下为通用就医准备建议。"}
          </div>
        )}

        {CATEGORIES.map((category) => {
          const items = pack[category.key] ?? [];
          if (items.length === 0) {
            return null;
          }
          return (
            <div key={category.key} className="visit-prep-category">
              <h3>
                {category.icon} {category.title}
              </h3>
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
                        <span className="visit-prep-item-text">{item}</span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}

        {/* 定位说明 */}
        <div className="visit-prep-positioning">
          <p>{pack.positioning_note}</p>
        </div>
      </section>
    </div>
  );
}
