#!/usr/bin/env python3
"""
download_images.py — download and text-clean logo images for BrandGuesser.

Pipeline per brand:
  1. Search DuckDuckGo for "{brand_name} logo" (or custom search_term from brands.py).
  2. Download candidates in parallel; apply size/dimension/aspect filters.
  3. Deduplicate by perceptual hash — keep highest-ranked (best DDG rank) copy.
  4. For each accepted image:
       a. Composite transparent backgrounds onto white.
       b. Run EasyOCR to find all text regions.
       c. Decide which regions to remove:
            Tier 1 — text fuzzy-matches the brand name (≥65% via rapidfuzz)
            Tier 2 — URLs, ©, ®, ™, phone numbers, domain patterns
       d. SAFETY CHECK: if text-to-remove covers >30% of image area, skip removal
          entirely — the text IS the logo (e.g. ESPN, GE, Coca-Cola script).
       e. Fill removed regions: solid-color fill for flat backgrounds,
          cv2.inpaint (Navier-Stokes) for complex/photo backgrounds.
  5. Save cleaned image → images/{brand}/img-NNN.jpg
     Save raw original → images/{brand}/raw/img-NNN.jpg

Usage:
    python download_images.py              # all brands
    python download_images.py 50           # first N brands
    python download_images.py "McDonald"   # single brand (substring match)
    python download_images.py --no-clean "McDonald"  # skip OCR/text removal

Output: images/ next to this script (override with IMAGES_DIR env var).

Re-runnable: brands with >= SKIP_THRESHOLD processed images are skipped.

NOTE: First run downloads EasyOCR language models (~100 MB to ~/.EasyOCR/).
"""

import io
import os
import re
import sys
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse
import posixpath

import cv2
import numpy as np
import requests
from PIL import Image
import imagehash
from rapidfuzz import fuzz

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
IMAGES_DIR = Path(os.environ.get("IMAGES_DIR", str(SCRIPT_DIR / "images")))

# ── Config ─────────────────────────────────────────────────────────────────────
MAX_IMAGES        = 5     # target images per brand
SKIP_THRESHOLD    = 5     # skip brand if already has >= this many processed images
CANDIDATES_MUL    = 10    # fetch MAX_IMAGES * this many candidate URLs to ensure variety
DELAY_MIN         = 3     # jittered inter-brand delay (seconds)
DELAY_MAX         = 8
DDG_TIMEOUT       = 25
DOWNLOAD_WORKERS  = 10
DOWNLOAD_TIMEOUT  = 20

MIN_DIMENSION     = 250   # both W and H must be >= this (px)
MIN_FILE_BYTES    = 5_000
MAX_ASPECT_RATIO  = 3.5   # skip ultra-wide banners

# Perceptual hash dedup — logo variants look more alike than artworks,
# so use a slightly tighter threshold than artguesser.
HASH_DISTANCE     = 8

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# We WANT logo/icon images — minimal skip list vs artguesser.
# Only skip known paywall/watermark stock-photo sites.
SKIP_URL_FRAGMENTS = {
    "shutterstock", "gettyimages", "istockphoto", "alamy", "dreamstime",
}

# ── Text removal thresholds ────────────────────────────────────────────────────
FUZZY_MATCH_THRESHOLD  = 65    # % rapidfuzz partial_ratio → remove text
WORD_MATCH_THRESHOLD   = 70    # % for individual word matching
MIN_WORD_LENGTH        = 4     # ignore short words when word-matching
TEXT_AREA_LIMIT        = 0.30  # if removal mask > 30% of image, skip — text IS the logo
BG_VARIANCE_THRESHOLD  = 600   # pixel variance below this = "solid" background
INPAINT_RADIUS         = 9     # pixels for cv2.inpaint radius
BORDER_SAMPLE_PX       = 28    # px ring around text bbox used to sample bg color
EXPAND_FACTOR          = 1.18  # grow OCR bounding polygon by this factor from centroid

# Tier-2 junk text patterns to always remove (regardless of brand name match)
_JUNK_RE = re.compile(
    r'(www\.|\.com|\.net|\.org|\.io|©|®|™|#{0,1}\d{3,}|\d{3}[\-.\s]\d{3,4})',
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── Lazy OCR loader ────────────────────────────────────────────────────────────
_ocr_reader = None

def get_ocr():
    """Return (and lazily init) the shared EasyOCR reader."""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        print("  [OCR] Loading EasyOCR (first call may download models ~100 MB)...",
              end="", flush=True)
        _ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        print(" ready.", flush=True)
    return _ocr_reader


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
    for attempt in range(3):
        try:
            results = list(_new_ddgs().images(search_term, max_results=want))
            return [r["image"] for r in results if r.get("image")][:want]
        except Exception as exc:
            wait = (attempt + 1) * 5
            print(f"\n  [DDG error #{attempt+1}] {exc!r} — waiting {wait}s", flush=True)
            time.sleep(wait)
    return []


# ── Download helpers ───────────────────────────────────────────────────────────
def url_is_blocked(url: str) -> bool:
    low = url.lower()
    return any(frag in low for frag in SKIP_URL_FRAGMENTS)


def ext_from_url(url: str) -> str:
    _, ext = posixpath.splitext(urlparse(url).path)
    ext = ext.lower().split("?")[0]
    return ext if ext in (".png", ".gif", ".webp") else ".jpg"


def fetch_and_hash(url: str):
    """Download URL, apply quality filters, return (raw_bytes, phash) or None."""
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
        if img.mode not in ("RGB", "L", "RGBA"):
            img = img.convert("RGB")
        # Use RGB for hashing (ignore alpha)
        hash_img = img.convert("RGB") if img.mode == "RGBA" else img
        ph = imagehash.phash(hash_img)
        return data, ph
    except Exception:
        return None


def existing_count(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.iterdir()
               if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


# ── Text removal ───────────────────────────────────────────────────────────────
def _expand_polygon(pts: np.ndarray, factor: float) -> np.ndarray:
    """Scale polygon outward from its centroid by `factor`."""
    cx, cy = pts.mean(axis=0)
    return ((pts - [cx, cy]) * factor + [cx, cy]).astype(np.int32)


def remove_text(img_rgb: np.ndarray, brand_name: str) -> tuple:
    """
    Detect and remove text from a logo image.

    Returns (cleaned_array, was_modified: bool).
    If text covers >TEXT_AREA_LIMIT of the image, returns original + False
    (text IS the logo — do not destroy it).
    """
    h, w = img_rgb.shape[:2]
    total_pixels = h * w

    try:
        results = get_ocr().readtext(img_rgb, detail=1)
    except Exception as exc:
        print(f"\n  [OCR error] {exc}", flush=True)
        return img_rgb, False

    # Build removal mask
    mask = np.zeros((h, w), dtype=np.uint8)
    brand_lower = brand_name.lower()
    brand_words = [w for w in brand_lower.split() if len(w) >= MIN_WORD_LENGTH]

    for (bbox, text, conf) in results:
        if conf < 0.25 or not text.strip():
            continue

        text_clean = text.strip()
        text_lower = text_clean.lower()
        should_remove = False

        # Tier 1a: fuzzy partial match against full brand name
        if fuzz.partial_ratio(text_lower, brand_lower) >= FUZZY_MATCH_THRESHOLD:
            should_remove = True

        # Tier 1b: word-level match (catches partial brand names, e.g. "McDonald" alone)
        if not should_remove:
            for word in brand_words:
                if fuzz.ratio(text_lower, word) >= WORD_MATCH_THRESHOLD:
                    should_remove = True
                    break

        # Tier 2: junk text patterns
        if not should_remove and _JUNK_RE.search(text_clean):
            should_remove = True

        if should_remove:
            pts = np.array([[int(p[0]), int(p[1])] for p in bbox], dtype=np.float32)
            expanded = _expand_polygon(pts, EXPAND_FACTOR)
            # Clip to image bounds
            expanded[:, 0] = np.clip(expanded[:, 0], 0, w - 1)
            expanded[:, 1] = np.clip(expanded[:, 1], 0, h - 1)
            cv2.fillPoly(mask, [expanded], 255)

    # Safety check: if we'd erase >TEXT_AREA_LIMIT of the image,
    # the "text" is the logo itself — leave it untouched.
    mask_coverage = mask.sum() / 255 / total_pixels
    if mask_coverage > TEXT_AREA_LIMIT:
        return img_rgb, False

    if mask.sum() == 0:
        return img_rgb, False

    # Dilate mask slightly so we fully cover anti-aliased text edges
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.dilate(mask, kernel, iterations=2)

    # Sample background color from the border ring around masked regions
    border_kernel = np.ones(
        (BORDER_SAMPLE_PX * 2 + 1, BORDER_SAMPLE_PX * 2 + 1), np.uint8
    )
    dilated_for_sample = cv2.dilate(mask, border_kernel)
    border_zone = cv2.bitwise_and(dilated_for_sample, cv2.bitwise_not(mask))
    bg_pixels = img_rgb[border_zone > 0]

    if len(bg_pixels) >= 10:
        variance = float(np.var(bg_pixels))
        if variance < BG_VARIANCE_THRESHOLD:
            # Solid/near-solid background — fill with median color
            fill_color = np.median(bg_pixels, axis=0).astype(np.uint8)
            result = img_rgb.copy()
            result[mask > 0] = fill_color
            return result, True

    # Complex/photo background — use Navier-Stokes inpainting
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    result_bgr = cv2.inpaint(img_bgr, mask, INPAINT_RADIUS, cv2.INPAINT_NS)
    return cv2.cvtColor(result_bgr, cv2.COLOR_BGR2RGB), True


# ── Core: process one brand ────────────────────────────────────────────────────
def process_brand(
    brand_name: str,
    search_term: str,
    idx: int,
    total: int,
    do_clean: bool = True,
) -> int:
    folder = IMAGES_DIR / brand_name
    raw_folder = folder / "raw"

    existing = existing_count(folder)
    if existing >= SKIP_THRESHOLD:
        print(f"[{idx:3d}/{total}] {brand_name:<42} skip  ({existing} images)")
        return existing

    folder.mkdir(parents=True, exist_ok=True)
    raw_folder.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: search ───────────────────────────────────────────────────────
    want = MAX_IMAGES * CANDIDATES_MUL
    print(f"[{idx:3d}/{total}] {brand_name:<42} searching '{search_term}'...",
          end="", flush=True)
    urls = search_images(search_term, want)
    if not urls:
        print(" no results")
        return 0
    print(f" {len(urls)} URLs | downloading...", end="", flush=True)

    # ── Phase 2: parallel download + hash ─────────────────────────────────────
    downloaded: dict = {}

    def _fetch(i_url):
        i, url = i_url
        return i, fetch_and_hash(url)

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        futures = {pool.submit(_fetch, (i, u)): i for i, u in enumerate(urls)}
        for future in as_completed(futures):
            i, result = future.result()
            if result is not None:
                downloaded[i] = result

    print(f" {len(downloaded)} valid |", end="", flush=True)

    # ── Phase 3: deduplicate in original search-rank order ────────────────────
    accepted: list = []
    for i in sorted(downloaded.keys()):
        if len(accepted) >= MAX_IMAGES:
            break
        data, ph = downloaded[i]
        if any(abs(ph - a_ph) <= HASH_DISTANCE for _, a_ph in accepted):
            continue
        accepted.append((data, ph))

    # ── Phase 4: determine next available slot numbers ─────────────────────────
    existing_slots = {
        int(p.stem.split("-")[1])
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and p.stem.startswith("img-")
    }
    slot = 1

    # ── Phase 5: text clean + save ─────────────────────────────────────────────
    saved = 0
    for data, _ in accepted:
        while slot in existing_slots:
            slot += 1

        # Save raw original
        raw_path = raw_folder / f"img-{slot:03d}.jpg"
        raw_path.write_bytes(data)

        try:
            img = Image.open(io.BytesIO(data))

            # Composite RGBA onto white background
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            if do_clean:
                img_arr = np.array(img)
                cleaned_arr, modified = remove_text(img_arr, brand_name)
                cleaned_img = Image.fromarray(cleaned_arr)
                status_char = "~" if modified else "."
            else:
                cleaned_img = img
                status_char = "-"

            dest = folder / f"img-{slot:03d}.jpg"
            cleaned_img.save(dest, "JPEG", quality=92)
            saved += 1
            existing_slots.add(slot)
            print(status_char, end="", flush=True)
            slot += 1

        except Exception as exc:
            print(f"\n  [save error slot {slot}] {exc}", flush=True)

    note = "  *** NONE ***" if saved == 0 else ""
    print(f"  kept {saved}/{len(downloaded)}{note}")
    return saved


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    global _ocr_reader

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    do_clean = "--no-clean" not in flags

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

    print("BrandGuesser — image downloader")
    print(f"  Brands       : {len(brands)} (of {len(all_brands)} total)")
    print(f"  Output       : {IMAGES_DIR}")
    print(f"  Target       : {MAX_IMAGES} images per brand")
    print(f"  Candidates   : up to {MAX_IMAGES * CANDIDATES_MUL} URLs per brand")
    print(f"  Dedup        : phash distance ≤ {HASH_DISTANCE}")
    print(f"  Skip if      : folder already has ≥ {SKIP_THRESHOLD} images")
    print(f"  Text removal : {'ON' if do_clean else 'OFF (--no-clean)'}")
    if do_clean:
        print(f"    Fuzzy threshold : ≥{FUZZY_MATCH_THRESHOLD}% match → remove")
        print(f"    Area safety cap : >{TEXT_AREA_LIMIT*100:.0f}% of image → keep "
              f"(text IS the logo)")
    print(f"  DDG delay    : {DELAY_MIN}–{DELAY_MAX}s jittered between brands")
    print("-" * 68)

    for i, (name, term) in enumerate(brands, 1):
        process_brand(name, term, i, len(brands), do_clean=do_clean)
        if i < len(brands):
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    print("\nDone.")


if __name__ == "__main__":
    main()
