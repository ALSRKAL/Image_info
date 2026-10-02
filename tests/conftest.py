"""Shared fixtures: a generated sample corpus plus pre-parsed analysis objects."""

from __future__ import annotations

import shutil
import pytest
from PIL import Image

from image_info.core import ImageInfo
from image_info.demo import create_sample_set
from image_info.exif import ExifData
from image_info.privacy import PrivacyReport, analyze_privacy


@pytest.fixture(scope="session")
def samples(tmp_path_factory) -> dict:
    """The full demo corpus, created once for the whole test session."""
    base = tmp_path_factory.mktemp("samples")
    return create_sample_set(base)


@pytest.fixture(scope="session")
def sample_photo(samples) -> Image.Image:
    return Image.open(samples["photo"])


@pytest.fixture(scope="session")
def photo_info(samples) -> ImageInfo:
    return ImageInfo.from_file(samples["photo"])


@pytest.fixture(scope="session")
def photo_exif(samples) -> ExifData:
    return ExifData.from_file(samples["photo"])


@pytest.fixture(scope="session")
def photo_privacy(samples) -> PrivacyReport:
    return analyze_privacy(samples["photo"])


@pytest.fixture(scope="session")
def clean_png_info(samples) -> ImageInfo:
    return ImageInfo.from_file(samples["clean_png"])
