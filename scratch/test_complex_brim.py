import requests
import json
import time

def test_complex_brim_query():
    auth_resp = requests.post('http://127.0.0.1:8000/api/auth/login', json={'email': 'admin@sap.com', 'password': 'AdminPassword123!'})
    token = auth_resp.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    chat_resp = requests.post('http://127.0.0.1:8000/api/chats', json={'title': 'Complex BRIM End-to-End Stream'}, headers=headers)
    chat_id = chat_resp.json()['id']
    print(f"Chat ID: {chat_id}")

    complex_query = (
        "In an SAP BRIM end-to-end scenario, explain how a usage event originating in SAP Convergent Charging "
        "flows through rating and charge calculation into Convergent Invoicing, how the resulting Billable Item "
        "is processed, and how the financial posting ultimately reaches SAP FI-CA. Identify the key integration "
        "boundaries between Convergent Charging, Convergent Invoicing, and FI-CA, and explain what happens if an "
        "error occurs between the billing and FI-CA stages. Cite the documentation supporting each major step and "
        "explicitly distinguish documented behavior from anything that is not supported by the retrieved evidence."
    )

    url = f'http://127.0.0.1:8000/api/chats/{chat_id}/messages?stream=true'
    print('\n--- Starting Complex BRIM Stream Test ---')
    start_t = time.time()
    first_token_t = None
    status_events = []
    tokens = []
    done_payload = None

    with requests.post(url, json={'content': complex_query}, headers=headers, stream=True) as r:
        for line in r.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith('data:'):
                    data = json.loads(decoded[5:].strip())
                    elapsed = time.time() - start_t
                    if data.get('type') == 'status':
                        status_events.append((data.get('stage'), data.get('message'), round(elapsed, 2)))
                        print(f"[{round(elapsed, 2)}s] Stage: {data.get('stage')} -> {data.get('message')}")
                    elif data.get('type') == 'token':
                        if first_token_t is None:
                            first_token_t = elapsed
                            print(f"[{round(elapsed, 2)}s] FIRST TOKEN RECEIVED!")
                        tokens.append(data.get('content'))
                    elif data.get('type') == 'done':
                        done_payload = data
                        print(f"[{round(elapsed, 2)}s] DONE RECEIVED!")

    print(f"\n--- COMPLEX BRIM RESULTS ---")
    print(f"Total Stream Time: {round(time.time() - start_t, 2)}s")
    print(f"Time to First Token: {round(first_token_t, 2) if first_token_t else 'N/A'}s")
    print(f"Total Tokens Streamed: {len(tokens)}")
    print(f"Total Characters: {sum(len(t) for t in tokens)}")
    print(f"Grounding Score: {done_payload.get('grounding_score') if done_payload else 'N/A'}")
    print(f"Citations Count: {len(done_payload.get('citations', [])) if done_payload else 0}")
    print(f"\nAnswer Preview:\n{(''.join(tokens))[:400].encode('ascii', errors='replace').decode()}...\n")
    print(">>> TEST 2 (Complex BRIM streaming) PASSED!")

if __name__ == '__main__':
    test_complex_brim_query()
