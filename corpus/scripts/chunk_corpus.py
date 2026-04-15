"""
chunk_corpus.py — Convierte artículos parseados en chunks listos para Qdrant.

Estrategia de chunking legal (ver sección 2.4 del plan de arquitectura):
  - Unidad mínima: artículo individual con metadata completa.
  - Unidad de contexto: cuando un artículo pertenece a un grupo altamente relacionado
    (ej: Arts. 61-66 terminación del contrato), se genera un chunk "grupo" adicional.
  - Header de contexto: cada chunk incluye el título del capítulo y título como prefijo
    para que el embedding capture la jerarquía temática.
  - Asignación de topics: mapeo de artículos a temas de la taxonomía.
  - Marcado de artículos modificados por la Ley 2466/2025.

Uso:
    python chunk_corpus.py               # Procesa CST + Ley 2466
    python chunk_corpus.py --stats       # Solo muestra estadísticas

Salida:
    corpus/parsed/chunks.json            # Lista de chunks listos para Qdrant
"""

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


# El texto de los artículos del CST contiene notas editoriales entre <...>
# añadidas por Avance Jurídico (el editor del sitio). Estas no son HTML real —
# son anotaciones en texto plano que contaminan el embedding.
# Ejemplos:
#   <Artículo modificado por el artículo 14 del Ley 50 de 1990. El nuevo texto es el siguiente:>
#   <Ver Notas del Editor>
#   <Aparte tachado INEXEQUIBLE>
#   <Texto con el cual fue publicado en el Diario Oficial...>
_ANGLE_BRACKETS_RE = re.compile(r"<[^>]+>")


def clean_for_embedding(text: str) -> str:
    """
    Elimina todo contenido entre <...> del texto antes de generar el embedding.
    El texto original (con las notas) se conserva en el campo 'text' del payload.
    """
    if not text:
        return text
    cleaned = _ANGLE_BRACKETS_RE.sub("", text)
    # Colapsar espacios múltiples que quedan tras eliminar las notas
    import re as _re
    cleaned = _re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()

PARSED_DIR = Path(__file__).parent.parent / "parsed"
METADATA_DIR = Path(__file__).parent.parent / "metadata"

# ── Modelo del chunk ────────────────────────────────────────────────────────────


@dataclass
class LegalChunk:
    """
    Un chunk listo para ser vectorizado y cargado en Qdrant.

    El campo `text_for_embedding` es lo que se vectoriza.
    El campo `payload` es lo que Qdrant almacena como metadata filtrable.
    """
    chunk_id: str = ""
    text_for_embedding: str = ""   # Header de contexto + texto del artículo

    # Payload / metadata para Qdrant
    source: str = ""
    book: str = ""
    title: str = ""
    chapter: str = ""
    article_number: str = ""
    article_number_int: int = 0
    article_title: str = ""
    text: str = ""                  # Texto original (sin el header)
    topics: list = field(default_factory=list)
    modified_by: str = ""
    effective_date: str = ""
    derogated: bool = False
    frequently_consulted: bool = False

    # Para chunks de grupo (varios artículos relacionados)
    chunk_type: str = "article"     # "article" | "group"
    articles_in_group: list = field(default_factory=list)


# ── Asignación de topics ────────────────────────────────────────────────────────
#
# Mapeo artículo → topics basado en el conocimiento de la estructura del CST.
# Ampliaremos esto con topics_taxonomy.json en fases posteriores.
# Por ahora, los rangos de artículos más consultados tienen topics predefinidos.

ARTICLE_TOPICS_MAP: dict[tuple[int, int], list[str]] = {
    # Título Preliminar
    (1, 21): ["principios", "definiciones", "aplicación"],

    # Contrato individual
    (22, 37): ["contrato_trabajo", "definición", "elementos"],
    (38, 47): ["capacidad", "nulidades", "formalidades"],
    (48, 60): ["representantes_empleador"],
    (61, 75): ["terminación_contrato", "despido", "justa_causa", "preaviso"],

    # Periodo de prueba
    (76, 82): ["periodo_prueba"],

    # Contratos especiales
    (89, 103): ["contratos_especiales", "aprendizaje", "temporal"],

    # Reglamento de trabajo
    (104, 126): ["reglamento_interno", "disciplina", "sanciones"],

    # Salarios — MUY CONSULTADO
    (127, 144): ["salario", "constitución_salario", "remuneración", "viáticos"],
    (145, 156): ["salario", "pagos_no_salariales", "prestaciones_sociales"],

    # Jornada — MODIFICADO LEY 2466
    (158, 166): ["jornada_trabajo", "horas_extras", "trabajo_nocturno"],
    (167, 171): ["jornada_trabajo", "turnos", "flexibilidad_horaria"],

    # Descansos — MODIFICADO LEY 2466
    (172, 180): ["dominical", "festivos", "recargo_dominical", "descanso_compensatorio"],
    (181, 192): ["vacaciones", "licencias"],

    # Maternidad/paternidad — MUY CONSULTADO
    (236, 245): ["maternidad", "licencia_maternidad", "fuero_maternidad", "lactancia"],
    (246, 248): ["paternidad", "licencia_paternidad"],

    # Cesantías — MUY CONSULTADO
    (249, 258): ["cesantías", "auxilio_cesantía", "intereses_cesantías"],

    # Prima de servicios — MUY CONSULTADO
    (306, 308): ["prima_servicios"],

    # Sindicatos
    (353, 400): ["sindicatos", "derecho_colectivo", "afiliación"],

    # Huelga
    (429, 452): ["huelga", "conflicto_colectivo"],

    # Prescripción — MUY CONSULTADO
    (488, 489): ["prescripción", "caducidad", "términos_legales"],
}

# Artículos frecuentemente consultados
FREQUENTLY_CONSULTED = {
    # Terminación del contrato
    61, 62, 63, 64, 65, 66,
    # Salario
    127, 128, 129, 130, 132,
    # Jornada
    158, 159, 161, 162, 163, 164, 168,
    # Dominical y festivos
    172, 173, 174, 175, 179, 180,
    # Vacaciones
    186, 187, 188, 189,
    # Maternidad
    236, 237, 238, 239,
    # Cesantías
    249, 250, 251, 252,
    # Prima
    306,
    # Prescripción
    488, 489,
}

# Artículos del CST modificados por la Ley 2466/2025
# Mapeo: número_artículo_cst → {artículo_ley_2466, fecha_vigencia}
# Fuente: análisis de la Ley 2466 (completar después de parsear ley_2466_articles.json)
CST_MODIFIED_BY_LEY2466: dict[int, dict] = {
    # Jornada de trabajo — Art. 161 CST (reducción progresiva a 42h)
    161: {"modified_by": "Ley 2466 de 2025, Art. 1", "effective_date": "2025-06-26"},
    # Recargo nocturno — Art. 168 CST
    168: {"modified_by": "Ley 2466 de 2025, Art. 2", "effective_date": "2025-06-26"},
    # Recargo dominical y festivo — Art. 179 CST (subida gradual al 100%)
    179: {"modified_by": "Ley 2466 de 2025, Art. 3", "effective_date": "2025-06-26"},
    180: {"modified_by": "Ley 2466 de 2025, Art. 4", "effective_date": "2025-06-26"},
    # Licencia de maternidad — Art. 236 CST (ampliación)
    236: {"modified_by": "Ley 2466 de 2025, Art. 10", "effective_date": "2025-06-26"},
    # Licencia de paternidad — Art. 236A CST (ampliación)
    # 236A no tiene número entero — manejado como string
    # Estabilidad laboral reforzada — varios artículos
    # NOTA: completar con el texto exacto de la Ley 2466 después del parsing
}


def assign_topics(article_number_int: int) -> list[str]:
    """Asigna topics a un artículo basándose en su número."""
    for (start, end), topics in ARTICLE_TOPICS_MAP.items():
        if start <= article_number_int <= end:
            return topics
    return ["general"]


def build_context_header(source: str, book: str, title: str, chapter: str) -> str:
    """
    Construye el header de contexto que se antepone al texto del artículo
    para mejorar la calidad del embedding.

    El embedding así captura "Código Sustantivo del Trabajo, Libro Primero,
    Título V - Salarios, Capítulo I" además del texto del artículo.
    """
    parts = [source]
    if book:
        parts.append(book)
    if title:
        parts.append(title)
    if chapter:
        parts.append(chapter)
    return " | ".join(parts)


def make_chunk_id(source: str, article_number: str, chunk_type: str = "article") -> str:
    """Genera un ID único y estable para el chunk."""
    safe_source = source.lower().replace(" ", "_").replace("/", "_")
    return f"{safe_source}_art_{article_number}_{chunk_type}"


def chunk_articles(articles: list[dict]) -> list[LegalChunk]:
    """
    Convierte artículos parseados en chunks con metadata enriquecida.
    """
    chunks = []

    for art in articles:
        art_num_int = art.get("article_number_int", 0)
        source = art.get("source", "CST")

        # Topics automáticos
        topics = assign_topics(art_num_int)

        # Marcar si fue modificado por la Ley 2466
        modified_by = art.get("modified_by", "")
        effective_date = art.get("effective_date", "")

        if art_num_int in CST_MODIFIED_BY_LEY2466 and source == "CST":
            reform_info = CST_MODIFIED_BY_LEY2466[art_num_int]
            modified_by = reform_info["modified_by"]
            effective_date = reform_info["effective_date"]

        # Marcar frecuentemente consultados
        frequently_consulted = art_num_int in FREQUENTLY_CONSULTED

        # Construir el header de contexto
        header = build_context_header(
            source=source,
            book=art.get("book", ""),
            title=art.get("title", ""),
            chapter=art.get("chapter", ""),
        )

        # Texto completo para embedding: header + título del artículo (si tiene) + cuerpo limpio
        article_title = art.get("article_title", "")
        text = art.get("text", "")
        text_clean = clean_for_embedding(text)  # Sin notas editoriales para mejor embedding

        if article_title:
            text_for_embedding = f"{header}\n\nArtículo {art.get('article_number')}: {article_title}\n{text_clean}"
        else:
            text_for_embedding = f"{header}\n\nArtículo {art.get('article_number')}: {text_clean}"

        chunk = LegalChunk(
            chunk_id=make_chunk_id(source, art.get("article_number", "0")),
            text_for_embedding=text_for_embedding,
            source=source,
            book=art.get("book", ""),
            title=art.get("title", ""),
            chapter=art.get("chapter", ""),
            article_number=art.get("article_number", ""),
            article_number_int=art_num_int,
            article_title=article_title,
            text=text,
            topics=topics,
            modified_by=modified_by,
            effective_date=effective_date,
            derogated=art.get("derogated", False),
            frequently_consulted=frequently_consulted,
            chunk_type="article",
        )
        chunks.append(chunk)

    return chunks


def generate_group_chunks(chunks: list[LegalChunk]) -> list[LegalChunk]:
    """
    Genera chunks adicionales que agrupan artículos relacionados.

    Para artículos de terminación del contrato (61-66), salarios (127-132),
    y otros grupos altamente consultados juntos, crea un chunk combinado
    que el retriever puede devolver cuando la consulta abarca el tema completo.
    """
    GROUPS = [
        {
            "name": "terminacion_contrato_61_66",
            "range": (61, 66),
            "source": "CST",
            "title": "Terminación del contrato de trabajo",
        },
        {
            "name": "salario_definicion_127_132",
            "range": (127, 132),
            "source": "CST",
            "title": "Definición y elementos del salario",
        },
        {
            "name": "jornada_158_168",
            "range": (158, 168),
            "source": "CST",
            "title": "Jornada de trabajo y horas extras",
        },
        {
            "name": "dominical_172_180",
            "range": (172, 180),
            "source": "CST",
            "title": "Trabajo dominical, festivos y recargos",
        },
        {
            "name": "maternidad_236_245",
            "range": (236, 245),
            "source": "CST",
            "title": "Protección a la maternidad",
        },
        {
            "name": "cesantias_249_258",
            "range": (249, 258),
            "source": "CST",
            "title": "Auxilio de cesantía e intereses",
        },
    ]

    group_chunks = []

    for group_def in GROUPS:
        start, end = group_def["range"]
        relevant = [
            c for c in chunks
            if c.source == group_def["source"]
            and start <= c.article_number_int <= end
            and c.chunk_type == "article"
        ]

        if not relevant:
            continue

        # Combinar textos en orden numérico
        relevant_sorted = sorted(relevant, key=lambda c: c.article_number_int)
        combined_text = "\n\n".join(
            f"Artículo {c.article_number}: {c.article_title + ' — ' if c.article_title else ''}{c.text}"
            for c in relevant_sorted
        )

        # Header del grupo
        first = relevant_sorted[0]
        header = build_context_header(first.source, first.book, first.title, first.chapter)

        group_chunk = LegalChunk(
            chunk_id=f"cst_group_{group_def['name']}",
            text_for_embedding=f"{header}\n\n{group_def['title']}\n\n{combined_text}",
            source=group_def["source"],
            book=first.book,
            title=first.title,
            chapter=first.chapter,
            article_number=f"{start}-{end}",
            article_number_int=start,
            article_title=group_def["title"],
            text=combined_text,
            topics=list({t for c in relevant_sorted for t in c.topics}),
            modified_by="; ".join(set(c.modified_by for c in relevant_sorted if c.modified_by)),
            chunk_type="group",
            articles_in_group=[c.article_number for c in relevant_sorted],
            frequently_consulted=True,
        )
        group_chunks.append(group_chunk)

    return group_chunks


def print_stats(chunks: list[LegalChunk]) -> None:
    by_source = {}
    by_topic: dict[str, int] = {}
    modified_count = 0
    group_count = 0

    for c in chunks:
        by_source[c.source] = by_source.get(c.source, 0) + 1
        for t in c.topics:
            by_topic[t] = by_topic.get(t, 0) + 1
        if c.modified_by:
            modified_count += 1
        if c.chunk_type == "group":
            group_count += 1

    print(f"\n{'='*50}")
    print(f"ESTADÍSTICAS DE CHUNKS")
    print(f"{'='*50}")
    print(f"Total chunks:           {len(chunks)}")
    print(f"Chunks de artículos:    {len(chunks) - group_count}")
    print(f"Chunks de grupo:        {group_count}")
    print(f"Modificados (Ley 2466): {modified_count}")

    print(f"\nPor fuente:")
    for source, count in sorted(by_source.items()):
        print(f"  {source:20s}: {count}")

    print(f"\nTop 10 topics:")
    for topic, count in sorted(by_topic.items(), key=lambda x: -x[1])[:10]:
        print(f"  {topic:30s}: {count}")

    # Estadísticas de longitud del texto para embedding
    lengths = [len(c.text_for_embedding) for c in chunks]
    if lengths:
        print(f"\nLongitud texto_for_embedding:")
        print(f"  Mín:    {min(lengths):6d} chars")
        print(f"  Máx:    {max(lengths):6d} chars")
        print(f"  Media:  {sum(lengths)//len(lengths):6d} chars")
        too_long = sum(1 for l in lengths if l > 2000)
        print(f"  >2000:  {too_long} chunks (posibles truncamientos en embedding)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera chunks legales desde artículos parseados."
    )
    parser.add_argument("--stats", action="store_true", help="Solo mostrar estadísticas")
    args = parser.parse_args()

    all_chunks: list[LegalChunk] = []

    # Cargar artículos del CST
    cst_path = PARSED_DIR / "cst_articles.json"
    if cst_path.exists():
        print(f"Cargando CST: {cst_path}")
        cst_articles = json.loads(cst_path.read_text(encoding="utf-8"))
        cst_chunks = chunk_articles(cst_articles)
        group_chunks = generate_group_chunks(cst_chunks)
        all_chunks.extend(cst_chunks)
        all_chunks.extend(group_chunks)
        print(f"  {len(cst_articles)} artículos → {len(cst_chunks)} chunks de artículo + {len(group_chunks)} chunks de grupo")
    else:
        print(f"[SKIP] {cst_path} no existe. Ejecuta parse_articles.py primero.")

    # Cargar artículos de la Ley 2466
    ley_path = PARSED_DIR / "ley_2466_articles.json"
    if ley_path.exists():
        print(f"Cargando Ley 2466: {ley_path}")
        ley_articles = json.loads(ley_path.read_text(encoding="utf-8"))
        ley_chunks = chunk_articles(ley_articles)
        all_chunks.extend(ley_chunks)
        print(f"  {len(ley_articles)} artículos → {len(ley_chunks)} chunks")
    else:
        print(f"[SKIP] {ley_path} no existe.")

    if not all_chunks:
        print("\n[ERROR] No hay chunks para procesar.")
        return

    print_stats(all_chunks)

    if args.stats:
        print("\n[DRY RUN] No se guardaron archivos.")
        return

    # Guardar chunks
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PARSED_DIR / "chunks.json"
    data = [asdict(c) for c in all_chunks]
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nChunks guardados: {output_path} ({len(all_chunks)} chunks)")
    print("\nPróximo paso: python corpus/scripts/generate_embeddings.py")


if __name__ == "__main__":
    main()
