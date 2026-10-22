import openpyxl

from app import config
from app.manifest.planning import PlanningRow, delete_passenger_from_reservation, group_blocks, read_blocks


def _row(row: int, pax: int | None, name: str, passport_no: str) -> PlanningRow:
    return PlanningRow(
        row=row,
        pax=pax,
        nationality="CHN",
        sex="F",
        name=name,
        room="",
        hotel="ARGOS",
        pickup="04:10",
        reserved_by="MAHMUT",
        agency="RANK UNITED",
        company="",
        balloon="BYF",
        pilot="",
        note="",
        driver="",
        coming_place="",
        passport_no=passport_no,
    )


def test_group_blocks_keeps_all_passenger_identities():
    blocks = group_blocks([
        _row(4, 2, "FIRST WOMAN", "P1"),
        _row(5, None, "SECOND WOMAN", "P2"),
    ])

    assert len(blocks) == 1
    assert blocks[0].rows == [4, 5]
    assert [p.name for p in blocks[0].passengers] == ["FIRST WOMAN", "SECOND WOMAN"]
    assert [p.passport_no for p in blocks[0].passengers] == ["P1", "P2"]


def _workbook(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "23.06.2026"
    ws.cell(4, config.COL_PAX).value = 2
    ws.cell(4, config.COL_NAME).value = "FIRST WOMAN"
    ws.cell(4, config.COL_PASSPORT_NO).value = "P1"
    ws.cell(4, config.COL_HOTEL).value = "ARGOS"
    ws.cell(4, config.COL_PICKUP).value = "04:10"
    ws.cell(4, config.COL_AGENCY).value = "ACME"
    ws.cell(4, config.COL_BALLOON).value = "BYF"
    ws.cell(5, config.COL_NAME).value = "SECOND WOMAN"
    ws.cell(5, config.COL_PASSPORT_NO).value = "P2"
    ws.cell(5, config.COL_BALLOON).value = "BYF"
    ws.merge_cells(start_row=4, start_column=config.COL_PAX, end_row=5, end_column=config.COL_PAX)
    ws.merge_cells(start_row=4, start_column=config.COL_HOTEL, end_row=5, end_column=config.COL_HOTEL)
    wb.save(path)
    wb.close()


def test_delete_non_lead_passenger_decrements_pax(tmp_path):
    path = tmp_path / "planning.xlsx"
    _workbook(path)

    delete_passenger_from_reservation(path, "23.06.2026", lead_row=4, rows=[4, 5], target_row=5)
    block = read_blocks(path, "23.06.2026")[0]

    assert block.pax == 1
    assert [p.name for p in block.passengers] == ["FIRST WOMAN"]


def test_delete_lead_passenger_moves_next_identity_to_lead(tmp_path):
    path = tmp_path / "planning.xlsx"
    _workbook(path)

    delete_passenger_from_reservation(path, "23.06.2026", lead_row=4, rows=[4, 5], target_row=4)
    block = read_blocks(path, "23.06.2026")[0]

    assert block.pax == 1
    assert block.hotel == "ARGOS"
    assert block.agency == "ACME"
    assert [p.name for p in block.passengers] == ["SECOND WOMAN"]
    assert [p.passport_no for p in block.passengers] == ["P2"]


# ─── create_reservation: hedef satırlar boş olmalı / reorder: birleşmeler kayar ───

from app.manifest.excel_cache import clear_excel_cache
from app.manifest.planning import create_reservation, reorder_reservation


def _put_block(ws, lead: int, names: list[str], *, hotel: str, balloon: str = "BYF"):
    """lead satırdan itibaren len(names) satırlık blok; PAX ve OTEL dikey birleşik."""
    last = lead + len(names) - 1
    ws.cell(lead, config.COL_PAX).value = len(names)
    ws.cell(lead, config.COL_HOTEL).value = hotel
    ws.cell(lead, config.COL_AGENCY).value = "ACME"
    for i, name in enumerate(names):
        ws.cell(lead + i, config.COL_NAME).value = name
        ws.cell(lead + i, config.COL_PASSPORT_NO).value = f"P-{name}"
        ws.cell(lead + i, config.COL_BALLOON).value = balloon
    if last > lead:
        for col in (config.COL_PAX, config.COL_HOTEL):
            ws.merge_cells(start_row=lead, start_column=col, end_row=last, end_column=col)


def _three_block_workbook(path):
    """A: 4-5, (6 boş), B: 7-9, C: 10-11"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "23.06.2026"
    _put_block(ws, 4, ["A1", "A2"], hotel="ARGOS")
    _put_block(ws, 7, ["B1", "B2", "B3"], hotel="MUSEUM")
    _put_block(ws, 10, ["C1", "C2"], hotel="KELEBEK")
    wb.save(path)
    wb.close()


def _blocks(path):
    clear_excel_cache()
    return read_blocks(path, "23.06.2026")


def _merged(path):
    wb = openpyxl.load_workbook(path)
    ranges = {(r.min_col, r.min_row, r.max_row) for r in wb["23.06.2026"].merged_cells.ranges}
    wb.close()
    return ranges


def test_create_reservation_does_not_overwrite_next_block(tmp_path):
    path = tmp_path / "planning.xlsx"
    _three_block_workbook(path)

    # 1 satırlık boşluk (6) var ama blok 3 kişilik → B'nin üzerine yazılmamalı
    result = create_reservation(path, "23.06.2026", pax=3, balloon="BZR", fields={"hotel": "NEW"})
    assert result["lead_row"] == 12, result
    names = [[p.name for p in b.passengers] for b in _blocks(path)]
    assert names[:3] == [["A1", "A2"], ["B1", "B2", "B3"], ["C1", "C2"]]
    assert _blocks(path)[1].hotel == "MUSEUM"


def test_create_reservation_reuses_gap_that_fits(tmp_path):
    path = tmp_path / "planning.xlsx"
    _three_block_workbook(path)

    result = create_reservation(path, "23.06.2026", pax=1, balloon="BZR")
    assert result["lead_row"] == 6
    assert [b.lead_row for b in _blocks(path)] == [4, 6, 7, 10]


def test_reorder_shifts_other_blocks_merged_ranges(tmp_path):
    path = tmp_path / "planning.xlsx"
    _three_block_workbook(path)

    # C'yi (10-11) A'nın başına (4) taşı → C 4-5, A 6-7, (8 boş), B 9-11
    reorder_reservation(path, "23.06.2026", source_rows=[10, 11], target_row=4)

    blocks = _blocks(path)
    assert [[p.name for p in b.passengers] for b in blocks] == [["C1", "C2"], ["A1", "A2"], ["B1", "B2", "B3"]]
    assert [b.lead_row for b in blocks] == [4, 6, 9]
    assert [b.hotel for b in blocks] == ["KELEBEK", "ARGOS", "MUSEUM"]
    assert [b.pax for b in blocks] == [2, 2, 3]

    merged = _merged(path)
    # Her bloğun PAX ve OTEL birleşmesi tam blok satırlarını kapsamalı
    for lead, last in ((4, 5), (6, 7), (9, 11)):
        assert (config.COL_PAX, lead, last) in merged, (lead, last, merged)
        assert (config.COL_HOTEL, lead, last) in merged, (lead, last, merged)
    # Hiçbir birleşme blok sınırını aşmamalı
    bounds = {(4, 5), (6, 7), (9, 11)}
    for _, lo, hi in merged:
        assert any(lo >= a and hi <= b for a, b in bounds), (lo, hi)


def test_reorder_moving_down_keeps_merges_aligned(tmp_path):
    path = tmp_path / "planning.xlsx"
    _three_block_workbook(path)

    # A'yı (4-5) C'nin altına (12) taşı → (4,5 boş), B 7-9? hayır: silme sonrası B 5-7, C 8-9, A 10-11
    reorder_reservation(path, "23.06.2026", source_rows=[4, 5], target_row=12)
    blocks = _blocks(path)
    assert [[p.name for p in b.passengers] for b in blocks] == [["B1", "B2", "B3"], ["C1", "C2"], ["A1", "A2"]]
    merged = _merged(path)
    for b in blocks:
        assert (config.COL_PAX, b.lead_row, b.rows[-1]) in merged, (b.lead_row, b.rows, merged)


def test_reorder_rejects_target_inside_a_block(tmp_path):
    path = tmp_path / "planning.xlsx"
    _three_block_workbook(path)
    import pytest
    with pytest.raises(ValueError):
        reorder_reservation(path, "23.06.2026", source_rows=[10, 11], target_row=8)
