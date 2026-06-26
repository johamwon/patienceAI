const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function searchEvidence(query: string, maxResults = 20): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE}/api/v1/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, max_results: maxResults }),
  });
  if (!res.ok) throw new Error(`搜索失败: ${res.status}`);
  return res.json();
}

export async function explainEvidence(query: string, evidenceIds?: string[]): Promise<ExplainResponse> {
  const res = await fetch(`${API_BASE}/api/v1/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, evidence_ids: evidenceIds }),
  });
  if (!res.ok) throw new Error(`解释失败: ${res.status}`);
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
