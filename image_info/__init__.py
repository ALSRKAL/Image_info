"""Image_info - inspect, audit and clean image metadata.

A batteries-included toolkit built on Pillow:

* :class:`ImageInfo` - one-call technical snapshot (dimensions, hashes,
  palette, brightness, ...)
* :class:`ExifData` - human friendly EXIF/GPS parsing

Quick start::

    from image_info import ImageInfo, ExifData

    info = ImageInfo.from_file("photo.jpg")
    exif = ExifData.from_file("photo.jpg")
    print(info.resolution, exif.camera)
"""

from __future__ import annotations

from .core import DominantColor, ImageInfo, hamming_distance, human_size
from .exif import ExifData, dms_to_decimal

__version__ = "2.0.0"
__all__ = [
    "ImageInfo", "ExifData", "DominantColor",
    "dms_to_decimal", "hamming_distance", "human_size", "__version__",
]
