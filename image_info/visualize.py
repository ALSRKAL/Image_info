"""Lightweight visualisations drawn with Pillow only - no matplotlib needed.

Every renderer returns a :class:`PIL.Image.Image` so callers can either save
it (``chart.save("hist.png")``) or embed it straight into the HTML report.

Example
-------
>>> from image_info.visualize import render_histogram, render_palette
>>> render_histogram("photo.jpg").save("histogram.png")
>>> render_palette("photo.jpg", count=8).save("palette.png")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

from PIL import Image, ImageDraw, ImageFont

from .core import DominantColor, dominant_colors

__all__ = ["render_histogram", "render_palette"]

ImageSource = Union[str, os.PathLike[str], Image.Image]

# Shared visual language: a dark card that reads well on GitHub light+dark.
_BG = (18, 22, 28)
_PANEL = (24, 29, 37)
_BORDER = (44, 52, 64)
_TEXT = (232, 236, 241)
_MUTED = (139, 150, 165)
_GRID = (40, 47, 58)
_CHANNEL_COLORS = {
    "R": (255, 92, 108),
    "G": (61, 220, 132),
    "B": (76, 154, 255),
    "Luma": (242, 201, 76),
}


def _load(source: ImageSource) -> Image.Image:
    if isinstance(source, Image.Image):
        return source
    image = Image.open(source)
    image.load()
    return image


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _smooth(values: list[int], passes: int = 2) -> list[float]:
    """Simple [1, 2, 1] kernel smoothing to make histogram curves readable."""
    data = [float(v) for v in values]
    for _ in range(passes):
        smoothed = list(data)
        for i in range(1, len(data) - 1):
            smoothed[i] = (data[i - 1] + 2 * data[i] + data[i + 1]) / 4.0
        data = smoothed
    return data


def _new_canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    """Create a 2x supersampled canvas so curves and text look crisp."""
    scale = 2
    canvas = Image.new("RGB", (width * scale, height * scale), _BG)
    return canvas, ImageDraw.Draw(canvas), scale


def _finish(canvas: Image.Image, width: int, height: int, scale: int) -> Image.Image:
    return canvas.resize((width, height), Image.Resampling.LANCZOS)


def _rounded_header(draw: ImageDraw.ImageDraw, title: str, width: int, scale: int) -> None:
    title_font = _font(15 * scale, bold=True)
    draw.text((20 * scale, 14 * scale), title, font=title_font, fill=_TEXT)
    draw.line(
        [(20 * scale, 40 * scale), ((width - 20) * scale, 40 * scale)],
        fill=_BORDER, width=scale,
    )


def _plot_area(width: int, height: int, scale: int) -> tuple[int, int, int, int]:
    """Bounding box of the plot region in supersampled coordinates."""
    left, top = 44 * scale, 56 * scale
    right, bottom = (width - 24) * scale, (height - 34) * scale
    return left, top, right, bottom


def render_histogram(
    source: ImageSource,
    width: int = 900,
    height: int = 430,
    title: Optional[str] = None,
) -> Image.Image:
    """Render the RGB + luminance histogram of ``source`` as a dark chart card."""
    image = _load(source)
    if title is None:
        title = "Color histogram" + (
            f" - {Path(image.filename).name}" if image.filename else ""
        )

    rgb = image.convert("RGB")
    hist = rgb.histogram()
    r_bins, g_bins, b_bins = hist[0:256], hist[256:512], hist[512:768]
    luma_bins = image.convert("L").histogram()

    series = {
        "R": _smooth(r_bins),
        "G": _smooth(g_bins),
        "B": _smooth(b_bins),
        "Luma": _smooth(luma_bins, passes=3),
    }
    peak = max(max(s) for s in series.values()) or 1.0

    canvas, draw, scale = _new_canvas(width, height)
    _rounded_header(draw, title, width, scale)
    left, top, right, bottom = _plot_area(width, height, scale)
    plot_w, plot_h = right - left, bottom - top

    for i in range(5):
        x = left + plot_w * i // 4
        draw.line([(x, top), (x, bottom)], fill=_GRID, width=scale)
        draw.text((x - 8 * scale, bottom + 6 * scale), str(i * 64),
                  font=_font(10 * scale), fill=_MUTED)
    for i in range(1, 4):
        y = top + plot_h * i // 4
        draw.line([(left, y), (right, y)], fill=_GRID, width=scale)

    step = plot_w / 255.0
    for name in ("Luma", "B", "G", "R"):  # luma first so colored curves stay on top
        bins = series[name]
        color = _CHANNEL_COLORS[name]
        if name == "Luma":
            points = [
                (left + i * step, bottom - (value / peak) * plot_h)
                for i, value in enumerate(bins)
            ]
            draw.line(points, fill=(*color, 200), width=scale)
            continue
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        polygon = [(left, bottom)]
        polygon += [
            (left + i * step, bottom - (value / peak) * plot_h)
            for i, value in enumerate(bins)
        ]
        polygon += [(right, bottom)]
        overlay_draw.polygon(polygon, fill=(*color, 90))
        overlay_draw.line(polygon[1:-1], fill=(*color, 230), width=scale)
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(canvas)

    legend_x = right - 210 * scale
    legend_y = top + 6 * scale
    for i, name in enumerate(("R", "G", "B", "Luma")):
        y = legend_y + i * 16 * scale
        draw.rectangle([legend_x, y, legend_x + 10 * scale, y + 8 * scale],
                       fill=_CHANNEL_COLORS[name])
        draw.text((legend_x + 16 * scale, y - 1 * scale), name,
                  font=_font(10 * scale), fill=_MUTED)

    return _finish(canvas, width, height, scale)


def render_palette(
    source: ImageSource,
    count: int = 8,
    width: int = 900,
    height: int = 260,
    title: Optional[str] = None,
) -> Image.Image:
    """Render the dominant colour palette of ``source`` as swatch cards."""
    image = _load(source)
    if title is None:
        title = "Dominant colors" + (
            f" - {Path(image.filename).name}" if image.filename else ""
        )

    colors: list[DominantColor] = dominant_colors(image, count)
    canvas, draw, scale = _new_canvas(width, height)
    _rounded_header(draw, title, width, scale)

    left, right = 20 * scale, (width - 20) * scale
    top = 56 * scale
    swatch_h = (height - 56 - 84) * scale
    gap = 6 * scale
    swatch_w = ((right - left) - gap * (len(colors) - 1)) / max(len(colors), 1)

    for i, color in enumerate(colors):
        x0 = left + i * (swatch_w + gap)
        box = [x0, top, x0 + swatch_w, top + swatch_h]
        draw.rectangle(box, fill=(color.red, color.green, color.blue))
        label_font = _font(11 * scale, bold=True)
        share_font = _font(9 * scale)
        draw.text((x0 + 2, top + swatch_h + 10 * scale), color.hex,
                  font=label_font, fill=_TEXT)
        draw.text((x0 + 2, top + swatch_h + 30 * scale), f"{color.share * 100:.1f}%",
                  font=share_font, fill=_MUTED)

    return _finish(canvas, width, height, scale)
