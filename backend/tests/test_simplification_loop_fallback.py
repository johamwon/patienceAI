from agents.core.simplification_loop import SimplificationLoop


class DummyLLM:
    def chat(self, *args, **kwargs):
        return ""


def test_fallback_output_returns_dict_when_simplified_text_is_long():
    loop = SimplificationLoop(DummyLLM())
    result = loop._fallback_output(
        [
            {
                "id": "ev1",
                "title": "PD-L1 expression testing in non-small cell lung cancer",
                "source_type": "guide",
                "evidence_level": "moderate",
            }
        ],
        "这是一段较长的通俗解释。" * 80,
        "PD-L1表达检测是什么意思",
    )

    assert isinstance(result, dict)
    assert result["layer1_conclusion"]["text"]
    assert result["layer3_patient_explanation"]["what_is_it"]
    assert result["layer3_patient_explanation"]["what_evidence_says"]


def test_fallback_output_does_not_show_english_process_text():
    loop = SimplificationLoop(DummyLLM())
    result = loop._fallback_output(
        [
            {
                "id": "ev1",
                "title": "Chinese expert consensus guidelines for non-small cell lung cancer",
                "source_type": "guide",
                "evidence_level": "moderate",
            }
        ],
        "Got it, let's tackle this. First, the original text is a list of Chinese expert consensus guidelines, right?",
        "肺腺癌免疫治疗最新进展",
    )

    assert "Got it" not in result["layer1_conclusion"]["text"]
    assert "let's tackle" not in result["layer3_patient_explanation"]["what_is_it"]
    assert result["layer1_conclusion"]["text"].startswith("肺癌")
