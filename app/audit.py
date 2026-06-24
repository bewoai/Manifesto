"""Minimal-PII audit trail helpers."""
from __future__ import annotations

import json
from typing import Any

from app.db import connect


def record(
    action: str,
    *,
    actor: str = "system",
    sheet: str | None = None,
    reservation_row: int | None = None,
    detail: dict[str, Any] | str | None = None,
) -> None:
    if isinstance(detail, dict):
        detail_text = json.dumps(detail, ensure_ascii=False, separators=(",", ":"))
    else:
        detail_text = detail
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO audit_log(actor, action, sheet, reservation_row, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (actor, action, sheet, reservation_row, detail_text),
        )
        conn.commit()
    finally:
        conn.close()


def list_entries(*, limit: int = 200, actor: str = "", action: str = "") -> list[dict]:
    clauses: list[str] = []
    values: list[Any] = []
    if actor:
        clauses.append("actor = ?")
        values.append(actor)
    if action:
        clauses.append("action = ?")
        values.append(action)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    values.append(max(1, min(int(limit), 1000)))
    conn = connect()
    try:
        rows = conn.execute(
            f"""
            SELECT id, ts, actor, action, sheet, reservation_row, detail
            FROM audit_log
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
