"""
loader.py — Carga y cachea los prompts desde archivos .md editables.

Estructura esperada en el directorio de prompts:
  prompts/system_prompt.md      — Prompt principal (contiene {{ANALYSIS_TEMPLATE}})
  prompts/analysis_template.md  — Estructura de respuesta inyectada en el prompt
  prompts/tool_descriptions.md  — Descripciones de herramientas (## tool_name\\ndesc)

Uso:
  from app.agent.prompts.loader import init_prompt_store, get_prompt_store

  # En lifespan de main.py:
  store = init_prompt_store(Path("/prompts"))

  # En orchestrator.py:
  SYSTEM_PROMPT = get_prompt_store().system_prompt
  TOOLS = get_prompt_store().build_tools(TOOLS_BASE)
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Fallbacks (usados si los .md no existen o están vacíos) ───────────────────
_FALLBACK_SYSTEM = (
    "Eres LaborIA, asistente jurídico laboral colombiano. "
    "Responde en lenguaje técnico-jurídico, cita artículos formalmente."
)
_FALLBACK_TOOL_DESCS: dict[str, str] = {}


class PromptStore:
    """
    Caché thread-safe de los prompts del sistema.

    El método reload() lee los .md del disco y reconstruye el prompt
    final (system_prompt.md + analysis_template.md inyectada).
    Los tool_descriptions.md se parsean para sobreescribir las
    descripciones hardcodeadas de las herramientas en TOOLS.
    """

    def __init__(self, prompts_dir: Path) -> None:
        self._dir = prompts_dir
        self._lock = threading.Lock()
        self._system_prompt: str = _FALLBACK_SYSTEM
        self._tool_descriptions: dict[str, str] = dict(_FALLBACK_TOOL_DESCS)
        self._load_count: int = 0

    # ── API pública ───────────────────────────────────────────────────────────

    @property
    def system_prompt(self) -> str:
        with self._lock:
            return self._system_prompt

    def get_tool_description(self, tool_name: str) -> str | None:
        """Retorna la descripción del tool desde .md, o None si no existe."""
        with self._lock:
            return self._tool_descriptions.get(tool_name)

    def build_tools(self, base_tools: list[dict]) -> list[dict]:
        """
        Clona la lista base de tools e inyecta las descripciones del .md
        cuando existen. Si no hay override, conserva la descripción Python.
        """
        result = []
        for tool in base_tools:
            name = tool.get("name", "")
            override = self.get_tool_description(name)
            if override:
                tool = {**tool, "description": override}
            result.append(tool)
        return result

    def reload(self) -> dict[str, object]:
        """
        Re-lee todos los archivos .md y actualiza el caché.
        Thread-safe: las peticiones en vuelo ven el valor anterior
        hasta que la asignación con _lock se completa.

        Retorna un dict con estadísticas de la recarga para el endpoint /admin.
        """
        system_raw     = self._read("system_prompt.md")
        analysis_raw   = self._read("analysis_template.md")
        tools_raw      = self._read("tool_descriptions.md")

        # Inyectar analysis_template en system_prompt vía placeholder
        if analysis_raw and "{{ANALYSIS_TEMPLATE}}" in system_raw:
            system_final = system_raw.replace("{{ANALYSIS_TEMPLATE}}", analysis_raw)
        elif analysis_raw:
            # No hay placeholder: adjuntar al final
            system_final = system_raw + "\n\n" + analysis_raw
        else:
            system_final = system_raw

        if not system_final.strip():
            logger.warning("system_prompt.md vacío — usando fallback")
            system_final = _FALLBACK_SYSTEM

        tool_descs = _parse_tool_descriptions(tools_raw)

        # Escribir bajo lock para que sea atómico
        with self._lock:
            self._system_prompt = system_final
            self._tool_descriptions = tool_descs
            self._load_count += 1

        files_loaded = [
            f for f in ("system_prompt.md", "analysis_template.md", "tool_descriptions.md")
            if (self._dir / f).exists()
        ]
        logger.info(
            "PromptStore recargado (#%d) — prompt=%d chars, tools=%s, archivos=%s",
            self._load_count, len(system_final), list(tool_descs.keys()), files_loaded,
        )
        return {
            "load_count": self._load_count,
            "system_prompt_chars": len(system_final),
            "tools_overridden": list(tool_descs.keys()),
            "files_loaded": files_loaded,
        }

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _read(self, filename: str) -> str:
        path = self._dir / filename
        if not path.exists():
            logger.debug("Prompt file no encontrado: %s", path)
            return ""
        try:
            content = path.read_text(encoding="utf-8").strip()
            logger.debug("Leído %s (%d chars)", path, len(content))
            return content
        except Exception as exc:
            logger.error("Error leyendo %s: %s", path, exc)
            return ""


# ── Parser de tool_descriptions.md ────────────────────────────────────────────

def _parse_tool_descriptions(markdown: str) -> dict[str, str]:
    """
    Parsea secciones `## tool_name\\nDescripción...` del markdown.

    Ejemplo de entrada:
        ## search_cst
        Busca artículos relevantes...

        ## calculate_liquidation
        Calcula la liquidación...

    Retorna: {"search_cst": "Busca artículos...", "calculate_liquidation": "Calcula..."}
    """
    if not markdown:
        return {}

    result: dict[str, str] = {}
    # Dividir en secciones por encabezado ## (nivel 2 exactamente)
    sections = re.split(r"^## ", markdown, flags=re.MULTILINE)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n", 1)
        name = lines[0].strip()
        desc = lines[1].strip() if len(lines) > 1 else ""
        if name and desc:
            result[name] = desc

    return result


# ── Singleton global ──────────────────────────────────────────────────────────

_store: PromptStore | None = None


def init_prompt_store(prompts_dir: Path) -> PromptStore:
    """Inicializa el singleton. Llamar una sola vez en el lifespan de FastAPI."""
    global _store
    _store = PromptStore(prompts_dir)
    _store.reload()
    return _store


def get_prompt_store() -> PromptStore:
    """Retorna el singleton. Lanza RuntimeError si no fue inicializado."""
    if _store is None:
        raise RuntimeError(
            "PromptStore no inicializado. "
            "Llama init_prompt_store(path) en el lifespan de la app."
        )
    return _store
