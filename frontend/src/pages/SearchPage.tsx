import { useState, useRef, FormEvent } from "react";
import { searchEvidence, explainEvidence, getVisitPrep } from "../api";
import type { SearchResponse, ExplainResponse, VisitPrepResponse } from "../types";
import EvidenceList from "../components/EvidenceList";
import ExplanationView from "../components/ExplanationView";
import Mascot from "../components/Mascot";

const DEMO_QUERIES = [
  "PD-L1阳性到底代表什么？",
  "报告里写的EGFR突变是什么意思？",
  "免疫治疗和化疗有什么区别？",
  "肿瘤标志物升高是不是复发了？",
  "临床试验适合什么样的人参加？",
];

const DISEASE_CATEGORIES = [
  {
    category: "报告看不懂",
    icon: "🫁",
    queries: ["PD-L1表达检测是什么意思", "EGFR突变阳性是什么意思", "Ki-67高说明什么"],
  },
  {
    category: "治疗怎么选",
    icon: "🏥",
    queries: ["免疫治疗和靶向治疗有什么区别", "化疗后还要不要免疫治疗", "临床试验值得了解吗"],
  },
  {
    category: "新药和新研究",
    icon: "🩸",
    queries: ["CAR-T疗法适合实体瘤吗", "ADC药物是什么意思", "最新指南更新怎么看"],
  },
  {
    category: "复查和复发担心",
    icon: "🧬",
    queries: ["肿瘤标志物升高一定是复发吗", "影像报告说结节增大怎么办", "复查前要准备哪些资料"],
  },
  {
    category: "副作用处理",
    icon: "🧠",
    queries: ["免疫治疗皮疹需要注意什么", "化疗后白细胞低怎么办", "靶向药腹泻什么时候就医"],
  },
  {
    category: "网上信息求证",
    icon: "🎀",
    queries: ["断食可以饿死癌细胞吗", "保健品能不能抗癌", "某某新疗法真的有效吗"],
  },
];

function getOrCreateAnonUserId(): string {
  const key = "yiyuqiao_radar_anon_user_id";
  try {
    const existing = localStorage.getItem(key);
    if (existing) return existing;
    const next =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `anon-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(key, next);
    return next;
  } catch {
    return `anon-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const [showDiseaseSelector, setShowDiseaseSelector] = useState(false);

  // 会话 id：组件首次挂载时生成一次，在整个页面会话内保持稳定，
  // 让后端会话记忆（Session_Memory）能够跨多次查询累积（R4）。
  const sessionIdRef = useRef<string>(
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`
  );

  const anonUserIdRef = useRef<string>(getOrCreateAnonUserId());

  // 就医准备包状态（OQ2：嵌入解释结果，按需触发，不阻塞主流程）
  const [visitPrep, setVisitPrep] = useState<VisitPrepResponse | null>(null);
  const [visitPrepLoading, setVisitPrepLoading] = useState(false);
  const [visitPrepError, setVisitPrepError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setSearchResult(null);
    setExplanation(null);
    // 新一次搜索时重置就医准备包状态
    setVisitPrep(null);
    setVisitPrepError(null);
    setVisitPrepLoading(false);

    try {
      const searchRes = await searchEvidence(query);
      setSearchResult(searchRes);
      setIsDemo(searchRes.evidences.length === 0);

      const explainRes = await explainEvidence(
        query,
        searchRes.evidences.slice(0, 5).map((e: { id: string }) => e.id),
        sessionIdRef.current
      );
      setExplanation(explainRes);

      // 方案A：核心答案返回后，自动异步补上就医准备包，不阻塞主答案展示。
      void fetchVisitPrep(query);
    } catch (err: any) {
      setError(err.message || "发生错误，请重试");
    } finally {
      setLoading(false);
    }
  };

  // 自动获取就医准备包：失败时只设错误态、不抛出，避免影响主答案（方案A）。
  const fetchVisitPrep = async (prepQuery: string) => {
    if (!prepQuery.trim()) return;
    setVisitPrepLoading(true);
    setVisitPrepError(null);
    try {
      // 复用当前 query 与稳定的会话 id，让后端会话记忆生效
      const res = await getVisitPrep(prepQuery, sessionIdRef.current);
      setVisitPrep(res);
    } catch (err: any) {
      setVisitPrepError(err.message || "就医准备包生成失败");
    } finally {
      setVisitPrepLoading(false);
    }
  };

  const handleDemoClick = (demoQuery: string) => {
    setQuery(demoQuery);
    setTimeout(() => {
      const form = document.querySelector(".search-form") as HTMLFormElement;
      if (form) form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    }, 100);
  };

  const handleDiseaseClick = (diseaseQuery: string) => {
    setQuery(diseaseQuery);
    setShowDiseaseSelector(false);
    setTimeout(() => {
      const form = document.querySelector(".search-form") as HTMLFormElement;
      if (form) form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    }, 100);
  };

  return (
    <div className="search-page">
      {/* Mascot：拿到解释结果后联动情绪，未出结果时回退 calm（R5.1/R5.3） */}
      <Mascot emotion={explanation?.emotion_state} />

      <header className="header">
        <h1>医语桥</h1>
        <p className="subtitle">面向患者的循证医学检索与通俗化解释</p>
      </header>

      <form onSubmit={handleSubmit} className="search-form">
        <div className="input-wrapper">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入你看不懂的报告、检查指标、药名或治疗问题"
            className="search-input"
            disabled={loading}
          />
          <button type="submit" disabled={loading || !query.trim()}>
            {loading ? "检索中..." : "搜索"}
          </button>
        </div>
      </form>

      {/* Disease Selector Toggle */}
      <div className="disease-selector-toggle">
        <button
          className="toggle-btn"
          onClick={() => setShowDiseaseSelector(!showDiseaseSelector)}
        >
          {showDiseaseSelector ? "收起问题分类" : "按常见困惑选一个问题"}
        </button>
      </div>

      {/* Disease Category Grid */}
      {showDiseaseSelector && (
        <div className="disease-selector">
          {DISEASE_CATEGORIES.map((cat) => (
            <div key={cat.category} className="disease-category">
              <h3>{cat.icon} {cat.category}</h3>
              <div className="disease-queries">
                {cat.queries.map((q) => (
                  <button
                    key={q}
                    className="disease-btn"
                    onClick={() => handleDiseaseClick(q)}
                    disabled={loading}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Demo Queries */}
      <div className="demo-queries">
        <span className="demo-label">你可以这样问：</span>
        {DEMO_QUERIES.map((q) => (
          <button
            key={q}
            className="demo-btn"
            onClick={() => handleDemoClick(q)}
            disabled={loading}
          >
            {q}
          </button>
        ))}
      </div>

      {isDemo && (
        <div className="demo-notice">
          ℹ️ 当前使用演示数据（KnowS API Key 申请中）。填入 LLM_API_KEY 后可体验完整功能。
        </div>
      )}

      {error && <div className="error-message">{error}</div>}

      {searchResult && !explanation && (
        <div className="loading-explanation">
          <div className="spinner"></div>
          <p>正在生成通俗化解释，请稍候...</p>
        </div>
      )}

      {explanation && (
        <ExplanationView
          data={explanation}
          query={query}
          visitPrep={visitPrep}
          visitPrepLoading={visitPrepLoading}
          visitPrepError={visitPrepError}
          anonUserId={anonUserIdRef.current}
        />
      )}

      {searchResult && searchResult.evidences.length > 0 && !explanation && (
        <EvidenceList evidences={searchResult.evidences} />
      )}
    </div>
  );
}
