import { useEffect, useState } from "react";
import { listRadarMessages } from "../api";
import type { InAppMessage } from "../types";

type Props = {
  anonUserId: string;
  refreshToken?: number;
};

const STAGE_LABEL: Record<string, string> = {
  breakthrough_rct: "突破性RCT/高等级证据",
  early_trial: "早期临床试验",
  preclinical: "临床前/动物实验",
};

export default function MessageCenter({ anonUserId, refreshToken = 0 }: Props) {
  const [messages, setMessages] = useState<InAppMessage[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = async () => {
    setError(null);
    try {
      setMessages(await listRadarMessages(anonUserId));
    } catch (err: any) {
      setError(err.message || "消息读取失败");
    }
  };

  useEffect(() => {
    void reload();
  }, [anonUserId, refreshToken]);

  return (
    <section className="radar-panel message-center">
      <div className="radar-panel-header">
        <h2>站内消息</h2>
        <button type="button" onClick={reload}>刷新</button>
      </div>
      {error && <p className="radar-status">{error}</p>}
      {messages.length === 0 ? (
        <p className="radar-empty">暂无研究雷达消息。</p>
      ) : (
        messages.map((msg) => (
          <article key={msg.id} className="radar-message">
            <div className="radar-message-title">
              <strong>{msg.digest.disease_keyword}</strong>
              {msg.digest.is_demo && <span className="demo-chip">演示内容</span>}
            </div>
            {msg.digest.items.map((item, idx) => (
              <div key={`${msg.id}-${idx}`} className="radar-message-item">
                <p>{item.summary}</p>
                <span>{STAGE_LABEL[item.research_stage] || item.research_stage}</span>
                <span>证据等级：{item.evidence_level}</span>
                {item.uncertainty_note && <p className="radar-uncertainty">{item.uncertainty_note}</p>}
              </div>
            ))}
          </article>
        ))
      )}
    </section>
  );
}
