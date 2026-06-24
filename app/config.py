"""Merkezi yol ve ayar tanımları.

Gerçek (PII içeren) kaynak dosyalar repo'ya KONULMAZ; varsayılan olarak
kullanıcının Downloads klasöründen okunur, ortam değişkeniyle override edilebilir.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Üretilen, PII içermeyen artefaktlar (repo içinde tutulabilir)
COUNTRY_MAP_PATH = Path(os.getenv("COUNTRY_MAP_PATH", DATA_DIR / "country_map.json"))
MANIFEST_TEMPLATE_PATH = Path(os.getenv("MANIFEST_TEMPLATE_PATH", DATA_DIR / "manifest_template.xlsx"))

# Geliştirme/test kaynakları (PII — repo dışı). Override için ortam değişkenleri.
_DOWNLOADS = Path(os.getenv("USERPROFILE", Path.home())) / "Downloads"
PLANNING_XLSX = Path(os.getenv("PLANNING_XLSX", _DOWNLOADS / "HAZİRAN AYI UÇUŞ PLANLAMASI 2026.xlsx"))
SOURCE_MANIFEST_XLSX = Path(os.getenv("SOURCE_MANIFEST_XLSX", _DOWNLOADS / "BZR.xlsx"))
GOLDEN_MANIFEST_XLSX = Path(os.getenv("GOLDEN_MANIFEST_XLSX", _DOWNLOADS / "BZR.xlsx"))

# Planlama sayfası kolon haritası (1 tabanlı) — brief §2
PLANNING_HEADER_ROW = 3
PLANNING_FIRST_DATA_ROW = 4
COL_PAX = 1
COL_UYRUK = 2          # PASAPORT
COL_MF = 3             # PASAPORT
COL_NAME = 4           # PASAPORT
COL_ROOM = 5           # İRTİBAT VE ODA NO
COL_HOTEL = 6          # OTEL
COL_PICKUP = 7         # PICK-UP saat
COL_RESERVED_BY = 8    # REZERVE YAPAN
COL_AGENCY = 9
COL_COMPANY = 10       # UÇACAĞI FİRMA
COL_BALLOON = 11       # manifesto filtresi
COL_PILOT = 12
COL_NOTE = 13
COL_DRIVER = 14        # ALIŞ ŞÖFÖR
COL_COMING_PLACE = 15  # GELECEĞİ YER
COL_PASSPORT_NO = 20   # PASAPORT
PASSPORT_COLS = (COL_UYRUK, COL_MF, COL_NAME, COL_PASSPORT_NO)

OPERATION_FIELD_TO_COL = {
    "pax": COL_PAX,
    "room": COL_ROOM,
    "hotel": COL_HOTEL,
    "pickup": COL_PICKUP,
    "reserved_by": COL_RESERVED_BY,
    "agency": COL_AGENCY,
    "company": COL_COMPANY,
    "balloon": COL_BALLOON,
    "pilot": COL_PILOT,
    "note": COL_NOTE,
    "driver": COL_DRIVER,
    "coming_place": COL_COMING_PLACE,
}

BLOCK_WIDE_OPERATION_FIELDS = {"balloon", "pilot", "driver", "coming_place"}

# Rezervasyon grubu boyunca dikey birleşik (tek değer gösterilen) lider kolonları —
# planlama sayfasındaki görünümü korumak için create_reservation bunları yeniden birleştirir.
LEAD_MERGE_COLS = (COL_PAX, COL_HOTEL, COL_PICKUP, COL_RESERVED_BY, COL_AGENCY, COL_NOTE)

# Manifesto sayfası — brief §3
MANIFEST_SHEET = "MANİFESTO"
MANIFEST_HEADER_ROW = 1
MANIFEST_FIRST_DATA_ROW = 2
M_COL_NAME = 1         # AD SOYAD
M_COL_SEX = 2          # CİNSİYET (Erkek/Kadın)
M_COL_NATIONALITY = 3  # UYRUK (İngilizce ad)
M_COL_PASSPORT = 4     # PASAPORT/KİMLİK NO

SEX_TR = {"M": "Erkek", "F": "Kadın"}

# Balon atama (brief §15 revize: balonu artık sistem otomatik atar)
DEFAULT_BALLOON_CODES = []
DEFAULT_BALLOON_CAPACITY = 28   # balon başına maksimum yolcu (Sayfa2 KAPASİTE 112 = ~4×28)
MAX_PAX = 28                    # tek rezervasyonun en fazla yolcu sayısı
VEHICLE_CAPACITY = 16          # araç (ALIŞ ŞÖFÖR/kaptan) başına maksimum yolcu

def get_resource_path(relative_path: str) -> Path:
    """Gets the absolute path to a resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = BASE_DIR
    return base_path / relative_path

MONTHLY_FLIGHT_TEMPLATE_PATH = get_resource_path("app/templates/monthly_flight_template.xlsx")

