"""Otel kartları: aynı otelin farklı yazımları tek kartta, bölge ve buluşma noktası notu.

Planlama Excel'i değişmez; operatör sayfaya ne yazdıysa o kalır. Kart yalnız uygulama
tarafında yazımları birleştirir ("MARRIOT", "Marriott Cappadocia" → tek otel), otel
gruplaması ve şoför listelerinde kullanılır.

Kayıt: ayarlarla aynı klasörde `hotels.json` (cihaza özel, repoya girmez).
Bir yazım yalnız bir karta ait olabilir. Eşleştirme açıkça bağlanmış adlarla yapılır
(`fold_name`); benzerlik yalnız öneri içindir, kendiliğinden birleştirmez.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Optional

from app import settings as settings_mod
from app.textfold import fold_name

REGIONS = ("Göreme", "Uçhisar", "Ürgüp", "Avanos", "Çavuşin", "Ortahisar", "Mustafapaşa", "Nevşehir", "Diğer")

# Öneri anahtarında atılan genel sözcükler ("ARGOS IN CAPPADOCIA" ~ "ARGOS")
_STOP_WORDS = {
    "HOTEL", "HOTELS", "OTEL", "OTELI", "CAVE", "CAVES", "SUITE", "SUITES", "BOUTIQUE", "BUTIK",
    "CAPPADOCIA", "CAPADOCIA", "CAPPADOCCIA", "KAPADOKYA", "IN", "THE", "AND", "RESORT", "SPA",
    # yer adları otel adında sık geçer, otelleri birbirine benzetmesin ("GOREME INN" ≠ "GOREME PALACE")
    "GOREME", "UCHISAR", "URGUP", "AVANOS", "CAVUSIN", "ORTAHISAR", "NEVSEHIR", "MUSTAFAPASA",
}
_SIMILAR = 0.86


def catalog_path() -> Path:
    override = os.getenv("IRTIFA_HOTELS_PATH")
    return Path(override) if override else settings_mod.SETTINGS_PATH.with_name("hotels.json")


@dataclass
class HotelCard:
    id: str
    name: str
    aliases: list[str] = field(default_factory=list)   # sayfada görülen diğer yazımlar
    region: str = ""
    meeting_point: str = ""                             # ör. "Araç girmiyor, meydanda bekle"
    map_url: str = ""

    def names(self) -> list[str]:
        return [self.name, *self.aliases]


def load_catalog(path: Optional[Path] = None) -> list[HotelCard]:
    p = path or catalog_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    cards = []
    for raw in data.get("hotels", []) if isinstance(data, dict) else []:
        if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
            continue
        cards.append(HotelCard(
            id=str(raw.get("id") or uuid.uuid4().hex[:8]),
            name=str(raw["name"]).strip(),
            aliases=[str(a).strip() for a in raw.get("aliases", []) if str(a).strip()],
            region=str(raw.get("region", "")).strip(),
            meeting_point=str(raw.get("meeting_point", "")).strip(),
            map_url=str(raw.get("map_url", "")).strip(),
        ))
    return cards


def save_catalog(cards: list[HotelCard], path: Optional[Path] = None) -> Path:
    p = path or catalog_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    cards = sorted(cards, key=lambda c: fold_name(c.name))
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"hotels": [asdict(c) for c in cards]}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, p)
    return p


def match_key(name: str) -> str:
    """Öneri anahtarı: noktalama ve genel sözcükler atılır ("Argos in Cappadocia" → "ARGOS")."""
    words = re.sub(r"[^A-Z0-9 ]+", " ", fold_name(name)).split()
    core = [w for w in words if w not in _STOP_WORDS]
    return " ".join(core or words)


def similar(a: str, b: str) -> bool:
    ka, kb = match_key(a), match_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    short, long_ = sorted((ka, kb), key=len)
    if len(short) >= 5 and long_.startswith(short + " "):   # "ROCCA" ~ "ROCCA STONE"
        return True
    return min(len(ka), len(kb)) >= 4 and SequenceMatcher(None, ka, kb).ratio() >= _SIMILAR


class HotelResolver:
    """Yazım → kart. Yalnız karta açıkça bağlanmış adlar eşleşir."""

    def __init__(self, cards: Iterable[HotelCard]):
        self.cards = list(cards)
        self._by_name: dict[str, HotelCard] = {}
        for card in self.cards:
            for n in card.names():
                self._by_name.setdefault(fold_name(n), card)

    def resolve(self, name: str) -> Optional[HotelCard]:
        return self._by_name.get(fold_name(name))

    def key(self, name: str) -> str:
        """Gruplama anahtarı: kartı varsa kart, yoksa katlanmış ad (eski davranış)."""
        card = self.resolve(name)
        return f"#{card.id}" if card else fold_name(name)

    def display(self, name: str) -> str:
        card = self.resolve(name)
        return card.name if card else str(name or "").strip()


def resolver(path: Optional[Path] = None) -> HotelResolver:
    return HotelResolver(load_catalog(path))


def unmatched_groups(name_counts: dict[str, int], cards: list[HotelCard]) -> list[dict]:
    """Karta bağlı olmayan yazımları benzerliğe göre öbekler (birleştirme önerisi).

    name_counts: sayfadaki yazım → rezervasyon sayısı (aynı katlanmış ad tek yazım sayılır).
    Dönüş: [{"names": [{"name", "count"}], "total", "suggested_name", "card_id"}],
    rezervasyon sayısı çoktan aza. `card_id`: öbeğe benzeyen mevcut kart (varsa).
    """
    res = HotelResolver(cards)
    folded: dict[str, dict] = {}
    for name, count in name_counts.items():
        clean = str(name or "").strip()
        if not clean or res.resolve(clean):
            continue
        f = folded.setdefault(fold_name(clean), {"name": clean, "count": 0})
        f["count"] += int(count or 0)
    items = sorted(folded.values(), key=lambda x: (-x["count"], fold_name(x["name"])))

    # En sık yazım öbeğin öncüsüdür; bir yazım ancak öncüye benziyorsa katılır
    # (zincirleme benzerlik "STONE HOUSE" gibi farklı otelleri tek öbekte toplamasın).
    clusters: list[list[dict]] = []
    for item in items:
        home = next((c for c in clusters if similar(c[0]["name"], item["name"])), None)
        if home is None:
            clusters.append([item])
        else:
            home.append(item)

    out = []
    for members in clusters:
        card = next((c for c in cards for m in members for n in c.names() if similar(m["name"], n)), None)
        out.append({
            "names": members,
            "total": sum(m["count"] for m in members),
            "suggested_name": card.name if card else members[0]["name"],
            "card_id": card.id if card else None,
        })
    out.sort(key=lambda g: (-g["total"], fold_name(g["suggested_name"])))
    return out


def _clean_region(region: str) -> str:
    region = str(region or "").strip()
    for known in REGIONS:
        if fold_name(known) == fold_name(region):
            return known
    return region


def _detach(cards: list[HotelCard], names: Iterable[str], keep: HotelCard) -> None:
    """Bu yazımları `keep` dışındaki kartların alias listesinden çıkarır (bir yazım tek kartta)."""
    keys = {fold_name(n) for n in names}
    for card in cards:
        if card is not keep:
            card.aliases = [a for a in card.aliases if fold_name(a) not in keys]


def upsert_card(data: dict, path: Optional[Path] = None) -> HotelCard:
    """Kart oluşturur ya da günceller. data: id?, name, aliases?, region, meeting_point, map_url."""
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Otel adı gerekli.")
    cards = load_catalog(path)
    card = next((c for c in cards if c.id == data.get("id")), None) if data.get("id") else None
    if card is None:
        owner = HotelResolver(cards).resolve(name)
        if owner and not data.get("id"):
            card = owner
        else:
            card = HotelCard(id=uuid.uuid4().hex[:8], name=name)
            cards.append(card)
    old_name = card.name
    card.name = name
    if "aliases" in data:
        card.aliases = [str(a).strip() for a in data.get("aliases") or [] if str(a).strip()]
    if fold_name(old_name) != fold_name(name) and fold_name(old_name) not in {fold_name(a) for a in card.aliases}:
        card.aliases.append(old_name)   # eski ad sayfada geçiyor olabilir, bağ kopmasın
    card.aliases = _unique([a for a in card.aliases if fold_name(a) != fold_name(name)])
    if "region" in data:
        card.region = _clean_region(data.get("region", ""))
    if "meeting_point" in data:
        card.meeting_point = str(data.get("meeting_point") or "").strip()
    if "map_url" in data:
        url = str(data.get("map_url") or "").strip()
        card.map_url = url if re.match(r"^https?://", url, re.I) else ""   # yalnız web linki
    _detach(cards, card.names(), card)
    save_catalog(cards, path)
    return card


def merge_names(names: list[str], *, card_id: str = "", name: str = "", region: str = "",
                path: Optional[Path] = None) -> HotelCard:
    """Yazımları tek karta bağlar: `card_id` varsa o karta, yoksa `name` adlı yeni karta."""
    names = [str(n).strip() for n in names if str(n).strip()]
    if not names:
        raise ValueError("Birleştirilecek otel adı yok.")
    cards = load_catalog(path)
    card = next((c for c in cards if c.id == card_id), None) if card_id else None
    if card_id and card is None:
        raise KeyError("Otel kartı bulunamadı.")
    if card is None:
        title = str(name or names[0]).strip()
        card = HotelCard(id=uuid.uuid4().hex[:8], name=title)
        cards.append(card)
    if region:
        card.region = _clean_region(region)
    card.aliases = _unique([*card.aliases, *[n for n in names if fold_name(n) != fold_name(card.name)]])
    _detach(cards, card.names(), card)
    save_catalog(cards, path)
    return card


def delete_card(card_id: str, path: Optional[Path] = None) -> bool:
    cards = load_catalog(path)
    kept = [c for c in cards if c.id != card_id]
    if len(kept) == len(cards):
        return False
    save_catalog(kept, path)
    return True


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for v in values:
        k = fold_name(v)
        if k and k not in seen:
            seen.add(k)
            out.append(v)
    return out
