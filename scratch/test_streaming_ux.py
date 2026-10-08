import requests
import json
import time

def run_tests():
    # Login
    auth_resp = requests.post('http://127.0.0.1:8000/api/auth/login', json={'email': 'admin@sap.com', 'password': 'AdminPassword123!'})
    token = auth_resp.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    # Create chat
    chat_resp = requests.post('http://127.0.0.1:8000/api/chats', json={'title': 'Stop & Multi-turn Verification'}, headers=headers)
    chat_id = chat_resp.json()['id']
    print(f"Test Chat ID: {chat_id}")

    # ==========================================
    # TEST 3: Stop generation mid-stream
    # ==========================================
    url = f'http://127.0.0.1:8000/api/chats/{chat_id}/messages?stream=true'
    print('\n--- TEST 3: Stop Generating Mid-Stream ---')
    tokens_before_stop = []
    with requests.post(url, json={'content': 'Explain SAP Convergent Charging rating in detail'}, headers=headers, stream=True) as r:
        for line in r.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith('data:'):
                    data = json.loads(decoded[5:].strip())
                    if data.get('type') == 'token':
                        tokens_before_stop.append(data.get('content'))
                        if len(tokens_before_stop) >= 40:
                            print(f"Received {len(tokens_before_stop)} tokens. Simulating user clicking STOP GENERATING!")
                            partial_text = ''.join(tokens_before_stop)
                            requests.post(f'http://127.0.0.1:8000/api/chats/{chat_id}/messages/save-partial', json={'content': partial_text}, headers=headers)
                            break

    time.sleep(0.5)
    msgs_resp = requests.get(f'http://127.0.0.1:8000/api/chats/{chat_id}/messages', headers=headers)
    msgs = msgs_resp.json()
    print(f"Total messages in DB: {len(msgs)}")
    assert len(msgs) == 2, f"Expected 2 messages (user + partial assistant), got {len(msgs)}"
    last_msg = msgs[-1]
    print(f"Assistant message saved: role={last_msg['role']}, source_type={last_msg['source_type']}")
    print(f"Partial content preserved: {last_msg['content'][:100].encode('ascii', errors='replace').decode()}...")
    assert last_msg['role'] == 'assistant', "Assistant message should be saved"
    assert len(last_msg['content']) > 0, "Content must not be empty"
    print(">>> TEST 3 (Stop generating & partial preservation) PASSED!")

    # ==========================================
    # TEST 5: Multi-turn Follow-up Question
    # ==========================================
    print('\n--- TEST 5: Multi-Turn Question ---')
    tokens_turn2 = []
    done_turn2 = None
    with requests.post(url, json={'content': 'How does it integrate with Convergent Invoicing?'}, headers=headers, stream=True) as r:
        for line in r.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith('data:'):
                    data = json.loads(decoded[5:].strip())
                    if data.get('type') == 'token':
                        tokens_turn2.append(data.get('content'))
                    elif data.get('type') == 'done':
                        done_turn2 = data

    print(f"Turn 2 streamed {len(tokens_turn2)} tokens.")
    print(f"Turn 2 citations count: {len(done_turn2.get('citations', [])) if done_turn2 else 0}")
    print(f"Turn 2 grounding score: {done_turn2.get('grounding_score') if done_turn2 else 'N/A'}")

    msgs2_resp = requests.get(f'http://127.0.0.1:8000/api/chats/{chat_id}/messages', headers=headers)
    msgs2 = msgs2_resp.json()
    print(f"Total messages in DB after 2 turns: {len(msgs2)}")
    for i, m in enumerate(msgs2):
        print(f"  Message {i+1} [{m['role']}]: {m['content'][:70].encode('ascii', errors='replace').decode()}...")
    assert len(msgs2) == 4, f"Expected 4 messages, got {len(msgs2)}"
    print(">>> TEST 5 (Multi-turn conversation persistence) PASSED!")

if __name__ == '__main__':
    run_tests()
