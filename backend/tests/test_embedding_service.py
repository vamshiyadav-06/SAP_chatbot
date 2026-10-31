import numpy as np
import pytest
import sys
from types import SimpleNamespace

from backend.app.config import settings
from backend.app.models.message import Message, set_embedding_provenance
from backend.app.services.embedding_service import EmbeddingService


def test_embedding_failure_does_not_generate_hash_vectors(monkeypatch):
    service = EmbeddingService()
    monkeypatch.setattr(service, "_get_model", lambda: (_ for _ in ()).throw(RuntimeError("model unavailable")))

    with pytest.raises(RuntimeError, match="model unavailable"):
        service.embed_text("billing document")
    with pytest.raises(RuntimeError, match="model unavailable"):
        service.embed_batch(["billing document"])


def test_fastembed_uses_configured_model_and_normalizes(monkeypatch):
    service = EmbeddingService()
    service.embedding_model = "configured-model"

    class FakeModel:
        def embed(self, texts, **_kwargs):
            assert texts == ["billing document"]
            return iter([np.ones(service.embedding_dim, dtype=np.float32)])

    monkeypatch.setattr(service, "_get_model", lambda: ("fastembed", FakeModel()))
    result = service.embed_text("billing document")

    assert len(result) == service.embedding_dim
    assert np.linalg.norm(result) == pytest.approx(1.0)


def test_fastembed_loader_receives_configured_model(monkeypatch):
    seen = []

    class FakeTextEmbedding:
        def __init__(self, model_name):
            seen.append(model_name)

    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=FakeTextEmbedding))
    service = EmbeddingService()
    service.embedding_model = "operator-selected-model"

    assert service._get_model()[0] == "fastembed"
    assert seen == ["operator-selected-model"]


def test_message_embeddings_are_stamped_with_configured_provenance():
    message = Message(content="history", role="user", chat_id="chat", embedding=[0.0] * settings.EMBEDDING_DIM)
    set_embedding_provenance(None, None, message)
    assert message.embedding_model == settings.EMBEDDING_MODEL
    assert message.embedding_version == settings.EMBEDDING_VERSION
