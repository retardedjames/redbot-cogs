#!/usr/bin/env python3
"""
download_images.py — populate artist image folders for ArtGuesser.

Strategy:
  1. Search DuckDuckGo for many candidate URLs per artist (using the
     artist's image_search_term from artists.py — e.g. "Rembrandt paintings"
     — to get artworks rather than portraits).
  2. Download all candidates in parallel (fast) while tracking each URL's
     original search-result position.
  3. Walk results in original search-rank order. Accept each image only if it
     is not too visually similar to any already-accepted image (perceptual hash
     comparison). The first result is preferred — DuckDuckGo's ranking is
     assumed to surface the best-quality copy of each artwork first.
  4. Stop once we have MAX_IMAGES. Save as img-001.jpg … img-NNN.jpg.

This means: when two images are near-duplicates (same artwork, different
source/crop/resolution), we always keep the earlier-ranked one and discard
the later.

Usage:
    python download_images.py              # all artists
    python download_images.py 50           # first N artists
    python download_images.py "Van Gogh"   # single artist (substring match)

Output path default: images/ next to this script.
Set IMAGES_DIR env var to override, e.g.:
    IMAGES_DIR=/var/www/html/artimages python download_images.py

Re-runnable: artists with >= SKIP_THRESHOLD images are skipped entirely.
"""

import io
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse
import posixpath

import requests
from PIL import Image
import imagehash

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
IMAGES_DIR = Path(os.environ.get("IMAGES_DIR", str(SCRIPT_DIR / "images")))

# ── Config ─────────────────────────────────────────────────────────────────────
MAX_IMAGES       = 18    # keep at most this many per artist
MIN_IMAGES       = 13    # skip artist folder if already has >= this many
SKIP_THRESHOLD   = MIN_IMAGES

CANDIDATES_MUL   = 5     # fetch MAX_IMAGES * this many candidate URLs
DELAY_BETWEEN    = 5     # seconds between artists (be polite to DDG)
DOWNLOAD_WORKERS = 10    # parallel download threads per artist
DOWNLOAD_TIMEOUT = 20    # seconds per HTTP request

MIN_DIMENSION    = 300   # both W and H must be >= this (pixels)
MIN_FILE_BYTES   = 8_000
MAX_ASPECT_RATIO = 4.0   # skip panoramic/icon-like images

# Perceptual hash dedup: phash distance scale —
#   0   = pixel-identical
#   1–5 = same image, different compression/tiny crop
#   6–10= same painting, different scan/photo quality
#   11+ = likely different artworks
# We reject a new image if it's within HASH_DISTANCE of any accepted image.
HASH_DISTANCE    = 10

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

SKIP_URL_FRAGMENTS = {
    "logo", "icon", "banner", "merch", "shop", "store",
    "tshirt", "tee", "mug", "poster-print",
    "redbubble", "teepublic", "zazzle", "amazon",
    "thumbnail", "thumb", "avatar",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── Artist list ────────────────────────────────────────────────────────────────
def load_artists() -> list:
    """Returns [(name, search_term), ...] from the ARTISTS dict in artists.py."""
    try:
        from artists import ARTISTS
    except ImportError:
        sys.path.insert(0, str(SCRIPT_DIR))
        try:
            from artists import ARTISTS
        except ImportError:
            print("ERROR: artists.py not found or missing ARTISTS dict.")
            sys.exit(1)

    return [
        (name, data.get("image_search_term") or f"{name} paintings")
        for name, data in ARTISTS.items()
    ]


# ── DDGS (shared, thread-safe) ─────────────────────────────────────────────────
_ddgs = None
_ddgs_lock = threading.Lock()


def _get_ddgs():
    global _ddgs
    with _ddgs_lock:
        if _ddgs is None:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            _ddgs = DDGS()
        return _ddgs


# ── Helpers ────────────────────────────────────────────────────────────────────
def existing_count(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def ext_from_url(url: str) -> str:
    _, ext = posixpath.splitext(urlparse(url).path)
    ext = ext.lower().split("?")[0]
    return ext if ext in (".png", ".gif", ".webp") else ".jpg"


def url_is_blocked(url: str) -> bool:
    low = url.lower()
    return any(frag in low for frag in SKIP_URL_FRAGMENTS)


def search_images(search_term: str, want: int) -> list:
    """Return up to `want` image URLs from DDG, retrying on error."""
    for attempt in range(3):
        try:
            results = list(_get_ddgs().images(search_term, max_results=want))
            return [r["image"] for r in results if r.get("image")][:want]
        except Exception as exc:
            wait = (attempt + 1) * 5
            print(f"\n  [DDG error #{attempt+1}] {exc!r} — waiting {wait}s", flush=True)
            time.sleep(wait)
    return []


def fetch_and_hash(url: str):
    """
    Download url and compute its perceptual hash.
    Returns (raw_bytes, phash_obj) on success, None on any failure.
    Applies quality filters: size, dimensions, aspect ratio, content-type.
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
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        ph = imagehash.phash(img)
        return data, ph
    except Exception:
        return None


# ── Core: process one artist ──────────────────────────────────────────────────
def process_artist(artist_name: str, search_term: str, idx: int, total: int) -> int:
    folder = IMAGES_DIR / artist_name
    existing = existing_count(folder)

    if existing >= SKIP_THRESHOLD:
        print(f"[{idx:3d}/{total}] {artist_name:<42} skip  ({existing} images)")
        return existing

    folder.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: search ───────────────────────────────────────────────────────
    want = MAX_IMAGES * CANDIDATES_MUL
    print(f"[{idx:3d}/{total}] {artist_name:<42} searching...", end="", flush=True)
    urls = search_images(search_term, want)
    if not urls:
        print(" no results")
        return 0
    print(f" {len(urls)} URLs | downloading...", end="", flush=True)

    # ── Phase 2: parallel download + hash ─────────────────────────────────────
    # We need original URL index to pick best (earliest = highest-ranked) copy
    # when duplicates appear, so store results keyed by index.
    downloaded: dict = {}   # {original_url_index: (raw_bytes, phash)}

    def _fetch(i_url):
        i, url = i_url
        result = fetch_and_hash(url)
        return i, result

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        futures = {pool.submit(_fetch, (i, u)): i for i, u in enumerate(urls)}
        for future in as_completed(futures):
            i, result = future.result()
            if result is not None:
                downloaded[i] = result

    print(f" {len(downloaded)} valid |", end="", flush=True)

    # ── Phase 3: deduplicate in original search-rank order ────────────────────
    # Walk from lowest index (best DDG rank) to highest. Accept an image only
    # if it is not too similar to any already-accepted image.
    accepted: list = []   # [(raw_bytes, phash), ...]

    for i in sorted(downloaded.keys()):
        if len(accepted) >= MAX_IMAGES:
            break
        data, ph = downloaded[i]
        if any(abs(ph - a_ph) <= HASH_DISTANCE for _, a_ph in accepted):
            continue    # near-duplicate of an already-accepted (higher-ranked) image
        accepted.append((data, ph))

    # ── Phase 4: save ─────────────────────────────────────────────────────────
    for slot, (data, _) in enumerate(accepted, 1):
        dest = folder / f"img-{slot:03d}.jpg"
        dest.write_bytes(data)

    kept = len(accepted)
    note = "  *** NONE ***" if kept == 0 else ""
    print(f" kept {kept}/{len(downloaded)}{note}")
    return kept


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    all_artists = load_artists()

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.isdigit():
            artists = all_artists[:int(arg)]
        else:
            needle = arg.lower()
            artists = [(n, s) for n, s in all_artists if needle in n.lower()]
            if not artists:
                print(f"No artist matching '{arg}' found.")
                sys.exit(1)
    else:
        artists = all_artists

    print("ArtGuesser — image downloader")
    print(f"  Artists      : {len(artists)} (of {len(all_artists)} total)")
    print(f"  Output       : {IMAGES_DIR}")
    print(f"  Target range : {MIN_IMAGES}–{MAX_IMAGES} images per artist")
    print(f"  Candidates   : up to {MAX_IMAGES * CANDIDATES_MUL} URLs fetched per artist")
    print(f"  Dedup        : phash distance ≤ {HASH_DISTANCE} → keep earliest-ranked copy")
    print(f"  Skip if      : folder already has ≥ {SKIP_THRESHOLD} images")
    print("-" * 68)

    for i, (name, term) in enumerate(artists, 1):
        process_artist(name, term, i, len(artists))
        if i < len(artists):
            time.sleep(DELAY_BETWEEN)

    print("\nDone.")
    if str(IMAGES_DIR) != str(SCRIPT_DIR / "images"):
        pass  # already writing to VPS path
    else:
        print(f"To sync to VPS: rsync -avz --progress images/ ubuntu@150.136.40.239:/var/www/html/artimages/")


if __name__ == "__main__":
    main()
