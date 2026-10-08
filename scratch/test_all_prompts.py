import json
import requests
import time
import sys

BASE_URL = "http://127.0.0.1:8000"

def get_auth_token():
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@sap.com", "password": "AdminPassword123!"}
    )
    if resp.status_code == 200:
        return resp.json()["access_token"]
    raise Exception(f"Login failed: {resp.text}")

def create_chat(token, title="Test Chat"):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(f"{BASE_URL}/api/chats", json={"title": title}, headers=headers)
    resp.raise_for_status()
    return resp.json()["id"]

def send_chat_message_stream(token, chat_id, message_text):
    headers = {"Authorization": f"Bearer {token}"}
    start_t = time.time()
    resp = requests.post(
        f"{BASE_URL}/api/chats/{chat_id}/messages?stream=true",
        json={"content": message_text},
        headers=headers,
        stream=True
    )
    if resp.status_code != 200:
        return {"status": resp.status_code, "text": resp.text, "events": []}
    
    events = []
    full_text = ""
    for line in resp.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith("data: "):
                data_str = decoded[6:]
                if data_str == "[DONE]":
                    break
                try:
                    payload = json.loads(data_str)
                    events.append(payload)
                    if payload.get("type") == "token":
                        full_text += payload.get("content", "")
                except Exception as e:
                    pass
    duration = time.time() - start_t
    return {"status": 200, "duration": duration, "events": events, "full_text": full_text}

def run_tests():
    print("=== Starting E2E Conversational Follow-Up Tests ===")
    token = get_auth_token()
    print("[OK] Authenticated")

    # TEST 1:
    print("\n--- TEST 1: 'What is SAP Convergent Invoicing?' -> 'can you explain in detail' ---")
    chat_id1 = create_chat(token, "Test 1 - CI Detail")
    r1 = send_chat_message_stream(token, chat_id1, "What is SAP Convergent Invoicing?")
    print(f"Turn 1 response len: {len(r1['full_text'])}, time: {r1['duration']:.2f}s")
    
    r2 = send_chat_message_stream(token, chat_id1, "can you explain in detail")
    print(f"Turn 2 response len: {len(r2['full_text'])}, time: {r2['duration']:.2f}s")
    is_rejected1 = "SAP Scope Restriction" in r2['full_text'] or "only help with SAP" in r2['full_text']
    assert not is_rejected1, f"Test 1 FAILED: Got scope restriction rejection for follow-up! Content: {r2['full_text'][:200]}"
    assert len(r2['full_text']) > 150, "Test 1 FAILED: Response too short!"
    print(f"[OK] Test 1 PASSED: Follow-up correctly answered with {len(r2['full_text'])} chars")

    # TEST 2:
    print("\n--- TEST 2: 'What is a Billable Item in SAP Convergent Invoicing?' -> 'what information does it contain?' ---")
    chat_id2 = create_chat(token, "Test 2 - Billable Item")
    r1 = send_chat_message_stream(token, chat_id2, "What is a Billable Item in SAP Convergent Invoicing?")
    print(f"Turn 1 response len: {len(r1['full_text'])}, time: {r1['duration']:.2f}s")
    
    r2 = send_chat_message_stream(token, chat_id2, "what information does it contain?")
    print(f"Turn 2 response len: {len(r2['full_text'])}, time: {r2['duration']:.2f}s")
    is_rejected2 = "SAP Scope Restriction" in r2['full_text']
    assert not is_rejected2, f"Test 2 FAILED: Got scope restriction rejection for follow-up! Content: {r2['full_text'][:200]}"
    assert len(r2['full_text']) > 150, "Test 2 FAILED: Response too short!"
    print(f"[OK] Test 2 PASSED: Follow-up correctly answered with {len(r2['full_text'])} chars")

    # TEST 3:
    print("\n--- TEST 3: 'Explain SAP Convergent Charging.' -> 'How does it integrate with CI?' ---")
    chat_id3 = create_chat(token, "Test 3 - CC & CI")
    r1 = send_chat_message_stream(token, chat_id3, "Explain SAP Convergent Charging.")
    print(f"Turn 1 response len: {len(r1['full_text'])}, time: {r1['duration']:.2f}s")
    
    r2 = send_chat_message_stream(token, chat_id3, "How does it integrate with CI?")
    print(f"Turn 2 response len: {len(r2['full_text'])}, time: {r2['duration']:.2f}s")
    is_rejected3 = "SAP Scope Restriction" in r2['full_text']
    assert not is_rejected3, f"Test 3 FAILED: Got scope restriction rejection for follow-up! Content: {r2['full_text'][:200]}"
    print(f"[OK] Test 3 PASSED: Follow-up correctly answered with {len(r2['full_text'])} chars")

    # TEST 4:
    print("\n--- TEST 4: 'Explain SAP BRIM.' -> 'What is the weather today?' ---")
    chat_id4 = create_chat(token, "Test 4 - Weather Non-SAP")
    r1 = send_chat_message_stream(token, chat_id4, "Explain SAP BRIM.")
    r2 = send_chat_message_stream(token, chat_id4, "What is the weather today?")
    print(f"Turn 2 response: {r2['full_text'][:120]}...")
    assert "SAP Scope Restriction" in r2['full_text'] or "only help with SAP" in r2['full_text'], "Test 4 FAILED: Weather was NOT rejected!"
    print("[OK] Test 4 PASSED: Non-SAP query successfully rejected under SAP Scope Restriction")

    # TEST 5:
    print("\n--- TEST 5: 'Explain SAP Convergent Invoicing.' -> 'Tell me a Python joke.' ---")
    chat_id5 = create_chat(token, "Test 5 - Python Joke Non-SAP")
    r1 = send_chat_message_stream(token, chat_id5, "Explain SAP Convergent Invoicing.")
    r2 = send_chat_message_stream(token, chat_id5, "Tell me a Python joke.")
    print(f"Turn 2 response: {r2['full_text'][:120]}...")
    assert "SAP Scope Restriction" in r2['full_text'] or "only help with SAP" in r2['full_text'], "Test 5 FAILED: Python joke was NOT rejected!"
    print("[OK] Test 5 PASSED: Non-SAP query successfully rejected under SAP Scope Restriction")

    # TEST 6:
    print("\n--- TEST 6: 3-Turn: 'What is SAP BRIM?' -> 'Explain Convergent Charging.' -> 'What happens after rating?' ---")
    chat_id6 = create_chat(token, "Test 6 - 3-Turn")
    r1 = send_chat_message_stream(token, chat_id6, "What is SAP BRIM?")
    r2 = send_chat_message_stream(token, chat_id6, "Explain Convergent Charging.")
    r3 = send_chat_message_stream(token, chat_id6, "What happens after rating?")
    print(f"Turn 3 response len: {len(r3['full_text'])}, time: {r3['duration']:.2f}s")
    is_rejected6 = "SAP Scope Restriction" in r3['full_text']
    assert not is_rejected6, f"Test 6 FAILED: Got scope restriction rejection for follow-up! Content: {r3['full_text'][:200]}"
    assert len(r3['full_text']) > 150, "Test 6 FAILED: Response too short!"
    print(f"[OK] Test 6 PASSED: 3-turn follow-up correctly resolved and answered with {len(r3['full_text'])} chars")

    print("\n[SUCCESS] ALL 6 TEST CASES PASSED PERFECTLY!")

if __name__ == "__main__":
    run_tests()
