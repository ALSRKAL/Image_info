"""Synthetic sample images so the toolkit can be tried without your own files.

:func:`create_sample_photo` renders a small "sunset over mountains" scene and
stamps it with realistic EXIF (device, timestamps, exposure, GPS position of
Petra, Jordan), and :func:`create_sample_set` builds a small corpus used by
the ``imageinfo demo`` command, the examples and the test suite.

Example
-------
>>> from image_info.demo import create_sample_set
>>> create_sample_set("demo_output")
{'photo': PosixPath('demo_output/petra_sunset.jpg'), ...}
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter
from PIL.TiffImagePlugin import IFDRational

from .exif import dms_to_decimal

__all__ = ["create_sample_photo", "create_sample_set", "PETRA"]

# Petra, Jordan - the GPS position stamped into the sample photo.
PETRA = (30.328500, 35.444389)


def _noise(i: int, seed: int = 0) -> float:
    """Deterministic pseudo-random value in [0, 1).

    A tiny integer hash (Knuth multiplicative) instead of the ``random``
    module, so rendered scenes are byte-reproducible on every machine.
    """
    return (((i + 1) * 2654435761 + (seed + 1) * 40503) % 65536) / 65536


def _hex(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _sky(draw: ImageDraw.ImageDraw, width: int, horizon: int) -> None:
    stops = [(0.0, "#16264F"), (0.45, "#5B3E75"), (0.75, "#B95560"),
             (0.92, "#E98A4E"), (1.0, "#F7C868")]
    for y in range(horizon + 1):
        t = y / max(horizon, 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                color = _lerp(_hex(c0), _hex(c1), (t - t0) / (t1 - t0))
                break
        draw.line([(0, y), (width, y)], fill=color)


def _sun(image: Image.Image, cx: float, cy: float, radius: float) -> Image.Image:
    """Blend a sun disc + glow into ``image`` and return the RGB result."""
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    for i in range(28, 0, -1):
        r = radius * i / 8
        alpha = max(0, 26 - i)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 196, 110, alpha))
    core_r = radius / 2.2
    draw.ellipse([cx - core_r, cy - core_r, cx + core_r, cy + core_r],
                 fill=(255, 224, 160, 235))
    return Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")


def _ridge(width: int, base_y: int, amplitude: int, seed: int) -> list[tuple[int, int]]:
    points = [(0, base_y + int((_noise(0, seed) - 0.5) * amplitude * 2 / 3))]
    step = width // 8
    for i in range(1, 9):
        jitter = int((_noise(i, seed) - 0.5) * amplitude * 2)
        points.append((step * i, base_y + jitter))
    return points


def _mountains(draw: ImageDraw.ImageDraw, width: int, height: int, horizon: int) -> None:
    layers = [
        (horizon - height // 9, 26, (38, 34, 64), 7),
        (horizon - height // 22, 20, (28, 25, 46), 11),
        (horizon + height // 30, 14, (18, 16, 30), 23),
    ]
    for base_y, amplitude, color, seed in layers:
        points = _ridge(width, base_y, amplitude, seed)
        draw.polygon(points + [(width, height), (0, height)], fill=color)


def _water(image: Image.Image, width: int, height: int, waterline: int) -> None:
    water = Image.new("RGBA", (width, height - waterline))
    sky_crop = image.crop((0, waterline - (height - waterline), width, waterline))
    water.paste(sky_crop.transpose(Image.FLIP_TOP_BOTTOM).point(
        lambda v: v // 3))
    image.paste(water.convert("RGB"), (0, waterline))
    draw = ImageDraw.Draw(image, "RGBA")
    for i in range(26):
        x = int(_noise(i, 101) * width)
        y = waterline + 4 + int(_noise(i, 202) * (height - waterline - 8))
        length = 8 + int(_noise(i, 303) * 52)
        draw.line([(x, y), (x + length, y)], fill=(255, 205, 130, 40), width=1)


def _grain(image: Image.Image, amount: int = 5) -> None:
    try:
        import numpy as np
    except ImportError:
        return
    rng = np.random.default_rng(20250930)
    noise = rng.integers(-amount, amount + 1, size=(image.height, image.width, 3))
    arr = np.asarray(image, dtype=np.int16) + noise
    result = Image.fromarray(arr.clip(0, 255).astype("uint8"), "RGB")
    image.paste(result)


def _dms_tuple(value: float, precision: int = 10000) -> tuple[Fraction, Fraction, Fraction]:
    degrees = int(abs(value))
    minutes_full = (abs(value) - degrees) * 3600
    seconds = Fraction(round(minutes_full * precision), precision)
    minutes = int(seconds // 60)
    seconds -= minutes * 60
    return (Fraction(degrees), Fraction(minutes), Fraction(seconds))


def build_exif_bytes(gps: Optional[tuple[float, float]] = None) -> bytes:
    """Compose a realistic EXIF payload with Pillow (optionally including GPS)."""
    from PIL import Image as PILImage

    exif = PILImage.Exif()
    exif[0x010F] = "PixelWorks"                       # Make
    exif[0x0110] = "PW-7 Pro"                         # Model
    exif[0x0112] = 1                                  # Orientation
    exif[0x011A] = Fraction(72, 1)                    # XResolution
    exif[0x011B] = Fraction(72, 1)                    # YResolution
    exif[0x0131] = "PW-Camera 3.2.1"                  # Software
    exif[0x0132] = "2025:09:30 17:42:10"              # DateTime
    exif[0x8769] = {                                  # Exif IFD
        0x829A: IFDRational(1, 120),                  # ExposureTime
        0x829D: IFDRational(17, 10),                  # FNumber
        0x8827: (200,),                               # ISOSpeedRatings
        0x9003: "2025:09:30 17:42:10",                # DateTimeOriginal
        0x920A: IFDRational(43, 10),                  # FocalLength
    }
    if gps:
        lat, lon = gps
        exif[0x8825] = {
            1: "N" if lat >= 0 else "S",
            2: _dms_tuple(lat),
            3: "E" if lon >= 0 else "W",
            4: _dms_tuple(lon),
            6: Fraction(910, 1),                      # GPSAltitude
        }
    return exif.tobytes()


def create_sample_photo(
    destination: str | Path,
    width: int = 1600,
    height: int = 1000,
    with_gps: bool = True,
) -> Path:
    """Render the sample photo with EXIF metadata and save it to ``destination``."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    horizon = int(height * 0.62)
    _sky(draw, width, horizon)
    image = _sun(image, width * 0.63, horizon - height * 0.13, height * 0.17)
    draw = ImageDraw.Draw(image)
    _mountains(draw, width, height, horizon)
    _water(image, width, height, horizon)
    _grain(image)
    image = image.filter(ImageFilter.GaussianBlur(0.4))

    image.save(
        path,
        format="JPEG",
        quality=94,
        exif=build_exif_bytes(PETRA if with_gps else None),
    )
    return path.resolve()


def create_sample_set(directory: str | Path) -> dict[str, Path]:
    """Create the demo corpus: GPS photo, clean PNG, animated GIF, duplicate."""
    base = Path(directory)
    photo = create_sample_photo(base / "petra_sunset.jpg")

    # A metadata-free PNG (simple synthetic chart).
    chart = Image.new("RGB", (800, 480), (250, 250, 252))
    chart_draw = ImageDraw.Draw(chart)
    for i in range(6):
        y = 40 + i * 80
        chart_draw.line([(60, y), (760, y)], fill=(225, 228, 233), width=1)
    points = [(60 + i * 140, 400 - [120, 210, 160, 300, 250, 340][i]) for i in range(6)]
    chart_draw.line(points, fill=(59, 110, 246), width=5, joint="curve")
    for point in points:
        chart_draw.ellipse([point[0] - 7, point[1] - 7, point[0] + 7, point[1] + 7],
                           fill=(59, 110, 246))
    chart_path = base / "monthly_views.png"
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart.save(chart_path, format="PNG")

    # A tiny animation.
    frames = []
    for index in range(3):
        frame = Image.new("RGB", (240, 160), (24 + index * 26, 30, 44))
        frame_draw = ImageDraw.Draw(frame)
        x = 40 + index * 70
        frame_draw.ellipse([x, 60, x + 44, 104], fill=(247, 200, 104))
        frames.append(frame)
    gif_path = base / "loop.gif"
    frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                   duration=350, loop=0, comment=b"ImageInfo sample animation")

    # A byte-level duplicate of the photo for the duplicates finder.
    duplicate_path = base / "petra_sunset (copy).jpg"
    duplicate_path.write_bytes(photo.read_bytes())

    return {
        "photo": photo,
        "clean_png": chart_path,
        "animation": gif_path,
        "duplicate": duplicate_path,
    }


def _self_check() -> None:
    """Verify the sample photo round-trips through the EXIF parser."""
    import tempfile

    from .exif import ExifData

    with tempfile.TemporaryDirectory() as tmp:
        photo = create_sample_photo(Path(tmp) / "check.jpg")
        data = ExifData.from_file(photo)
    assert data.camera == ("PixelWorks", "PW-7 Pro"), data.camera
    assert data.gps is not None
    lat, lon = data.gps
    expected_lat = dms_to_decimal(_dms_tuple(PETRA[0]), "N")
    expected_lon = dms_to_decimal(_dms_tuple(PETRA[1]), "E")
    assert abs(lat - expected_lat) < 1e-6 and abs(lon - expected_lon) < 1e-6


if __name__ == "__main__":
    _self_check()
    print("demo module OK")
