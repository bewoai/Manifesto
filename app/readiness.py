"""Operational readiness checks for a flight-day sheet."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from app import config
from app.manifest.planning import Capacity, ReservationBlock, block_seats, capacity_fn, read_blocks


def _where(row: int, name: str = "") -> str:
    """Uyarı öneki: "Satır 83 · AHMET YILMAZ" (isim yoksa "Satır 83")."""
    return f"Satır {row} · {name}" if name else f"Satır {row}"



def check_blocks(
    blocks: list[ReservationBlock],
    *,
    balloon_capacity: Capacity = config.DEFAULT_BALLOON_CAPACITY,
    daily_max_balloons: int = 0,
    daily_capacity: int = 0,
    pending_review_count: int = 0,
) -> dict:
    """Gün sayfasının uçuşa hazırlık kontrolü.

    `balloon_capacity`: tek int ya da `kod → kapasite` (ör. `Settings.capacity_for`).
    `daily_max_balloons`: > 0 ise yolcu taşıyan balon sayısı bunu aşarsa uyarı.
    `daily_capacity`: > 0 ise günün toplam yolcusu bunu aşarsa uyarı (acentenin günlük kapasitesi).
    `lead_row` taşıyan her uyarıda `lead_name` de vardır (arayüz rezervasyona bağlantı kurar).
    """
    cap = capacity_fn(balloon_capacity)
    issues: list[dict] = []
    balloon_load: Counter[str] = Counter()
    document_rows: dict[str, list[int]] = {}

    for block in blocks:
        lead_where = _where(block.lead_row, block.lead_name)
        expected = block.pax if block.pax is not None else len(block.rows)
        if expected != len(block.rows):
            issues.append({
                "code": "pax_mismatch",
                "lead_row": block.lead_row,
                "lead_name": block.lead_name,
                "message": f"{lead_where}: PAX {expected}, yolcu satırı {len(block.rows)}.",
            })

        for passenger in block.passengers:
            missing = []
            if not passenger.nationality:
                missing.append("uyruk")
            if not passenger.sex:
                missing.append("cinsiyet")
            if not passenger.name:
                missing.append("isim")
            if not passenger.passport_no:
                missing.append("pasaport/kimlik no")
            if missing:
                who = passenger.name or (f"{block.lead_name} grubu" if block.lead_name else "")
                issues.append({
                    "code": "missing_identity",
                    "lead_row": block.lead_row,
                    "lead_name": block.lead_name,
                    "row": passenger.row,
                    "message": f"{_where(passenger.row, who)}: {', '.join(missing)} eksik.",
                })
            if passenger.passport_no:
                document_rows.setdefault(passenger.passport_no.upper(), []).append(passenger.row)

        required = {
            "balloon": ("balon", block.balloon),
            "pilot": ("pilot", block.pilot),
            "driver": ("şoför", block.driver),
            "pickup": ("pickup", block.pickup),
            "hotel": ("otel", block.hotel),
            "coming_place": ("geleceği yer", block.coming_place),
        }
        for code, (label, value) in required.items():
            if not value:
                issues.append({
                    "code": f"missing_{code}",
                    "lead_row": block.lead_row,
                    "lead_name": block.lead_name,
                    "message": f"{lead_where}: {label} eksik.",
                })

        if block.balloon:
            balloon_load[block.balloon] += block_seats(block)

    for document_no, rows in document_rows.items():
        if len(rows) > 1:
            issues.append({
                "code": "duplicate_document",
                "rows": rows,
                "message": f"{document_no} birden fazla satırda kullanılmış: {rows}.",
            })

    for balloon, used in balloon_load.items():
        limit = cap(balloon)
        if used > limit:
            issues.append({
                "code": "capacity_overflow",
                "balloon": balloon,
                "used": used,
                "capacity": limit,
                "message": f"{balloon} kapasitesi aşıldı: {used}/{limit}.",
            })

    balloons_in_use = sum(1 for used in balloon_load.values() if used > 0)
    daily_max_balloons = int(daily_max_balloons or 0)
    if daily_max_balloons > 0 and balloons_in_use > daily_max_balloons:
        issues.append({
            "code": "daily_balloon_limit",
            "balloons_in_use": balloons_in_use,
            "limit": daily_max_balloons,
            "message": f"Günlük balon sınırı aşıldı: {balloons_in_use}/{daily_max_balloons} balon.",
        })

    total_seats = sum(balloon_load.values())
    daily_capacity = int(daily_capacity or 0)
    if daily_capacity > 0 and total_seats > daily_capacity:
        issues.append({
            "code": "daily_capacity_exceeded",
            "used": total_seats,
            "capacity": daily_capacity,
            "message": f"Günlük kapasite aşıldı: {total_seats}/{daily_capacity} kişi.",
        })

    if pending_review_count:
        issues.append({
            "code": "pending_ocr_review",
            "message": f"{pending_review_count} sarı OCR sonucu henüz onaylanmadı.",
        })

    by_code = Counter(issue["code"] for issue in issues)
    return {
        "ready": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "counts": dict(by_code),
        "balloon_load": dict(balloon_load),
        "balloons_in_use": balloons_in_use,
        "total_blocks": len(blocks),
        "total_passengers": sum(len(block.passengers) for block in blocks),
    }


def check_workbook(
    planning_xlsx: Path,
    sheet: str,
    *,
    balloon_capacity: Capacity = config.DEFAULT_BALLOON_CAPACITY,
    daily_max_balloons: int = 0,
    daily_capacity: int = 0,
    pending_review_count: int = 0,
) -> dict:
    return check_blocks(
        read_blocks(planning_xlsx, sheet),
        balloon_capacity=balloon_capacity,
        daily_max_balloons=daily_max_balloons,
        daily_capacity=daily_capacity,
        pending_review_count=pending_review_count,
    )
