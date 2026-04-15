"""
models.py — Modelos Pydantic para la API de LaborIA.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Consulta del usuario")
    session_id: str | None = Field(None, description="ID de sesión para contexto multi-turno (futuro)")
    top_k: int = Field(5, ge=1, le=10, description="Artículos a recuperar")


class ArticleSource(BaseModel):
    """Artículo recuperado del corpus, devuelto al cliente como fuente."""
    chunk_id: str
    source: str           # "CST" o "Ley 2466/2025"
    article_number: str
    article_title: str
    text: str
    topics: list[str]
    book: str
    chapter: str
    rerank_score: float = 0.0
    derogated: bool = False
    modified_by: str = ""
    effective_date: str = ""


class ChatEvent(BaseModel):
    """
    Evento SSE. El campo 'type' determina qué campos están presentes:
      - "text":    content = fragmento de texto generado
      - "sources": sources = lista de ArticleSource
      - "error":   content = mensaje de error
      - "done":    sin campos adicionales
    """
    type: str
    content: str | None = None
    sources: list[ArticleSource] | None = None


class HealthResponse(BaseModel):
    status: str
    qdrant_points: int
    model: str
    embedding_dim: int
