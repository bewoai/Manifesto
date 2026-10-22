"""Liste işaret kuralları: acentenin listede "uçuyor" demek için kullandığı işaret dili.

Sahadan görülen beş konvansiyon: ✓ tik, fosforlu satır, kırmızı "B" harfi, el yazısı sıra
numarası, "SI" / evet. Model işareti yorumlamaz, satır başına ham `annotation` döner;
operatör listede hangi kuralın geçerli olduğunu seçer, kural acenteye kaydedilir.
"""
from __future__ import annotations

import re
import unicodedata

MARK_RULES: dict[str, str] = {
    "all": "Hepsi uçuyor",
    "any_mark": "İşaretli satırlar (ne olursa olsun)",
    "check": "Tik (✓) olanlar",
    "highlight": "Fosforlu satırlar",
    "number": "Yanında sıra numarası olanlar",
    "yes": "SI / EVET / YES yazanlar",
    "letter_b": "B harfi olanlar",
}

_CHECK_TOKENS = ("✓", "✔", "√", "☑", "tick", "check")
_HIGHLIGHT_TOKENS = ("highlight", "fosfor", "marker", "yellow", "green")
_YES_TOKENS = {"si", "sí", "yes", "evet", "ok", "y", "x"}
_STRIKE_TOKENS = ("strike", "ustu cizili", "crossed")


def _fold(text: str) -> str:
    """Küçük harfe indir, aksanları düşür (SÍ → si), boşlukları kırp."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.strip().lower()


def normalize_agency_key(agency: str) -> str:
    return _fold(agency)


def annotation_matches(rule: str, annotation: str) -> bool:
    """Satırın işareti verilen kurala göre 'uçuyor' anlamına geliyor mu?"""
    a = _fold(annotation)
    if rule == "all":
        return True
    if not a or any(tok in a for tok in _STRIKE_TOKENS):
        return False
    if rule == "any_mark":
        return True
    if rule == "check":
        return any(tok in a for tok in _CHECK_TOKENS)
    if rule == "highlight":
        return any(tok in a for tok in _HIGHLIGHT_TOKENS)
    if rule == "number":
        return re.fullmatch(r"\d{1,3}", a) is not None
    if rule == "yes":
        return a in _YES_TOKENS
    if rule == "letter_b":
        return a in {"b", "balon", "balloon"}
    return False


def normalize_rules(rules) -> dict[str, str]:
    """Settings'ten gelen {acente: kural} sözlüğünü temizler; geçersiz kural atılır."""
    if not isinstance(rules, dict):
        return {}
    out: dict[str, str] = {}
    for agency, rule in rules.items():
        key = normalize_agency_key(agency)
        if key and rule in MARK_RULES:
            out[key] = rule
    return out
