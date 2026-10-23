"""country_map.json yükleyici ve iki yönlü ülke çözümü.

country_map.json yapısı (brief §4):  { "ITA": {"code": "ITA", "name": "Italy"}, ... }
- code: operasyonun/planlamanın kullandığı 3 harf kod (çoğunlukla ISO alpha-3 ile birebir)
- name: manifestonun UYRUK kolonuna yazılacak `ULKELER` İngilizce adı

Sahada ISO dışı kodlar da yazılıyor (ör. İrlanda için "IRE", İngiltere için "UK", Alman
pasaportu MRZ'sinde "D"). `normalize_code` bunları ISO alpha-3'e çevirir; tam ülke adları
(İngilizce ve birkaç Türkçe) de kabul edilir.
"""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.config import COUNTRY_MAP_PATH

# ISO dışı ama sahada / spor kodlarında (IOC, FIFA) / MRZ'de yaygın kodlar → ISO alpha-3.
# Belirsiz olanlar (CHI: Şili mi Çin mi, SLO, MAL, LIB …) bilinçli olarak yok.
ALIASES: dict[str, str] = {
    "IRE": "IRL", "EIR": "IRL",
    "UK": "GBR", "GB": "GBR", "ENG": "GBR", "SCO": "GBR", "WAL": "GBR", "NIR": "GBR",
    "D": "DEU", "GER": "DEU",
    "SUI": "CHE", "NED": "NLD", "HOL": "NLD", "POR": "PRT", "DEN": "DNK",
    "ROM": "ROU", "BUL": "BGR", "CRO": "HRV", "GRE": "GRC", "LAT": "LVA",
    "KSA": "SAU", "UAE": "ARE", "RSA": "ZAF", "IRI": "IRN", "TPE": "TWN",
    "PHI": "PHL", "INA": "IDN", "MAS": "MYS", "VIE": "VNM", "SIN": "SGP",
    "ALG": "DZA", "KUW": "KWT", "MGL": "MNG", "NEP": "NPL", "SRI": "LKA", "BAN": "BGD",
    "JAP": "JPN", "US": "USA", "URU": "URY", "PAR": "PRY", "CRC": "CRI",
    "GUA": "GTM", "HON": "HND", "NGR": "NGA", "TAN": "TZA", "ZIM": "ZWE", "ANG": "AGO",
    "TC": "TUR", "T.C.": "TUR", "T.C": "TUR",
}

_EXTRA_NAMES: dict[str, str] = {
    "TURKEY": "TUR", "TURKIYE": "TUR", "TURKIYE CUMHURIYETI": "TUR",
    "ENGLAND": "GBR", "GREAT BRITAIN": "GBR", "BRITISH": "GBR", "UNITED KINGDOM": "GBR",
    "USA": "USA", "UNITED STATES": "USA", "AMERICA": "USA", "UNITED STATES OF AMERICA": "USA",
    "KOREA": "KOR", "SOUTH KOREA": "KOR", "HOLLAND": "NLD", "SWISS": "CHE",
    "ALMANYA": "DEU", "INGILTERE": "GBR", "IRLANDA": "IRL", "ITALYA": "ITA", "ISPANYA": "ESP",
    "FRANSA": "FRA", "POLONYA": "POL", "ROMANYA": "ROU", "RUSYA": "RUS", "CIN": "CHN",
    "JAPONYA": "JPN", "KORE": "KOR", "AMERIKA": "USA", "ISVICRE": "CHE", "HOLLANDA": "NLD",
}


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").replace("İ", "I").replace("ı", "i"))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).strip().upper()


@lru_cache(maxsize=1)
def load(path: Optional[Path] = None) -> dict[str, dict]:
    p = Path(path) if path else COUNTRY_MAP_PATH
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=4)
def _name_index(path: Optional[Path] = None) -> dict[str, str]:
    index = {_fold(v.get("name", "")): k for k, v in load(path).items() if v.get("name")}
    index.update(_EXTRA_NAMES)
    return index


def normalize_code(code: str, path: Optional[Path] = None) -> str:
    """Uyruk girdisini ISO alpha-3'e çevirir: 'ire'→'IRL', 'UK'→'GBR', 'D'→'DEU',
    'Türkiye'→'TUR'. Tanınmayan değer büyük harfe çevrilmiş hâliyle döner."""
    raw = _fold(code)
    if not raw:
        return ""
    data = load(path)
    if raw in data:
        return raw
    compact = raw.replace(" ", "").rstrip("<")
    if compact in ALIASES:
        return ALIASES[compact]
    if compact in data:
        return compact
    by_name = _name_index(path).get(raw)
    return by_name or raw


def iso3_to_name(code: str, path: Optional[Path] = None) -> Optional[str]:
    """MRZ/planlama alpha-3 kodu -> manifesto UYRUK adı (ör. 'CHE' -> 'Switzerland', 'IRE' -> 'Ireland')."""
    if not code:
        return None
    entry = load(path).get(normalize_code(code, path))
    return entry["name"] if entry else None


def iso3_to_planning_code(code: str, path: Optional[Path] = None) -> Optional[str]:
    """MRZ alpha-3 -> planlama col 2 kodu (çoğunlukla aynı koddur)."""
    if not code:
        return None
    entry = load(path).get(normalize_code(code, path))
    return entry["code"] if entry else None
