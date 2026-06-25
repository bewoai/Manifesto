from __future__ import annotations

from fastapi import HTTPException
from starlette.requests import Request

from app.db import connect, init_db
from app.main import ResolveManualReviewRequest, api_passport_manual_review_resolve
from app.main import app


def _request() -> Request:
    return Request({"type": "http", "headers": []})


def test_passport_cleanup_route_is_registered():
    assert any(
        route.path == "/api/passport/cleanup" and "POST" in (route.methods or set())
        for route in app.routes
    )


def test_passport_cleanup_rejects_non_date_sheet():
    try:
        from app.main import api_passport_cleanup
        api_passport_cleanup(_request(), {"sheet": "Sayfa2"})
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Tarih olmayan sayfa için temizlik kabul edildi.")


def test_manual_review_approval_returns_planning_record(tmp_path, monkeypatch):
    db_path = tmp_path / "review.db"
    monkeypatch.setenv("IRTIFA_DB_PATH", str(db_path))
    init_db()
    conn = connect()
    cursor = conn.execute(
        """
        INSERT INTO passport_extraction(
            name, document_number, status, requires_manual_review
        ) VALUES ('ESKI AD', 'OLD1', 'pending', 1)
        """
    )
    extraction_id = cursor.lastrowid
    conn.commit()
    conn.close()

    result = api_passport_manual_review_resolve(
        ResolveManualReviewRequest(
            id=extraction_id,
            action="approve",
            corrected_data={
                "nationality": "tur",
                "sex": "f",
                "name": "ayse yilmaz",
                "document_number": "u123456",
            },
        ),
        _request(),
    )

    assert result["record"] == {
        "extraction_id": extraction_id,
        "nationality": "TUR",
        "sex": "F",
        "name": "AYSE YILMAZ",
        "passport_no": "U123456",
        "green": True,
        "flags": [],
        "requires_manual_review": False,
        "manual_reviewed": True,
        "source": "",
    }
    conn = connect()
    row = conn.execute(
        "SELECT checks_ok, requires_manual_review, manual_review_reason "
        "FROM passport_extraction WHERE id = ?",
        (extraction_id,),
    ).fetchone()
    conn.close()
    assert dict(row) == {
        "checks_ok": 1,
        "requires_manual_review": 0,
        "manual_review_reason": "operator_approved",
    }


def test_manual_review_rejects_duplicate_document(tmp_path, monkeypatch):
    db_path = tmp_path / "duplicate.db"
    monkeypatch.setenv("IRTIFA_DB_PATH", str(db_path))
    init_db()
    conn = connect()
    conn.execute(
        """
        INSERT INTO passport_extraction(
            document_number, status, requires_manual_review
        ) VALUES ('DUP123', 'approved', 0)
        """
    )
    cursor = conn.execute(
        """
        INSERT INTO passport_extraction(status, requires_manual_review)
        VALUES ('pending', 1)
        """
    )
    extraction_id = cursor.lastrowid
    conn.commit()
    conn.close()

    try:
        api_passport_manual_review_resolve(
            ResolveManualReviewRequest(
                id=extraction_id,
                action="approve",
                corrected_data={
                    "nationality": "TUR",
                    "sex": "M",
                    "name": "TEST USER",
                    "document_number": "DUP123",
                },
            ),
            _request(),
        )
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("Mükerrer belge numarası kabul edildi.")
