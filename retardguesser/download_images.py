#!/usr/bin/env python3
"""
download_images.py — populate images/ for RetardGuesser.

Fetches photos of people via DuckDuckGo Images with duplicate
detection (perceptual hash), quality filtering, and parallel downloads.

Usage:
    python download_images.py              # all people
    python download_images.py 50           # first N people
    python download_images.py "Einstein"   # single person by name (substring match)

Images are saved to:
    images/{Person Name}/img-001.jpg
    images/{Person Name}/img-002.jpg
    ...

Re-runnable: folders with >= SKIP_THRESHOLD images are skipped.
"""

import io
import re
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
IMAGES_DIR = SCRIPT_DIR / "images"
LIST_FILE  = SCRIPT_DIR / "list.txt"

# ── Config ─────────────────────────────────────────────────────────────────────
IMAGES_PER_PERSON  = 6        # target images per person
SKIP_THRESHOLD     = 4        # skip folder if already has >= this many images
DELAY_BETWEEN      = 2        # seconds between people
DOWNLOAD_WORKERS   = 6        # parallel downloads per person
DOWNLOAD_TIMEOUT   = 20       # seconds per request
MIN_DIMENSION      = 150      # pixels — both width and height must meet this
MIN_FILE_BYTES     = 5_000
MAX_ASPECT_RATIO   = 3.0      # skip if w/h > 3 or h/w > 3
HASH_DISTANCE      = 10       # phash distance threshold for duplicate detection

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── Person list ────────────────────────────────────────────────────────────────
def load_people() -> list[str]:
    if not LIST_FILE.exists():
        print(f"ERROR: {LIST_FILE} not found.")
        sys.exit(1)

    names = []
    for line in LIST_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip markdown/formatting artifacts
        if line.startswith(("*", "#", "`", "-", "\\", "!", "|")):
            continue
        if "**" in line or line == "--":
            continue
        # Must start with an uppercase letter (all real names do; junk lines don't)
        if not line[0].isupper():
            continue
        names.append(line)
    return names


def safe_folder_name(name: str) -> str:
    """Sanitize a name for use as a filesystem folder name."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip(". ")
    return name or "unknown"


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


def search_images(person: str, count: int) -> list[str]:
    query = f"{person} photo portrait"
    for attempt in range(3):
        try:
            ddgs = _get_ddgs()
            results = list(ddgs.images(query, max_results=count * 4))
            urls = [r["image"] for r in results if r.get("image")]
            return urls[: count * 4]
        except Exception as exc:
            wait = (attempt + 1) * 5
            print(
                f"\n      [Search error attempt {attempt+1}] {person}: {exc} — retrying in {wait}s"
            )
            time.sleep(wait)
    return []


def fetch_and_validate(url: str) -> "tuple[bytes, Image.Image] | None":
    """Download url, run quality checks. Returns (raw_bytes, pil_image) or None."""
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


# ── Per-person processor ───────────────────────────────────────────────────────
def process_person(person: str, idx: int, total: int) -> int:
    folder_name = safe_folder_name(person)
    folder = IMAGES_DIR / folder_name
    count = existing_count(folder)

    if count >= SKIP_THRESHOLD:
        print(f"[{idx:3d}/{total}] {person:<45} skip ({count} images present)")
        return count

    folder.mkdir(parents=True, exist_ok=True)
    print(f"[{idx:3d}/{total}] {person:<45} searching...", end="", flush=True)

    urls = search_images(person, IMAGES_PER_PERSON)
    if not urls:
        print(" no results")
        return 0

    print(f" found {len(urls)} URLs, downloading...", end="", flush=True)

    save_lock = threading.Lock()
    saved_count = [0]
    seen_hashes: list = []

    def try_download(url: str) -> bool:
        with save_lock:
            if saved_count[0] >= IMAGES_PER_PERSON:
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
            if saved_count[0] >= IMAGES_PER_PERSON:
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
    IMAGES_DIR.mkdir(exist_ok=True)
    PEOPLE = load_people()

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.isdigit():
            people = PEOPLE[: int(arg)]
        else:
            needle = arg.lower()
            people = [p for p in PEOPLE if needle in p.lower()]
            if not people:
                print(f"No person matching '{arg}' found.")
                sys.exit(1)
    else:
        people = PEOPLE

    print("RetardGuesser — image downloader (DuckDuckGo Images)")
    print(f"  People    : {len(people)} (of {len(PEOPLE)} total)")
    print(f"  Output    : {IMAGES_DIR}")
    print(f"  Per person: {IMAGES_PER_PERSON} images (target)")
    print(f"  Skip if   : >= {SKIP_THRESHOLD} images already present")
    print(f"  Min size  : {MIN_DIMENSION}x{MIN_DIMENSION}px, {MIN_FILE_BYTES} bytes")
    print(f"  Hash dedup: phash distance < {HASH_DISTANCE}")
    print("-" * 60)

    for i, person in enumerate(people, 1):
        process_person(person, i, len(people))
        if i < len(people):
            time.sleep(DELAY_BETWEEN)

    print("\nDone! Review images/<Person>/ and delete any bad photos.")


if __name__ == "__main__":
    main()
