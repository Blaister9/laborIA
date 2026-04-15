"""
retriever.py — Retriever híbrido: dense (Qdrant) + sparse (BM25) + reranking.

Flujo:
  1. Dense: query_points en Qdrant con embedding de la consulta
  2. Sparse: BM25 sobre el corpus completo cargado en memoria
  3. Fusión: Reciprocal Rank Fusion (RRF)
  4. Reranking: CrossEncoder sobre los candidatos fusionados
"""

from __future__ import annotations

import json
from pathlib import Path

from rank_bm25 import BM25Okapi

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchAny
except ImportError as e:
    raise ImportError("pip install qdrant-client") from e

from app.rag.embeddings import EmbeddingModel
from app.rag.reranker import Reranker

RRF_K = 60  # constante estándar de RRF


class Retriever:
    """
    Retriever híbrido para artículos del CST y Ley 2466.
    Se inicializa una vez en el lifespan de FastAPI.
    """

    def __init__(
        self,
        *,
        qdrant_host: str,
        qdrant_port: int,
        collection_name: str,
        chunks_path: str,
        embedding_model: EmbeddingModel,
        reranker: Reranker,
        dense_top_k: int = 20,
        bm25_top_k: int = 20,
        reranker_top_k: int = 5,
    ) -> None:
        self.collection_name = collection_name
        self.embedder = embedding_model
        self.reranker = reranker
        self.dense_top_k = dense_top_k
        self.bm25_top_k = bm25_top_k
        self.reranker_top_k = reranker_top_k

        # ── Qdrant (HTTP — Docker en localhost:6333) ─────────────────────────
        print(f"[Retriever] Conectando a Qdrant HTTP: {qdrant_host}:{qdrant_port}")
        self._qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
        info = self._qdrant.get_collection(collection_name)
        print(f"[Retriever] Colección '{collection_name}' — {info.points_count} puntos")

        # ── BM25 ─────────────────────────────────────────────────────────────
        print(f"[Retriever] Construyendo índice BM25 desde {chunks_path}")
        self._chunks: list[dict] = json.loads(
            Path(chunks_path).read_text(encoding="utf-8")
        )
        # Mapa chunk_id → chunk para lookup rápido
        self._chunk_by_id: dict[str, dict] = {
            c["chunk_id"]: c for c in self._chunks
        }
        tokenized = [
            c.get("text_for_embedding", c.get("text", "")).lower().split()
            for c in self._chunks
        ]
        self._bm25 = BM25Okapi(tokenized)
        print(f"[Retriever] BM25 listo — {len(self._chunks)} documentos")

    # ── Búsqueda pública ─────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        topics: list[str] | None = None,
    ) -> list[dict]:
        """
        Ejecuta búsqueda híbrida y retorna artículos rerankeados.

        Args:
            query: Consulta en lenguaje natural.
            top_k: Resultados finales (usa reranker_top_k por defecto).
            topics: Filtrar por temas (ej. ["terminación_contrato", "cesantías"]).

        Returns:
            Lista de dicts con campos del payload + rerank_score.
        """
        final_k = top_k or self.reranker_top_k

        # 1. Búsqueda densa en Qdrant
        dense_hits = self._dense_search(query, topics=topics)

        # 2. Búsqueda BM25
        bm25_hits = self._bm25_search(query, topics=topics)

        # 3. Fusión RRF
        fused = self._rrf_merge(dense_hits, bm25_hits)

        # 4. Reranking
        reranked = self.reranker.rerank(
            query=query,
            candidates=fused,
            top_k=final_k,
            text_key="text_for_rerank",
        )

        return reranked

    # ── Dense ────────────────────────────────────────────────────────────────

    def _dense_search(
        self,
        query: str,
        topics: list[str] | None = None,
    ) -> list[dict]:
        vector = self.embedder.embed(query)

        qdrant_filter = None
        if topics:
            qdrant_filter = Filter(
                must=[
                    FieldCondition(
                        key="topics",
                        match=MatchAny(any=topics),
                    )
                ]
            )

        response = self._qdrant.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=self.dense_top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        results = []
        for point in response.points:
            payload = dict(point.payload)
            payload["dense_score"] = point.score
            payload["text_for_rerank"] = payload.get("text", "")
            results.append(payload)

        return results

    # ── BM25 ─────────────────────────────────────────────────────────────────

    def _bm25_search(
        self,
        query: str,
        topics: list[str] | None = None,
    ) -> list[dict]:
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)

        # Ordenar por score y tomar top N
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in indexed:
            if len(results) >= self.bm25_top_k:
                break
            if score <= 0:
                break

            chunk = self._chunks[idx]

            # Filtrar por topics si se especificaron
            if topics:
                chunk_topics = chunk.get("topics", [])
                if not any(t in chunk_topics for t in topics):
                    continue

            payload = {
                "chunk_id": chunk.get("chunk_id", ""),
                "source": chunk.get("source", ""),
                "book": chunk.get("book", ""),
                "title": chunk.get("title", ""),
                "chapter": chunk.get("chapter", ""),
                "article_number": chunk.get("article_number", ""),
                "article_number_int": chunk.get("article_number_int", 0),
                "article_title": chunk.get("article_title", ""),
                "text": chunk.get("text", ""),
                "topics": chunk.get("topics", []),
                "modified_by": chunk.get("modified_by", ""),
                "effective_date": chunk.get("effective_date", ""),
                "derogated": chunk.get("derogated", False),
                "frequently_consulted": chunk.get("frequently_consulted", False),
                "chunk_type": chunk.get("chunk_type", "article"),
                "articles_in_group": chunk.get("articles_in_group", []),
                "bm25_score": score,
                "text_for_rerank": chunk.get(
                    "text_for_embedding", chunk.get("text", "")
                ),
            }
            results.append(payload)

        return results

    # ── RRF ──────────────────────────────────────────────────────────────────

    def _rrf_merge(
        self,
        dense: list[dict],
        sparse: list[dict],
    ) -> list[dict]:
        """
        Reciprocal Rank Fusion de dos listas de resultados.
        Usa chunk_id para deduplicar.
        """
        scores: dict[str, float] = {}
        by_id: dict[str, dict] = {}

        for rank, doc in enumerate(dense):
            cid = doc.get("chunk_id", f"dense_{rank}")
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
            by_id[cid] = doc

        for rank, doc in enumerate(sparse):
            cid = doc.get("chunk_id", f"sparse_{rank}")
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
            if cid not in by_id:
                by_id[cid] = doc

        merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [by_id[cid] for cid, _ in merged]
