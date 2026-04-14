#!/usr/bin/env python3
"""
download_images.py — download food photos for FoodGuesser.

For each food in FOODS:
  1. Search DuckDuckGo images for "{food name} food dish".
  2. Download the first 4 successful results.
  3. Save as images/{slug}/img-001.jpg … img-004.jpg

Usage:
    python download_images.py              # all foods
    python download_images.py 10           # first N foods
    python download_images.py "pizza"      # single food (substring match)
"""

import io
import os
import re
import sys
import time
import random
from pathlib import Path

import requests
from PIL import Image

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
IMAGES_DIR = Path(os.environ.get("IMAGES_DIR", str(SCRIPT_DIR / "images")))

# ── Config ─────────────────────────────────────────────────────────────────────
DELAY_MIN        = 3
DELAY_MAX        = 8
DDG_TIMEOUT      = 25
DOWNLOAD_TIMEOUT = 20
CANDIDATE_URLS   = 20   # fetch this many URLs; take first 4 that download OK
IMAGES_PER_FOOD  = 4

DISPLAY_SIZE = (400, 400)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── Slug helper ───────────────────────────────────────────────────────────────
def slugify(name: str) -> str:
    """'Kung Pao Chicken' → 'kung_pao_chicken'"""
    s = name.lower()
    s = re.sub(r"[''']", "", s)          # drop apostrophes
    s = re.sub(r"[^a-z0-9]+", "_", s)   # non-alphanum → underscore
    return s.strip("_")


# ── DDG search ────────────────────────────────────────────────────────────────
def search_images(query: str, n: int) -> list:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    for attempt in range(3):
        try:
            results = list(DDGS(timeout=DDG_TIMEOUT).images(query, max_results=n))
            return [r["image"] for r in results if r.get("image")]
        except Exception as exc:
            wait = (attempt + 1) * 5
            print(f"\n  [DDG error #{attempt+1}] {exc!r} — retrying in {wait}s", flush=True)
            time.sleep(wait)
    return []


# ── Download one image ────────────────────────────────────────────────────────
def fetch_image(url: str):
    """Download URL and return a PIL Image (RGB), or None on failure."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=DOWNLOAD_TIMEOUT)
        if r.status_code != 200 or "image" not in r.headers.get("content-type", ""):
            return None
        img = Image.open(io.BytesIO(r.content))
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            return bg
        return img.convert("RGB")
    except Exception:
        return None


# ── Process one food ──────────────────────────────────────────────────────────
def process_food(name: str, idx: int, total: int):
    slug = slugify(name)
    folder = IMAGES_DIR / slug

    # Skip if all images already exist
    if all((folder / f"img-{n:03d}.jpg").exists() for n in range(1, IMAGES_PER_FOOD + 1)):
        print(f"[{idx:3d}/{total}] {name:<42} skip", flush=True)
        return

    folder.mkdir(parents=True, exist_ok=True)

    print(f"[{idx:3d}/{total}] {name:<42}", end="", flush=True)

    search_term = f"{name} food dish"
    urls = search_images(search_term, CANDIDATE_URLS)
    saved = 0
    for url in urls:
        if saved >= IMAGES_PER_FOOD:
            break
        img = fetch_image(url)
        if img is None:
            continue
        slot = saved + 1
        dest = folder / f"img-{slot:03d}.jpg"
        img_resized = img.resize(DISPLAY_SIZE, Image.LANCZOS)
        img_resized.save(dest, "JPEG", quality=92)
        print(f" img-{slot:03d}", end="", flush=True)
        saved += 1

    if saved == 0:
        print(" *** no images ***", flush=True)
    else:
        print(f"  ({saved}/{IMAGES_PER_FOOD})", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def load_foods():
    try:
        from foods import FOODS
    except ImportError:
        sys.path.insert(0, str(SCRIPT_DIR))
        from foods import FOODS
    return FOODS


def main():
    args = sys.argv[1:]
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    all_foods = load_foods()

    if args:
        arg = args[0]
        if arg.isdigit():
            foods = all_foods[:int(arg)]
        else:
            needle = arg.lower()
            foods = [f for f in all_foods if needle in f.lower()]
            if not foods:
                print(f"No food matching '{arg}' found.")
                sys.exit(1)
    else:
        foods = all_foods

    print(f"FoodGuesser pipeline — {len(foods)} foods")
    print(f"  Output: {IMAGES_DIR}")
    print("-" * 60)

    for i, name in enumerate(foods, 1):
        process_food(name, i, len(foods))
        if i < len(foods):
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print("\nDone.")


if __name__ == "__main__":
    main()
