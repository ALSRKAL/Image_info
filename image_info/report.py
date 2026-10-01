"""Self-contained HTML analysis reports.

:func:`generate_report` bundles everything the library knows about one image
- technical snapshot, EXIF table, privacy audit, colour histogram, dominant
palette and a GPS card - into a single HTML file with the charts embedded as
base64 PNGs.  The result opens offline in any browser and is trivially
shareable.

Example
-------
>>> from image_info.report import generate_report
>>> generate_report("petra.jpg", "petra-report.html")
PosixPath('/home/you/petra-report.html')
"""

from __future__ import annotations

import base64
import html
import io
from pathlib import Path
from typing import Optional, Union

from PIL import Image

from .core import ImageInfo
from .exif import ExifData
from .maps import reverse_geocode
from .privacy import PrivacyReport, analyze_privacy
from .visualize import render_histogram, render_palette

__all__ = ["generate_report"]

_RISK_COLORS = {"Low": "#2f9e68", "Medium": "#d6a61d", "High": "#e0642f",
                "Critical": "#d64545"}


def _b64_png(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _thumbnail_b64(source: Path, max_side: int = 520) -> str:
    with Image.open(source) as image:
        image.load()
        image.thumbnail((max_side, max_side))
        buffer = io.BytesIO()
        if image.mode in ("RGBA", "LA", "P"):
            image.convert("RGBA").save(buffer, format="PNG", optimize=True)
            mime = "image/png"
        else:
            image.convert("RGB").save(buffer, format="JPEG", quality=85)
            mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def _dms_string(lat: float, lon: float) -> str:
    def fmt(value: float, positive: str, negative: str) -> str:
        hemisphere = positive if value >= 0 else negative
        value = abs(value)
        degrees = int(value)
        minutes = int((value - degrees) * 60)
        seconds = (value - degrees - minutes / 60) * 3600
        return f"{degrees}°{minutes:02d}'{seconds:05.2f}\"{hemisphere}"

    return f"{fmt(lat, 'N', 'S')} {fmt(lon, 'E', 'W')}"


def _rows(pairs: list[tuple[str, str]]) -> str:
    out = []
    for key, value in pairs:
        out.append(
            f"<tr><td>{html.escape(str(key))}</td>"
            f"<td class='mono'>{html.escape(str(value))}</td></tr>"
        )
    return "\n".join(out)


def _rows_raw(pairs: list[tuple[str, str]]) -> str:
    """Like :func:`_rows` but values may contain trusted inline HTML."""
    out = []
    for key, value in pairs:
        out.append(
            f"<tr><td>{html.escape(str(key))}</td>"
            f"<td class='mono'>{value}</td></tr>"
        )
    return "\n".join(out)


def generate_report(
    source: Union[str, Path],
    destination: Optional[Union[str, Path]] = None,
    include_charts: bool = True,
    geocode: bool = True,
) -> Path:
    """Build a standalone HTML report for ``source``.

    ``destination`` defaults to ``<image name>-report.html`` next to the
    image.  Returns the path of the written report.
    """
    src = Path(source)
    if not src.exists():
        raise FileNotFoundError(f"no such file: {src}")
    if destination is None:
        destination = src.with_suffix(src.suffix + "-report.html")
    dst = Path(destination)

    info = ImageInfo.from_file(src)
    exif = ExifData.from_file(src)
    privacy = analyze_privacy(src, info=info, exif=exif)

    risk_color = _RISK_COLORS[privacy.risk_level]
    gps = exif.gps
    address: Optional[str] = None
    if gps and geocode:
        address = reverse_geocode(*gps)

    file_rows = [
        ("Filename", info.filename),
        ("Format", f"{info.format} ({info.mode})"),
        ("Resolution", f"{info.resolution} px  ({info.megapixels:.1f} MP)"),
        ("File size", f"{info.human_size} ({info.size_bytes:,} bytes)"),
        ("Animation", f"{info.n_frames} frame(s)"),
        ("DPI", str(tuple(round(v, 1) for v in info.dpi)) if info.dpi else "not stored"),
        ("Brightness", f"{info.brightness} / 255"),
        ("Modified", info.modified_at.strftime("%Y-%m-%d %H:%M:%S")
         if info.modified_at else "unknown"),
    ]

    gps_html = ""
    if gps:
        lat, lon = gps
        maps_link = f"https://www.google.com/maps?q={lat},{lon}"
        osm_link = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}"
        embed = (
            f'<iframe src="https://www.openstreetmap.org/export/embed.html'
            f'?bbox={lon - 0.004}%2C{lat - 0.002}%2C{lon + 0.004}%2C{lat + 0.002}'
            f'&layer=mapnik&marker={lat}%2C{lon}"></iframe>'
        )
        gps_html = f"""
    <section class="card">
      <h2>Location</h2>
      <table>{_rows_raw([
            ("Coordinates", f"{lat:.6f}, {lon:.6f}"),
            ("DMS", _dms_string(lat, lon)),
            ("Altitude", f"{exif.gps_altitude:.0f} m" if exif.gps_altitude else "not stored"),
            ("Address", html.escape(address or "lookup unavailable (offline?)")),
            ("Links", f"<a href='{maps_link}'>Google Maps</a> &middot; "
                      f"<a href='{osm_link}'>OpenStreetMap</a>"),
        ])}</table>
      {embed}
    </section>"""
    else:
        gps_html = """
    <section class="card">
      <h2>Location</h2>
      <p class="muted">No GPS data is embedded in this file.</p>
    </section>"""

    charts_html = ""
    if include_charts:
        try:
            hist = _b64_png(render_histogram(src))
            palette = _b64_png(render_palette(src))
            charts_html = f"""
    <section class="card">
      <h2>Color analysis</h2>
      <img src="data:image/png;base64,{hist}" alt="Histogram" width="100%">
      <img src="data:image/png;base64,{palette}" alt="Palette" width="100%" style="margin-top:12px">
    </section>"""
        except Exception:  # noqa: BLE001 - charts must never kill the report
            charts_html = ""

    findings_html = ""
    if privacy.findings:
        rows = []
        for f in privacy.findings:
            rows.append(
                f"<tr><td>{html.escape(f.category)}</td>"
                f"<td class='mono'>{html.escape(f.key)}</td>"
                f"<td>{html.escape(f.detail)}</td>"
                f"<td><span class='sev'>{html.escape(f.severity)}</span></td></tr>"
            )
        findings_html = f"<table class='findings'>{''.join(rows)}</table>"
    else:
        findings_html = "<p class='muted'>No sensitive metadata found.</p>"

    exif_sections = []
    if exif.tags:
        exif_sections.append(
            "<h3>Primary IFD</h3><table>" + _rows(sorted(exif.tags.items())) + "</table>"
        )
    for ifd_name, ifd in sorted(exif.sub_ifds.items()):
        if ifd:
            exif_sections.append(
                f"<h3>{html.escape(ifd_name)} IFD</h3><table>"
                + _rows(sorted(ifd.items())) + "</table>"
            )
    if exif.xmp:
        exif_sections.append("<p class='muted'>An XMP packet is also present "
                             f"({len(exif.xmp):,} bytes).</p>")
    exif_html = "".join(exif_sections) or "<p class='muted'>No EXIF metadata.</p>"

    title = f"Image report - {info.filename}"
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ --bg:#f5f6f8; --card:#ffffff; --ink:#1c2128; --muted:#6b7280;
           --line:#e3e6ea; --accent:#3b6ef6; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
          font:15px/1.55 system-ui, 'Segoe UI', sans-serif; }}
  main {{ max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }}
  header.hero {{ display:flex; gap:20px; align-items:flex-start; flex-wrap:wrap;
                 background:var(--card); border:1px solid var(--line);
                 border-radius:14px; padding:22px; margin-bottom:18px; }}
  header.hero img {{ border-radius:10px; max-width:340px; box-shadow:0 4px 18px rgba(0,0,0,.12); }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  h2 {{ font-size:17px; margin:0 0 12px; }}
  h3 {{ font-size:14px; margin:16px 0 6px; color:var(--muted);
        text-transform:uppercase; letter-spacing:.06em; }}
  .risk {{ display:inline-block; padding:4px 12px; border-radius:999px;
           background:{risk_color}; color:#fff; font-weight:600; font-size:13px; }}
  .muted {{ color:var(--muted); }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px;
           padding:20px 22px; margin-bottom:18px; }}
  table {{ border-collapse:collapse; width:100%; font-size:14px; }}
  td {{ padding:6px 10px 6px 0; border-bottom:1px solid var(--line);
        vertical-align:top; }}
  tr:last-child td {{ border-bottom:none; }}
  td:first-child {{ color:var(--muted); white-space:nowrap; width:200px; }}
  .mono {{ font-family:ui-monospace, 'Cascadia Code', monospace; font-size:13px;
           word-break:break-all; }}
  table.findings td:first-child {{ width:110px; color:var(--ink); }}
  .sev {{ background:#eef1f5; border-radius:6px; padding:2px 8px; font-size:12px; }}
  iframe {{ width:100%; height:300px; border:1px solid var(--line);
            border-radius:10px; margin-top:12px; }}
  a {{ color:var(--accent); text-decoration:none; }}
  footer {{ color:var(--muted); font-size:12.5px; text-align:center; margin-top:8px; }}
</style>
</head>
<body>
<main>
  <header class="hero">
    <img src="{_thumbnail_b64(src)}" alt="thumbnail">
    <div>
      <h1>{html.escape(info.filename)}</h1>
      <p class="muted">{html.escape(info.format or "?")} &middot; {info.resolution}
         &middot; {info.human_size}</p>
      <p>Privacy exposure: <span class="risk">{privacy.risk_level} - {privacy.risk_score}/100</span></p>
      <p class="muted mono" style="font-size:12.5px">BLAKE2b {info.blake2b}<br>
         SHA-256 {info.sha256}<br>dHash {info.dhash}</p>
    </div>
  </header>

  <section class="card">
    <h2>File</h2>
    <table>{_rows(file_rows)}</table>
  </section>

  {gps_html}

  <section class="card">
    <h2>Privacy audit</h2>
    {findings_html}
  </section>

  <section class="card">
    <h2>EXIF metadata</h2>
    {exif_html}
  </section>

  {charts_html}

  <footer>Generated by Image_info &middot; {Path(__file__).name} &middot; single-file offline report</footer>
</main>
</body>
</html>
"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(document, encoding="utf-8")
    return dst.resolve()
