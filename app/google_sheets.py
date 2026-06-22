"""Google Sheets bridge for the planning workbook.

The app keeps Excel as the internal planning format. For Google Sheets mode we
export the live spreadsheet to a temporary xlsx for reading/exporting manifests,
then write approved identity fields back with the Sheets API.
"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Iterable

from app import config
from app.settings import Settings

SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
)


def _require_google_libs():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as exc:
        raise RuntimeError(
            "Google Sheets bağlantısı için google-api-python-client ve google-auth "
            "paketleri kurulu olmalı."
        ) from exc
    return service_account, build, MediaIoBaseDownload


def _credentials(settings: Settings):
    service_account, _, _ = _require_google_libs()
    path = Path(settings.google_credentials_json)
    if not path.exists():
        raise FileNotFoundError(f"Google servis hesabı JSON dosyası bulunamadı: {path}")
    return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)


def _sheets_service(settings: Settings):
    _, build, _ = _require_google_libs()
    return build("sheets", "v4", credentials=_credentials(settings), cache_discovery=False)


def _drive_service(settings: Settings):
    _, build, _ = _require_google_libs()
    return build("drive", "v3", credentials=_credentials(settings), cache_discovery=False)


def _spreadsheet_id(settings: Settings) -> str:
    sid = settings.google_spreadsheet_id.strip()
    if not sid:
        raise ValueError("Google Sheet ID boş. Ayarlar'dan Sheet ID girin.")
    return sid


def list_sheets(settings: Settings) -> list[str]:
    """Return visible tab names for the configured Google spreadsheet."""
    service = _sheets_service(settings)
    meta = service.spreadsheets().get(
        spreadsheetId=_spreadsheet_id(settings),
        fields="sheets(properties(title,hidden))",
    ).execute()
    return [
        s["properties"]["title"]
        for s in meta.get("sheets", [])
        if not s.get("properties", {}).get("hidden")
    ]


def _sheet_metadata(settings: Settings) -> list[dict]:
    service = _sheets_service(settings)
    meta = service.spreadsheets().get(
        spreadsheetId=_spreadsheet_id(settings),
        fields="sheets(properties(sheetId,title,hidden,index))",
    ).execute()
    return meta.get("sheets", [])


def create_day_sheet(settings: Settings, new_sheet: str, source_sheet: str | None = None) -> None:
    """Duplicate a source tab, rename it, and clear planning data rows."""
    sheets = _sheet_metadata(settings)
    titles = [s["properties"]["title"] for s in sheets]
    if new_sheet in titles:
        raise ValueError(f"'{new_sheet}' sayfası zaten var.")

    visible = [s for s in sheets if not s.get("properties", {}).get("hidden")]
    source = None
    if source_sheet:
        source = next((s for s in sheets if s["properties"]["title"] == source_sheet), None)
    if source is None and visible:
        source = visible[-1]
    if source is None:
        raise ValueError("Kopyalanacak gün sayfası bulunamadı.")

    service = _sheets_service(settings)
    service.spreadsheets().batchUpdate(
        spreadsheetId=_spreadsheet_id(settings),
        body={
            "requests": [{
                "duplicateSheet": {
                    "sourceSheetId": source["properties"]["sheetId"],
                    "newSheetName": new_sheet,
                }
            }]
        },
    ).execute()
    service.spreadsheets().values().clear(
        spreadsheetId=_spreadsheet_id(settings),
        range=f"{_quote_sheet(new_sheet)}!A{config.PLANNING_FIRST_DATA_ROW}:{_col_letter(config.COL_PASSPORT_NO)}",
        body={},
    ).execute()


def download_as_xlsx(settings: Settings) -> Path:
    """Export the configured Google spreadsheet to a temporary xlsx file."""
    drive = _drive_service(settings)
    request = drive.files().export_media(
        fileId=_spreadsheet_id(settings),
        mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    handle = io.BytesIO()
    downloader = _require_google_libs()[2](handle, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    target = Path(tempfile.gettempdir()) / f"balon-planning-{_spreadsheet_id(settings)}.xlsx"
    target.write_bytes(handle.getvalue())
    return target


def _col_letter(col: int) -> str:
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _quote_sheet(sheet: str) -> str:
    return "'" + sheet.replace("'", "''") + "'"


def write_identity(settings: Settings, sheet: str, updates: dict[int, dict]) -> None:
    """Write only passport identity columns back to the configured Google Sheet."""
    if not updates:
        return

    field_to_col = {
        "nationality": config.COL_UYRUK,
        "sex": config.COL_MF,
        "name": config.COL_NAME,
        "passport_no": config.COL_PASSPORT_NO,
    }
    data: list[dict] = []
    for row, fields in updates.items():
        for key, col in field_to_col.items():
            if key not in fields or fields[key] is None:
                continue
            cell = f"{_quote_sheet(sheet)}!{_col_letter(col)}{row}"
            data.append({"range": cell, "values": [[fields[key]]]})

    service = _sheets_service(settings)
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=_spreadsheet_id(settings),
        body={
            "valueInputOption": "USER_ENTERED",
            "data": data,
        },
    ).execute()


def write_operation_details(
    settings: Settings,
    sheet: str,
    lead_row: int,
    rows: list[int],
    fields: dict,
) -> None:
    """Write reservation operation fields back to the configured Google Sheet."""
    data: list[dict] = []
    for key, col in config.OPERATION_FIELD_TO_COL.items():
        if key not in fields:
            continue
        value = fields[key]
        target_rows = rows if key in config.BLOCK_WIDE_OPERATION_FIELDS else [lead_row]
        for row in target_rows:
            cell = f"{_quote_sheet(sheet)}!{_col_letter(col)}{row}"
            data.append({"range": cell, "values": [[value]]})
    if not data:
        return

    service = _sheets_service(settings)
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=_spreadsheet_id(settings),
        body={
            "valueInputOption": "USER_ENTERED",
            "data": data,
        },
    ).execute()
