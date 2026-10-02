"""Tests for the command line interface (run through cli.main)."""

from __future__ import annotations

import json

import pytest

from image_info.cli import main


@pytest.fixture()
def run(capsys):
    def _run(*argv) -> str:
        code = main(list(argv))
        assert code == 0, f"command failed: {argv}"
        return capsys.readouterr().out

    return _run


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "2.0.0" in capsys.readouterr().out


def test_no_arguments_prints_help(capsys):
    assert main([]) == 0
    assert "usage: imageinfo" in capsys.readouterr().out


class TestInfo:
    def test_human_output(self, run, samples):
        out = run("info", str(samples["photo"]))
        assert "JPEG" in out and "1600x1000" in out

    def test_json_output(self, run, samples):
        payload = json.loads(run("info", str(samples["photo"]), "--json"))
        assert payload["format"] == "JPEG"
        assert len(payload["sha256"]) == 64

    def test_missing_file_exits_1(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["info", "/nowhere/none.jpg"])
        assert exc.value.code == 1
        assert "not found" in capsys.readouterr().err


class TestExifAndGps:
    def test_exif_lists_camera(self, run, samples):
        out = run("exif", str(samples["photo"]))
        assert "PixelWorks" in out and "GPS.GPSLatitude" in out

    def test_exif_json(self, run, samples):
        payload = json.loads(run("exif", str(samples["photo"]), "--json"))
        assert payload["tags"]["Make"] == "PixelWorks"

    def test_gps_reports_coordinates(self, run, samples):
        out = run("gps", str(samples["photo"]), "--no-geocode")
        assert "30.328500" in out and "35.444389" in out

    def test_gps_writes_map(self, run, samples, tmp_path):
        map_path = tmp_path / "m.html"
        run("gps", str(samples["photo"]), "--no-geocode", "--map", str(map_path))
        text = map_path.read_text(encoding="utf-8")
        assert "leaflet" in text.lower() and "30.328500" in text

    def test_gps_without_data(self, run, samples):
        assert "No GPS" in run("gps", str(samples["clean_png"]))


class TestPrivacyAndStrip:
    def test_privacy_flags_location(self, run, samples):
        out = run("privacy", str(samples["photo"]))
        assert "Critical" in out or "High" in out

    def test_privacy_json(self, run, samples):
        payload = json.loads(run("privacy", str(samples["photo"]), "--json"))
        assert payload["risk_score"] >= 50

    def test_strip_then_privacy_is_clean(self, run, samples, tmp_path):
        target = tmp_path / "clean.jpg"
        out = run("strip", str(samples["photo"]), "-o", str(target))
        assert "Stripped" in out
        assert "Low" in run("privacy", str(target))


class TestVisualCommands:
    def test_histogram(self, run, samples, tmp_path):
        out_png = tmp_path / "hist.png"
        run("histogram", str(samples["photo"]), "-o", str(out_png))
        assert out_png.stat().st_size > 1000

    def test_palette(self, run, samples, tmp_path):
        out_png = tmp_path / "pal.png"
        run("palette", str(samples["photo"]), "-o", str(out_png), "-n", "6")
        assert out_png.exists()

    def test_report(self, run, samples, tmp_path):
        report = tmp_path / "r.html"
        run("report", str(samples["photo"]), "-o", str(report), "--no-geocode")
        text = report.read_text(encoding="utf-8")
        assert "Privacy audit" in text and "EXIF metadata" in text


class TestBatchCommands:
    def test_scan_table(self, run, samples):
        out = run("scan", str(samples["photo"].parent))
        assert "petra_sunset.jpg" in out and "image(s) scanned" in out

    def test_scan_json(self, run, samples):
        payload = json.loads(run("scan", str(samples["photo"].parent), "--json"))
        assert len(payload) >= 4

    def test_duplicates_finds_copies(self, run, samples):
        out = run("duplicates", str(samples["photo"].parent))
        assert "Group 1" in out and "petra_sunset (copy).jpg" in out

    def test_csv_export(self, run, samples, tmp_path):
        csv_path = tmp_path / "out.csv"
        run("scan", str(samples["photo"].parent), "--csv", str(csv_path))
        assert "filename" in csv_path.read_text(encoding="utf-8")


class TestCompareAndHash:
    def test_compare_identical(self, run, samples):
        out = run("compare", str(samples["photo"]), str(samples["duplicate"]))
        assert "byte-identical" in out

    def test_compare_different(self, run, samples):
        out = run("compare", str(samples["photo"]), str(samples["clean_png"]))
        assert "different" in out

    def test_hash_two_files(self, run, samples):
        out = run("hash", str(samples["photo"]), str(samples["duplicate"]))
        assert "SHA-256" in out and "Perceptual distance" in out


class TestConvertResizeDemo:
    def test_convert(self, run, samples, tmp_path):
        target = tmp_path / "out.png"
        run("convert", str(samples["photo"]), "-o", str(target))
        assert target.exists()

    def test_resize_keeps_aspect(self, run, samples, tmp_path):
        target = tmp_path / "small.jpg"
        run("resize", str(samples["photo"]), "--width", "320", "-o", str(target))
        from image_info.core import ImageInfo

        assert ImageInfo.from_file(target).resolution == "320x200"

    def test_demo_creates_corpus(self, run, tmp_path):
        out = run("demo", "--dir", str(tmp_path / "demo"))
        assert "petra_sunset.jpg" in out
