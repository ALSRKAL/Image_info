"""Build a machine-readable catalogue of a photo library.

Walks a folder and writes one JSON sidecar per image plus a summary CSV into
a fixed ``catalogue_out/`` directory inside the current working directory -
the scanned library itself is only ever read.

Run:  python examples/batch_catalogue.py [folder]
"""

import json
import sys
from pathlib import Path

from image_info import ExifData, scan_directory, to_csv, write_csv

#: All generated files land here (relative to the current directory).
OUTPUT_DIR = Path("catalogue_out")


def main() -> None:
    folder = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path(".").resolve()
    if not folder.is_dir():
        raise SystemExit(f"not a folder: {folder}")

    OUTPUT_DIR.mkdir(exist_ok=True)

    infos = scan_directory(folder, recursive=True)
    print(f"Cataloguing {len(infos)} image(s) from {folder}")

    for info in infos:
        exif = ExifData.from_file(info.path)
        record = info.to_dict()
        record["exif"] = {
            "camera": exif.camera,
            "captured": exif.datetime_original,
            "gps": exif.gps,
        }
        sidecar = OUTPUT_DIR / f"{Path(info.path).stem}.json"
        sidecar.write_text(json.dumps(record, indent=2, ensure_ascii=False),
                           encoding="utf-8")
        print(f"  {sidecar.name}")

    summary = write_csv(infos, OUTPUT_DIR / "summary.csv")
    print(f"\nSummary CSV: {summary}")
    print("Preview of the first CSV rows:")
    print("\n".join(to_csv(infos[:3]).splitlines()[:4]))


if __name__ == "__main__":
    main()
