"""E2E 测试：验证第一波完整链路"""
import requests

BASE = "http://127.0.0.1:8000"
passed = []
failed = []

def check(name, condition, detail=""):
    if condition:
        passed.append(name)
        print(f"  ✅ {name}")
    else:
        failed.append((name, detail))
        print(f"  ❌ {name}: {detail}")

print("=" * 60)
print("迭代三第一波 - 完整链路测试")
print("=" * 60)

# Phase 1: 创建 Session
print("\n[1] 创建 Session")
r = requests.post(f"{BASE}/api/sessions/create", json={"topic": "E2E测试：大语言模型幻觉检测"})
check("Create Session", r.status_code == 200, r.text[:100])
sid = r.json()["session_id"]
print(f"    Session ID: {sid}")

# Phase 2: 执行 Plan 阶段
print("\n[2] 执行 Plan 阶段（生成关键词）")
r = requests.post(f"{BASE}/api/sessions/{sid}/run/plan", 
    json={"topic": "E2E测试：大语言模型幻觉检测", "start_phase": "plan"})
check("Run Plan", r.status_code == 200, r.text[:200])
keywords = r.json().get("keywords", [])
plan = r.json().get("initial_plan", "")
print(f"    生成 {len(keywords)} 个关键词候选项")

# Phase 3: 用户编辑关键词并确认
print("\n[3] 编辑关键词并确认")
edited_keywords = []
for i, kw in enumerate(keywords[:5]):
    edited_keywords.append({
        "original": kw.get("original", ""),
        "english": f"english_term_{i}",
        "synonyms": f"synonym_{i}_a, synonym_{i}_b",
    })
# 添加一个用户自定义关键词
edited_keywords.append({
    "original": "LLM幻觉",
    "english": "LLM Hallucination",
    "synonyms": "language model hallucination, factual error",
})

r = requests.put(f"{BASE}/api/sessions/{sid}/keywords", json={"keywords": edited_keywords})
check("Save Keywords", r.status_code == 200, r.text[:200])

# Phase 4: 更新状态为 plan_confirmed
print("\n[4] 确认关键词 → plan_confirmed")
r = requests.put(f"{BASE}/api/sessions/{sid}/state", json={"state": "plan_confirmed"})
check("State → plan_confirmed", r.status_code == 200, r.text[:200])
print(f"    当前状态: {r.json()['state']}")

# Phase 5: 验证 Session 完整性
print("\n[5] 验证 Session 完整性")
r = requests.get(f"{BASE}/api/sessions/{sid}")
check("Get Session", r.status_code == 200)
session = r.json()
check("Has plan", bool(session.get("initial_plan")))
check("Has keywords", len(session.get("keywords", [])) > 0)
check("Has state", session.get("state") == "plan_confirmed")
print(f"    关键词数: {len(session.get('keywords', []))}")
print(f"    规划长度: {len(session.get('initial_plan', ''))} 字符")

# Phase 6: 非法操作测试
print("\n[6] 非法操作防护测试")
r = requests.put(f"{BASE}/api/sessions/{sid}/state", json={"state": "complete"})
check("Block plan_confirmed→complete", r.status_code == 400)

r = requests.put(f"{BASE}/api/sessions/{sid}/state", json={"state": "searching"})
check("Allow plan_confirmed→searching", r.status_code == 200)

# Phase 7: Session 列表
print("\n[7] Session 列表")
r = requests.get(f"{BASE}/api/sessions/list")
check("List Sessions", r.status_code == 200 and len(r.json()) > 0)
print(f"    总 Session 数: {len(r.json())}")

# Phase 8: 状态机信息
print("\n[8] 状态机信息")
r = requests.get(f"{BASE}/api/sessions/state-machine")
check("State Machine", r.status_code == 200 and len(r.json()["states"]) == 8)

# 清理
print("\n[9] 清理测试数据")
r = requests.delete(f"{BASE}/api/sessions/{sid}")
check("Delete Session", r.status_code == 200)

# 结果
print("\n" + "=" * 60)
print(f"结果: {len(passed)}/{len(passed)+len(failed)} 通过")
if failed:
    print("失败项:")
    for name, detail in failed:
        print(f"  ❌ {name}: {detail}")
else:
    print("🎉 全部通过！第一波完整链路验证成功！")
print("=" * 60)
