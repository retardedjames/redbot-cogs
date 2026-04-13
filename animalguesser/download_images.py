#!/usr/bin/env python3
"""
download_images.py — populate images/ for AnimalGuesser.

Fetches the top 15 image results per animal via DuckDuckGo Images
(same sources as Google Images; no API key or scraping blocks).

Usage:
    cd animalguesser
    python download_images.py           # all animals
    python download_images.py 10        # first N animals only

Images are saved to:
    images/<Animal Name>/img-001.jpg
    images/<Animal Name>/img-002.jpg
    ...

Re-runnable: folders with >= SKIP_THRESHOLD images are skipped.
After the run, browse images/<Animal Name>/ and delete any bad photos.
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
IMAGES_DIR = SCRIPT_DIR / "images"

# ── Animal list ────────────────────────────────────────────────────────────────
ANIMALS = [
    # A
    "Aardvark", "African Buffalo", "African Elephant", "African Wild Dog",
    "Albatross", "Alligator", "Alpaca", "Anaconda", "Anteater", "Antelope",
    "Arctic Fox", "Arctic Wolf", "Armadillo", "Axolotl",
    # B
    "Baboon", "Bald Eagle", "Barn Owl", "Barracuda", "Bat", "Bearded Dragon",
    "Beaver", "Beluga Whale", "Bengal Tiger", "Bighorn Sheep", "Bison",
    "Black Bear", "Black Mamba", "Blue Jay", "Blue Whale", "Boa Constrictor",
    "Bobcat", "Box Jellyfish", "Brown Bear", "Bullfrog", "Bushbaby",
    # C
    "Caiman", "Camel", "Capybara", "Caracal", "Cat", "Catfish", "Chameleon",
    "Cheetah", "Chicken", "Chimpanzee", "Chinchilla", "Chipmunk", "Clownfish",
    "Clouded Leopard", "Cobra", "Cockatoo", "Condor", "Cormorant", "Cougar",
    "Coyote", "Crab", "Crane", "Crocodile", "Crow", "Cuttlefish",
    # D
    "Deer", "Dhole", "Dingo", "Dolphin", "Donkey", "Duck", "Dugong",
    # E
    "Eagle", "Echidna", "Electric Eel", "Elephant", "Elk", "Emu",
    # F
    "Falcon", "Ferret", "Finch", "Flamingo", "Flying Squirrel", "Fossa",
    "Fox", "Frigate Bird", "Frog",
    # G
    "Gaur", "Gazelle", "Gecko", "Giant Panda", "Giant Squid", "Gila Monster",
    "Giraffe", "Gnu", "Goat", "Golden Eagle", "Goose", "Gorilla",
    "Grizzly Bear", "Groundhog", "Guinea Pig",
    # H
    "Hammerhead Shark", "Hamster", "Hare", "Hawk", "Hedgehog", "Heron",
    "Hippopotamus", "Honey Badger", "Horse", "Hummingbird",
    "Humpback Whale", "Hyena",
    # I
    "Ibis", "Iguana", "Impala",
    # J
    "Jackrabbit", "Jaguar", "Jellyfish",
    # K
    "Kangaroo", "King Cobra", "Kinkajou", "Kiwi", "Koala",
    "Komodo Dragon", "Kookaburra", "Kudu",
    # L
    "Leafy Sea Dragon", "Lemur", "Leopard", "Leopard Seal", "Lion",
    "Llama", "Lobster", "Lynx",
    # M
    "Macaw", "Magpie", "Manatee", "Mandrill", "Manta Ray", "Marmoset",
    "Marmot", "Meerkat", "Mongoose", "Monitor Lizard", "Moose",
    "Mountain Goat", "Mouse", "Mule", "Musk Ox",
    # N
    "Narwhal", "Numbat",
    # O
    "Ocelot", "Octopus", "Opossum", "Orangutan", "Orca", "Oryx",
    "Ostrich", "Otter", "Owl",
    # P
    "Pangolin", "Parrot", "Peacock", "Pelican", "Penguin",
    "Peregrine Falcon", "Pheasant", "Pig", "Pika", "Pigeon", "Piranha",
    "Platypus", "Polar Bear", "Porcupine", "Prairie Dog", "Proboscis Monkey",
    "Pronghorn", "Puffin", "Puma", "Python",
    # Q
    "Quail", "Quokka",
    # R
    "Rabbit", "Raccoon", "Rat", "Rattlesnake", "Red Fox", "Red Panda",
    "Reindeer", "Rhinoceros", "Ring-Tailed Lemur", "Robin", "Rock Hyrax",
    "Rooster",
    # S
    "Salamander", "Scorpion", "Sea Horse", "Sea Lion", "Sea Otter",
    "Sea Turtle", "Seal", "Secretary Bird", "Serval", "Shark", "Skunk",
    "Sloth", "Sloth Bear", "Snapping Turtle", "Snow Leopard", "Snowy Owl",
    "Sperm Whale", "Springbok", "Squirrel", "Starfish", "Stingray", "Stoat",
    "Stork", "Sun Bear", "Swan", "Swordfish",
    # T
    "Tapir", "Tarantula", "Tarsier", "Tasmanian Devil", "Tiger",
    "Tiger Shark", "Toad", "Toucan", "Tree Frog", "Tuna", "Turkey", "Turtle",
    # U
    "Uakari",
    # V
    "Vampire Bat", "Viper", "Vulture",
    # W
    "Walrus", "Warthog", "Water Buffalo", "Weasel", "Whale", "Whale Shark",
    "White-Tailed Deer", "Wild Boar", "Wildebeest", "Wolf", "Wolverine",
    "Wombat", "Woodpecker",
    # Y – Z
    "Yak", "Zebra",
]

# ── Config ─────────────────────────────────────────────────────────────────────
IMAGES_PER_ANIMAL = 15
SKIP_THRESHOLD = 5        # skip folder if already has >= this many images
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
DELAY_BETWEEN_ANIMALS = 2  # seconds between animals
DOWNLOAD_WORKERS = 8       # parallel image downloads per animal
DOWNLOAD_TIMEOUT = 20      # seconds per image download

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def existing_count(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


_ddgs = None  # single shared session to avoid rate limits


def _get_ddgs():
    global _ddgs
    if _ddgs is None:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # fallback
        _ddgs = DDGS()
    return _ddgs


def search_images(animal: str, count: int) -> list[str]:
    """Return up to *count* image URLs for *animal* via DuckDuckGo Images."""
    for attempt in range(3):
        try:
            ddgs = _get_ddgs()
            results = list(ddgs.images(
                f"{animal} animal",
                max_results=count * 2,  # fetch extra in case some fail
            ))
            return [r["image"] for r in results if r.get("image")][:count * 2]
        except Exception as exc:
            wait = (attempt + 1) * 5
            print(f"\n      [Search error attempt {attempt+1}] {animal}: {exc} — retrying in {wait}s")
            time.sleep(wait)
    return []


def download_image(url: str, dest: Path) -> bool:
    """Download *url* to *dest*. Returns True on success."""
    if dest.exists():
        return True
    try:
        r = requests.get(url, headers=HEADERS, timeout=DOWNLOAD_TIMEOUT, stream=True)
        if r.status_code == 200:
            content_type = r.headers.get("content-type", "")
            if "image" not in content_type and "octet" not in content_type:
                return False
            data = r.content
            if len(data) > 5_000:  # skip suspiciously tiny responses
                dest.write_bytes(data)
                return True
    except Exception:
        pass
    return False


def ext_from_url(url: str) -> str:
    """Derive a file extension from a URL."""
    from urllib.parse import urlparse
    import posixpath
    path = urlparse(url).path
    _, ext = posixpath.splitext(path)
    ext = ext.lower().split("?")[0]
    if ext in (".jpeg", ".jpg"):
        return ".jpg"
    if ext in (".png", ".gif", ".webp"):
        return ext
    return ".jpg"  # default


def process_animal(animal: str, idx: int, total: int) -> int:
    """Download images for one animal. Returns number of images saved."""
    folder = IMAGES_DIR / animal
    count = existing_count(folder)

    if count >= SKIP_THRESHOLD:
        print(f"[{idx:3d}/{total}] {animal:<32} skip ({count} images present)")
        return count

    folder.mkdir(parents=True, exist_ok=True)
    print(f"[{idx:3d}/{total}] {animal:<32} searching...", end="", flush=True)

    urls = search_images(animal, IMAGES_PER_ANIMAL)
    if not urls:
        print(f" no results")
        return 0

    print(f" found {len(urls)} URLs, downloading...", end="", flush=True)

    # Download images in parallel, capping at IMAGES_PER_ANIMAL successes
    import threading
    save_lock = threading.Lock()
    saved_paths = []

    def try_download(url):
        """Download url; return saved Path on success or None."""
        ext = ext_from_url(url)
        with save_lock:
            if len(saved_paths) >= IMAGES_PER_ANIMAL:
                return None
            idx = len(saved_paths) + 1
            dest = folder / f"img-{idx:03d}{ext}"
            saved_paths.append(dest)  # reserve the slot
        ok = download_image(url, dest)
        if not ok:
            with save_lock:
                if dest in saved_paths:
                    saved_paths.remove(dest)
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
        return dest if ok else None

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        list(pool.map(try_download, urls))

    saved = sum(1 for p in saved_paths if p.exists())

    note = "  *** NO IMAGES ***" if saved == 0 else ""
    print(f" {saved} saved{note}")
    return saved


def main() -> None:
    IMAGES_DIR.mkdir(exist_ok=True)

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(ANIMALS)
    animals = ANIMALS[:limit]

    print("AnimalGuesser — image downloader (DuckDuckGo Images)")
    print(f"  Animals   : {len(animals)} (of {len(ANIMALS)} total)")
    print(f"  Output    : {IMAGES_DIR}")
    print(f"  Per animal: {IMAGES_PER_ANIMAL} images")
    print(f"  Skip if   : >= {SKIP_THRESHOLD} images already present")
    print("-" * 60)

    for idx, animal in enumerate(animals, 1):
        process_animal(animal, idx, len(animals))
        if idx < len(animals):
            time.sleep(DELAY_BETWEEN_ANIMALS)

    print("\nDone! Review images/<Animal>/ and delete any bad photos.")
    print("Then rsync/scp the images/ folder to your Redbot server.")


if __name__ == "__main__":
    main()
