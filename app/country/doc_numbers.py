"""Belge numarası biçiminden uyruk tespiti (uyruk yazmayan listeler için).

İki güven seviyesi:

KESİN — numarada ülkeye özgü kontrol hanesi kodda doğrulanır:
  - ESP DNI (kimlik):   8 hane + harf; harf = "TRWAGMYFPDXBNJZSQVHLCKE"[sayı % 23]
  - POL kimlik kartı:   3 harf + 6 hane; 4. karakter kontrol hanesi
                        (ağırlık 7,3,1,·,7,3,1,7,3; A=10 … Z=35; toplam mod 10)
  - TUR T.C. kimlik no: 11 hane, 10. ve 11. hane kontrol haneleri

OLASI — yalnız biçim; bazı biçimler birden çok ülkeye uyar, o zaman aday listesi döner
ve karar aynı listedeki diğer satırların çoğunluğuyla verilir (`infer_nationalities`).
Biçimler saha örneklerinden ve genel bilgiden derlendi; tam bir ülke kataloğu değildir.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional

_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_POL_WEIGHTS = (7, 3, 1, 9, 7, 3, 1, 7, 3)


@dataclass(frozen=True)
class NatGuess:
    candidates: tuple[str, ...]   # alpha-3, öncelik sırasıyla
    certain: bool                 # kontrol hanesiyle doğrulandı mı
    reason: str                   # operatöre gösterilecek kısa gerekçe


def _clean(doc_no: str) -> str:
    return "".join(ch for ch in str(doc_no or "").upper() if ch.isalnum())


def valid_es_dni(n: str) -> bool:
    return bool(re.fullmatch(r"\d{8}[A-Z]", n)) and _DNI_LETTERS[int(n[:8]) % 23] == n[8]


def valid_pl_id_card(n: str) -> bool:
    if not re.fullmatch(r"[A-Z]{3}\d{6}", n):
        return False
    values = [ord(c) - 55 for c in n[:3]] + [int(c) for c in n[3:]]
    return sum(v * w for v, w in zip(values, _POL_WEIGHTS)) % 10 == 0


def valid_tr_tckn(n: str) -> bool:
    if not re.fullmatch(r"[1-9]\d{10}", n):
        return False
    d = [int(c) for c in n]
    if ((sum(d[0:9:2]) * 7) - sum(d[1:8:2])) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


# (regex, adaylar, gerekçe) — sıra önemli değil; tüm eşleşenlerin adayları birleşir
_PATTERNS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (r"(PA|XD)[A-Z]\d{6}", ("ESP",), "İspanya pasaport biçimi"),
    (r"C[A-Z]\d{5}[A-Z]{2}", ("ITA",), "İtalya kimlik kartı (CIE) biçimi"),
    (r"Y[A-Z]\d{7}", ("ITA",), "İtalya pasaport biçimi"),
    (r"M\d{3}[A-Z]\d{4}", ("KOR",), "Kore pasaport biçimi"),
    (r"M\d{8}", ("KOR",), "Kore pasaport biçimi (eski)"),
    (r"[A-Z]\d{2}[A-Z]\d{5}", ("TUR",), "T.C. kimlik kartı seri no biçimi"),
    (r"[A-Z]{2}\d{7}", ("POL", "AUS"), "2 harf + 7 hane (Polonya/Avustralya…)"),
    (r"\d{9}", ("GBR", "USA"), "9 hane (Birleşik Krallık/ABD…)"),
    (r"[A-Z]\d{8}", ("USA", "CHN"), "harf + 8 hane (ABD/Çin…)"),
)


def guess_from_document(doc_no: str, doc_type: str = "") -> Optional[NatGuess]:
    """Belge numarasından uyruk adayları. Hiçbir biçime uymuyorsa None."""
    n = _clean(doc_no)
    if not n:
        return None

    certain: list[tuple[str, str]] = []
    if valid_es_dni(n):
        certain.append(("ESP", "İspanya DNI kontrol harfi doğru"))
    if valid_pl_id_card(n):
        certain.append(("POL", "Polonya kimlik kartı kontrol hanesi doğru"))
    if valid_tr_tckn(n):
        certain.append(("TUR", "T.C. kimlik no kontrol haneleri doğru"))

    likely: list[str] = []
    reasons: list[str] = []
    for pattern, cands, reason in _PATTERNS:
        if re.fullmatch(pattern, n):
            for c in cands:
                if c not in likely:
                    likely.append(c)
            reasons.append(reason)

    if len(certain) == 1:
        nat, reason = certain[0]
        # Kontrol hanesi tuttu ama başka bir ülkenin kalıbına da uyuyorsa (ör. ESP pasaport
        # 3 harf + 6 hane ↔ POL kimlik): kesin sayma, aday olarak bırak.
        others = [c for c in likely if c != nat]
        if not others:
            return NatGuess((nat,), True, reason)
        return NatGuess(tuple([nat] + others), False, f"{reason}; ayrıca {', '.join(reasons)}")
    if len(certain) > 1:
        return NatGuess(tuple(c for c, _ in certain), False, "birden çok ülkenin kontrol hanesi tutuyor")
    if likely:
        return NatGuess(tuple(likely), False, "; ".join(reasons))
    return None


# Kaynak etiketleri (PassportRecord.nationality_source)
SOURCE_MRZ = "mrz"            # MRZ'den, checksum'lı
SOURCE_STATED = "stated"      # satırda yazıyor
SOURCE_HEADER = "header"      # liste başlığında yazıyor ("İtalyan", "POL" …)
SOURCE_DOCUMENT = "document"  # belge no kontrol hanesi (kesin)
SOURCE_PATTERN = "pattern"    # belge no biçimi (tek aday)
SOURCE_LIST = "list"          # listedeki diğer satırların çoğunluğu
SOURCE_MODEL = "model"        # modelin grup tahmini (isimler, dil, başlık)

INFERRED_SOURCES = (SOURCE_PATTERN, SOURCE_LIST, SOURCE_MODEL)   # operatörün bakması gerekenler
DERIVED_SOURCES = (SOURCE_DOCUMENT,) + INFERRED_SOURCES


def infer_nationalities(rows: Iterable, *, model_guess: str = "") -> None:
    """Aynı görselin satırlarında boş uyrukları doldurur (yerinde değiştirir).

    `rows` öğeleri: `.mrz` (nationality, issuing_country, document_number), `.document_type`,
    `.nationality_source`, `.nationality_reason` niteliklerine sahip nesneler.

    Öncelik: MRZ / satırda yazan > belge no kontrol hanesi (başlık ipucunu da geçer) >
    başlık ipucu > tek adaylı biçim > listedeki çoğunluk (adaylarla kesişen) >
    güçlü çoğunluk (≥3 satır, %80) > modelin grup tahmini.
    """
    rows = [r for r in rows if getattr(r, "mrz", None) is not None]

    def _set(r, nat: str, source: str, reason: str) -> None:
        r.mrz.nationality = nat
        r.mrz.issuing_country = nat
        r.nationality_source = source
        r.nationality_reason = reason

    guesses = {id(r): guess_from_document(r.mrz.document_number, getattr(r, "document_type", "")) for r in rows}

    # 1) Kesin kontrol hanesi: boş ya da yalnız başlıktan gelen uyruğu belirler
    for r in rows:
        g = guesses[id(r)]
        if g and g.certain and r.nationality_source in ("", SOURCE_HEADER):
            if r.mrz.nationality != g.candidates[0] or r.nationality_source == "":
                _set(r, g.candidates[0], SOURCE_DOCUMENT, g.reason)

    trusted = (SOURCE_MRZ, SOURCE_STATED, SOURCE_HEADER, SOURCE_DOCUMENT)
    counts = Counter(r.mrz.nationality for r in rows if r.mrz.nationality and r.nationality_source in trusted)

    # 2) Biçim: tek aday → doldur; çok aday → listedeki çoğunlukla kesişeni seç
    for r in rows:
        if r.mrz.nationality:
            continue
        g = guesses[id(r)]
        if not g:
            continue
        if len(g.candidates) == 1:
            _set(r, g.candidates[0], SOURCE_PATTERN, g.reason)
            continue
        ranked = [c for c in sorted(g.candidates, key=lambda c: -counts.get(c, 0)) if counts.get(c, 0) > 0]
        if ranked:
            _set(r, ranked[0], SOURCE_LIST,
                 f"{g.reason}; listedeki {counts[ranked[0]]} satır {ranked[0]}")

    # 3) Güçlü çoğunluk: biçimi tanınmayan satırlar
    counts = Counter(r.mrz.nationality for r in rows if r.mrz.nationality)
    known = sum(counts.values())
    if counts and known >= 3:
        top, top_n = counts.most_common(1)[0]
        if top_n / known >= 0.8:
            for r in rows:
                if not r.mrz.nationality:
                    _set(r, top, SOURCE_LIST, f"listedeki {top_n}/{known} satır {top}")

    # 4) Modelin grup tahmini (isimler, dil, başlık) — en düşük öncelik
    guess = str(model_guess or "").strip().upper()[:3]
    if len(guess) == 3 and guess.isalpha():
        for r in rows:
            if not r.mrz.nationality:
                _set(r, guess, SOURCE_MODEL, "modelin grup tahmini (isimler/dil/başlık)")
