# ─────────────────────────────────────────────────────────────────────────────
# LaborIA — Backend Dockerfile
# Build context: project root (needs backend/ AND corpus/)
#
# Stages:
#   deps    → instala dependencias Python (layer cacheada)
#   runtime → copia deps + descarga modelos HuggingFace + copia código
#
# Los modelos se BAKEAN en la imagen para evitar descarga en cada cold start.
# Tamaño final: ~1.5 GB. Build time: ~8-12 min (primera vez).
# ─────────────────────────────────────────────────────────────────────────────

# ── Etapa 1: instalar dependencias Python ─────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Etapa 2: descargar modelos HuggingFace ────────────────────────────────────
FROM python:3.11-slim AS model-cache

COPY --from=deps /install /usr/local

# Descarga y cachea ambos modelos ML en la imagen
# Esto evita descargas de ~600 MB en cada arranque del contenedor
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
print('Descargando embedding model...'); \
SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'); \
print('Descargando reranker model...'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-12-v2'); \
print('Modelos listos.');"


# ── Etapa 3: imagen final de runtime ──────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Dependencias del sistema (solo curl para healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Paquetes Python desde etapa deps
COPY --from=deps /install /usr/local

# Modelos ML pre-descargados (cache de HuggingFace)
COPY --from=model-cache /root/.cache/huggingface /root/.cache/huggingface

# Código del backend
COPY backend/ .

# Corpus: chunks.json para el índice BM25 en memoria
# config.py calcula PROJECT_ROOT incorrectamente en Docker,
# por eso se sobreescribe CHUNKS_PATH con la ruta absoluta real.
COPY corpus/parsed/chunks.json /app/corpus/parsed/chunks.json
ENV CHUNKS_PATH=/app/corpus/parsed/chunks.json

# Prompts editables: los .md se montan aquí en producción.
# En Docker Compose se puede montar como volumen para edición en caliente:
#   volumes: ["./prompts:/prompts"]
# Si no se monta, se usan los que están bakeados en la imagen.
COPY prompts/ /prompts/
ENV PROMPTS_DIR=/prompts

# Puerto de la aplicación
EXPOSE 8080

# Healthcheck: espera hasta 2 min para que carguen los modelos ML
HEALTHCHECK --interval=30s --timeout=15s --start-period=120s --retries=5 \
    CMD curl -f http://localhost:8080/health || exit 1

# workers=1 porque los modelos ML no son thread-safe para múltiples procesos
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", \
     "--workers", "1", "--log-level", "info"]
