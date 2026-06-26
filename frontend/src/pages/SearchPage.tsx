import { useState, FormEvent } from "react";
import { searchEvidence, explainEvidence } from "../api";
import type { SearchResponse, ExplainResponse } from "../types";
import EvidenceList from "../components/EvidenceList";
import ExplanationView from "../components/ExplanationView";
import Mascot from "../components/Mascot";

const DEMO_QUERIES = [
  "肺腺癌免疫治疗最新进展",
  "CAR-T疗法实体瘤最新研究",
  "PD-L1表达检测是什么意思",
  "断食可以饿死癌细胞吗",
  "奥希替尼和吉非替尼哪个更好",
];

const DISEASE_CATEGORIES = [
  {
    category: "肺癌",
    icon: "🫁",
    queries: ["肺腺癌免疫治疗", "小细胞肺癌最新疗法", "EGFR突变靶向治疗"],
  },
  {
    category: "消化道肿瘤",
    icon: "🏥",
    queries: ["胰腺癌治疗新进展", "胃癌靶向治疗", "结直肠癌免疫治疗"],
  },
  {
    category: "血液肿瘤",
    icon: "🩸",
    queries: ["CAR-T疗法淋巴瘤", "多发性骨髓瘤新药", "白血病靶向治疗"],
  },
  {
    category: "罕见病",
    icon: "🧬",
    queries: ["SMA基因疗法", "渐冻症ALS最新研究", "血友病基因治疗"],
  },
  {
    category: "神经系统肿瘤",
    icon: "🧠",
    queries: ["胶质母细胞瘤新疗法", "脑膜瘤治疗方案"],
  },
  {
    category: "乳腺癌",
    icon: "🎀",
    queries: ["HER2阳性靶向治疗", "三阴性乳腺癌免疫治疗"],
  },
];

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const [showDiseaseSelector, setShowDiseaseSelector] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setSearchResult(null);
    setExplanation(null);

    try {
      const searchRes = await searchEvidence(query);
      setSearchResult(searchRes);
      setIsDemo(searchRes.evidences.length === 0);

      const explainRes = await explainEvidence(
        query,
        searchRes.evidences.slice(0, 5).map((e) => e.id)
      );
      setExplanation(explainRes);
    } catch (err: any) {
      setError(err.message || "发生错误，请重试");
    } finally {
      setLoading(false);
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
      {/* Mascot */}
      <Mascot />

      <header className="header">
        <h1>患癌知光</h1>
        <p className="subtitle">面向患者的疑难杂症科研动态检索与通俗化解释</p>
      </header>

      <form onSubmit={handleSubmit} className="search-form">
        <div className="input-wrapper">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="请输入您想了解的疾病、药物或治疗方案"
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
          {showDiseaseSelector ? "收起疾病列表" : "🔍 从疑难杂症列表中选择"}
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
        <span className="demo-label">试试这些演示：</span>
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
        <ExplanationView data={explanation} query={query} />
      )}

      {searchResult && searchResult.evidences.length > 0 && !explanation && (
        <EvidenceList evidences={searchResult.evidences} />
      )}
    </div>
  );
}
