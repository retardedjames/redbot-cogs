#!/usr/bin/env python3
"""
download_images.py — populate artist image folders for ArtGuesser.

Fetches artwork images per artist via DuckDuckGo Images using each artist's
`image_search_term` from the database (e.g. "Rembrandt paintings" rather than
just the artist name, to avoid portraits of the artist).

Usage:
    python download_images.py              # all artists
    python download_images.py 50           # first N artists
    python download_images.py "Van Gogh"   # single artist by name (substring match)

Output path (default: local images/):
    images/{Artist Name}/img-001.jpg
    ...

To save directly to VPS nginx folder, set IMAGES_DIR env var or edit the
IMAGES_DIR constant below to /var/www/html/artimages/ (when running on VPS).

Re-runnable: folders with >= SKIP_THRESHOLD images are skipped.
"""

import io
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
import posixpath

import requests
from PIL import Image
import imagehash

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent

# Override with env var IMAGES_DIR (e.g. /var/www/html/artimages on VPS)
IMAGES_DIR = Path(os.environ.get("IMAGES_DIR", str(SCRIPT_DIR / "images")))

# ── Config ─────────────────────────────────────────────────────────────────────
IMAGES_PER_ARTIST  = 20       # target images per artist (fetch 3x as candidates)
SKIP_THRESHOLD     = 12       # skip folder if already has >= this many images
DELAY_BETWEEN      = 2        # seconds between artists
DOWNLOAD_WORKERS   = 8        # parallel downloads per artist
DOWNLOAD_TIMEOUT   = 20       # seconds per request
MIN_DIMENSION      = 300      # pixels — both width and height must meet this
MIN_FILE_BYTES     = 8_000
MAX_ASPECT_RATIO   = 4.0      # skip if w/h > 4 or h/w > 4
HASH_DISTANCE      = 10       # phash distance threshold for duplicate detection

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# URL substrings that indicate non-artwork (merch, icons, etc.)
SKIP_URL_FRAGMENTS = {
    "logo", "icon", "banner", "merch", "shop", "store",
    "tshirt", "tee", "mug", "poster-print",
    "redbubble", "teepublic", "zazzle", "amazon",
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
    """
    Returns list of (name, search_term) tuples from the ARTISTS dict.
    Falls back to "{name} paintings" if no image_search_term is set.
    """
    try:
        from artists import ARTISTS
    except ImportError:
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from artists import ARTISTS
        except ImportError:
            print("ERROR: artists.py not found or missing ARTISTS dict.")
            sys.exit(1)

    result = []
    for name, data in ARTISTS.items():
        search_term = data.get("image_search_term") or f"{name} paintings"
        result.append((name, search_term))
    return result


# ── DDGS session ───────────────────────────────────────────────────────────────
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
    path = urlparse(url).path
    _, ext = posixpath.splitext(path)
    ext = ext.lower().split("?")[0]
    if ext in (".jpeg", ".jpg"):
        return ".jpg"
    if ext in (".png", ".gif", ".webp"):
        return ext
    return ".jpg"


def url_is_blocked(url: str) -> bool:
    lower = url.lower()
    return any(frag in lower for frag in SKIP_URL_FRAGMENTS)


def search_images(search_term: str, count: int) -> list:
    for attempt in range(3):
        try:
            ddgs = _get_ddgs()
            results = list(ddgs.images(search_term, max_results=count * 3))
            urls = [r["image"] for r in results if r.get("image")]
            return urls[:count * 3]
        except Exception as exc:
            wait = (attempt + 1) * 5
            print(f"\n      [Search error attempt {attempt+1}] {search_term!r}: {exc} — retrying in {wait}s")
            time.sleep(wait)
    return []


def fetch_and_validate(url: str):
    """Download url, run quality checks. Returns (raw_bytes, pil_image) or None."""
    if url_is_blocked(url):
        return None
    try:
        r = requests.get(url, headers=HEADERS, timeout=DOWNLOAD_TIMEOUT, stream=True)
        if r.status_code != 200:
            return None
        content_type = r.headers.get("content-type", "")
        if "image" not in content_type:
            return None
        data = r.content
        if len(data) < MIN_FILE_BYTES:
            return None
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w < MIN_DIMENSION or h < MIN_DIMENSION:
            return None
        ratio = max(w, h) / min(w, h)
        if ratio > MAX_ASPECT_RATIO:
            return None
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        return data, img
    except Exception:
        return None


# ── Per-artist processor ───────────────────────────────────────────────────────
def process_artist(artist_name: str, search_term: str, idx: int, total: int) -> int:
    folder = IMAGES_DIR / artist_name
    count = existing_count(folder)

    if count >= SKIP_THRESHOLD:
        print(f"[{idx:3d}/{total}] {artist_name:<40} skip ({count} images present)")
        return count

    folder.mkdir(parents=True, exist_ok=True)
    print(f"[{idx:3d}/{total}] {artist_name:<40} searching: {search_term!r}", end="", flush=True)

    urls = search_images(search_term, IMAGES_PER_ARTIST)
    if not urls:
        print(" — no results")
        return 0

    print(f" | {len(urls)} URLs found, downloading...", end="", flush=True)

    save_lock = threading.Lock()
    saved_count = [0]
    seen_hashes: list = []

    def try_download(url: str) -> bool:
        with save_lock:
            if saved_count[0] >= IMAGES_PER_ARTIST:
                return False

        result = fetch_and_validate(url)
        if result is None:
            return False

        data, img = result

        try:
            ph = imagehash.phash(img)
        except Exception:
            return False

        with save_lock:
            if saved_count[0] >= IMAGES_PER_ARTIST:
                return False
            for existing_hash in seen_hashes:
                if abs(ph - existing_hash) < HASH_DISTANCE:
                    return False  # duplicate
            slot = saved_count[0] + 1
            saved_count[0] = slot
            seen_hashes.append(ph)

        ext = ext_from_url(url)
        dest = folder / f"img-{slot:03d}{ext}"
        try:
            dest.write_bytes(data)
            return True
        except Exception:
            with save_lock:
                saved_count[0] -= 1
                seen_hashes.remove(ph)
            return False

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        list(pool.map(try_download, urls))

    saved = saved_count[0]
    note = "  *** NO IMAGES ***" if saved == 0 else ""
    print(f" {saved} saved{note}")
    return saved


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

    print("ArtGuesser — image downloader (DuckDuckGo Images)")
    print(f"  Artists   : {len(artists)} (of {len(all_artists)} total)")
    print(f"  Output    : {IMAGES_DIR}")
    print(f"  Per artist: {IMAGES_PER_ARTIST} images (target)")
    print(f"  Skip if   : >= {SKIP_THRESHOLD} images already present")
    print(f"  Min size  : {MIN_DIMENSION}x{MIN_DIMENSION}px, {MIN_FILE_BYTES} bytes")
    print(f"  Hash dedup: phash distance < {HASH_DISTANCE}")
    print("  Note      : Uses image_search_term from artists.py for each artist")
    print("-" * 60)

    for i, (artist_name, search_term) in enumerate(artists, 1):
        process_artist(artist_name, search_term, i, len(artists))
        if i < len(artists):
            time.sleep(DELAY_BETWEEN)

    print("\nDone! Review images/<Artist>/ and delete any bad photos.")
    print(f"To deploy to VPS: rsync -avz images/ ubuntu@150.136.40.239:/var/www/html/artimages/")


if __name__ == "__main__":
    main()
