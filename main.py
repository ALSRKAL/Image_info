#!/usr/bin/env python3
"""Convenience entry point kept for the original workflow.

Running this file without arguments opens a graphical file picker (when the
optional ``easygui`` package is installed) and prints the full analysis of the
chosen image - exactly what the 2022 original did, now powered by the modern
``image_info`` engine.  Any extra arguments are forwarded to the ``imageinfo``
CLI, so ``python main.py info photo.jpg`` works too.
"""

from __future__ import annotations

import sys


def _interactive_path() -> str | None:
    """Ask the user for an image via a file dialog when possible."""
    try:
        import easygui
    except ImportError:
        return None
    return easygui.fileopenbox(msg="Pick an image to inspect",
                               title="Image_info")


def main() -> int:
    from image_info import ImageInfo, ExifData, analyze_privacy
    from image_info.cli import main as cli_main

    args = sys.argv[1:]
    if args:
        return cli_main(args)

    path = _interactive_path()
    if not path:
        print("No file selected (or easygui missing).")
        print("Tip: use the CLI instead, e.g.  imageinfo info photo.jpg")
        return 1

    info = ImageInfo.from_file(path)
    exif = ExifData.from_file(path)
    privacy = analyze_privacy(path, info=info, exif=exif)

    print(f"Analysis of {info.filename}\n")
    for label, value in info.summary():
        print(f"  {label:20}: {value}")
    print(f"\n  EXIF tags           : {exif.tag_count()}")
    print(f"  GPS                 : "
          + (f"{exif.gps[0]:.6f}, {exif.gps[1]:.6f}" if exif.gps else "not present"))
    print(f"  Privacy risk        : {privacy.risk_level} ({privacy.risk_score}/100)")
    print("\nFor the full report:  imageinfo report \"" + info.path + "\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
