# Corpus Legal — LaborIA

## Pipeline de preparación del corpus

Ejecutar en este orden:

```bash
# 1. Descargar HTMLs oficiales
python corpus/scripts/download_cst.py

# 1b. Inspeccionar la estructura del DOM antes de parsear (ejecutar si hay problemas)
python corpus/scripts/download_cst.py --probe

# 2. Parsear artículos → JSONs estructurados
python corpus/scripts/parse_articles.py

# 2b. Revisar el reporte de parsing para detectar artículos mal extraídos
#     cat corpus/parsed/cst_parse_report.json

# 3. Generar chunks con metadata enriquecida
python corpus/scripts/chunk_corpus.py

# 4. Levantar Qdrant si no está corriendo
docker compose up -d qdrant

# 5. Vectorizar y cargar en Qdrant
python corpus/scripts/generate_embeddings.py

# 6. Validar calidad del corpus
python corpus/scripts/validate_corpus.py
```

## Dependencias Python del corpus

```bash
pip install requests beautifulsoup4 sentence-transformers qdrant-client tqdm
```

## Estructura de carpetas

```
corpus/
├── scripts/
│   ├── download_cst.py          # Descarga HTMLs oficiales
│   ├── parse_articles.py        # HTML → JSON por artículo
│   ├── chunk_corpus.py          # JSON → chunks con metadata
│   ├── generate_embeddings.py   # Chunks → Qdrant
│   └── validate_corpus.py       # Validación de calidad
├── raw/                          # HTMLs descargados (gitignored)
│   ├── cst.html
│   └── ley_2466_2025.html
├── parsed/                       # JSONs generados (gitignored)
│   ├── cst_articles.json
│   ├── ley_2466_articles.json
│   ├── chunks.json
│   ├── cst_parse_report.json
│   └── validation_report.json
└── metadata/
    ├── topics_taxonomy.json      # Taxonomía de temas
    └── reform_tracking.json      # Artículos modificados por Ley 2466/2025
```

## Troubleshooting del parser

Si `parse_articles.py` no encuentra artículos:

1. Ejecutar `download_cst.py --probe` para ver la estructura real del HTML.
2. Buscar en el output qué patrón de artículo usa el documento (ej: `ARTICULO 1o.` vs `Artículo 1.`).
3. Ajustar los patrones en `parse_articles.py` → `CST_ARTICLE_PATTERNS`.
4. Verificar el encoding: el sitio puede usar ISO-8859-1 (latin-1).

## Objetivos de calidad (Fase 1)

| Métrica | Objetivo |
|---------|----------|
| Artículos parseados | > 450 (CST tiene ~492) |
| Hit rate en validación | > 85% |
| Artículos críticos presentes | 100% |
| Tiempo de búsqueda | < 50ms p99 |
