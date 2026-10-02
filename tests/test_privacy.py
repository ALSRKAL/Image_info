"""Tests for image_info.privacy - risk scoring and metadata stripping."""

from __future__ import annotations

import pytest

from image_info.exif import ExifData
from image_info.privacy import analyze_privacy, strip_metadata


class TestPrivacyScoring:
    def test_gps_photo_is_risky(self, photo_privacy):
        assert photo_privacy.risk_score >= 50
        assert photo_privacy.risk_level in ("High", "Critical")
        assert photo_privacy.has_location

    def test_clean_png_scores_low(self, samples):
        report = analyze_privacy(samples["clean_png"])
        assert report.risk_score < 20
        assert report.risk_level == "Low"
        assert not report.has_location

    def test_levels_are_ordered(self, samples, photo_privacy):
        order = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
        assert order[photo_privacy.risk_level] > order[
            analyze_privacy(samples["clean_png"]).risk_level
        ]

    def test_findings_carry_details(self, photo_privacy):
        location = [f for f in photo_privacy.findings if f.category == "Location"]
        assert location and "30.32850" in location[0].detail

    def test_to_dict_round_trip(self, photo_privacy):
        payload = photo_privacy.to_dict()
        assert payload["risk_score"] == photo_privacy.risk_score
        assert len(payload["findings"]) == len(photo_privacy.findings)


class TestStripMetadata:
    def test_strip_removes_exif_and_gps(self, samples, tmp_path):
        destination = tmp_path / "clean.jpg"
        result = strip_metadata(samples["photo"], destination)

        assert result["removed_exif_tags"] > 0
        assert result["removed_gps"] is True
        assert result["remaining_exif_tags"] == 0

        after = ExifData.from_file(destination)
        assert after.tag_count() == 0
        assert after.gps is None

    def test_stripped_pixels_survive(self, samples, tmp_path):
        from image_info.core import ImageInfo

        destination = tmp_path / "clean.jpg"
        strip_metadata(samples["photo"], destination)
        before = ImageInfo.from_file(samples["photo"])
        after = ImageInfo.from_file(destination)
        assert after.resolution == before.resolution
        assert after.looks_like_duplicate_of(before, threshold=2)

    def test_strip_shrinks_file(self, samples, tmp_path):
        destination = tmp_path / "clean.jpg"
        result = strip_metadata(samples["photo"], destination)
        assert result["after_bytes"] < result["before_bytes"]

    def test_strip_missing_source(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            strip_metadata(tmp_path / "ghost.jpg", tmp_path / "out.jpg")

    def test_strip_refuses_to_overwrite_source(self, samples):
        with pytest.raises(ValueError):
            strip_metadata(samples["photo"], samples["photo"])
