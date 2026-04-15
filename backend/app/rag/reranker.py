"""
reranker.py — Singleton de CrossEncoder para reranking local (sin APIs externas).

Modelo: cross-encoder/ms-marco-MiniLM-L-12-v2
  - Entrenado en MS MARCO passage ranking
  - Funciona bien con español formal/legal
  - ~85MB, corre en CPU
"""

from __future__ import annotations

from sentence_transformers import CrossEncoder


class Reranker:
    """Reranker basado en CrossEncoder."""

    def __init__(self, model_name: str) -> None:
        print(f"[Reranker] Cargando modelo: {model_name}")
        self._model = CrossEncoder(model_name)
        print("[Reranker] Listo.")

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 5,
        text_key: str = "text",
    ) -> list[dict]:
        """
        Reordena candidates por relevancia respecto a query.

        Args:
            query: Consulta del usuario.
            candidates: Lista de dicts con al menos text_key.
            top_k: Cuántos devolver.
            text_key: Campo del dict que contiene el texto a puntuar.

        Returns:
            Lista ordenada por score descendente, con campo 'rerank_score' añadido.
        """
        if not candidates:
            return []

        pairs = [(query, c[text_key]) for c in candidates]
        scores: list[float] = self._model.predict(pairs).tolist()

        scored = [
            {**c, "rerank_score": score}
            for c, score in zip(candidates, scores)
        ]
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k]
