"""
health.py — GET /health
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.agent.models import HealthResponse
from app.api.dependencies import get_retriever
from app.rag.retriever import Retriever

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(
    request: Request,
    retriever: Retriever = Depends(get_retriever),
) -> HealthResponse:
    info = retriever._qdrant.get_collection(retriever.collection_name)
    return HealthResponse(
        status="ok",
        qdrant_points=info.points_count or 0,
        model=request.app.state.claude.model,
        embedding_dim=retriever.embedder.dim,
    )
