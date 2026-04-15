"""
test_scenarios.py — Prueba 5 escenarios variados contra LaborIA.

Uso:
    python test_scenarios.py

Requiere: pip install httpx
Requiere: servidor corriendo en localhost:8080
"""

import asyncio
import json
import sys

try:
    import httpx
except ImportError:
    print("[ERROR] httpx no instalado. Ejecuta: pip install httpx")
    sys.exit(1)

BASE_URL = "http://localhost:8080"

SCENARIOS = [
    {
        "id": 1,
        "name": "Embarazo y despido (fuero de maternidad)",
        "query": "Estoy embarazada de 4 meses y mi jefe me dijo que no me va a renovar el contrato que se vence el mes que viene. ¿Pueden hacer eso?",
        "expected_articles": ["239", "240", "241"],
        "tests_tool": "search_cst",
    },
    {
        "id": 2,
        "name": "Acoso laboral",
        "query": "Mi jefe me grita frente a mis compañeros, me pone tareas imposibles de cumplir en poco tiempo y me amenaza con despedirme si no las termino. Esto lleva 6 meses pasando. ¿Qué puedo hacer?",
        "expected_articles": ["Ley 1010"],
        "tests_tool": "search_cst",
    },
    {
        "id": 3,
        "name": "Recargo dominical post-reforma",
        "query": "Trabajo todos los domingos en un restaurante. ¿Cuánto me deben pagar de recargo desde la reforma laboral de 2025?",
        "expected_articles": ["179", "180"],
        "tests_tool": "search_cst + reforma",
    },
    {
        "id": 4,
        "name": "Liquidación con datos concretos",
        "query": "Me renuncié voluntariamente después de 1 año y 7 meses. Mi salario era de 3.500.000 pesos mensuales con contrato a término indefinido. ¿Cuánto me deben pagar de liquidación?",
        "expected_articles": ["249", "306", "186"],
        "tests_tool": "calculate_liquidation",
    },
    {
        "id": 5,
        "name": "Prescripción de derechos",
        "query": "Me despidieron hace 2 años y 10 meses y nunca me pagaron la liquidación. ¿Todavía puedo reclamar o ya perdí el derecho?",
        "expected_articles": ["488", "489"],
        "tests_tool": "check_deadlines",
    },
]


async def run_scenario(client: httpx.AsyncClient, scenario: dict) -> dict:
    """Ejecuta un escenario y retorna el resultado."""
    result = {
        "id": scenario["id"],
        "name": scenario["name"],
        "query": scenario["query"],
        "expected_articles": scenario["expected_articles"],
        "tests_tool": scenario["tests_tool"],
        "response_text": "",
        "sources": [],
        "error": None,
    }

    try:
        full_text = []
        sources = []

        async with client.stream(
            "POST", "/chat", json={"query": scenario["query"], "top_k": 5}, timeout=120
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
                    continue

                if event.get("type") == "text":
                    full_text.append(event.get("content", ""))
                elif event.get("type") == "sources":
                    sources = event.get("sources", [])
                elif event.get("type") == "error":
                    result["error"] = event.get("content")

        result["response_text"] = "".join(full_text)
        result["sources"] = sources

    except Exception as e:
        result["error"] = str(e)

    return result


def print_result(r: dict) -> None:
    """Imprime un resultado de forma legible."""
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  ESCENARIO {r['id']}: {r['name']}")
    print(f"  Tool esperada: {r['tests_tool']}")
    print(sep)
    print(f"\n  PREGUNTA: {r['query']}\n")

    if r["error"]:
        print(f"  [ERROR] {r['error']}\n")
        return

    # Respuesta (primeros 1500 chars para no saturar)
    text = r["response_text"]
    if len(text) > 1500:
        text = text[:1500] + "\n\n  [...TRUNCADO — respuesta completa: " + str(len(r['response_text'])) + " chars...]"
    print(f"  RESPUESTA:\n{text}\n")

    # Fuentes
    print(f"  FUENTES ({len(r['sources'])} artículos):")
    for i, src in enumerate(r["sources"][:8], 1):
        art = src.get("article_number", "?")
        title = src.get("article_title", "")[:40]
        source = src.get("source", "CST")
        score = src.get("rerank_score", 0)
        print(f"    {i}. Art. {art} {source} — {title} (score={score:.3f})")

    # Check expected
    found_arts = [str(s.get("article_number", "")) for s in r["sources"]]
    expected = r["expected_articles"]
    hits = [e for e in expected if any(e in fa for fa in found_arts)]
    misses = [e for e in expected if not any(e in fa for fa in found_arts)]

    print(f"\n  ARTÍCULOS ESPERADOS: {expected}")
    print(f"  ENCONTRADOS:         {hits if hits else 'NINGUNO'}")
    if misses:
        print(f"  FALTANTES:           {misses}")
    print()


async def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         LaborIA — Test de 5 Escenarios Variados           ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # Health check
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        try:
            resp = await client.get("/health", timeout=10)
            data = resp.json()
            print(f"\n  Servidor OK — {data.get('qdrant_points')} chunks, modelo {data.get('model')}")
        except Exception as e:
            print(f"\n  [FATAL] Servidor no responde en {BASE_URL}: {e}")
            print("  Arráncalo con: cd backend && uvicorn app.main:app --reload --port 8080")
            sys.exit(1)

        results = []
        for scenario in SCENARIOS:
            print(f"\n  Ejecutando escenario {scenario['id']}/5: {scenario['name']}...")
            r = await run_scenario(client, scenario)
            results.append(r)
            print(f"  → {'OK' if not r['error'] else 'ERROR'} — {len(r['response_text'])} chars, {len(r['sources'])} fuentes")

    # Print all results
    for r in results:
        print_result(r)

    # Summary
    print("\n" + "=" * 70)
    print("  RESUMEN")
    print("=" * 70)
    total = len(results)
    errors = sum(1 for r in results if r["error"])
    with_sources = sum(1 for r in results if r["sources"])
    print(f"  Escenarios ejecutados: {total}")
    print(f"  Errores:               {errors}")
    print(f"  Con fuentes legales:   {with_sources}/{total}")
    print()


if __name__ == "__main__":
    asyncio.run(main())