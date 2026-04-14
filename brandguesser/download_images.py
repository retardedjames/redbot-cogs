#!/usr/bin/env python3
"""
download_images.py — download logo images for BrandGuesser.

For each brand:
  1. Search DuckDuckGo for logos (transparent/clipart filters first, then general).
  2. Download candidates in parallel; apply size/dimension/aspect filters.
  3. Score each candidate for "logo on solid background" quality.
  4. Reject photographs and complex multi-logo collages.
  5. Deduplicate by perceptual hash.
  6. Keep the top 3 highest-scoring images.

Scoring prioritizes:
  - Solid / uniform background (white, light, or single color)
  - Square-ish dimensions (close to 1:1 aspect ratio)
  - Simple color palette (few distinct colors)
  - No photographic detail everywhere (texture = photo penalty)
  - Transparent-source bonus (PNG with alpha = clean logo)

Usage:
    python download_images.py              # all brands
    python download_images.py 5            # first N brands
    python download_images.py "McDonald"   # single brand (substring match)

Output: images/ next to this script (override with IMAGES_DIR env var).
Re-runnable: brands with >= SKIP_THRESHOLD processed images are skipped.
"""

import io
import os
import sys
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import requests
from PIL import Image
import imagehash

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
IMAGES_DIR = Path(os.environ.get("IMAGES_DIR", str(SCRIPT_DIR / "images")))

# ── Config ─────────────────────────────────────────────────────────────────────
MAX_IMAGES        = 3      # images to keep per brand
SKIP_THRESHOLD    = 3      # skip brand if already has >= this many images
CANDIDATES_MUL    = 15     # fetch MAX_IMAGES * this many candidate URLs
DELAY_MIN         = 3      # jittered inter-brand delay (seconds)
DELAY_MAX         = 8
DDG_TIMEOUT       = 25
DOWNLOAD_WORKERS  = 10
DOWNLOAD_TIMEOUT  = 20

MIN_DIMENSION     = 200    # both W and H must be >= this (px)
MIN_FILE_BYTES    = 4_000
MAX_ASPECT_RATIO  = 2.5    # skip wide banners (tighter than before)

# Perceptual hash dedup
HASH_DISTANCE     = 8

# Logo quality thresholds
PHOTO_REJECT_SCORE = -10   # images scoring below this are rejected as photos/bad

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

SKIP_URL_FRAGMENTS = {
    "shutterstock", "gettyimages", "istockphoto", "alamy", "dreamstime",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── Brand list ─────────────────────────────────────────────────────────────────
def load_brands() -> list:
    """Returns [(name, search_term), ...] from brands.py."""
    try:
        from brands import BRANDS
    except ImportError:
        sys.path.insert(0, str(SCRIPT_DIR))
        from brands import BRANDS

    pairs = []
    for name, data in BRANDS.items():
        term = data.get("search_term") or f"{name} logo"
        pairs.append((name, term))
    return pairs


# ── DDG helpers ────────────────────────────────────────────────────────────────
def _new_ddgs():
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    return DDGS(timeout=DDG_TIMEOUT)


def search_images(search_term: str, want: int) -> list:
    """
    Search DDG with transparent/clipart filters first, then fall back to general.
    Returns a deduplicated list of up to `want` image URLs.
    """
    urls_seen = set()
    urls = []

    def _fetch(term, type_image=None, max_results=None):
        for attempt in range(3):
            try:
                kwargs = {"max_results": max_results or want}
                if type_image:
                    kwargs["type_image"] = type_image
                results = list(_new_ddgs().images(term, **kwargs))
                return [r["image"] for r in results if r.get("image")]
            except Exception as exc:
                wait = (attempt + 1) * 5
                print(f"\n  [DDG error #{attempt+1}] {exc!r} — waiting {wait}s", flush=True)
                time.sleep(wait)
        return []

    # Pass 1: transparent PNGs (best for logos)
    for url in _fetch(search_term, type_image="transparent", max_results=want):
        if url not in urls_seen:
            urls_seen.add(url)
            urls.append(url)

    # Pass 2: clipart type
    if len(urls) < want:
        for url in _fetch(search_term, type_image="clipart", max_results=want):
            if url not in urls_seen:
                urls_seen.add(url)
                urls.append(url)

    # Pass 3: general (no filter) — more candidates
    if len(urls) < want:
        for url in _fetch(search_term, max_results=want * 2):
            if url not in urls_seen:
                urls_seen.add(url)
                urls.append(url)

    return urls[:want]


# ── Download helpers ───────────────────────────────────────────────────────────
def url_is_blocked(url: str) -> bool:
    low = url.lower()
    return any(frag in low for frag in SKIP_URL_FRAGMENTS)


def fetch_image(url: str):
    """
    Download URL, apply basic quality filters.
    Returns (pil_image, had_alpha: bool) or None.
    """
    if url_is_blocked(url):
        return None
    try:
        r = requests.get(url, headers=HEADERS, timeout=DOWNLOAD_TIMEOUT, stream=True)
        if r.status_code != 200:
            return None
        if "image" not in r.headers.get("content-type", ""):
            return None
        data = r.content
        if len(data) < MIN_FILE_BYTES:
            return None
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w < MIN_DIMENSION or h < MIN_DIMENSION:
            return None
        if max(w, h) / min(w, h) > MAX_ASPECT_RATIO:
            return None
        had_alpha = img.mode == "RGBA"
        return img, had_alpha
    except Exception:
        return None


# ── Logo quality scoring ───────────────────────────────────────────────────────
def score_logo(img: Image.Image, had_alpha: bool) -> float:
    """
    Score an image for logo-on-solid-background quality.
    Higher = better candidate. Below PHOTO_REJECT_SCORE = reject.

    Scoring components:
      +25   squareness (aspect ratio close to 1:1)
      +35   solid/uniform border (likely plain background)
      +15   simple color palette (few distinct colors)
      +10   large light/white region (transparent-origin logo)
      +10   was RGBA with transparency (clean logo source)
      -40   photographic detail everywhere (all tiles high-variance)
      -20   high overall unique-color count (photo-like)
    """
    img_rgb = img.convert("RGB")
    w, h = img_rgb.size
    arr = np.array(img_rgb, dtype=np.float32)

    score = 0.0

    # 1. Squareness bonus
    squareness = min(w, h) / max(w, h)
    score += squareness * 25

    # 2. Solid background: check border ring uniformity
    bw = max(2, min(w, h) // 10)
    edges = np.concatenate([
        arr[:bw, :].reshape(-1, 3),
        arr[-bw:, :].reshape(-1, 3),
        arr[:, :bw].reshape(-1, 3),
        arr[:, -bw:].reshape(-1, 3),
    ])
    median_edge = np.median(edges, axis=0)
    edge_diffs = np.abs(edges - median_edge).sum(axis=1)
    solid_frac = float((edge_diffs < 30).mean())
    score += solid_frac * 35

    # 3. Color palette simplicity
    try:
        small = img_rgb.resize((64, 64), Image.LANCZOS)
        quantized = small.quantize(colors=24, method=Image.Quantize.FASTOCTREE)
        palette_size = len(quantized.getcolors() or [])
        score += max(0, 1 - palette_size / 24) * 15
    except Exception:
        pass

    # 4. White/light area bonus (transparent logos composite to white)
    light_mask = (arr[:, :, 0] > 238) & (arr[:, :, 1] > 238) & (arr[:, :, 2] > 238)
    light_frac = float(light_mask.mean())
    if light_frac > 0.35:
        score += 10

    # 5. Was originally transparent PNG (likely a clean vector/logo)
    if had_alpha:
        score += 10

    # 6. Photo penalty: if ~all 4x4 grid tiles have high local variance → photo
    gray = np.array(img_rgb.convert("L"), dtype=np.float32)
    tile_h, tile_w = max(1, h // 4), max(1, w // 4)
    high_var_count = 0
    total_tiles = 0
    for ti in range(4):
        for tj in range(4):
            tile = gray[ti * tile_h:(ti + 1) * tile_h, tj * tile_w:(tj + 1) * tile_w]
            if tile.size > 0:
                total_tiles += 1
                if np.var(tile) > 300:
                    high_var_count += 1
    if total_tiles > 0 and (high_var_count / total_tiles) > 0.80:
        score -= 40  # strong photo penalty

    # 7. High unique-color count penalty (photos have hundreds of unique quantized colors)
    small_arr = np.array(img_rgb.resize((64, 64)).convert("P"))
    unique_colors = len(np.unique(small_arr))
    if unique_colors > 200:
        score -= 20

    return score


def existing_count(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.iterdir()
               if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


# ── Core: process one brand ────────────────────────────────────────────────────
def process_brand(
    brand_name: str,
    search_term: str,
    idx: int,
    total: int,
) -> int:
    folder = IMAGES_DIR / brand_name

    existing = existing_count(folder)
    if existing >= SKIP_THRESHOLD:
        print(f"[{idx:3d}/{total}] {brand_name:<42} skip  ({existing} images)")
        return existing

    folder.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: search ───────────────────────────────────────────────────────
    want = MAX_IMAGES * CANDIDATES_MUL
    print(f"[{idx:3d}/{total}] {brand_name:<42} searching...", end="", flush=True)
    urls = search_images(search_term, want)
    if not urls:
        print(" no results")
        return 0
    print(f" {len(urls)} URLs | downloading...", end="", flush=True)

    # ── Phase 2: parallel download ────────────────────────────────────────────
    downloaded: dict = {}

    def _fetch(i_url):
        i, url = i_url
        return i, fetch_image(url)

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        futures = {pool.submit(_fetch, (i, u)): i for i, u in enumerate(urls)}
        for future in as_completed(futures):
            i, result = future.result()
            if result is not None:
                downloaded[i] = result

    print(f" {len(downloaded)} valid |", end="", flush=True)

    if not downloaded:
        print("  *** NONE ***")
        return 0

    # ── Phase 3: score and sort (best first) ─────────────────────────────────
    scored: list = []
    for i, (img, had_alpha) in downloaded.items():
        s = score_logo(img, had_alpha)
        scored.append((s, i, img, had_alpha))
    scored.sort(key=lambda x: -x[0])  # highest score first

    # ── Phase 4: deduplicate (phash) picking best-scored first ────────────────
    accepted: list = []
    seen_hashes: list = []
    for s, i, img, had_alpha in scored:
        if s < PHOTO_REJECT_SCORE:
            continue  # skip photos / low-quality
        if len(accepted) >= MAX_IMAGES:
            break
        try:
            rgb_img = img.convert("RGB")
            ph = imagehash.phash(rgb_img)
        except Exception:
            continue
        if any(abs(ph - h) <= HASH_DISTANCE for h in seen_hashes):
            continue
        seen_hashes.append(ph)
        accepted.append((s, img, had_alpha))

    if not accepted:
        print("  *** all rejected (photo/low-quality) ***")
        return 0

    # ── Phase 5: convert and save ─────────────────────────────────────────────
    existing_slots = {
        int(p.stem.split("-")[1])
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and p.stem.startswith("img-")
    }
    slot = 1
    saved = 0

    for _, img, had_alpha in accepted:
        while slot in existing_slots:
            slot += 1

        try:
            # Composite onto white (handles RGBA)
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            dest = folder / f"img-{slot:03d}.jpg"
            img.save(dest, "JPEG", quality=92)
            saved += 1
            existing_slots.add(slot)
            slot += 1

        except Exception as exc:
            print(f"\n  [save error slot {slot}] {exc}", flush=True)

    note = "  *** NONE ***" if saved == 0 else ""
    print(f"  kept {saved}/{len(downloaded)} (scored+deduped){note}")
    return saved


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    all_brands = load_brands()

    if args:
        arg = args[0]
        if arg.isdigit():
            brands = all_brands[: int(arg)]
        else:
            needle = arg.lower()
            brands = [(n, s) for n, s in all_brands if needle in n.lower()]
            if not brands:
                print(f"No brand matching '{arg}' found.")
                sys.exit(1)
    else:
        brands = all_brands

    print("BrandGuesser — image downloader (logo-quality filter)")
    print(f"  Brands       : {len(brands)} (of {len(all_brands)} total)")
    print(f"  Output       : {IMAGES_DIR}")
    print(f"  Target       : {MAX_IMAGES} images per brand")
    print(f"  Candidates   : up to {MAX_IMAGES * CANDIDATES_MUL} URLs per brand")
    print(f"  Dedup        : phash distance ≤ {HASH_DISTANCE}")
    print(f"  Skip if      : folder already has ≥ {SKIP_THRESHOLD} images")
    print(f"  Search order : transparent → clipart → general")
    print("-" * 68)

    for i, (name, term) in enumerate(brands, 1):
        process_brand(name, term, i, len(brands))
        if i < len(brands):
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print("\nDone.")


if __name__ == "__main__":
    main()
