"""Core image inspection engine.

:class:`ImageInfo` is the heart of the library: point it at a file and you get
a fully populated snapshot of everything the file can tell about itself --
dimensions, colour mode, storage footprint, cryptographic and perceptual
hashes, dominant colours, brightness and more.

Example
-------
>>> from image_info import ImageInfo
>>> info = ImageInfo.from_file("photo.jpg")
>>> info.width, info.height, info.format
(4000, 3000, 'JPEG')
>>> info.sha256[:16]
'9f2c8a1e7b3d...'
"""

from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from PIL import Image, ImageStat

__all__ = [
    "ImageInfo",
    "DominantColor",
    "UnsupportedImageError",
    "human_size",
    "dhash",
    "dhash_hex",
    "hamming_distance",
    "dominant_colors",
    "SUPPORTED_EXTENSIONS",
]

#: File extensions recognised by the batch scanner.
SUPPORTED_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".heic", ".ico"}
)


class UnsupportedImageError(ValueError):
    """Raised when a file cannot be opened as an image."""


def human_size(nbytes: float) -> str:
    """Format a byte count as a human readable string (``4.2 MB``)."""
    if nbytes < 0:
        raise ValueError("byte count cannot be negative")
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    size = float(nbytes)
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)} B"
    return f"{size:.1f} {units[index]}"


def dhash(image: Image.Image, hash_size: int = 8) -> int:
    """Compute the difference hash (dHash) of an image.

    dHash resamples the image to ``(hash_size + 1) x hash_size`` greyscale and
    records whether each pixel is brighter than its left neighbour.  Visually
    similar images end up with nearly identical hashes, which makes it a cheap
    building block for duplicate detection.
    """
    grey = image.convert("L").resize(
        (hash_size + 1, hash_size), Image.Resampling.LANCZOS
    )
    pixels = list(grey.getdata())
    bits = 0
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for col in range(hash_size):
            left = pixels[row_start + col]
            right = pixels[row_start + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def dhash_hex(image: Image.Image, hash_size: int = 8) -> str:
    """Return :func:`dhash` formatted as a fixed width hex string."""
    width = (hash_size * hash_size + 3) // 4
    return f"{dhash(image, hash_size):0{width}x}"


def hamming_distance(a: int, b: int) -> int:
    """Number of differing bits between two integer hashes."""
    return bin(a ^ b).count("1")


def dominant_colors(image: Image.Image, count: int = 8) -> list["DominantColor"]:
    """Extract the ``count`` most representative colours of an image."""
    sample = image.convert("RGB")
    if sample.width * sample.height > 512 * 512:
        sample = sample.resize((512, 512), Image.Resampling.BILINEAR)
    quantized = sample.quantize(colors=count)
    palette = quantized.getpalette() or []
    counts: dict[int, int] = {}
    for index in quantized.getdata():
        counts[index] = counts.get(index, 0) + 1
    total = sum(counts.values()) or 1
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:count]
    result = []
    for index, hits in ordered:
        r, g, b = palette[index * 3 : index * 3 + 3]
        result.append(DominantColor(r, g, b, hits / total))
    return result


@dataclass(frozen=True)
class DominantColor:
    """A single entry of an image colour palette."""

    red: int
    green: int
    blue: int
    share: float

    @property
    def hex(self) -> str:
        return f"#{self.red:02X}{self.green:02X}{self.blue:02X}"

    def to_dict(self) -> dict[str, Any]:
        return {"hex": self.hex, "rgb": [self.red, self.green, self.blue],
                "share": round(self.share, 4)}


@dataclass
class ImageInfo:
    """A complete technical snapshot of a single image file."""

    path: str
    filename: str
    format: Optional[str]
    mode: str
    width: int
    height: int
    size_bytes: int
    is_animated: bool = False
    n_frames: int = 1
    has_transparency: bool = False
    dpi: Optional[tuple[float, float]] = None
    brightness: float = 0.0
    blake2b: str = ""
    sha256: str = ""
    dhash: str = ""
    dominant_colors: list[DominantColor] = field(default_factory=list)
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    error: Optional[str] = None

    # ------------------------------------------------------------------ #
    # construction
    # ------------------------------------------------------------------ #
    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> "ImageInfo":
        """Inspect ``path`` and return a populated :class:`ImageInfo`.

        Raises :class:`UnsupportedImageError` when the file cannot be decoded.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"no such file: {file_path}")
        if not file_path.is_file():
            raise IsADirectoryError(f"not a file: {file_path}")

        data = file_path.read_bytes()
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception as exc:  # noqa: BLE001 - Pillow raises many types
            raise UnsupportedImageError(
                f"{file_path.name} is not a readable image ({exc})"
            ) from exc

        stat = ImageStat.Stat(image.convert("L"))
        dpi_raw = image.info.get("dpi")
        dpi: Optional[tuple[float, float]] = None
        if dpi_raw:
            try:
                dpi = (float(dpi_raw[0]), float(dpi_raw[1]))
            except (TypeError, ValueError, IndexError):
                dpi = None

        created = None
        modified = None
        try:
            modified = datetime.fromtimestamp(file_path.stat().st_mtime)
            created = datetime.fromtimestamp(file_path.stat().st_ctime)
        except OSError:
            pass

        return cls(
            path=str(file_path.resolve()),
            filename=file_path.name,
            format=image.format,
            mode=image.mode,
            width=image.width,
            height=image.height,
            size_bytes=len(data),
            is_animated=bool(getattr(image, "is_animated", False)),
            n_frames=int(getattr(image, "n_frames", 1)),
            has_transparency="transparency" in image.info or image.mode in ("RGBA", "LA", "PA"),
            dpi=dpi,
            brightness=round(stat.mean[0], 1),
            blake2b=hashlib.blake2b(data, digest_size=16).hexdigest(),
            sha256=hashlib.sha256(data).hexdigest(),
            dhash=dhash_hex(image),
            dominant_colors=dominant_colors(image),
            created_at=created,
            modified_at=modified,
        )

    # ------------------------------------------------------------------ #
    # derived values
    # ------------------------------------------------------------------ #
    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 0.0

    @property
    def megapixels(self) -> float:
        return self.width * self.height / 1_000_000

    @property
    def human_size(self) -> str:
        return human_size(self.size_bytes)

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    # ------------------------------------------------------------------ #
    # export helpers
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "filename": self.filename,
            "format": self.format,
            "mode": self.mode,
            "width": self.width,
            "height": self.height,
            "resolution": self.resolution,
            "aspect_ratio": round(self.aspect_ratio, 4),
            "megapixels": round(self.megapixels, 2),
            "size_bytes": self.size_bytes,
            "human_size": self.human_size,
            "is_animated": self.is_animated,
            "n_frames": self.n_frames,
            "has_transparency": self.has_transparency,
            "dpi": list(self.dpi) if self.dpi else None,
            "brightness": self.brightness,
            "blake2b": self.blake2b,
            "sha256": self.sha256,
            "dhash": self.dhash,
            "dominant_colors": [c.to_dict() for c in self.dominant_colors],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
        }

    def summary(self) -> list[tuple[str, str]]:
        """Ordered ``(label, value)`` pairs used by the CLI ``info`` view."""
        pairs: list[tuple[str, str]] = [
            ("Filename", self.filename),
            ("Format", self.format or "unknown"),
            ("Resolution", f"{self.resolution}  ({self.megapixels:.1f} MP)"),
            ("Colour mode", self.mode),
            ("File size", f"{self.human_size}  ({self.size_bytes:,} bytes)"),
            ("Animated", str(self.is_animated)),
            ("Frames", str(self.n_frames)),
            ("Transparency", str(self.has_transparency)),
            ("DPI", str(tuple(round(v, 1) for v in self.dpi)) if self.dpi else "not stored"),
            ("Brightness", f"{self.brightness} / 255"),
            ("BLAKE2b", self.blake2b),
            ("SHA-256", self.sha256),
            ("Perceptual hash", self.dhash),
        ]
        if self.modified_at:
            pairs.append(("Modified", self.modified_at.strftime("%Y-%m-%d %H:%M:%S")))
        return pairs

    def looks_like_duplicate_of(self, other: "ImageInfo", threshold: int = 8) -> bool:
        """True when this image is visually similar to ``other``.

        Two images are considered duplicates when their perceptual hashes
        differ by at most ``threshold`` bits.
        """
        if not self.dhash or not other.dhash:
            return False
        return hamming_distance(int(self.dhash, 16), int(other.dhash, 16)) <= threshold
