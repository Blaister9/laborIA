"""
chat.py — POST /chat → Server-Sent Events (SSE)

Formato SSE de respuesta:
  data: {"type":"text","content":"Según el artículo..."}\n\n
  data: {"type":"sources","sources":[...]}\n\n
  data: {"type":"done"}\n\n

En caso de error:
  data: {"type":"error","content":"Mensaje de error"}\n\n
  data: {"type":"done"}\n\n
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent.models import ChatRequest
from app.agent.orchestrator import Orchestrator
from app.api.dependencies import get_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat")
async def chat(
    body: ChatRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> StreamingResponse:
    """
    Endpoint principal. Acepta una consulta y devuelve un stream SSE.

    Body JSON:
        {"query": "Me despidieron sin justa causa, cuánto me deben?"}

    Responde con Content-Type: text/event-stream
    """
    logger.info("Chat query: %r (top_k=%d)", body.query[:80], body.top_k)

    async def event_stream():
        try:
            async for chunk in orchestrator.run(
                query=body.query,
                top_k=body.top_k,
            ):
                yield chunk
        except Exception as exc:
            logger.exception("Error en event_stream")
            yield f'data: {{"type":"error","content":{str(exc)!r}}}\n\n'
            yield 'data: {"type":"done"}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Nginx: desactivar buffering
        },
    )
