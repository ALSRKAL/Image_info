"""Image_info - inspect, audit and clean image metadata.

A batteries-included toolkit built on Pillow:

* :class:`ImageInfo` - one-call technical snapshot (dimensions, hashes,
  palette, brightness, ...)

Quick start::

    from image_info import ImageInfo

    info = ImageInfo.from_file("photo.jpg")
    print(info.resolution, info.human_size, info.sha256)
"""

from __future__ import annotations

from .core import DominantColor, ImageInfo, hamming_distance, human_size

__version__ = "2.0.0"
__all__ = [
    "ImageInfo", "DominantColor",
    "hamming_distance", "human_size", "__version__",
]
