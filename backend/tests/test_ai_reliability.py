"""AI reliability regressions (offline). The real provider functions (_call_openrouter, _stream_openrouter,
_call_groq, _stream_groq) run against fake SDK clients that raise the SDK's own exception classes:
error classification and cooldowns, no fail-over after part of an answer was streamed, the per-request
deadline, Stop, truncated output, empty replies, input/prompt size limits and log privacy."""

import importlib
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import groq
import httpx
import httpx2
import openai
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.api import messages as messages_api
from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.schemas.message import MessageCreate
from backend.app.services.conversation_memory_service import MemoryIntent, conversation_memory_service
from backend.app.services.detached_stream import stream_cancellations
from backend.app.services.llm_service import (
    GenerationResult,
    HISTORY_MESSAGE_MAX_CHARS,
    LLMStreamInterrupted,
    ModelCooldowns,
    RequestDeadline,
    SPRINT_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    TRUNCATED_ANSWER_NOTICE,
    UNAVAILABLE_RESPONSE,
    deadline_scope,
    model_cooldowns,
)
from backend.app.services.rag_service import rag_service
from backend.tests.org_helpers import OrgFixtures, headers_for
from backend.tests.test_chat_modes import FakeSession, _sse_events

llm_module = importlib.import_module("backend.app.services.llm_service")
service = llm_module.llm_service

STUB_URL = "http://stub-openrouter.test/api/v1"
SECRET = "PRIVATE-PROMPT-FRAGMENT-7731"
MODERATION_BODY = {
    "message": "Input was flagged by the moderation model",
    "code": 403,
    "metadata": {"reasons": ["violence"], "flagged_input": f"user wrote {SECRET}", "provider_name": "Meta"},
}
INTERRUPTED = "Generation interrupted. Please try again."
PARAGRAPH = "Convergent Invoicing bills the billable items of a contract account. " * 10


# ---------------------------------------------------------------- fakes

def _openai_error(cls, status, body, headers=None):
    response = httpx2.Response(status, request=httpx2.Request("POST", f"{STUB_URL}/chat/completions"),
                               json={"error": body}, headers=headers or {})
    return cls(f"Error code: {status} - {body}", response=response, body=body)


def _groq_error(cls, status, body):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.groq.test/v1/chat"),
                              json={"error": body})
    return cls(f"Error code: {status} - {body}", response=response, body=body)


def _timeout_error():
    return openai.APITimeoutError(request=httpx2.Request("POST", f"{STUB_URL}/chat/completions"))


class FakeStream:
    """An SDK stream: text chunks (finish_reason on the last one), optionally an error after them."""

    def __init__(self, pieces, finish_reason="stop", error=None, on_chunk=None):
        self.pieces, self.finish_reason, self.error, self.on_chunk = list(pieces), finish_reason, error, on_chunk
        self.consumed = 0
        self.closed = False

    def __iter__(self):
        for index, piece in enumerate(self.pieces):
            if self.on_chunk is not None:
                self.on_chunk(index)
            self.consumed += 1
            last = index == len(self.pieces) - 1 and self.error is None
            delta = SimpleNamespace(content=piece)
            yield SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=self.finish_reason if last else None)])
        if self.error is not None:
            raise self.error

    def close(self):
        self.closed = True


class FakeChatClient:
    """Stands in for openai.OpenAI and groq.Groq. `script[model]` is a list of replies used in order (the last
    one repeats): an exception to raise, a FakeStream, a string, or a (content, finish_reason) pair."""

    instances, requests, script = [], [], {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeChatClient.instances.append(self)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        FakeChatClient.requests.append(kwargs)
        replies = FakeChatClient.script[kwargs["model"]]
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        if callable(reply) and not isinstance(reply, FakeStream):
            reply = reply()
        if isinstance(reply, BaseException):
            raise reply
        if kwargs.get("stream"):
            return reply if isinstance(reply, FakeStream) else FakeStream([reply])
        content, finish_reason = reply if isinstance(reply, tuple) else (reply, "stop")
        choice = SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)
        return SimpleNamespace(choices=[choice], usage=None)


def _requested(stream=None):
    return [r["model"] for r in FakeChatClient.requests if stream is None or bool(r.get("stream")) == stream]


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def providers(monkeypatch):
    """The shared llm_service with OpenRouter models or-a, or-b and Groq models gq-a, gq-b, all faked. Keys
    are set here because the suite blanks real provider keys."""
    FakeChatClient.instances, FakeChatClient.requests, FakeChatClient.script = [], [], {}
    monkeypatch.setattr(openai, "OpenAI", FakeChatClient)
    monkeypatch.setattr(groq, "Groq", FakeChatClient)
    monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", STUB_URL)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "LLM_LAST_RESORT_MODELS", "")
    monkeypatch.setattr(settings, "LLM_REQUEST_DEADLINE_SECONDS", 120.0)
    monkeypatch.setattr(service, "allowed_providers", {"openrouter"})
    monkeypatch.setattr(service, "openrouter_api_key", "test-openrouter-key")
    monkeypatch.setattr(service, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(service, "gemini_api_key", "")
    monkeypatch.setattr(service, "OPENROUTER_MODELS", ["or-a", "or-b"])
    monkeypatch.setattr(service, "GROQ_MODELS", ["gq-a", "gq-b"])
    monkeypatch.setattr(service, "_prepare_external_prompts", lambda provider, model, prompt, system: (prompt, system))
    model_cooldowns.clear()
    stream_cancellations.clear()
    yield
    model_cooldowns.clear()
    stream_cancellations.clear()


def _sprint_events(monkeypatch, *, regeneration_index=0, query="Explain the SAP BRIM convergent invoicing run"):
    session = FakeSession()
    monkeypatch.setattr(messages_api, "SessionLocal", lambda: session)
    monkeypatch.setattr(messages_api, "issue_stream_token", lambda *_args: "signed-stream-id-0123456789")
    monkeypatch.setattr(conversation_memory_service, "update_rolling_summary", lambda *_a, **_k: None)
    response = messages_api.handle_sprint_streaming_response(
        "chat-id", query, chat_history=[], current_user=SimpleNamespace(id="user-id", is_admin=False),
        attachments=[], user_message_id="user-message-id", memory={}, conversation_chars=0,
        is_regeneration=bool(regeneration_index), regeneration_index=regeneration_index,
    )
    return _sse_events(response), session


def _saved_answers(session):
    return [row for row in session.added if isinstance(row, Message) and row.role == "assistant"]


def _tokens(events):
    return "".join(event.get("content", "") for event in events if event["type"] == "token")


# ---------------------------------------------------------------- error classification and cooldowns

def test_401_is_a_configuration_error_that_skips_every_model_of_the_provider():
    FakeChatClient.script = {"or-a": [_openai_error(openai.AuthenticationError, 401, {"message": "No auth credentials found"})],
                             "or-b": ["never asked"]}
    meta = GenerationResult()

    assert service._call_openrouter("prompt", "system", result=meta) is None

    assert _requested() == ["or-a"]
    assert meta.failure_category == "auth_error"
    assert not model_cooldowns.available("openrouter", "or-b")


def test_moderation_403_skips_only_that_request_and_never_logs_the_prompt(caplog):
    error = _openai_error(openai.PermissionDeniedError, 403, MODERATION_BODY)
    FakeChatClient.script = {"or-a": [error], "or-b": ["answer from or-b"]}

    with caplog.at_level(logging.INFO, logger="backend.app.services.llm_service"):
        answer = service._call_openrouter("prompt", "system", result=GenerationResult())

    assert answer == "answer from or-b"
    assert ModelCooldowns.is_auth_error(error) is False
    assert model_cooldowns.available("openrouter", "or-a") and model_cooldowns.available("openrouter", "or-b")
    assert SECRET not in caplog.text, "provider error bodies can quote the user's prompt"
    assert "PermissionDeniedError" in caplog.text and "403" in caplog.text


def test_403_that_says_the_key_is_blocked_disables_the_provider():
    error = _openai_error(openai.PermissionDeniedError, 403, {"message": "This API key is disabled", "code": 403})
    FakeChatClient.script = {"or-a": [error], "or-b": ["never asked"]}

    assert service._call_openrouter("prompt", "system", result=GenerationResult()) is None
    assert ModelCooldowns.is_auth_error(error) is True
    assert _requested() == ["or-a"]
    assert not model_cooldowns.available("openrouter", "or-b")


def test_402_out_of_credits_cools_the_whole_provider_down():
    error = _openai_error(openai.APIStatusError, 402, {"message": "Insufficient credits", "code": 402})
    FakeChatClient.script = {"or-a": [error], "or-b": ["never asked"]}
    meta = GenerationResult()

    assert service._call_openrouter("prompt", "system", result=meta) is None
    assert _requested() == ["or-a"]
    assert meta.failure_category == "insufficient_credits"

    clock = FakeClock()
    cooldowns = ModelCooldowns(clock=clock)
    cooldowns.record_failure("openrouter", "or-a", error)
    assert not cooldowns.available("openrouter", "or-b")
    clock.now += ModelCooldowns.PAYMENT_REQUIRED_SECONDS + 1
    assert cooldowns.available("openrouter", "or-b")


def test_404_cools_down_only_the_unknown_model():
    FakeChatClient.script = {"or-a": [_openai_error(openai.NotFoundError, 404, {"message": "No endpoints found"})],
                             "or-b": ["answer from or-b"]}

    assert service._call_openrouter("prompt", "system", result=GenerationResult()) == "answer from or-b"
    assert not model_cooldowns.available("openrouter", "or-a")
    assert model_cooldowns.available("openrouter", "or-b")


def test_429_honours_retry_after():
    clock = FakeClock()
    cooldowns = ModelCooldowns(clock=clock)
    error = _openai_error(openai.RateLimitError, 429, {"message": "Rate limit exceeded"}, headers={"Retry-After": "12"})

    cooldowns.record_failure("openrouter", "or-a", error)

    assert not cooldowns.available("openrouter", "or-a")
    clock.now += 12.5
    assert cooldowns.available("openrouter", "or-a")


def test_429_without_retry_after_honours_openrouter_ratelimit_reset():
    clock, wall = FakeClock(), 1_800_000_000.0
    cooldowns = ModelCooldowns(clock=clock, wall_clock=lambda: wall)
    reset_ms = int((wall + 40) * 1000)
    error = _openai_error(openai.RateLimitError, 429, {"message": "Rate limit exceeded: free-models-per-min"},
                          headers={"X-RateLimit-Reset": str(reset_ms)})

    cooldowns.record_failure("openrouter", "or-a", error)

    clock.now += 39
    assert not cooldowns.available("openrouter", "or-a"), "the 30 s default would already have expired"
    clock.now += 2
    assert cooldowns.available("openrouter", "or-a")


def test_429_through_the_real_call_moves_on_and_cools_the_model_down():
    error = _openai_error(openai.RateLimitError, 429, {"message": "Rate limit exceeded"}, headers={"retry-after": "20"})
    FakeChatClient.script = {"or-a": [error], "or-b": ["answer from or-b"]}
    meta = GenerationResult()

    assert service._call_openrouter("prompt", "system", result=meta) == "answer from or-b"
    assert not model_cooldowns.available("openrouter", "or-a")


def test_timeout_cools_the_model_down_for_a_minute():
    FakeChatClient.script = {"or-a": [_timeout_error()], "or-b": [_timeout_error()]}
    meta = GenerationResult()

    assert service._call_openrouter("prompt", "system", result=meta) is None
    assert meta.failure_category == "timeout"
    assert not model_cooldowns.available("openrouter", "or-a")

    clock = FakeClock()
    cooldowns = ModelCooldowns(clock=clock)
    cooldowns.record_failure("openrouter", "or-a", _timeout_error())
    clock.now += ModelCooldowns.TIMEOUT_SECONDS + 1
    assert cooldowns.available("openrouter", "or-a")


def test_500_is_request_specific():
    FakeChatClient.script = {"or-a": [_openai_error(openai.InternalServerError, 500, {"message": "upstream error"})],
                             "or-b": ["answer from or-b"]}
    meta = GenerationResult()

    assert service._call_openrouter("prompt", "system", result=meta) == "answer from or-b"
    assert model_cooldowns.available("openrouter", "or-a")


def test_groq_403_is_not_a_provider_wide_auth_error_and_is_logged_without_its_body(caplog, monkeypatch):
    monkeypatch.setattr(service, "allowed_providers", {"groq"})
    error = _groq_error(groq.PermissionDeniedError, 403, {"message": f"model blocked for this request: {SECRET}"})
    FakeChatClient.script = {"gq-a": [error], "gq-b": ["answer from gq-b"]}

    with caplog.at_level(logging.INFO, logger="backend.app.services.llm_service"):
        assert service._call_groq("prompt", "system", result=GenerationResult()) == "answer from gq-b"

    assert model_cooldowns.available("groq", "gq-a")
    assert SECRET not in caplog.text


# ---------------------------------------------------------------- empty and whitespace replies

def test_empty_and_whitespace_replies_try_the_next_model_and_are_logged(caplog):
    FakeChatClient.script = {"or-a": ["  \n\t "], "or-b": ["answer from or-b"]}
    meta = GenerationResult()

    with caplog.at_level(logging.INFO, logger="backend.app.services.llm_service"):
        assert service._call_openrouter("prompt", "system", result=meta) == "answer from or-b"

    assert "empty_response" in caplog.text


def test_a_whitespace_only_stream_counts_as_no_output():
    FakeChatClient.script = {"or-a": [FakeStream(["  ", "\n\n"])], "or-b": [FakeStream(["Real ", "answer."])]}

    assert "".join(service._stream_openrouter("prompt", "system")) == "Real answer."
    assert _requested() == ["or-a", "or-b"]


# ---------------------------------------------------------------- no fail-over after streamed text

def _server_error():
    return _openai_error(openai.InternalServerError, 502, {"message": "upstream connection reset"})


def test_a_stream_that_fails_after_text_raises_instead_of_failing_over():
    FakeChatClient.script = {"or-a": [FakeStream(["Partial ", "answer"], error=_server_error())],
                             "or-b": [FakeStream(["A different full answer."])]}
    received = []

    with pytest.raises(LLMStreamInterrupted):
        for chunk in service._stream_openrouter("prompt", "system"):
            received.append(chunk)

    assert "".join(received) == "Partial answer"
    assert _requested() == ["or-a"], "or-b's whole answer must not be appended to or-a's partial one"


def test_an_openrouter_error_event_after_text_is_an_interruption():
    # OpenRouter reports a mid-stream provider failure as an SSE `data: {"error": ...}` event, which the SDK
    # raises as a plain APIError after the chunks already received.
    error = openai.APIError("Provider returned error", httpx2.Request("POST", f"{STUB_URL}/chat/completions"),
                            body={"message": "Provider returned error", "code": 502})
    FakeChatClient.script = {"or-a": [FakeStream(["Partial ", "answer"], error=error)],
                             "or-b": [FakeStream(["A different full answer."])]}

    with pytest.raises(LLMStreamInterrupted):
        list(service._stream_openrouter("prompt", "system"))
    assert _requested() == ["or-a"]


def test_a_stream_that_stops_without_a_finish_reason_after_text_is_an_interruption():
    # A dropped connection (no final chunk, no [DONE]) ends the SDK iteration quietly with finish_reason None.
    FakeChatClient.script = {"or-a": [FakeStream(["Partial ", "answer"], finish_reason=None)],
                             "or-b": [FakeStream(["A different full answer."])]}
    received = []

    with pytest.raises(LLMStreamInterrupted) as interrupted:
        for chunk in service._stream_openrouter("prompt", "system"):
            received.append(chunk)

    assert "".join(received) == "Partial answer"
    assert interrupted.value.category == "stream_incomplete"
    assert _requested() == ["or-a"]


def test_a_stream_that_stops_without_a_finish_reason_before_text_tries_the_next_model():
    FakeChatClient.script = {"or-a": [FakeStream([" "], finish_reason=None)], "or-b": [FakeStream(["Answer."])]}

    assert "".join(service._stream_openrouter("prompt", "system")) == "Answer."


def test_sprint_sse_stream_cut_without_a_finish_reason_saves_nothing(monkeypatch):
    FakeChatClient.script = {"or-a": [FakeStream(["## Partial SAP answer\n\n"], finish_reason=None)],
                             "or-b": [FakeStream(["SECOND FULL ANSWER"])]}

    events, session = _sprint_events(monkeypatch)

    assert events[-1] == {"type": "error", "message": INTERRUPTED}
    assert _saved_answers(session) == []


def test_groq_stream_failure_after_text_does_not_reach_the_next_model_or_provider(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(service, "allowed_providers", {"groq", "openrouter"})
    error = groq.APIConnectionError(request=httpx.Request("POST", "https://api.groq.test/v1/chat"))
    FakeChatClient.script = {"gq-a": [FakeStream(["Half of ", "it"], error=error)],
                             "gq-b": [FakeStream(["gq-b answer"])], "or-a": [FakeStream(["or-a answer"])]}

    with pytest.raises(LLMStreamInterrupted):
        list(service._stream_configured("prompt", "system"))

    assert _requested() == ["gq-a"]


def test_sprint_sse_mid_stream_failure_sends_an_error_event_and_saves_nothing(monkeypatch):
    FakeChatClient.script = {"or-a": [FakeStream(["## Partial SAP answer\n\n"], error=_server_error())],
                             "or-b": [FakeStream(["SECOND FULL ANSWER"])]}

    events, session = _sprint_events(monkeypatch)

    assert _tokens(events) == "## Partial SAP answer\n\n"
    assert events[-1] == {"type": "error", "message": INTERRUPTED}
    assert not any(event["type"] == "done" for event in events)
    assert "SECOND FULL ANSWER" not in str(events)
    assert _saved_answers(session) == [], "a partial answer is never stored as a complete one"
    assert session.closed


def test_regenerate_and_edit_streams_fail_the_same_way(monkeypatch):
    FakeChatClient.script = {model: [FakeStream([f"{model} partial "], error=_server_error())] for model in ("or-a", "or-b")}

    events, session = _sprint_events(monkeypatch, regeneration_index=1)

    assert events[-1] == {"type": "error", "message": INTERRUPTED}
    assert len(_requested()) == 1
    assert _saved_answers(session) == []


def test_scholar_memory_recall_stream_failure_sends_an_error_event(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(messages_api, "SessionLocal", lambda: session)
    monkeypatch.setattr(messages_api, "issue_stream_token", lambda *_args: "signed-stream-id-0123456789")
    monkeypatch.setattr(conversation_memory_service, "get_chat_summary", lambda db, chat_id: None)
    monkeypatch.setattr(conversation_memory_service, "classify_intent", lambda query, chat_history=None: MemoryIntent.HISTORY_RECALL)
    monkeypatch.setattr(conversation_memory_service, "search_history", lambda *a, **k: [
        {"role": "user", "content": "How is dunning configured?", "created_at": "2026-11-01", "id": "m1"}])
    monkeypatch.setattr(conversation_memory_service, "embed_message_content", lambda *_a, **_k: None)
    FakeChatClient.script = {"or-a": [FakeStream(["You asked about ", "dunning"], error=_server_error())],
                             "or-b": [FakeStream(["SECOND FULL ANSWER"])]}

    response = messages_api.handle_streaming_response(
        "chat-id", "What did I ask earlier about dunning?", chat_history=[],
        current_user=SimpleNamespace(id="user-id", is_admin=False), attachments=[], user_message_id="q",
        conversation_chars=0,
    )
    events = _sse_events(response)

    assert _tokens(events) == "You asked about dunning"
    assert events[-1] == {"type": "error", "message": INTERRUPTED}
    assert _saved_answers(session) == []
    assert "or-b" not in _requested()


# ---------------------------------------------------------------- request deadline

def test_the_deadline_stops_further_attempts_and_reports_deadline(monkeypatch):
    clock = FakeClock()

    def slow_timeout():
        clock.now += 50  # this attempt used up the whole budget
        return _timeout_error()

    FakeChatClient.script = {"or-a": [slow_timeout], "or-b": ["too late"]}

    with deadline_scope(RequestDeadline(seconds=30, clock=clock)):
        result = service.generate_answer_result("question", [])

    assert result.text == UNAVAILABLE_RESPONSE and result.available is False
    assert result.failure_category == "deadline"
    assert _requested() == ["or-a"]
    assert FakeChatClient.requests[0]["timeout"] <= 30, "the SDK timeout never exceeds the remaining budget"
    assert model_cooldowns.available("openrouter", "or-a"), "a deadline is not the model's fault"


def test_the_deadline_interrupts_a_stream_between_chunks():
    clock = FakeClock()

    def advance(index):
        if index == 1:
            clock.now += 100

    FakeChatClient.script = {"or-a": [FakeStream(["First part. ", "Second part. ", "Third part."], on_chunk=advance)]}

    with deadline_scope(RequestDeadline(seconds=30, clock=clock)):
        stream = service._stream_openrouter("prompt", "system")
        assert next(stream) == "First part. "
        with pytest.raises(LLMStreamInterrupted) as interrupted:
            next(stream)

    assert interrupted.value.category == "deadline"
    assert FakeChatClient.script["or-a"][0].closed


def test_sprint_sse_deadline_before_any_text_returns_the_unavailable_answer_without_a_second_pass(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(llm_module, "deadline_clock", clock)
    monkeypatch.setattr(settings, "LLM_REQUEST_DEADLINE_SECONDS", 30.0)

    def slow_timeout():
        clock.now += 50
        return _timeout_error()

    FakeChatClient.script = {"or-a": [slow_timeout], "or-b": [FakeStream(["too late"])]}

    events, session = _sprint_events(monkeypatch)

    done = events[-1]
    assert done["type"] == "done" and done["answer"] == UNAVAILABLE_RESPONSE
    assert done["verification_status"] == "unavailable"
    assert _requested() == ["or-a"], "no other model and no non-streaming pass after the deadline"
    assert _saved_answers(session)[0].source_type == "unavailable"


def test_sprint_skips_the_non_stream_pass_when_the_stream_pass_tried_every_model(monkeypatch):
    FakeChatClient.script = {"or-a": [_server_error()], "or-b": [_server_error()]}

    answer = "".join(service.stream_sprint_reply("Explain SAP BRIM convergent invoicing"))

    assert answer == UNAVAILABLE_RESPONSE
    assert _requested(stream=False) == [], "every model already failed while streaming"
    assert _requested(stream=True) == ["or-a", "or-b"]


# ---------------------------------------------------------------- Stop closes the provider stream

def test_stop_stops_reading_the_provider_stream_and_closes_it(monkeypatch):
    def press_stop(index):
        if index == 2:
            stream_cancellations.cancel("signed-stream-id-0123456789")

    stream = FakeStream([f"word{index} " for index in range(50)], on_chunk=press_stop)
    FakeChatClient.script = {"or-a": [stream], "or-b": [FakeStream(["never"])]}

    events, session = _sprint_events(monkeypatch)

    assert stream.closed, "closing the SDK stream stops token usage at the provider"
    assert stream.consumed <= 4, f"kept reading after Stop ({stream.consumed} chunks)"
    assert not any(event["type"] == "done" for event in events)
    assert _saved_answers(session) == [], "the stopped text is saved by save-partial, not by the stream"
    assert _requested() == ["or-a"]


# ---------------------------------------------------------------- truncated output (finish_reason == "length")

def test_a_stream_cut_at_the_token_limit_is_continued():
    FakeChatClient.script = {"or-a": [FakeStream(["The invoicing run creates ", "invoicing documents"],
                                                 finish_reason="length"),
                                      ("and posts them to FI-CA.", "stop")]}

    text = "".join(service._stream_openrouter("prompt", "system"))

    assert text == "The invoicing run creates invoicing documents and posts them to FI-CA."
    assert [(r["model"], bool(r.get("stream"))) for r in FakeChatClient.requests] == [("or-a", True), ("or-a", False)]


def test_a_stream_cut_at_the_token_limit_ends_with_a_notice_when_continuation_fails():
    FakeChatClient.script = {"or-a": [FakeStream(["The invoicing run creates "], finish_reason="length"),
                                      _openai_error(openai.RateLimitError, 429, {"message": "slow down"})]}

    text = "".join(service._stream_openrouter("prompt", "system"))

    assert text == "The invoicing run creates " + TRUNCATED_ANSWER_NOTICE


def test_a_groq_stream_cut_at_the_token_limit_is_continued(monkeypatch):
    monkeypatch.setattr(service, "allowed_providers", {"groq"})
    FakeChatClient.script = {"gq-a": [FakeStream(["Part one."], finish_reason="length"), ("Part two.", "stop")]}

    assert "".join(service._stream_groq("prompt", "system")) == "Part one. Part two."


def test_non_stream_openrouter_keeps_complete_paragraphs_when_continuation_fails():
    truncated = PARAGRAPH + "\n\n" + PARAGRAPH + "\n\nThe invoicing run then"
    FakeChatClient.script = {"or-a": [(truncated, "length"), _server_error()], "or-b": ["never asked"]}
    meta = GenerationResult()

    answer = service._call_openrouter("prompt", "system", result=meta)

    assert answer.endswith(PARAGRAPH.strip()) and "The invoicing run then" not in answer
    assert meta.is_truncated is True and meta.model == "or-a"


def test_a_tiny_truncated_openrouter_answer_moves_to_the_next_model():
    FakeChatClient.script = {"or-a": [("Short start", "length"), _server_error()], "or-b": ["Full answer from or-b."]}

    assert service._call_openrouter("prompt", "system", result=GenerationResult()) == "Full answer from or-b."


# ---------------------------------------------------------------- OpenRouter client settings

def test_both_openrouter_clients_use_the_configured_base_url_and_streams_do_not_retry():
    FakeChatClient.script = {"or-a": ["answer"]}
    service._call_openrouter("prompt", "system", result=GenerationResult())
    "".join(service._stream_openrouter("prompt", "system"))

    assert [client.kwargs["base_url"] for client in FakeChatClient.instances] == [STUB_URL, STUB_URL]
    assert FakeChatClient.instances[1].kwargs["max_retries"] == 0


# ---------------------------------------------------------------- input and prompt size limits

def test_a_message_over_the_limit_is_rejected_with_a_clear_message(monkeypatch):
    monkeypatch.setattr(settings, "MAX_MESSAGE_CHARS", 50)
    assert MessageCreate(content="x" * 50).content == "x" * 50
    with pytest.raises(ValidationError) as error:
        MessageCreate(content="x" * 51)
    assert "too long" in str(error.value) and "50" in str(error.value)


def test_send_and_edit_endpoints_answer_422_for_an_over_long_message(monkeypatch):
    monkeypatch.setattr(settings, "MAX_MESSAGE_CHARS", 100)
    fx = OrgFixtures()
    try:
        user = fx.user()
        with SessionLocal() as db:
            chat = Chat(user_id=user.id, title="Limits")
            db.add(chat)
            db.commit()
            chat_id = chat.id
        client = TestClient(app)
        body = {"content": "SAP " * 100, "mode": "sprint"}
        for url in (f"/api/chats/{chat_id}/messages/stream", f"/api/chats/{chat_id}/messages/some-id/edit"):
            response = client.post(url, headers=headers_for(user.id), json=body)
            assert response.status_code == 422, response.text
            assert "too long" in response.text
    finally:
        fx.cleanup()


def _history(count, size):
    return [{"role": "user" if index % 2 == 0 else "assistant", "content": f"MSG{index:02d} " + "detail " * (size // 7)}
            for index in range(count)]


def test_sprint_prompt_budget_trims_the_oldest_context_and_keeps_the_question(monkeypatch):
    monkeypatch.setattr(settings, "MAX_PROMPT_CHARS", 30000)
    monkeypatch.setattr(settings, "MAX_ATTACHMENT_PROMPT_CHARS", 8000)
    question = "QUESTION-START " + "How is the FI-CA posting of invoicing documents configured? " * 50 + "QUESTION-END"
    recalled = [{"role": "assistant", "content": "RECALLED " + "r" * 50000, "created_at": "2026-10-01", "id": "old"}]

    prompt = service._build_sprint_prompt(
        question, chat_history=_history(20, 6000),
        attachments=[{"name": "a.txt", "text": "A" * 20000}, {"name": "b.txt", "text": "B" * 20000}],
        summary="SUMMARY " * 600, recalled_messages=recalled,
    )

    assert len(prompt) + len(SPRINT_SYSTEM_PROMPT) <= 30000
    assert prompt.endswith(question.strip()), "the user's question is never trimmed"
    assert "MSG19" in prompt, "the newest message survives"
    assert "MSG14" not in prompt and "SUMMARY" not in prompt, "the oldest context goes first"
    assert prompt.count("A") + prompt.count("B") <= 8000 + 200


def test_scholar_prompt_budget_trims_memory_before_evidence_and_keeps_the_question(monkeypatch):
    monkeypatch.setattr(settings, "MAX_PROMPT_CHARS", 30000)
    monkeypatch.setattr(settings, "ANSWER_STYLE_ROUTER_ENABLED", False)
    question = "How does Convergent Invoicing post invoicing documents to FI-CA? " * 20
    evidence = [{"chunk_text": f"PASSAGE{index} " + "e" * 1100, "document_name": f"Doc {index}", "evidence_id": f"E{index}"}
                for index in range(8)]

    prompt = service._build_answer_prompt(
        question, evidence, "knowledge_base", chat_history=_history(20, 5000), summary="SUMMARY " * 400,
        historical_memory=[{"role": "user", "content": "RECALLED " + "r" * 30000, "created_at": "2026-10-01"}],
    )

    assert len(prompt) + len(SYSTEM_PROMPT) <= 30000
    assert prompt.count(question.strip()) == 2, "the question and its restatement stay whole"
    assert "SUMMARY" not in prompt and "RECALLED" not in prompt
    assert "PASSAGE0" in prompt, "evidence is kept before old conversation context"


def test_the_last_line_of_defence_trims_any_oversized_prompt_and_keeps_its_end(monkeypatch):
    from backend.app.services import audit_log

    monkeypatch.setattr(audit_log, "record", lambda *args, **kwargs: None)
    monkeypatch.setattr(settings, "MAX_PROMPT_CHARS", 10000)
    prompt = "START " + "context " * 5000 + "Current SAP question:\nWhat is FI-CA?"

    safe_prompt, safe_system = llm_module.LLMService._prepare_external_prompts(service, "groq", "m", prompt, "system")

    assert len(safe_prompt) + len(safe_system) <= 10000
    assert safe_prompt.endswith("What is FI-CA?") and safe_prompt.startswith("START")


def test_recalled_messages_are_capped_in_prompts():
    text = conversation_memory_service.format_historical_memory_for_prompt(
        [{"role": "assistant", "content": "x" * 50000, "created_at": "2026-10-01", "id": "m1"}]
    )
    assert len(text) < HISTORY_MESSAGE_MAX_CHARS + 300


def test_rag_attachment_passages_stay_within_the_attachment_budget(monkeypatch):
    monkeypatch.setattr(settings, "MAX_ATTACHMENT_PROMPT_CHARS", 5000)
    passages = rag_service._attachment_passages("billing", [{"name": "big.txt", "text": "billing data " * 20000}])
    assert sum(len(p["chunk_text"]) for p in passages) <= 5000


def test_sync_rag_endpoint_runs_inside_a_request_deadline(monkeypatch):
    seen = {}

    def process_query(db, query, **kwargs):
        seen["deadline"] = llm_module.current_deadline()
        return {"answer": "ok", "source_type": "knowledge_base", "grounding_score": 0.9}

    monkeypatch.setattr(rag_service, "process_query", process_query)
    from backend.app.api import rag as rag_api
    from backend.app.schemas.rag import RAGQueryRequest

    rag_api.query_rag(RAGQueryRequest(query="What is FI-CA?"), current_user=SimpleNamespace(id="u", is_admin=True),
                      db=MagicMock())

    assert seen["deadline"] is not None and seen["deadline"].remaining() > 100

