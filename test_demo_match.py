import sys
sys.path.insert(0, 'E:/patienceAI')
from agents.demo_scenarios import get_demo_scenario, DEMO_SCENARIOS

queries = ['肺腺癌免疫治疗', '肺腺癌免疫治疗最新进展', 'CAR-T实体瘤', 'PD-L1检测']
for q in queries:
    result = get_demo_scenario(q)
    if result:
        print(f'Query: {q} -> Matched: {result["id"]}')
    else:
        print(f'Query: {q} -> No match')
        available = [s['query'] for s in DEMO_SCENARIOS]
        print(f'  Available scenarios: {available}')
