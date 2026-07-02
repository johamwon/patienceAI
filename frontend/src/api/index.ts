import type { SearchResponse, ExplainResponse, VisitPrepResponse } from "../types";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

export async function searchEvidence(query: string, maxResults = 20): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE}/api/v1/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, max_results: maxResults }),
  });
  if (!res.ok) throw new Error(`搜索失败: ${res.status}`);
  return res.json();
}

export async function explainEvidence(query: string, evidenceIds?: string[], sessionId?: string): Promise<ExplainResponse> {
  const res = await fetch(`${API_BASE}/api/v1/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, evidence_ids: evidenceIds, session_id: sessionId }),
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
