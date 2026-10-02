"""Reclaim disk space: find and report duplicate images in a folder.

Uses perceptual hashing, so renamed, re-saved and re-compressed copies are
still detected - not just byte-identical files.

Run:  python examples/find_duplicates.py [folder]
"""

import sys
from pathlib import Path

from image_info import find_duplicates, scan_directory


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    if not folder.is_dir():
        raise SystemExit(f"not a folder: {folder}")

    print(f"Scanning {folder.resolve()} ...")
    infos = scan_directory(folder, recursive=True)
    print(f"Found {len(infos)} image(s)\n")

    groups = find_duplicates(infos)
    if not groups:
        print("No duplicates - your library is clean.")
        return

    wasted = 0
    for number, group in enumerate(groups, start=1):
        print(f"Group {number}:")
        for info in group:
            print(f"  {info.filename}  ({info.human_size}, {info.resolution})")
        redundant = group[1:]
        wasted += sum(info.size_bytes for info in redundant)
        keep = min(redundant + [group[0]], key=lambda i: i.filename).filename
        print(f"  -> keep one, e.g. '{keep}', delete the rest\n")

    print(f"Total recoverable: {wasted:,} bytes")


if __name__ == "__main__":
    main()
