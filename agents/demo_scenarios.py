"""
演示场景数据

大赛展示用的预设演示数据，覆盖不同癌种、不同风险等级。
当 KnowS AI 未接入时，使用这些预设数据展示完整功能。
"""

from typing import Optional

DEMO_SCENARIOS = [
    {
        "id": "demo_lung_cancer_immunotherapy",
        "title": "肺腺癌免疫治疗最新进展",
        "query": "肺腺癌免疫治疗最新进展",
        "risk_level": "low",
        "intent": "treatment_progress",
        "evidences": [
            {
                "id": "demo_pmid_32743622",
                "title": "Pembrolizumab plus Chemotherapy in Metastatic Non-Small-Cell Lung Cancer",
                "authors": "Gandhi L, et al.",
                "source_type": "paper_en",
                "pmid": "32743622",
                "abstract": "In patients with metastatic non-small-cell lung cancer, pembrolizumab plus chemotherapy improved overall survival and progression-free survival compared with chemotherapy alone.",
                "publish_date": "2020-05-01",
                "journal": "NEJM",
                "evidence_level": "high",
                "url": "https://pubmed.ncbi.nlm.nih.gov/32743622/",
            },
            {
                "id": "demo_pmid_35123456",
                "title": "免疫检查点抑制剂联合化疗治疗晚期非小细胞肺癌的系统综述",
                "authors": "张伟, 李强, 王芳",
                "source_type": "paper_cn",
                "pmid": "35123456",
                "abstract": "meta分析显示，免疫联合化疗方案降低晚期NSCLC患者死亡风险约21%，客观缓解率提高至45.2%。",
                "publish_date": "2024-03-15",
                "journal": "中华肿瘤杂志",
                "evidence_level": "high",
                "url": "https://pubmed.ncbi.nlm.nih.gov/35123456/",
            },
            {
                "id": "demo_guide_nsclc_2024",
                "title": "非小细胞肺癌诊疗指南（2024年版）",
                "authors": "国家卫健委",
                "source_type": "guide",
                "pmid": None,
                "abstract": "推荐PD-1/PD-L1抑制剂联合化疗作为晚期非鳞非小细胞肺癌的一线治疗方案，PD-L1表达阳性患者优先选择免疫单药治疗。",
                "publish_date": "2024-01-01",
                "journal": "国家卫健委",
                "evidence_level": "high",
                "url": None,
            },
        ],
        "expected_conclusion": "免疫治疗联合化疗已成为晚期肺腺癌的标准一线方案之一，约45%的患者能获得显著疗效。",
    },
    {
        "id": "demo_car_t_cancer",
        "title": "CAR-T 疗法在实体瘤中的最新研究",
        "query": "CAR-T疗法实体瘤最新研究进展",
        "risk_level": "low",
        "intent": "treatment_progress",
        "evidences": [
            {
                "id": "demo_pmid_car_t_001",
                "title": "CAR-T Cell Therapy for Solid Tumors: A Systematic Review",
                "authors": "Wang Y, et al.",
                "source_type": "paper_en",
                "pmid": "demo_car_t_001",
                "abstract": "CAR-T therapy has shown promising results in solid tumors with objective response rates of 30-50% in selected patients.",
                "publish_date": "2024-06-01",
                "journal": "Nature Medicine",
                "evidence_level": "moderate",
                "url": None,
            },
            {
                "id": "demo_meeting_car_t_2024",
                "title": "ASCO 2024: 实体瘤CAR-T治疗新突破",
                "authors": "ASCO年会",
                "source_type": "meeting",
                "pmid": None,
                "abstract": "多项I/II期临床试验显示，针对CLDN18.2的CAR-T在胃癌和胰腺癌中显示出初步疗效。",
                "publish_date": "2024-05-01",
                "journal": "ASCO年会",
                "evidence_level": "moderate",
                "url": None,
            },
        ],
        "expected_conclusion": "CAR-T疗法在实体瘤治疗中取得初步进展，针对特定靶点的CAR-T在胃癌和胰腺癌中显示出约30-50%的有效率。",
    },
    {
        "id": "demo_pd_l1_explanation",
        "title": "PD-L1 表达检测解释",
        "query": "PD-L1表达检测是什么意思？",
        "risk_level": "low",
        "intent": "test_explanation",
        "evidences": [
            {
                "id": "demo_guide_pdl1",
                "title": "PD-L1 检测临床意义解读",
                "authors": "国家癌症中心",
                "source_type": "guide",
                "pmid": None,
                "abstract": "PD-L1（程序性死亡配体1）是一种在肿瘤细胞表面表达的蛋白质，可以通过免疫组化方法检测。TPS评分≥50%的患者适合免疫单药治疗，TPS评分1-49%的患者适合免疫联合治疗。",
                "publish_date": "2023-06-01",
                "journal": "国家癌症中心",
                "evidence_level": "high",
                "url": None,
            },
        ],
        "expected_conclusion": 'PD-L1检测看癌细胞表面有多少"隐形衣"，TPS≥50%适合单用免疫治疗，1-49%适合联合治疗。',
    },
    {
        "id": "demo_high_risk_triage",
        "title": "高风险问题分流演示",
        "query": "我这个症状是不是癌症复发？",
        "risk_level": "high",
        "intent": "high_risk",
        "evidences": [],
        "expected_conclusion": "您的提问涉及个体化诊疗决策，系统无法提供此类建议。",
    },
    {
        "id": "demo_rumor_check",
        "title": "健康谣言核验",
        "query": "断食可以饿死癌细胞吗？",
        "risk_level": "medium",
        "intent": "rumor_check",
        "evidences": [
            {
                "id": "demo_rumor_001",
                "title": "饥饿能否饿死癌细胞？科学辟谣",
                "authors": "中国疾控中心",
                "source_type": "guide",
                "pmid": None,
                "abstract": "目前没有科学证据支持断食可以饿死癌细胞。癌细胞具有独特的代谢能力，即使在营养缺乏的环境下也能通过改变代谢途径获取能量。盲目断食反而可能导致营养不良，影响正常治疗。",
                "publish_date": "2023-08-15",
                "journal": "中国疾控中心",
                "evidence_level": "high",
                "url": None,
            },
        ],
        "expected_conclusion": "没有科学证据支持断食可以饿死癌细胞，盲目断食可能影响正常治疗。",
    },
    {
        "id": "demo_targeted_therapy_comparison",
        "title": "奥希替尼 vs 吉非替尼：靶向药对比",
        "query": "奥希替尼和吉非替尼哪个更好",
        "risk_level": "medium",
        "intent": "drug_info",
        "evidences": [
            {
                "id": "demo_trial_osimertinib",
                "title": "奥希替尼一线治疗EGFR突变NSCLC的III期临床试验",
                "authors": "Soria JC, et al.",
                "source_type": "trial",
                "pmid": "demo_trial_osi",
                "abstract": "奥希替尼组中位PFS显著优于吉非替尼组（18.9个月 vs 10.2个月），且中枢神经系统进展风险更低。",
                "publish_date": "2024-01-01",
                "journal": "NEJM",
                "evidence_level": "high",
                "url": None,
            },
            {
                "id": "demo_package_insert_osi",
                "title": "奥希替尼药品说明书",
                "authors": "国家药监局",
                "source_type": "package_insert",
                "pmid": None,
                "abstract": "适应症：既往经EGFR TKI治疗时或治疗后出现疾病进展，并且经检测确认存在EGFR T790M突变阳性的局部晚期或转移性NSCLC。常见不良反应：腹泻、皮疹、甲沟炎。",
                "publish_date": "2023-06-01",
                "journal": "国家药监局",
                "evidence_level": "high",
                "url": None,
            },
        ],
        "expected_conclusion": "奥希替尼在EGFR突变患者中表现优于吉非替尼，无进展生存期更长且脑转移风险更低，但需在医生指导下选择。",
    },
    {
        "id": "demo_cancer_foundation",
        "title": "胰腺癌基础认知",
        "query": "胰腺癌是什么？有哪些类型？",
        "risk_level": "low",
        "intent": "disease_understanding",
        "evidences": [
            {
                "id": "demo_guide_pancreatic",
                "title": "胰腺癌诊疗指南（2023年版）",
                "authors": "国家癌症中心",
                "source_type": "guide",
                "pmid": None,
                "abstract": "胰腺癌主要包括胰腺导管腺癌（占90%以上）和胰腺神经内分泌肿瘤。早期症状隐匿，多数患者确诊时已属晚期。",
                "publish_date": "2023-06-01",
                "journal": "国家癌症中心",
                "evidence_level": "high",
                "url": None,
            },
            {
                "id": "demo_paper_pancreatic",
                "title": "胰腺癌流行病学与预后分析",
                "authors": "Chen W, et al.",
                "source_type": "paper_cn",
                "pmid": "demo_pancreatic_001",
                "abstract": "胰腺癌5年生存率约10%，早期诊断是改善预后的关键。CA19-9是重要的肿瘤标志物。",
                "publish_date": "2024-02-01",
                "journal": "中华流行病学杂志",
                "evidence_level": "moderate",
                "url": None,
            },
        ],
        "expected_conclusion": "胰腺癌是一种恶性程度很高的消化道肿瘤，最常见的是胰腺导管腺癌，早期发现对治疗至关重要。",
    },
]


def get_demo_scenario(query: str) -> Optional[dict]:
    """根据查询匹配演示场景（支持中英文模糊匹配）"""
    query_lower = query.lower()
    for scenario in DEMO_SCENARIOS:
        scenario_query = scenario["query"].lower()
        # 精确包含匹配
        if scenario_query in query_lower or query_lower in scenario_query:
            return scenario
        # 关键词重叠匹配（支持中文逐字匹配）
        scenario_chars = set(scenario_query.replace(" ", ""))
        query_chars = set(query_lower.replace(" ", ""))
        overlap = len(scenario_chars & query_chars)
        if overlap >= min(len(scenario_chars), len(query_chars)) * 0.6:
            return scenario
    return None
