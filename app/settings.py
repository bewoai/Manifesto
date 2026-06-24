"""Kullanıcı ayarları — masaüstü uygulaması için yerel, kalıcı JSON.

API anahtarı ve yol override'ları burada saklanır (sahip bir kez girer, operatör
uğraşmaz). Dosya: %APPDATA%/Irtifa/settings.json (Windows).
config.py'deki sabitler varsayılan; buradakiler onları geçersiz kılar.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from app import config


def _config_dir() -> Path:
    base = os.getenv("APPDATA") or os.path.expanduser("~/.config")
    return Path(base) / "Irtifa"


SETTINGS_PATH = Path(os.getenv("MANIFESTO_SETTINGS", _config_dir() / "settings.json"))
LEGACY_SETTINGS_PATH = Path(os.getenv("APPDATA") or os.path.expanduser("~/.config")) / "BalonManifesto" / "settings.json"

VISION_MODE_GOOGLE_VISION = "google_vision"
VISION_MODE_CLAUDE = "claude"
VISION_MODE_MANUAL = "manual"
VISION_MODES = (
    VISION_MODE_GOOGLE_VISION,
    VISION_MODE_CLAUDE,
    VISION_MODE_MANUAL,
)

DATA_SOURCE_EXCEL = "excel"
DATA_SOURCE_GOOGLE_SHEETS = "google_sheets"
DATA_SOURCES = (DATA_SOURCE_EXCEL, DATA_SOURCE_GOOGLE_SHEETS)

DEFAULT_MODEL = "claude-opus-4-8"  # MRZ okuma modeli (Settings'ten değiştirilebilir)


@dataclass
class Settings:
    is_setup_complete: bool = False
    company_name: str = ""
    vision_mode: str = VISION_MODE_GOOGLE_VISION
    data_source: str = DATA_SOURCE_EXCEL
    anthropic_api_key: str = ""
    model: str = DEFAULT_MODEL
    google_vision_document_text: bool = False
    planning_xlsx: str = ""          # boşsa config.PLANNING_XLSX kullanılır
    output_dir: str = ""             # manifesto export klasörü
    manifest_template: str = ""      # boşsa config.MANIFEST_TEMPLATE_PATH
    google_credentials_json: str = ""
    google_spreadsheet_id: str = ""
    operation_options: dict[str, list[str]] = field(default_factory=dict)
    delete_images_after_write: bool = True   # KVKK (brief §10)
    balloon_capacity: int = config.DEFAULT_BALLOON_CAPACITY   # balon başına max yolcu
    balloon_codes: list[str] = field(default_factory=lambda: list(config.DEFAULT_BALLOON_CODES))
    weather_enabled: bool = True
    weather_provider: str = "open_meteo"
    weather_api_key: str = ""
    weather_api_url: str = ""
    weather_latitude: float = 38.6431
    weather_longitude: float = 34.8289
    weather_location_name: str = "Goreme Valley"
    weather_poll_minutes: int = 30
    google_sheets_experimental: bool = False
    update_manifest_url: str = ""
    update_public_key: str = ""

    # --- türetilmiş yollar ---
    def planning_path(self) -> Path:
        return Path(self.planning_xlsx) if self.planning_xlsx else Path("BELIRLENMEDI.xlsx")

    def template_path(self) -> Path:
        return Path(self.manifest_template) if self.manifest_template else config.MANIFEST_TEMPLATE_PATH

    def output_path(self) -> Path:
        if self.output_dir:
            return Path(self.output_dir)
        # .exe içinde BASE_DIR geçici klasördür; kalıcı bir yere yaz
        return Path(os.path.expanduser("~")) / "Documents" / "Irtifa"

    def has_api_key(self) -> bool:
        return bool(self.anthropic_api_key.strip() or os.getenv("ANTHROPIC_API_KEY"))

    def uses_claude(self) -> bool:
        return self.vision_mode == VISION_MODE_CLAUDE

    def uses_google_vision(self) -> bool:
        return self.vision_mode == VISION_MODE_GOOGLE_VISION

    def uses_automatic_vision(self) -> bool:
        return self.vision_mode != VISION_MODE_MANUAL

    def uses_google_sheets(self) -> bool:
        return self.data_source == DATA_SOURCE_GOOGLE_SHEETS

    def google_is_configured(self) -> bool:
        return bool(self.google_spreadsheet_id.strip() and self.google_credentials_json.strip())

    def normalized(self) -> "Settings":
        if self.vision_mode not in VISION_MODES:
            self.vision_mode = VISION_MODE_GOOGLE_VISION
        if self.data_source not in DATA_SOURCES:
            self.data_source = DATA_SOURCE_EXCEL
        # Balon kapasitesi 1..MAX_PAX aralığında
        try:
            self.balloon_capacity = int(self.balloon_capacity)
        except (TypeError, ValueError):
            self.balloon_capacity = config.DEFAULT_BALLOON_CAPACITY
        try:
            self.weather_latitude = float(self.weather_latitude)
            self.weather_longitude = float(self.weather_longitude)
        except (TypeError, ValueError):
            self.weather_latitude = 38.6431
            self.weather_longitude = 34.8289
        try:
            self.weather_poll_minutes = int(self.weather_poll_minutes)
        except (TypeError, ValueError):
            self.weather_poll_minutes = 30
        if not (10 <= self.weather_poll_minutes <= 180):
            self.weather_poll_minutes = 30
        self.weather_provider = str(self.weather_provider or "open_meteo").strip() or "open_meteo"
        self.weather_location_name = str(self.weather_location_name or "Goreme Valley").strip() or "Goreme Valley"
        if not (1 <= self.balloon_capacity <= config.MAX_PAX):
            self.balloon_capacity = config.DEFAULT_BALLOON_CAPACITY
        # Balon kodları: upper, trim, uniq, boşları at
        codes: list[str] = []
        seen_codes: set[str] = set()
        for code in (self.balloon_codes or []):
            c = str(code).strip().upper()
            if c and c not in seen_codes:
                codes.append(c)
                seen_codes.add(c)
        self.balloon_codes = codes or list(config.DEFAULT_BALLOON_CODES)
        cleaned: dict[str, list[str]] = {}
        if isinstance(self.operation_options, dict):
            for key, values in self.operation_options.items():
                if not isinstance(values, list):
                    continue
                seen: set[str] = set()
                cleaned_values: list[str] = []
                for value in values:
                    text = str(value).strip()
                    norm = text.upper()
                    if text and norm not in seen:
                        cleaned_values.append(text)
                        seen.add(norm)
                cleaned[key] = cleaned_values
        self.operation_options = cleaned
        return self


def load(path: Optional[Path] = None) -> Settings:
    p = Path(path) if path else SETTINGS_PATH
    if path is None and not p.exists() and LEGACY_SETTINGS_PATH.exists():
        p = LEGACY_SETTINGS_PATH
    if not p.exists():
        return Settings()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Settings()
    known = {k: data[k] for k in Settings.__dataclass_fields__ if k in data}
    settings = Settings(**known).normalized()
    try:
        from app.secret_store import get_secret
        for key in ("anthropic_api_key", "google_credentials_json", "weather_api_key"):
            stored = get_secret(key)
            if stored:
                setattr(settings, key, stored)
    except Exception:
        pass
    return settings


def save(settings: Settings, path: Optional[Path] = None) -> Path:
    p = Path(path) if path else SETTINGS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(settings)
    from app.secret_store import migrate_file_secret, set_secret
    set_secret("anthropic_api_key", settings.anthropic_api_key)
    set_secret("weather_api_key", settings.weather_api_key)
    if settings.google_credentials_json:
        migrate_file_secret("google_credentials_json", settings.google_credentials_json)
    data["anthropic_api_key"] = "dpapi:anthropic_api_key" if settings.anthropic_api_key else ""
    data["weather_api_key"] = "dpapi:weather_api_key" if settings.weather_api_key else ""
    data["google_credentials_json"] = (
        "dpapi:google_credentials_json" if settings.google_credentials_json else ""
    )
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
