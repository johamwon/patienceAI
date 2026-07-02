import { useEffect, useState } from "react";
import {
  deleteRadarSubscription,
  deleteRadarUserData,
  getRadarChannels,
  listRadarSubscriptions,
  revokeRadarSubscription,
  setRadarChannel,
  triggerRadarDemo,
  unsetRadarChannel,
} from "../api";
import type { RadarChannels, Subscription } from "../types";

type Props = {
  anonUserId: string;
  refreshToken?: number;
  onChanged?: () => void;
};

export default function SubscriptionManager({ anonUserId, refreshToken = 0, onChanged }: Props) {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [channels, setChannels] = useState<RadarChannels>({ in_app: false, email: false, wechat: false });
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const demoMode = import.meta.env.VITE_RADAR_DEMO_MODE === "true";

  const reload = async () => {
    setLoading(true);
    try {
      const [nextSubs, nextChannels] = await Promise.all([
        listRadarSubscriptions(anonUserId),
        getRadarChannels(anonUserId),
      ]);
      setSubs(nextSubs);
      setChannels(nextChannels);
    } catch (err: any) {
      setStatus(err.message || "订阅信息读取失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
  }, [anonUserId, refreshToken]);

  const run = async (task: () => Promise<any>, okText: string) => {
    setStatus(null);
    try {
      await task();
      setStatus(okText);
      await reload();
      onChanged?.();
    } catch (err: any) {
      setStatus(err.message || "操作失败");
    }
  };

  return (
    <section className="radar-panel">
      <div className="radar-panel-header">
        <h2>研究雷达</h2>
        <button type="button" onClick={reload} disabled={loading}>刷新</button>
      </div>

      <div className="radar-subscriptions">
        {subs.length === 0 ? (
          <p className="radar-empty">还没有订阅。查询并解释某个病症后，可在结果里订阅最新研究动态。</p>
        ) : (
          subs.map((sub) => (
            <div key={sub.id} className="radar-subscription-item">
              <span>{sub.disease_keyword}</span>
              <div className="radar-actions">
                {demoMode && (
                  <button type="button" onClick={() => run(() => triggerRadarDemo(sub.id), "已尝试触发演示推送，请查看站内消息。")}>
                    演示推送
                  </button>
                )}
                <button type="button" onClick={() => run(() => revokeRadarSubscription(sub.id), "已撤销订阅。")}>
                  撤销
                </button>
                <button type="button" onClick={() => run(() => deleteRadarSubscription(sub.id), "已删除订阅。")}>
                  删除
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="radar-channel-grid">
        <label className="radar-channel">
          <input
            type="checkbox"
            checked={channels.in_app}
            onChange={(e) =>
              run(
                () => e.target.checked ? setRadarChannel(anonUserId, "in_app") : unsetRadarChannel(anonUserId, "in_app"),
                e.target.checked ? "已开启站内消息。" : "已关闭站内消息。"
              )
            }
          />
          <span>站内消息</span>
        </label>

        <label className="radar-channel radar-channel-email">
          <input
            type="checkbox"
            checked={channels.email}
            onChange={(e) =>
              run(
                () => e.target.checked ? setRadarChannel(anonUserId, "email", email) : unsetRadarChannel(anonUserId, "email"),
                e.target.checked ? "已开启邮件渠道。" : "已关闭邮件渠道并删除邮箱。"
              )
            }
          />
          <span>邮件</span>
          <input
            className="radar-email-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="邮箱地址"
          />
        </label>

        <div className="radar-channel disabled">
          <span>微信</span>
          <small>已预留接口，当前环境先降级为站内和邮件。</small>
        </div>
      </div>

      <button
        type="button"
        className="radar-delete-all"
        onClick={() => run(() => deleteRadarUserData(anonUserId), "已删除当前匿名身份下的订阅、渠道和站内消息。")}
      >
        删除全部雷达数据
      </button>

      {status && <p className="radar-status">{status}</p>}
    </section>
  );
}
