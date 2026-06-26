from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import date


class Evidence(BaseModel):
    """结构化医学证据"""
    id: str
    title: str
    authors: Optional[str] = None
    source_type: Literal[
        "paper_en", "paper_cn", "meeting",
        "guide", "trial", "package_insert", "unknown"
    ]
    pmid: Optional[str] = None
    doi: Optional[str] = None
    nct_id: Optional[str] = None
    abstract: Optional[str] = None
    publish_date: Optional[date] = None
    journal: Optional[str] = None
    evidence_level: Optional[Literal["high", "moderate", "low", "very_low"]] = None
    url: Optional[str] = None
    raw: Optional[dict] = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="患者自然语言查询")
    max_results: int = Field(default=20, ge=1, le=40, description="最多返回结果数")
    sources: Optional[list[str]] = Field(
        default=None,
        description="指定检索源: paper_en, paper_cn, guide, trial, meeting, package_insert",
    )


class SearchResponse(BaseModel):
    query: str
    intent: Optional[str] = None
    risk_level: Literal["low", "medium", "high", "prohibited"] = "low"
    evidences: list[Evidence]
    total: int


class ExplainRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    evidence_ids: Optional[list[str]] = Field(default=None, description="指定要解释的证据ID列表")


class LayerOneConclusion(BaseModel):
    """一句话结论"""
    text: str
    citations: list[str] = Field(default_factory=list, description="绑定的PMID/DOI列表")


class EvidenceCard(BaseModel):
    """证据卡片"""
    study_type: str
    sample_size: Optional[str] = None
    intervention: Optional[str] = None
    comparator: Optional[str] = None
    outcome: Optional[str] = None
    limitations: Optional[str] = None
    evidence_level: str
    source_id: str
    source_url: Optional[str] = None


class PatientExplanation(BaseModel):
    """患者通俗解释"""
    what_is_it: str = Field(description="这是什么——用类比解释")
    what_evidence_says: str = Field(description="证据说明什么")
    what_it_means_for_you: str = Field(description="对你意味着什么")
    when_to_see_doctor: str = Field(description="何时需要立即就医")
    disclaimer: str = Field(
        default="本内容为医学文献通俗化解释，仅供参考，不构成诊疗建议，不替代医生判断。"
    )


class ExplainResponse(BaseModel):
    layer1_conclusion: LayerOneConclusion
    layer2_evidence_cards: list[EvidenceCard]
    layer3_patient_explanation: PatientExplanation
    risk_level: str
    risk_message: Optional[str] = None


class EvaluateRequest(BaseModel):
    predictions: list[dict]
    references: list[dict]


class EvaluateResponse(BaseModel):
    fact_consistency: float
    citation_accuracy: float
    readability_fkgl: float
    hallucination_rate: float
    total_samples: int
