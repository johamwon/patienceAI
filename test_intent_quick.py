import sys
sys.path.insert(0, '.')
from backend.app.services.intent_classifier import parse_query

r = parse_query('奥希替尼和吉非替尼哪个好')
print(f"Intent: {r['intent']}")

r2 = parse_query('肺腺癌是什么')
print(f"Intent2: {r2['intent']}")
