from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.app.api.rag import query_rag_stream
from backend.app.schemas.rag import RAGQueryRequest


def test_rag_stream_rejects_inaccessible_supplied_chat_id():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        query_rag_stream(
            RAGQueryRequest(query="What is SAP BRIM?", chat_id="another-users-chat"),
            current_user=SimpleNamespace(id="current-user"),
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Chat not found"
