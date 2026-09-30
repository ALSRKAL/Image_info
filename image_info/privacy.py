"""Privacy auditing and metadata stripping.

Photos quietly carry a lot of personal information: where they were taken,
which device took them, when, sometimes even serial numbers and the owner's
name.  :func:`analyze_privacy` scores that exposure on a 0-100 scale and
:func:`strip_metadata` produces a clean copy with all of it removed.

Example
-------
>>> from image_info.privacy import analyze_privacy, strip_metadata
>>> report = analyze_privacy("IMG_20250930_174210.jpg")
>>> report.risk_level
'High'
>>> strip_metadata("IMG_20250930_174210.jpg", "safe_copy.jpg")
{'removed_exif_tags': 42, 'removed_gps': True, ...}
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from PIL import Image, ImageOps

from .core import ImageInfo
from .exif import ExifData

__all__ = ["PrivacyFinding", "PrivacyReport", "analyze_privacy", "strip_metadata"]


@dataclass(frozen=True)
class PrivacyFinding:
    """One piece of sensitive metadata discovered in a file."""

    category: str          # e.g. "Location", "Device", "Timeline"
    key: str               # metadata key, e.g. "GPS.latitude"
    detail: str            # human readable explanation
    severity: str          # "low" | "medium" | "high"
    points: int            # contribution to the risk score


@dataclass
class PrivacyReport:
    """Aggregated privacy exposure of a single image."""

    path: str
    findings: list[PrivacyFinding] = field(default_factory=list)

    @property
    def risk_score(self) -> int:
        return min(100, sum(f.points for f in self.findings))

    @property
    def risk_level(self) -> str:
        score = self.risk_score
        if score < 20:
            return "Low"
        if score < 50:
            return "Medium"
        if score < 75:
            return "High"
        return "Critical"

    @property
    def has_location(self) -> bool:
        return any(f.category == "Location" for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "has_location": self.has_location,
            "findings": [
                {
                    "category": f.category,
                    "key": f.key,
                    "detail": f.detail,
                    "severity": f.severity,
                    "points": f.points,
                }
                for f in self.findings
            ],
        }

    def table(self) -> list[tuple[str, str, str, str]]:
        """Rows of ``(category, key, detail, severity)`` for CLI rendering."""
        return [(f.category, f.key, f.detail, f.severity) for f in self.findings]


_SERIALIZABLE_KEYS = ("BodySerialNumber", "LensSerialNumber", "InternalSerialNumber",
                      "CameraSerialNumber", "OwnerName", "Artist", "Copyright",
                      "UserComment", "ImageUniqueID")

_SCORES = {
    "gps": ("Location", "high", 45),
    "device": ("Device", "medium", 12),
    "timestamp": ("Timeline", "medium", 12),
    "software": ("Software", "low", 5),
    "serial": ("Identity", "high", 10),
    "owner": ("Identity", "medium", 8),
    "comment": ("Comments", "medium", 8),
    "xmp": ("Container", "low", 6),
    "text_chunks": ("Container", "low", 5),
    "file_times": ("Filesystem", "low", 4),
}


def _finding(kind: str, key: str, detail: str) -> PrivacyFinding:
    category, severity, points = _SCORES[kind]
    return PrivacyFinding(category, key, detail, severity, points)


def analyze_privacy(
    source: Union[str, Path, ImageInfo, ExifData],
    info: Optional[ImageInfo] = None,
    exif: Optional[ExifData] = None,
) -> PrivacyReport:
    """Audit ``source`` and return a :class:`PrivacyReport`.

    ``source`` may be a path, an :class:`~image_info.core.ImageInfo` or an
    :class:`~image_info.exif.ExifData`; pass ``info`` and/or ``exif`` together
    with a path to reuse already-computed objects instead of re-reading.
    """
    path_str = ""
    if isinstance(source, (str, Path)):
        path_str = str(source)
        if exif is None:
            exif = ExifData.from_file(source)
        if info is None:
            info = ImageInfo.from_file(source)
    elif isinstance(source, ExifData):
        exif = source
    elif isinstance(source, ImageInfo):
        info = source
    if exif is None:
        exif = ExifData()

    findings: list[PrivacyFinding] = []

    if exif.has_gps:
        lat, lon = exif.gps  # type: ignore[misc]
        altitude = f", altitude {exif.gps_altitude:.0f} m" if exif.gps_altitude else ""
        findings.append(_finding(
            "gps", "GPS.latitude/longitude",
            f"Exact capture location: {lat:.5f}, {lon:.5f}{altitude}",
        ))

    camera = exif.camera
    if camera and any(camera):
        findings.append(_finding(
            "device", "EXIF.Make/Model",
            f"Device fingerprint: {camera[0] or '?'} {camera[1] or '?'}".rstrip(),
        ))

    when = exif.datetime_original
    if when:
        findings.append(_finding(
            "timestamp", "EXIF.DateTimeOriginal",
            f"Capture timestamp: {when}",
        ))

    if exif.software:
        findings.append(_finding(
            "software", "EXIF.Software",
            f"Editing/capture software: {exif.software}",
        ))

    for key in _SERIALIZABLE_KEYS:
        value = exif.tags.get(key) or exif.sub_ifds.get("Exif", {}).get(key)
        if value:
            kind = "serial" if "Serial" in key or key == "ImageUniqueID" else (
                "owner" if key in ("Artist", "Copyright", "OwnerName") else "comment"
            )
            preview = str(value)
            if len(preview) > 64:
                preview = preview[:61] + "..."
            findings.append(_finding(kind, f"EXIF.{key}", f"Stored value: {preview}"))

    if exif.xmp:
        findings.append(_finding(
            "xmp", "XMP packet",
            f"XMP metadata present ({len(exif.xmp):,} bytes) - may embed "
            "history, location or authorship data",
        ))

    if exif.comment:
        findings.append(_finding(
            "comment", "Container.comment",
            f"Embedded comment: {str(exif.comment)[:64]}",
        ))

    if info is not None and info.modified_at:
        findings.append(_finding(
            "file_times", "filesystem.mtime",
            f"File modified at {info.modified_at:%Y-%m-%d %H:%M:%S}",
        ))

    return PrivacyReport(path=path_str, findings=findings)


# Formats we know how to re-encode when stripping metadata.
_FORMAT_BY_SUFFIX = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP",
    ".gif": "GIF", ".bmp": "BMP", ".tif": "TIFF", ".tiff": "TIFF",
}


def strip_metadata(
    source: Union[str, Path],
    destination: Union[str, Path],
    quality: int = 92,
    auto_rotate: bool = True,
) -> dict[str, Any]:
    """Write a metadata-free copy of ``source`` to ``destination``.

    Only raw pixels travel to the new file: EXIF, GPS, XMP, comments and
    colour profiles are all dropped.  ``auto_rotate`` bakes the EXIF
    orientation into the pixels first, so the clean copy still displays
    upright after the orientation tag is gone.

    Returns a small report describing what was removed.
    """
    src = Path(source).resolve()
    dst = Path(destination)
    if not src.exists():
        raise FileNotFoundError(f"no such file: {src}")
    dst = dst.resolve()
    if dst == src:
        raise ValueError(
            "destination must differ from the source file - stripping re-encodes "
            "the pixels and must never overwrite the original in place"
        )

    before = ExifData.from_file(src)
    before_bytes = src.stat().st_size

    with Image.open(src) as opened:
        opened.load()
        if auto_rotate:
            try:
                opened = ImageOps.exif_transpose(opened) or opened
            except Exception:  # noqa: BLE001 - orientation tag can be malformed
                pass
        src_format = opened.format or "PNG"

        frames: list[Image.Image] = []
        frame_count = getattr(opened, "n_frames", 1)
        for index in range(frame_count):
            opened.seek(index)
            frames.append(_clean_pixels(opened))
        animation_info = {
            "duration": opened.info.get("duration"),
            "loop": opened.info.get("loop"),
        }

    dst_format = _FORMAT_BY_SUFFIX.get(dst.suffix.lower(), src_format)
    first = frames[0]
    if dst_format == "JPEG" and first.mode not in ("RGB", "L"):
        frames = [f.convert("RGB") for f in frames]
        first = frames[0]

    dst.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs: dict[str, Any] = {}
    if dst_format == "JPEG":
        save_kwargs = {"quality": quality, "optimize": True}
    if len(frames) > 1 and dst_format in ("GIF", "WEBP"):
        first.save(
            dst, format=dst_format, save_all=True, append_images=frames[1:],
            duration=animation_info["duration"], loop=animation_info["loop"] or 0,
            **save_kwargs,
        )
    else:
        first.save(dst, format=dst_format, **save_kwargs)

    after = ExifData.from_file(dst)
    return {
        "source": str(src),
        "destination": str(dst),
        "removed_exif_tags": before.tag_count(),
        "remaining_exif_tags": after.tag_count(),
        "removed_gps": before.has_gps and not after.has_gps,
        "before_bytes": before_bytes,
        "after_bytes": dst.stat().st_size,
        "format": dst_format,
    }


def _clean_pixels(image: Image.Image) -> Image.Image:
    """Rebuild an image from raw pixel values only - no metadata attached."""
    clean = Image.new(image.mode, image.size)
    clean.putdata(list(image.getdata()))
    return clean
