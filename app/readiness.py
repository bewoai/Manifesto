"""Operational readiness checks for a flight-day sheet."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.manifest.planning import ReservationBlock, block_seats, read_blocks


def check_blocks(
    blocks: list[ReservationBlock],
    *,
    balloon_capacity: int,
    pending_review_count: int = 0,
) -> dict:
    issues: list[dict] = []
    balloon_load: Counter[str] = Counter()
    document_rows: dict[str, list[int]] = {}

    for block in blocks:
        expected = block.pax if block.pax is not None else len(block.rows)
        if expected != len(block.rows):
            issues.append({
                "code": "pax_mismatch",
                "lead_row": block.lead_row,
                "message": f"PAX {expected}, yolcu satırı {len(block.rows)}.",
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
                issues.append({
                    "code": "missing_identity",
                    "lead_row": block.lead_row,
                    "row": passenger.row,
                    "message": f"Satır {passenger.row}: {', '.join(missing)} eksik.",
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
                    "message": f"Satır {block.lead_row}: {label} eksik.",
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
        if used > balloon_capacity:
            issues.append({
                "code": "capacity_overflow",
                "balloon": balloon,
                "message": f"{balloon} kapasitesi aşıldı: {used}/{balloon_capacity}.",
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
        "total_blocks": len(blocks),
        "total_passengers": sum(len(block.passengers) for block in blocks),
    }


def check_workbook(
    planning_xlsx: Path,
    sheet: str,
    *,
    balloon_capacity: int,
    pending_review_count: int = 0,
) -> dict:
    return check_blocks(
        read_blocks(planning_xlsx, sheet),
        balloon_capacity=balloon_capacity,
        pending_review_count=pending_review_count,
    )
