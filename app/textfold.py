"""Ad eşleştirme anahtarı: Türkçe harf, büyük/küçük harf ve fazla boşluk duyarsız.

Acente (kota) ve otel (balon gruplama) adları aynı kuralla karşılaştırılır:
"Bedel Turizm", "BEDEL TURİZM" ve "bedel  turizm" → "BEDEL TURIZM".
"""
from __future__ import annotations

_TR_FOLD = str.maketrans({"Ş": "S", "Ğ": "G", "Ü": "U", "Ö": "O", "Ç": "C", "Â": "A", "Î": "I", "Û": "U"})


def fold_name(name) -> str:
    """İ/ı→I, Ş→S, Ğ→G, Ü→U, Ö→O, Ç→C, büyük harf, tek boşluk."""
    text = str(name or "").replace("İ", "I").replace("ı", "I").upper().translate(_TR_FOLD)
    return " ".join(text.split())
