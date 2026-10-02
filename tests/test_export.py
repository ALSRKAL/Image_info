"""Tests for image_info.export - scanning, exports, duplicate grouping."""

from __future__ import annotations

import csv
import io
import json

import pytest

from image_info.core import ImageInfo
from image_info.export import (
    find_duplicates,
    scan_directory,
    to_csv,
    to_json,
    write_csv,
    write_json,
)


class TestScan:
    def test_finds_all_samples(self, samples):
        infos = scan_directory(samples["photo"].parent)
        names = {info.filename for info in infos}
        assert "petra_sunset.jpg" in names
        assert "monthly_views.png" in names
        assert "loop.gif" in names

    def test_not_a_directory(self, tmp_path):
        with pytest.raises(NotADirectoryError):
            scan_directory(tmp_path / "missing")

    def test_corrupt_files_are_skipped(self, samples, tmp_path):
        (tmp_path / "broken.jpg").write_bytes(b"junk")
        (tmp_path / "note.txt").write_text("ignore me")
        infos = scan_directory(tmp_path)
        assert infos == []


class TestExports:
    def test_json_single(self, photo_info):
        payload = json.loads(to_json(photo_info))
        assert payload["filename"] == photo_info.filename

    def test_json_list(self, samples):
        infos = scan_directory(samples["photo"].parent)
        payload = json.loads(to_json(infos))
        assert isinstance(payload, list) and len(payload) >= 4

    def test_write_json(self, photo_info, tmp_path):
        out = write_json(photo_info, tmp_path / "nested" / "info.json")
        assert out.exists()
        assert photo_info.filename in out.read_text(encoding="utf-8")

    def test_csv_round_trip(self, samples):
        infos = scan_directory(samples["photo"].parent)
        rows = list(csv.DictReader(io.StringIO(to_csv(infos))))
        assert len(rows) == len(infos)
        assert rows[0]["format"] in {"JPEG", "PNG", "GIF"}

    def test_write_csv(self, samples, tmp_path):
        infos = scan_directory(samples["photo"].parent)
        out = write_csv(infos, tmp_path / "report.csv")
        assert "petra_sunset.jpg" in out.read_text(encoding="utf-8")


class TestDuplicates:
    def test_groups_identical_copies(self, samples):
        infos = scan_directory(samples["photo"].parent)
        groups = find_duplicates(infos)
        assert len(groups) == 1
        names = {info.filename for info in groups[0]}
        assert names == {"petra_sunset.jpg", "petra_sunset (copy).jpg"}

    def test_from_directory(self, samples):
        groups = find_duplicates(samples["photo"].parent)
        assert groups

    def test_no_duplicates_here(self, tmp_path):
        from PIL import Image

        Image.new("RGB", (64, 64), (200, 30, 30)).save(tmp_path / "a.jpg")
        Image.new("RGB", (64, 64), (30, 200, 30)).save(tmp_path / "b.jpg")
        assert find_duplicates(tmp_path) == []

    def test_singleton_needs_no_search(self, photo_info):
        assert find_duplicates([photo_info]) == []
