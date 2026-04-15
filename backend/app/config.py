"""
config.py — Configuración centralizada de LaborIA Backend.
Lee variables desde .env en la raíz del proyecto.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del proyecto (backend/app/config.py → sube 3 niveles)
PROJECT_ROOT = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Anthropic ────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    claude_default_model: str = "claude-sonnet-4-6"
    claude_max_tokens: int = 4096

    # ── Qdrant ───────────────────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_cst: str = "cst_articles"

    # ── Embeddings ───────────────────────────────────────────────────────────
    embedding_model: str = (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    embedding_dim: int = 384

    # ── Reranker ─────────────────────────────────────────────────────────────
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"

    # ── Retrieval ────────────────────────────────────────────────────────────
    retriever_dense_top_k: int = 20   # candidatos densos de Qdrant
    retriever_bm25_top_k: int = 20    # candidatos BM25
    reranker_top_k: int = 5           # resultados finales tras reranking

    # ── Corpus ───────────────────────────────────────────────────────────────
    chunks_path: str = str(PROJECT_ROOT / "corpus" / "parsed" / "chunks.json")

    # ── Admin ────────────────────────────────────────────────────────────────
    # Token para el endpoint POST /admin/reload-prompts.
    # Si está vacío, el endpoint queda deshabilitado (403).
    admin_token: str = ""

    # Directorio de archivos .md de prompts.
    # En Docker: sobreescribir con PROMPTS_DIR=/prompts
    # En dev: por defecto PROJECT_ROOT/prompts/
    prompts_dir: str = str(PROJECT_ROOT / "prompts")

    # ── API ──────────────────────────────────────────────────────────────────
    api_cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://laboriaia.netlify.app",
    ]
    # Regex para orígenes dinámicos (ngrok cambia de URL frecuentemente)
    api_cors_origin_regex: str = r"https://.*\.ngrok-free\.dev"


# Singleton global
settings = Settings()
