"""测试脚本：验证迭代三第一波所有 API 端点"""
import sys
sys.path.insert(0, ".")

from web_app import app
from fastapi.testclient import TestClient

client = TestClient(app)
results = []

# 1. Health
r = client.get('/api/health')
results.append(('Health', r.status_code == 200))

# 2. Create Session
r = client.post('/api/sessions/create', json={'topic': 'LLM Hallucination Detection Test'})
sid = r.json()['session_id']
results.append(('Create Session', r.status_code == 200 and sid.startswith('sess_')))

# 3. List Sessions
r = client.get('/api/sessions/list')
results.append(('List Sessions', r.status_code == 200 and len(r.json()) > 0))

# 4. Get Session
r = client.get(f'/api/sessions/{sid}')
results.append(('Get Session', r.status_code == 200 and r.json()['state'] == 'planning'))

# 5. State Machine (must not be matched by {session_id})
r = client.get('/api/sessions/state-machine')
results.append(('State Machine', r.status_code == 200 and len(r.json()['states']) == 8))

# 6. Invalid Transition
r = client.put(f'/api/sessions/{sid}/state', json={'state': 'complete'})
results.append(('Invalid Transition', r.status_code == 400))

# 7. Valid Transition
r = client.put(f'/api/sessions/{sid}/state', json={'state': 'plan_confirmed'})
results.append(('Valid Transition', r.status_code == 200))

# 8. Save Keywords
r = client.put(f'/api/sessions/{sid}/keywords', json={
    'keywords': [{'original': 'LLM', 'english': 'Large Language Model', 'synonyms': 'GPT,Transformer'}]
})
results.append(('Save Keywords', r.status_code == 200))

# 9. Get Papers
r = client.get(f'/api/sessions/{sid}/papers')
results.append(('Get Papers', r.status_code == 200))

# 10. Delete Session
r = client.delete(f'/api/sessions/{sid}')
results.append(('Delete Session', r.status_code == 200))

print('=' * 50)
passed = sum(1 for _, ok in results if ok)
print(f'Results: {passed}/{len(results)} passed')
for name, ok in results:
    print(f'  {"PASS" if ok else "FAIL"} - {name}')
