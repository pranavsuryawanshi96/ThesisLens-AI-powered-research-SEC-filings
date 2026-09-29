from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter


# Params: edit these, then run `uv run --project backend python data/convert.py`
DATA_DIR = Path(__file__).resolve().parent
INPUT_DIR = DATA_DIR / "downloads"
OUTPUT_DIR = DATA_DIR / "markdown"
CLEAR_OUTPUT_DIR = True


def convert_filings() -> dict:
    if CLEAR_OUTPUT_DIR and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    source_manifest = json.loads(
        (INPUT_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    manifest = {
        **source_manifest,
        "converted_at_utc": datetime.now(UTC).isoformat(),
        "converter": "docling",
        "converted_count": 0,
        "filings": [],
    }
    converter = DocumentConverter(allowed_formats=[InputFormat.HTML])

    for filing in source_manifest["filings"]:
        # download.py writes local_path with the OS separator, so normalize it.
        source_rel = Path(filing["local_path"].replace("\\", "/"))
        output_rel = source_rel.with_suffix(".md")
        output_path = OUTPUT_DIR / output_rel
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Converting {source_rel.as_posix()}...")
        document = converter.convert(INPUT_DIR / source_rel).document
        output_path.write_text(document.export_to_markdown(), encoding="utf-8")

        manifest["filings"].append(
            {
                **filing,
                "local_path": output_rel.as_posix(),
                "source_local_path": source_rel.as_posix(),
            }
        )
        manifest["converted_count"] += 1

    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = convert_filings()
    print(f"Converted {result['converted_count']} filing(s) to {OUTPUT_DIR}")
    print(f"Manifest: {OUTPUT_DIR / 'manifest.json'}")
