import type {
  SearchResponse,
  ExplainResponse,
  VisitPrepResponse,
  Subscription,
  InAppMessage,
  RadarChannels,
  ClarificationAnswer,
  ClarifyResponse,
} from "../types";

// 生产环境（同源部署）走相对路径，开发环境用 Vite 代理或显式地址
const API_BASE = import.meta.env.DEV
  ? (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000")
  : "";

export async function clarifyQuery(query: string): Promise<ClarifyResponse> {
  const res = await fetch(`${API_BASE}/api/v1/clarify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error(`追问生成失败: ${res.status}`);
  return res.json();
}

export async function searchEvidence(
  query: string,
  maxResults = 20,
  clarificationAnswers: ClarificationAnswer[] = []
): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE}/api/v1/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      max_results: maxResults,
      clarification_answers: clarificationAnswers,
    }),
  });
  if (!res.ok) throw new Error(`搜索失败: ${res.status}`);
  return res.json();
}

export async function explainEvidence(
  query: string,
  evidenceIds?: string[],
  sessionId?: string,
  clarificationAnswers: ClarificationAnswer[] = []
): Promise<ExplainResponse> {
  const res = await fetch(`${API_BASE}/api/v1/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      evidence_ids: evidenceIds,
      session_id: sessionId,
      clarification_answers: clarificationAnswers,
    }),
  });
  if (!res.ok) throw new Error(`解释失败: ${res.status}`);
  return res.json();
}

export async function getVisitPrep(query: string, sessionId?: string): Promise<VisitPrepResponse> {
  const res = await fetch(`${API_BASE}/api/v1/visit-prep`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(`就医准备包生成失败: ${res.status}`);
  return res.json();
}

export async function evaluateResponse(predictions: any[], references: any[]) {
  const res = await fetch(`${API_BASE}/api/v1/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ predictions, references }),
  });
  if (!res.ok) throw new Error(`评测失败: ${res.status}`);
  return res.json();
}

export async function subscribeRadar(
  anonUserId: string,
  diseaseKeyword: string,
  entitiesJson?: string,
): Promise<Subscription> {
  const res = await fetch(`${API_BASE}/api/v1/radar/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      anon_user_id: anonUserId,
      disease_keyword: diseaseKeyword,
      entities_json: entitiesJson,
    }),
  });
  if (!res.ok) throw new Error(`订阅失败: ${res.status}`);
  return res.json();
}

export async function listRadarSubscriptions(anonUserId: string): Promise<Subscription[]> {
  const res = await fetch(`${API_BASE}/api/v1/radar/subscriptions?anon_user_id=${encodeURIComponent(anonUserId)}`);
  if (!res.ok) throw new Error(`订阅列表读取失败: ${res.status}`);
  return res.json();
}

export async function revokeRadarSubscription(subscriptionId: string) {
  const res = await fetch(`${API_BASE}/api/v1/radar/subscriptions/${subscriptionId}/revoke`, { method: "POST" });
  if (!res.ok) throw new Error(`撤销订阅失败: ${res.status}`);
  return res.json();
}

export async function deleteRadarSubscription(subscriptionId: string) {
  const res = await fetch(`${API_BASE}/api/v1/radar/subscriptions/${subscriptionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`删除订阅失败: ${res.status}`);
  return res.json();
}

export async function getRadarChannels(anonUserId: string): Promise<RadarChannels> {
  const res = await fetch(`${API_BASE}/api/v1/radar/channels?anon_user_id=${encodeURIComponent(anonUserId)}`);
  if (!res.ok) throw new Error(`渠道状态读取失败: ${res.status}`);
  return res.json();
}

export async function setRadarChannel(anonUserId: string, channel: keyof RadarChannels, contact?: string) {
  const res = await fetch(`${API_BASE}/api/v1/radar/channels`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ anon_user_id: anonUserId, channel, contact }),
  });
  if (!res.ok) throw new Error(`开启渠道失败: ${res.status}`);
  return res.json();
}

export async function unsetRadarChannel(anonUserId: string, channel: keyof RadarChannels) {
  const res = await fetch(
    `${API_BASE}/api/v1/radar/channels/${channel}?anon_user_id=${encodeURIComponent(anonUserId)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error(`关闭渠道失败: ${res.status}`);
  return res.json();
}

export async function deleteRadarUserData(anonUserId: string) {
  const res = await fetch(`${API_BASE}/api/v1/radar/user/${encodeURIComponent(anonUserId)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`删除全部数据失败: ${res.status}`);
  return res.json();
}

export async function listRadarMessages(anonUserId: string): Promise<InAppMessage[]> {
  const res = await fetch(`${API_BASE}/api/v1/radar/messages?anon_user_id=${encodeURIComponent(anonUserId)}`);
  if (!res.ok) throw new Error(`站内消息读取失败: ${res.status}`);
  return res.json();
}

export async function triggerRadarDemo(subscriptionId: string) {
  const res = await fetch(`${API_BASE}/api/v1/radar/demo/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subscription_id: subscriptionId }),
  });
  if (!res.ok) throw new Error(`演示触发失败: ${res.status}`);
  return res.json();
}
