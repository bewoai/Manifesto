"""Test ortak kurulumu: repo kökünü import yoluna ekle, PII kaynakları için skip."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402


def _require(path: Path, what: str):
    if not Path(path).exists():
        pytest.skip(f"{what} bulunamadı: {path}")


@pytest.fixture
def country_map_ready():
    _require(config.COUNTRY_MAP_PATH, "country_map.json (önce: python -m scripts.build_country_map)")


@pytest.fixture
def template_ready():
    _require(config.MANIFEST_TEMPLATE_PATH, "manifest_template.xlsx (önce: python -m scripts.make_manifest_template)")


@pytest.fixture
def planning_ready():
    _require(config.PLANNING_XLSX, "planlama xlsx (Downloads)")


@pytest.fixture
def golden_ready():
    _require(config.GOLDEN_MANIFEST_XLSX, "golden BZR.xlsx (Downloads)")
