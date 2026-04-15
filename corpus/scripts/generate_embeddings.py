"""
generate_embeddings.py — Vectoriza los chunks y los carga en Qdrant.

Proceso:
  1. Leer corpus/parsed/chunks.json
  2. Generar embeddings con sentence-transformers (local, $0 costo)
  3. Crear colección en Qdrant con el esquema correcto
  4. Cargar todos los chunks con sus embeddings y payload (metadata)
  5. Crear índices en los campos de filtrado clave

Uso:
    python generate_embeddings.py                    # Carga completa
    python generate_embeddings.py --dry-run          # Test sin cargar a Qdrant
    python generate_embeddings.py --reset            # Borra colección y recarga
    python generate_embeddings.py --batch-size 32   # Ajusta el batch size

Requisitos:
    docker compose up -d qdrant   # Qdrant debe estar corriendo
    pip install sentence-transformers qdrant-client tqdm
"""

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# Namespace fijo para generar UUIDs determinísticos desde chunk_ids
LABORIA_UUID_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def chunk_id_to_uuid(chunk_id: str) -> str:
    """Convierte un chunk_id string en un UUID v5 determinístico."""
    return str(uuid.uuid5(LABORIA_UUID_NS, chunk_id))

# ── Imports con mensajes de error claros ────────────────────────────────────────

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("[ERROR] sentence-transformers no instalado.")
    print("  pip install sentence-transformers")
    sys.exit(1)

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PayloadSchemaType,
        PointStruct,
        VectorParams,
    )
except ImportError:
    print("[ERROR] qdrant-client no instalado.")
    print("  pip install qdrant-client")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    # tqdm es opcional — usar fallback simple si no está instalado
    def tqdm(iterable, **kwargs):
        return iterable

PARSED_DIR = Path(__file__).parent.parent / "parsed"

# ── Configuración ───────────────────────────────────────────────────────────────

# Modelo de embeddings: multilingüe, funciona bien con español formal/legal
# Alternativas en orden de calidad:
#   1. "intfloat/multilingual-e5-large"     → 1024 dims, mejor calidad, 1.2GB
#   2. "paraphrase-multilingual-MiniLM-L12-v2" → 384 dims, más rápido, 470MB
#   3. "paraphrase-multilingual-mpnet-base-v2"  → 768 dims, balance
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_CST", "cst_articles")

DEFAULT_BATCH_SIZE = 32

# Campos del payload que se indexarán para filtrado eficiente en Qdrant
INDEXED_FIELDS = {
    "source": PayloadSchemaType.KEYWORD,
    "book": PayloadSchemaType.KEYWORD,
    "article_number_int": PayloadSchemaType.INTEGER,
    "topics": PayloadSchemaType.KEYWORD,       # keyword permite filtro sobre arrays
    "modified_by": PayloadSchemaType.KEYWORD,
    "derogated": PayloadSchemaType.KEYWORD,    # bool se indexa como keyword en Qdrant
    "frequently_consulted": PayloadSchemaType.KEYWORD,
    "chunk_type": PayloadSchemaType.KEYWORD,
}


# ── Embedding ───────────────────────────────────────────────────────────────────


def load_model(model_name: str) -> SentenceTransformer:
    print(f"Cargando modelo de embeddings: {model_name}")
    print("  (Primera vez: descarga ~470MB. Luego se cachea localmente.)")
    model = SentenceTransformer(model_name)
    dim = model.get_sentence_embedding_dimension()
    print(f"  Dimensión del embedding: {dim}")
    return model


def embed_batch(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    """Genera embeddings para un batch de textos."""
    vectors = model.encode(
        texts,
        normalize_embeddings=True,  # Normalizar para similitud coseno
        show_progress_bar=False,
    )
    return vectors.tolist()


# ── Qdrant ──────────────────────────────────────────────────────────────────────


QDRANT_LOCAL_PATH = str(Path(__file__).parent.parent.parent / "qdrant_local")


def get_qdrant_client(local: bool = False) -> QdrantClient:
    """
    Intenta conectar a Qdrant via Docker. Si falla (o --local), usa modo
    de almacenamiento local en disco (sin Docker necesario).
    """
    if local:
        print(f"Modo local: Qdrant en disco -> {QDRANT_LOCAL_PATH}")
        client = QdrantClient(path=QDRANT_LOCAL_PATH)
        print("  Conectado (modo local en disco).")
        return client

    print(f"Conectando a Qdrant en {QDRANT_HOST}:{QDRANT_PORT}...")
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=5)
        info = client.get_collections()
        print(f"  Conectado (Docker). Colecciones: {[c.name for c in info.collections]}")
        return client
    except Exception as e:
        print(f"  [WARN] Docker Qdrant no disponible ({e})")
        print(f"  Fallback: usando Qdrant en disco -> {QDRANT_LOCAL_PATH}")
        client = QdrantClient(path=QDRANT_LOCAL_PATH)
        print("  Conectado (modo local en disco).")
        return client


def setup_collection(
    client: QdrantClient,
    collection_name: str,
    embedding_dim: int,
    reset: bool = False,
) -> None:
    """Crea la colección en Qdrant con el esquema correcto."""
    existing = [c.name for c in client.get_collections().collections]

    if collection_name in existing:
        if reset:
            print(f"  [RESET] Borrando colección existente: {collection_name}")
            client.delete_collection(collection_name)
        else:
            print(f"  Colección '{collection_name}' ya existe. Usando la existente.")
            print("  (Usa --reset para borrarla y recrearla)")
            return

    print(f"  Creando colección: {collection_name} (dim={embedding_dim})")
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=embedding_dim,
            distance=Distance.COSINE,
        ),
    )

    # Crear índices en campos de filtrado
    print("  Creando índices de payload...")
    for field_name, field_type in INDEXED_FIELDS.items():
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=field_type,
        )
        print(f"    Índice creado: {field_name} ({field_type})")

    print(f"  Colección '{collection_name}' lista.")


def build_payload(chunk: dict) -> dict:
    """
    Construye el payload para Qdrant a partir de un chunk.
    Excluye el text_for_embedding (ya está en el vector).
    Incluye todo lo necesario para filtrar y mostrar resultados.
    """
    return {
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
    }


def load_to_qdrant(
    client: QdrantClient,
    collection_name: str,
    model: SentenceTransformer,
    chunks: list[dict],
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
) -> dict:
    """
    Vectoriza y carga todos los chunks en Qdrant.
    Retorna estadísticas de la carga.
    """
    total = len(chunks)
    loaded = 0
    skipped = 0
    errors = 0

    print(f"\nCargando {total} chunks en '{collection_name}'...")
    print(f"  Batch size: {batch_size}")

    # Verificar cuáles chunks ya existen (para carga incremental)
    existing_ids = set()
    if not dry_run:
        try:
            # Scroll para obtener IDs existentes
            # Solo relevante si no usamos --reset
            scroll_result = client.scroll(
                collection_name=collection_name,
                limit=10000,
                with_payload=False,
                with_vectors=False,
            )
            existing_ids = {str(p.id) for p in scroll_result[0]}
            if existing_ids:
                print(f"  {len(existing_ids)} chunks ya existen (carga incremental)")
        except Exception:
            pass  # Colección vacía, continuar

    # Procesar en batches
    for batch_start in tqdm(
        range(0, total, batch_size),
        desc="Vectorizando y cargando",
        unit="batch",
    ):
        batch = chunks[batch_start : batch_start + batch_size]

        # Filtrar chunks ya existentes (comparar por UUID)
        new_chunks = []
        for c in batch:
            chunk_id = c.get("chunk_id", "")
            point_uuid = chunk_id_to_uuid(chunk_id)
            if point_uuid in existing_ids:
                skipped += 1
            else:
                new_chunks.append(c)

        if not new_chunks:
            continue

        # Generar embeddings
        texts = [c.get("text_for_embedding", c.get("text", "")) for c in new_chunks]

        try:
            vectors = embed_batch(model, texts)
        except Exception as e:
            print(f"\n  [ERROR] Fallo al vectorizar batch {batch_start}: {e}")
            errors += len(new_chunks)
            continue

        if dry_run:
            loaded += len(new_chunks)
            continue

        # Construir PointStructs para Qdrant
        # Qdrant requiere UUIDs como IDs — generamos UUID v5 determinístico desde chunk_id
        points = []
        for chunk, vector in zip(new_chunks, vectors):
            chunk_id = chunk.get("chunk_id", f"chunk_{batch_start}")
            point_uuid = chunk_id_to_uuid(chunk_id)
            payload = build_payload(chunk)
            payload["chunk_id"] = chunk_id  # Guardar el ID legible como campo del payload
            points.append(
                PointStruct(
                    id=point_uuid,
                    vector=vector,
                    payload=payload,
                )
            )

        try:
            client.upsert(
                collection_name=collection_name,
                points=points,
            )
            loaded += len(new_chunks)
        except Exception as e:
            print(f"\n  [ERROR] Fallo al insertar batch {batch_start}: {e}")
            errors += len(new_chunks)

    return {
        "total": total,
        "loaded": loaded,
        "skipped": skipped,
        "errors": errors,
    }


# ── Verificación post-carga ─────────────────────────────────────────────────────


def verify_collection(client: QdrantClient, collection_name: str) -> None:
    """Hace una búsqueda de prueba para verificar que la colección funciona."""
    print(f"\nVerificando colección '{collection_name}'...")

    info = client.get_collection(collection_name)
    print(f"  Puntos indexados: {info.points_count}")
    status = getattr(info, "status", "ok")
    print(f"  Estado: {status}")

    # Búsqueda de prueba
    print("\n  Búsqueda de prueba: 'despido sin justa causa'")
    # Para la búsqueda necesitamos un vector de query — hardcodeamos None aquí
    # La verificación real se hace en validate_corpus.py
    print("  (La verificación de búsqueda se hace con validate_corpus.py)")


# ── CLI ─────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vectoriza chunks legales y los carga en Qdrant."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Genera embeddings pero no los carga en Qdrant"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Borra la colección existente y recarga todo"
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"Chunks por batch (default: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "--model", type=str, default=EMBEDDING_MODEL,
        help=f"Modelo de sentence-transformers (default: {EMBEDDING_MODEL})"
    )
    parser.add_argument(
        "--collection", type=str, default=COLLECTION_NAME,
        help=f"Nombre de la colección en Qdrant (default: {COLLECTION_NAME})"
    )
    parser.add_argument(
        "--local", action="store_true",
        help="Usar Qdrant en disco local en vez de Docker (no requiere Docker)"
    )
    args = parser.parse_args()

    # Cargar chunks
    chunks_path = PARSED_DIR / "chunks.json"
    if not chunks_path.exists():
        print(f"[ERROR] No se encontró {chunks_path}")
        print("  Ejecuta primero: python corpus/scripts/chunk_corpus.py")
        sys.exit(1)

    print(f"Cargando chunks desde {chunks_path}...")
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    print(f"  {len(chunks)} chunks cargados")

    # Cargar modelo de embeddings
    model = load_model(args.model)
    embedding_dim = model.get_sentence_embedding_dimension()

    if args.dry_run:
        print("\n[DRY RUN] Probando vectorización con los primeros 5 chunks...")
        sample = chunks[:5]
        texts = [c.get("text_for_embedding", "") for c in sample]
        vectors = embed_batch(model, texts)
        print(f"  Dimensión del vector: {len(vectors[0])}")
        print(f"  Rango de valores: [{min(min(v) for v in vectors):.4f}, {max(max(v) for v in vectors):.4f}]")
        for i, (chunk, vec) in enumerate(zip(sample, vectors)):
            print(f"  Chunk {i}: '{chunk.get('chunk_id')}' → norm={sum(x**2 for x in vec)**0.5:.4f}")
        print("\n[DRY RUN] Completado. Sin carga a Qdrant.")
        return

    # Conectar a Qdrant y configurar colección
    client = get_qdrant_client(local=args.local)
    setup_collection(client, args.collection, embedding_dim, reset=args.reset)

    # Cargar
    t_start = time.time()
    stats = load_to_qdrant(
        client=client,
        collection_name=args.collection,
        model=model,
        chunks=chunks,
        batch_size=args.batch_size,
    )
    elapsed = time.time() - t_start

    # Reporte final
    print(f"\n{'='*50}")
    print(f"CARGA COMPLETADA")
    print(f"{'='*50}")
    print(f"  Total chunks:  {stats['total']}")
    print(f"  Cargados:      {stats['loaded']}")
    print(f"  Omitidos:      {stats['skipped']} (ya existían)")
    print(f"  Errores:       {stats['errors']}")
    print(f"  Tiempo:        {elapsed:.1f}s")
    if stats['loaded'] > 0:
        print(f"  Velocidad:     {stats['loaded'] / elapsed:.1f} chunks/s")

    # Verificar
    if stats['errors'] == 0:
        verify_collection(client, args.collection)

    print("\nPróximo paso: python corpus/scripts/validate_corpus.py")


if __name__ == "__main__":
    main()
