"""Streaming keeps whitespace-only chunks: models emit Markdown line breaks as separate tokens."""

import importlib
from types import SimpleNamespace

import groq

service = importlib.import_module("backend.app.services.llm_service").llm_service


def _chunk(text, finish=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text), finish_reason=finish)])


def test_groq_stream_keeps_newline_only_chunks(monkeypatch):
    chunks = [_chunk("\n"), _chunk("## Steps"), _chunk("\n\n"), _chunk("1. Rate"), _chunk("\n"), _chunk("2. Bill", "stop")]

    class Completions:
        def create(self, **kwargs):
            return iter(chunks)

    class FakeGroq:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr(groq, "Groq", FakeGroq)
    monkeypatch.setattr(service, "allowed_providers", {"groq"})
    monkeypatch.setattr(service, "groq_api_key", "test-key")
    monkeypatch.setattr(service, "_get_models", lambda *a, **k: ["gq-a"])

    assert "".join(service._stream_groq("prompt", "system")) == "## Steps\n\n1. Rate\n2. Bill"
