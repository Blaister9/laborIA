"""
analyze_document.py — Extracción y clasificación de documentos laborales (PDF).

Flujo de uso:
  1. El endpoint POST /analyze-document recibe el PDF (UploadFile).
  2. extract_pdf_text() extrae el texto plano.
  3. classify_document() detecta el tipo (contrato, carta de despido, etc.)
     y extrae campos clave (fechas, salario, partes).
  4. El orquestador recibe el texto enriquecido y lo incluye en el contexto
     de Claude, que luego llama a search_cst para el análisis jurídico.

Dependencia: pypdf (pip install pypdf)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO


# ── Tipos de documento soportados ────────────────────────────────────────────

DOCUMENT_TYPES = {
    "contrato_trabajo": [
        r"contrato\s+de\s+trabajo",
        r"contrato\s+individual",
        r"contrato\s+laboral",
        r"vinculación\s+laboral",
    ],
    "carta_despido": [
        r"termina(?:ción|mos)\s+(?:del?\s+)?contrato",
        r"desvincula(?:ción|mos)",
        r"justa\s+causa",
        r"carta\s+de\s+despido",
        r"termina(?:ción|mos)\s+(?:del?\s+)?vínculo",
    ],
    "liquidacion_final": [
        r"liquidación\s+(?:final|de\s+contrato|laboral)",
        r"acta\s+de\s+liquidación",
        r"paz\s+y\s+salvo\s+laboral",
    ],
    "prorroga_contrato": [
        r"prórroga\s+(?:del?\s+)?contrato",
        r"renovación\s+(?:del?\s+)?contrato",
        r"ampliación\s+(?:del?\s+)?contrato",
    ],
    "acta_descargos": [
        r"acta\s+de\s+descargos",
        r"diligencia\s+de\s+descargos",
        r"versión\s+libre",
    ],
    "reglamento_interno": [
        r"reglamento\s+interno\s+de\s+trabajo",
        r"reglamento\s+laboral",
    ],
    "certificado_laboral": [
        r"certificado\s+(?:de\s+)?(?:trabajo|laboral|ingresos)",
        r"constancia\s+(?:de\s+)?(?:trabajo|laboral)",
    ],
}


@dataclass
class DocumentInfo:
    tipo: str                              # tipo detectado
    texto_extraido: str                    # texto completo
    paginas: int
    campos_detectados: dict[str, str]      # salario, fechas, partes, etc.
    advertencias: list[str] = field(default_factory=list)
    confianza_tipo: str = "alta"           # "alta" | "media" | "baja"


# ── Extracción de texto desde PDF ─────────────────────────────────────────────

def extract_pdf_text(file_bytes: bytes) -> tuple[str, int]:
    """
    Extrae texto de un PDF.

    Returns:
        (texto_plano, numero_paginas)
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError(
            "pypdf no instalado. Ejecuta: pip install pypdf"
        )

    reader = PdfReader(BytesIO(file_bytes))
    paginas = len(reader.pages)
    partes: list[str] = []

    for i, page in enumerate(reader.pages):
        texto = page.extract_text() or ""
        if texto.strip():
            partes.append(f"[Página {i + 1}]\n{texto}")

    texto_completo = "\n\n".join(partes)

    # Limpiar espacios excesivos y caracteres de control
    texto_completo = re.sub(r"\r\n|\r", "\n", texto_completo)
    texto_completo = re.sub(r"\n{4,}", "\n\n\n", texto_completo)
    texto_completo = re.sub(r"[ \t]{3,}", "  ", texto_completo)

    return texto_completo.strip(), paginas


# ── Clasificación y extracción de campos ──────────────────────────────────────

def classify_document(texto: str) -> DocumentInfo:
    """
    Detecta el tipo de documento y extrae campos clave.
    """
    texto_lower = texto.lower()

    # ── Detectar tipo ─────────────────────────────────────────────────────────
    tipo_detectado = "documento_laboral_generico"
    confianza = "baja"
    max_matches = 0

    for tipo, patrones in DOCUMENT_TYPES.items():
        matches = sum(
            1 for p in patrones if re.search(p, texto_lower)
        )
        if matches > max_matches:
            max_matches = matches
            tipo_detectado = tipo
            confianza = "alta" if matches >= 2 else "media"

    # ── Extraer campos clave ──────────────────────────────────────────────────
    campos: dict[str, str] = {}

    # Salario
    m = re.search(
        r"salario[^\d$]*?\$?\s*([\d.,]+(?:\.\d{3})*(?:,\d+)?)",
        texto_lower,
    )
    if m:
        campos["salario_detectado"] = m.group(1).strip()

    # Fechas (DD/MM/YYYY o YYYY-MM-DD)
    fechas = re.findall(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", texto)
    if fechas:
        campos["fechas_detectadas"] = ", ".join(dict.fromkeys(fechas[:5]))  # max 5 únicas

    # NIT / Cédula
    m_nit = re.search(r"\b(?:nit|c\.c\.|c\.c|cédula)[.:\s]+(\d[\d.-]+)", texto_lower)
    if m_nit:
        campos["identificacion_detectada"] = m_nit.group(1).strip()

    # Cargo / posición
    m_cargo = re.search(
        r"(?:cargo|posición|puesto)[:\s]+([A-ZÁÉÍÓÚÑa-záéíóúñ ]{3,40})",
        texto,
    )
    if m_cargo:
        campos["cargo_detectado"] = m_cargo.group(1).strip()

    # Tipo de contrato
    for tc in ("término fijo", "término indefinido", "obra o labor", "prestación de servicios"):
        if tc in texto_lower:
            campos["tipo_contrato_detectado"] = tc
            break

    # Justa causa (para cartas de despido)
    if tipo_detectado == "carta_despido":
        causas = re.findall(r"numeral\s+\d+|literal\s+[a-zA-Z]|art(?:ículo)?\s*\d+", texto_lower)
        if causas:
            campos["causales_citadas"] = "; ".join(dict.fromkeys(causas[:5]))

    advertencias: list[str] = []
    if not texto.strip():
        advertencias.append("No se pudo extraer texto del PDF. Puede ser un documento escaneado.")
    if len(texto) < 200:
        advertencias.append("Texto muy corto; puede tratarse de un documento escaneado o con protección.")

    return DocumentInfo(
        tipo=tipo_detectado,
        texto_extraido=texto,
        paginas=0,  # se setea en el caller
        campos_detectados=campos,
        advertencias=advertencias,
        confianza_tipo=confianza,
    )


# ── Construir el prompt enriquecido para el orquestador ───────────────────────

def build_document_prompt(info: DocumentInfo, question: str, filename: str) -> str:
    """
    Construye el mensaje enriquecido que se envía al orquestador.
    El documento queda en el contexto de Claude, que luego llama search_cst.
    """
    tipo_labels = {
        "contrato_trabajo": "Contrato de trabajo",
        "carta_despido": "Carta de despido / Terminación de contrato",
        "liquidacion_final": "Liquidación final / Paz y salvo laboral",
        "prorroga_contrato": "Prórroga o renovación de contrato",
        "acta_descargos": "Acta de descargos",
        "reglamento_interno": "Reglamento interno de trabajo",
        "certificado_laboral": "Certificado laboral",
        "documento_laboral_generico": "Documento laboral",
    }

    tipo_label = tipo_labels.get(info.tipo, info.tipo)
    campos_txt = ""
    if info.campos_detectados:
        campos_txt = "\n**Campos detectados automáticamente:**\n" + "\n".join(
            f"- {k}: {v}" for k, v in info.campos_detectados.items()
        )

    advertencias_txt = ""
    if info.advertencias:
        advertencias_txt = "\n**Advertencias de extracción:**\n" + "\n".join(
            f"- {a}" for a in info.advertencias
        )

    # Truncar texto si es muy largo (Claude tiene límite de tokens)
    MAX_CHARS = 12_000
    texto_para_claude = info.texto_extraido
    truncado = False
    if len(texto_para_claude) > MAX_CHARS:
        texto_para_claude = texto_para_claude[:MAX_CHARS]
        truncado = True

    prompt = f"""El usuario ha subido un documento laboral para análisis jurídico.

**Archivo:** {filename}
**Tipo detectado:** {tipo_label} (confianza: {info.confianza_tipo}){campos_txt}{advertencias_txt}

---
**CONTENIDO DEL DOCUMENTO:**

{texto_para_claude}
{"[... documento truncado a los primeros 12.000 caracteres ...]" if truncado else ""}
---

**TAREA:** {question}

Por favor:
1. Confirma o corrige el tipo de documento.
2. Extrae y presenta los datos clave (partes, fechas, salario, tipo de contrato, cláusulas relevantes).
3. Usa la herramienta `search_cst` para verificar la legalidad de las cláusulas o condiciones identificadas.
4. Si es una carta de despido, verifica si las causales invocadas están tipificadas en el CST.
5. Si es un contrato, identifica cláusulas que podrían ser abusivas o ilegales según el CST.
6. Presenta conclusiones con las referencias legales que respaldan tu análisis.
"""
    return prompt
