"""
search_cst.py — Ejecutor de la herramienta search_cst.

Recibe el input de Claude (dict con query, topics, top_k),
llama al Retriever, y devuelve:
  - result_text: string JSON para Claude (tool_result content)
  - sources: lista de ArticleSource para enviar al cliente
"""

from __future__ import annotations

import json

from app.agent.models import ArticleSource
from app.rag.retriever import Retriever


def run_search_cst(
    tool_input: dict,
    retriever: Retriever,
) -> tuple[str, list[ArticleSource]]:
    """
    Ejecuta búsqueda y formatea el resultado para Claude.

    Returns:
        (result_json_str, sources_list)
        - result_json_str: contenido del tool_result que lee Claude
        - sources_list: ArticleSource[] que se envía al cliente vía SSE
    """
    query: str = tool_input.get("query", "")
    topics: list[str] | None = tool_input.get("topics") or None
    top_k: int = min(int(tool_input.get("top_k", 5)), 10)

    if not query:
        return json.dumps({"error": "query vacía"}), []

    hits = retriever.retrieve(query=query, top_k=top_k, topics=topics)

    # Construir lista estructurada para Claude
    articles_for_claude = []
    sources: list[ArticleSource] = []

    for hit in hits:
        article_number = str(hit.get("article_number", ""))
        article_title = hit.get("article_title", "")
        source_name = hit.get("source", "CST")
        text = hit.get("text", "")
        topics_hit = hit.get("topics", [])
        derogated = hit.get("derogated", False)
        modified_by = hit.get("modified_by", "") or ""
        effective_date = hit.get("effective_date", "") or ""
        chunk_type = hit.get("chunk_type", "article")

        # Nota de vigencia para que Claude la incluya en su respuesta
        vigencia_note = ""
        if derogated:
            vigencia_note = " [DEROGADO]"
        elif modified_by:
            vigencia_note = f" [Modificado: {modified_by}"
            if effective_date:
                vigencia_note += f", vigente desde {effective_date}"
            vigencia_note += "]"

        # Formato legible para Claude
        article_entry = {
            "articulo": f"Art. {article_number} {source_name}{vigencia_note}",
            "titulo": article_title,
            "tipo": chunk_type,
            "temas": topics_hit,
            "texto": text[:1500],  # Truncar para no saturar el contexto
        }
        if chunk_type == "group":
            article_entry["articulos_del_grupo"] = hit.get("articles_in_group", [])

        articles_for_claude.append(article_entry)

        # Source para el cliente SSE
        sources.append(
            ArticleSource(
                chunk_id=hit.get("chunk_id", ""),
                source=source_name,
                article_number=article_number,
                article_title=article_title,
                text=text,
                topics=topics_hit,
                book=hit.get("book", ""),
                chapter=hit.get("chapter", ""),
                rerank_score=float(hit.get("rerank_score", 0.0)),
                derogated=derogated,
                modified_by=modified_by,
                effective_date=effective_date,
            )
        )

    result = {
        "query": query,
        "total_encontrados": len(articles_for_claude),
        "articulos": articles_for_claude,
    }

    return json.dumps(result, ensure_ascii=False), sources
