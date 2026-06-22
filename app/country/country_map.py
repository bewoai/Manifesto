"""country_map.json yükleyici ve iki yönlü ülke çözümü.

country_map.json yapısı (brief §4):  { "ITA": {"code": "ITA", "name": "Italy"}, ... }
- code: operasyonun/planlamanın kullandığı 3 harf kod (çoğunlukla ISO alpha-3 ile birebir)
- name: manifestonun UYRUK kolonuna yazılacak `ULKELER` İngilizce adı
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.config import COUNTRY_MAP_PATH


@lru_cache(maxsize=1)
def load(path: Optional[Path] = None) -> dict[str, dict]:
    p = Path(path) if path else COUNTRY_MAP_PATH
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def iso3_to_name(code: str, path: Optional[Path] = None) -> Optional[str]:
    """MRZ/planlama alpha-3 kodu -> manifesto UYRUK adı (ör. 'CHE' -> 'Switzerland')."""
    if not code:
        return None
    entry = load(path).get(code.strip().upper())
    return entry["name"] if entry else None


def iso3_to_planning_code(code: str, path: Optional[Path] = None) -> Optional[str]:
    """MRZ alpha-3 -> planlama col 2 kodu (çoğunlukla aynı koddur)."""
    if not code:
        return None
    entry = load(path).get(code.strip().upper())
    return entry["code"] if entry else None
