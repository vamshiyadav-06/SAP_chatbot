import logging
import numpy as np
from typing import List
from backend.app.config import settings

logger = logging.getLogger(__name__)

import threading

class EmbeddingService:
    def __init__(self):
        self._model = None
        self.embedding_dim = settings.EMBEDDING_DIM
        self.embedding_model = settings.EMBEDDING_MODEL
        self.embedding_version = settings.EMBEDDING_VERSION
        self._query_cache: dict = {}
        self._cache_lock = threading.Lock()

    def _get_model(self):
        if self._model is not None:
            return self._model
        # Try FastEmbed ONNX runtime first (robust, fast, no AppLocker/torch DLL block)
        try:
            from fastembed import TextEmbedding
            logger.info("Loading FastEmbed model: %s", self.embedding_model)
            self._model = ("fastembed", TextEmbedding(model_name=self.embedding_model))
            logger.info("FastEmbed ONNX model loaded successfully.")
            return self._model
        except Exception as fe_err:
            logger.info("FastEmbed could not load configured embedding model (%s); trying SentenceTransformer.", type(fe_err).__name__)

        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
            self._model = ("st", SentenceTransformer(settings.EMBEDDING_MODEL))
            logger.info("SentenceTransformer model loaded successfully.")
            return self._model
        except Exception as e:
            logger.error("Could not load SentenceTransformer model (%s).", type(e).__name__)
            raise RuntimeError(f"Unable to load embedding model '{self.embedding_model}'.") from e

    def embed_text(self, text: str) -> List[float]:
        cleaned = text.strip()
        if not cleaned:
            return [0.0] * self.embedding_dim

        # Check embedding cache
        with self._cache_lock:
            if cleaned in self._query_cache:
                return self._query_cache[cleaned]

        tag, model = self._get_model()
        try:
            if tag == "fastembed":
                emb = list(model.embed([cleaned]))[0]
            else:
                emb = model.encode(cleaned, convert_to_numpy=True)
            emb = np.array(emb, dtype=np.float32)
            if emb.shape != (self.embedding_dim,):
                raise ValueError(f"Expected {self.embedding_dim} dimensions, received {emb.shape}.")
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            res = emb.tolist()
        except Exception as e:
            logger.error("Embedding encoding failed (%s, %s).", tag, type(e).__name__, exc_info=True)
            raise RuntimeError(f"Embedding failed for configured model '{self.embedding_model}'.") from e
        with self._cache_lock:
            if len(self._query_cache) >= 1024:
                self._query_cache.pop(next(iter(self._query_cache)))
            self._query_cache[cleaned] = res
        return res

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        cleaned_texts = [t.strip() for t in texts]
        tag, model = self._get_model()
        try:
            if tag == "fastembed":
                embs = list(model.embed(cleaned_texts, batch_size=64))
            else:
                embs = model.encode(cleaned_texts, batch_size=32, convert_to_numpy=True)
            result = []
            for emb in embs:
                emb = np.asarray(emb, dtype=np.float32)
                if emb.shape != (self.embedding_dim,):
                    raise ValueError(f"Expected {self.embedding_dim} dimensions, received {emb.shape}.")
                norm = np.linalg.norm(emb)
                if norm > 0:
                    emb = emb / norm
                result.append(emb.tolist())
            if len(result) != len(cleaned_texts):
                raise ValueError("Embedding model returned an unexpected number of vectors.")
            return result
        except Exception as e:
            logger.error("Batch embedding failed (%s, %s).", tag, type(e).__name__, exc_info=True)
            raise RuntimeError(f"Embedding failed for configured model '{self.embedding_model}'.") from e

embedding_service = EmbeddingService()
