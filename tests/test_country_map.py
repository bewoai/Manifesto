"""country_map.json testleri — planlamada gerçekten görülen kodlar çözülmeli."""
from __future__ import annotations

import pytest

from app.country.country_map import iso3_to_name, load

# 22.06 planlama sayfasında gerçekte görülen uyruk kodları + beklenen ULKELER adı
EXPECTED = {
    "BEL": "Belgium",
    "CHE": "Switzerland",
    "CHN": "China",
    "GBR": "United Kingdom",
    "IDN": "Indonesia",
    "LBN": "Lebanon",
    "ROU": "Romania",
    "RUS": "Russia",
    "THA": "Thailand",
    "TUR": "Türkiye",
    "USA": "United States",
}


@pytest.mark.usefixtures("country_map_ready")
def test_planning_codes_resolve():
    for code, name in EXPECTED.items():
        assert iso3_to_name(code) == name, f"{code} -> {iso3_to_name(code)!r} (beklenen {name!r})"


@pytest.mark.usefixtures("country_map_ready")
def test_india_injected_despite_ulkeler_gap():
    # ULKELER sayfasında India satırı boş; haritaya yine de eklenmeli
    assert iso3_to_name("IND") == "India"


@pytest.mark.usefixtures("country_map_ready")
def test_map_is_reasonably_complete():
    m = load()
    assert len(m) >= 240
    # her kayıt code+name içermeli, code anahtarla aynı olmalı
    for code, entry in m.items():
        assert entry["code"] == code
        assert entry["name"]


@pytest.mark.usefixtures("country_map_ready")
def test_unknown_code_returns_none():
    assert iso3_to_name("ZZZ") is None
