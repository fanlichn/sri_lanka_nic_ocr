"""Command-line interface for testing a single image without the HTTP server.

Usage:
    python -m app.cli path/to/id_card.jpg
"""
from __future__ import annotations

import json
import sys

from .config import get_settings
from .extractor import extract
from .ocr_engine import create_engine
from .preprocessing import build_variants, load_image


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python -m app.cli <图片路径>")
        return 1

    settings = get_settings()
    engine = create_engine(settings)
    engine.warmup()

    with open(sys.argv[1], "rb") as f:
        img = load_image(f.read())

    lines = []
    for variant in build_variants(img):
        lines.extend(engine.recognize(variant["img"]))

    dedup = {}
    for ln in lines:
        key = ln.text.strip().lower()
        if not key:
            continue
        if key not in dedup or ln.confidence > dedup[key].confidence:
            dedup[key] = ln
    unique = sorted(dedup.values(), key=lambda l: l.confidence, reverse=True)

    result = extract(unique, settings)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
