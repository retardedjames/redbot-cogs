#!/usr/bin/env python3
"""
download_images.py — one-time script to populate images/ for AnimalGuesser.

Usage:
    cd animalguesser
    python download_images.py

Sources per animal:
  - Wikipedia article images      →  wiki-001.jpg,    wiki-002.jpg,    ...
  - Wikimedia Commons search      →  commons-001.jpg, commons-002.jpg, ...
  - iNaturalist research-grade    →  in-001.jpg,      in-002.jpg,      ...

Re-runnable: animals whose folder already has >= SKIP_THRESHOLD images are skipped.
After the run, browse images/<Animal Name>/ and delete any bad/inaccurate photos.
Prefixes make mass-deletion easy: del commons-* to nuke all Commons photos, etc.
"""

import asyncio
import posixpath
import random
import sys
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
IMAGES_DIR = SCRIPT_DIR / "images"

sys.path.insert(0, str(SCRIPT_DIR))
from animalguesser import ANIMALS  # noqa: E402

# ── Config ─────────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "AnimalGuesserBot/1.0 (Educational Discord Bot; "
        "github.com/jamescvermont-cyber/redbot-cogs)"
    )
}
MIN_WIKI_BYTES = 30_000   # skip Wikipedia images smaller than ~30 KB (likely icons)
INAT_PER_ANIMAL = 10      # iNaturalist images to fetch per animal
COMMONS_PER_ANIMAL = 6    # Wikimedia Commons search images per animal
SKIP_THRESHOLD = 5        # skip animal folder if it already has this many images
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# ── Wikipedia filename noise filter ───────────────────────────────────────────
_SKIP_PATTERNS = frozenset([
    "map", "range", "distribut", "flag", "logo", "icon", "symbol",
    "coat_of", "clade", "taxon", "skeleton", "skull", "diagram",
    "stamp", "coin", "commons-logo", "wiktionary", "wikisource",
    "template", "ambox", "portal", "question_mark",
    "graph", "chart", "phylo", "vector", "wikispecies",
    "blank", "border", "arrow", "button", "star_", "_star",
])


def _is_wiki_photo(title: str, mime: str, size: int) -> bool:
    """Return True if this Wikipedia file looks like a real animal photo."""
    if mime not in ("image/jpeg", "image/png"):
        return False
    if size < MIN_WIKI_BYTES:
        return False
    t = title.lower()
    return not any(kw in t for kw in _SKIP_PATTERNS)


def _url_ext(url: str) -> str:
    """Derive a normalised file extension from a URL."""
    _, ext = posixpath.splitext(urlparse(url).path)
    ext = ext.lower()
    if ext in (".jpg", ".jpeg"):
        return ".jpg"
    if ext == ".png":
        return ".png"
    return ".jpg"


def _wiki_thumb_to_original(url: str) -> str:
    """Convert a Wikipedia /thumb/ CDN URL to the original full-size URL.

    e.g. .../thumb/7/73/Lion.jpg/1200px-Lion.jpg  →  .../7/73/Lion.jpg
    """
    if "/thumb/" not in url:
        return url
    left, right = url.split("/thumb/", 1)
    path_no_size = right.rsplit("/", 1)[0]
    return f"{left}/{path_no_size}"


# ── Fetchers ───────────────────────────────────────────────────────────────────

async def fetch_wikipedia_urls(session: aiohttp.ClientSession, animal: str) -> list[str]:
    """Return photo URLs scraped from the animal's Wikipedia article."""
    urls: list[str] = []
    base = {"format": "json", "action": "query", "titles": animal}

    try:
        # 1. Main article lead image (reliable — always the actual animal)
        async with session.get(
            "https://en.wikipedia.org/w/api.php",
            params={**base, "prop": "pageimages", "pithumbsize": "1200"},
        ) as r:
            data = await r.json()
        for page in data.get("query", {}).get("pages", {}).values():
            src = page.get("thumbnail", {}).get("source", "")
            if src:
                url = _wiki_thumb_to_original(src)
                if url not in urls:
                    urls.append(url)

        await asyncio.sleep(0.25)

        # 2. All images transcluded in the article (more variety, needs filtering)
        async with session.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                **base,
                "generator": "images",
                "prop": "imageinfo",
                "iiprop": "url|mime|size",
                "gimlimit": "50",
            },
        ) as r:
            data = await r.json()
        for page in data.get("query", {}).get("pages", {}).values():
            title = page.get("title", "")
            for ii in page.get("imageinfo", []):
                url = _wiki_thumb_to_original(ii.get("url", ""))
                mime = ii.get("mime", "")
                size = ii.get("size", 0)
                if url and _is_wiki_photo(title, mime, size) and url not in urls:
                    urls.append(url)

    except Exception as exc:
        print(f"      [Wikipedia error] {animal}: {exc}")

    return urls


async def fetch_commons_urls(
    session: aiohttp.ClientSession,
    animal: str,
    count: int = COMMONS_PER_ANIMAL,
) -> list[str]:
    """Return photo URLs from a direct Wikimedia Commons full-text search.

    Unlike fetch_wikipedia_urls (which only finds images transcluded in one
    article), this searches the entire Commons File: namespace and can return
    dozens of additional photos per species.
    """
    urls: list[str] = []
    try:
        async with session.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrnamespace": "6",       # File: namespace
                "gsrsearch": animal,
                "gsrlimit": str(count * 4),  # fetch extra to allow for filtering
                "prop": "imageinfo",
                "iiprop": "url|mime|size",
                "format": "json",
            },
        ) as r:
            data = await r.json()
        for page in data.get("query", {}).get("pages", {}).values():
            title = page.get("title", "")
            for ii in page.get("imageinfo", []):
                url = _wiki_thumb_to_original(ii.get("url", ""))
                mime = ii.get("mime", "")
                size = ii.get("size", 0)
                if url and _is_wiki_photo(title, mime, size) and url not in urls:
                    urls.append(url)
    except Exception as exc:
        print(f"      [Commons error] {animal}: {exc}")

    return urls[:count]


async def fetch_inaturalist_urls(
    session: aiohttp.ClientSession,
    animal: str,
    count: int = INAT_PER_ANIMAL,
) -> list[str]:
    """Return up to *count* research-grade iNaturalist photo URLs."""
    try:
        async with session.get(
            "https://api.inaturalist.org/v1/taxa",
            params={"q": animal, "per_page": 1},
        ) as r:
            data = await r.json()
        results = data.get("results", [])
        if not results:
            return []
        taxon_id = results[0]["id"]

        await asyncio.sleep(1.2)  # be courteous to iNaturalist

        async with session.get(
            "https://api.inaturalist.org/v1/observations",
            params={
                "taxon_id": taxon_id,
                "photos": "true",
                "per_page": count * 3,
                "order_by": "votes",
                "quality_grade": "research",
            },
        ) as r:
            data = await r.json()

        photos: list[str] = []
        for obs in data.get("results", []):
            for p in obs.get("photos", []):
                url = p.get("url", "").replace("square", "medium")
                if url.startswith("http") and url not in photos:
                    photos.append(url)

        random.shuffle(photos)
        return photos[:count]

    except Exception as exc:
        print(f"      [iNaturalist error] {animal}: {exc}")
        return []


async def download_file(session: aiohttp.ClientSession, url: str, dest: Path) -> bool:
    """Download *url* to *dest*. Returns True on success."""
    if dest.exists():
        return True  # already downloaded
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status == 200:
                data = await r.read()
                if len(data) > 5_000:  # skip suspiciously tiny responses
                    dest.write_bytes(data)
                    return True
    except Exception:
        pass
    return False


# ── Per-animal orchestration ───────────────────────────────────────────────────

async def process_animal(
    session: aiohttp.ClientSession,
    animal: str,
    idx: int,
    total: int,
) -> None:
    folder = IMAGES_DIR / animal
    folder.mkdir(parents=True, exist_ok=True)

    # Skip if already populated
    existing = [p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS]
    if len(existing) >= SKIP_THRESHOLD:
        print(f"[{idx:3d}/{total}] {animal:<32} skip ({len(existing)} images present)")
        return

    wiki_urls = await fetch_wikipedia_urls(session, animal)
    await asyncio.sleep(0.25)
    commons_urls = await fetch_commons_urls(session, animal)
    inat_urls = await fetch_inaturalist_urls(session, animal)
    await asyncio.sleep(1.0)

    wiki_saved = 0
    for i, url in enumerate(wiki_urls, 1):
        dest = folder / f"wiki-{i:03d}{_url_ext(url)}"
        if await download_file(session, url, dest):
            wiki_saved += 1

    commons_saved = 0
    for i, url in enumerate(commons_urls, 1):
        dest = folder / f"commons-{i:03d}{_url_ext(url)}"
        if await download_file(session, url, dest):
            commons_saved += 1

    inat_saved = 0
    for i, url in enumerate(inat_urls, 1):
        dest = folder / f"in-{i:03d}{_url_ext(url)}"
        if await download_file(session, url, dest):
            inat_saved += 1

    total_saved = wiki_saved + commons_saved + inat_saved
    note = "  *** NO IMAGES ***" if total_saved == 0 else ""
    print(
        f"[{idx:3d}/{total}] {animal:<32} "
        f"wiki={wiki_saved}  commons={commons_saved}  inat={inat_saved}  total={total_saved}{note}"
    )


# ── Entry point ────────────────────────────────────────────────────────────────

async def main() -> None:
    IMAGES_DIR.mkdir(exist_ok=True)
    print(f"AnimalGuesser image downloader")
    print(f"  Animals   : {len(ANIMALS)}")
    print(f"  Output    : {IMAGES_DIR}")
    print(f"  Skip if   : >= {SKIP_THRESHOLD} images already present")
    print(f"  Commons   : {COMMONS_PER_ANIMAL} per animal  (prefix: commons-)")
    print(f"  iNat quota: {INAT_PER_ANIMAL} per animal  (prefix: in-)")
    print("-" * 60)

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for idx, animal in enumerate(ANIMALS, 1):
            await process_animal(session, animal, idx, len(ANIMALS))

    print("\nDone! Review images/<Animal>/ folders and delete any inaccurate photos.")
    print("Prefixes: wiki-* (Wikipedia article), commons-* (Commons search), in-* (iNaturalist)")


if __name__ == "__main__":
    asyncio.run(main())
