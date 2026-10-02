#!/usr/bin/env python3
"""Render CLI output as a terminal-style PNG for the README.

The text shown in the screenshots is captured from the real CLI, so the
README always matches actual behaviour.

Usage:  python tools/render_terminal.py <out.png> <title> <command> [-- args...]
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from image_info.cli import main as cli_main  # noqa: E402

BG = (13, 17, 23)
TITLEBAR = (26, 32, 42)
BORDER = (48, 57, 70)
TEXT = (201, 209, 217)
MUTED = (110, 122, 138)
PROMPT_GREEN = (63, 185, 80)
ACCENT = (88, 166, 255)
RED, YELLOW, GREEN_DOT = (229, 83, 75), (241, 196, 83), (56, 178, 97)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    name = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
    path = f"/usr/share/fonts/truetype/dejavu/{name}"
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def capture(command: list[str]) -> list[str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        cli_main(command)
    return buffer.getvalue().rstrip("\n").splitlines()


def render(out_path: Path, title: str, command: str, lines: list[str]) -> None:
    scale = 2
    font = _font(15 * scale)
    bold = _font(15 * scale, bold=True)
    small = _font(12 * scale)
    line_h = 24 * scale
    pad_x, pad_top, pad_bottom = 22 * scale, 52 * scale, 20 * scale

    body = [command] + lines
    text_w = max(font.getlength(line) for line in body) + pad_x * 2 + 30 * scale
    width = max(int(text_w), 640 * scale)
    height = pad_top + line_h * len(body) + pad_bottom

    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)

    # title bar
    draw.rectangle([0, 0, width, 36 * scale], fill=TITLEBAR)
    draw.line([(0, 36 * scale), (width, 36 * scale)], fill=BORDER, width=scale)
    for i, color in enumerate((RED, YELLOW, GREEN_DOT)):
        cx = (18 + i * 20) * scale
        cy = 18 * scale
        r = 6 * scale
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    title_font = small
    tw = title_font.getlength(title)
    draw.text(((width - tw) / 2, 10 * scale), title, font=title_font, fill=MUTED)

    # prompt line
    y = pad_top
    draw.text((pad_x, y), "$", font=bold, fill=PROMPT_GREEN)
    draw.text((pad_x + 18 * scale, y), command, font=bold, fill=TEXT)
    y += line_h

    # output
    for line in lines:
        color = TEXT
        stripped = line.lstrip()
        if stripped.startswith("error:"):
            color = (242, 113, 113)
        elif "Privacy risk" in line or "risk:" in line:
            color = ACCENT
        draw.text((pad_x, y), line, font=font, fill=color)
        y += line_h

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = canvas.resize((width // scale, height // scale),
                           Image.Resampling.LANCZOS)
    # subtle rounded corners
    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, canvas.width - 1, canvas.height - 1],
                                           radius=10, fill=255)
    final = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    final.paste(canvas, (0, 0), mask)
    final.save(out_path)
    print(f"wrote {out_path}")


def main() -> None:
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    out_path = Path(sys.argv[1])
    title = sys.argv[2]
    cli_args = sys.argv[3:]
    command_display = "imageinfo " + " ".join(cli_args)
    render(out_path, title, command_display, capture(cli_args))


if __name__ == "__main__":
    main()
