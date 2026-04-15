"""
admin.py — Endpoints de administración (protegidos con ADMIN_TOKEN).

Rutas:
  POST /admin/reload-prompts  → Recarga los .md de prompts/ sin reiniciar el servidor
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.agent.prompts.loader import get_prompt_store
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _verify_token(authorization: str | None) -> None:
    """
    Verifica el Bearer token contra ADMIN_TOKEN.
    - Si ADMIN_TOKEN no está configurado → endpoint deshabilitado (403).
    - Si el token no coincide → 401 Unauthorized.
    """
    if not settings.admin_token:
        raise HTTPException(
            status_code=403,
            detail=(
                "Endpoint deshabilitado. "
                "Configura ADMIN_TOKEN en las variables de entorno para habilitarlo."
            ),
        )
    expected = f"Bearer {settings.admin_token}"
    if authorization != expected:
        raise HTTPException(
            status_code=401,
            detail="Token inválido. Usa el header: Authorization: Bearer <ADMIN_TOKEN>",
        )


@router.post("/reload-prompts")
async def reload_prompts(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    """
    Recarga los archivos .md de prompts/ y actualiza el caché en memoria.

    No requiere reiniciar el servidor — las siguientes peticiones al /chat
    usarán inmediatamente el prompt actualizado.

    Headers requeridos:
      Authorization: Bearer <ADMIN_TOKEN>

    Retorna estadísticas de la recarga:
    ```json
    {
      "status": "ok",
      "load_count": 3,
      "system_prompt_chars": 4200,
      "tools_overridden": ["search_cst", "calculate_liquidation", "check_deadlines"],
      "files_loaded": ["system_prompt.md", "analysis_template.md", "tool_descriptions.md"]
    }
    ```
    """
    _verify_token(authorization)

    try:
        store = get_prompt_store()
        stats = store.reload()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Error recargando prompts")
        raise HTTPException(status_code=500, detail=f"Error interno: {exc}")

    logger.info(
        "Prompts recargados via /admin/reload-prompts desde %s",
        request.client.host if request.client else "unknown",
    )
    return {"status": "ok", **stats}
