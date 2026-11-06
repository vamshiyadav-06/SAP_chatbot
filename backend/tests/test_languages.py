"""Answer language: Settings choice, question and answer translation, direct-answer directive."""

import importlib

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import languages
from backend.tests.org_helpers import OrgFixtures, headers_for

client = TestClient(app)
llm_module = importlib.import_module("backend.app.services.llm_service")


@pytest.fixture
def fx():
    fixtures = OrgFixtures()
    yield fixtures
    fixtures.cleanup()


def test_the_user_picks_an_answer_language_in_settings(fx):
    user = fx.user()
    headers = headers_for(user.id)
    assert client.get("/api/auth/me", headers=headers).json()["preferred_language"] == "en"
    chosen = client.patch("/api/auth/me/language", headers=headers, json={"language": "hi"})
    assert chosen.status_code == 200 and chosen.json()["preferred_language"] == "hi"
    assert client.get("/api/auth/me", headers=headers).json()["preferred_language"] == "hi"
    assert client.patch("/api/auth/me/language", headers=headers, json={"language": "xx"}).status_code == 422
    assert client.patch("/api/auth/me/language", json={"language": "hi"}).status_code in (401, 403)


def test_english_text_is_recognised_and_other_text_is_not():
    assert languages.looks_english("What is a billable item in SAP BRIM?")
    assert not languages.looks_english("SAP BRIM में बिलिंग क्या है?")
    assert not languages.looks_english("¿Qué es la facturación convergente?")
    assert not languages.looks_english("FKKINVBILL")  # an identifier alone says nothing about the language


def test_questions_are_translated_to_english_only_when_needed(monkeypatch):
    calls = []
    monkeypatch.setattr(languages, "_complete", lambda prompt, system: calls.append(prompt) or "What is FI-CA?")

    assert languages.question_to_english("FI-CA क्या है?", "hi") == "What is FI-CA?"
    assert languages.question_to_english("What is FI-CA?", "hi") == "What is FI-CA?"  # already English
    assert languages.question_to_english("FI-CA क्या है?", "en") == "FI-CA क्या है?"  # English user, untouched
    assert len(calls) == 1


def test_answers_are_translated_with_citations_and_identifiers_protected(monkeypatch):
    seen = {}
    monkeypatch.setattr(languages, "_complete", lambda prompt, system: seen.setdefault("p", prompt) and "अनुवादित [E1]")

    assert languages.answer_to_language("Run FKKINVBILL [E1].", "hi") == "अनुवादित [E1]"
    assert "Hindi" in seen["p"] and "[E1]" in seen["p"] and "transaction codes" in seen["p"]
    assert languages.answer_to_language("Run FKKINVBILL [E1].", "en") == "Run FKKINVBILL [E1]."


def test_a_translation_failure_never_loses_the_answer(monkeypatch):
    monkeypatch.setattr(languages, "_complete", lambda prompt, system: None)
    assert languages.answer_to_language("Original answer.", "hi") == "Original answer."
    assert languages.question_to_english("FI-CA क्या है?", "hi") == "FI-CA क्या है?"


def test_direct_answers_are_told_to_write_in_the_chosen_language():
    def build():
        yield llm_module.llm_service._build_sprint_prompt("FI-CA क्या है?", [], None)

    in_hindi = list(languages.scoped(build(), "hi"))[0]
    assert "ANSWER LANGUAGE" in in_hindi and "Hindi" in in_hindi
    in_english = list(languages.scoped(build(), "en"))[0]
    assert "ANSWER LANGUAGE" not in in_english


def test_question_language_defaults_to_the_answer_language_and_can_differ(fx):
    headers = headers_for(fx.user().id)
    assert client.get("/api/auth/me", headers=headers).json()["question_language"] is None
    chosen = client.patch("/api/auth/me/question-language", headers=headers, json={"language": "te"})
    assert chosen.status_code == 200 and chosen.json()["question_language"] == "te"
    assert chosen.json()["preferred_language"] == "en"  # the answer language is independent
    assert client.patch("/api/auth/me/question-language", headers=headers, json={"language": "xx"}).status_code == 422
    cleared = client.patch("/api/auth/me/question-language", headers=headers, json={"language": None})
    assert cleared.status_code == 200 and cleared.json()["question_language"] is None
    assert client.patch("/api/auth/me/question-language", json={"language": "te"}).status_code in (401, 403)


def test_question_language_of_prefers_the_explicit_choice():
    from types import SimpleNamespace

    assert languages.question_language_of(SimpleNamespace(preferred_language="hi", question_language=None)) == "hi"
    assert languages.question_language_of(SimpleNamespace(preferred_language="hi", question_language="te")) == "te"
    assert languages.question_language_of(SimpleNamespace(preferred_language="hi", question_language="en")) == "en"
    assert languages.question_language_of(SimpleNamespace(preferred_language=None, question_language="xx")) == "en"
