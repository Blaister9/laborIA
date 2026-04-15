"""
orchestrator.py — Loop de tool use + síntesis streaming.

Flujo:
  1. Llamada no-streaming a Claude con las 3 tools disponibles.
  2. Si Claude solicita tools → ejecutar, agregar tool_result, repetir (max 5 iteraciones).
  3. Cuando stop_reason != "tool_use" → llamada final STREAMING para síntesis.
  4. Emite eventos SSE: text | sources | error | done.

Tools disponibles para Claude:
  - search_cst           → recupera artículos del corpus RAG
  - calculate_liquidation → calculadora de liquidación laboral
  - check_deadlines       → verificador de plazos de prescripción
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from app.agent.models import ArticleSource, ChatEvent
from app.agent.prompts.loader import get_prompt_store
from app.agent.prompts.tool_descriptions import TOOLS
from app.agent.tools.calculate_liquidation import run_calculate_liquidation
from app.agent.tools.check_deadlines import run_check_deadlines
from app.agent.tools.search_cst import run_search_cst
from app.llm.claude_client import ClaudeClient
from app.rag.retriever import Retriever

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5   # search + calculate + deadlines + posibles re-búsquedas


class Orchestrator:
    def __init__(self, retriever: Retriever, claude: ClaudeClient) -> None:
        self.retriever = retriever
        self.claude = claude

    async def run(
        self, query: str, top_k: int = 5
    ) -> AsyncGenerator[str, None]:
        """
        Generador asíncrono que produce líneas SSE.
        Formato: `data: <json>\\n\\n`
        """
        messages: list[dict] = [{"role": "user", "content": query}]
        all_sources: list[ArticleSource] = []
        tools_were_called = False

        # ── Fase 1: loop de tool use (no-streaming) ───────────────────────────
        # Obtener prompt y tools del store en cada request — así los cambios
        # de /admin/reload-prompts se aplican sin reiniciar el servidor.
        store = get_prompt_store()
        system_prompt = store.system_prompt
        tools = store.build_tools(TOOLS)

        for iteration in range(MAX_TOOL_ITERATIONS):
            try:
                response = await self.claude.create(
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                )
            except Exception as exc:
                logger.exception("Error llamando a Claude (iter %d)", iteration)
                yield _sse(ChatEvent(type="error", content=str(exc)))
                return

            stop_reason = response.stop_reason

            if stop_reason != "tool_use":
                # Claude no pide más tools — salir del loop
                break

            tools_were_called = True

            # Registrar turno del asistente con los bloques de tool_use
            messages.append(
                {"role": "assistant", "content": _blocks_to_dict(response.content)}
            )

            # Ejecutar cada tool solicitada
            tool_results: list[dict] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                result_str, block_sources = self._dispatch(block.name, block.input)
                all_sources.extend(block_sources)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })
                logger.info(
                    "Tool '%s' ejecutada — resultado: %d chars",
                    block.name, len(result_str),
                )

            messages.append({"role": "user", "content": tool_results})
            # continuar loop para que Claude procese los resultados

        # ── Fase 2: respuesta final streaming ────────────────────────────────
        # IMPORTANTE: siempre pasar TOOLS aunque no se llamen más tools.
        # La API de Anthropic requiere que `tools` esté presente en cualquier
        # request cuyo historial contenga bloques `tool_result`. Sin el schema,
        # Claude no puede procesar el contexto y devuelve texto vacío.
        try:
            async with self.claude.stream(
                system=system_prompt,
                messages=messages,
                tools=tools,
            ) as stream:
                async for text_chunk in stream.text_stream:
                    yield _sse(ChatEvent(type="text", content=text_chunk))
        except Exception as exc:
            logger.exception("Error en streaming final")
            yield _sse(ChatEvent(type="error", content=str(exc)))
            return

        # ── Fase 3: fuentes ───────────────────────────────────────────────────
        if all_sources:
            # Deduplicar por source + article_number, mantener mayor score
            seen: dict[str, ArticleSource] = {}
            for src in all_sources:
                key = f"{src.source}_{src.article_number}"
                if key not in seen or src.rerank_score > seen[key].rerank_score:
                    seen[key] = src
            unique = sorted(seen.values(), key=lambda s: s.rerank_score, reverse=True)
            yield _sse(ChatEvent(type="sources", sources=unique))

        yield _sse(ChatEvent(type="done"))

    # ── Dispatcher de tools ───────────────────────────────────────────────────

    def _dispatch(
        self, tool_name: str, tool_input: dict
    ) -> tuple[str, list[ArticleSource]]:
        """
        Enruta la llamada de Claude a la implementación correcta.
        Retorna (result_json_str, sources_para_cliente).
        """
        if tool_name == "search_cst":
            result_str, sources = run_search_cst(
                tool_input=tool_input,
                retriever=self.retriever,
            )
            return result_str, sources

        if tool_name == "calculate_liquidation":
            result_str = run_calculate_liquidation(tool_input)
            # Enriquecer fuentes automáticamente con los artículos base de liquidación.
            # Esto asegura que el cliente siempre vea la base legal del cálculo,
            # sin requerir que Claude haga una segunda llamada a search_cst.
            # Fetch artículos fundamentales de liquidación con queries específicas
            # para garantizar que los 5 pilares legales aparezcan en las fuentes.
            legal_sources = _fetch_liquidation_legal_sources(self.retriever)
            return result_str, legal_sources

        if tool_name == "check_deadlines":
            return run_check_deadlines(tool_input), []

        # Tool desconocida (no debería ocurrir con el schema correcto)
        logger.warning("Tool desconocida: %s", tool_name)
        return json.dumps({"error": f"Herramienta desconocida: {tool_name}"}), []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_liquidation_legal_sources(retriever) -> list[ArticleSource]:
    """
    Recupera los artículos fundamentales que respaldan todo cálculo de liquidación
    directamente desde el índice BM25 en memoria del retriever (por chunk_id).

    Esto garantiza que Art. 64, 249, 306 y 186 aparezcan siempre en las fuentes,
    independientemente del ranking semántico.
    """
    TARGET_IDS = [
        "cst_group_cesantias_249_258",  # grupo cesantías + intereses (Art. 249-258)
        "cst_art_249_article",          # fallback artículo individual
        "cst_art_64_article",           # indemnización por despido sin justa causa
        "cst_art_306_article",          # prima de servicios
        "cst_art_186_article",          # vacaciones
    ]

    sources: list[ArticleSource] = []
    seen_arts: set[str] = set()

    for chunk_id in TARGET_IDS:
        chunk = retriever._chunk_by_id.get(chunk_id)
        if not chunk:
            continue
        art_num = str(chunk.get("article_number", ""))
        if art_num in seen_arts:
            continue
        seen_arts.add(art_num)
        sources.append(
            ArticleSource(
                chunk_id=chunk_id,
                source=chunk.get("source", "CST"),
                article_number=art_num,
                article_title=chunk.get("article_title", ""),
                text=chunk.get("text", ""),
                topics=chunk.get("topics", []),
                book=chunk.get("book", ""),
                chapter=chunk.get("chapter", ""),
                rerank_score=1.0,
                derogated=bool(chunk.get("derogated", False)),
                modified_by=chunk.get("modified_by", "") or "",
                effective_date=chunk.get("effective_date", "") or "",
            )
        )

    return sources


def _sse(event: ChatEvent) -> str:
    """Serializa un ChatEvent al formato SSE."""
    return f"data: {event.model_dump_json(exclude_none=True)}\n\n"


def _blocks_to_dict(content_blocks) -> list[dict]:
    """Convierte bloques de Anthropic a dicts serializables para el historial."""
    result = []
    for block in content_blocks:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return result
