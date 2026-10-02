#!/usr/bin/env python3
"""Regenerate every README asset under assets/.

Usage:  python tools/make_assets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from image_info.demo import create_sample_photo  # noqa: E402
from image_info.visualize import render_histogram, render_palette  # noqa: E402

ASSETS = ROOT / "assets"


# --------------------------------------------------------------------------- #
# banner
# --------------------------------------------------------------------------- #
def _font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.ImageFont:
    name = ("DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf") if mono else (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    path = f"/usr/share/fonts/truetype/dejavu/{name}"
    if Path(path).exists():
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def banner() -> None:
    width, height, scale = 1280, 380, 2
    canvas = Image.new("RGB", (width * scale, height * scale))
    draw = ImageDraw.Draw(canvas)
    top, bottom = _hex("#0B0F16"), _hex("#151C29")
    for y in range(height * scale):
        draw.line([(0, y), (width * scale, y)],
                  fill=_lerp(top, bottom, y / (height * scale)))

    # faint pixel grid, echoing the perceptual-hash motif
    for gx in range(0, width * scale, 40 * scale):
        for gy in range(0, height * scale, 40 * scale):
            draw.rectangle([gx, gy, gx + 2 * scale, gy + 2 * scale],
                           fill=(32, 40, 54))

    # accent bar
    for x in range(56 * scale, 620 * scale):
        t = (x - 56 * scale) / (564 * scale)
        color = _lerp(_hex("#3B6EF6"), _hex("#9B59F6"), t)
        draw.line([(x, 300 * scale), (x, 306 * scale)], fill=color)

    title_font = _font(64 * scale, bold=True)
    sub_font = _font(21 * scale, mono=True)
    chip_font = _font(15 * scale, bold=True, mono=True)

    draw.text((56 * scale, 74 * scale), "Image_info", font=title_font, fill=(238, 242, 247))
    draw.text((56 * scale, 176 * scale),
              "EXIF & GPS forensics  -  privacy audits  -  duplicate finder",
              font=sub_font, fill=(148, 160, 178))
    draw.text((56 * scale, 214 * scale),
              "hashes  -  palettes  -  single-file HTML reports",
              font=sub_font, fill=(148, 160, 178))

    chips = [("Pillow-powered", "#3B6EF6"), ("Zero-config CLI", "#2DA44E"),
             ("Python 3.9+", "#B083F0")]
    x = 56 * scale
    for label, color in chips:
        w = int(chip_font.getlength(label)) + 28 * scale
        draw.rounded_rectangle([x, 330 * scale, x + w, 362 * scale],
                               radius=16 * scale, outline=_hex(color), width=2 * scale)
        draw.text((x + 14 * scale, 336 * scale), label, font=chip_font,
                  fill=_lerp(_hex(color), (255, 255, 255), 0.35))
        x += w + 14 * scale

    # right side: mini palette + mini histogram silhouette
    swatch_colors = ["#373261", "#71456F", "#AE5863", "#E07B54", "#F7C868"]
    sw = 52 * scale
    for i, c in enumerate(swatch_colors):
        x0 = (width - 40) * scale - len(swatch_colors) * (sw + 8 * scale) + i * (sw + 8 * scale)
        draw.rounded_rectangle([x0, 96 * scale, x0 + sw, 200 * scale],
                               radius=8 * scale, fill=_hex(c))
    import math

    base_y = 316 * scale
    x_start, x_end = 700 * scale, (width - 56) * scale
    points = [(x_start, base_y)]
    steps = 46

    def noise(i: int) -> float:  # deterministic silhouette heights
        return (math.sin(i * 12.9898) * 43758.5453) % 1.0

    for i in range(1, steps):
        h = (10 + noise(i) * 100) * scale
        points.append((x_start + (x_end - x_start) * i // steps, base_y - int(h)))
    points.append((x_end, base_y))
    draw.polygon(points, fill=(38, 50, 70))
    draw.line(points[1:-1], fill=(58, 74, 100), width=scale)

    canvas = canvas.resize((width, height), Image.Resampling.LANCZOS)
    ASSETS.mkdir(exist_ok=True)
    canvas.save(ASSETS / "banner.png")
    print("wrote assets/banner.png")


def charts_and_photo() -> Path:
    ASSETS.mkdir(exist_ok=True)
    photo = create_sample_photo(ASSETS / "sample_photo.jpg")
    render_histogram(photo).save(ASSETS / "histogram.png")
    render_palette(photo, count=8).save(ASSETS / "palette.png")
    print("wrote assets/sample_photo.jpg, histogram.png, palette.png")
    return photo


if __name__ == "__main__":
    banner()
    charts_and_photo()
