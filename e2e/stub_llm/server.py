"""Stub OpenRouter: a tiny OpenAI-compatible chat-completions server for browser, load and recovery tests.

Never used in production. The E2E / load stacks point OPENROUTER_BASE_URL at it, so the backend's real
OpenRouter client code runs end to end without any chargeable AI call.

    python e2e/stub_llm/server.py --port 9100

Behaviour is chosen per request by a marker anywhere in the LAST user message, or globally with
POST /__control {"mode": "<marker>"} (mode "normal" resets it):
    [[stub:fail500]]  500 error            [[stub:auth401]]   401 invalid key
    [[stub:mod403]]   403 moderation        [[stub:rate429]]   429 with X-RateLimit-Reset
    [[stub:empty]]    empty answer          [[stub:length]]    answer cut off (finish_reason "length")
    [[stub:midstream]] streams a few words, then an SSE error event (how OpenRouter reports it)
    [[stub:drop]]     streams a few words, then the connection closes without [DONE]
    [[stub:slow=N]]   waits N seconds before answering (timeouts / request deadline)
The normal answer names every context token (pattern AB-123) found in earlier messages, so tests can
prove that conversation history reached the provider. GET /__stats returns request counters.
Pure standard library; no dependencies.
"""
import argparse
import json
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = re.compile(r"\b[A-Z]{2,5}-\d{3}\b")
MARKER = re.compile(r"\[\[stub:([a-z0-9]+)(?:=(\d+(?:\.\d+)?))?\]\]")
STATE = {"mode": "normal", "requests": 0, "streams": 0, "by_mode": {}}
LOCK = threading.Lock()


def _text(message):
    content = message.get("content", "")
    if isinstance(content, list):  # OpenAI content parts
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content or "")


def plan(messages):
    """(mode, seconds, answer) for a request."""
    user_turns = [m for m in messages if m.get("role") == "user"]
    last = _text(user_turns[-1]) if user_turns else ""
    found = MARKER.search(last)
    mode, seconds = (found.group(1), float(found.group(2) or 0)) if found else (STATE["mode"], 0.0)
    if mode.startswith("slow"):
        seconds = seconds or 30.0
    earlier = " ".join(_text(m) for m in messages[:-1]) if messages else ""
    tokens = sorted(set(TOKEN.findall(earlier)) - set(TOKEN.findall(MARKER.sub("", last))))
    question = MARKER.sub("", last).strip().splitlines()[-1][:120] if last.strip() else ""
    answer = (f"Stub answer about SAP BRIM. You asked: {question}. "
              f"Context tokens seen: {', '.join(tokens) if tokens else 'none'}. "
              "Convergent Charging rates usage, Convergent Invoicing bills it, and FI-CA posts the invoice.")
    return mode, seconds, answer


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep test output quiet
        pass

    def _json(self, status, body, headers=None):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            return self._json(200, {"object": "list", "data": [{"id": "stub/model", "object": "model"}]})
        if self.path == "/__stats":
            with LOCK:
                return self._json(200, dict(STATE))
        if self.path == "/health":
            return self._json(200, {"status": "ok"})
        return self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/__control":
            with LOCK:
                STATE["mode"] = body.get("mode", "normal")
            return self._json(200, {"mode": STATE["mode"]})
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self._json(404, {"error": {"message": "not found"}})
        if not (self.headers.get("Authorization") or "").startswith("Bearer "):
            return self._json(401, {"error": {"message": "No auth credentials found", "code": 401}})

        mode, seconds, answer = plan(body.get("messages") or [])
        with LOCK:
            STATE["requests"] += 1
            STATE["by_mode"][mode] = STATE["by_mode"].get(mode, 0) + 1
        if seconds:
            time.sleep(seconds)
        errors = {
            "fail500": (500, {"error": {"message": "Internal Server Error", "code": 500}}, {}),
            "auth401": (401, {"error": {"message": "Invalid API key", "code": 401}}, {}),
            "mod403": (403, {"error": {"message": "Input flagged by moderation", "code": 403,
                                       "metadata": {"reasons": ["test"], "flagged_input": "stub"}}}, {}),
            "rate429": (429, {"error": {"message": "Rate limit exceeded", "code": 429}},
                        {"X-RateLimit-Reset": str(int((time.time() + 5) * 1000))}),
        }
        if mode in errors:
            status, payload, headers = errors[mode]
            return self._json(status, payload, headers)
        content = "" if mode == "empty" else answer
        finish = "length" if mode == "length" else "stop"
        model = body.get("model", "stub/model")
        if body.get("stream"):
            return self._stream(model, content, finish, cut=mode if mode in ("midstream", "drop") else None)
        return self._json(200, {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion", "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": len(content.split()), "total_tokens": 10},
        })

    def _stream(self, model, content, finish, cut):
        with LOCK:
            STATE["streams"] += 1
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        def chunk(delta, finish_reason=None):
            payload = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
                       "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()

        chunk({"role": "assistant"})
        words = content.split(" ") if content else []
        for index, word in enumerate(words):
            if cut and index == 4:
                if cut == "midstream":  # OpenRouter reports a provider failure mid-stream as an error event
                    error = {"error": {"message": "Provider returned error", "code": 502}}
                    self.wfile.write(f"data: {json.dumps(error)}\n\n".encode())
                    self.wfile.flush()
                self.close_connection = True
                return  # the connection closes without [DONE]
            chunk({"content": word + (" " if index < len(words) - 1 else "")})
            time.sleep(0.01)
        chunk({}, finish)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9100)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f"stub OpenRouter listening on http://{args.host}:{args.port}/v1", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
