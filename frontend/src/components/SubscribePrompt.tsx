import { useState } from "react";
import { setRadarChannel, subscribeRadar } from "../api";

type SubscribePromptProps = {
  anonUserId: string;
  offer?: { disease_keyword: string; prompt_text: string };
  onSubscribed?: () => void;
};

export default function SubscribePrompt({ anonUserId, offer, onSubscribed }: SubscribePromptProps) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  if (!offer) return null;

  const handleSubscribe = async () => {
    const normalizedEmail = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      setMessage("请先填写一个可以接收提醒的邮箱。");
      return;
    }

    setLoading(true);
    setMessage(null);
    try {
      await subscribeRadar(anonUserId, offer.disease_keyword);
      await setRadarChannel(anonUserId, "email", normalizedEmail);
      setMessage("已订阅。以后有高质量新进展时，小光会通过邮件提醒你。");
      onSubscribed?.();
    } catch (err: any) {
      setMessage(err.message || "订阅失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="subscribe-prompt">
      <div>
        <span className="subscribe-prompt-label">后续提醒</span>
        <p>{offer.prompt_text}</p>
      </div>
      <div className="subscribe-prompt-actions">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="填写邮箱接收提醒"
          disabled={loading}
        />
        <button type="button" onClick={handleSubscribe} disabled={loading}>
          {loading ? "订阅中..." : "邮件订阅"}
        </button>
      </div>
      {message && <p className="subscribe-prompt-status">{message}</p>}
    </section>
  );
}
