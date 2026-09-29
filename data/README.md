# Data

Local data artifacts for development live here.

- `downloads/` holds raw source files fetched from SEC EDGAR, grouped by year.
- Downloaded payloads are gitignored because the corpus can get large.
- Fetch a sample corpus with `uv run data/download.py` 
- `markdown/` mirrors `downloads/` (same year folders + `manifest.json`) with each filing converted to Markdown by docling.
- Convert with `uv run --project backend python data/convert.py` (docling is a backend dev dependency).
