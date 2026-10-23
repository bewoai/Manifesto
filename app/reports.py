"""Driver route reports and operation output bundles."""
from __future__ import annotations

import datetime
import math
import os
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.manifest.planning import ReservationBlock, read_blocks


HEADERS = [
    "SIRA", "YOLCU ADI", "PAX", "OTEL", "ODA / İRTİBAT",
    "PICKUP", "ACENTE", "BALON", "GELECEĞİ YER", "NOT",
]

# Rezervasyon başına bir kez yazılan (yolcu satırlarına yayılan, birleşik) alanlar,
# HEADERS'taki sırayla. SIRA ve YOLCU ADI yolcu başınadır.
GROUP_FIELDS = (
    "pax", "hotel", "room", "pickup", "agency", "balloon", "coming_place", "note",
)
GROUP_COLS = tuple(range(2, len(HEADERS)))   # 0-tabanlı kolon indexleri

# Rezervasyon PDF'te tek parça kalır (reportlab rowspan içinden bölmez). Bu sınırı
# aşan rezervasyon sayfaya sığsın diye parçalanır; ortak alanlar her parçada tekrarlanır.
PDF_MAX_GROUP_ROWS = 20

# DESIGN.md "Kısık Tüf": tek vurgu lapis; turuncu ve mor yok.
LAPIS = "3D5A8A"
ON_LAPIS = "EEF0F3"
INK = "2E2B28"
LINE = "C4BDB3"
ZEBRA = "F1EFEC"

_TIME_RE = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?!\d)")
_DOT_TIME_RE = re.compile(r"(\d{1,2})\.(\d{2})")


def _safe_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", value.strip())
    return cleaned or "ATANMAMIS"


def format_pickup(value) -> str:
    """Pickup saatini "HH:MM" yapar.

    Kabul: `datetime.time` / `datetime.datetime`, "05:20:00", "2026-06-22 05:20:00",
    "5:20", Excel gün kesri ("0.2222"). Tanınmayan değer olduğu gibi döner.
    """
    if value is None:
        return ""
    if isinstance(value, (datetime.datetime, datetime.time)):
        return f"{value.hour:02d}:{value.minute:02d}"
    text = str(value).strip()
    if not text:
        return ""
    # Önce "HH:MM[:SS]" (tarihli metinde de); "04.10" yalnız tek başınaysa saat sayılır,
    # yoksa "22.06.2026" gibi bir tarih saat diye okunurdu.
    match = _TIME_RE.search(text) or _DOT_TIME_RE.fullmatch(text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour < 24 and minute < 60:
            return f"{hour:02d}:{minute:02d}"
    try:
        fraction = float(text.replace(",", "."))
    except ValueError:
        return text
    if 0 <= fraction < 1:
        minutes = round(fraction * 24 * 60) % (24 * 60)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
    return text


def driver_groups(blocks: list[ReservationBlock]) -> dict[str, list[dict]]:
    """Şoför -> rezervasyon grupları (pickup, otel, satır sırasıyla).

    Her grup: `GROUP_FIELDS` ortak alanları bir kez + `passengers` (yolcu adları).
    """
    grouped_blocks: dict[str, list[ReservationBlock]] = defaultdict(list)
    for block in blocks:
        grouped_blocks[block.driver or "ATANMAMIŞ"].append(block)
    grouped: dict[str, list[dict]] = {}
    for driver, driver_blocks in grouped_blocks.items():
        driver_blocks.sort(key=lambda block: (
            format_pickup(block.pickup) or "99:99", block.hotel, block.lead_row
        ))
        groups = []
        for block in driver_blocks:
            passengers = [p.name or "(kimlik eksik)" for p in block.passengers]
            groups.append({
                "pax": block.pax if block.pax is not None else "",
                "hotel": block.hotel,
                "room": block.room,
                "pickup": format_pickup(block.pickup),
                "agency": block.agency,
                "balloon": block.balloon,
                "coming_place": block.coming_place,
                "note": block.note,
                "passengers": passengers or ["(kimlik eksik)"],
            })
        grouped[driver] = groups
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def driver_rows(blocks: list[ReservationBlock]) -> dict[str, list[dict]]:
    """Önizleme için düz yolcu listesi (PAX yalnız rezervasyonun ilk satırında)."""
    grouped: dict[str, list[dict]] = {}
    for driver, groups in driver_groups(blocks).items():
        rows: list[dict] = []
        for group_index, group in enumerate(groups):
            for index, name in enumerate(group["passengers"]):
                row = {key: group[key] for key in GROUP_FIELDS}
                row["pax"] = group["pax"] if index == 0 else ""
                row["name"] = name
                row["group"] = group_index
                rows.append(row)
        grouped[driver] = rows
    return grouped


def driver_summary(
    blocks: list[ReservationBlock],
    overrides: dict[str, str] | None = None,
) -> list[dict]:
    overrides = overrides or {}
    mapping: dict[str, set[str]] = defaultdict(set)
    for block in blocks:
        if block.balloon:
            mapping[block.balloon].add(block.driver or "ATANMAMIŞ")
    rows = []
    for balloon in sorted(mapping):
        default = ", ".join(sorted(mapping[balloon]))
        rows.append({
            "balloon": balloon,
            "driver": overrides.get(balloon, default),
        })
    return rows


def _group_values(group: dict) -> list:
    return [group[key] for key in GROUP_FIELDS]


XLSX_WIDTHS = [7, 28, 7, 22, 16, 9, 20, 9, 18, 40]
_XLSX_LINE_HEIGHT = 15.0


def _excel_report(path: Path, sheet: str, driver: str, groups: list[dict]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "YOL LİSTESİ"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(HEADERS))
    ws["A1"] = f"İRTİFA - {sheet} - ŞOFÖR {driver}"
    ws["A1"].font = Font(bold=True, size=16, color=INK)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    thin = Side(style="thin", color=LINE)
    strong = Side(style="medium", color=INK)
    for col, header in enumerate(HEADERS, 1):
        cell = ws.cell(3, col, header)
        cell.font = Font(bold=True, color=ON_LAPIS)
        cell.fill = PatternFill("solid", fgColor=LAPIS)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(left=thin, right=thin, top=thin, bottom=strong)
    ws.row_dimensions[3].height = 20

    zebra = PatternFill("solid", fgColor=ZEBRA)
    centred = {1, 3, 6, 8}          # SIRA, PAX, PICKUP, BALON (1-tabanlı)
    row = 4
    seq = 0
    for group_index, group in enumerate(groups):
        names = group["passengers"]
        first, last = row, row + len(names) - 1
        fill = zebra if group_index % 2 else None
        # Yolcu başına kolonlar: SIRA, YOLCU ADI.
        for offset, name in enumerate(names):
            seq += 1
            r = first + offset
            for col, value in ((1, seq), (2, name)):
                cell = ws.cell(r, col, value)
                cell.border = Border(
                    left=thin, right=thin,
                    top=strong if r == first else thin,
                    bottom=strong if r == last else thin,
                )
                cell.alignment = Alignment(
                    horizontal="center" if col in centred else None,
                    vertical="center", wrap_text=True,
                )
                if fill:
                    cell.fill = fill
        # Rezervasyon başına kolonlar: bir kez yazılır, yolcu satırlarına birleştirilir.
        values = _group_values(group)
        for col, value in zip(range(3, len(HEADERS) + 1), values):
            cell = ws.cell(first, col, value)
            cell.border = Border(left=thin, right=thin, top=strong, bottom=strong)
            cell.alignment = Alignment(
                horizontal="center" if col in centred else "left",
                vertical="center", wrap_text=True,
            )
            if fill:
                cell.fill = fill
            if last > first:
                ws.merge_cells(start_row=first, start_column=col,
                               end_row=last, end_column=col)
        # Excel birleşik hücrede satırı kendisi büyütmez: uzun not/otel için yükseklik ver.
        needed_lines = 1
        for col, value in zip(range(3, len(HEADERS) + 1), values):
            text = str(value if value is not None else "")
            if text:
                per_line = max(1, int(XLSX_WIDTHS[col - 1] * 1.1))
                needed_lines = max(needed_lines, math.ceil(len(text) / per_line))
        per_row = needed_lines * _XLSX_LINE_HEIGHT / len(names)
        if per_row > _XLSX_LINE_HEIGHT:
            for r in range(first, last + 1):
                ws.row_dimensions[r].height = round(per_row, 1)
        row = last + 1

    for index, width in enumerate(XLSX_WIDTHS, 1):
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.freeze_panes = "A4"
    ws.print_title_rows = "3:3"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    wb.save(path)
    wb.close()
    return path


# Türkçe karakter (İ, ş, ğ) için gömülü TTF şart; Helvetica bunları çizemez.
_PDF_FONT_CANDIDATES = (
    ("arial.ttf", "arialbd.ttf"),
    ("segoeui.ttf", "segoeuib.ttf"),
    ("calibri.ttf", "calibrib.ttf"),
    ("tahoma.ttf", "tahomabd.ttf"),
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
)


def _font_dirs() -> list[Path]:
    windir = os.environ.get("WINDIR") or r"C:\Windows"
    return [
        Path(__file__).resolve().parent.parent / "assets" / "fonts",
        Path(windir) / "Fonts",
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/Library/Fonts"),
    ]


def _register_pdf_fonts() -> tuple[str, str]:
    if "IrtifaSans" in pdfmetrics.getRegisteredFontNames():
        return "IrtifaSans", "IrtifaSans-Bold"
    for regular_name, bold_name in _PDF_FONT_CANDIDATES:
        for folder in _font_dirs():
            regular, bold = folder / regular_name, folder / bold_name
            if regular.exists() and bold.exists():
                try:
                    pdfmetrics.registerFont(TTFont("IrtifaSans", str(regular)))
                    pdfmetrics.registerFont(TTFont("IrtifaSans-Bold", str(bold)))
                except Exception:
                    continue
                return "IrtifaSans", "IrtifaSans-Bold"
    return "Helvetica", "Helvetica-Bold"


PDF_COL_WIDTHS_MM = [9, 44, 10, 30, 24, 15, 28, 14, 28, 75]   # 277 = A4 yatay - kenarlar


def _pdf_chunks(groups: list[dict]) -> list[tuple[dict, list[str], int]]:
    """(grup, yolcu adları, grup indexi); uzun grup PDF_MAX_GROUP_ROWS'luk parçalara bölünür."""
    chunks = []
    for group_index, group in enumerate(groups):
        names = group["passengers"]
        for start in range(0, len(names), PDF_MAX_GROUP_ROWS):
            chunks.append((group, names[start:start + PDF_MAX_GROUP_ROWS], group_index))
    return chunks


def _pdf_table_parts(
    groups: list[dict], regular: str, bold: str
) -> tuple[list[list], list[tuple]]:
    """PDF tablosunun hücreleri ve TableStyle komutları (test edilebilsin diye ayrı)."""
    cell = ParagraphStyle(
        "cell", fontName=regular, fontSize=8, leading=9.6,
        textColor=colors.HexColor(f"#{INK}"),
    )
    centre = ParagraphStyle("cell-c", parent=cell, alignment=TA_CENTER)
    head = ParagraphStyle(
        "head", fontName=bold, fontSize=8, leading=9.6, alignment=TA_CENTER,
        textColor=colors.HexColor(f"#{ON_LAPIS}"),
    )
    centred = {0, 2, 5, 7}          # SIRA, PAX, PICKUP, BALON (0-tabanlı)

    def para(value, col):
        text = escape(str(value if value is not None else ""))
        return Paragraph(text, centre if col in centred else cell)

    data: list[list] = [[Paragraph(escape(header), head) for header in HEADERS]]
    style: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{LAPIS}")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(f"#{LINE}")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.HexColor(f"#{INK}")),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    seq = 0
    previous_group = None
    for group, names, group_index in _pdf_chunks(groups):
        new_group = group_index != previous_group
        previous_group = group_index
        first = len(data)
        last = first + len(names) - 1
        shared = _group_values(group)
        for offset, name in enumerate(names):
            seq += 1
            row = [para(seq, 0), para(name, 1)]
            if offset == 0:
                row += [para(value, col) for col, value in zip(GROUP_COLS, shared)]
            else:
                row += [""] * len(GROUP_COLS)
            data.append(row)
        if last > first:
            for col in GROUP_COLS:
                style.append(("SPAN", (col, first), (col, last)))
        if first > 1 and new_group:      # aynı rezervasyonun parçaları arasında değil
            style.append(("LINEABOVE", (0, first), (-1, first), 1.2,
                          colors.HexColor(f"#{INK}")))
        if group_index % 2:
            style.append(("BACKGROUND", (0, first), (-1, last),
                          colors.HexColor(f"#{ZEBRA}")))
    return data, style


def _pdf_report(path: Path, sheet: str, driver: str, groups: list[dict]) -> Path:
    regular, bold = _register_pdf_fonts()
    title = f"İRTİFA - {sheet} - ŞOFÖR {driver}"
    document = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=title,
    )
    title_style = ParagraphStyle(
        "title", fontName=bold, fontSize=15, alignment=TA_CENTER, spaceAfter=5 * mm,
        textColor=colors.HexColor(f"#{INK}"),
    )
    data, style = _pdf_table_parts(groups, regular, bold)
    # repeatRows=1: rezervasyon sayfa sonuna denk gelirse başlık yeni sayfada tekrarlanır.
    table = Table(data, repeatRows=1, colWidths=[w * mm for w in PDF_COL_WIDTHS_MM])
    table.setStyle(TableStyle(style))
    story = [
        Paragraph(escape(title), title_style),
        Spacer(1, 2 * mm),
        table,
    ]
    document.build(story)
    return path


def export_driver_reports(
    planning_xlsx: Path,
    sheet: str,
    out_dir: Path,
    *,
    selected_driver: str = "",
) -> list[Path]:
    grouped = driver_groups(read_blocks(planning_xlsx, sheet))
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for driver, groups in grouped.items():
        if selected_driver and driver != selected_driver:
            continue
        base = f"Sofor_{_safe_name(driver)}"
        outputs.append(_excel_report(out_dir / f"{base}.xlsx", sheet, driver, groups))
        outputs.append(_pdf_report(out_dir / f"{base}.pdf", sheet, driver, groups))
    return outputs


def export_summary(
    planning_xlsx: Path,
    sheet: str,
    out_dir: Path,
    *,
    overrides: dict[str, str] | None = None,
) -> list[Path]:
    rows = driver_summary(read_blocks(planning_xlsx, sheet), overrides)
    out_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = out_dir / "Arac_Ozeti.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ARAÇ ÖZETİ"
    ws.append(["BALON", "ŞOFÖR / ARAÇ"])
    for row in rows:
        ws.append([row["balloon"], row["driver"]])
    for cell in ws[1]:
        cell.font = Font(bold=True, color=ON_LAPIS)
        cell.fill = PatternFill("solid", fgColor=LAPIS)
    ws.column_dimensions["A"].width = 15
    ws.column_dimensions["B"].width = 35
    wb.save(xlsx_path)
    wb.close()

    text_path = out_dir / "Arac_Ozeti.txt"
    text_path.write_text(
        "\n".join(f"{row['balloon']}: {row['driver']}" for row in rows),
        encoding="utf-8",
    )
    return [xlsx_path, text_path]


def zip_outputs(paths: list[Path], target: Path) -> Path:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, arcname=path.name)
    return target
