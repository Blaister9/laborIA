"""
dependencies.py — Proveedores de dependencias FastAPI.
Los singletons viven en app.state (inicializados en el lifespan).
"""

from __future__ import annotations

from fastapi import Request

from app.agent.orchestrator import Orchestrator
from app.rag.retriever import Retriever


def get_retriever(request: Request) -> Retriever:
    return request.app.state.retriever


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator
