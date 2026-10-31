import asyncio

from backend.app.security.body_size import RequestBodySizeLimitMiddleware


def test_chunked_body_is_rejected_after_limit_without_content_length():
    async def application(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodySizeLimitMiddleware(application, default_limit=3, upload_limit=10)
    incoming = iter([
        {"type": "http.request", "body": b"1234", "more_body": True},
        {"type": "http.request", "body": b"5678", "more_body": False},
    ])
    sent = []
    async def receive():
        return next(incoming)
    async def send(message):
        sent.append(message)
    asyncio.run(middleware({"type": "http", "path": "/api/rag/query"}, receive, send))
    assert sent[0]["status"] == 413


def test_upload_path_uses_its_separate_batch_limit():
    async def application(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodySizeLimitMiddleware(application, default_limit=3, upload_limit=10)
    incoming = iter([{"type": "http.request", "body": b"12345678", "more_body": False}])
    sent = []
    async def receive():
        return next(incoming)
    async def send(message):
        sent.append(message)
    asyncio.run(middleware({"type": "http", "path": "/api/documents/upload"}, receive, send))
    assert sent[0]["status"] == 200
