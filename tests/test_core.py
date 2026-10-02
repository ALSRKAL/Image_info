"""Tests for image_info.core - the technical snapshot engine."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from image_info.core import (
    ImageInfo,
    UnsupportedImageError,
    dhash_hex,
    hamming_distance,
    human_size,
)


class TestHumanSize:
    def test_bytes(self):
        assert human_size(512) == "512 B"

    def test_kilobytes(self):
        assert human_size(2048) == "2.0 KB"

    def test_megabytes(self):
        assert human_size(5 * 1024 * 1024) == "5.0 MB"

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            human_size(-1)


class TestDHash:
    def test_identical_images_share_hash(self):
        image = Image.new("RGB", (120, 90), (30, 144, 255))
        assert dhash_hex(image) == dhash_hex(image.copy())

    def test_different_images_differ(self):
        flat = Image.new("RGB", (120, 90), (0, 0, 0))
        checker = Image.new("RGB", (120, 90), (255, 255, 255))
        for x in range(0, 120, 10):
            for y in range(0, 90, 10):
                if (x // 10 + y // 10) % 2 == 0:
                    checker.paste((0, 0, 0), (x, y, x + 10, y + 10))
        distance = hamming_distance(int(dhash_hex(flat), 16), int(dhash_hex(checker), 16))
        assert distance > 8

    def test_hash_is_hex_of_fixed_width(self):
        image = Image.new("L", (64, 64), 128)
        value = dhash_hex(image, hash_size=8)
        assert len(value) == 16
        int(value, 16)  # must parse as hex


class TestImageInfo:
    def test_from_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ImageInfo.from_file(tmp_path / "ghost.jpg")

    def test_from_directory(self, tmp_path):
        with pytest.raises(IsADirectoryError):
            ImageInfo.from_file(tmp_path)

    def test_unsupported_file(self, tmp_path):
        bogus = tmp_path / "not-an-image.jpg"
        bogus.write_bytes(b"definitely not a jpeg")
        with pytest.raises(UnsupportedImageError):
            ImageInfo.from_file(bogus)

    def test_basic_fields(self, photo_info):
        assert photo_info.format == "JPEG"
        assert photo_info.mode == "RGB"
        assert photo_info.width == 1600 and photo_info.height == 1000
        assert photo_info.megapixels == pytest.approx(1.6)
        assert photo_info.aspect_ratio == pytest.approx(1.6)
        assert not photo_info.is_animated
        assert photo_info.n_frames == 1

    def test_hashes_are_stable(self, samples, photo_info):
        again = ImageInfo.from_file(samples["photo"])
        assert again.blake2b == photo_info.blake2b
        assert again.sha256 == photo_info.sha256
        assert again.dhash == photo_info.dhash
        assert len(photo_info.sha256) == 64
        assert len(photo_info.blake2b) == 32

    def test_duplicate_detection(self, samples, photo_info):
        twin = ImageInfo.from_file(samples["duplicate"])
        stranger = ImageInfo.from_file(samples["clean_png"])
        assert photo_info.looks_like_duplicate_of(twin)
        assert not photo_info.looks_like_duplicate_of(stranger, threshold=8)

    def test_to_dict_is_json_safe(self, photo_info):
        import json

        payload = photo_info.to_dict()
        assert json.loads(json.dumps(payload))["filename"] == photo_info.filename

    def test_animated_gif(self, samples):
        info = ImageInfo.from_file(samples["animation"])
        assert info.format == "GIF"
        assert info.is_animated
        assert info.n_frames == 3

    def test_png_transparency_flag(self, tmp_path):
        rgba = Image.new("RGBA", (32, 32), (10, 200, 120, 128))
        path = tmp_path / "alpha.png"
        rgba.save(path)
        assert ImageInfo.from_file(path).has_transparency

    def test_summary_covers_core_fields(self, photo_info):
        labels = [label for label, _ in photo_info.summary()]
        assert "Filename" in labels and "SHA-256" in labels
