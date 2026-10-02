"""Quick start: one call gives you everything about an image.

Run:  python examples/basic_usage.py [path/to/image.jpg]

Without an argument the script generates a sample photo first, so it always
works out of the box.
"""

import sys
from pathlib import Path

from image_info import ImageInfo, ExifData, analyze_privacy


def main() -> None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        from image_info.demo import create_sample_photo

        path = create_sample_photo(Path("demo_output") / "sample.jpg")
        print(f"(no argument given - generated a sample photo at {path})\n")

    info = ImageInfo.from_file(path)
    exif = ExifData.from_file(path)
    privacy = analyze_privacy(path, info=info, exif=exif)

    print("== Technical snapshot " + "=" * 40)
    for label, value in info.summary():
        print(f"  {label:18} {value}")

    print("\n== Camera " + "=" * 47)
    if exif.camera:
        print(f"  Device            {exif.camera[0]} {exif.camera[1]}")
        print(f"  Captured          {exif.datetime_original}")
    else:
        print("  (no camera metadata)")

    print("\n== Location " + "=" * 44)
    if exif.gps:
        lat, lon = exif.gps
        print(f"  Coordinates       {lat:.6f}, {lon:.6f}")
        if exif.gps_altitude:
            print(f"  Altitude          {exif.gps_altitude:.0f} m")
        print(f"  Map               https://www.google.com/maps?q={lat},{lon}")
    else:
        print("  (no GPS data)")

    print("\n== Privacy " + "=" * 45)
    print(f"  Risk level        {privacy.risk_level} ({privacy.risk_score}/100)")
    for finding in privacy.findings:
        print(f"  [{finding.severity:6}] {finding.detail}")


if __name__ == "__main__":
    main()
