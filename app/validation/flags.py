"""Validation kapıları (brief §7).

Yeşil = MRZ + tüm check digit'ler doğru ve flag yok.
Sarı  = en az bir flag var; operatör gözden geçirir (brief §8).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.mrz.parser import MRZResult


class Flag(str, Enum):
    CHECKSUM_FAIL = "checksum_fail"
    EXPIRED = "expired"
    DUPLICATE = "duplicate"
    PAX_MISMATCH = "pax_mismatch"
    UNREADABLE = "unreadable"
    MRZ_INCONSISTENT = "mrz_inconsistent"  # uyruk ≠ issuing → satır/isim şüpheli
    FREE_TEXT_UNVERIFIED = "free_text_unverified"  # MRZ yok, serbest metinden çıkarıldı


@dataclass
class ValidationOutcome:
    flags: list[Flag] = field(default_factory=list)

    @property
    def is_green(self) -> bool:
        return not self.flags

    def add(self, flag: Flag) -> None:
        if flag not in self.flags:
            self.flags.append(flag)


def validate_mrz(
    result: Optional[MRZResult],
    *,
    seen_document_numbers: Optional[set[str]] = None,
    today: Optional[_dt.date] = None,
) -> ValidationOutcome:
    """Tek bir MRZ sonucunu kapılardan geçirir.

    seen_document_numbers: önceden onaylanmış belge no kümesi (duplicate tespiti).
    """
    outcome = ValidationOutcome()
    today = today or _dt.date.today()

    if result is None:
        outcome.add(Flag.UNREADABLE)
        return outcome

    if not result.checks_ok:
        outcome.add(Flag.CHECKSUM_FAIL)

    if result.expiry_date is not None and result.expiry_date < today:
        outcome.add(Flag.EXPIRED)

    if seen_document_numbers is not None and result.document_number:
        if result.document_number in seen_document_numbers:
            outcome.add(Flag.DUPLICATE)

    # Pasaportta issuing country ≈ uyruk her zaman aynıdır. Farklıysa satır 1 hizası
    # bozulmuş olabilir (isim alanı checksum'sız olduğundan hatalı isim yeşile kaçabilir);
    # operatör gözden geçirsin (sarı).
    if (result.issuing_country and result.nationality
            and len(result.issuing_country) == 3 and len(result.nationality) == 3
            and result.issuing_country != result.nationality):
        outcome.add(Flag.MRZ_INCONSISTENT)

    return outcome


def check_pax(expected_pax: Optional[int], received: int) -> Optional[Flag]:
    """Rezervasyonun beklenen PAX'ı ile gelen pasaport sayısını karşılaştırır (brief §5)."""
    if expected_pax is not None and expected_pax != received:
        return Flag.PAX_MISMATCH
    return None
