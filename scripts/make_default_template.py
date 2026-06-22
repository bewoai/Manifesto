"""Kaynak BZR.xlsx olmadan, bilinen yapıdan PII'siz manifesto şablonu üretir.

`make_manifest_template.py` dolu bir BZR.xlsx'e ihtiyaç duyar; bu script ise
brief §3'teki sabit MANİFESTO kolon yapısından (config) işlevsel bir şablon
oluşturur. Gerçek BZR.xlsx geldiğinde tam biçim için onu kullanın.

Kullanım:
  python -m scripts.make_default_template [--out <xlsx>]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

HEADERS = {
    config.M_COL_NAME: ("AD SOYAD", 32),
    config.M_COL_SEX: ("CİNSİYET", 12),
    config.M_COL_NATIONALITY: ("UYRUK", 22),
    config.M_COL_PASSPORT: ("PASAPORT/KİMLİK NO", 22),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=config.MANIFEST_TEMPLATE_PATH)
    args = ap.parse_args()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = config.MANIFEST_SHEET

    bold = Font(bold=True)
    for col, (label, width) in HEADERS.items():
        cell = ws.cell(config.MANIFEST_HEADER_ROW, col)
        cell.value = label
        cell.font = bold
        ws.column_dimensions[cell.column_letter].width = width

    args.out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(args.out)
    wb.close()
    print(f"Varsayılan şablon yazıldı -> {args.out}")


if __name__ == "__main__":
    main()
