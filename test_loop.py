"""Test Simplification Loop directly"""
import asyncio
import sys
sys.path.insert(0, '.')

from agents.core.simplification_loop import SimplificationLoop
from backend.services.llm_client import llm_client

async def test():
    print('Testing SimplificationLoop...')
    loop = SimplificationLoop(llm_client=llm_client, max_iterations=1)
    test_evidences = [
        {'title': 'Test', 'abstract': 'Test abstract', 'source_type': 'guide', 'pmid': '123', 'publish_date': '2024-01-01'}
    ]
    try:
        result = await loop.run(test_evidences, 'test query')
        print('SUCCESS')
        print(str(result)[:500])
    except Exception as e:
        print('ERROR: ' + str(e))
        import traceback
        traceback.print_exc()

asyncio.run(test())
