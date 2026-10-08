from groq import Groq
from backend.app.config import settings

client = Groq(api_key=settings.GROQ_API_KEY)

test_cases = [
    {
        'history': [{'role': 'user', 'content': 'What is SAP Convergent Invoicing?'}, {'role': 'assistant', 'content': 'SAP Convergent Invoicing is...'}],
        'query': 'can you explain in detail'
    },
    {
        'history': [{'role': 'user', 'content': 'What is a Billable Item in SAP Convergent Invoicing?'}, {'role': 'assistant', 'content': 'A Billable Item is...'}],
        'query': 'what information does it contain?'
    },
    {
        'history': [{'role': 'user', 'content': 'Explain SAP Convergent Charging.'}, {'role': 'assistant', 'content': 'SAP Convergent Charging performs rating...'}],
        'query': 'How does it integrate with CI?'
    },
    {
        'history': [{'role': 'user', 'content': 'Explain SAP BRIM.'}, {'role': 'assistant', 'content': 'SAP BRIM is...'}],
        'query': 'What is the weather today?'
    },
    {
        'history': [{'role': 'user', 'content': 'Explain SAP Convergent Invoicing.'}, {'role': 'assistant', 'content': 'SAP CI is...'}],
        'query': 'Tell me a Python joke.'
    },
    {
        'history': [
            {'role': 'user', 'content': 'What is SAP BRIM?'}, {'role': 'assistant', 'content': 'SAP BRIM is...'},
            {'role': 'user', 'content': 'Explain Convergent Charging.'}, {'role': 'assistant', 'content': 'Convergent Charging is the rating engine...'}
        ],
        'query': 'What happens after rating?'
    }
]

system_prompt = """You are a query rewriting engine for an SAP technical assistant.
Given recent conversation history and the latest user query:
1. If the latest query is a follow-up or contains pronouns ('it', 'this', 'that', 'its') or contextual requests ('explain in detail', 'what happens next', 'how does it integrate', 'transactions'), rewrite it into a self-contained, standalone question incorporating the most recent relevant SAP topic from history. Expand abbreviations in context (e.g. CI -> SAP Convergent Invoicing, CC -> SAP Convergent Charging).
2. If the query is already standalone, or is completely unrelated to the SAP conversation (e.g. asking about weather, sports, jokes, non-SAP topics), output the query EXACTLY as submitted. Do not force SAP into unrelated queries.
3. Output ONLY the standalone question without explanation or quotation marks."""

for i, tc in enumerate(test_cases, 1):
    hist_text = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in tc['history']])
    user_msg = f"Conversation History:\n{hist_text}\n\nLatest User Query: {tc['query']}\n\nStandalone Question:"
    res = client.chat.completions.create(
        model="qwen/qwen3.8-27b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ],
        temperature=0.0,
        max_tokens=80
    )
    ans = res.choices[0].message.content.strip().strip('"\'')
    print(f"Test {i}:")
    print(f"  Query: {tc['query']}")
    print(f"  Rewritten: {ans}")
