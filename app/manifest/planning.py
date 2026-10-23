"""Planlama xlsx okuma + (hibrit mimari) sadece 4 kimlik kolonunu geri yazma.

Brief §12.1 kararı: Excel kaynak olarak KALIR. Sistem planlama sayfasını okur,
yalnızca col 2/3/4/20'yi (UYRUK, M/F, İSİM, PASAPORT NO) doldurup geri yazar;
diğer her şey (PAX, otel, balon, pilot...) operasyon girişidir ve dokunulmaz.
"""
from __future__ import annotations

import re

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional, Union

import openpyxl

from app import config
from app.manifest.excel_cache import get_cached_excel_data, clear_excel_cache
from app.textfold import fold_name


@dataclass
class PlanningRow:
    row: int
    pax: Optional[int]           # rezervasyon grubu boyutu (yalnız lead satırda)
    nationality: str             # col 2
    sex: str                     # col 3
    name: str                    # col 4
    room: str
    hotel: str                   # col 6
    pickup: str                  # col 7
    reserved_by: str
    agency: str                  # col 9 — eşleştirme anahtarı
    company: str
    balloon: str                 # col 11 — manifesto filtresi
    pilot: str
    note: str
    driver: str
    coming_place: str
    passport_no: str             # col 20

    @property
    def is_seat(self) -> bool:
        """Önceden balona atanmış boş koltuk: balon kodu var; isim, pasaport ve PAX yok.

        Arkadaşın gerçek şablonu günün 112 satırını önceden balonlara dağıtır (balon başına
        28 satırlık bant; firma/balon/pilot dolu, isim boş). Bu satırlar yolcu değildir.
        """
        return bool(self.balloon) and not self.name and not self.passport_no and self.pax is None


# Koltuk şablonunda boş koltukta önceden dolu gelen, silme/küçültmede KORUNAN kolonlar
SEAT_TEMPLATE_COLS = (config.COL_COMPANY, config.COL_BALLOON, config.COL_PILOT, config.COL_COMING_PLACE)


@dataclass
class PassengerIdentity:
    row: int
    nationality: str
    sex: str
    name: str
    passport_no: str


@dataclass
class ReservationBlock:
    """Bir rezervasyon: lead satır (PAX dolu) + altındaki boş-PAX yolcu satırları.

    Operatör bu bloğu seçer, ait olduğu pasaport fotoğraflarını yükler; onaylanan
    pasaportlar bu bloğun satırlarına (col 2/3/4/20) sırayla yazılır.
    """
    lead_row: int
    rows: list[int]              # bloğun tüm satır indexleri (lead dâhil)
    pax: Optional[int]           # beklenen yolcu sayısı (PAX checksum)
    room: str
    agency: str
    reserved_by: str
    company: str
    balloon: str
    pilot: str
    note: str
    driver: str
    coming_place: str
    hotel: str
    pickup: str
    lead_name: str               # mevcut booking ismi (varsa) — eşleştirme ipucu
    passengers: list[PassengerIdentity] = field(default_factory=list)

    def label(self) -> str:
        pax = self.pax if self.pax is not None else "?"
        who = self.lead_name or "(isim yok)"
        return (f"r{self.lead_row}  •  {self.agency or '—'}  •  {self.balloon or '—'}  "
                f"•  PAX {pax}  •  {self.hotel or '—'}  •  {who}")


def _cell(ws, row: int, col: int) -> str:
    v = ws.cell(row, col).value
    return "" if v is None else str(v).strip()


def _rows_from_ws(ws) -> list[PlanningRow]:
    """Bir çalışma sayfasının veri satırlarını PlanningRow listesine çevirir (row 4+).

    İsim, balon ve pasaport no'su olmayan satırlar atlanır. Boş koltuklar (balon dolu,
    kimlik boş) listede kalır; `is_seat` ile ayırt edilir.
    """
    return _parse_rows(lambda r, c: _cell(ws, r, c), ws.max_row)


def _rows_from_grid(grid: list[tuple]) -> list[PlanningRow]:
    """Salt-okunur ızgaradan (satır değer demetleri, 1 tabanlı satır = indeks+1) aynı ayrıştırma."""
    def get(r: int, c: int) -> str:
        if r - 1 >= len(grid):
            return ""
        row = grid[r - 1]
        v = row[c - 1] if c - 1 < len(row) else None
        return "" if v is None else str(v).strip()
    return _parse_rows(get, len(grid))


def _parse_rows(get, max_row: int) -> list[PlanningRow]:
    rows: list[PlanningRow] = []
    for r in range(config.PLANNING_FIRST_DATA_ROW, max_row + 1):
        name = get(r, config.COL_NAME)
        balloon = get(r, config.COL_BALLOON)
        if not name and not balloon and not get(r, config.COL_PASSPORT_NO):
            continue
        pax_raw = get(r, config.COL_PAX)
        try:
            pax = int(float(pax_raw)) if pax_raw else None
        except ValueError:
            pax = None
        rows.append(PlanningRow(
            row=r,
            pax=pax,
            nationality=get(r, config.COL_UYRUK),
            sex=get(r, config.COL_MF),
            name=name,
            room=get(r, config.COL_ROOM),
            hotel=get(r, config.COL_HOTEL),
            pickup=get(r, config.COL_PICKUP),
            reserved_by=get(r, config.COL_RESERVED_BY),
            agency=get(r, config.COL_AGENCY),
            company=get(r, config.COL_COMPANY),
            balloon=balloon.upper(),
            pilot=get(r, config.COL_PILOT),
            note=get(r, config.COL_NOTE),
            driver=get(r, config.COL_DRIVER),
            coming_place=get(r, config.COL_COMING_PLACE),
            passport_no=get(r, config.COL_PASSPORT_NO),
        ))
    return rows


def _read_workbook_grid(path: Path) -> dict[str, list[tuple]]:
    """Kitabın tüm sayfalarını salt-okunur modda tek geçişte okur (yalnız değerler, A..T).

    Tam (biçimli) yükleme 17 sayfalık gerçek dosyada ~2,2 sn sürüyordu; bu yol ~0,25 sn'de
    bütün sayfaları verir. Birleşik hücrelerin sol üstü dışındaki hücreler None gelir (tam
    yüklemedeki MergedCell ile aynı).
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        grid: dict[str, list[tuple]] = {}
        for ws in wb.worksheets:
            ws.reset_dimensions()   # bozuk <dimension> etiketi satırları kesmesin
            grid[ws.title] = [list(r) for r in ws.iter_rows(values_only=True, max_col=config.COL_PASSPORT_NO)]
    finally:
        wb.close()
    # Salt-okunur mod birleşik alanların altında kalmış eski değerleri de döndürür; tam
    # yüklemede bunlar None'dur (MergedCell). Aynı sonucu vermek için sol üst dışını boşalt.
    for title, ranges in _merged_ranges(path).items():
        rows = grid.get(title)
        if not rows:
            continue
        for min_col, min_row, max_col, max_row in ranges:
            for r in range(min_row, min(max_row, len(rows)) + 1):
                row = rows[r - 1]
                for c in range(min_col, min(max_col, len(row)) + 1):
                    if (r, c) != (min_row, min_col):
                        row[c - 1] = None
    return {title: [tuple(r) for r in rows] for title, rows in grid.items()}


def _merged_ranges(path: Path) -> dict[str, list[tuple[int, int, int, int]]]:
    """Sayfa adı → birleşik alanlar (min_col, min_row, max_col, max_row); xlsx XML'inden okunur."""
    import posixpath
    import zipfile
    import xml.etree.ElementTree as ET
    from openpyxl.utils.cell import range_boundaries

    ns_main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    ns_rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    out: dict[str, list[tuple[int, int, int, int]]] = {}
    with zipfile.ZipFile(path) as z:
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels}
        wbx = ET.fromstring(z.read("xl/workbook.xml"))
        for sh in wbx.iter(f"{ns_main}sheet"):
            target = targets.get(sh.get(f"{ns_rel}id"))
            if not target:
                continue
            part = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
            try:
                xml = z.read(part)
            except KeyError:
                continue
            refs = re.findall(rb'<(?:\w+:)?mergeCell\s+ref="([A-Z]+[0-9]+:[A-Z]+[0-9]+)"', xml)
            if refs:
                out[sh.get("name")] = [range_boundaries(ref.decode()) for ref in refs]
    return out


def workbook_grid(planning_xlsx: Path) -> dict[str, list[tuple]]:
    """Önbellekli ızgara: dosyanın mtime+boyutu değişene kadar tek okuma paylaşılır."""
    return get_cached_excel_data(planning_xlsx, "workbook_grid", _read_workbook_grid)


def read_rows(planning_xlsx: Path, sheet: str) -> list[PlanningRow]:
    """Bir gün sayfasının tüm satırlarını okur (header row 3 sonrası); boş koltuklar dahil."""
    def _read(path: Path, s: str) -> list[PlanningRow]:
        grid = workbook_grid(path)
        if s not in grid:
            raise KeyError(f"Planlama dosyasında '{s}' sayfası yok. Mevcut: {list(grid)}")
        return _rows_from_grid(grid[s])

    return get_cached_excel_data(planning_xlsx, "read_rows", _read, sheet)


def group_blocks(rows: list[PlanningRow]) -> list[ReservationBlock]:
    """Satırları rezervasyon bloklarına böler: PAX dolu satır yeni blok başlatır.

    Boş koltuk satırı (`is_seat`) bloğa ancak blok PAX'ı dolmadıysa ve aynı balondaysa
    katılır (henüz kimliği gelmemiş yolcu yeri). Aksi hâlde serbest koltuktur, hiçbir
    bloğa ait değildir ve açık bloğu kapatır.
    """
    blocks: list[ReservationBlock] = []
    cur: Optional[ReservationBlock] = None
    for pr in rows:
        starts = pr.pax is not None
        if not starts and pr.is_seat:
            if (cur is not None and cur.pax is not None and len(cur.rows) < cur.pax
                    and pr.balloon == cur.balloon):
                cur.rows.append(pr.row)
                cur.passengers.append(PassengerIdentity(
                    row=pr.row, nationality="", sex="", name="", passport_no=""))
            else:
                cur = None   # serbest koltuk: bloğa ait değil
            continue
        if starts or cur is None:
            cur = ReservationBlock(
                lead_row=pr.row, rows=[pr.row], pax=pr.pax,
                room=pr.room, agency=pr.agency, reserved_by=pr.reserved_by,
                company=pr.company, balloon=pr.balloon, pilot=pr.pilot,
                note=pr.note, driver=pr.driver, coming_place=pr.coming_place,
                hotel=pr.hotel,
                pickup=pr.pickup, lead_name=pr.name,
                passengers=[PassengerIdentity(
                    row=pr.row,
                    nationality=pr.nationality,
                    sex=pr.sex,
                    name=pr.name,
                    passport_no=pr.passport_no,
                )],
            )
            blocks.append(cur)
        else:
            cur.rows.append(pr.row)
            cur.passengers.append(PassengerIdentity(
                row=pr.row,
                nationality=pr.nationality,
                sex=pr.sex,
                name=pr.name,
                passport_no=pr.passport_no,
            ))
    return blocks


def read_blocks(planning_xlsx: Path, sheet: str) -> list[ReservationBlock]:
    return group_blocks(read_rows(planning_xlsx, sheet))


# ─────────────────────────────────────────────────────────────────────
#  Balon otomatik atama (brief §15 revize: sistem atar)
# ─────────────────────────────────────────────────────────────────────

def block_seats(block: ReservationBlock) -> int:
    """Bloğun kapladığı koltuk sayısı (PAX, yoksa satır sayısı)."""
    return block.pax if block.pax is not None else len(block.rows)


def balloon_load(blocks: list[ReservationBlock]) -> dict[str, int]:
    """Balon kodu → dolu koltuk sayısı."""
    load: dict[str, int] = {}
    for b in blocks:
        if b.balloon:
            load[b.balloon] = load.get(b.balloon, 0) + block_seats(b)
    return load


Capacity = Union[int, Callable[[str], int]]


def capacity_fn(capacity: Capacity) -> Callable[[str], int]:
    """Kapasite argümanını `kod → kapasite` fonksiyonuna çevirir.

    Tek bir int (eski çağrılar, testler) tüm balonlara aynı kapasiteyi verir; fonksiyon
    (ör. `Settings.capacity_for`) balon başına kapasite verir. Boş kod varsayılanı döndürür.
    """
    if callable(capacity):
        return lambda code: int(capacity(str(code or "").strip().upper()))
    cap = int(capacity)
    return lambda _code: cap


def _candidates(codes: list[str], allowed: Optional[Iterable[str]]) -> list[str]:
    """`allowed` verilirse (günlük balon sınırı dolu) yalnız o balonlar; sıra `codes`, sonra kalanlar."""
    if allowed is None:
        return list(codes)
    allowed_set = {str(c).strip().upper() for c in allowed if c}
    out = [c for c in codes if c in allowed_set]
    out += sorted(allowed_set - set(out))
    return out


def pickup_key(value) -> str:
    """Pickup saatini karşılaştırma için 'HH:MM'e çevirir ('5:20', '05:20:00', '1900-01-01 05:20:00').

    Saat okunamazsa boş döner (bilinmiyor)."""
    m = re.search(r"(\d{1,2})[:.](\d{2})", str(value or ""))
    if not m:
        return ""
    h, mnt = int(m.group(1)), int(m.group(2))
    return f"{h:02d}:{mnt:02d}" if h < 24 and mnt < 60 else ""


def _same_pickup(a: str, b: str) -> bool:
    """Saatlerden biri bilinmiyorsa (henüz girilmemiş) eşleşir; ikisi de biliniyorsa eşit olmalı."""
    return not a or not b or a == b


def hotel_seats_by_balloon(blocks: list[ReservationBlock], hotel: str, pickup: str = "") -> dict[str, int]:
    """Bu otelin (ve aynı pickup saatinin) yolcularını taşıyan balonlar → koltuk; çoktan aza.

    Otel adları `fold_name` ile karşılaştırılır ("Argos" = "ARGOS", "Kapadokya  Otel" =
    "KAPADOKYA OTEL"). Aynı otel farklı saatte alınıyorsa ayrı araç/ayrı kalkış demektir,
    gruplanmaz; saati girilmemiş rezervasyon her saatle eşleşir. Eşit koltukta sayfada önce
    görülen balon önce gelir.
    """
    key = fold_name(hotel)
    if not key:
        return {}
    want = pickup_key(pickup)
    seats: dict[str, int] = {}
    for b in blocks:
        if b.balloon and fold_name(b.hotel) == key and _same_pickup(want, pickup_key(b.pickup)):
            seats[b.balloon] = seats.get(b.balloon, 0) + block_seats(b)
    return dict(sorted(seats.items(), key=lambda kv: -kv[1]))


def hotel_split(blocks: list[ReservationBlock]) -> list[dict]:
    """Aynı gün, aynı pickup saatinde 2+ balona dağılmış oteller (birleştirme önerisi).

    Aynı otel farklı saatlerde alınıyorsa dağınık sayılmaz (ayrı kalkış). Saati girilmemiş
    bloklar kendi grubundadır.
    Dönüş: [{"hotel", "pickup", "balloons": [kod, ...], "seats": toplam koltuk}], koltuk çoktan aza.
    `balloons` o otelden en çok koltuk taşıyandan aza sıralıdır. Görünen ad, sayfada ilk
    görülen yazımdır. Bilgi amaçlıdır; readiness uyarısı değildir (çıktıyı engellemez).
    """
    groups: dict[str, dict] = {}
    for b in blocks:
        name = fold_name(b.hotel)
        if not name or not b.balloon:
            continue
        key = f"{name}|{pickup_key(b.pickup)}"
        g = groups.setdefault(key, {"hotel": b.hotel.strip(), "pickup": pickup_key(b.pickup), "per": {}, "seats": 0})
        seats = block_seats(b)
        g["per"][b.balloon] = g["per"].get(b.balloon, 0) + seats
        g["seats"] += seats
    out = [
        {"hotel": g["hotel"], "pickup": g["pickup"],
         "balloons": [code for code, _ in sorted(g["per"].items(), key=lambda kv: -kv[1])],
         "seats": g["seats"]}
        for g in groups.values() if len(g["per"]) >= 2
    ]
    out.sort(key=lambda item: (-item["seats"], fold_name(item["hotel"])))
    return out


def assign_balloon(
    load: dict[str, int],
    pax: int,
    codes: list[str],
    capacity: Capacity,
    allowed: Optional[Iterable[str]] = None,
    hotel: str = "",
    pickup: str = "",
    blocks: Optional[list[ReservationBlock]] = None,
) -> tuple[str, bool]:
    """Yeni bir `pax` kişilik grup için balon seç (grup bölünmez).

    First-fit: `codes` sırasında kalan kapasitesi ≥ pax olan ilk balonu döndürür.
    Hiçbiri sığmazsa en az dolu balonu döndürür ve overflow=True işaretler.
    `allowed` verilirse yalnız bu balonlar aday olur (günlük balon sınırı).
    `hotel` ve `blocks` verilirse bu otelin yolcularını taşıyan aday balonlar (çok
    koltuktan aza) `codes` sırasından önce denenir; hiçbirine sığmazsa davranış aynıdır.
    """
    cap = capacity_fn(capacity)
    candidates = _candidates(codes, allowed)
    if not candidates:
        return (codes[0] if codes else ""), True
    preferred = [c for c in hotel_seats_by_balloon(blocks or [], hotel, pickup) if c in candidates]
    for code in [*preferred, *candidates]:
        if cap(code) - load.get(code, 0) >= pax:
            return code, False
    # Hiçbiri tüm grubu alamıyor → en boş balon + overflow uyarısı
    least = min(candidates, key=lambda c: load.get(c, 0) - cap(c))
    return least, True


def free_seat_runs(rows: list[PlanningRow], blocks: Optional[list[ReservationBlock]] = None) -> dict[str, list[list[int]]]:
    """Balon kodu → ardışık serbest koltuk satır dizileri (hiçbir bloğa ait olmayan boş koltuklar)."""
    blocks = group_blocks(rows) if blocks is None else blocks
    claimed = {r for b in blocks for r in b.rows}
    runs: dict[str, list[list[int]]] = {}
    prev: Optional[PlanningRow] = None
    for pr in rows:
        free = pr.is_seat and pr.row not in claimed
        if free:
            seq = runs.setdefault(pr.balloon, [])
            if prev is not None and prev.balloon == pr.balloon and prev.row == pr.row - 1 and seq and seq[-1][-1] == prev.row:
                seq[-1].append(pr.row)
            else:
                seq.append([pr.row])
            prev = pr
        else:
            prev = None
    return runs


def free_seat_summary(rows: list[PlanningRow], blocks: Optional[list[ReservationBlock]] = None) -> dict[str, dict]:
    """Balon → {"free": toplam serbest koltuk, "longest": en uzun ardışık dizi}."""
    return {b: {"free": sum(len(r) for r in seqs), "longest": max(len(r) for r in seqs)}
            for b, seqs in free_seat_runs(rows, blocks).items()}


def choose_balloon(
    rows: list[PlanningRow],
    blocks: list[ReservationBlock],
    pax: int,
    codes: list[str],
    capacity: Capacity,
    requested: str = "",
    allowed: Optional[Iterable[str]] = None,
    hotel: str = "",
    pickup: str = "",
) -> dict:
    """Yeni `pax` kişilik grup için balon ve yazım biçimi seçer (grup bölünmez).

    Koltuk şablonu (sayfada serbest koltuk var): `requested`, sonra aynı otelin balonları,
    sonra `codes` sırası, sonra sayfadaki diğer balonlar içinde ≥ pax ardışık serbest koltuğu
    olan ve balon kapasitesini aşmayan ilk balon → "seat". Hiçbirinde yer yoksa overflow
    (operatör onayıyla şablonun altına eklenir). Ekleme şablonu (serbest koltuk yok):
    first-fit kapasite kuralı → "append".

    `capacity`: tek int ya da `kod → kapasite` fonksiyonu (balon başına kapasite).
    `allowed`: verilirse yalnız bu balonlar aday olur (günlük balon sınırı dolduğunda
    uçan balonlar); iki modda da geçerlidir.
    `hotel`: verilirse bu otelin yolcularını zaten taşıyan balonlar (o otelden çok koltuk
    taşıyandan aza) normal sıradan önce denenir — pickup kolaylığı. Kapasite, günlük sınır
    ve ardışık koltuk kuralları aynen geçerlidir; hiçbirine sığmazsa davranış değişmez.
    Dönüşteki `hotel_match`: seçilen balon bu oteli zaten taşıyor mu.
    """
    cap = capacity_fn(capacity)
    allowed_set = None if allowed is None else {str(c).strip().upper() for c in allowed if c}
    load = balloon_load(blocks)
    runs = free_seat_runs(rows, blocks)
    requested = (requested or "").strip().upper()
    hotel_codes = list(hotel_seats_by_balloon(blocks, hotel, pickup))

    def result(code: str, overflow: bool, mode: str) -> dict:
        return {"balloon": code, "overflow": overflow, "mode": mode,
                "hotel_match": bool(code) and code in hotel_codes}

    if runs:
        order = [c for c in [requested, *hotel_codes, *codes, *runs.keys()] if c]
        seen: set[str] = set()
        for code in order:
            if code in seen:
                continue
            seen.add(code)
            if allowed_set is not None and code not in allowed_set:
                continue
            if load.get(code, 0) + pax > cap(code):
                continue
            if any(len(seq) >= pax for seq in runs.get(code, [])):
                return result(code, False, "seat")
        if is_seat_template(rows, runs, cap):
            pool = _candidates(codes, allowed_set)
            if requested in codes and (allowed_set is None or requested in allowed_set):
                least = requested
            else:
                least = pool[0] if pool else (codes[0] if codes else next(iter(runs)))
            return result(least, True, "seat")
        # Ekleme şablonunda silmeden kalan küçük boşluklar: grup sığmıyorsa sona ekle
    balloon, overflow = assign_balloon(load, pax, codes, cap, allowed=allowed_set,
                                       hotel=hotel, pickup=pickup, blocks=blocks)
    return result(balloon, overflow, "append")


def is_seat_template(rows: list[PlanningRow], runs: dict[str, list[list[int]]], capacity: Capacity) -> bool:
    """Sayfa, koltukları önceden balonlara dağıtan bir şablon mu?

    Ölçüt: serbest koltuğu olan en az bir balonun sayfada (dolu + boş) en az kendi
    kapasitesi kadar satırı var. Arkadaşın şablonunda her balon 28 satırlık banttır;
    uygulamanın ekleme şablonunda serbest koltuk yalnız silmeden kalır ve bant oluşturmaz.
    """
    from collections import Counter

    cap = capacity_fn(capacity)
    per_balloon = Counter(r.balloon for r in rows if r.balloon)
    return any(per_balloon[b] >= cap(b) for b in runs)


def pilot_for_balloon(rows: list[PlanningRow], code: str) -> str:
    """Verilen balonun mevcut satırlarından pilot adını bul (yoksa boş)."""
    code = code.upper().strip()
    for pr in rows:
        if pr.balloon == code and pr.pilot:
            return pr.pilot
    return ""


def _row_is_empty(ws, r: int) -> bool:
    """Tüm planlama kolonları (PAX..PASAPORT NO) boş mu? max_row sonrası boş sayılır."""
    if r > ws.max_row:
        return True
    return not any(_cell(ws, r, col) for col in range(1, config.COL_PASSPORT_NO + 1))


def next_free_row(ws) -> int:
    """Tüm planlama kolonları boş olan ilk veri satırı."""
    return next_free_rows(ws, 1)


def next_free_rows(ws, count: int) -> int:
    """`count` ardışık boş satırın ilkini döndürür.

    Yeni blok hiçbir dolu satırın üzerine yazılmaz: aradaki küçük boşluklar (ör.
    silinmiş tek yolcu) yalnız sığan bloklar için kullanılır; sığmayan blok sona eklenir.
    """
    count = max(1, int(count))
    r = config.PLANNING_FIRST_DATA_ROW
    while r <= ws.max_row:
        if all(_row_is_empty(ws, r + k) for k in range(count)):
            return r
        r += 1
    # Veri her zaman başlık satırlarının altından başlar (sayfada başlık olmasa bile)
    return max(ws.max_row + 1, config.PLANNING_FIRST_DATA_ROW)


def _clear_row(ws, r: int) -> None:
    """Satırın planlama kolonlarını temizler; koltuk şablonu kolonları (firma/balon/pilot/
    geleceği yer) korunur → satır, o balonun serbest koltuğu olarak kalır."""
    for c in range(1, config.COL_PASSPORT_NO + 1):
        if c in SEAT_TEMPLATE_COLS:
            continue
        ws.cell(r, c).value = None


def _claimed_rows(ws) -> set[int]:
    return {r for b in group_blocks(_rows_from_ws(ws)) for r in b.rows}


def _is_block_boundary(ws, row: int) -> bool:
    """Satır bir rezervasyon sınırı mı? (blok başı, boş/serbest koltuk satırı veya verinin sonu)

    Bir bloğun ortasına taşıma, o bloğu ikiye böler ve PAX/otel gibi lider alanları
    yanlış satıra düşürür; bu yüzden reorder yalnız sınırlara izin verir.
    """
    if row < config.PLANNING_FIRST_DATA_ROW:
        return False
    if row == config.PLANNING_FIRST_DATA_ROW or row > ws.max_row:
        return True
    claimed = _claimed_rows(ws)
    if row not in claimed or (row - 1) not in claimed:
        return True
    return bool(_cell(ws, row, config.COL_PAX))  # PAX dolu = lider satır


def _detach_merges(ws, *, from_row: int) -> list[tuple[int, int, int, int]]:
    """`from_row` ve altında başlayan birleşik aralıkları çözer ve koordinatlarını döndürür.

    openpyxl `insert_rows`/`delete_rows` birleşik hücreleri taşımaz; satır eklemeden
    önce ayırıp (`_detach_merges`), sonra kaydırılmış konuma geri takmak
    (`_reattach_merges`) gerekir. Aksi hâlde diğer blokların birleşmeleri yanlış
    satırlara düşer ve Excel değerleri gizler.
    """
    detached = []
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= from_row:
            ws.unmerge_cells(str(rng))
            detached.append((rng.min_row, rng.min_col, rng.max_row, rng.max_col))
    return detached


def _reattach_merges(ws, detached: list[tuple[int, int, int, int]], *, delta: int) -> None:
    for min_row, min_col, max_row, max_col in detached:
        min_row += delta
        max_row += delta
        if min_row >= config.PLANNING_FIRST_DATA_ROW and max_row >= min_row:
            ws.merge_cells(start_row=min_row, start_column=min_col,
                           end_row=max_row, end_column=max_col)


def _unmerge_rows(ws, lo: int, hi: int) -> None:
    for rng in list(ws.merged_cells.ranges):
        if not (rng.max_row < lo or rng.min_row > hi):
            ws.unmerge_cells(str(rng))


def _merge_lead_columns(ws, lead: int, last: int) -> None:
    if last <= lead:
        return
    for col in config.LEAD_MERGE_COLS:
        ws.merge_cells(start_row=lead, start_column=col, end_row=last, end_column=col)


def create_reservation(
    planning_xlsx: Path,
    sheet: str,
    *,
    pax: int,
    balloon: str,
    pilot: str = "",
    fields: Optional[dict] = None,
    out_path: Optional[Path] = None,
) -> dict:
    """Günün sayfasına boş satırlardan itibaren yeni rezervasyon bloğu ekler.

    Lider satıra PAX + lider-özel alanlar (agency/hotel/pickup/room/reserved_by/note);
    bloğun tüm satırlarına balloon/pilot/driver/coming_place yazılır. Biçim korunur.
    """
    fields = dict(fields or {})
    fields["balloon"] = balloon
    if pilot:
        fields["pilot"] = pilot

    wb = openpyxl.load_workbook(planning_xlsx)
    ws = wb[sheet]
    pax_rows = max(1, int(pax))

    # Koltuk şablonu: seçilen balonun ilk uygun ardışık serbest koltuklarına yaz.
    # Yer yoksa (veya şablon ekleme tipindeyse) hiçbir dolu satırın üzerine yazmadan sona ekle.
    seat_run = next(
        (seq for seq in free_seat_runs(_rows_from_ws(ws)).get(str(balloon).strip().upper(), [])
         if len(seq) >= pax_rows),
        None,
    )
    mode = "seat" if seat_run else "append"
    if seat_run:
        lead = seat_run[0]
    else:
        # Hedef satırların TAMAMI boş olmalı; aksi hâlde sonraki bloğun üzerine yazılırdı.
        lead = next_free_rows(ws, pax_rows)
    rows = list(range(lead, lead + pax_rows))
    last = rows[-1]

    # Hedef satırlarla kesişen mevcut birleşmeleri çöz (kaynak günden miras kalan,
    # yeni blok sınırlarımıza uymayan birleşik hücreler yazımı engeller).
    _unmerge_rows(ws, lead, last)

    from copy import copy
    ref_row = config.PLANNING_FIRST_DATA_ROW
    for r in (rows if mode == "append" else []):   # koltuklar zaten şablon biçiminde
        if r > ref_row:
            for c in range(1, ws.max_column + 1):
                sc = ws.cell(row=ref_row, column=c)
                tc = ws.cell(row=r, column=c)
                if sc.has_style:
                    tc.font = copy(sc.font)
                    tc.border = copy(sc.border)
                    tc.fill = copy(sc.fill)
                    tc.number_format = copy(sc.number_format)
                    tc.protection = copy(sc.protection)
                    tc.alignment = copy(sc.alignment)

    ws.cell(lead, config.COL_PAX).value = int(pax)
    for key, col in config.OPERATION_FIELD_TO_COL.items():
        if key == "pax" or key not in fields:
            continue
        value = fields[key]
        if value in (None, ""):
            continue
        target_rows = rows if key in config.BLOCK_WIDE_OPERATION_FIELDS else [lead]
        for row in target_rows:
            ws.cell(row, col).value = value

    # Lider-gösterim kolonlarını blok boyunca dikey birleştir (orijinal görünüm)
    _merge_lead_columns(ws, lead, last)

    target = out_path or planning_xlsx
    wb.save(target)
    wb.close()
    return {"lead_row": lead, "rows": rows, "balloon": balloon, "pilot": pilot, "mode": mode}


def list_sheets(planning_xlsx: Path) -> list[str]:
    """Gün sayfalarını döndürür (Sayfa2 gibi özet sayfaları hariç)."""
    def _read(path: Path) -> list[str]:
        wb = openpyxl.load_workbook(path, read_only=True)
        names = [s for s in wb.sheetnames if s.lower() not in ("sayfa2", "sheet2")]
        wb.close()
        return names
    return get_cached_excel_data(planning_xlsx, "list_sheets", _read)


def sheet_date(name: str):
    """'GG.AA.YYYY' sayfa adını tarihe çevirir; gün sayfası değilse None."""
    import datetime as _dt
    m = re.fullmatch(r"\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*", str(name or ""))
    if not m:
        return None
    try:
        return _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def day_seat_load(ws, *, capacity: Capacity, codes: list[str]) -> dict:
    """Bir gün sayfasının koltuk doluluğu: {"used", "free", "total"}.

    Dolu = `balloon_load` toplamı; serbest = `free_seat_summary` toplamı.
    Koltuk şablonunda (balon bantları) toplam, sayfadaki koltuklardır (dolu + serbest).
    Ekleme şablonunda satır yalnız yolcu için açıldığından toplam = kapasite × balon sayısı
    (Ayarlar'daki kodlar + sayfada görülenler).
    """
    return _day_seat_load_rows(_rows_from_ws(ws), capacity=capacity, codes=codes)


def _day_seat_load_rows(rows: list[PlanningRow], *, capacity: Capacity, codes: list[str]) -> dict:
    cap = capacity_fn(capacity)
    blocks = group_blocks(rows)
    load = balloon_load(blocks)
    free = free_seat_summary(rows, blocks)
    used = sum(load.values())
    free_total = sum(v["free"] for v in free.values())
    if _is_seat_layout_rows(rows, cap("")):   # bant tespiti varsayılan kapasiteyle
        total = used + free_total
    else:
        balloons = {c for c in codes if c} | set(load) | set(free)
        total = max(used + free_total, sum(cap(b) for b in balloons))
    return {"used": used, "free": free_total, "total": total}


def month_load(planning_xlsx: Path, year: int, month: int, *, capacity: Capacity, codes: list[str]) -> dict[str, dict]:
    """Ayın her gün sayfası için `day_seat_load`. Anahtar 'GG.AA.YYYY'.

    Ortak salt-okunur ızgarayı kullanır (gün okumalarıyla aynı tek okuma); okunamayan
    sayfa atlanır (takvim yine çizilir).
    """
    out: dict[str, dict] = {}
    for name, grid in workbook_grid(planning_xlsx).items():
        d = sheet_date(name)
        if d is None or d.year != year or d.month != month:
            continue
        try:
            out[d.strftime("%d.%m.%Y")] = _day_seat_load_rows(_rows_from_grid(grid), capacity=capacity, codes=codes)
        except Exception:
            continue
    return out


def nearest_source_sheet(sheetnames: list[str], new_sheet: str) -> Optional[str]:
    """Yeni gün için kopyalanacak gün: tarihçe en yakın ÖNCEKİ gün, yoksa en yakın sonraki."""
    target = sheet_date(new_sheet)
    dated = [(sheet_date(s), s) for s in sheetnames if sheet_date(s) and s != new_sheet]
    if not dated:
        return None
    if target is None:
        return max(dated)[1]
    before = [d for d in dated if d[0] < target]
    return (max(before) if before else min(dated))[1]


def is_seat_layout(ws, capacity: int = config.DEFAULT_BALLOON_CAPACITY) -> bool:
    """Sayfa satırları balon bantlarına önceden dağıtılmış mı (arkadaşın şablonu)?

    Ölçüt: en az 2 balon bandı kadar satırda balon kodu var ve her balon en çok 2
    ardışık parça hâlinde (ekleme şablonunda balonlar bloklar arasında karışır).
    """
    return _is_seat_layout_rows(_rows_from_ws(ws), capacity)


def _is_seat_layout_rows(rows: list[PlanningRow], capacity: int = config.DEFAULT_BALLOON_CAPACITY) -> bool:
    from collections import Counter

    cap = max(int(capacity or 28), 1)
    with_balloon = [r for r in rows if r.balloon]
    if len(with_balloon) < 2 * cap:
        return False
    runs: Counter = Counter()
    prev = None
    for r in with_balloon:
        if prev is None or r.balloon != prev.balloon or r.row != prev.row + 1:
            runs[r.balloon] += 1
        prev = r
    return max(runs.values()) <= 2


def _prepare_blank_day(ws, new_sheet: str, *, keep_seats: bool) -> None:
    """Kopyalanmış gün sayfasını boşaltır: rezervasyon birleşmeleri çözülür, veri temizlenir.

    keep_seats=True: firma/balon/pilot/geleceği yer korunur → koltuk düzeni aynen kalır.
    Başlıktaki tarih hücresi yeni güne güncellenir.
    """
    import datetime as _dt

    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= config.PLANNING_FIRST_DATA_ROW:
            ws.unmerge_cells(str(rng))
    for row in range(config.PLANNING_FIRST_DATA_ROW, ws.max_row + 1):
        if keep_seats:
            _clear_row(ws, row)
        else:
            for col in range(1, config.COL_PASSPORT_NO + 1):
                ws.cell(row, col).value = None
    new_date = sheet_date(new_sheet)
    if new_date:
        for r in range(1, config.PLANNING_FIRST_DATA_ROW - 1):
            for c in range(1, ws.max_column + 1):
                v = ws.cell(r, c).value
                if isinstance(v, (_dt.datetime, _dt.date)):
                    ws.cell(r, c).value = _dt.datetime(new_date.year, new_date.month, new_date.day)


def _place_chronologically(wb, ws) -> None:
    """Yeni gün sayfasını tarih sırasındaki yerine taşır (gün olmayan sayfalar sonda kalır)."""
    target = sheet_date(ws.title)
    if target is None:
        return
    names = wb.sheetnames
    idx_now = names.index(ws.title)
    dest = None
    for i, n in enumerate(names):
        d = sheet_date(n)
        if n != ws.title and d and d > target:
            dest = i
            break
    if dest is None:
        # son gün sayfasının hemen arkası
        dated_idx = [i for i, n in enumerate(names) if n != ws.title and sheet_date(n)]
        dest = (max(dated_idx) + 1) if dated_idx else idx_now
    if dest > idx_now:
        dest -= 1
    wb.move_sheet(ws, offset=dest - idx_now)


def _create_day_in_wb(wb, new_sheet: str, source_sheet: Optional[str]) -> str:
    if new_sheet in wb.sheetnames:
        raise ValueError(f"'{new_sheet}' sayfası zaten var.")
    if source_sheet and source_sheet in wb.sheetnames:
        source_name = source_sheet
    else:
        source_name = nearest_source_sheet(wb.sheetnames, new_sheet)
    if not source_name:
        raise ValueError("Kopyalanacak gün sayfası bulunamadı.")
    src = wb[source_name]
    keep_seats = is_seat_layout(src)
    ws = wb.copy_worksheet(src)
    ws.title = new_sheet
    _prepare_blank_day(ws, new_sheet, keep_seats=keep_seats)
    _place_chronologically(wb, ws)
    return source_name


def create_day_sheet(planning_xlsx: Path, new_sheet: str, source_sheet: Optional[str] = None) -> Path:
    """Yeni gün sekmesi oluşturur: en yakın önceki günü (ya da verilen kaynağı) kopyalar,
    rezervasyonları temizler. Kaynak koltuk düzenindeyse balon bantları/firma/pilot korunur."""
    wb = openpyxl.load_workbook(planning_xlsx)
    try:
        _create_day_in_wb(wb, new_sheet, source_sheet)
        wb.save(planning_xlsx)
    finally:
        wb.close()
    return planning_xlsx


def create_missing_days(planning_xlsx: Path, days: list[str]) -> list[str]:
    """Verilen günlerden dosyada olmayanları (tarih sırasıyla) boş gün olarak oluşturur."""
    wb = openpyxl.load_workbook(planning_xlsx)
    created: list[str] = []
    try:
        for day in sorted({d for d in days if sheet_date(d)}, key=sheet_date):
            if day in wb.sheetnames:
                continue
            _create_day_in_wb(wb, day, None)
            created.append(day)
        if created:
            wb.save(planning_xlsx)
    finally:
        wb.close()
    return created


def delete_reservation(planning_xlsx: Path, sheet: str, rows: list[int],
                       out_path: Optional[Path] = None) -> Path:
    """Bir rezervasyon bloğunun satırlarını temizler, birleşmeleri çözer.

    Firma/balon/pilot/geleceği yer korunur: satırlar o balonun serbest koltuğu olur ve
    sonraki `create_reservation` bunları tekrar kullanır (koltuk şablonu bozulmaz).
    """
    if not rows:
        return planning_xlsx
    wb = openpyxl.load_workbook(planning_xlsx)
    ws = wb[sheet]
    lo, hi = min(rows), max(rows)
    # Bu satırlarla kesişen birleşmeleri çöz (yoksa MergedCell yazılamaz)
    for rng in list(ws.merged_cells.ranges):
        if not (rng.max_row < lo or rng.min_row > hi):
            ws.unmerge_cells(str(rng))
    for r in rows:
        _clear_row(ws, r)
    target = out_path or planning_xlsx
    wb.save(target)
    wb.close()
    return target


def reorder_reservation(planning_xlsx: Path, sheet: str, source_rows: list[int], target_row: int, out_path: Optional[Path] = None) -> Path:
    """Belirli bir rezervasyon bloğunu (source_rows) hedef satırın (target_row) üstüne taşır."""
    if not source_rows or target_row in source_rows:
        return planning_xlsx

    target_row = int(target_row)
    wb = openpyxl.load_workbook(planning_xlsx)
    ws = wb[sheet]
    lo, hi = min(source_rows), max(source_rows)
    num_rows = hi - lo + 1

    if not _is_block_boundary(ws, target_row):
        wb.close()
        raise ValueError(
            f"Hedef satır {target_row} bir rezervasyon sınırı değil; "
            "bloğu başka bir bloğun başına veya listenin sonuna bırakın."
        )

    _unmerge_rows(ws, lo, hi)

    # insert_rows birleşmeleri taşımaz → hedefin altındakileri ayır, ekle, kaydırarak geri tak
    detached = _detach_merges(ws, from_row=target_row)
    ws.insert_rows(target_row, num_rows)
    _reattach_merges(ws, detached, delta=num_rows)

    new_lo = lo + num_rows if lo >= target_row else lo
    
    from copy import copy
    for r_offset in range(num_rows):
        old_r = new_lo + r_offset
        new_r = target_row + r_offset
        for col in range(1, ws.max_column + 1):
            sc = ws.cell(row=old_r, column=col)
            tc = ws.cell(row=new_r, column=col)
            tc.value = sc.value
            if sc.has_style:
                tc.font = copy(sc.font)
                tc.border = copy(sc.border)
                tc.fill = copy(sc.fill)
                tc.number_format = copy(sc.number_format)
                tc.protection = copy(sc.protection)
                tc.alignment = copy(sc.alignment)
    
    # delete_rows da birleşmeleri taşımaz → silinen bandın altındakileri ayır, sil, geri tak
    detached = _detach_merges(ws, from_row=new_lo + num_rows)
    ws.delete_rows(new_lo, num_rows)
    _reattach_merges(ws, detached, delta=-num_rows)

    final_target = target_row if target_row <= lo else target_row - num_rows
    _merge_lead_columns(ws, final_target, final_target + num_rows - 1)
    
    target = out_path or planning_xlsx
    wb.save(target)
    wb.close()
    return target


def delete_passenger_from_reservation(
    planning_xlsx: Path,
    sheet: str,
    *,
    lead_row: int,
    rows: list[int],
    target_row: int,
    out_path: Optional[Path] = None,
) -> dict:
    """Rezervasyon içinden tek yolcu siler, operasyon alanlarını korur.

    Lider yolcu silinirse alttaki ilk dolu kimlik lider satıra taşınır. Böylece
    PAX/otel/acente gibi lider satırdaki operasyon bilgileri kaybolmaz.
    """
    if target_row not in rows:
        raise ValueError("Silinecek yolcu bu rezervasyon bloğunda değil.")
    if len(rows) <= 1:
        delete_reservation(planning_xlsx, sheet, rows, out_path=out_path)
        return {"deleted_block": True, "pax": 0}

    wb = openpyxl.load_workbook(planning_xlsx)
    ws = wb[sheet]
    lo, hi = min(rows), max(rows)

    _unmerge_rows(ws, lo, hi)

    identity_cols = (config.COL_UYRUK, config.COL_MF, config.COL_NAME, config.COL_PASSPORT_NO)

    target_index = rows.index(target_row)
    for index in range(target_index, len(rows) - 1):
        source_row = rows[index + 1]
        destination_row = rows[index]
        for col in identity_cols:
            ws.cell(destination_row, col).value = ws.cell(source_row, col).value

    clear_row = rows[-1]
    _clear_row(ws, clear_row)

    pax_raw = _cell(ws, lead_row, config.COL_PAX)
    try:
        pax = int(float(pax_raw)) if pax_raw else len(rows)
    except ValueError:
        pax = len(rows)
    pax = max(1, pax - 1)
    ws.cell(lead_row, config.COL_PAX).value = pax
    _merge_lead_columns(ws, lead_row, rows[-2])

    target = out_path or planning_xlsx
    wb.save(target)
    wb.close()
    return {"deleted_block": False, "pax": pax, "cleared_row": clear_row}


def resize_reservation(
    planning_xlsx: Path,
    sheet: str,
    *,
    lead_row: int,
    rows: list[int],
    new_pax: int,
    allow_data_loss: bool = False,
    out_path: Optional[Path] = None,
) -> list[int]:
    """Rezervasyonu bitişik satır düzenini koruyarak büyütür veya küçültür."""
    if not (1 <= new_pax <= config.MAX_PAX):
        raise ValueError(f"PAX 1-{config.MAX_PAX} arasında olmalı.")
    if not rows or rows[0] != lead_row:
        raise ValueError("Rezervasyon satırları geçersiz.")

    wb = openpyxl.load_workbook(planning_xlsx)
    ws = wb[sheet]
    old_last = rows[-1]
    new_last = lead_row + new_pax - 1
    _unmerge_rows(ws, lead_row, max(old_last, new_last))

    if new_last > old_last:
        lead_balloon = _cell(ws, lead_row, config.COL_BALLOON).upper()
        sheet_rows = {pr.row: pr for pr in _rows_from_ws(ws)}
        claimed = {r for b in group_blocks(list(sheet_rows.values())) for r in b.rows}
        for row in range(old_last + 1, new_last + 1):
            pr = sheet_rows.get(row)
            empty = not any(_cell(ws, row, col) for col in range(1, config.COL_PASSPORT_NO + 1))
            same_balloon_seat = (pr is not None and pr.is_seat and row not in claimed
                                 and pr.balloon == lead_balloon)
            if not (empty or same_balloon_seat):
                wb.close()
                raise ValueError(
                    "PAX artırılamadı; rezervasyonun altındaki satırlar başka veri içeriyor "
                    "ya da başka balonun koltuğu."
                )
        
        from copy import copy
        ref_row = config.PLANNING_FIRST_DATA_ROW
        for row in range(old_last + 1, new_last + 1):
            if row > ref_row:
                for col in range(1, ws.max_column + 1):
                    sc = ws.cell(row=ref_row, column=col)
                    tc = ws.cell(row=row, column=col)
                    if sc.has_style:
                        tc.font = copy(sc.font)
                        tc.border = copy(sc.border)
                        tc.fill = copy(sc.fill)
                        tc.number_format = copy(sc.number_format)
                        tc.protection = copy(sc.protection)
                        tc.alignment = copy(sc.alignment)

        for key in config.BLOCK_WIDE_OPERATION_FIELDS:
            col = config.OPERATION_FIELD_TO_COL[key]
            value = ws.cell(lead_row, col).value
            for row in range(old_last + 1, new_last + 1):
                ws.cell(row, col).value = value
    elif new_last < old_last:
        removed_rows = range(new_last + 1, old_last + 1)
        has_identity = any(
            _cell(ws, row, col)
            for row in removed_rows
            for col in (config.COL_UYRUK, config.COL_MF, config.COL_NAME, config.COL_PASSPORT_NO)
        )
        if has_identity and not allow_data_loss:
            wb.close()
            raise ValueError(
                "PAX azaltılacak satırlarda yolcu bilgisi var. Açık onay gerekli."
            )
        for row in removed_rows:
            _clear_row(ws, row)

    ws.cell(lead_row, config.COL_PAX).value = new_pax
    _merge_lead_columns(ws, lead_row, new_last)
    target = out_path or planning_xlsx
    wb.save(target)
    wb.close()
    return list(range(lead_row, new_last + 1))


def write_identity(planning_xlsx: Path, sheet: str, updates: dict[int, dict],
                   out_path: Optional[Path] = None) -> Path:
    """Belirli satırların yalnız kimlik kolonlarını günceller, biçimi korur.

    updates: { row_index: {"nationality": "...", "sex": "M",
                           "name": "...", "passport_no": "..."} }
    Yalnızca verilen alanlar yazılır; None/eksik alanlara dokunulmaz.
    """
    wb = openpyxl.load_workbook(planning_xlsx)  # biçim korunur
    ws = wb[sheet]
    field_to_col = {
        "nationality": config.COL_UYRUK,
        "sex": config.COL_MF,
        "name": config.COL_NAME,
        "passport_no": config.COL_PASSPORT_NO,
    }
    for row, fields in updates.items():
        for key, col in field_to_col.items():
            if key in fields and fields[key] is not None:
                ws.cell(row, col).value = fields[key]
    target = out_path or planning_xlsx
    wb.save(target)
    wb.close()
    return target


def write_operation_details(
    planning_xlsx: Path,
    sheet: str,
    lead_row: int,
    rows: list[int],
    fields: dict,
    out_path: Optional[Path] = None,
) -> Path:
    """Rezervasyonun operasyon alanlarını yazar.

    PAX/otel/acente gibi rezervasyon alanları lead satıra yazılır. Balon, pilot,
    şoför ve geleceği yer bloktaki tüm yolculara yazılır; bu kolonlar gerçek
    listede her yolcu satırında tekrar ediyor ve manifesto filtresi için önemlidir.
    """
    wb = openpyxl.load_workbook(planning_xlsx)
    ws = wb[sheet]
    for key, col in config.OPERATION_FIELD_TO_COL.items():
        if key not in fields:
            continue
        value = fields[key]
        target_rows = rows if key in config.BLOCK_WIDE_OPERATION_FIELDS else [lead_row]
        for row in target_rows:
            ws.cell(row, col).value = value
    target = out_path or planning_xlsx
    wb.save(target)
    wb.close()
    return target



# ─── Rezervasyonları birleşik düzene getirme ───────────────────────────
# Arkadaşın doğru örneğinde bir rezervasyonun ortak bilgileri (PAX, irtibat/oda, otel,
# pickup, rezerve yapan, acente, not) blok boyunca TEK birleşik hücrede durur. Elle
# girilmiş bazı bloklarda aynı değer her satıra tekrar yazılmış olabiliyor; bu yardımcı
# yalnız güvenli durumda (tüm dolu değerler aynı) birleştirir, farklı değer varsa dokunmaz.

def _multi_row_blocks(rows: list[PlanningRow]) -> list[tuple[ReservationBlock, int, int]]:
    out = []
    for b in group_blocks(rows):
        block_rows = sorted(b.rows)
        if len(block_rows) >= 2 and block_rows == list(range(block_rows[0], block_rows[-1] + 1)):
            out.append((b, block_rows[0], block_rows[-1]))
    return out


def block_merge_columns(rows: list[PlanningRow], merged: list[tuple[int, int, int, int]]) -> tuple[int, ...]:
    """Sayfanın KENDİ düzenine göre hangi kolonlar rezervasyon boyunca birleştirilir.

    Çok satırlı rezervasyonların en az yarısında tam (lider..son satır) birleşik olan aday
    kolonlar seçilir. Sayfada henüz birleşik rezervasyon yoksa çekirdek beş kolon. Böylece
    yolcu başına yazılan irtibat/oda ve not gibi kolonlar zorla birleştirilmez.
    """
    blocks = _multi_row_blocks(rows)
    exact = {(m[0], m[1], m[3]) for m in merged if m[0] == m[2]}
    counts = {c: sum(1 for _, lead, last in blocks if (c, lead, last) in exact) for c in config.BLOCK_MERGE_CANDIDATE_COLS}
    with_any = sum(1 for _, lead, last in blocks if any((c, lead, last) in exact for c in config.BLOCK_MERGE_CANDIDATE_COLS))
    if with_any < 2:
        return tuple(config.BLOCK_MERGE_CORE_COLS)
    chosen = tuple(c for c in config.BLOCK_MERGE_CANDIDATE_COLS if counts[c] * 2 >= with_any)
    return chosen or tuple(config.BLOCK_MERGE_CORE_COLS)


def plan_block_merges(rows: list[PlanningRow], get, merged: list[tuple[int, int, int, int]]) -> dict:
    """Hangi blok/kolonun birleştirileceğini hesaplar (yazmaz).

    get(r, c) → hücre metni; merged → (min_col, min_row, max_col, max_row) listesi.
    Kolonlar sayfanın kendi düzeninden öğrenilir (`block_merge_columns`).
    Döner: {"actions": [{lead_row, last_row, col, value}], "skipped": [{lead_row, lead_name, col, values}],
            "blocks": birleştirilecek blok sayısı, "columns": [kolon no]}
    """
    actions: list[dict] = []
    skipped: list[dict] = []
    touched: set[int] = set()
    columns = block_merge_columns(rows, merged)
    for b, lead, last in _multi_row_blocks(rows):
        block_rows = list(range(lead, last + 1))
        for col in columns:
            covering = [m for m in merged if m[0] <= col <= m[2] and not (m[3] < lead or m[1] > last)]
            if any(m[1] == lead and m[3] == last and m[0] == col == m[2] for m in covering):
                continue          # zaten doğru birleşik
            if covering:
                skipped.append({"lead_row": lead, "lead_name": b.lead_name, "col": col, "values": ["(başka bir birleşik alan)"]})
                continue
            values = [get(r, col) for r in block_rows]
            filled = {v for v in values if v}
            if len(filled) > 1:
                skipped.append({"lead_row": lead, "lead_name": b.lead_name, "col": col, "values": sorted(filled)})
                continue
            actions.append({"lead_row": lead, "last_row": last, "col": col, "value": next(iter(filled), "")})
            touched.add(lead)
    return {"actions": actions, "skipped": skipped, "blocks": len(touched), "columns": list(columns)}


def merge_reservation_blocks(planning_xlsx: Path, sheet: str, out_path: Optional[Path] = None) -> dict:
    """`plan_block_merges` planını uygular: değer lider satıra yazılır, diğerleri temizlenip birleştirilir."""
    wb = openpyxl.load_workbook(planning_xlsx)
    try:
        if sheet not in wb.sheetnames:
            raise KeyError(f"'{sheet}' sayfası yok.")
        ws = wb[sheet]
        rows = _rows_from_ws(ws)
        merged = [(m.min_col, m.min_row, m.max_col, m.max_row) for m in ws.merged_cells.ranges]
        plan = plan_block_merges(rows, lambda r, c: _cell(ws, r, c), merged)
        for a in plan["actions"]:
            lead_cell = ws.cell(a["lead_row"], a["col"])
            raw = None
            for r in range(a["lead_row"], a["last_row"] + 1):     # özgün tipi koru (saat, sayı)
                v = ws.cell(r, a["col"]).value
                if v not in (None, ""):
                    raw = v
                    break
            for r in range(a["lead_row"] + 1, a["last_row"] + 1):
                ws.cell(r, a["col"]).value = None
            lead_cell.value = raw
            ws.merge_cells(start_row=a["lead_row"], start_column=a["col"], end_row=a["last_row"], end_column=a["col"])
            from openpyxl.styles import Alignment
            al = lead_cell.alignment
            lead_cell.alignment = Alignment(horizontal=al.horizontal or "center", vertical="center", wrap_text=al.wrap_text)
        wb.save(out_path or planning_xlsx)
    finally:
        wb.close()
    clear_excel_cache()
    return {"blocks": plan["blocks"], "cells": len(plan["actions"]), "skipped": plan["skipped"]}


def preview_block_merges(planning_xlsx: Path, sheet: str) -> dict:
    """Ortak salt-okunur ızgara + XML birleşmeleriyle yazmadan plan (Excel görünümü düğmesi için)."""
    grid = workbook_grid(planning_xlsx)
    if sheet not in grid:
        raise KeyError(f"'{sheet}' sayfası yok.")
    values = grid[sheet]
    rows = _rows_from_grid(values)

    def get(r: int, c: int) -> str:
        if r - 1 >= len(values):
            return ""
        row = values[r - 1]
        v = row[c - 1] if c - 1 < len(row) else None
        return "" if v is None else str(v).strip()

    return plan_block_merges(rows, get, _merged_ranges(planning_xlsx).get(sheet, []))
