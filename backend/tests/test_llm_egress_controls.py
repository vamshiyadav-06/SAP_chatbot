from backend.app.config import settings
from backend.app.services.data_redaction import redact_external_text
from backend.app.services.llm_service import LLMService


def test_outbound_text_redacts_common_pii_and_counts_each_type():
    raw = "mail jane.doe@example.com IBAN DE89370400440532013000 BP 1234567890 phone +1 (212) 555-0198"
    redacted, counts = redact_external_text(raw)
    assert "jane.doe@example.com" not in redacted
    assert "DE89370400440532013000" not in redacted
    assert "1234567890" not in redacted
    assert "+1 (212) 555-0198" not in redacted
    assert counts == {"email": 1, "iban": 1, "sap_account_number": 1, "phone": 1}


def test_provider_allowlist_defaults_to_no_external_providers(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ALLOWED_PROVIDERS", "")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "LLM_ALLOW_FREE_TIER", False)
    instance = LLMService()
    assert instance._provider_order() == []
    assert all(":free" not in model for model in instance.OPENROUTER_MODELS)


def test_free_models_require_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ALLOWED_PROVIDERS", "openrouter")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "LLM_MODEL", "")
    monkeypatch.setattr(settings, "LLM_OPENROUTER_MODELS", "model:free,paid-model")
    monkeypatch.setattr(settings, "LLM_ALLOW_FREE_TIER", True)
    assert LLMService().OPENROUTER_MODELS == ["model:free", "paid-model"]


def test_configured_openrouter_free_models_are_available_for_tier_three(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ALLOWED_PROVIDERS", "groq,gemini,openrouter")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "LLM_MODEL", "")
    monkeypatch.setattr(settings, "LLM_OPENROUTER_MODELS", "router-a:free,router-b:free")
    monkeypatch.setattr(settings, "LLM_ALLOW_FREE_TIER", True)
    service = LLMService()
    assert service.OPENROUTER_MODELS == ["router-a:free", "router-b:free"]
    assert "openrouter" in service._provider_order()


def test_provider_model_and_order_configuration_is_applied(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ALLOWED_PROVIDERS", "gemini,groq")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "LLM_MODEL", "gemini-approved")
    monkeypatch.setattr(settings, "LLM_GEMINI_MODELS", "gemini-fallback,gemini-approved")
    monkeypatch.setattr(settings, "LLM_GROQ_MODELS", "groq-a,groq-b")
    monkeypatch.setattr(settings, "LLM_ALLOW_FREE_TIER", False)
    instance = LLMService()
    assert instance._provider_order() == ["gemini", "groq"]
    assert instance.GEMINI_MODELS == ["gemini-approved", "gemini-fallback"]


def test_local_preference_uses_approved_tier_order(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ALLOWED_PROVIDERS", "groq,gemini")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "local")
    monkeypatch.setattr(settings, "LLM_ALLOW_FREE_TIER", False)
    assert LLMService()._provider_order() == ["groq", "gemini"]


def test_external_prompt_is_redacted_and_audited(monkeypatch):
    from backend.app.services import audit_log

    events = []
    monkeypatch.setattr(audit_log, "record", lambda *args, **kwargs: events.append((args, kwargs)))
    safe_prompt, safe_system = LLMService()._prepare_external_prompts(
        "groq", "approved-model", "Contact jane@example.com, BP 1234567890", "System"
    )
    assert "jane@example.com" not in safe_prompt
    assert "1234567890" not in safe_prompt
    assert safe_system == "System"
    assert events[0][0][0] == "llm_egress"
    details = events[0][1]["details"]
    assert details["provider"] == "groq"
    assert details["model"] == "approved-model"
    assert details["redaction_counts"] == {"email": 1, "sap_account_number": 1}


def test_groq_transport_receives_redacted_prompt(monkeypatch):
    from types import SimpleNamespace
    from backend.app.services import audit_log

    monkeypatch.setattr(settings, "LLM_ALLOWED_PROVIDERS", "groq")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "LLM_MODEL", "approved-groq")
    monkeypatch.setattr(settings, "LLM_GROQ_MODELS", "approved-groq")
    monkeypatch.setattr(settings, "LLM_ALLOW_FREE_TIER", False)
    captured = {}

    class FakeGroq:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            choice = SimpleNamespace(message=SimpleNamespace(content="safe answer"), finish_reason="stop")
            return SimpleNamespace(choices=[choice])

    monkeypatch.setattr("groq.Groq", FakeGroq)
    monkeypatch.setattr(audit_log, "record", lambda *args, **kwargs: None)
    instance = LLMService()
    instance.groq_api_key = "test-key"
    instance.generate_completion("Contact jane@example.com, BP 1234567890", "system")
    outbound = captured["messages"][1]["content"]
    assert "jane@example.com" not in outbound
    assert "1234567890" not in outbound


def test_vision_external_calls_are_off_by_default(monkeypatch):
    from backend.app.services.image_vision_service import _call_vision_models

    monkeypatch.setattr(settings, "VISION_EXTERNAL_ENABLED", False)
    assert _call_vision_models("data:image/png;base64,example") == (None, None)
