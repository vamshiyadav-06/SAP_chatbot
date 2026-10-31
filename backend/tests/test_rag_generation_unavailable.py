"""Generation failure must never turn retrieved evidence into a user-facing answer."""

from unittest.mock import MagicMock, patch

from backend.app.config import settings
from backend.app.services.llm_service import GenerationResult, LLMService, UNAVAILABLE_RESPONSE
from backend.app.services.public_payload import public_done_event
from backend.app.services.rag_service import rag_service
from backend.tests.offline_rag import RAG_QUESTION, offline_rag


EVIDENCE = [{"chunk_text": "PRIVATE_EXCERPT_SENTINEL", "source_type": "knowledge_base"}]


def _service(provider: str, allowed: str, key: str = ""):
    with patch.object(settings, "LLM_PROVIDER", provider), \
            patch.object(settings, "LLM_ALLOWED_PROVIDERS", allowed), \
            patch.object(settings, "GROQ_API_KEY", key), \
            patch.object(settings, "GEMINI_API_KEY", ""), \
            patch.object(settings, "OPENROUTER_API_KEY", ""), \
            patch.object(settings, "LLM_MODEL", "test-model" if provider == "groq" else ""), \
            patch.object(settings, "LLM_GROQ_MODELS", "test-model"):
        return LLMService()


def test_local_provider_returns_explicit_unavailable_without_evidence_excerpt():
    service = _service("local", "")
    with patch.object(settings, "LLM_PROVIDER", "local"):
        result = service.generate_answer_result("question", EVIDENCE)

    assert result.text == UNAVAILABLE_RESPONSE
    assert result.available is False
    assert result.failure_category == "no_provider_allowed"
    assert result.providers_attempted == []
    assert "PRIVATE_EXCERPT_SENTINEL" not in result.text


def test_all_allowed_providers_failing_never_falls_back_to_evidence_text():
    service = _service("groq", "groq", "fake-test-key")
    service.allowed_providers = {"groq"}
    with patch.object(settings, "LLM_PROVIDER", "groq"), \
            patch.object(service, "_call_groq", return_value=None):
        result = service.generate_answer_result("question", EVIDENCE)

    assert result.text == UNAVAILABLE_RESPONSE
    assert result.available is False
    assert result.failure_category == "provider_failed"
    assert result.providers_attempted == ["groq"]
    assert "PRIVATE_EXCERPT_SENTINEL" not in result.text


def test_successful_provider_response_is_returned_with_request_scoped_metadata():
    service = _service("groq", "groq", "fake-test-key")
    service.allowed_providers = {"groq"}
    with patch.object(settings, "LLM_PROVIDER", "groq"), \
            patch.object(service, "_call_groq", return_value="A generated answer."):
        result = service.generate_answer_result("question", EVIDENCE)

    assert result.text == "A generated answer."
    assert result.available is True
    assert result.provider == "groq"
    assert result.model == "test-model"
    assert result.failure_category is None


def test_rag_skips_verifier_for_unavailable_generation():
    def fail_generation(*args, result: GenerationResult, **kwargs):
        result.available = False
        result.failure_category = "provider_failed"
        result.text = UNAVAILABLE_RESPONSE
        return UNAVAILABLE_RESPONSE

    with patch("backend.app.services.rag_service.llm_service.generate_answer", side_effect=fail_generation), \
            patch("backend.app.services.rag_service.grounding_service.verify_answer") as verify:
        result = rag_service._generate_grounded_answer("question", EVIDENCE)

    assert result["verification_status"] == "unavailable"
    assert result["grounded_score"] is None
    assert result["answer"] == UNAVAILABLE_RESPONSE
    verify.assert_not_called()


def test_public_stream_exposes_only_unavailable_status_without_internal_diagnostics():
    payload = public_done_event({
        "type": "done",
        "answer": UNAVAILABLE_RESPONSE,
        "verification_status": "unavailable",
        "provider_used": "groq",
        "diagnostics": {"failure_category": "provider_failed"},
    })

    assert payload["verification_status"] == "unavailable"
    assert "provider_used" not in payload and "diagnostics" not in payload


def test_provider_error_categories_are_safe_and_specific():
    service = LLMService()
    cases = [
        (TimeoutError("request timed out"), "timeout"),
        (RuntimeError("429 rate limit exceeded"), "rate_limited"),
        (RuntimeError("invalid model response"), "invalid_response"),
        (RuntimeError("upstream unavailable"), "provider_error"),
    ]
    for error, expected in cases:
        assert service._provider_failure_category(error) == expected


def test_sync_and_stream_rag_fail_closed_when_every_provider_fails():
    def fail_generation(*args, result: GenerationResult, **kwargs):
        result.available = False
        result.failure_category = "provider_failed"
        result.text = UNAVAILABLE_RESPONSE
        result.providers_attempted = ["groq", "gemini"]
        return UNAVAILABLE_RESPONSE

    with offline_rag():
        with patch("backend.app.services.rag_service.llm_service.generate_answer", side_effect=fail_generation):
            sync = rag_service.process_query(db=MagicMock(), query=RAG_QUESTION)
    with offline_rag():
        with patch("backend.app.services.rag_service.llm_service.generate_answer", side_effect=fail_generation):
            events = list(rag_service.stream_query(db=MagicMock(), query=RAG_QUESTION))

    streamed = "".join(item["content"] for item in events if item["type"] == "token")
    done = events[-1]
    for result in (sync, done):
        assert result["answer"] == UNAVAILABLE_RESPONSE
        assert result["verification_status"] == "unavailable"
        assert result["grounding_score"] is None
        assert result["source_type"] == "unavailable"
    assert streamed == UNAVAILABLE_RESPONSE
    assert "Convergent Invoicing transfers" not in sync["answer"]
