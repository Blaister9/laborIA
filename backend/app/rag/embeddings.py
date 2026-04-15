"""
embeddings.py — Singleton de SentenceTransformer para generar vectores de consulta.
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingModel:
    """Wrapper sobre SentenceTransformer con carga lazy."""

    def __init__(self, model_name: str) -> None:
        print(f"[Embeddings] Cargando modelo: {model_name}")
        self._model = SentenceTransformer(model_name)
        get_dim = getattr(
            self._model,
            "get_embedding_dimension",
            getattr(self._model, "get_sentence_embedding_dimension", None),
        )
        self.dim: int = get_dim()
        print(f"[Embeddings] Listo — dim={self.dim}")

    def embed(self, text: str) -> list[float]:
        """Genera el embedding de un texto de consulta."""
        vector: np.ndarray = self._model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Genera embeddings para una lista de textos."""
        vectors: np.ndarray = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()
