"""MRZ parser — TD3 (pasaport, 2x44) ve TD1 (kimlik, 3x30).

Çıktı: 4 kimlik alanı (nationality alpha-3, sex M/F, name UPPERCASE, document_no)
+ her check digit'in deterministik doğrulaması. Vision LLM yalnızca MRZ
satırlarını (ham metin) verir; doğrulama burada, kodda yapılır.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Optional

from .checksum import check_digit, verify


@dataclass
class MRZResult:
    format: str  # "TD3" | "TD1"
    document_type: str
    issuing_country: str
    nationality: str  # alpha-3
    document_number: str
    sex: str  # "M" | "F" | "X"
    surname: str
    given_names: str
    birth_date: Optional[_dt.date]
    expiry_date: Optional[_dt.date]
    # check digit sonuçları
    checks: dict = field(default_factory=dict)
    raw_lines: list = field(default_factory=list)

    @property
    def name(self) -> str:
        """Manifesto/planlama için tek satır AD SOYAD (UPPERCASE)."""
        return " ".join(p for p in (self.given_names, self.surname) if p).strip().upper()

    @property
    def full_name_surname_first(self) -> str:
        return " ".join(p for p in (self.surname, self.given_names) if p).strip().upper()

    @property
    def checks_ok(self) -> bool:
        return all(self.checks.values())


def _clean(line: str) -> str:
    return line.strip().replace(" ", "").upper()


def _parse_name(field_text: str) -> tuple[str, str]:
    """MRZ isim alanını (SURNAME<<GIVEN<NAMES) ad-soyada böler."""
    field_text = field_text.rstrip("<")
    if "<<" in field_text:
        surname_part, _, given_part = field_text.partition("<<")
    else:
        surname_part, given_part = field_text, ""
    surname = " ".join(t for t in surname_part.split("<") if t)
    given = " ".join(t for t in given_part.split("<") if t)
    return surname.strip(), given.strip()


def _parse_date(yymmdd: str, *, expiry: bool, today: Optional[_dt.date] = None) -> Optional[_dt.date]:
    """YYMMDD -> date. Yüzyıl penceresi: doğum geçmiş, son geçerlilik gelecek varsayılır."""
    if not yymmdd.isdigit() or len(yymmdd) != 6:
        return None
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    today = today or _dt.date.today()
    if expiry:
        year = 2000 + yy  # pasaport son geçerlilikleri 2000'li yıllar
    else:
        year = 2000 + yy
        if year > today.year:
            year -= 100  # gelecekteki doğum tarihi olamaz -> 19xx
    try:
        return _dt.date(year, mm, dd)
    except ValueError:
        return None


def parse_td3(line1: str, line2: str, *, today: Optional[_dt.date] = None) -> MRZResult:
    """TD3 (pasaport): iki satır, her biri 44 karakter."""
    l1, l2 = _clean(line1).ljust(44, "<")[:44], _clean(line2).ljust(44, "<")[:44]

    document_type = l1[0:2].replace("<", "")
    issuing_country = l1[2:5].replace("<", "")
    surname, given = _parse_name(l1[5:44])

    document_number = l2[0:9].replace("<", "")
    doc_cd = l2[9]
    nationality = l2[10:13].replace("<", "")
    birth_raw = l2[13:19]
    birth_cd = l2[19]
    sex = l2[20] if l2[20] in ("M", "F") else "X"
    expiry_raw = l2[21:27]
    expiry_cd = l2[27]
    personal = l2[28:42]
    personal_cd = l2[42]
    composite_cd = l2[43]

    composite_input = l2[0:10] + l2[13:20] + l2[21:43]
    checks = {
        "document_number": verify(l2[0:9], doc_cd),
        "birth_date": verify(birth_raw, birth_cd),
        "expiry_date": verify(expiry_raw, expiry_cd),
        "personal_number": verify(personal, personal_cd),
        "composite": check_digit(composite_input) == int(composite_cd) if composite_cd.isdigit() else False,
    }
    return MRZResult(
        format="TD3",
        document_type=document_type,
        issuing_country=issuing_country,
        nationality=nationality,
        document_number=document_number,
        sex=sex,
        surname=surname,
        given_names=given,
        birth_date=_parse_date(birth_raw, expiry=False, today=today),
        expiry_date=_parse_date(expiry_raw, expiry=True, today=today),
        checks=checks,
        raw_lines=[l1, l2],
    )


def parse_td1(line1: str, line2: str, line3: str, *, today: Optional[_dt.date] = None) -> MRZResult:
    """TD1 (kimlik kartı): üç satır, her biri 30 karakter."""
    l1 = _clean(line1).ljust(30, "<")[:30]
    l2 = _clean(line2).ljust(30, "<")[:30]
    l3 = _clean(line3).ljust(30, "<")[:30]

    document_type = l1[0:2].replace("<", "")
    issuing_country = l1[2:5].replace("<", "")
    document_number = l1[5:14].replace("<", "")
    doc_cd = l1[14]
    optional1 = l1[15:30]

    birth_raw = l2[0:6]
    birth_cd = l2[6]
    sex = l2[7] if l2[7] in ("M", "F") else "X"
    expiry_raw = l2[8:14]
    expiry_cd = l2[14]
    nationality = l2[15:18].replace("<", "")
    optional2 = l2[18:29]
    composite_cd = l2[29]

    surname, given = _parse_name(l3)

    composite_input = l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29]
    checks = {
        "document_number": verify(l1[5:14], doc_cd),
        "birth_date": verify(birth_raw, birth_cd),
        "expiry_date": verify(expiry_raw, expiry_cd),
        "composite": check_digit(composite_input) == int(composite_cd) if composite_cd.isdigit() else False,
    }
    return MRZResult(
        format="TD1",
        document_type=document_type,
        issuing_country=issuing_country,
        nationality=nationality,
        document_number=document_number,
        sex=sex,
        surname=surname,
        given_names=given,
        birth_date=_parse_date(birth_raw, expiry=False, today=today),
        expiry_date=_parse_date(expiry_raw, expiry=True, today=today),
        checks=checks,
        raw_lines=[l1, l2, l3],
    )


def parse(lines: list[str], *, today: Optional[_dt.date] = None) -> MRZResult:
    """Satır sayısına göre TD3/TD1 seçer. 2 satır -> TD3, 3 satır -> TD1."""
    cleaned = [ln for ln in (l.rstrip("\n") for l in lines) if ln.strip()]
    if len(cleaned) == 2:
        return parse_td3(cleaned[0], cleaned[1], today=today)
    if len(cleaned) == 3:
        return parse_td1(cleaned[0], cleaned[1], cleaned[2], today=today)
    raise ValueError(f"MRZ 2 (TD3) veya 3 (TD1) satır olmalı, {len(cleaned)} geldi")
