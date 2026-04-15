"""
main.py — Punto de entrada de la aplicación FastAPI.

Lifespan:
  - Carga EmbeddingModel (SentenceTransformer)
  - Carga Reranker (CrossEncoder)
  - Inicializa Retriever (Qdrant + BM25)
  - Inicializa ClaudeClient
  - Construye Orchestrator

Rutas:
  GET  /health   → Estado del sistema
  POST /chat     → Consulta con respuesta SSE
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path

from app.agent.orchestrator import Orchestrator
from app.agent.prompts.loader import init_prompt_store
from app.api.routes import admin, chat, documents, health
from app.config import settings
from app.llm.claude_client import ClaudeClient
from app.rag.embeddings import EmbeddingModel
from app.rag.reranker import Reranker
from app.rag.retriever import Retriever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa y libera recursos al arrancar/detener la app."""
    logger.info("=== LaborIA Backend arrancando ===")

    # 0. Prompts desde archivos .md (antes de todo — rápido, sin GPU)
    prompts_dir = Path(settings.prompts_dir)
    logger.info("Cargando prompts desde %s...", prompts_dir)
    store = init_prompt_store(prompts_dir)
    logger.info(
        "Prompts listos — system_prompt=%d chars, tools overridden=%s",
        len(store.system_prompt), store.build_tools([]),
    )

    # 1. Modelos de ML (costosos — cargar una sola vez)
    logger.info("Cargando EmbeddingModel...")
    embedder = EmbeddingModel(settings.embedding_model)

    logger.info("Cargando Reranker...")
    reranker = Reranker(settings.reranker_model)

    # 2. Retriever (conecta a Qdrant + construye BM25)
    logger.info("Inicializando Retriever...")
    retriever = Retriever(
        qdrant_host=settings.qdrant_host,
        qdrant_port=settings.qdrant_port,
        collection_name=settings.qdrant_collection_cst,
        chunks_path=settings.chunks_path,
        embedding_model=embedder,
        reranker=reranker,
        dense_top_k=settings.retriever_dense_top_k,
        bm25_top_k=settings.retriever_bm25_top_k,
        reranker_top_k=settings.reranker_top_k,
    )

    # 3. Cliente Claude
    logger.info("Inicializando ClaudeClient (modelo: %s)...", settings.claude_default_model)
    claude = ClaudeClient(
        api_key=settings.anthropic_api_key,
        model=settings.claude_default_model,
        max_tokens=settings.claude_max_tokens,
    )

    # 4. Orchestrator
    orchestrator = Orchestrator(retriever=retriever, claude=claude)

    # Guardar en app.state para acceso desde los handlers
    app.state.retriever = retriever
    app.state.claude = claude
    app.state.orchestrator = orchestrator

    logger.info("=== LaborIA Backend listo ===")
    yield

    logger.info("=== LaborIA Backend deteniendo ===")


app = FastAPI(
    title="LaborIA",
    description="Asistente jurídico laboral colombiano — CST + Ley 2466/2025",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    # Wildcard para ngrok (URL cambia en cada sesión) y futuros dominios dinámicos.
    # CORSMiddleware acepta allow_origin_regex junto con allow_origins — se aprueba
    # si el origen está en la lista O coincide con el regex.
    allow_origin_regex=settings.api_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(admin.router)
