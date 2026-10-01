"""Location utilities: self-contained map pages and reverse geocoding.

Two jobs live here:

* :func:`save_map` writes a single-file HTML map (Leaflet + OpenStreetMap
  tiles) for the photo's GPS position.  Unlike the Google Maps based approach
  of earlier versions this needs no API key.
* :func:`reverse_geocode` turns coordinates into a street address using the
  public Nominatim service through a deliberately strict HTTP client: the
  endpoint is pinned to https + a fixed host, redirects to unsafe targets are
  refused, and the actual TCP peer must be a public address before any
  request data is sent (anti-DNS-rebinding).

Example
-------
>>> from image_info.maps import save_map, reverse_geocode
>>> save_map(30.3285, 35.4444, "petra-map.html")
>>> reverse_geocode(30.3285, 35.4444)
'Petra, Wadi Musa, Maan, Jordan'
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

__all__ = ["save_map", "build_map_html", "reverse_geocode"]

#: The only remote endpoint this library ever contacts on its own.
NOMINATIM_HOST = "nominatim.openstreetmap.org"
NOMINATIM_URL = f"https://{NOMINATIM_HOST}/reverse"
_USER_AGENT = "ImageInfo/2.0 (https://github.com/ALSRKAL/Image_info)"


def _fmt(coord: float) -> str:
    return f"{coord:.6f}"


def build_map_html(
    lat: float,
    lon: float,
    zoom: int = 14,
    title: str = "Image capture location",
    address: Optional[str] = None,
) -> str:
    """Return a self-contained Leaflet HTML page centred on ``lat, lon``."""
    import html as _html
    import json as _json

    popup = f"<b>{_html.escape(title)}</b><br>{_fmt(lat)}, {_fmt(lon)}"
    if address:
        popup += f"<br><small>{_html.escape(address)}</small>"
    popup_js = _json.dumps(popup)  # safe JS string literal
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(title)}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  html, body {{ margin: 0; height: 100%; font-family: system-ui, sans-serif; }}
  #map {{ height: 100%; }}
  .coords {{ position: fixed; bottom: 12px; left: 12px; z-index: 1000;
             background: rgba(20, 24, 30, .85); color: #eef2f6; padding: 8px 12px;
             border-radius: 8px; font: 12px/1.5 ui-monospace, monospace; }}
</style>
</head>
<body>
<div id="map"></div>
<div class="coords">{_fmt(lat)}, {_fmt(lon)}</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const map = L.map('map').setView([{lat!r}, {lon!r}], {zoom});
  L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
  }}).addTo(map);
  L.marker([{lat!r}, {lon!r}]).addTo(map).bindPopup({popup_js}).openPopup();
  L.circle([{lat!r}, {lon!r}], {{radius: 120, color: '#e5484d',
    fillColor: '#e5484d', fillOpacity: .25}}).addTo(map);
</script>
</body>
</html>
"""


def save_map(
    lat: float,
    lon: float,
    destination: str | Path,
    zoom: int = 14,
    title: str = "Image capture location",
    address: Optional[str] = None,
) -> Path:
    """Write the map page to ``destination`` and return the resolved path."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_map_html(lat, lon, zoom=zoom, title=title, address=address),
                    encoding="utf-8")
    return path.resolve()


def _is_safe_endpoint(url: str) -> bool:
    """True when ``url`` is https and every resolved address is public.

    Blocks plain http, missing hosts, and loopback / private / link-local /
    reserved ranges so metadata files can never redirect geocoding at
    internal services.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that refuses to talk to non-public peers.

    DNS answers are re-checked at connection time, closing the window between
    the pre-flight :func:`_is_safe_endpoint` check and the actual connect
    (DNS rebinding).
    """

    def connect(self) -> None:
        super().connect()
        try:
            peer = self.sock.getpeername()[0]
            ip = ipaddress.ip_address(peer)
        except (OSError, ValueError, IndexError):
            self.close()
            raise OSError("could not verify connection peer address")
        if not ip.is_global:
            self.close()
            raise OSError(f"refusing to connect to non-public address {peer}")


class _SafeHTTPSHandler(urllib.request.HTTPSHandler):
    https_connection_class = _PinnedHTTPSConnection


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects that leave the validated https/public-IP boundary."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_safe_endpoint(newurl):
            raise urllib.error.HTTPError(
                newurl, code, "redirect to a non-https or non-public target blocked",
                headers, fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _safe_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        _SafeRedirectHandler(), _SafeHTTPSHandler(context=ssl.create_default_context()),
    )


def reverse_geocode(lat: float, lon: float, timeout: float = 8.0) -> Optional[str]:
    """Look up a human readable address for ``lat, lon`` via Nominatim.

    Returns ``None`` when the endpoint is unreachable, rate limited or the
    network is unavailable - callers must treat the address as optional.
    """
    query = urllib.parse.urlencode({
        "lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "format": "jsonv2", "zoom": 17,
    })
    url = f"{NOMINATIM_URL}?{query}"
    if not _is_safe_endpoint(url):
        return None
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
    )
    try:
        with _safe_opener().open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return payload.get("display_name") or None
