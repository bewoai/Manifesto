"""Planlama xlsx okuma + (hibrit mimari) sadece 4 kimlik kolonunu geri yazma.

Brief §12.1 kararı: Excel kaynak olarak KALIR. Sistem planlama sayfasını okur,
yalnızca col 2/3/4/20'yi (UYRUK, M/F, İSİM, PASAPORT NO) doldurup geri yazar;
diğer her şey (PAX, otel, balon, pilot...) operasyon girişidir ve dokunulmaz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import openpyxl

from app import config
from app.manifest.excel_cache import get_cached_excel_data, clear_excel_cache


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
    rows: list[PlanningRow] = []
    for r in range(config.PLANNING_FIRST_DATA_ROW, ws.max_row + 1):
        name = _cell(ws, r, config.COL_NAME)
        balloon = _cell(ws, r, config.COL_BALLOON)
        if not name and not balloon and not _cell(ws, r, config.COL_PASSPORT_NO):
            continue
        pax_raw = _cell(ws, r, config.COL_PAX)
        try:
            pax = int(float(pax_raw)) if pax_raw else None
        except ValueError:
            pax = None
        rows.append(PlanningRow(
            row=r,
            pax=pax,
            nationality=_cell(ws, r, config.COL_UYRUK),
            sex=_cell(ws, r, config.COL_MF),
            name=name,
            room=_cell(ws, r, config.COL_ROOM),
            hotel=_cell(ws, r, config.COL_HOTEL),
            pickup=_cell(ws, r, config.COL_PICKUP),
            reserved_by=_cell(ws, r, config.COL_RESERVED_BY),
            agency=_cell(ws, r, config.COL_AGENCY),
            company=_cell(ws, r, config.COL_COMPANY),
            balloon=balloon.upper(),
            pilot=_cell(ws, r, config.COL_PILOT),
            note=_cell(ws, r, config.COL_NOTE),
            driver=_cell(ws, r, config.COL_DRIVER),
            coming_place=_cell(ws, r, config.COL_COMING_PLACE),
            passport_no=_cell(ws, r, config.COL_PASSPORT_NO),
        ))
    return rows


def read_rows(planning_xlsx: Path, sheet: str) -> list[PlanningRow]:
    """Bir gün sayfasının tüm satırlarını okur (header row 3 sonrası); boş koltuklar dahil."""
    def _read(path: Path, s: str) -> list[PlanningRow]:
        wb = openpyxl.load_workbook(path, data_only=True)
        if s not in wb.sheetnames:
            wb.close()
            raise KeyError(f"Planlama dosyasında '{s}' sayfası yok. Mevcut: {wb.sheetnames}")
        rows = _rows_from_ws(wb[s])
        wb.close()
        return rows

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


def assign_balloon(
    load: dict[str, int],
    pax: int,
    codes: list[str],
    capacity: int,
) -> tuple[str, bool]:
    """Yeni bir `pax` kişilik grup için balon seç (grup bölünmez).

    First-fit: `codes` sırasında kalan kapasitesi ≥ pax olan ilk balonu döndürür.
    Hiçbiri sığmazsa en az dolu balonu döndürür ve overflow=True işaretler.
    """
    if not codes:
        return "", True
    for code in codes:
        if capacity - load.get(code, 0) >= pax:
            return code, False
    # Hiçbiri tüm grubu alamıyor → en boş balon + overflow uyarısı
    least = min(codes, key=lambda c: load.get(c, 0))
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
    capacity: int,
    requested: str = "",
) -> dict:
    """Yeni `pax` kişilik grup için balon ve yazım biçimi seçer (grup bölünmez).

    Koltuk şablonu (sayfada serbest koltuk var): `requested`, sonra `codes` sırası, sonra
    sayfadaki diğer balonlar içinde ≥ pax ardışık serbest koltuğu olan ilk balon → "seat".
    Hiçbirinde yer yoksa overflow (operatör onayıyla şablonun altına eklenir).
    Ekleme şablonu (serbest koltuk yok): mevcut first-fit kapasite kuralı → "append".
    """
    runs = free_seat_runs(rows, blocks)
    requested = (requested or "").strip().upper()
    if runs:
        order = [c for c in [requested, *codes, *runs.keys()] if c]
        seen: set[str] = set()
        for code in order:
            if code in seen:
                continue
            seen.add(code)
            if any(len(seq) >= pax for seq in runs.get(code, [])):
                return {"balloon": code, "overflow": False, "mode": "seat"}
        if is_seat_template(rows, runs, capacity):
            least = requested if requested in codes else (codes[0] if codes else next(iter(runs)))
            return {"balloon": least, "overflow": True, "mode": "seat"}
        # Ekleme şablonunda silmeden kalan küçük boşluklar: grup sığmıyorsa sona ekle
    balloon, overflow = assign_balloon(balloon_load(blocks), pax, codes, capacity)
    return {"balloon": balloon, "overflow": overflow, "mode": "append"}


def is_seat_template(rows: list[PlanningRow], runs: dict[str, list[list[int]]], capacity: int) -> bool:
    """Sayfa, koltukları önceden balonlara dağıtan bir şablon mu?

    Ölçüt: serbest koltuğu olan en az bir balonun sayfada (dolu + boş) en az `capacity`
    satırı var. Arkadaşın şablonunda her balon 28 satırlık banttır; uygulamanın ekleme
    şablonunda serbest koltuk yalnız silmeden kalır ve bant oluşturmaz.
    """
    from collections import Counter

    per_balloon = Counter(r.balloon for r in rows if r.balloon)
    return any(per_balloon[b] >= capacity for b in runs)


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


def create_day_sheet(planning_xlsx: Path, new_sheet: str, source_sheet: Optional[str] = None) -> Path:
    """Yeni gün sekmesi oluşturur: kaynak günü kopyalar, veri satırlarını temizler."""
    wb = openpyxl.load_workbook(planning_xlsx)
    if new_sheet in wb.sheetnames:
        wb.close()
        raise ValueError(f"'{new_sheet}' sayfası zaten var.")

    candidates = [s for s in wb.sheetnames if s.lower() not in ("sayfa2", "sheet2")]
    if source_sheet and source_sheet in wb.sheetnames:
        source_name = source_sheet
    elif candidates:
        source_name = candidates[-1]
    else:
        wb.close()
        raise ValueError("Kopyalanacak gün sayfası bulunamadı.")

    ws = wb.copy_worksheet(wb[source_name])
    ws.title = new_sheet
    for row in range(config.PLANNING_FIRST_DATA_ROW, ws.max_row + 1):
        for col in range(1, config.COL_PASSPORT_NO + 1):
            ws.cell(row, col).value = None

    wb.save(planning_xlsx)
    wb.close()
    return planning_xlsx


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
