"""
validate_corpus.py — Valida la integridad y calidad del corpus en Qdrant.

Ejecuta 20 consultas de prueba contra los temas más comunes del derecho
laboral colombiano y verifica que los artículos correctos aparezcan en los
primeros resultados. También valida cobertura del CST.

Uso:
    python validate_corpus.py                    # Suite completa (20 queries)
    python validate_corpus.py --quick            # Solo 5 queries básicas
    python validate_corpus.py --query "texto"    # Query manual
    python validate_corpus.py --coverage         # Solo reporte de cobertura

Salida:
    Consola: resultados por query con artículos recuperados
    corpus/parsed/validation_report.json: reporte completo
"""

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

PARSED_DIR = Path(__file__).parent.parent / "parsed"

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("[ERROR] pip install sentence-transformers")
    sys.exit(1)

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue, ScoredPoint
except ImportError:
    print("[ERROR] pip install qdrant-client")
    sys.exit(1)

import os
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_CST", "cst_articles")
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
QDRANT_LOCAL_PATH = str(Path(__file__).parent.parent.parent / "qdrant_local")

# ── Suite de queries de validación ─────────────────────────────────────────────
#
# Cada query tiene:
#   - query: texto de la consulta en lenguaje natural
#   - expected_articles: artículos CST que DEBEN aparecer en top-5
#   - topic: tema para el reporte
#   - priority: "critical" | "high" | "medium"

VALIDATION_QUERIES = [
    # ── Terminación del contrato ────────────────────────────────────────────────
    {
        "query": "causales de terminación del contrato de trabajo con justa causa por parte del empleador",
        "expected_articles": ["62", "63"],
        "topic": "terminación_contrato",
        "priority": "critical",
    },
    {
        "query": "indemnización por despido sin justa causa contrato indefinido",
        "expected_articles": ["64"],
        "topic": "terminación_contrato",
        "priority": "critical",
    },
    {
        "query": "preaviso para terminar contrato de trabajo",
        "expected_articles": ["64", "47"],
        "topic": "terminación_contrato",
        "priority": "high",
    },

    # ── Salario ─────────────────────────────────────────────────────────────────
    {
        "query": "qué constituye salario en Colombia elementos integrantes",
        "expected_articles": ["127"],
        "topic": "salario",
        "priority": "critical",
    },
    {
        "query": "pagos que no constituyen salario bonificaciones ocasionales",
        "expected_articles": ["128"],
        "topic": "salario",
        "priority": "critical",
    },
    {
        "query": "salario mínimo remuneración mínima legal vigente",
        "expected_articles": ["145", "146"],
        "topic": "salario",
        "priority": "high",
    },

    # ── Jornada y horas extras ──────────────────────────────────────────────────
    {
        "query": "jornada máxima legal de trabajo en Colombia horas semanales",
        "expected_articles": ["161"],
        "topic": "jornada",
        "priority": "critical",
    },
    {
        "query": "recargo por trabajo en horas extras nocturnas porcentaje",
        "expected_articles": ["168"],
        "topic": "jornada",
        "priority": "critical",
    },

    # ── Dominical y festivos ────────────────────────────────────────────────────
    {
        "query": "recargo por trabajo dominical y festivo porcentaje Colombia",
        "expected_articles": ["179", "180"],
        "topic": "dominical",
        "priority": "critical",
    },
    {
        "query": "trabajo el domingo sin pagar recargo obligaciones del empleador",
        "expected_articles": ["179"],
        "topic": "dominical",
        "priority": "critical",
    },

    # ── Vacaciones ──────────────────────────────────────────────────────────────
    {
        "query": "días de vacaciones a cuántos días tengo derecho por año trabajado",
        "expected_articles": ["186"],
        "topic": "vacaciones",
        "priority": "critical",
    },
    {
        "query": "compensación en dinero de vacaciones cuándo se puede pagar",
        "expected_articles": ["189"],
        "topic": "vacaciones",
        "priority": "high",
    },

    # ── Maternidad ──────────────────────────────────────────────────────────────
    {
        "query": "licencia de maternidad duración cuántas semanas Colombia",
        "expected_articles": ["236"],
        "topic": "maternidad",
        "priority": "critical",
    },
    {
        "query": "fuero de maternidad protección embarazo despido mujer embarazada",
        "expected_articles": ["239"],
        "topic": "maternidad",
        "priority": "critical",
    },

    # ── Cesantías ───────────────────────────────────────────────────────────────
    {
        "query": "liquidación de cesantías cómo se calcula auxilio cesantía",
        "expected_articles": ["249"],
        "topic": "cesantías",
        "priority": "critical",
    },
    {
        "query": "intereses sobre cesantías 12% porcentaje anual",
        "expected_articles": ["99"],  # Ley 50/1990 — puede no estar en CST base
        "topic": "cesantías",
        "priority": "high",
    },

    # ── Prima de servicios ──────────────────────────────────────────────────────
    {
        "query": "prima de servicios cuándo se paga y cómo se liquida",
        "expected_articles": ["306"],
        "topic": "prima_servicios",
        "priority": "critical",
    },

    # ── Prescripción ───────────────────────────────────────────────────────────
    {
        "query": "prescripción de acciones laborales en cuánto tiempo prescriben",
        "expected_articles": ["488"],
        "topic": "prescripción",
        "priority": "critical",
    },

    # ── Acoso laboral ───────────────────────────────────────────────────────────
    {
        "query": "acoso laboral definición modalidades cómo denunciar",
        "expected_articles": [],  # Ley 1010/2006 — no en CST base
        "topic": "acoso_laboral",
        "priority": "medium",
    },

    # ── Periodo de prueba ───────────────────────────────────────────────────────
    {
        "query": "periodo de prueba duración máxima cuántos días",
        "expected_articles": ["76", "78"],
        "topic": "periodo_prueba",
        "priority": "high",
    },
]

# Solo 5 queries para el modo --quick
QUICK_QUERIES = [q for q in VALIDATION_QUERIES if q["priority"] == "critical"][:5]


# ── Modelos de resultado ────────────────────────────────────────────────────────


@dataclass
class QueryResult:
    query: str = ""
    topic: str = ""
    priority: str = ""
    expected_articles: list = field(default_factory=list)
    retrieved_articles: list = field(default_factory=list)
    retrieved_texts: list = field(default_factory=list)
    hit: bool = False                   # ¿Apareció al menos 1 artículo esperado en top-5?
    latency_ms: float = 0.0
    top_score: float = 0.0


@dataclass
class ValidationReport:
    collection: str = ""
    model: str = ""
    total_queries: int = 0
    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    avg_latency_ms: float = 0.0
    critical_hit_rate: float = 0.0
    results: list = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


# ── Búsqueda ────────────────────────────────────────────────────────────────────


def search(
    client: QdrantClient,
    model: SentenceTransformer,
    query_text: str,
    collection: str,
    top_k: int = 5,
    filter_source: Optional[str] = None,
) -> list[dict]:
    """Busca chunks similares a la query y retorna los resultados."""
    vector = model.encode(query_text, normalize_embeddings=True).tolist()

    qdrant_filter = None
    if filter_source:
        qdrant_filter = Filter(
            must=[FieldCondition(key="source", match=MatchValue(value=filter_source))]
        )

    # qdrant-client >= 1.7: usar query_points en lugar de search
    response = client.query_points(
        collection_name=collection,
        query=vector,
        limit=top_k,
        query_filter=qdrant_filter,
        with_payload=True,
    )
    results = response.points

    return [
        {
            "article_number": r.payload.get("article_number", "") if r.payload else "",
            "source": r.payload.get("source", "") if r.payload else "",
            "article_title": r.payload.get("article_title", "") if r.payload else "",
            "text_preview": (r.payload.get("text", "") if r.payload else "")[:150],
            "score": r.score,
            "chunk_type": r.payload.get("chunk_type", "article") if r.payload else "",
            "topics": r.payload.get("topics", []) if r.payload else [],
        }
        for r in results
    ]


# ── Validación de cobertura ─────────────────────────────────────────────────────


def check_coverage(client: QdrantClient, collection: str) -> dict:
    """Verifica qué artículos del CST están en el corpus."""
    # Artículos críticos que deben estar presentes
    critical_articles = [
        "61", "62", "63", "64", "65", "66",   # Terminación
        "127", "128", "129", "130",             # Salario
        "158", "161", "162", "168",             # Jornada
        "172", "179", "180",                    # Dominical
        "186", "187", "188", "189",             # Vacaciones
        "236", "237", "239",                    # Maternidad
        "249", "250",                           # Cesantías
        "306",                                  # Prima
        "488", "489",                           # Prescripción
        "76", "78",                             # Periodo de prueba
    ]

    results = {}
    for art_num in critical_articles:
        scroll = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="article_number", match=MatchValue(value=art_num)),
                    FieldCondition(key="source", match=MatchValue(value="CST")),
                ]
            ),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        results[art_num] = len(scroll[0]) > 0

    present = sum(1 for v in results.values() if v)
    return {
        "critical_articles_checked": len(critical_articles),
        "critical_articles_present": present,
        "coverage_pct": round(present / len(critical_articles) * 100, 1),
        "missing": [a for a, present in results.items() if not present],
    }


# ── CLI ─────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Valida la calidad del corpus de LaborIA en Qdrant."
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Solo ejecutar 5 queries críticas"
    )
    parser.add_argument(
        "--query", type=str,
        help="Ejecutar una query manual y mostrar top-5 resultados"
    )
    parser.add_argument(
        "--coverage", action="store_true",
        help="Solo mostrar reporte de cobertura del CST"
    )
    parser.add_argument(
        "--top-k", type=int, default=5,
        help="Número de resultados a recuperar por query (default: 5)"
    )
    args = parser.parse_args()

    # Conectar — intentar Docker primero, fallback a local
    print(f"Conectando a Qdrant...")
    client = None
    try:
        c = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=5)
        c.get_collections()
        client = c
        print(f"  Conectado (Docker) en {QDRANT_HOST}:{QDRANT_PORT}")
    except Exception:
        print(f"  Docker no disponible, usando modo local: {QDRANT_LOCAL_PATH}")
        client = QdrantClient(path=QDRANT_LOCAL_PATH)

    try:
        info = client.get_collection(COLLECTION_NAME)
        print(f"  Coleccion: {COLLECTION_NAME}")
        print(f"  Puntos: {info.points_count}")
    except Exception as e:
        print(f"[ERROR] No se puede acceder a la coleccion '{COLLECTION_NAME}': {e}")
        sys.exit(1)

    print(f"\nCargando modelo: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    # Modo: query manual
    if args.query:
        print(f"\nQuery: '{args.query}'")
        print(f"{'─'*60}")
        results = search(client, model, args.query, COLLECTION_NAME, top_k=args.top_k)
        for i, r in enumerate(results, 1):
            print(f"  {i}. Art. {r['article_number']} ({r['source']}) — score: {r['score']:.4f}")
            if r['article_title']:
                print(f"     Título: {r['article_title']}")
            print(f"     Topics: {r['topics']}")
            print(f"     Texto: {r['text_preview']}...")
        return

    # Modo: solo cobertura
    if args.coverage:
        print("\nVerificando cobertura del CST...")
        coverage = check_coverage(client, COLLECTION_NAME)
        print(f"  Artículos críticos verificados: {coverage['critical_articles_checked']}")
        print(f"  Presentes en corpus:            {coverage['critical_articles_present']}")
        print(f"  Cobertura:                      {coverage['coverage_pct']}%")
        if coverage['missing']:
            print(f"  Faltantes: {coverage['missing']}")
        return

    # Modo: suite de validación
    queries = QUICK_QUERIES if args.quick else VALIDATION_QUERIES
    print(f"\n{'='*70}")
    print(f"SUITE DE VALIDACIÓN — {len(queries)} queries")
    print(f"{'='*70}")

    report = ValidationReport(
        collection=COLLECTION_NAME,
        model=EMBEDDING_MODEL,
        total_queries=len(queries),
    )

    query_results = []

    for q in queries:
        query_text = q["query"]
        expected = q["expected_articles"]
        priority = q["priority"]

        t_start = time.time()
        retrieved = search(client, model, query_text, COLLECTION_NAME, top_k=args.top_k)
        latency = (time.time() - t_start) * 1000

        retrieved_nums = [r["article_number"] for r in retrieved]
        hit = any(exp in retrieved_nums for exp in expected) if expected else True

        result = QueryResult(
            query=query_text,
            topic=q["topic"],
            priority=priority,
            expected_articles=expected,
            retrieved_articles=retrieved_nums,
            retrieved_texts=[r["text_preview"] for r in retrieved],
            hit=hit,
            latency_ms=round(latency, 1),
            top_score=retrieved[0]["score"] if retrieved else 0.0,
        )
        query_results.append(result)

        # Mostrar resultado en consola
        status = "OK" if hit else "MISS"
        marker = "" if hit else " ←── REVISAR"
        print(f"\n[{status}] ({priority}) {q['topic']}{marker}")
        print(f"  Query: {query_text[:80]}...")
        if expected:
            print(f"  Esperados: {expected}")
        print(f"  Top-5:     {retrieved_nums} | latencia: {latency:.0f}ms | score: {result.top_score:.4f}")
        if not hit and expected:
            print(f"  Top resultado: Art. {retrieved[0]['article_number']} — {retrieved[0]['text_preview'][:100]}")

    # Resumen
    hits = sum(1 for r in query_results if r.hit)
    critical_queries = [r for r in query_results if r.priority == "critical"]
    critical_hits = sum(1 for r in critical_queries if r.hit)
    avg_latency = sum(r.latency_ms for r in query_results) / len(query_results)

    print(f"\n{'='*70}")
    print(f"RESUMEN DE VALIDACIÓN")
    print(f"{'='*70}")
    print(f"  Hit rate total:     {hits}/{len(query_results)} ({hits/len(query_results)*100:.0f}%)")
    if critical_queries:
        print(f"  Hit rate críticos:  {critical_hits}/{len(critical_queries)} ({critical_hits/len(critical_queries)*100:.0f}%)")
    print(f"  Latencia promedio:  {avg_latency:.0f}ms")

    # Objetivo de la Fase 1: >85% hit rate
    target = 0.85
    hit_rate = hits / len(query_results)
    if hit_rate >= target:
        print(f"\n  OBJETIVO FASE 1 (>85%): CUMPLIDO ({hit_rate*100:.0f}%)")
    else:
        print(f"\n  OBJETIVO FASE 1 (>85%): NO CUMPLIDO ({hit_rate*100:.0f}%)")
        print(f"  Queries fallidas:")
        for r in query_results:
            if not r.hit:
                print(f"    - [{r.priority}] {r.topic}: esperado {r.expected_articles}, obtenido {r.retrieved_articles[:3]}")

    # Cobertura
    coverage = check_coverage(client, COLLECTION_NAME)
    print(f"\n  Cobertura artículos críticos: {coverage['coverage_pct']}%")
    if coverage['missing']:
        print(f"  Artículos faltantes: {coverage['missing']}")

    # Guardar reporte
    report.hits = hits
    report.misses = len(query_results) - hits
    report.hit_rate = round(hit_rate, 4)
    report.avg_latency_ms = round(avg_latency, 1)
    report.critical_hit_rate = round(
        critical_hits / len(critical_queries) if critical_queries else 0, 4
    )
    report.results = [asdict(r) for r in query_results]
    report.coverage = coverage

    report_path = PARSED_DIR / "validation_report.json"
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  Reporte guardado: {report_path}")


if __name__ == "__main__":
    main()
