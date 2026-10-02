"""Batch operations: directory scanning, exports and duplicate detection.

Example
-------
>>> from image_info.export import scan_directory, find_duplicates, write_json
>>> infos = scan_directory("~/Pictures", recursive=True)
>>> find_duplicates(infos)
[[ImageInfo(filename='IMG_0001.jpg'), ImageInfo(filename='copy_of_IMG_0001.jpg')]]
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Iterable, Sequence, Union

from .core import SUPPORTED_EXTENSIONS, ImageInfo, hamming_distance

__all__ = [
    "scan_directory",
    "find_duplicates",
    "to_json",
    "write_json",
    "to_csv",
    "write_csv",
]

PathLike = Union[str, Path]

_CSV_COLUMNS = (
    "filename", "format", "width", "height", "megapixels", "size_bytes",
    "human_size", "mode", "is_animated", "dhash", "blake2b", "sha256", "path",
)


def scan_directory(
    root: PathLike,
    recursive: bool = False,
    skip_errors: bool = True,
) -> list[ImageInfo]:
    """Inspect every supported image under ``root``.

    With ``recursive=False`` only files directly inside ``root`` are read.
    Broken or unrelated files are skipped when ``skip_errors`` is true,
    otherwise the first unreadable file raises.
    """
    base = Path(root).expanduser()
    if not base.is_dir():
        raise NotADirectoryError(f"not a directory: {base}")

    pattern = "**/*" if recursive else "*"
    infos: list[ImageInfo] = []
    for candidate in sorted(base.glob(pattern)):
        if not candidate.is_file() or candidate.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            infos.append(ImageInfo.from_file(candidate))
        except Exception:  # noqa: BLE001
            if not skip_errors:
                raise
    return infos


def find_duplicates(
    images: Union[PathLike, Iterable[ImageInfo]],
    threshold: int = 8,
    brightness_tolerance: float = 16.0,
    recursive: bool = True,
) -> list[list[ImageInfo]]:
    """Group visually identical images using their perceptual hashes.

    ``images`` is either a directory (scanned for you) or a pre-built sequence
    of :class:`~image_info.core.ImageInfo`.  Two images land in the same group
    when their dHash values differ by at most ``threshold`` bits *and* their
    mean brightness differs by at most ``brightness_tolerance``/255 - the
    brightness tie-breaker keeps solid-colour images (whose dHash is always
    all-zero) from being merged with each other.
    """
    if isinstance(images, (str, Path)):
        infos = scan_directory(images, recursive=recursive)
    else:
        infos = [info for info in images if info.dhash]
    if len(infos) < 2:
        return []

    unique_hashes = {int(info.dhash, 16) for info in infos}
    # representative brightness per unique hash, used as tie-breaker
    brightness = {}
    for info in infos:
        brightness.setdefault(int(info.dhash, 16), info.brightness)

    ordered = sorted(unique_hashes)
    parent = {h: h for h in unique_hashes}

    def find(h: int) -> int:
        while parent[h] != h:
            parent[h] = parent[parent[h]]
            h = parent[h]
        return h

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if hamming_distance(a, b) <= threshold and abs(
                brightness[a] - brightness[b]
            ) <= brightness_tolerance:
                union(a, b)

    groups: dict[int, list[ImageInfo]] = {}
    for info in infos:
        groups.setdefault(find(int(info.dhash, 16)), []).append(info)

    result: list[list[ImageInfo]] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        for cluster in _split_by_brightness(group, brightness_tolerance):
            if len(cluster) > 1:
                result.append(sorted(cluster, key=lambda i: i.filename))
    return result


def _split_by_brightness(group: list[ImageInfo], tolerance: float) -> list[list[ImageInfo]]:
    """Split a hash-identical group so brightness gaps break clusters apart."""
    ordered = sorted(group, key=lambda info: info.brightness)
    clusters: list[list[ImageInfo]] = []
    current = [ordered[0]]
    for info in ordered[1:]:
        if info.brightness - current[-1].brightness <= tolerance:
            current.append(info)
        else:
            clusters.append(current)
            current = [info]
    clusters.append(current)
    return clusters


def to_json(data: Union[ImageInfo, PrivacyLike, Sequence], indent: int = 2) -> str:
    """Serialize an :class:`ImageInfo` or a sequence of them to JSON text."""
    if isinstance(data, ImageInfo):
        payload = data.to_dict()
    elif isinstance(data, Sequence):
        payload = [item.to_dict() if isinstance(item, ImageInfo) else item
                   for item in data]
    else:
        payload = data  # type: ignore[assignment]
    return json.dumps(payload, indent=indent, ensure_ascii=False, default=str)


def write_json(data: Union[ImageInfo, Sequence], path: PathLike, indent: int = 2) -> Path:
    """Write :func:`to_json` output to ``path`` and return it."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(to_json(data, indent=indent), encoding="utf-8")
    return target


def to_csv(infos: Iterable[ImageInfo]) -> str:
    """Serialize a collection of :class:`ImageInfo` rows as CSV text."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for info in infos:
        row = info.to_dict()
        row["megapixels"] = f"{info.megapixels:.2f}"
        writer.writerow(row)
    return buffer.getvalue()


def write_csv(infos: Iterable[ImageInfo], path: PathLike) -> Path:
    """Write :func:`to_csv` output to ``path`` and return it."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(to_csv(infos), encoding="utf-8")
    return target
