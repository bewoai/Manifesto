from app.manifest.planning import PlanningRow, group_blocks


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
