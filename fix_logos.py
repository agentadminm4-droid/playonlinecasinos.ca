#!/usr/bin/env python3
"""Fetch the REAL Betway wordmark and a PNG version of Spin Casino.

For Betway: try a few CDN paths. The 200x235 8-bit file we have is the
betway.ca favicon — a small shield, not the brand wordmark.

For Spin Casino: convert the SVG we have to PNG.
"""
import os
import sys
import urllib.request
import subprocess
from pathlib import Path

ROOT = Path(os.path.expanduser("~/Desktop/playonlinecasinos"))
LOGOS = ROOT / "images" / "logos"
LOGOS.mkdir(parents=True, exist_ok=True)


def download(url, dest, headers=None):
    h = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "image/png,image/svg+xml,image/*,*/*;q=0.8",
    }
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            # Verify it's actually an image
            if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"GIF" or data[:2] == b"\xff\xd8" or data[:4] == b"RIFF":
                dest.write_bytes(data)
                print(f"  ✓ {dest.name}: {dest.stat().st_size:,} bytes <- {url[:80]}")
                return True
            else:
                print(f"  ✗ {dest.name}: response is not an image (HTML/redirect) <- {url[:80]}")
                return False
    except Exception as e:
        print(f"  ✗ {dest.name}: {type(e).__name__} <- {url[:80]}")
        return False


def scrape_with_playwright(url, selector, dest):
    """Use a headless browser to grab an image that requires JS rendering."""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            # Wait for image
            try:
                page.wait_for_selector(selector, timeout=10000)
            except Exception:
                pass
            # Get image src
            img_src = page.eval_on_selector(selector, "el => el.src || el.getAttribute('data-src') || el.getAttribute('href')")
            print(f"  Found: {img_src}")
            if img_src:
                return download(img_src, dest)
            browser.close()
    except Exception as e:
        print(f"  Playwright error: {e}")
    return False


def main():
    print("=== Betway: get the real wordmark ===\n")
    betway_dest = LOGOS / "betway.png"
    # Try multiple paths
    betway_urls = [
        # Common CDN paths
        "https://www.betway.ca/_next/static/media/betway-logo.7e9b2c1d.png",
        "https://cdn.betwaygroup.com/logos/betway/betway-logo-red.png",
        "https://www.betway.com/static/images/betway-logo.png",
        "https://www.betway.com/etc/designs/betway-consumer/clientlibs/img/logo.svg",
    ]
    success = False
    for url in betway_urls:
        if download(url, betway_dest):
            success = True
            break
    if not success:
        print("\n  Skipping Playwright fallback (not installed). Will use real-asset hint from skill.")
        # If CDN failed, the fallback per the regen-brand skill: don't guess.
        # Keep the existing file but log it as suspect.
        if betway_dest.exists() and betway_dest.stat().st_size < 15000:
            print(f"  ! Existing betway.png is small ({betway_dest.stat().st_size} bytes) — likely a favicon, not a wordmark")

    print("\n=== Spin Casino: convert SVG → PNG ===\n")
    spin_dest = LOGOS / "spincasino.png"
    # Try direct PNG from CDN first
    spin_urls = [
        "https://dm.imagethumb.com/images/spin-logos/logo-ca.png",
        "https://www.spincasino.ca/images/logos/spin-casino.png",
    ]
    success_spin = False
    for url in spin_urls:
        if download(url, spin_dest):
            success_spin = True
            break
    if not success_spin:
        # Convert the SVG to PNG using cairosvg
        svg_path = LOGOS / "spincasino.svg"
        if svg_path.exists():
            try:
                import cairosvg
                cairosvg.svg2png(url=str(svg_path), write_to=str(spin_dest), output_width=400)
                print(f"  ✓ {spin_dest.name}: {spin_dest.stat().st_size:,} bytes (converted from SVG)")
                success_spin = True
            except ImportError:
                print("  ✗ cairosvg not available, trying PIL via svglib")
                try:
                    from svglib.svglib import svg2rlg
                    from reportlab.graphics import renderPM
                    drawing = svg2rlg(str(svg_path))
                    renderPM.drawToFile(drawing, str(spin_dest), fmt="PNG")
                    print(f"  ✓ {spin_dest.name}: {spin_dest.stat().st_size:,} bytes (svglib convert)")
                    success_spin = True
                except ImportError:
                    print("  ✗ svglib not available either")
            except Exception as e:
                print(f"  ✗ SVG convert error: {e}")

    # If still no PNG, fallback: rename SVG to .svg in HTML and let browser handle it
    if not success_spin:
        print("\n  All conversions failed. Will use SVG in HTML instead.")


if __name__ == "__main__":
    main()
