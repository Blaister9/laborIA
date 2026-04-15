"""
parse_articles.py — Parsea los HTMLs descargados y genera un JSON por artículo.

Estrategia de parsing:
  1. Detectar automáticamente la estructura del DOM del HTML (modo auto-detect).
  2. Extraer libros, títulos, capítulos y artículos como unidades independientes.
  3. Para el CST: manejar el formato "ARTICULO Xo." o "ARTÍCULO X."
  4. Para la Ley 2466: manejar el formato "Artículo X."
  5. Normalizar texto: limpiar espacios, caracteres especiales, encoding.

Uso:
    python parse_articles.py                      # Parsea ambas fuentes
    python parse_articles.py --source cst         # Solo CST
    python parse_articles.py --source ley2466     # Solo Ley 2466
    python parse_articles.py --dry-run            # Muestra stats sin guardar

Salida:
    corpus/parsed/cst_articles.json              # Lista de artículos CST
    corpus/parsed/ley_2466_articles.json         # Lista de artículos Ley 2466
    corpus/parsed/parse_report.json              # Reporte de calidad del parsing
"""

import argparse
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag

RAW_DIR = Path(__file__).parent.parent / "raw"
PARSED_DIR = Path(__file__).parent.parent / "parsed"

# ── Modelos de datos ────────────────────────────────────────────────────────────


@dataclass
class ParsedArticle:
    """Un artículo legal individual con toda su metadata estructural."""

    # Identificación
    source: str = ""            # "CST" | "Ley_2466" | "Ley_1010" | ...
    article_number: str = ""    # "1", "22", "488" — string para manejar "1o."
    article_number_int: int = 0 # Para ordenamiento numérico

    # Jerarquía estructural
    book: str = ""      # "Título Preliminar" | "Primero" | "Segundo" | "Tercero"
    title: str = ""     # "Título V - Salarios"
    chapter: str = ""   # "Capítulo I - Disposiciones generales"

    # Contenido
    article_title: str = ""     # Título propio del artículo (si tiene)
    text: str = ""              # Texto completo del artículo

    # Metadata legal
    topics: list = field(default_factory=list)  # Se asigna en chunk_corpus.py
    modified_by: str = ""       # "Ley 2466 de 2025, Art. X"
    effective_date: str = ""    # ISO date de la modificación
    derogated: bool = False
    frequently_consulted: bool = False

    # Trazabilidad
    raw_html_snippet: str = ""  # Primeros 500 chars del HTML fuente para debug


@dataclass
class ParseReport:
    """Reporte de calidad del parsing para detectar artículos mal extraídos."""
    source: str = ""
    total_articles: int = 0
    articles_with_text: int = 0
    articles_empty: int = 0
    articles_short: int = 0     # < 50 chars — probable error de parsing
    articles_very_long: int = 0 # > 5000 chars — probable merge de artículos
    books_found: list = field(default_factory=list)
    titles_found: list = field(default_factory=list)
    encoding_issues: int = 0
    warnings: list = field(default_factory=list)


# ── Normalización de texto ──────────────────────────────────────────────────────


def normalize_text(text: str) -> str:
    """Limpia y normaliza texto legal: espacios, encoding, caracteres especiales."""
    if not text:
        return ""
    # Normalizar unicode (NFC: componer caracteres acentuados)
    text = unicodedata.normalize("NFC", text)
    # Colapsar whitespace múltiple y newlines excesivos
    text = re.sub(r"\s+", " ", text)
    # Limpiar caracteres de control excepto newline
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def normalize_article_number(raw: str) -> tuple[str, int]:
    """
    Normaliza el número de artículo.
    Entrada: "1o.", "22", "488", "1°", "1º"
    Salida: ("1", 1), ("22", 22), ("488", 488)
    """
    # Extraer solo dígitos del número
    digits = re.sub(r"[^\d]", "", raw)
    if digits:
        n = int(digits)
        return str(n), n
    return raw.strip(), 0


# ── Parser del CST ──────────────────────────────────────────────────────────────
#
# Estructura REAL del DOM (confirmada con --probe en secretariasenado.gov.co):
#
#   ARTICULOS:
#     <p><a class="bookmarkaj" name="1">ARTICULO 1o. OBJETO.</A> texto del artículo...</p>
#     El número del artículo está en el atributo name="N" del anchor.
#     El texto del anchor contiene "ARTICULO Xo. TITULO."
#     El cuerpo del artículo sigue dentro del mismo <p> tras el </A>.
#
#   ENCABEZADOS (libro/título/capítulo):
#     <p class="centrado"><span class="b_aj">TITULO PRELIMINAR.</span></p>
#     <p class="centrado"><span class="b_aj">PRINCIPIOS GENERALES</span></p>
#     <p class="centrado"><a class="bookmarkaj" name="CAPITULO_III">CAPITULO III.</A></p>
#
#   PÁRRAFOS DE CONTINUACIÓN (notas, parágrafos):
#     <p>Texto adicional sin marcador de artículo...</p>
#
# Estrategia: localizar todos los <a class="bookmarkaj" name="N"> donde N sea numérico.
# Eso identifica artículos de forma directa y confiable.

# Patrones para jerarquía estructural
CST_BOOK_PATTERN = re.compile(
    r"^(LIBRO\s+(PRIMERO|SEGUNDO|TERCERO|[IVX]+)|TITULO\s+PRELIMINAR)",
    re.IGNORECASE,
)
CST_TITLE_PATTERN = re.compile(r"^T[ÍI]TULO\s+[IVX\d]+", re.IGNORECASE)
CST_CHAPTER_PATTERN = re.compile(r"^CAP[ÍI]TULO\s+[IVX\d]+", re.IGNORECASE)

# Patrón para extraer número y título del texto del anchor de un artículo
# Entrada: "ARTICULO 1o. OBJETO."  →  grupo1="1o", grupo2="OBJETO"
CST_ANCHOR_ARTICLE_RE = re.compile(
    r"^ARTICULO\s+(\d+[o°º]?)\.?\s*(.*?)\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _is_numeric_name(name_val: str) -> bool:
    """Retorna True si el atributo name del anchor es un número de artículo."""
    return bool(re.match(r"^\d+$", name_val.strip()))


def _classify_header(text: str) -> tuple[str, str]:
    """Clasifica texto de encabezado: retorna (tipo, texto). Tipo: book/title/chapter/unknown."""
    t = text.strip()
    if CST_BOOK_PATTERN.match(t):
        return "book", t
    if CST_TITLE_PATTERN.match(t):
        return "title", t
    if CST_CHAPTER_PATTERN.match(t):
        return "chapter", t
    return "unknown", t


def parse_cst(html_path: Path) -> tuple[list[ParsedArticle], ParseReport]:
    """
    Parsea el HTML del CST concatenado (multi-pagina) y extrae artículos.

    Estrategia basada en el DOM real de secretariasenado.gov.co:
    1. Buscar todos los <a class="bookmarkaj" name="N"> donde N es numérico → artículos.
    2. Buscar <p class="centrado"> → encabezados de libro/título/capítulo.
    3. Iterar todos los <p> en orden del documento, manteniendo contexto estructural.
    4. Cuando encontramos un anchor de artículo, iniciar nuevo artículo.
    5. Párrafos siguientes sin anchor numérico = continuación del artículo.
    """
    report = ParseReport(source="CST")
    articles: list[ParsedArticle] = []

    if not html_path.exists():
        report.warnings.append(f"Archivo no encontrado: {html_path}")
        return articles, report

    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # Estado del contexto estructural actual
    current_book = ""
    current_title = ""
    current_chapter = ""
    current_article: Optional[ParsedArticle] = None

    body = soup.find("body") or soup

    def _flush_article():
        """Finaliza el artículo en curso y lo agrega a la lista."""
        nonlocal current_article
        if current_article and current_article.text:
            # Post-procesar: si el texto del artículo empieza con su título,
            # separar el título del cuerpo
            _split_article_title(current_article)
            articles.append(current_article)
            report.total_articles += 1
        current_article = None

    def _split_article_title(art: ParsedArticle) -> None:
        """
        Separa el título del artículo de su texto si están unidos.
        Ejemplo: "OBJETO Y FINALIDAD DEL CODIGO. El presente Código..."
                → article_title="OBJETO Y FINALIDAD DEL CODIGO"
                  text="El presente Código..."
        """
        # Patrón: TITULO EN MAYÚSCULAS. Texto en minúsculas o mixto.
        m = re.match(r"^([A-ZÁÉÍÓÚÜÑ\s\,\-\/]{5,80})\.\s+(.+)", art.text, re.DOTALL)
        if m:
            candidate_title = m.group(1).strip()
            candidate_body = m.group(2).strip()
            # Solo separar si el "título" parece ser un encabezado (todo mayúsculas, < 80 chars)
            if len(candidate_title) < 80 and candidate_title == candidate_title.upper():
                art.article_title = candidate_title
                art.text = candidate_body

    # ── Iteración principal sobre todos los <p> del documento ──────────────────
    # Clasificación por tipo de elemento:
    #   A) <p> o <b> con <a name="N"> donde N es numérico → ARTÍCULO
    #      (clase bookmarkaj opcional — algunos articulos reformados usan <b> sin la clase)
    #      También: <span class="b_aj"><a name="N"> → ARTÍCULO
    #   B) <p class="centrado"> con <span class="b_aj"> → ENCABEZADO libro/título/capítulo
    #   C) <p> normal sin marker → CONTINUACIÓN del artículo en curso
    #      EXCEPTO: si empieza con prefijos de notas editoriales → IGNORAR

    IGNORE_PREFIXES = (
        "notas de vigencia", "jurisprudencia", "concordancias",
        "doctrina", "legislación anterior", "ir al inicio",
    )

    # Incluir <b> y <span> además de <p> para capturar artículos reformados
    all_paragraphs = body.find_all(["p", "b", "span"])

    # Filtrar <span> a solo aquellos con class="b_aj" que contienen anchors numéricos
    # (para evitar procesar miles de spans irrelevantes)
    def _should_process(tag) -> bool:
        if tag.name == "p":
            return True
        if tag.name == "b":
            # Solo <b> que contienen un <a name="N"> numérico directo
            a = tag.find("a", attrs={"name": re.compile(r"^\d+$")})
            return a is not None
        if tag.name == "span":
            classes = tag.get("class", [])
            if "b_aj" in classes:
                a = tag.find("a", attrs={"name": re.compile(r"^\d+$")})
                return a is not None
        return False

    all_paragraphs = [t for t in all_paragraphs if _should_process(t)]

    for tag in all_paragraphs:
        raw_text = normalize_text(tag.get_text())
        if not raw_text or len(raw_text) < 3:
            continue

        # Ignorar párrafos que son metadata editorial (notas de vigencia, etc.)
        if any(raw_text.lower().startswith(pref) for pref in IGNORE_PREFIXES):
            continue

        # ── Caso A: elemento con anchor numérico → es un artículo ─────────────
        # Buscar <a name="N"> con N numérico — con o sin class="bookmarkaj"
        bookmark_anchor = tag.find("a", attrs={"name": re.compile(r"^\d+$")})
        if bookmark_anchor:
            name_val = bookmark_anchor.get("name", "")
            if _is_numeric_name(name_val):
                # Es un artículo
                _flush_article()

                anchor_text = normalize_text(bookmark_anchor.get_text())

                # Extraer número y título del anchor: "ARTICULO 1o. OBJETO."
                art_num_str = name_val.strip()
                try:
                    art_num_int = int(art_num_str)
                except ValueError:
                    art_num_int = 0

                # Extraer título del artículo del texto del anchor
                # Patron: ARTICULO Xo. TITULO DEL ARTICULO.
                art_title = ""
                m = CST_ANCHOR_ARTICLE_RE.match(anchor_text)
                if m and m.lastindex >= 2:
                    art_title = normalize_text(m.group(2))

                # El cuerpo del artículo es el texto del <p> EXCEPTO el texto del anchor
                # Obtener texto después del anchor dentro del mismo <p>
                body_parts = []
                for child in tag.children:
                    if child == bookmark_anchor:
                        continue
                    if isinstance(child, NavigableString):
                        body_parts.append(str(child))
                    elif hasattr(child, 'get_text'):
                        # No incluir <div> de notas de vigencia
                        if child.name == "div":
                            continue
                        body_parts.append(child.get_text())
                article_body = normalize_text("".join(body_parts))

                current_article = ParsedArticle(
                    source="CST",
                    article_number=art_num_str,
                    article_number_int=art_num_int,
                    book=current_book,
                    title=current_title,
                    chapter=current_chapter,
                    article_title=art_title,
                    text=article_body,
                    raw_html_snippet=str(tag)[:500],
                )
                continue

            else:
                # Anchor no numérico → probablemente encabezado (CAPITULO_III, etc.)
                anchor_text = normalize_text(bookmark_anchor.get_text())
                elem_type, elem_text = _classify_header(anchor_text)
                if elem_type == "chapter":
                    _flush_article()
                    current_chapter = elem_text
                continue

        # ── Caso B: párrafo centrado con span.b_aj → encabezado libro/título ──
        p_class = " ".join(tag.get("class", []))
        if "centrado" in p_class:
            span_baj = tag.find("span", class_="b_aj")
            if span_baj:
                header_text = normalize_text(span_baj.get_text())
                elem_type, elem_text = _classify_header(header_text)

                if elem_type == "book":
                    _flush_article()
                    current_book = elem_text
                    current_title = ""
                    current_chapter = ""
                    if elem_text not in report.books_found:
                        report.books_found.append(elem_text)
                elif elem_type == "title":
                    _flush_article()
                    current_title = elem_text
                    current_chapter = ""
                    if elem_text not in report.titles_found:
                        report.titles_found.append(elem_text)
                elif elem_type == "chapter":
                    _flush_article()
                    current_chapter = elem_text
                # Si es "unknown" podría ser el subtítulo del título (ej: "PRINCIPIOS GENERALES")
                # No necesitamos guardarlo en un campo, pero tampoco es continuación de artículo
            continue

        # ── Caso C: párrafo normal → continuación del artículo en curso ────────
        if current_article is not None:
            # Filtrar párrafos que son claramente notas editoriales
            # (suelen empezar con "Texto con el cual fue" o "<" o son muy cortos)
            if raw_text.startswith("<") or len(raw_text) < 5:
                continue
            if current_article.text:
                current_article.text += " " + raw_text
            else:
                current_article.text = raw_text

    # Guardar el último artículo
    _flush_article()

    # Si no encontramos artículos con la estrategia principal, intentar fallback por regex
    if not articles:
        report.warnings.append(
            "Estrategia principal no encontro articulos. "
            "Intentando fallback por regex sobre texto completo."
        )
        articles, report = _parse_cst_regex_fallback(html, report)

    # Calcular estadísticas del reporte
    for art in articles:
        if art.text:
            report.articles_with_text += 1
            if len(art.text) < 50:
                report.articles_short += 1
                report.warnings.append(
                    f"Art. {art.article_number}: texto muy corto ({len(art.text)} chars): '{art.text[:80]}'"
                )
            if len(art.text) > 5000:
                report.articles_very_long += 1
                report.warnings.append(
                    f"Art. {art.article_number}: texto muy largo ({len(art.text)} chars) — posible merge"
                )
        else:
            report.articles_empty += 1
            report.warnings.append(f"Art. {art.article_number}: texto vacío")

    return articles, report


def _parse_cst_regex_fallback(html: str, report: ParseReport) -> tuple[list[ParsedArticle], ParseReport]:
    """
    Fallback: parsear el texto plano del HTML usando solo regex.
    Útil si el HTML tiene estructura diferente a la esperada.
    """
    # Extraer todo el texto plano del HTML
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(separator="\n")

    # Patrón para encontrar artículos: "ARTICULO Xo. TITULO. Texto..."
    pattern = re.compile(
        r"(ARTICULO|ART[ÍI]CULO)\s+(\d+[o°º]?)\.?\s*",
        re.IGNORECASE,
    )

    articles = []
    matches = list(pattern.finditer(full_text))

    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        article_text = normalize_text(full_text[start:end])

        art_num_str, art_num_int = normalize_article_number(m.group(2))

        articles.append(ParsedArticle(
            source="CST",
            article_number=art_num_str,
            article_number_int=art_num_int,
            text=article_text,
        ))

    report.warnings.append(
        f"Fallback regex encontró {len(articles)} artículos (sin metadata estructural)"
    )
    return articles, report


# ── Parser de la Ley 2466 ───────────────────────────────────────────────────────
#
# funcionpublica.gov.co usa HTML más moderno. Estructura típica:
#
#   <div class="norma"> o similar
#     <p><strong>Artículo 1°.</strong> Modifícase el artículo 161...</p>
#     <p>Parágrafo 1°. ...</p>
#   </div>
#
# O puede ser una tabla:
#   <table><tr><td>Artículo 1°...</td></tr></table>

LEY2466_ARTICLE_PATTERNS = [
    re.compile(r"^Art[ÍI]culo\s+(\d+[°º]?)\.?\s*(.*)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^ARTICULO\s+(\d+[o°º]?)\.?\s*(.*)", re.IGNORECASE | re.DOTALL),
]


def parse_ley2466(html_path: Path) -> tuple[list[ParsedArticle], ParseReport]:
    """Parsea el HTML de la Ley 2466 de 2025."""
    report = ParseReport(source="Ley_2466")
    articles: list[ParsedArticle] = []

    if not html_path.exists():
        report.warnings.append(f"Archivo no encontrado: {html_path}")
        return articles, report

    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    current_chapter = ""
    current_article: Optional[ParsedArticle] = None

    def _flush():
        nonlocal current_article
        if current_article and current_article.text:
            articles.append(current_article)
            report.total_articles += 1
        current_article = None

    # funcionpublica.gov.co puede envolver el contenido en un div con la norma
    # Intentamos el contenedor más específico primero, luego fallback a body
    content_div = (
        soup.find("div", class_=re.compile(r"norma|contenido|texto", re.I))
        or soup.find("div", id=re.compile(r"norma|contenido|cuerpo", re.I))
        or soup.find("body")
        or soup
    )

    all_tags = content_div.find_all(["p", "h1", "h2", "h3", "h4", "td"])

    for tag in all_tags:
        raw_text = normalize_text(tag.get_text())
        if not raw_text or len(raw_text) < 3:
            continue

        # Detectar artículo
        article_match = None
        for pat in LEY2466_ARTICLE_PATTERNS:
            m = pat.match(raw_text)
            if m:
                article_match = m
                break

        if article_match:
            _flush()
            art_num_raw = article_match.group(1)
            art_num_str, art_num_int = normalize_article_number(art_num_raw)
            remainder = normalize_text(article_match.group(2)) if article_match.lastindex >= 2 else ""

            current_article = ParsedArticle(
                source="Ley_2466",
                article_number=art_num_str,
                article_number_int=art_num_int,
                chapter=current_chapter,
                text=remainder,
                raw_html_snippet=str(tag)[:500],
            )
        elif current_article is not None:
            # Continuación del artículo
            continuation = raw_text
            if current_article.text:
                current_article.text += " " + continuation
            else:
                current_article.text = continuation
        else:
            # Posible capítulo/título antes del primer artículo
            upper = raw_text.upper()
            if "CAPÍTULO" in upper or "CAPITULO" in upper or "TÍTULO" in upper or "TITULO" in upper:
                current_chapter = raw_text
                if raw_text not in report.titles_found:
                    report.titles_found.append(raw_text)

    _flush()

    # Estadísticas
    for art in articles:
        if art.text:
            report.articles_with_text += 1
            if len(art.text) < 50:
                report.articles_short += 1
            if len(art.text) > 5000:
                report.articles_very_long += 1
        else:
            report.articles_empty += 1

    return articles, report


# ── Guardado de resultados ──────────────────────────────────────────────────────


def save_articles(articles: list[ParsedArticle], output_path: Path) -> None:
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    data = [asdict(a) for a in articles]
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Guardado: {output_path} ({len(articles)} artículos)")


def save_report(report: ParseReport, output_path: Path) -> None:
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Reporte: {output_path}")


# ── CLI ─────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parsea HTMLs legales → JSONs estructurados por artículo."
    )
    parser.add_argument(
        "--source", choices=["cst", "ley2466", "all"], default="all"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Muestra estadísticas pero no guarda archivos"
    )
    args = parser.parse_args()

    all_reports = []

    if args.source in ("cst", "all"):
        print("\n" + "=" * 70)
        print("Parseando CST...")
        cst_path = RAW_DIR / "cst.html"
        articles, report = parse_cst(cst_path)
        all_reports.append(report)

        print(f"\nResultados CST:")
        print(f"  Artículos encontrados:  {report.total_articles}")
        print(f"  Con texto:              {report.articles_with_text}")
        print(f"  Vacíos:                 {report.articles_empty}")
        print(f"  Muy cortos (<50 chars): {report.articles_short}")
        print(f"  Muy largos (>5000):     {report.articles_very_long}")
        print(f"  Libros encontrados:     {len(report.books_found)}")
        print(f"  Títulos encontrados:    {len(report.titles_found)}")

        if report.books_found:
            print(f"\n  Libros: {report.books_found}")
        if report.titles_found[:5]:
            print(f"  Primeros títulos: {report.titles_found[:5]}")
        if report.warnings:
            print(f"\n  ADVERTENCIAS ({len(report.warnings)}):")
            for w in report.warnings[:10]:
                print(f"    - {w}")
            if len(report.warnings) > 10:
                print(f"    ... y {len(report.warnings) - 10} más (ver reporte completo)")

        if not args.dry_run:
            save_articles(articles, PARSED_DIR / "cst_articles.json")
            save_report(report, PARSED_DIR / "cst_parse_report.json")
        else:
            print("\n  [DRY RUN] No se guardaron archivos.")

        # Mostrar muestra de los primeros artículos parseados
        if articles:
            print(f"\n  Muestra — primeros 3 artículos:")
            for art in articles[:3]:
                print(f"    Art. {art.article_number}: '{art.text[:100]}...'")
                print(f"      Book='{art.book}' | Title='{art.title}' | Chapter='{art.chapter}'")

    if args.source in ("ley2466", "all"):
        print("\n" + "=" * 70)
        print("Parseando Ley 2466/2025...")
        ley_path = RAW_DIR / "ley_2466_2025.html"
        articles, report = parse_ley2466(ley_path)
        all_reports.append(report)

        print(f"\nResultados Ley 2466:")
        print(f"  Artículos encontrados:  {report.total_articles}")
        print(f"  Con texto:              {report.articles_with_text}")
        print(f"  Vacíos:                 {report.articles_empty}")

        if report.warnings:
            print(f"\n  ADVERTENCIAS:")
            for w in report.warnings[:5]:
                print(f"    - {w}")

        if not args.dry_run:
            save_articles(articles, PARSED_DIR / "ley_2466_articles.json")
            save_report(report, PARSED_DIR / "ley_2466_parse_report.json")
        else:
            print("\n  [DRY RUN] No se guardaron archivos.")

        if articles:
            print(f"\n  Muestra — primeros 3 artículos:")
            for art in articles[:3]:
                print(f"    Art. {art.article_number}: '{art.text[:100]}...'")

    print("\nPróximo paso: python corpus/scripts/chunk_corpus.py")


if __name__ == "__main__":
    main()
