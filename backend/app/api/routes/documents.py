"""
documents.py — POST /analyze-document

Acepta un PDF (multipart), extrae su texto, y lo pasa al orquestador
con el contexto del documento inyectado en el mensaje del usuario.
Devuelve SSE stream idéntico al endpoint /chat.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.agent.orchestrator import Orchestrator
from app.agent.tools.analyze_document import (
    build_document_prompt,
    classify_document,
    extract_pdf_text,
)
from app.api.dependencies import get_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_TYPES = {"application/pdf", "application/x-pdf"}


@router.post("/analyze-document")
async def analyze_document(
    file: UploadFile = File(..., description="PDF del documento laboral"),
    question: str = Form(
        default="Analiza este documento e identifica sus implicaciones legales laborales.",
        description="Pregunta o instrucción específica sobre el documento.",
    ),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> StreamingResponse:
    """
    Analiza un documento laboral (PDF) con el agente LaborIA.

    - Acepta: `multipart/form-data` con campo `file` (PDF) y `question` (str).
    - Devuelve: `text/event-stream` con los mismos eventos SSE que `/chat`.

    Eventos SSE:
      data: {"type":"text","content":"..."}\\n\\n
      data: {"type":"sources","sources":[...]}\\n\\n
      data: {"type":"done"}\\n\\n
    """
    # ── Validaciones ──────────────────────────────────────────────────────────
    if file.content_type not in ALLOWED_TYPES and not (
        (file.filename or "").lower().endswith(".pdf")
    ):
        raise HTTPException(
            status_code=415,
            detail="Solo se aceptan archivos PDF.",
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo supera el límite de {MAX_FILE_SIZE // (1024*1024)} MB.",
        )

    if not file_bytes:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    # ── Extracción y clasificación ────────────────────────────────────────────
    try:
        texto, num_paginas = extract_pdf_text(file_bytes)
    except Exception as exc:
        logger.exception("Error extrayendo PDF: %s", file.filename)
        raise HTTPException(
            status_code=422,
            detail=f"No se pudo extraer texto del PDF: {exc}",
        )

    doc_info = classify_document(texto)
    doc_info.paginas = num_paginas

    logger.info(
        "Documento: %s | tipo=%s | páginas=%d | chars=%d",
        file.filename, doc_info.tipo, num_paginas, len(texto),
    )

    # ── Construir prompt enriquecido ──────────────────────────────────────────
    enriched_query = build_document_prompt(
        info=doc_info,
        question=question,
        filename=file.filename or "documento.pdf",
    )

    # ── Stream del orquestador ────────────────────────────────────────────────
    async def event_stream():
        try:
            async for chunk in orchestrator.run(query=enriched_query, top_k=5):
                yield chunk
        except Exception as exc:
            logger.exception("Error en análisis de documento")
            yield f'data: {{"type":"error","content":{str(exc)!r}}}\n\n'
            yield 'data: {"type":"done"}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
