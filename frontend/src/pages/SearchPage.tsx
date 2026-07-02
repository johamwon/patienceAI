import { useState, useRef, FormEvent, useEffect } from "react";
import { clarifyQuery, searchEvidence, explainEvidence, getVisitPrep } from "../api";
import type {
  ClarificationAnswer,
  SearchResponse,
  ExplainResponse,
  VisitPrepResponse,
  GateResult,
} from "../types";
import EvidenceList from "../components/EvidenceList";
import ExplanationView from "../components/ExplanationView";
import GateBlock from "../components/GateBlock";
import Mascot from "../components/Mascot";
import AccessibilityPanel from "../components/AccessibilityPanel";

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

// 搜索历史：localStorage 存储最多 20 条
const HISTORY_KEY = "yiyuqiao_search_history";
const MAX_HISTORY = 20;

function loadSearchHistory(): string[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveSearchHistory(queries: string[]) {
  try {
    const deduped = [...new Set(queries)].slice(0, MAX_HISTORY);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(deduped));
  } catch {
    // silent fail
  }
}

function addToSearchHistory(newQuery: string): string[] {
  const trimmed = newQuery.trim();
  if (!trimmed) return loadSearchHistory();
  const history = loadSearchHistory().filter((q) => q !== trimmed);
  history.unshift(trimmed);
  saveSearchHistory(history);
  return history;
}

function clearSearchHistory() {
  try {
    localStorage.removeItem(HISTORY_KEY);
  } catch {
    // silent
  }
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const [gate, setGate] = useState<GateResult | null>(null);
  const [showDiseaseSelector, setShowDiseaseSelector] = useState(false);
  const [clarifying, setClarifying] = useState(false);
  const [clarificationQuestions, setClarificationQuestions] = useState<string[]>([]);
  const [clarificationIndex, setClarificationIndex] = useState(0);
  const [clarificationInput, setClarificationInput] = useState("");
  const [clarificationAnswers, setClarificationAnswers] = useState<ClarificationAnswer[]>([]);
  const [pendingQuery, setPendingQuery] = useState("");
  // 非阻塞追问建议：答案展示后，LLM 后台判断是否需要补充信息
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [searchHistory, setSearchHistory] = useState<string[]>(() => loadSearchHistory());

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

  const resetResults = () => {
    setError(null);
    setSearchResult(null);
    setExplanation(null);
    setGate(null);
    setVisitPrep(null);
    setVisitPrepError(null);
    setVisitPrepLoading(false);
  };

  const resetClarification = () => {
    setClarifying(false);
    setClarificationQuestions([]);
    setClarificationIndex(0);
    setClarificationInput("");
    setClarificationAnswers([]);
    setPendingQuery("");
  };

  const buildQueryForPrep = (baseQuery: string, answers: ClarificationAnswer[]) => {
    const details = answers
      .filter((item) => item.answer.trim())
      .map((item) => `- ${item.question}：${item.answer.trim()}`)
      .join("\n");
    return details ? `${baseQuery}\n\n用户补充信息：\n${details}` : baseQuery;
  };

  const runSearchAndExplain = async (
    baseQuery: string,
    answers: ClarificationAnswer[] = []
  ) => {
    setLoading(true);
    setError(null);

    try {
      const searchRes = await searchEvidence(baseQuery, 20, answers);
      setSearchResult(searchRes);
      setIsDemo(searchRes.evidences.length === 0);

      // 门禁拦截：非 pass 时展示 GateBlock，不进入解释流程
      if (searchRes.gate && searchRes.gate.status !== "pass") {
        setGate(searchRes.gate);
        setLoading(false);
        return;
      }

      // 保存到搜索历史
      setSearchHistory(addToSearchHistory(baseQuery));

      const explainRes = await explainEvidence(
        baseQuery,
        searchRes.evidences.slice(0, 5).map((e: { id: string }) => e.id),
        sessionIdRef.current,
        answers
      );
      setExplanation(explainRes);

      // 非阻塞追问建议：答案已展示，后台异步判断是否需要补充信息
      void clarifyQuery(baseQuery).then((clarification) => {
        const qs = (clarification.questions || []).filter((item: string) => item.trim());
        if (clarification.needs_clarification && qs.length > 0) {
          setSuggestedQuestions(qs);
        }
      }).catch(() => {
        // 后台追问失败不影响主流程
      });

      // 方案A：核心答案返回后，自动异步补上就医准备包，不阻塞主答案展示。
      void fetchVisitPrep(buildQueryForPrep(baseQuery, answers));
    } catch (err: any) {
      setError(err.message || "发生错误，请重试");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const submittedQuery = query.trim();
    if (!submittedQuery) return;

    resetResults();
    resetClarification();
    setSuggestedQuestions([]);
    setLoading(true);

    // 不再阻塞：直接进入搜索，追问改为答案后的非阻塞建议
    await runSearchAndExplain(submittedQuery, []);
  };

  const handleClarificationSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const answer = clarificationInput.trim();
    const question = clarificationQuestions[clarificationIndex];
    if (!answer || !question) {
      setError("请先回答当前问题，再继续生成答案。");
      return;
    }

    setError(null);
    const nextAnswers = [...clarificationAnswers, { question, answer }];
    setClarificationAnswers(nextAnswers);

    const nextIndex = clarificationIndex + 1;
    if (nextIndex < clarificationQuestions.length) {
      setClarificationIndex(nextIndex);
      setClarificationInput("");
      return;
    }

    setClarifying(false);
    setClarificationInput("");
    setSearchHistory(addToSearchHistory(pendingQuery || query.trim()));
    await runSearchAndExplain(pendingQuery || query.trim(), nextAnswers);
  };

  // 跳过追问，直接搜索（带上已回答的问题）
  const handleSkipClarification = () => {
    setClarifying(false);
    setClarificationInput("");
    setSearchHistory(addToSearchHistory(pendingQuery || query.trim()));
    void runSearchAndExplain(
      pendingQuery || query.trim(),
      clarificationAnswers  // 已答的带上，没答的空着
    );
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
      <AccessibilityPanel />
      {/* Mascot：拿到解释结果后联动情绪，未出结果时回退 calm（R5.1/R5.3） */}
      <Mascot emotion={explanation?.emotion_state} />

      <header className="header">
        <h1>
          医语桥
          {isDemo && <span className="header-demo-badge" aria-label="演示模式">DEMO</span>}
        </h1>
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
            disabled={loading || clarifying}
            aria-label="搜索医学问题"
          />
          <button type="submit" disabled={loading || clarifying || !query.trim()} aria-label="开始搜索">
            {loading ? "处理中..." : "搜索"}
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
                    disabled={loading || clarifying}
                    aria-label={`按问题分类: ${cat.category} - ${q}`}
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
            disabled={loading || clarifying}
            aria-label={`演示问题: ${q}`}
          >
            {q}
          </button>
        ))}
      </div>

      {isDemo && (
        <div className="demo-notice">
          当前为演示模式，结果来自预置场景。配置 API Key 后可体验全功能检索。
        </div>
      )}

      {/* 搜索历史 */}
      {searchHistory.length > 0 && !searchResult && (
        <div className="search-history">
          <div className="search-history-header">
            <span>最近搜索</span>
            <button
              className="search-history-clear"
              onClick={() => { clearSearchHistory(); setSearchHistory([]); }}
              aria-label="清除搜索历史"
            >
              清除
            </button>
          </div>
          <div className="search-history-items">
            {searchHistory.slice(0, 8).map((q) => (
              <button
                key={q}
                className="search-history-btn"
                onClick={() => handleDemoClick(q)}
                disabled={loading || clarifying}
                aria-label={`搜索: ${q}`}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <div className="error-message">{error}</div>}

      {gate && <GateBlock gate={gate} />}

      {clarifying && clarificationQuestions.length > 0 && (
        <form className="clarification-flow" onSubmit={handleClarificationSubmit}>
          <div className="clarification-flow-header">
            <span>补充信息</span>
            <strong>
              {clarificationIndex + 1}/{clarificationQuestions.length}
            </strong>
          </div>
          <p className="clarification-flow-question">
            {clarificationQuestions[clarificationIndex]}
          </p>
          <div className="clarification-flow-input">
            <input
              type="text"
              value={clarificationInput}
              onChange={(e) => setClarificationInput(e.target.value)}
              placeholder="请输入你的补充信息"
              autoFocus
              disabled={loading}
            />
            <button type="submit" disabled={loading || !clarificationInput.trim()}>
              {clarificationIndex + 1 === clarificationQuestions.length ? "生成答案" : "下一题"}
            </button>
          </div>
          <button
            type="button"
            className="clarification-skip-btn"
            onClick={handleSkipClarification}
            disabled={loading}
          >
            跳过，直接搜索
          </button>
        </form>
      )}

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

      {/* 非阻塞追问建议：答案后方展示 LLM 生成的补充信息建议 */}
      {explanation && suggestedQuestions.length > 0 && !clarifying && (
        <div className="clarify-suggestions">
          <span className="clarify-suggestions-label">想获得更精准的回答？</span>
          <div className="clarify-suggestions-chips">
            {suggestedQuestions.map((q, i) => (
              <button
                key={i}
                type="button"
                className="clarify-suggestion-chip"
                onClick={() => {
                  setPendingQuery(query);
                  setClarificationQuestions(suggestedQuestions);
                  setClarificationIndex(0);
                  setClarificationAnswers([]);
                  setClarificationInput("");
                  setClarifying(true);
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {searchResult && searchResult.evidences.length > 0 && !explanation && (
        <EvidenceList evidences={searchResult.evidences} />
      )}
    </div>
  );
}
