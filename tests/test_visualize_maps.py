"""Tests for image_info.visualize and image_info.maps."""

from __future__ import annotations

import pytest
from PIL import Image

from image_info.maps import _is_safe_endpoint, build_map_html
from image_info.visualize import render_histogram, render_palette


class TestCharts:
    def test_histogram_dimensions(self, samples):
        chart = render_histogram(str(samples["photo"]))
        assert chart.size == (900, 430)
        assert chart.getcolors(maxcolors=10**6)  # not a blank canvas

    def test_histogram_from_pil_image(self, photo_info, tmp_path):
        with Image.open(photo_info.path) as image:
            chart = render_histogram(image, width=640, height=320)
        assert chart.size == (640, 320)

    def test_palette_swatch_count(self, samples):
        chart = render_palette(str(samples["photo"]), count=5)
        assert chart.size == (900, 260)


class TestSafeEndpoints:
    @pytest.mark.parametrize("url", [
        "http://nominatim.openstreetmap.org/reverse",   # plain http
        "https://localhost/reverse",                    # loopback host
        "https://127.0.0.1/reverse",                    # loopback address
        "https://192.168.1.10/reverse",                 # private range
        "https://169.254.169.254/latest/meta-data",     # link-local / cloud metadata
        "ftp://nominatim.openstreetmap.org/reverse",    # wrong scheme
        "not a url at all",
    ])
    def test_unsafe_endpoints_rejected(self, url):
        assert _is_safe_endpoint(url) is False

    def test_blocked_endpoint_returns_none(self, monkeypatch):
        # TEST-NET-1 is reserved, so the safety guard must stop the request
        # before a single byte leaves the process.
        from image_info import maps

        monkeypatch.setattr(maps, "NOMINATIM_URL", "https://192.0.2.1/reverse")
        assert maps.reverse_geocode(1.0, 2.0) is None


class TestMapHtml:
    def test_contains_coordinates_and_leaflet(self, tmp_path):
        html = build_map_html(30.3285, 35.4444, title="Petra")
        assert "30.3285" in html and "35.4444" in html
        assert "leaflet" in html.lower()

    def test_address_is_escaped(self):
        html = build_map_html(1.0, 2.0, address="<script>alert(1)</script>")
        assert "<script>alert" not in html

    def test_save_map_writes_file(self, tmp_path):
        from image_info.maps import save_map

        out = save_map(10.0, 20.0, tmp_path / "sub" / "map.html")
        assert out.exists() and "L.map" in out.read_text(encoding="utf-8")
