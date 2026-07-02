from datetime import datetime

import pytest

from app.models.schemas import PushDigest
from app.services.radar.digest_generator import generate_push_digest


@pytest.mark.asyncio
async def test_digest_marks_stage_and_cleans_patient_facing_text(make_mock_llm_client):
    llm = make_mock_llm_client(response="你患了肺癌。这个研究提示群体层面可能有新方向。")
    digest = await generate_push_digest(
        "肺癌",
        [
            {
                "id": "ev1",
                "title": "Phase I trial of a new therapy",
                "source_type": "trial",
                "evidence_level": "moderate",
                "publish_date": datetime.now().date().isoformat(),
            }
        ],
        llm,
    )

    assert isinstance(digest, PushDigest)
    assert digest.disease_keyword == "肺癌"
    assert digest.items[0].research_stage == "early_trial"
    assert digest.items[0].uncertainty_note
    assert "你患了" not in digest.items[0].summary


@pytest.mark.asyncio
async def test_preclinical_digest_keeps_uncertainty_note(make_mock_llm_client):
    digest = await generate_push_digest(
        "SMA",
        [
            {
                "id": "mouse-study",
                "title": "Mouse model shows signal in preclinical therapy",
                "abstract": "mice model only",
                "source_type": "paper_en",
                "evidence_level": "low",
                "publish_date": datetime.now().date().isoformat(),
            }
        ],
        make_mock_llm_client(response="这是一条群体研究进展摘要。"),
    )

    assert digest.items[0].research_stage == "preclinical"
    assert "尚未" in (digest.items[0].uncertainty_note or "")
