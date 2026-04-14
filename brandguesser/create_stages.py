#!/usr/bin/env python3
"""
create_stages.py — generate progressive reveal stages for BrandGuesser.

Game design:
  - Round lasts 60 seconds total.
  - 5 stages shown at t=0, 10, 20, 30, 40s. Image stays at stage 5 until
    someone guesses correctly or time expires.
  - The fully clear original (img-NNN.jpg) is shown by the bot ONLY on a correct
    guess or when time runs out — it is NOT pre-generated here.

For each processed image images/{brand}/img-NNN.jpg, generates 5 stages:
  images/{brand}/stages/img-NNN_s1.jpg   ← most obscured  (t=0s)
  images/{brand}/stages/img-NNN_s2.jpg                    (t=10s)
  images/{brand}/stages/img-NNN_s3.jpg                    (t=20s)
  images/{brand}/stages/img-NNN_s4.jpg                    (t=30s)
  images/{brand}/stages/img-NNN_s5.jpg   ← final stage    (t=40s–60s)

Three styles. Assignment per image (5 images per brand):
  img-001 → shuffle   (guaranteed one of each style)
  img-002 → pixel
  img-003 → blur
  img-004 → random choice from the 3
  img-005 → random choice from the 3

  shuffle — image divided into 40px blocks, randomly shuffled; blocks
            progressively snap back to correct positions (stage 5: 85% correct)
  pixel   — hard block pixelation (downscale + NEAREST upscale)
  blur    — smooth Gaussian blur

Usage:
    python create_stages.py                  # all brands, styles assigned randomly
    python create_stages.py "Toyota"         # single brand (substring match)
    python create_stages.py --regen          # regenerate even if stages exist
    python create_stages.py --test           # all 5 styles on first available image
    python create_stages.py --test "Target"  # all 5 styles on Target img-001
"""

import os
import sys
import random
from pathlib import Path
from PIL import Image, ImageFilter

# ── Paths & config ─────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
IMAGES_DIR  = Path(os.environ.get("IMAGES_DIR", str(SCRIPT_DIR / "images")))

DISPLAY_SIZE = (400, 400)   # all stage images standardized to this — 400 divides
                             # evenly by 20 and 40, keeping block grids clean
IMAGE_EXTS   = {".jpg", ".jpeg", ".png", ".webp"}
STYLES       = ["shuffle", "pixel", "blur"]
FIXED_STYLES = ["shuffle", "pixel", "blur"]   # assigned in order to images 1-3
NUM_STAGES   = 5

# ── Style parameters ───────────────────────────────────────────────────────────

# pixel / blob: intermediate downscale size (geometric ~1.7× each step)
PIXEL_SIZES = [8, 14, 24, 42, 72]

# blur: Gaussian radius (geometric ~1.5× decrease: 45→30→20→13→9)
BLUR_RADII = [45, 30, 20, 13, 9]

# shuffle: fraction of blocks that are back in their correct position
# 0.0 = fully shuffled chaos; 0.85 = 15% still wrong at final stage
SHUFFLE_FIX_FRACTIONS = [0.0, 0.30, 0.55, 0.72, 0.85]
SHUFFLE_BLOCK_SIZE    = 40   # 400/40 = 10×10 = 100 blocks

# blackout: fraction of blocks that are VISIBLE (rest are black)
# 0.10 = 90% blacked out at start; 0.80 = 20% still black at final stage
BLACKOUT_REVEAL_FRACTIONS = [0.10, 0.28, 0.50, 0.68, 0.80]
BLACKOUT_BLOCK_SIZE       = 20   # 400/20 = 20×20 = 400 blocks


# ── Stage generators ───────────────────────────────────────────────────────────

def stage_pixel(img: Image.Image, small_size: int) -> Image.Image:
    small = img.resize((small_size, small_size), Image.BOX)
    return small.resize(DISPLAY_SIZE, Image.NEAREST)


def stage_blur(img: Image.Image, radius: float) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


def stage_blob(img: Image.Image, small_size: int) -> Image.Image:
    small = img.resize((small_size, small_size), Image.BOX)
    return small.resize(DISPLAY_SIZE, Image.LANCZOS)


def stage_shuffle(img: Image.Image, fix_fraction: float, seed: int) -> Image.Image:
    """
    Divide image into SHUFFLE_BLOCK_SIZE px blocks. Randomly shuffle all blocks
    (using `seed` for reproducibility), then fix `fix_fraction` of them back to
    their correct positions. The same seed ensures stages are cumulative — more
    blocks correctly placed at each step.
    """
    bs = SHUFFLE_BLOCK_SIZE
    cols = DISPLAY_SIZE[0] // bs   # 10
    rows = DISPLAY_SIZE[1] // bs   # 10
    n    = cols * rows              # 100

    # Extract all blocks
    blocks = []
    for r in range(rows):
        for c in range(cols):
            box = (c * bs, r * bs, (c + 1) * bs, (r + 1) * bs)
            blocks.append(img.crop(box))

    # Shuffled arrangement: shuffled[i] = which original block goes in slot i
    rng_shuffle = random.Random(seed)
    shuffled = list(range(n))
    rng_shuffle.shuffle(shuffled)

    # Determine which slots to "fix" (return to identity), using a separate
    # seed offset so fix order is stable and independent of the shuffle order.
    n_fix = int(n * fix_fraction)
    rng_fix = random.Random(seed + 99991)
    fix_order = list(range(n))
    rng_fix.shuffle(fix_order)
    fixed_slots = set(fix_order[:n_fix])

    # Build arrangement: fixed slots use block i; unfixed use shuffled[i]
    result = img.copy()
    for i in range(n):
        src = i if i in fixed_slots else shuffled[i]
        r, c = divmod(i, cols)
        result.paste(blocks[src], (c * bs, r * bs))

    return result


def stage_blackout(img: Image.Image, reveal_fraction: float, seed: int) -> Image.Image:
    """
    Divide image into BLACKOUT_BLOCK_SIZE px blocks. Using `seed`, generate a
    fixed random reveal order. Show the first `reveal_fraction` of blocks; paint
    the rest solid black. Consistent seed means earlier stages' revealed blocks
    are always a subset of later stages'.
    """
    bs   = BLACKOUT_BLOCK_SIZE
    cols = DISPLAY_SIZE[0] // bs   # 20
    rows = DISPLAY_SIZE[1] // bs   # 20
    n    = cols * rows              # 400

    n_reveal = int(n * reveal_fraction)

    rng = random.Random(seed)
    reveal_order = list(range(n))
    rng.shuffle(reveal_order)
    visible = set(reveal_order[:n_reveal])

    result  = img.copy()
    black   = Image.new("RGB", (bs, bs), (0, 0, 0))

    for i in range(n):
        if i not in visible:
            r, c = divmod(i, cols)
            result.paste(black, (c * bs, r * bs))

    return result


def _image_seed(img_path: Path) -> int:
    """Derive a stable integer seed from the image filename (e.g. img-001 → 1)."""
    stem = img_path.stem  # "img-001"
    try:
        return int(stem.split("-")[1])
    except (IndexError, ValueError):
        return abs(hash(stem)) % 100_000


def _make_stage(
    img: Image.Image,
    style: str,
    stage_num: int,
    seed: int = 1,
) -> Image.Image:
    """stage_num is 1-based (1 = most obscured, 5 = last shown in-game)."""
    idx = stage_num - 1
    if style == "pixel":
        return stage_pixel(img, PIXEL_SIZES[idx])
    elif style == "blur":
        return stage_blur(img, BLUR_RADII[idx])
    elif style == "blob":
        return stage_blob(img, PIXEL_SIZES[idx])
    elif style == "shuffle":
        return stage_shuffle(img, SHUFFLE_FIX_FRACTIONS[idx], seed)
    elif style == "blackout":
        return stage_blackout(img, BLACKOUT_REVEAL_FRACTIONS[idx], seed)
    else:
        raise ValueError(f"Unknown style: {style!r}")


# ── Core: process one image ────────────────────────────────────────────────────

def generate_stages_for_image(
    img_path: Path,
    style: str,
    regen: bool = False,
) -> bool:
    """
    Generate NUM_STAGES stages for a single processed image.
    Returns True if stages were written, False if skipped (already exist).
    """
    stages_dir = img_path.parent / "stages"
    stem = img_path.stem

    if not regen:
        existing = list(stages_dir.glob(f"{stem}_s*.jpg"))
        if len(existing) >= NUM_STAGES:
            return False

    stages_dir.mkdir(exist_ok=True)

    img  = Image.open(img_path).convert("RGB")
    img  = img.resize(DISPLAY_SIZE, Image.LANCZOS)
    seed = _image_seed(img_path)

    for stage_num in range(1, NUM_STAGES + 1):
        out = stages_dir / f"{stem}_s{stage_num}.jpg"
        _make_stage(img, style, stage_num, seed=seed).save(out, "JPEG", quality=90)

    return True


# ── Process a brand ────────────────────────────────────────────────────────────

def process_brand(brand_name: str, regen: bool = False) -> int:
    folder = IMAGES_DIR / brand_name
    if not folder.is_dir():
        print(f"  [{brand_name}] folder not found, skipping")
        return 0

    img_files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and p.stem.startswith("img-")
    )
    if not img_files:
        print(f"  [{brand_name}] no images found, skipping")
        return 0

    done = 0
    for i, img_path in enumerate(img_files):
        # First 3 images get one guaranteed style each; remainder are random
        style = FIXED_STYLES[i] if i < len(FIXED_STYLES) else random.choice(STYLES)
        generated = generate_stages_for_image(img_path, style, regen=regen)
        marker = f" {img_path.name}[{style[:2]}]" if generated else f" {img_path.name}[skip]"
        print(marker, end="", flush=True)
        if generated:
            done += 1

    print()
    return done


# ── Test mode: all 5 styles on one image ──────────────────────────────────────

def test_mode(brand_hint: str = "") -> None:
    """
    Generate all 5 styles × 5 stages for a single image.
    Output: images/_test_comparison/{style}_s{N}.jpg + original.jpg
    """
    test_img = None

    if brand_hint:
        needle = brand_hint.lower()
        for brand_dir in sorted(IMAGES_DIR.iterdir()):
            if needle in brand_dir.name.lower() and brand_dir.is_dir():
                imgs = sorted(
                    p for p in brand_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTS
                    and p.stem.startswith("img-")
                )
                if imgs:
                    test_img = imgs[0]
                    break
    else:
        for brand_dir in sorted(IMAGES_DIR.iterdir()):
            if brand_dir.is_dir() and brand_dir.name != "_test_comparison":
                imgs = sorted(
                    p for p in brand_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTS
                    and p.stem.startswith("img-")
                )
                if imgs:
                    test_img = imgs[0]
                    break

    if not test_img:
        print("ERROR: No images found to test with.")
        return

    print(f"Test image : {test_img}")
    out_dir = IMAGES_DIR / "_test_comparison"
    out_dir.mkdir(parents=True, exist_ok=True)

    img  = Image.open(test_img).convert("RGB")
    img  = img.resize(DISPLAY_SIZE, Image.LANCZOS)
    seed = _image_seed(test_img)

    for style in STYLES:
        for stage_num in range(1, NUM_STAGES + 1):
            out_path = out_dir / f"{style}_s{stage_num}.jpg"
            _make_stage(img, style, stage_num, seed=seed).save(out_path, "JPEG", quality=90)
        print(f"  {style}: s1→s{NUM_STAGES} written")

    img.save(out_dir / "original.jpg", "JPEG", quality=93)
    print(f"  original written")

    total = len(STYLES) * NUM_STAGES + 1
    print(f"\n{total} images → {out_dir}")
    print(f"\nStyles: {', '.join(STYLES)}")
    print(f"Stage 1 = most obscured (t=0s) │ Stage {NUM_STAGES} = final in-game stage (t=40s)")
    print(f"original.jpg = shown by bot on correct guess or timeout")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args  = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    regen = "--regen" in flags
    test  = "--test"  in flags

    if test:
        test_mode(brand_hint=args[0] if args else "")
        return

    from brands import BRANDS
    all_brand_names = list(BRANDS.keys())

    if args:
        needle = args[0].lower()
        targets = [n for n in all_brand_names if needle in n.lower()]
        if not targets:
            print(f"No brand matching '{args[0]}' found.")
            sys.exit(1)
    else:
        targets = all_brand_names

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"BrandGuesser — stage generator")
    print(f"  Brands  : {len(targets)}")
    print(f"  Output  : {IMAGES_DIR}")
    print(f"  Stages  : {NUM_STAGES} per image (t=0s … t=40s, every 10s)")
    print(f"  Styles  : img-001=shuffle, img-002=pixel, img-003=blur, img-004/005=random")
    print(f"  Regen   : {'yes' if regen else f'no (skip if {NUM_STAGES} stages exist)'}")
    print("-" * 60)

    total_done = 0
    for name in targets:
        n = process_brand(name, regen=regen)
        total_done += n

    print(f"\nDone — generated stages for {total_done} images.")


if __name__ == "__main__":
    main()
