"""
test_chat.py — Prueba end-to-end del endpoint POST /chat.

Uso:
    # Con el servidor corriendo en otra terminal:
    python test_chat.py
    python test_chat.py --query "¿Cuánto es el recargo dominical desde la reforma?"
    python test_chat.py --url http://localhost:8000 --verbose

El servidor se inicia con:
    cd backend
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

try:
    import httpx
except ImportError:
    print("[ERROR] httpx no instalado. Ejecuta: pip install httpx")
    sys.exit(1)

BASE_URL = "http://localhost:8080"

DEMO_QUERY = (
    "Me despidieron sin justa causa después de 3 años trabajando. "
    "Mi salario era de 2.000.000 de pesos. ¿Cuánto me deben de liquidación?"
)


async def test_health(client: httpx.AsyncClient) -> bool:
    print("\n── GET /health ─────────────────────────────────────────────")
    try:
        resp = await client.get("/health", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        print(f"  status:        {data.get('status')}")
        print(f"  qdrant_points: {data.get('qdrant_points')}")
        print(f"  model:         {data.get('model')}")
        print(f"  embedding_dim: {data.get('embedding_dim')}")
        return True
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


async def test_chat(
    client: httpx.AsyncClient,
    query: str,
    top_k: int = 5,
    verbose: bool = False,
) -> None:
    print(f"\n── POST /chat ──────────────────────────────────────────────")
    print(f"  query: {query[:80]}...")
    print()

    payload = {"query": query, "top_k": top_k}
    full_text = []
    sources = []

    async with client.stream(
        "POST",
        "/chat",
        json=payload,
        timeout=120,
    ) as resp:
        resp.raise_for_status()

        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue

            raw = line[len("data:"):].strip()
            if not raw:
                continue

            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                if verbose:
                    print(f"  [WARN] línea no parseable: {raw[:80]}")
                continue

            event_type = event.get("type")

            if event_type == "text":
                chunk = event.get("content", "")
                full_text.append(chunk)
                print(chunk, end="", flush=True)

            elif event_type == "sources":
                sources = event.get("sources", [])
                if verbose:
                    print(f"\n\n  [sources raw] {len(sources)} artículos")

            elif event_type == "error":
                print(f"\n\n  [ERROR] {event.get('content')}")

            elif event_type == "done":
                pass

    # ── Resumen ──────────────────────────────────────────────────────────────
    print("\n")
    print("── Fuentes recuperadas ─────────────────────────────────────")
    if sources:
        for i, src in enumerate(sources, 1):
            score = src.get("rerank_score", 0)
            art = src.get("article_number", "?")
            title = src.get("article_title", "")[:50]
            source_name = src.get("source", "CST")
            derogated = " [DEROGADO]" if src.get("derogated") else ""
            print(f"  {i}. Art. {art} {source_name} — {title}{derogated}  (score={score:.3f})")
    else:
        print("  (sin fuentes)")

    print(f"\n── Stats ────────────────────────────────────────────────────")
    print(f"  Texto total: {sum(len(t) for t in full_text)} caracteres")
    print(f"  Fuentes:     {len(sources)} artículos")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test del endpoint /chat de LaborIA")
    parser.add_argument("--url", default=BASE_URL, help="URL base del servidor")
    parser.add_argument("--query", default=DEMO_QUERY, help="Consulta a enviar")
    parser.add_argument("--top-k", type=int, default=5, help="Artículos a recuperar")
    parser.add_argument("--verbose", action="store_true", help="Mostrar eventos SSE en crudo")
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.url) as client:
        health_ok = await test_health(client)
        if not health_ok:
            print("\n[FATAL] El servidor no responde. Arráncalo con:")
            print("  cd backend && uvicorn app.main:app --reload --port 8000")
            sys.exit(1)

        await test_chat(
            client=client,
            query=args.query,
            top_k=args.top_k,
            verbose=args.verbose,
        )


if __name__ == "__main__":
    asyncio.run(main())
