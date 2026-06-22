"""Manifesto türetme (brief §3): bir gün + bir balon kodu için planlama
satırlarını filtrele, 4 kolonu al, 2 dönüşüm uygula, şablona yaz.

Dönüşümler:
  AD SOYAD            <- col 4 (aynen, UPPERCASE)
  CİNSİYET           <- col 3 M/F  ->  M=Erkek, F=Kadın
  UYRUK              <- col 2 alpha-3  ->  ULKELER İngilizce adı (country_map)
  PASAPORT/KİMLİK NO <- col 20 (aynen)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import openpyxl

from app import config
from app.country.country_map import iso3_to_name
from app.manifest.planning import PlanningRow, read_rows


@dataclass
class ManifestRow:
    name: str
    sex: str          # Erkek/Kadın
    nationality: str  # ULKELER İngilizce adı
    passport_no: str
    warnings: list[str]


def _transform(row: PlanningRow) -> ManifestRow:
    warnings: list[str] = []
    sex = config.SEX_TR.get(row.sex.upper().strip())
    if sex is None:
        warnings.append(f"bilinmeyen cinsiyet {row.sex!r}")
        sex = row.sex
    nat = iso3_to_name(row.nationality)
    if nat is None:
        warnings.append(f"uyruk kodu country_map'te yok: {row.nationality!r}")
        nat = row.nationality
    return ManifestRow(
        name=row.name.upper(),
        sex=sex,
        nationality=nat,
        passport_no=row.passport_no,
        warnings=warnings,
    )


def build_rows(planning_xlsx: Path, sheet: str, balloon: str) -> list[ManifestRow]:
    """Planlamadan tek balonun manifesto satırlarını üretir (yazmadan)."""
    balloon = balloon.upper().strip()
    rows = [r for r in read_rows(planning_xlsx, sheet) if r.balloon == balloon]
    return [_transform(r) for r in rows]


def write_manifest(rows: list[ManifestRow], out_path: Path,
                   template_path: Optional[Path] = None) -> Path:
    """ManifestRow'ları şablonun MANİFESTO sayfasına yazar (biçim + ULKELER korunur)."""
    template_path = template_path or config.MANIFEST_TEMPLATE_PATH
    wb = openpyxl.load_workbook(template_path)
    ws = wb[config.MANIFEST_SHEET]

    # mevcut veri satırlarını temizle (header'ın altından itibaren), biçimi bırak
    for r in range(config.MANIFEST_FIRST_DATA_ROW, ws.max_row + 1):
        for c in (config.M_COL_NAME, config.M_COL_SEX, config.M_COL_NATIONALITY, config.M_COL_PASSPORT):
            ws.cell(r, c).value = None

    for i, row in enumerate(rows):
        r = config.MANIFEST_FIRST_DATA_ROW + i
        ws.cell(r, config.M_COL_NAME).value = row.name
        ws.cell(r, config.M_COL_SEX).value = row.sex
        ws.cell(r, config.M_COL_NATIONALITY).value = row.nationality
        ws.cell(r, config.M_COL_PASSPORT).value = row.passport_no

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    wb.close()
    return out_path


def export(planning_xlsx: Path, sheet: str, balloon: str, out_dir: Path,
           template_path: Optional[Path] = None) -> Path:
    """Uçtan uca: filtrele -> dönüştür -> `<BALLOON>.xlsx` yaz. Çıktı yolunu döndürür."""
    rows = build_rows(planning_xlsx, sheet, balloon)
    out_path = Path(out_dir) / f"{balloon.upper().strip()}.xlsx"
    return write_manifest(rows, out_path, template_path)
