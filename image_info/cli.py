"""The ``imageinfo`` command line interface.

Every library feature is reachable from the shell::

    imageinfo info photo.jpg          # technical snapshot
    imageinfo privacy photo.jpg       # what does this photo leak?
    imageinfo strip photo.jpg -o clean.jpg
    imageinfo report photo.jpg -o report.html
    imageinfo scan ~/Pictures -r      # batch inspection
    imageinfo demo                    # try it with generated samples

Run ``imageinfo --help`` or ``imageinfo <command> --help`` for details.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .core import ImageInfo, UnsupportedImageError, hamming_distance
from .demo import create_sample_set
from .exif import ExifData
from .export import find_duplicates, scan_directory, write_csv
from .maps import save_map
from .privacy import analyze_privacy, strip_metadata
from .report import generate_report
from .visualize import render_histogram, render_palette

# --------------------------------------------------------------------------- #
# terminal styling
# --------------------------------------------------------------------------- #


class _Style:
    """Minimal ANSI styling that disables itself on pipes and NO_COLOR."""

    def __init__(self) -> None:
        enabled = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.bold = "\033[1m" if enabled else ""
        self.dim = "\033[2m" if enabled else ""
        self.cyan = "\033[36m" if enabled else ""
        self.green = "\033[32m" if enabled else ""
        self.yellow = "\033[33m" if enabled else ""
        self.red = "\033[31m" if enabled else ""
        self.magenta = "\033[35m" if enabled else ""
        self.reset = "\033[0m" if enabled else ""


_RISK_COLORS = {"Low": "green", "Medium": "yellow", "High": "red",
                "Critical": "magenta"}


def _kv_table(style: _Style, pairs: Sequence[tuple[str, str]], indent: str = "  ") -> None:
    width = max(len(key) for key, _ in pairs)
    for key, value in pairs:
        print(f"{indent}{style.cyan}{key.ljust(width)}{style.reset}  {value}")


def _print_error(message: str) -> None:
    style = _Style()
    print(f"{style.red}error:{style.reset} {message}", file=sys.stderr)


def _load_info(path: str) -> ImageInfo:
    try:
        return ImageInfo.from_file(path)
    except FileNotFoundError:
        _print_error(f"file not found: {path}")
        raise SystemExit(1)
    except IsADirectoryError:
        _print_error(f"expected a file, got a directory: {path}")
        raise SystemExit(1)
    except UnsupportedImageError as exc:
        _print_error(str(exc))
        raise SystemExit(1)


# --------------------------------------------------------------------------- #
# command implementations
# --------------------------------------------------------------------------- #


def _cmd_info(args: argparse.Namespace) -> int:
    info = _load_info(args.path)
    if args.json:
        print(json.dumps(info.to_dict(), indent=2, ensure_ascii=False))
        return 0
    style = _Style()
    print(f"{style.bold}{info.filename}{style.reset}  {style.dim}({info.path}){style.reset}")
    _kv_table(style, info.summary())
    return 0


def _cmd_exif(args: argparse.Namespace) -> int:
    exif = _load_exif(args.path)
    if args.json:
        print(json.dumps(exif.to_dict(), indent=2, ensure_ascii=False))
        return 0
    style = _Style()
    if exif.tag_count() == 0 and not exif.xmp and not exif.comment:
        print(f"{style.dim}This file carries no EXIF metadata.{style.reset}")
        return 0
    for key, value in exif.flat_table():
        print(f"  {style.cyan}{key:<28}{style.reset} {value}")
    return 0


def _load_exif(path: str) -> ExifData:
    try:
        return ExifData.from_file(path)
    except FileNotFoundError:
        _print_error(f"file not found: {path}")
        raise SystemExit(1)
    except UnsupportedImageError as exc:
        _print_error(str(exc))
        raise SystemExit(1)


def _cmd_gps(args: argparse.Namespace) -> int:
    exif = _load_exif(args.path)
    coords = exif.gps
    if coords is None:
        if args.json:
            print(json.dumps({"gps": None}, indent=2))
        else:
            print("No GPS data embedded in this file.")
        return 0
    lat, lon = coords
    address = None
    if not args.no_geocode:
        from .maps import reverse_geocode

        address = reverse_geocode(lat, lon)

    if args.json:
        print(json.dumps({
            "latitude": lat, "longitude": lon,
            "altitude": exif.gps_altitude,
            "address": address,
        }, indent=2, ensure_ascii=False))
        return 0

    style = _Style()
    rows = [
        ("Latitude", f"{lat:.6f}"),
        ("Longitude", f"{lon:.6f}"),
        ("Altitude", f"{exif.gps_altitude:.0f} m" if exif.gps_altitude else "not stored"),
        ("Address", address or "lookup unavailable (offline?)"),
        ("Google Maps", f"https://www.google.com/maps?q={lat},{lon}"),
    ]
    _kv_table(style, rows)
    if args.map:
        out = save_map(lat, lon, args.map, address=address)
        print(f"\n{style.green}Map written to {out}{style.reset}")
    return 0


def _cmd_privacy(args: argparse.Namespace) -> int:
    report = analyze_privacy(args.path)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0
    style = _Style()
    color = getattr(style, _RISK_COLORS[report.risk_level])
    print(f"Privacy risk: {style.bold}{color}{report.risk_level}"
          f"{style.reset} {style.dim}({report.risk_score}/100){style.reset}")
    if not report.findings:
        print(f"  {style.dim}Nothing sensitive found.{style.reset}")
        return 0
    width = max(len(f.category) for f in report.findings)
    for finding in report.findings:
        severity_color = {"low": style.dim, "medium": style.yellow,
                          "high": style.red}.get(finding.severity, "")
        print(f"  {style.cyan}{finding.category.ljust(width)}{style.reset}  "
              f"{finding.detail}")
        print(f"  {style.dim}{' '.ljust(width)}  [{severity_color}"
              f"{finding.severity}{style.reset}{style.dim} {finding.key}]"
              f"{style.reset}")
    return 0


def _cmd_strip(args: argparse.Namespace) -> int:
    src = Path(args.path)
    dst = Path(args.output) if args.output else src.with_name(f"{src.stem}_clean{src.suffix}")
    result = strip_metadata(src, dst, quality=args.quality, auto_rotate=not args.no_rotate)
    style = _Style()
    saved = result["before_bytes"] - result["after_bytes"]
    print(f"{style.green}Stripped metadata:{style.reset} "
          f"{result['removed_exif_tags']} tag(s) removed, "
          f"GPS {'removed' if result['removed_gps'] else 'was not present'}")
    print(f"  {result['before_bytes']:,} B -> {result['after_bytes']:,} B "
          f"({saved:+,} B)  ->  {result['destination']}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    out = generate_report(
        args.path, args.output, include_charts=not args.no_charts,
        geocode=not args.no_geocode,
    )
    style = _Style()
    print(f"{style.green}Report written to {out}{style.reset}")
    return 0


def _cmd_histogram(args: argparse.Namespace) -> int:
    source = Path(args.path)
    out = Path(args.output) if args.output else source.with_suffix(".histogram.png")
    chart = render_histogram(source)
    chart.save(out, format="PNG")
    style = _Style()
    print(f"{style.green}Histogram written to {out.resolve()}{style.reset}")
    return 0


def _cmd_palette(args: argparse.Namespace) -> int:
    source = Path(args.path)
    out = Path(args.output) if args.output else source.with_suffix(".palette.png")
    chart = render_palette(source, count=args.count)
    chart.save(out, format="PNG")
    style = _Style()
    print(f"{style.green}Palette written to {out.resolve()}{style.reset}")
    return 0


def _cmd_hash(args: argparse.Namespace) -> int:
    infos = [_load_info(path) for path in args.paths]
    if args.json:
        print(json.dumps([i.to_dict() for i in infos], indent=2, ensure_ascii=False))
        return 0
    style = _Style()
    for info in infos:
        print(f"{style.bold}{info.filename}{style.reset}")
        _kv_table(style, [("BLAKE2b", info.blake2b), ("SHA-256", info.sha256),
                          ("dHash", info.dhash)])
        print()
    if len(infos) == 2:
        a, b = infos
        distance = hamming_distance(int(a.dhash, 16), int(b.dhash, 16))
        verdict = "identical" if distance == 0 else (
            "very similar" if distance <= 6 else (
                "similar" if distance <= args.threshold else "different"))
        print(f"Perceptual distance: {distance} bits -> {style.bold}{verdict}{style.reset}")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    a, b = _load_info(args.a), _load_info(args.b)
    distance = hamming_distance(int(a.dhash, 16), int(b.dhash, 16))
    style = _Style()
    same_file = a.blake2b == b.blake2b
    if same_file:
        verdict, verdict_color = "byte-identical copies", style.green
    elif distance == 0:
        verdict, verdict_color = "same pixels, different files", style.green
    elif distance <= 6:
        verdict, verdict_color = "very similar images", style.green
    elif distance <= args.threshold:
        verdict, verdict_color = "similar images", style.yellow
    else:
        verdict, verdict_color = "different images", style.red
    print(f"{a.filename}  vs  {b.filename}")
    _kv_table(style, [
        ("Resolution", f"{a.resolution} vs {b.resolution}"),
        ("Format", f"{a.format} vs {b.format}"),
        ("Perceptual distance", f"{distance} bits (threshold {args.threshold})"),
        ("Byte-identical", "yes" if same_file else "no"),
    ])
    print(f"\nVerdict: {verdict_color}{style.bold}{verdict}{style.reset}")
    return 0


def _cmd_convert(args: argparse.Namespace) -> int:
    from PIL import Image

    src = Path(args.path)
    fmt = (args.format or "").upper()
    if args.output:
        dst = Path(args.output)
        fmt = fmt or dst.suffix.lstrip(".").upper() or "PNG"
    else:
        fmt = fmt or "PNG"
        dst = src.with_suffix("." + fmt.lower())
    fmt = {"JPG": "JPEG", "TIF": "TIFF"}.get(fmt, fmt)
    with Image.open(src) as image:
        image.load()
        if fmt == "JPEG" and image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        dst.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs = {"quality": args.quality} if fmt == "JPEG" else {}
        image.save(dst, format=fmt, **save_kwargs)
    before, after = src.stat().st_size, dst.stat().st_size
    style = _Style()
    print(f"{style.green}Converted{style.reset} {src.name} -> {dst.name} "
          f"({fmt}, {before:,} B -> {after:,} B)")
    return 0


def _cmd_resize(args: argparse.Namespace) -> int:
    from PIL import Image

    src = Path(args.path)
    with Image.open(src) as image:
        image.load()
        width, height = args.width, args.height
        if width and not height:
            height = round(image.height * width / image.width)
        elif height and not width:
            width = round(image.width * height / image.height)
        elif not width and not height:
            _print_error("provide --width and/or --height")
            return 1
        resized = image.resize((width, height), Image.Resampling.LANCZOS)
        dst = Path(args.output) if args.output else src.with_name(
            f"{src.stem}_{width}x{height}{src.suffix}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs = {"quality": args.quality} if src.suffix.lower() in (".jpg", ".jpeg") else {}
        resized.save(dst, **save_kwargs)
    style = _Style()
    print(f"{style.green}Resized{style.reset} {src.name}: "
          f"{image.width}x{image.height} -> {width}x{height}  ->  {dst}")
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    try:
        infos = scan_directory(args.directory, recursive=args.recursive)
    except NotADirectoryError as exc:
        _print_error(str(exc))
        return 1
    if args.csv:
        out = write_csv(infos, args.csv)
        style = _Style()
        print(f"{style.green}CSV written to {out.resolve()}"
              f"{style.reset} ({len(infos)} image(s))")
        return 0
    if args.json:
        print(json.dumps([i.to_dict() for i in infos], indent=2, ensure_ascii=False))
        return 0
    style = _Style()
    if not infos:
        print(f"{style.dim}No images found.{style.reset}")
        return 0
    name_w = max(len(i.filename) for i in infos)
    print(f"  {style.cyan}{'Image'.ljust(name_w)}  {'Format':<6} {'Resolution':>11} "
          f"{'Size':>9}  Mode{style.reset}")
    for info in infos:
        print(f"  {info.filename.ljust(name_w)}  {info.format or '?':<6} "
              f"{info.resolution:>11} {info.human_size:>9}  {info.mode}")
    print(f"\n  {style.dim}{len(infos)} image(s) scanned{style.reset}")
    return 0


def _cmd_duplicates(args: argparse.Namespace) -> int:
    try:
        groups = find_duplicates(args.directory, threshold=args.threshold,
                                 recursive=args.recursive)
    except (NotADirectoryError, OSError) as exc:
        _print_error(str(exc))
        return 1
    style = _Style()
    if not groups:
        print(f"{style.dim}No duplicates found.{style.reset}")
        return 0
    for number, group in enumerate(groups, start=1):
        print(f"{style.bold}Group {number}{style.reset}")
        for info in group:
            print(f"  {info.filename}  {style.dim}({info.human_size}, "
                  f"{info.resolution}, dHash {info.dhash[:12]}...){style.reset}")
    total = sum(len(g) for g in groups)
    wasted = sum(i.size_bytes for g in groups for i in g[1:])
    print(f"\n{len(groups)} group(s), {total} redundant file(s), "
          f"{style.yellow}{wasted:,} bytes{style.reset} recoverable")
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    style = _Style()
    if directory.exists():
        shutil.rmtree(directory)
    files = create_sample_set(directory)
    print(f"{style.green}Sample set created in {directory.resolve()}{style.reset}\n")
    for label, path in files.items():
        print(f"  {style.cyan}{label:<10}{style.reset} {path.name}")
    photo = files["photo"]
    info = ImageInfo.from_file(photo)
    exif = ExifData.from_file(photo)
    print(f"\n{style.bold}The photo carries:{style.reset}")
    _kv_table(style, [
        ("Camera", f"{exif.tags.get('Make')} {exif.tags.get('Model')}"),
        ("Captured", exif.datetime_original or "?"),
        ("GPS", f"{exif.gps[0]:.6f}, {exif.gps[1]:.6f}" if exif.gps else "no"),
        ("Size", f"{info.resolution}, {info.human_size}"),
    ])
    print(f"\nTry it:{style.dim}")
    print(f"  imageinfo info        {photo}")
    print(f"  imageinfo privacy     {photo}")
    print(f"  imageinfo gps         {photo} --map map.html")
    print(f"  imageinfo strip       {photo} -o clean.jpg")
    print(f"  imageinfo duplicates  {directory}")
    print(f"  imageinfo report      {photo} -o report.html{style.reset}")
    return 0


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imageinfo",
        description="Inspect, audit and clean image metadata.",
        epilog="Run 'imageinfo <command> --help' for command specific options.",
    )
    parser.add_argument("--version", action="version",
                        version=f"imageinfo {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("info", help="technical snapshot of one image")
    p.add_argument("path")
    p.add_argument("--json", action="store_true", help="machine readable output")
    p.set_defaults(func=_cmd_info)

    p = sub.add_parser("exif", help="dump all EXIF metadata")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_exif)

    p = sub.add_parser("gps", help="show GPS coordinates, address and map")
    p.add_argument("path")
    p.add_argument("--map", metavar="FILE.html", help="write a Leaflet map page")
    p.add_argument("--no-geocode", action="store_true",
                   help="skip the online address lookup")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_gps)

    p = sub.add_parser("privacy", help="what does this image leak about you?")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_privacy)

    p = sub.add_parser("strip", help="write a metadata-free copy")
    p.add_argument("path")
    p.add_argument("-o", "--output", help="destination (default: <name>_clean.<ext>)")
    p.add_argument("--quality", type=int, default=92, help="JPEG quality (default 92)")
    p.add_argument("--no-rotate", action="store_true",
                   help="do not bake EXIF orientation into pixels")
    p.set_defaults(func=_cmd_strip)

    p = sub.add_parser("report", help="single-file HTML analysis report")
    p.add_argument("path")
    p.add_argument("-o", "--output", help="report path (default: <name>-report.html)")
    p.add_argument("--no-charts", action="store_true", help="skip histogram/palette")
    p.add_argument("--no-geocode", action="store_true")
    p.set_defaults(func=_cmd_report)

    p = sub.add_parser("histogram", help="render a color histogram chart")
    p.add_argument("path")
    p.add_argument("-o", "--output", help="PNG path (default: <name>.histogram.png)")
    p.set_defaults(func=_cmd_histogram)

    p = sub.add_parser("palette", help="render the dominant color palette")
    p.add_argument("path")
    p.add_argument("-o", "--output", help="PNG path (default: <name>.palette.png)")
    p.add_argument("-n", "--count", type=int, default=8, help="number of colors")
    p.set_defaults(func=_cmd_palette)

    p = sub.add_parser("hash", help="cryptographic + perceptual hashes")
    p.add_argument("paths", nargs="+")
    p.add_argument("--threshold", type=int, default=8)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_hash)

    p = sub.add_parser("compare", help="compare two images visually")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--threshold", type=int, default=10)
    p.set_defaults(func=_cmd_compare)

    p = sub.add_parser("convert", help="convert between image formats")
    p.add_argument("path")
    p.add_argument("-o", "--output", help="destination file")
    p.add_argument("--format", help="target format, e.g. png (default: from output)")
    p.add_argument("--quality", type=int, default=92, help="JPEG quality")
    p.set_defaults(func=_cmd_convert)

    p = sub.add_parser("resize", help="resize an image")
    p.add_argument("path")
    p.add_argument("--width", type=int, help="target width")
    p.add_argument("--height", type=int, help="target height")
    p.add_argument("-o", "--output", help="destination file")
    p.add_argument("--quality", type=int, default=92, help="JPEG quality")
    p.set_defaults(func=_cmd_resize)

    p = sub.add_parser("scan", help="batch-inspect a directory")
    p.add_argument("directory")
    p.add_argument("-r", "--recursive", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--csv", metavar="FILE.csv", help="write results to CSV")
    p.set_defaults(func=_cmd_scan)

    p = sub.add_parser("duplicates", help="find visually duplicate images")
    p.add_argument("directory")
    p.add_argument("-r", "--recursive", action="store_true", default=True)
    p.add_argument("--threshold", type=int, default=8,
                   help="max perceptual bit distance (default 8)")
    p.set_defaults(func=_cmd_duplicates)

    p = sub.add_parser("demo", help="generate sample images to play with")
    p.add_argument("--dir", default="image_info_demo", help="output directory")
    p.set_defaults(func=_cmd_demo)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())
