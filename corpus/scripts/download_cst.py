"""
download_cst.py — Descarga el HTML del CST y la Ley 2466 desde sus fuentes oficiales.

IMPORTANTE — El CST en secretariasenado.gov.co esta paginado:
  - codigo_sustantivo_trabajo.html        (page 0, Arts 1-31 aprox)
  - codigo_sustantivo_trabajo_pr001.html  (page 1)
  - codigo_sustantivo_trabajo_pr002.html  (page 2)
  - ...hasta que no haya mas enlace "Siguiente"

Este script descarga todas las paginas y las concatena en un solo cst.html.

Uso:
    python download_cst.py                  # Descarga ambas fuentes
    python download_cst.py --probe          # Muestra estructura del DOM de la primera pagina
    python download_cst.py --source cst     # Solo CST
    python download_cst.py --source ley2466 # Solo Ley 2466

Salida:
    corpus/raw/cst.html           (todas las paginas concatenadas)
    corpus/raw/ley_2466_2025.html
"""

import argparse
import re
import sys
import time
from pathlib import Path

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

RAW_DIR = Path(__file__).parent.parent / "raw"

CST_BASE_URL = "http://www.secretariasenado.gov.co/senado/basedoc/"
CST_FIRST_PAGE = "codigo_sustantivo_trabajo.html"

LEY2466_URL = "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=260676"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

PROBE_BYTES = 3000
PROBE_CONTEXT = 2000


# ── HTTP helper ─────────────────────────────────────────────────────────────────

def fetch_page(url: str, encoding: str = "latin-1", timeout: int = 60) -> str:
    """Descarga una URL y retorna el texto con encoding correcto."""
    session = requests.Session()
    try:
        resp = session.get(url, headers=HEADERS, verify=False, timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        print(f"  [ERROR] No se pudo conectar a {url}: {e}")
        raise SystemExit(1)
    except requests.exceptions.HTTPError as e:
        print(f"  [ERROR] HTTP {resp.status_code} en {url}: {e}")
        raise SystemExit(1)

    if encoding:
        resp.encoding = encoding
    return resp.text


def find_next_page(html: str) -> str | None:
    """
    Busca el enlace 'Siguiente' en la pagina actual.
    El patron es: <a class=antsig href="codigo_sustantivo_trabajo_pr001.html">Siguiente</a>
    Retorna solo el nombre del archivo (ej: "codigo_sustantivo_trabajo_pr001.html") o None.
    """
    # Buscar con BeautifulSoup — mas robusto que regex para atributos sin comillas
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("a"):
        text = tag.get_text(strip=True)
        href = tag.get("href", "")
        if "siguiente" in text.lower() and href.endswith(".html"):
            # Retornar solo el nombre del archivo (sin base URL)
            return href.split("/")[-1].split("#")[0]

    # Fallback por regex para casos de HTML malformado
    m = re.search(
        r'<a[^>]*href=["\']?(codigo_sustantivo_trabajo_pr\d+\.html)["\']?[^>]*>Siguiente',
        html, re.IGNORECASE
    )
    if m:
        return m.group(1)

    return None


def extract_body_content(html: str) -> str:
    """
    Extrae solo el contenido util del body, descartando header/footer/navigation.
    El contenido esta dentro de <div id="aj_data"> o similar.
    """
    soup = BeautifulSoup(html, "html.parser")

    # El contenido del CST esta en un div con id="aj_data" o "aj_data_arbol"
    # Si no lo encontramos, usamos el body completo
    content_div = soup.find("div", id="aj_data")
    if content_div:
        return str(content_div)

    # Fallback: extraer entre el primer ARTICULO y el fin del body
    body = soup.find("body")
    if body:
        return str(body)

    return html


# ── Descarga CST (multi-pagina) ─────────────────────────────────────────────────

def download_cst(probe: bool = False) -> Path:
    """
    Descarga todas las paginas del CST y las concatena en corpus/raw/cst.html.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / "cst.html"

    print("\n" + "=" * 70)
    print("Descargando CST -- secretariasenado.gov.co (multi-pagina)")
    print("=" * 70)

    all_pages_html: list[str] = []
    current_file = CST_FIRST_PAGE
    page_num = 0
    total_articles = 0

    while current_file:
        url = CST_BASE_URL + current_file
        print(f"  Pagina {page_num:3d}: {url}")

        html = fetch_page(url, encoding="latin-1")

        # Contar articulos en esta pagina
        art_count = len(re.findall(r"ARTICULO\s+\d+", html, re.IGNORECASE))
        print(f"           {art_count} articulos encontrados")
        total_articles += art_count

        # Si es la primera pagina y hay probe, ejecutarlo
        if page_num == 0 and probe:
            _probe_html(html, current_file)

        all_pages_html.append(html)

        # Buscar la siguiente pagina
        next_file = find_next_page(html)
        if next_file == current_file:
            print("  [ADVERTENCIA] Enlace 'Siguiente' apunta a la misma pagina. Deteniendo.")
            break

        current_file = next_file
        page_num += 1

        # Pausa cortés entre requests
        if current_file:
            time.sleep(0.5)

    print(f"\n  Total: {page_num} paginas, ~{total_articles} articulos")

    # Concatenar todo en un solo HTML
    # Envolvemos en estructura HTML valida con el contenido de todas las paginas
    combined = _build_combined_html(all_pages_html)
    out_path.write_text(combined, encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    print(f"  Guardado: {out_path} ({size_kb:.0f} KB)")
    return out_path


def _build_combined_html(pages: list[str]) -> str:
    """
    Combina todas las paginas en un solo HTML.
    Extrae el contenido util de cada pagina y los concatena.
    """
    # Tomar el head de la primera pagina
    soup_first = BeautifulSoup(pages[0], "html.parser")
    head = str(soup_first.find("head") or "")

    # Extraer body content de cada pagina
    bodies = []
    for i, page_html in enumerate(pages):
        soup = BeautifulSoup(page_html, "html.parser")

        # Buscar el div de contenido principal
        content = soup.find("div", id="aj_data")
        if not content:
            # Fallback: buscar todos los parrafos con articulos
            body = soup.find("body")
            content = body if body else soup

        bodies.append(f"\n<!-- ===== PAGINA {i} ===== -->\n{content}")

    combined_body = "\n".join(str(b) for b in bodies)

    return f"""<!DOCTYPE html>
<html lang="es">
{head}
<body>
{combined_body}
</body>
</html>"""


# ── Descarga Ley 2466 ───────────────────────────────────────────────────────────

def download_ley2466(probe: bool = False) -> Path:
    """Descarga la Ley 2466/2025 desde funcionpublica.gov.co."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / "ley_2466_2025.html"

    print("\n" + "=" * 70)
    print("Descargando Ley 2466/2025 -- funcionpublica.gov.co")
    print("=" * 70)
    print(f"  URL: {LEY2466_URL}")

    html = fetch_page(LEY2466_URL, encoding=None)  # Dejar que requests detecte encoding

    art_count = len(re.findall(r"Art[íi]culo\s+\d+", html, re.IGNORECASE))
    print(f"  Articulos encontrados: {art_count}")
    print(f"  Tamano: {len(html.encode('utf-8')):,} bytes")

    if probe:
        _probe_html(html, "ley_2466_2025.html")

    out_path.write_text(html, encoding="utf-8")
    print(f"  Guardado: {out_path}")
    return out_path


# ── Probe ───────────────────────────────────────────────────────────────────────

def _probe_html(html: str, filename: str) -> None:
    """Vuelca muestras del HTML para inspeccion manual de la estructura del DOM."""
    # Forzar stdout a utf-8 para terminales Windows cp1252
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    sep = "-" * 70
    print(f"\n{sep}")
    print(f"MODO PROBE -- {filename}")
    print(sep)

    print(f"\n[INICIO DEL DOCUMENTO -- primeros {PROBE_BYTES} chars]")
    print(html[:PROBE_BYTES])

    # Buscar el primer articulo
    patterns = [
        r"ARTICULO\s+\d+",
        r"ART[IÍ]CULO\s+\d+",
        r"Art[ií]culo\s+\d+",
    ]
    first_pos = None
    matched_pat = None
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            first_pos = m.start()
            matched_pat = pat
            break

    if first_pos is not None:
        start = max(0, first_pos - 300)
        end = min(len(html), first_pos + PROBE_CONTEXT)
        print(f"\n[PRIMER ARTICULO con patron '{matched_pat}' -- pos {first_pos}]")
        print(f"[HTML crudo chars {start}-{end}]")
        print(html[start:end])
    else:
        print("\n[SIN articulos detectados con patrones conocidos]")
        mid = len(html) // 2
        print(f"\n[MITAD DEL DOC -- chars {mid}-{mid+PROBE_CONTEXT}]")
        print(html[mid : mid + PROBE_CONTEXT])

    # Conteo de patrones
    print(f"\n{sep}")
    print("CONTEO DE PATRONES CLAVE:")
    count_patterns = {
        "ARTICULO (mayusc)": r"ARTICULO\s+\d+",
        "Articulo (mixto)": r"Art[ií]culo\s+\d+",
        "class=bookmarkaj": r'class=["\']?bookmarkaj',
        "class=centrado": r'class=["\']?centrado',
        "span.b_aj": r'class=["\']?b_aj',
        "<h1>": r"<h1[^>]*>",
        "<h2>": r"<h2[^>]*>",
        "<h3>": r"<h3[^>]*>",
        "<p>": r"<p[^>]*>",
        "<div>": r"<div[^>]*>",
        "<b>": r"<b[^>]*>",
        "<strong>": r"<strong[^>]*>",
        "name=N (anchor)": r'name=["\']?\d+["\']?',
        "Siguiente (pag)": r">Siguiente<",
        "Anterior (pag)": r">Anterior<",
    }
    for name, pat in count_patterns.items():
        count = len(re.findall(pat, html, re.IGNORECASE))
        if count > 0:
            print(f"  {name:30s}: {count:5d}")
    print(sep)


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarga el corpus legal para LaborIA (CST multi-pagina + Ley 2466)."
    )
    parser.add_argument(
        "--source", choices=["cst", "ley2466", "all"], default="all",
        help="Fuente a descargar (default: all)"
    )
    parser.add_argument(
        "--probe", action="store_true",
        help="Vuelca muestra del HTML para inspeccionar estructura del DOM"
    )
    args = parser.parse_args()

    if args.source in ("cst", "all"):
        download_cst(probe=args.probe)

    if args.source in ("ley2466", "all"):
        download_ley2466(probe=args.probe)

    print("\nDescarga completa. Siguiente paso:")
    print("  python corpus/scripts/parse_articles.py")


if __name__ == "__main__":
    main()
