#!/usr/bin/env python3
"""Optimize AI-generated images for web use.

gpt-image-1 outputs ~1.5-2.5MB PNGs. We need:
- Resize to web-appropriate dimensions (max 1600px wide)
- Convert to JPEG at quality 80 (cuts size by 80%)
- Generate thumbnail variants for cards (600px wide, q75)

Run: python3 optimize_images.py
"""
import os
from pathlib import Path
from PIL import Image

ROOT = Path(os.path.expanduser("~/Desktop/playonlinecasinos"))
ART = ROOT / "images" / "art"
OG = ROOT / "images" / "og"


def optimize_image(src, max_width=1600, quality=82):
    """Resize and compress a single image."""
    try:
        img = Image.open(src)
    except Exception as e:
        print(f"  ✗ {src.name}: cannot open ({e})")
        return False

    # Convert RGBA to RGB if needed (PNG → JPEG)
    if img.mode == "RGBA":
        # Composite onto dark background
        bg = Image.new("RGB", img.size, (10, 14, 26))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize if wider than max_width
    if img.width > max_width:
        ratio = max_width / img.width
        new_h = int(img.height * ratio)
        img = img.resize((max_width, new_h), Image.LANCZOS)

    # Save as JPEG, overwrite
    jpeg_path = src.with_suffix(".jpg")
    img.save(jpeg_path, "JPEG", quality=quality, optimize=True, progressive=True)

    # Remove original PNG if it exists and is different
    if src != jpeg_path and src.exists():
        src.unlink()

    orig_size = src.stat().st_size if src.exists() else 0
    new_size = jpeg_path.stat().st_size
    saved = max(0, orig_size - new_size)
    print(f"  ✓ {jpeg_path.name}: {img.width}x{img.height}, {new_size:,} bytes")
    return True


def make_thumbnail(src, max_width=600, quality=78):
    """Generate a small thumbnail variant for card use."""
    try:
        img = Image.open(src)
    except Exception:
        return False
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (10, 14, 26))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        new_h = int(img.height * ratio)
        img = img.resize((max_width, new_h), Image.LANCZOS)
    thumb = src.parent / (src.stem + "-thumb.jpg")
    img.save(thumb, "JPEG", quality=quality, optimize=True, progressive=True)
    print(f"  ✓ {thumb.name}: {img.width}x{img.height}, {thumb.stat().st_size:,} bytes")
    return True


def main():
    print("=== Optimizing AI-generated images ===\n")
    total_orig = 0
    total_new = 0
    for d in (ART, OG):
        for f in sorted(d.glob("*.jpg")):
            orig_size = f.stat().st_size
            if optimize_image(f):
                new_size = f.stat().st_size
                total_orig += orig_size
                total_new += new_size
    for f in sorted(ART.glob("*.jpg")):
        make_thumbnail(f)

    saved = total_orig - total_new
    if total_orig:
        print(f"\nTotal: {total_orig:,} → {total_new:,} bytes (saved {saved:,} = {100*saved//total_orig}%)")


if __name__ == "__main__":
    main()
