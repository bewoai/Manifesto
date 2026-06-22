"""Balon otomatik atama (first-fit) testleri — PII gerektirmez."""
from app import config
from app.manifest.planning import ReservationBlock, assign_balloon, balloon_load


CODES = ["BYF", "BTK", "BYJ", "BZR", "BZV"]
CAP = config.DEFAULT_BALLOON_CAPACITY  # 28


def test_first_fit_picks_first_balloon_with_room():
    code, overflow = assign_balloon({}, 5, CODES, CAP)
    assert code == "BYF"
    assert overflow is False


def test_skips_full_balloon_keeps_group_whole():
    # BYF'de 26 dolu → 5 kişilik grup sığmaz (26+5>28), BTK'ya gitmeli (bölünmez)
    load = {"BYF": 26}
    code, overflow = assign_balloon(load, 5, CODES, CAP)
    assert code == "BTK"
    assert overflow is False


def test_exact_fit_allowed():
    load = {"BYF": 23}
    code, overflow = assign_balloon(load, 5, CODES, CAP)  # 23+5 == 28
    assert code == "BYF"
    assert overflow is False


def test_overflow_when_no_balloon_fits_whole_group():
    # Hepsi neredeyse dolu; 5 kişilik grup hiçbirine tam sığmıyor → en boş + overflow
    load = {"BYF": 27, "BTK": 26, "BYJ": 25, "BZR": 28, "BZV": 26}
    code, overflow = assign_balloon(load, 5, CODES, CAP)
    assert overflow is True
    assert code == "BYJ"  # en az dolu (25)


def test_full_pax_28_needs_empty_balloon():
    load = {"BYF": 1}
    code, overflow = assign_balloon(load, 28, CODES, CAP)
    assert code == "BTK"  # BYF'de 28 sığmaz, ilk tam boş balon
    assert overflow is False


def test_no_codes_returns_overflow():
    code, overflow = assign_balloon({}, 3, [], CAP)
    assert code == ""
    assert overflow is True


def test_custom_capacity():
    load = {"BYF": 20}
    code, overflow = assign_balloon(load, 6, CODES, 24)  # 20+6>24 → BTK
    assert code == "BTK"


def _block(balloon: str, pax: int, lead_row: int) -> ReservationBlock:
    return ReservationBlock(
        lead_row=lead_row, rows=list(range(lead_row, lead_row + pax)), pax=pax,
        room="", agency="", reserved_by="", company="", balloon=balloon, pilot="",
        note="", driver="", coming_place="", hotel="", pickup="", lead_name="",
    )


def test_balloon_load_sums_pax_per_balloon():
    blocks = [_block("BYF", 18, 4), _block("BYF", 4, 22), _block("BTK", 6, 26)]
    load = balloon_load(blocks)
    assert load == {"BYF": 22, "BTK": 6}
