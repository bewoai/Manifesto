"""Excel Uçuş Planı -> SQLite Aktarım (Import) modülü.
"""
from __future__ import annotations

import json
import datetime
from pathlib import Path
from typing import Optional, Any
import sqlite3

from app.db import connect
from app.manifest.planning import read_blocks, list_sheets, read_rows, ReservationBlock, PassengerIdentity

def sheet_name_to_iso(sheet_name: str) -> str | None:
    parts = sheet_name.strip().split('.')
    if len(parts) == 3:
        try:
            day = int(parts[0])
            month = int(parts[1])
            year_val = int(parts[2])
            if year_val < 100:
                year = 2000 + year_val
            else:
                year = year_val
            dt = datetime.date(year, month, day)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None

def import_excel_to_sqlite(
    db_path: Optional[Path] = None,
    planning_xlsx: Optional[Path] = None,
    sheet_name: Optional[str] = None
) -> dict[str, Any]:
    """Excel planlama dosyasındaki verileri SQLite veritabanına aktarır.
    
    Eşleştirme (Upsert) Mantığı:
    1. Pasaport numarası doluysa `passport_no` ile eşleştirilir.
    2. Pasaport numarası boşsa `full_name COLLATE NOCASE` ile eşleştirilir.
    """
    if not planning_xlsx:
        from app import settings as settings_mod
        s = settings_mod.load()
        planning_xlsx = s.planning_path()
        
    if not planning_xlsx.exists():
        raise FileNotFoundError(f"Planlama Excel dosyası bulunamadı: {planning_xlsx}")

    conn = connect(db_path)
    cursor = conn.cursor()

    sheets_to_process = []
    if sheet_name:
        sheets_to_process = [sheet_name]
    else:
        # Tüm sayfaları bul ve tarih formatındakileri al
        all_sheets = list_sheets(planning_xlsx)
        for s in all_sheets:
            if sheet_name_to_iso(s) is not None:
                sheets_to_process.append(s)

    stats = {
        "sheets_processed": [],
        "total_rows": 0,
        "passengers_added": 0,
        "passengers_updated": 0,
        "reservations_created": 0,
        "status": "success",
        "message": ""
    }

    try:
        for s_name in sheets_to_process:
            iso_date = sheet_name_to_iso(s_name)
            if not iso_date:
                if sheet_name:
                    raise ValueError(f"Geçersiz sayfa adı (tarih formatında olmalı, ör. DD.MM.YYYY): {s_name}")
                continue

            # 1. Flight gününü bul veya oluştur
            cursor.execute("SELECT id FROM flights WHERE flight_date = ?", (iso_date,))
            row = cursor.fetchone()
            if row:
                flight_id = row["id"]
            else:
                cursor.execute(
                    "INSERT INTO flights (flight_date, capacity) VALUES (?, ?)",
                    (iso_date, 112)
                )
                flight_id = cursor.lastrowid

            # 2. Bu uçuş gününün eski rezervasyonlarını sil (idempotent import)
            cursor.execute("DELETE FROM reservations WHERE flight_id = ?", (flight_id,))

            # 3. Excel'den rezervasyon bloklarını oku
            blocks = read_blocks(planning_xlsx, s_name)

            for block in blocks:
                # Rezervasyon kaydını ekle
                cursor.execute(
                    """
                    INSERT INTO reservations (
                        flight_id, pax, hotel, pickup_time, reserved_by, agency,
                        balloon_code, pilot, driver_no, destination, notes, room_no,
                        flight_firm, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        flight_id,
                        block.pax if block.pax is not None else len(block.rows),
                        block.hotel,
                        block.pickup,
                        block.reserved_by,
                        block.agency,
                        block.balloon,
                        block.pilot,
                        block.driver,
                        block.coming_place,
                        block.note,
                        block.room,
                        block.company,
                        block.lead_row
                    )
                )
                res_id = cursor.lastrowid
                stats["reservations_created"] += 1

                # Her yolcuyu işle ve rezervasyonla ilişkilendir
                for seq, passenger in enumerate(block.passengers, start=1):
                    stats["total_rows"] += 1
                    name_clean = passenger.name.strip()
                    passport_clean = passenger.passport_no.strip() if passenger.passport_no else ""
                    nationality_clean = passenger.nationality.strip() if passenger.nationality else ""
                    sex_clean = passenger.sex.strip().upper() if passenger.sex else ""

                    # Tamamen boş yolcu satırı (isim de yok) ise atla
                    if not name_clean and not passport_clean:
                        continue

                    passenger_id = None
                    # Yolcuyu bulma mantığı
                    if passport_clean:
                        cursor.execute(
                            "SELECT id, full_name, nationality, sex FROM passengers WHERE passport_no = ?",
                            (passport_clean,)
                        )
                        p_row = cursor.fetchone()
                        if p_row:
                            passenger_id = p_row["id"]
                            cursor.execute(
                                """
                                UPDATE passengers 
                                SET full_name = ?, nationality = ?, sex = ?, updated_at = datetime('now')
                                WHERE id = ?
                                """,
                                (name_clean or p_row["full_name"], nationality_clean or p_row["nationality"], sex_clean or p_row["sex"], passenger_id)
                            )
                            stats["passengers_updated"] += 1
                    
                    if passenger_id is None and name_clean:
                        cursor.execute(
                            "SELECT id, passport_no, nationality, sex FROM passengers WHERE full_name = ? COLLATE NOCASE",
                            (name_clean,)
                        )
                        p_row = cursor.fetchone()
                        if p_row:
                            passenger_id = p_row["id"]
                            new_passport = passport_clean or p_row["passport_no"]
                            cursor.execute(
                                """
                                UPDATE passengers 
                                SET passport_no = ?, nationality = ?, sex = ?, updated_at = datetime('now')
                                WHERE id = ?
                                """,
                                (new_passport, nationality_clean or p_row["nationality"], sex_clean or p_row["sex"], passenger_id)
                            )
                            stats["passengers_updated"] += 1

                    if passenger_id is None:
                        cursor.execute(
                            """
                            INSERT INTO passengers (passport_no, nationality, sex, full_name)
                            VALUES (?, ?, ?, ?)
                            """,
                            (passport_clean or None, nationality_clean or None, sex_clean or None, name_clean)
                        )
                        passenger_id = cursor.lastrowid
                        stats["passengers_added"] += 1

                    # Rezervasyon-yolcu ilişkisini ekle
                    cursor.execute(
                        """
                        INSERT INTO reservation_passengers (reservation_id, passenger_id, seq)
                        VALUES (?, ?, ?)
                        """,
                        (res_id, passenger_id, seq)
                    )

            stats["sheets_processed"].append(s_name)

        conn.commit()
        
        # import_logs kaydı ekle
        stats_summary = json.dumps({
            "sheets": stats["sheets_processed"],
            "total_rows": stats["total_rows"],
            "passengers_added": stats["passengers_added"],
            "passengers_updated": stats["passengers_updated"],
            "reservations_created": stats["reservations_created"]
        }, ensure_ascii=False)
        
        cursor.execute(
            """
            INSERT INTO import_logs (file_name, sheet_name, status, summary)
            VALUES (?, ?, ?, ?)
            """,
            (
                planning_xlsx.name,
                sheet_name or "ALL_SHEETS",
                "success",
                stats_summary
            )
        )
        conn.commit()
        stats["message"] = f"{len(stats['sheets_processed'])} sayfa başarıyla SQLite'a aktarıldı."

    except Exception as e:
        conn.rollback()
        stats["status"] = "failed"
        stats["message"] = f"Hata oluştu: {e}"
        try:
            cursor.execute(
                """
                INSERT INTO import_logs (file_name, sheet_name, status, summary)
                VALUES (?, ?, ?, ?)
                """,
                (
                    planning_xlsx.name,
                    sheet_name or "ALL_SHEETS",
                    "failed",
                    str(e)
                )
            )
            conn.commit()
        except Exception:
            pass
        raise e
    finally:
        conn.close()

    return stats


def load_blocks_from_sqlite(flight_id: int, conn: sqlite3.Connection) -> list[ReservationBlock]:
    """SQLite veritabanından belirli bir uçuşun rezervasyon bloklarını yükler."""
    res_rows = conn.execute("SELECT * FROM reservations WHERE flight_id = ? ORDER BY sort_order", (flight_id,)).fetchall()
    blocks = []
    for r in res_rows:
        res_id = r["id"]
        # Fetch passengers linked to this reservation
        pass_rows = conn.execute(
            """
            SELECT rp.seq, p.passport_no, p.nationality, p.sex, p.full_name
            FROM reservation_passengers rp
            JOIN passengers p ON rp.passenger_id = p.id
            WHERE rp.reservation_id = ?
            ORDER BY rp.seq
            """,
            (res_id,)
        ).fetchall()
        
        passengers = []
        pax_count = r["pax"]
        start_row = r["sort_order"]
        rows_indices = list(range(start_row, start_row + pax_count))
        
        for idx, p in enumerate(pass_rows):
            p_row_num = start_row + idx
            passengers.append(PassengerIdentity(
                row=p_row_num,
                nationality=p["nationality"] or "",
                sex=p["sex"] or "",
                name=p["full_name"] or "",
                passport_no=p["passport_no"] or ""
            ))
            
        # If there are fewer passenger rows in DB than pax, pad it
        while len(passengers) < pax_count:
            p_row_num = start_row + len(passengers)
            passengers.append(PassengerIdentity(
                row=p_row_num,
                nationality="",
                sex="",
                name="",
                passport_no=""
            ))
            
        lead_name = passengers[0].name if passengers else ""
            
        blocks.append(ReservationBlock(
            lead_row=start_row,
            rows=rows_indices,
            pax=pax_count,
            room=r["room_no"] or "",
            agency=r["agency"] or "",
            reserved_by=r["reserved_by"] or "",
            company=r["flight_firm"] or "",
            balloon=r["balloon_code"] or "",
            pilot=r["pilot"] or "",
            note=r["notes"] or "",
            driver=r["driver_no"] or "",
            coming_place=r["destination"] or "",
            hotel=r["hotel"] or "",
            pickup=r["pickup_time"] or "",
            lead_name=lead_name,
            passengers=passengers
        ))
    return blocks

