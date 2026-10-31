"""
Signed stream ids (AUDIT_REPORT F-37).

When an answer stream starts, the server issues a token bound to the user, the chat and an expiry.
POST .../save-partial accepts the text a user saw only with such a token, once. Tokens are HMAC-signed
with a key derived from JWT_SECRET, so no server-side state is needed to validate them.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from backend.app.config import settings

STREAM_TOKEN_TTL_SECONDS = 2 * 60 * 60


def _key() -> bytes:
    return hashlib.sha256(b"stream-token:" + settings.JWT_SECRET.encode("utf-8")).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_stream_token(user_id: str, chat_id: str, ttl_seconds: int = STREAM_TOKEN_TTL_SECONDS) -> str:
    payload = json.dumps(
        {"u": user_id, "c": chat_id, "n": secrets.token_hex(12), "e": int(time.time()) + ttl_seconds},
        separators=(",", ":"),
    ).encode("utf-8")
    signature = hmac.new(_key(), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(signature)}"


def verify_stream_token(token: str, user_id: str, chat_id: str) -> Optional[str]:
    """The token's nonce if it is authentic, unexpired and issued for this user and chat; else None."""
    try:
        payload_b64, signature_b64 = (token or "").split(".", 1)
        payload = _unb64(payload_b64)
        expected = hmac.new(_key(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature_b64)):
            return None
        claims = json.loads(payload)
    except (ValueError, TypeError):
        return None
    if claims.get("u") != user_id or claims.get("c") != chat_id or int(claims.get("e", 0)) < time.time():
        return None
    return str(claims.get("n") or "") or None
