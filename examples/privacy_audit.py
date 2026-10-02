"""Audit a photo before sharing it online.

Photos posted to social media or forums leak your location, your device and
your habits.  This recipe runs the same audit the ``imageinfo privacy``
command performs and tells you exactly what a file would expose - plus the
one command that fixes it.  It never modifies anything.

Run:  python examples/privacy_audit.py path/to/photo.jpg
"""

import sys
from pathlib import Path

from image_info import analyze_privacy

#: Only these container types are inspected by this recipe.
SAFE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff")


def validated_image(raw: str) -> Path:
    """Normalise CLI input into an existing image path."""
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"not a file: {path}")
    if path.suffix.lower() not in SAFE_EXTENSIONS:
        raise SystemExit(f"unsupported image type: {path.suffix or '(none)'}")
    return path


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python examples/privacy_audit.py <image>")

    source = validated_image(sys.argv[1])
    report = analyze_privacy(source)

    print(f"Auditing {source.name}: {report.risk_level} risk ({report.risk_score}/100)")
    for finding in report.findings:
        print(f"  - [{finding.category}] {finding.detail}")

    if report.findings:
        print("\nThis file is not safe to share as-is. One command fixes it:")
        print(f"  imageinfo strip \"{source}\"")
        print("(the library equivalent is image_info.privacy.strip_metadata)")
    else:
        print("Nothing sensitive found - the file is already safe to share.")


if __name__ == "__main__":
    main()
