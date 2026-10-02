"""Tests for image_info.exif - EXIF/GPS parsing."""

from __future__ import annotations

import pytest

from image_info.demo import PETRA
from image_info.exif import ExifData, dms_to_decimal


class TestDmsConversion:
    def test_north_east(self):
        assert dms_to_decimal((30.0, 19.0, 42.6), "N") == pytest.approx(30.3285, abs=1e-5)

    def test_south_is_negative(self):
        assert dms_to_decimal((30.0, 0.0, 0.0), "S") == -30.0

    def test_west_is_negative(self):
        assert dms_to_decimal((35.0, 26.0, 39.8), "W") == pytest.approx(-35.444389, abs=1e-5)


class TestExifParsing:
    def test_camera_identification(self, photo_exif):
        assert photo_exif.tags["Make"] == "PixelWorks"
        assert photo_exif.tags["Model"] == "PW-7 Pro"
        assert photo_exif.camera == ("PixelWorks", "PW-7 Pro")

    def test_timestamps(self, photo_exif):
        assert photo_exif.datetime_original == "2025:09:30 17:42:10"

    def test_gps_decimal(self, photo_exif):
        assert photo_exif.has_gps
        lat, lon = photo_exif.gps
        assert lat == pytest.approx(PETRA[0], abs=1e-4)
        assert lon == pytest.approx(PETRA[1], abs=1e-4)

    def test_gps_altitude(self, photo_exif):
        assert photo_exif.gps_altitude == pytest.approx(910.0)

    def test_exposure_triad(self, photo_exif):
        exif_ifd = photo_exif.sub_ifds["Exif"]
        assert exif_ifd["ISOSpeedRatings"] == 200
        assert exif_ifd["ExposureTime"] == pytest.approx(1 / 120)
        assert exif_ifd["FNumber"] == pytest.approx(1.7)

    def test_clean_file_has_no_metadata(self, samples):
        exif = ExifData.from_file(samples["clean_png"])
        assert exif.tag_count() == 0
        assert exif.gps is None
        assert exif.camera is None

    def test_flat_table_contains_gps_paths(self, photo_exif):
        keys = [key for key, _ in photo_exif.flat_table()]
        assert "GPS.GPSLatitude" in keys
        assert "Exif.DateTimeOriginal" in keys

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ExifData.from_file(tmp_path / "nope.jpg")

    def test_to_dict_shape(self, photo_exif):
        payload = photo_exif.to_dict()
        assert payload["gps"]["latitude"] == pytest.approx(PETRA[0], abs=1e-4)
        assert payload["has_xmp"] is False
