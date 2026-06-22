"""ICAO 9303 MRZ check-digit hesabı (deterministik).

MRZ karakter değerleri: 0-9 -> kendi değeri, A-Z -> 10..35, '<' (filler) -> 0.
Ağırlıklar 7,3,1 döngüsel; toplamın mod 10'u check digit'tir.
"""
from __future__ import annotations


def char_value(c: str) -> int:
    """Tek MRZ karakterinin sayısal değeri."""
    if c == "<":
        return 0
    if "0" <= c <= "9":
        return ord(c) - ord("0")
    if "A" <= c <= "Z":
        return ord(c) - ord("A") + 10
    raise ValueError(f"Geçersiz MRZ karakteri: {c!r}")


def check_digit(s: str) -> int:
    """Verilen alan için ICAO 9303 check digit'ini (0-9) döndürür."""
    weights = (7, 3, 1)
    total = 0
    for i, c in enumerate(s):
        total += char_value(c) * weights[i % 3]
    return total % 10


def verify(field: str, expected: str) -> bool:
    """`field`'in check digit'i `expected` ile uyuşuyor mu?

    `expected` '<' veya boş ise (opsiyonel alan, check yok) True kabul edilir.
    """
    if expected in ("", "<"):
        return True
    if not expected.isdigit():
        return False
    return check_digit(field) == int(expected)
