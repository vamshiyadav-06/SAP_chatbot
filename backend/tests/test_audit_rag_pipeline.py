"""Audit regressions for the RAG orchestrator (AUDIT_REPORT.md F-02, F-03, F-04, F-27). Offline only."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.app.api import messages as messages_api
from backend.app.services.rag_service import rag_service
from backend.tests.offline_rag import DEFAULT_ANSWER, RAG_QUESTION, offline_rag

# Draft with a fabricated procedure; the repair returns the supported answer instead.
UNVERIFIED_DRAFT = (
    "Run transaction ZQQ_FAKE_UNBLOCK and update table ZFAKE_POSTING directly to change the posting area [E1]. "
    "Convergent Invoicing transfers invoicing documents to FI-CA [E1]."
)


def _stream_events(**offline_kwargs):
    with offline_rag(**offline_kwargs):
        return list(rag_service.stream_query(db=MagicMock(), query=RAG_QUESTION))


def test_f02_process_query_completes_retrieval_backed_answer():
    """process_query used undefined names in its diagnostics and raised NameError after generation."""
    with offline_rag() as calls:
        result = rag_service.process_query(db=MagicMock(), query=RAG_QUESTION)

    assert calls["retrieve"] >= 1, "question must go through retrieval"
    assert "posting area" in result["answer"].lower()
    assert result["citations"], "knowledge-base citations are built"
    diagnostics = result["diagnostics"]
    assert diagnostics["retrieved_chunks_count"] == 2
    assert diagnostics["final_context_chunks_count"] >= 1
    assert isinstance(diagnostics["post_processing_modified"], bool)


def test_f03_stream_never_emits_text_before_verification():
    events = _stream_events(answer=UNVERIFIED_DRAFT, repair=DEFAULT_ANSWER)
    types = [e["type"] for e in events]
    stages = [e.get("stage") for e in events]
    verifying_at = stages.index("verifying_claims")
    first_token_at = types.index("token")
    assert first_token_at > verifying_at, "draft tokens were streamed before claim verification"

    done = events[-1]
    streamed = "".join(e["content"] for e in events if e["type"] == "token")
    assert done["type"] == "done"
    assert streamed == done["answer"], "client must receive exactly the verified answer"
    assert "ZQQ_FAKE_UNBLOCK" not in streamed and "ZFAKE_POSTING" not in streamed


def test_f03_stream_text_matches_verified_answer_without_repair():
    events = _stream_events()
    streamed = "".join(e["content"] for e in events if e["type"] == "token")
    assert streamed == events[-1]["answer"]


def _run_stream(response):
    async def collect():
        return [chunk async for chunk in response.body_iterator]
    return asyncio.run(collect())


def test_f03_interrupted_stream_does_not_persist_unverified_text():
    def broken_stream(*args, **kwargs):
        yield {"type": "token", "content": "Unverified partial text that never reached done"}
        raise RuntimeError("provider disconnected")

    save_db = MagicMock()
    user = SimpleNamespace(id="u1", is_admin=False)
    with patch.object(messages_api, "SessionLocal", return_value=save_db), \
            patch.object(messages_api.rag_service, "stream_query", side_effect=broken_stream):
        response = messages_api.handle_streaming_response(
            "chat-1", "question", chat_history=[], current_user=user, attachments=None, user_message_id="m1"
        )
        body = "".join(c if isinstance(c, str) else c.decode() for c in _run_stream(response))

    assert '"type": "error"' in body
    save_db.add.assert_not_called()
    save_db.commit.assert_not_called()
    save_db.close.assert_called_once()


def test_f04_simple_sap_question_goes_through_retrieval_by_default():
    from backend.app.services.query_router import QueryRoute, query_router
    question = "What does FI-CA stand for?"
    assert query_router.route(question).route == QueryRoute.SIMPLE_SAP
    with offline_rag() as calls:
        result = rag_service.process_query(db=MagicMock(), query=question)
        events = list(rag_service.stream_query(db=MagicMock(), query=question))
    assert calls["retrieve"] >= 2, "both paths must retrieve for an SAP question"
    assert result["source_type"] != "direct_llm" and events[-1]["source_type"] != "direct_llm"
    assert result["citations"] and events[-1]["citations"]


def test_f04_small_talk_skips_retrieval_and_is_reported_unverified():
    with offline_rag() as calls:
        result = rag_service.process_query(db=MagicMock(), query="Hey")
        done = list(rag_service.stream_query(db=MagicMock(), query="Hey"))[-1]
    assert calls["retrieve"] == 0
    for payload in (result, done):
        assert payload["grounding_score"] is None
        assert payload["verification_status"] == "unverified"


def test_f49_default_flags_never_trigger_comparator():
    from backend.app.config import settings
    weak = {"should_trigger_tavily": True}
    with patch.object(settings, "AUTO_MULTI_SOURCE_FALLBACK", True), \
            patch.object(settings, "REPO_SOURCE_ENABLED", False), \
            patch.object(settings, "MULTI_SOURCE_COMPARE_ENABLED", False):
        assert rag_service._should_auto_compare(0.10, weak) is False
    with patch.object(settings, "AUTO_MULTI_SOURCE_FALLBACK", True), \
            patch.object(settings, "REPO_SOURCE_ENABLED", True), \
            patch.object(settings, "MULTI_SOURCE_COMPARE_ENABLED", False):
        assert rag_service._should_auto_compare(0.10, weak) is True


def test_f49_weak_evidence_with_default_flags_does_not_call_github_or_web_comparator():
    from backend.app.config import settings
    from backend.app.retrieval.multi_source_compare import multi_source_comparator
    weak_rows = [dict(row, score=0.2, vector_score=0.2) for row in __import__(
        "backend.tests.offline_rag", fromlist=["KB_ROWS"]).KB_ROWS]
    with offline_rag(rows=weak_rows), \
            patch.object(settings, "AUTO_MULTI_SOURCE_FALLBACK", True), \
            patch("backend.app.services.rag_service.reranking_service.rerank_kb",
                  side_effect=lambda q, c, top_n=4: ([dict(x) for x in c][:top_n], 0.2, False)), \
            patch.object(multi_source_comparator, "execute_multi_source_comparison") as compare:
        rag_service.process_query(db=MagicMock(), query=RAG_QUESTION)
        list(rag_service.stream_query(db=MagicMock(), query=RAG_QUESTION))
    compare.assert_not_called()


PARITY_KEYS = ("answer", "source_type", "grounding_score", "verification_status", "citations", "web_sources",
               "follow_up_questions", "answer_decision", "route", "kb_score", "winning_score", "selection_summary")


def _parity(**offline_kwargs):
    with offline_rag(**offline_kwargs):
        sync_result = rag_service.process_query(db=MagicMock(), query=RAG_QUESTION)
    with offline_rag(**offline_kwargs):
        events = list(rag_service.stream_query(db=MagicMock(), query=RAG_QUESTION))
    return sync_result, events[-1]


def test_f27_sync_and_stream_paths_produce_the_same_answer():
    sync_result, done = _parity()
    for key in PARITY_KEYS:
        assert sync_result[key] == done[key], key


def test_f27_parity_holds_when_repair_and_guard_change_the_draft():
    sync_result, done = _parity(answer=UNVERIFIED_DRAFT, repair=DEFAULT_ANSWER)
    for key in PARITY_KEYS:
        assert sync_result[key] == done[key], key
    assert "ZQQ_FAKE_UNBLOCK" not in sync_result["answer"]
