"""Image_info - inspect, audit and clean image metadata.

A batteries-included toolkit built on Pillow:

* :class:`ImageInfo` - one-call technical snapshot (dimensions, hashes,
  palette, brightness, ...)
* :class:`ExifData` - human friendly EXIF/GPS parsing
* :func:`analyze_privacy` / :func:`strip_metadata` - find and remove what a
  photo leaks about you
* ``imageinfo`` - a full command line interface (see ``imageinfo --help``)

Quick start::

    from image_info import analyze

    result = analyze("photo.jpg")
    print(result.info.resolution, result.exif.camera, result.privacy.risk_level)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from .core import DominantColor, ImageInfo, hamming_distance, human_size
from .exif import ExifData, dms_to_decimal
from .export import find_duplicates, scan_directory, to_csv, to_json
from .privacy import PrivacyReport, analyze_privacy, strip_metadata

__version__ = "2.0.0"
__all__ = [
    "ImageInfo", "ExifData", "PrivacyReport", "DominantColor", "Analysis",
    "analyze", "analyze_privacy", "strip_metadata", "scan_directory",
    "find_duplicates", "to_json", "to_csv", "dms_to_decimal", "hamming_distance",
    "human_size", "__version__",
]


@dataclass
class Analysis:
    """Everything :func:`analyze` could extract from one image."""

    path: Path
    info: ImageInfo
    exif: ExifData
    privacy: PrivacyReport
    address: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "info": self.info.to_dict(),
            "exif": self.exif.to_dict(),
            "privacy": self.privacy.to_dict(),
            "address": self.address,
        }


def analyze(
    source: Union[str, Path],
    geocode: bool = False,
) -> Analysis:
    """Full analysis of one image in a single call.

    With ``geocode=True`` the GPS coordinates (when present) are also resolved
    to a place name through the Nominatim service; offline environments simply
    leave :attr:`Analysis.address` as ``None``.
    """
    path = Path(source)
    info = ImageInfo.from_file(path)
    exif = ExifData.from_file(path)
    privacy = analyze_privacy(path, info=info, exif=exif)
    address = None
    if geocode and exif.has_gps:
        from .maps import reverse_geocode

        address = reverse_geocode(*exif.gps)  # type: ignore[misc]
    return Analysis(path=path, info=info, exif=exif, privacy=privacy, address=address)
