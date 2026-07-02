from agents.core.simplification_loop import SimplificationLoop
from backend.app.services.answer_alignment import (
    analyze_query_focus,
    rerank_evidences_for_query,
    score_evidence_relevance,
)
from backend.app.services.intent_classifier import IntentType, classify_intent
from backend.app.services.query_rewriter import _fallback_rewrite


def test_alzheimer_latest_treatment_query_focus():
    focus = analyze_query_focus("朋友父亲得了阿尔兹海默症，有没有最新的治疗方案")

    assert focus.disease == "阿尔茨海默病"
    assert focus.intent == "latest_treatment"
    assert focus.audience == "family_or_friend"
    assert "最新治疗方案" in focus.treatment_angle
    assert any("轻度" in q or "中度" in q or "重度" in q for q in focus.clarification_questions)
    assert any("临床试验" in q or "已获批" in q for q in focus.clarification_questions)


def test_intent_classifier_treatment_plan_phrase():
    assert classify_intent("有没有最新的治疗方案") == IntentType.TREATMENT_PROGRESS


def test_fallback_rewrite_adds_alzheimer_aliases_and_english_terms():
    result = _fallback_rewrite("朋友父亲得了阿尔兹海默症，有没有最新的治疗方案")

    assert "阿尔茨海默病" in result.medical_terms_cn
    assert "最新治疗方案" in result.medical_terms_cn
    assert "Alzheimer" in result.medical_terms_en
    assert "treatment" in result.medical_terms_en
    assert "meeting" in result.suggested_sources
    assert "trial" in result.suggested_sources
    assert "guide" in result.suggested_sources


def test_rerank_prioritizes_treatment_relevant_evidence():
    focus = analyze_query_focus("阿尔兹海默症有没有最新的治疗方案")
    generic = {
        "id": "generic",
        "source_type": "paper_cn",
        "title": "阿尔茨海默病早期诊疗专家共识",
        "abstract": "介绍诊断流程。",
    }
    treatment = {
        "id": "treatment",
        "source_type": "guide",
        "title": "阿尔茨海默病治疗方案与新疗法专家共识2025",
        "abstract": "讨论治疗、药物、临床试验和新进展。",
    }

    assert score_evidence_relevance(treatment, focus) > score_evidence_relevance(generic, focus)
    ranked = rerank_evidences_for_query([generic, treatment], focus)
    assert ranked[0]["id"] == "treatment"


def test_simplification_fallback_conclusion_answers_latest_treatment():
    loop = SimplificationLoop(llm_client=None)
    evidences = [
        {
            "source_type": "guide",
            "title": "阿尔茨海默病治疗专家共识",
        },
        {
            "source_type": "trial",
            "title": "阿尔茨海默病新药临床试验",
        },
    ]

    text = loop._compose_fallback_conclusion(
        evidences,
        "",
        "朋友父亲得了阿尔兹海默症，有没有最新的治疗方案",
    )

    assert "阿尔茨海默病" in text
    assert "最新治疗" in text
    assert "指南" in text
    assert "临床试验" in text
    assert "医生" in text
