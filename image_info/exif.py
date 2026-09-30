"""EXIF and container metadata parsing, including GPS coordinates.

The :class:`ExifData` class turns the semi-structured tag soup inside a photo
into a typed, human friendly object:

* tag ids are translated to readable names (``0x0110`` -> ``Model``),
* rational values become plain floats, byte blobs become text,
* GPS IFD entries are converted to decimal degrees,
* sub-IFDs (Exif, GPS, Interop) are kept separately but searchable.

Example
-------
>>> from image_info.exif import ExifData
>>> data = ExifData.from_file("photo.jpg")
>>> data.camera
('samsung', 'SM-N986B')
>>> data.gps
(30.328500, 35.444389)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Optional

from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS
from PIL.TiffImagePlugin import IFDRational

# IFD pointer tags understood by Pillow's ``getexif``.
_TAG_EXIF_IFD = 0x8769      # 34665
_TAG_GPS_IFD = 0x8825       # 34853
_TAG_INTEROP_IFD = 0xA005   # 40965

_IFD_NAMES = {
    _TAG_EXIF_IFD: "Exif",
    _TAG_GPS_IFD: "GPS",
    _TAG_INTEROP_IFD: "Interop",
}

__all__ = ["ExifData", "clean_value", "dms_to_decimal"]


def clean_value(value: Any) -> Any:
    """Normalise a raw Pillow metadata value into JSON friendly Python.

    ``IFDRational`` -> float, tuples of rationals -> tuples of floats,
    byte strings are decoded with a lossy codec so exotic firmwares cannot
    crash the parser.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").rstrip("\x00")
    if isinstance(value, (Fraction, IFDRational)):
        return float(value)
    if isinstance(value, tuple):
        return tuple(clean_value(item) for item in value)
    if isinstance(value, list):
        return [clean_value(item) for item in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


def dms_to_decimal(dms: tuple[float, float, float], ref: str) -> float:
    """Convert ``degrees, minutes, seconds`` plus hemisphere ref to decimal degrees."""
    degrees, minutes, seconds = (float(part) for part in dms)
    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    if str(ref).upper().strip() in ("S", "W"):
        decimal = -decimal
    return round(decimal, 6)


def _label(tag_id: int, names: dict[int, str]) -> str:
    return names.get(tag_id, f"Tag_{tag_id}")


@dataclass
class ExifData:
    """Parsed EXIF metadata of one image."""

    tags: dict[str, Any] = field(default_factory=dict)
    sub_ifds: dict[str, dict[str, Any]] = field(default_factory=dict)
    xmp: Optional[str] = None
    comment: Optional[str] = None

    # ------------------------------------------------------------------ #
    @classmethod
    def from_image(cls, image: Image.Image) -> "ExifData":
        """Parse metadata from an already opened Pillow image."""
        tags: dict[str, Any] = {}
        sub_ifds: dict[str, dict[str, Any]] = {}

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            exif = image.getexif()

        for tag_id, raw in exif.items():
            if tag_id in _IFD_NAMES:
                pointer_name = _IFD_NAMES[tag_id]
                ifd: dict[str, Any] = {}
                try:
                    sub = exif.get_ifd(tag_id)
                    for sub_id, sub_raw in sub.items():
                        names = GPSTAGS if tag_id == _TAG_GPS_IFD else TAGS
                        ifd[_label(sub_id, names)] = clean_value(sub_raw)
                except Exception:  # noqa: BLE001 - malformed IFDs happen in the wild
                    pass
                sub_ifds[pointer_name] = ifd
            else:
                tags[_label(tag_id, TAGS)] = clean_value(raw)

        xmp = image.info.get("XML:com.adobe.xmp")
        if isinstance(xmp, bytes):
            xmp = xmp.decode("utf-8", errors="replace")
        comment = image.info.get("comment")
        if isinstance(comment, bytes):
            comment = comment.decode("utf-8", errors="replace")

        return cls(tags=tags, sub_ifds=sub_ifds, xmp=xmp, comment=comment)

    @classmethod
    def from_file(cls, path: str | Path) -> "ExifData":
        """Open ``path`` and parse its metadata."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"no such file: {file_path}")
        from .core import UnsupportedImageError

        try:
            with Image.open(file_path) as image:
                return cls.from_image(image)
        except UnsupportedImageError:
            raise
        except Exception as exc:  # noqa: BLE001 - Pillow raises several types
            raise UnsupportedImageError(
                f"{file_path.name} is not a readable image ({exc})"
            ) from exc

    # ------------------------------------------------------------------ #
    # GPS helpers
    # ------------------------------------------------------------------ #
    @property
    def gps_ifd(self) -> dict[str, Any]:
        return self.sub_ifds.get("GPS", {})

    @property
    def gps(self) -> Optional[tuple[float, float]]:
        """Decimal ``(latitude, longitude)`` or ``None`` when no GPS fix exists."""
        gps = self.gps_ifd
        lat_dms = gps.get("GPSLatitude")
        lon_dms = gps.get("GPSLongitude")
        lat_ref = gps.get("GPSLatitudeRef", "")
        lon_ref = gps.get("GPSLongitudeRef", "")
        if not lat_dms or not lon_dms or not lat_ref or not lon_ref:
            return None
        try:
            lat = dms_to_decimal(lat_dms, str(lat_ref))  # type: ignore[arg-type]
            lon = dms_to_decimal(lon_dms, str(lon_ref))  # type: ignore[arg-type]
        except (TypeError, ValueError, ZeroDivisionError):
            return None
        return (lat, lon)

    @property
    def gps_altitude(self) -> Optional[float]:
        altitude = self.gps_ifd.get("GPSAltitude")
        try:
            return float(altitude) if altitude is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def has_gps(self) -> bool:
        return self.gps is not None

    # ------------------------------------------------------------------ #
    # convenience accessors
    # ------------------------------------------------------------------ #
    @property
    def camera(self) -> Optional[tuple[str, str]]:
        """``(make, model)`` or ``None``."""
        make = self.tags.get("Make") or self.tags.get("Model")
        if make is None:
            return None
        return (self.tags.get("Make", ""), self.tags.get("Model", ""))

    @property
    def datetime_original(self) -> Optional[str]:
        for key in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
            value = self.tags.get(key) or self.sub_ifds.get("Exif", {}).get(key)
            if value:
                return str(value)
        return None

    @property
    def software(self) -> Optional[str]:
        return self.tags.get("Software") or self.sub_ifds.get("Exif", {}).get("Software")

    def flat_table(self) -> list[tuple[str, str]]:
        """Flatten all metadata into ordered ``(dotted.path, value)`` rows."""
        rows: list[tuple[str, str]] = []
        for key, value in self.tags.items():
            rows.append((key, _stringify(value)))
        for ifd_name, ifd in self.sub_ifds.items():
            for key, value in ifd.items():
                rows.append((f"{ifd_name}.{key}", _stringify(value)))
        if self.comment:
            rows.append(("Container.comment", _stringify(self.comment)))
        if self.xmp:
            rows.append(("Container.XMP", f"{len(self.xmp)} bytes of XMP metadata"))
        return rows

    def to_dict(self) -> dict[str, Any]:
        gps = self.gps
        return {
            "tags": self.tags,
            "sub_ifds": self.sub_ifds,
            "has_xmp": self.xmp is not None,
            "comment": self.comment,
            "gps": {"latitude": gps[0], "longitude": gps[1]} if gps else None,
            "gps_altitude": self.gps_altitude,
        }

    def tag_count(self) -> int:
        return len(self.tags) + sum(len(ifd) for ifd in self.sub_ifds.values())


def _stringify(value: Any, limit: int = 96) -> str:
    text = str(value)
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text
