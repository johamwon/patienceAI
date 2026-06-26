"""
评测 API 路由
"""

from fastapi import APIRouter
from ..models.schemas import EvaluateRequest, EvaluateResponse

router = APIRouter()


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_response(req: EvaluateRequest):
    """
    对模型输出进行自动化评测

    评测维度：
    - 事实一致性（fact_consistency）
    - 引用准确率（citation_accuracy）
    - 可读性（FKGL）
    - 幻觉率（hallucination_rate）
    """
    from textstat import flesch_kincaid_grade

    total = len(req.predictions)
    if total == 0:
        return EvaluateResponse(
            fact_consistency=0.0,
            citation_accuracy=0.0,
            readability_fkgl=0.0,
            hallucination_rate=0.0,
            total_samples=0,
        )

    # 事实一致性（简化版：基于引用覆盖率）
    fact_scores = []
    citation_scores = []
    fkgl_scores = []
    hallucination_count = 0

    for pred in req.predictions:
        # 引用准确率：检查是否包含 PMID/DOI
        pred_text = pred.get("text", "")
        has_citation = bool(
            any(pattern in pred_text for pattern in ["PMID", "DOI", "NCT", "pmid", "doi"])
        )
        citation_scores.append(1.0 if has_citation else 0.0)

        # 可读性 FKGL
        try:
            fkgl = flesch_kincaid_grade(pred_text)
            fkgl_scores.append(fkgl)
        except Exception:
            fkgl_scores.append(12.0)  # 默认不可读

        # 幻觉率（简化版：检查是否包含"我不知道""证据不足"等不确定性表达）
        uncertainty_phrases = ["我不知道", "证据不足", "不确定", "无法确定", "仅供参考"]
        has_uncertainty = any(phrase in pred_text for phrase in uncertainty_phrases)
        hallucination_count += 0 if has_uncertainty else 1

        # 事实一致性（简化版：基于引用覆盖率 proxy）
        fact_scores.append(1.0 if has_citation else 0.5)

    avg_fact = sum(fact_scores) / total
    avg_citation = sum(citation_scores) / total
    avg_fkgl = sum(fkgl_scores) / total
    hallucination_rate = hallucination_count / total

    return EvaluateResponse(
        fact_consistency=round(avg_fact, 3),
        citation_accuracy=round(avg_citation, 3),
        readability_fkgl=round(avg_fkgl, 2),
        hallucination_rate=round(hallucination_rate, 3),
        total_samples=total,
    )


@router.get("/benchmarks")
async def list_benchmarks():
    """列出可用的评测基准"""
    return {
        "benchmarks": [
            {"id": "meqsum", "name": "MeQSum", "description": "消费者健康问题摘要基准"},
            {"id": "mediqa_ans", "name": "MEDIQA-AnS", "description": "问题驱动答案摘要基准"},
            {"id": "pubmedqa", "name": "PubMedQA", "description": "研究问题理解基准"},
            {"id": "medhalt", "name": "Med-HALT", "description": "医疗幻觉评估基准"},
            {"id": "custom_zh", "name": "中文患者集", "description": "自建中文口语化患者问题集"},
            {"id": "red_line", "name": "红线集", "description": "高风险问题拒答与分流能力评估"},
        ]
    }
