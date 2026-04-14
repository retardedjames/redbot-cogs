#!/usr/bin/env python3
"""
run_pipeline.py — combined download + stage generation for BrandGuesser.

For each brand: download images (with OCR text removal), then immediately
generate blur stages. Stages are ready as soon as images land — no waiting.

Every PREVIEW_EVERY brands a random completed stage image is copied to
images/_preview/ so an external monitor can SCP it for spot-checking.

Usage:
    python run_pipeline.py              # all brands
    python run_pipeline.py 50           # first N brands
    python run_pipeline.py "McDonald"   # single brand (substring match)
    python run_pipeline.py --regen      # re-generate stages even if they exist

Progress is also written to pipeline.log in this directory.
"""

import os
import random
import shutil
import sys
import time
from pathlib import Path

import download_images as dl
import create_stages   as cs

IMAGES_DIR  = dl.IMAGES_DIR
PREVIEW_DIR = IMAGES_DIR / "_preview"
LOG_PATH    = Path(__file__).parent / "pipeline.log"


def log(msg: str) -> None:
    print(msg, flush=True)
    with LOG_PATH.open("a") as f:
        f.write(msg + "\n")


def write_preview(brand_name: str, brand_index: int) -> None:
    """Copy all 5 stages for a random image to _preview/ for external monitoring."""
    stages_dir = IMAGES_DIR / brand_name / "stages"
    if not stages_dir.is_dir():
        return
    # Pick a random source image (img-001 … img-005) that has stages
    img_stems = sorted({p.name.split("_s")[0] for p in stages_dir.glob("img-*_s*.jpg")})
    if not img_stems:
        return
    chosen_stem = random.choice(img_stems)
    safe = brand_name.replace("/", "-").replace(" ", "_")
    for stage_file in sorted(stages_dir.glob(f"{chosen_stem}_s*.jpg")):
        dest = PREVIEW_DIR / f"preview_{brand_index:03d}_{safe}__{stage_file.name}"
        shutil.copy2(stage_file, dest)
    log(f"  [preview] {brand_index:03d} {brand_name} — all stages for {chosen_stem}")


def main() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("")  # clear log on fresh run

    args  = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    regen = "--regen" in flags

    all_brands = dl.load_brands()

    if args:
        arg = args[0]
        if arg.isdigit():
            brands = all_brands[: int(arg)]
        else:
            needle = arg.lower()
            brands = [(n, s) for n, s in all_brands if needle in n.lower()]
            if not brands:
                log(f"No brand matching '{arg}' found.")
                sys.exit(1)
    else:
        brands = all_brands

    total = len(brands)
    log("BrandGuesser — full pipeline (download + stages)")
    log(f"  Brands   : {total}")
    log(f"  Preview  : after every brand → {PREVIEW_DIR}")
    log(f"  Log      : {LOG_PATH}")
    log("-" * 64)

    completed = 0
    for i, (name, term) in enumerate(brands, 1):
        # ── Step 1: download + OCR ─────────────────────────────────────────────
        dl.process_brand(name, term, i, total)

        # ── Step 2: stages (fast — ~0.5s per brand) ───────────────────────────
        n = cs.process_brand(name, regen=regen)
        if n:
            completed += 1

        # ── Preview: write one after every completed brand ────────────────────
        if completed > 0:
            write_preview(name, i)

        if i < total:
            time.sleep(random.uniform(dl.DELAY_MIN, dl.DELAY_MAX))

    log(f"\nDone. {completed}/{total} brands fully processed.")


if __name__ == "__main__":
    main()
