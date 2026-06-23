"""İrtifa — masaüstü uygulaması (tkinter).

Akış (brief'in tam zinciri):
  1) Planlama Excel + gün seç
  2) Rezervasyon bloğu seç
  3) Pasaport fotoğraflarını ekle → "MRZ oku" (Claude Vision)
  4) Kontrol: yeşil/sarı; operatör sarıları düzeltir/onaylar
  5) "Planlamaya yaz" → ana uçuş listesine (col 2/3/4/20) yazılır
  6) "Manifesto üret" → güncellenen planlamadan balon manifestosu

Çift tıkla açılan .exe için tasarlandı (PyInstaller). Tek harici görsel bağımlılık
Pillow; gerisi stdlib.
"""
from __future__ import annotations

import shutil
import threading
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import (BOTH, END, LEFT, RIGHT, W, X, Y, BooleanVar, Canvas, StringVar,
                     Tk, Toplevel, filedialog, messagebox, simpledialog, ttk)

from PIL import Image, ImageTk

from app import config, settings as settings_mod
from app.manifest.planning import (
    ReservationBlock,
    list_sheets,
    read_blocks,
    create_day_sheet,
    write_identity,
    write_operation_details,
)
from app.manifest.writer import export as export_manifest

GREEN = "#1c7c3a"
YELLOW = "#b07a00"
GREY = "#888888"
ADD_OPTION_LABEL = "+ Yeni ekle..."
SELECT_OPERATION_FIELDS = {
    "hotel",
    "reserved_by",
    "agency",
    "company",
    "balloon",
    "pilot",
    "driver",
    "coming_place",
}


class ToolTip:
    """Small hover explanation for the operator-facing question marks."""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + 18
        self.tip = Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(
            self.tip,
            text=self.text,
            padding=8,
            relief="solid",
            borderwidth=1,
            background="#fff8dc",
            wraplength=320,
            justify="left",
        )
        label.pack()

    def _hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def add_help(parent, text: str):
    label = ttk.Label(parent, text="?", foreground="#0b5cab", cursor="question_arrow")
    ToolTip(label, text)
    return label


class ManifestoApp:
    def __init__(self, root: Tk):
        self.root = root
        self.settings = settings_mod.load()
        self.blocks: list[ReservationBlock] = []
        self.current_block: ReservationBlock | None = None
        self._planning_snapshot: Path | None = None
        self.op_vars: dict[str, StringVar] = {}
        self.op_widgets: dict[str, ttk.Widget] = {}
        self.photos: list[str] = []
        self.records: list = []           # PassportRecord
        self._cards: list[dict] = []      # her kart: vars + entry'ler
        self._thumbs: list = []           # PhotoImage GC koruması

        root.title("Balon Uçuş — Pasaport & Manifesto")
        root.geometry("1180x860")
        self._build_ui()
        self._refresh_api_badge()
        self._autoload_planning()

    # ---------------------------------------------------------------- UI iskeleti
    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=X)
        ttk.Label(top, text="Balon Uçuş — Pasaport → Planlama → Manifesto",
                  font=("Segoe UI", 13, "bold")).pack(side=LEFT)
        ttk.Button(top, text="⚙ Ayarlar", command=self._open_settings).pack(side=RIGHT)
        self.api_badge = ttk.Label(top, text="", font=("Segoe UI", 9))
        self.api_badge.pack(side=RIGHT, padx=10)

        # 1) dosya + gün
        f1 = ttk.LabelFrame(self.root, text="1) Planlama dosyası ve gün", padding=8)
        f1.pack(fill=X, padx=8, pady=4)
        plan_value = self.settings.google_spreadsheet_id if self.settings.uses_google_sheets() else str(self.settings.planning_path())
        self.plan_var = StringVar(value=plan_value)
        ttk.Entry(f1, textvariable=self.plan_var, width=70).grid(row=0, column=0, sticky=W)
        ttk.Button(f1, text="Seç…", command=self._pick_planning).grid(row=0, column=1, padx=4)
        ttk.Label(f1, text="Gün:").grid(row=0, column=2, padx=(16, 4))
        self.sheet_var = StringVar()
        self.sheet_combo = ttk.Combobox(f1, textvariable=self.sheet_var, width=14, state="readonly")
        self.sheet_combo.grid(row=0, column=3)
        ttk.Button(f1, text="Yükle", command=self._load_day).grid(row=0, column=4, padx=6)
        ttk.Button(f1, text="Yeni gün", command=self._create_day).grid(row=0, column=5, padx=4)
        add_help(
            f1,
            "Seçili günü şablon olarak kopyalar, yeni tarih sekmesi oluşturur ve 4. satırdan "
            "itibaren listeyi boşaltır. Başlıklar ve biçim korunur.",
        ).grid(row=0, column=6, padx=(2, 0))

        # 2) rezervasyon
        f2 = ttk.LabelFrame(self.root, text="2) Rezervasyon bloğu", padding=8)
        f2.pack(fill=X, padx=8, pady=4)
        self.block_var = StringVar()
        self.block_combo = ttk.Combobox(f2, textvariable=self.block_var, width=95, state="readonly")
        self.block_combo.pack(side=LEFT, fill=X, expand=True)
        self.block_combo.bind("<<ComboboxSelected>>", self._on_block_select)
        add_help(
            f2,
            "Bir rezervasyon bloğu, PAX yazan ana satır ve altındaki yolcu satırlarıdır. "
            "Onaylanan pasaport bilgileri bu bloğun satırlarına sırayla yazılır.",
        ).pack(side=LEFT, padx=6)

        f_ops = ttk.LabelFrame(self.root, text="3) Operasyon bilgileri", padding=8)
        f_ops.pack(fill=X, padx=8, pady=4)
        op_fields = [
            ("pax", "PAX", 6, "Rezervasyondaki yolcu sayısı. Lead satıra yazılır."),
            ("room", "Oda / irtibat", 14, "Oda no veya irtibat bilgisi. Lead satıra yazılır."),
            ("hotel", "Otel", 20, "Misafirin alınacağı otel. Lead satıra yazılır."),
            ("pickup", "Pickup", 10, "Alış saati. Örn. 04:10."),
            ("reserved_by", "Rezerve yapan", 18, "Rezervasyonu yapan kişi veya firma."),
            ("agency", "Acente", 18, "Satışı yapan acente adı."),
            ("company", "Uçacağı firma", 10, "Operasyon firması. Örn. THK."),
            ("balloon", "Balon", 8, "Manifesto filtresi için balon kodu. Örn. BYF, BZR."),
            ("pilot", "Pilot", 12, "Uçuş pilotu."),
            ("driver", "Alış şoför", 8, "Pickup aracı/şoför numarası."),
            ("coming_place", "Geleceği yer", 16, "Örn. DİREKT ALAN."),
            ("note", "Not", 18, "Rezervasyon notu."),
        ]
        for i, (key, label, width, help_text) in enumerate(op_fields):
            row = i // 4
            base_col = (i % 4) * 3
            ttk.Label(f_ops, text=label).grid(row=row * 2, column=base_col, sticky=W, padx=3)
            var = StringVar()
            self.op_vars[key] = var
            if key in SELECT_OPERATION_FIELDS:
                widget = ttk.Combobox(f_ops, textvariable=var, width=width, state="readonly")
                widget.bind("<<ComboboxSelected>>", lambda _evt, field=key: self._on_operation_option(field))
            else:
                widget = ttk.Entry(f_ops, textvariable=var, width=width)
            widget.grid(row=row * 2 + 1, column=base_col, sticky=W, padx=3, pady=(0, 4))
            self.op_widgets[key] = widget
            add_help(f_ops, help_text).grid(row=row * 2 + 1, column=base_col + 1, sticky=W, padx=(0, 8))

        # 4) foto + işle
        f3 = ttk.LabelFrame(self.root, text="3) Pasaport fotoğrafları", padding=8)
        f3.pack(fill=X, padx=8, pady=4)
        ttk.Button(f3, text="📷 Fotoğraf ekle…", command=self._add_photos).pack(side=LEFT)
        ttk.Button(f3, text="Temizle", command=self._clear_photos).pack(side=LEFT, padx=4)
        self.photo_lbl = ttk.Label(f3, text="0 foto")
        self.photo_lbl.pack(side=LEFT, padx=10)
        self.process_btn = ttk.Button(f3, text="▶ MRZ oku (Claude)", command=self._process)
        self.process_btn.pack(side=LEFT, padx=10)
        add_help(
            f3,
            "API'siz modda fotoğraflar için boş giriş kartları açılır ve 4 alan elle doldurulur. "
            "Claude modunda fotoğraftaki MRZ otomatik okunur; yine de operatör onayı gerekir.",
        ).pack(side=LEFT)
        self.prog = ttk.Label(f3, text="")
        self.prog.pack(side=LEFT, padx=8)

        # 4) kontrol (scrollable)
        f4 = ttk.LabelFrame(self.root, text="4) Kontrol — yeşil: doğrulandı / sarı: gözden geçir", padding=4)
        f4.pack(fill=BOTH, expand=True, padx=8, pady=4)
        self.canvas = Canvas(f4, highlightthickness=0)
        sb = ttk.Scrollbar(f4, orient="vertical", command=self.canvas.yview)
        self.cards_frame = ttk.Frame(self.canvas)
        self.cards_frame.bind("<Configure>",
                              lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

        # 5) aksiyonlar + durum
        f5 = ttk.Frame(self.root, padding=8)
        f5.pack(fill=X)
        ttk.Button(f5, text="💾 Planlamaya yaz", command=self._write_planning).pack(side=LEFT)
        add_help(
            f5,
            "Operasyon alanlarını her zaman yazar. Onay işaretli pasaport kartları varsa ayrıca "
            "UYRUK, M/F, İSİM ve PASAPORT NO kolonlarını doldurur.",
        ).pack(side=LEFT, padx=(4, 8))
        ttk.Label(f5, text="Balon:").pack(side=LEFT, padx=(16, 4))
        self.balloon_var = StringVar()
        self.balloon_combo = ttk.Combobox(f5, textvariable=self.balloon_var, width=8, state="readonly")
        self.balloon_combo.pack(side=LEFT)
        ttk.Button(f5, text="📄 Manifesto üret", command=self._export).pack(side=LEFT, padx=8)
        add_help(
            f5,
            "Seçilen gün ve balon koduna göre manifesto üretir. Manifesto, planlama listesinden "
            "türetilir; cinsiyet ve uyruk dönüşümleri otomatik yapılır.",
        ).pack(side=LEFT)
        self.status = ttk.Label(self.root, text="Hazır.", relief="sunken", anchor=W, padding=4)
        self.status.pack(fill=X, side="bottom")

    # ---------------------------------------------------------------- yardımcılar
    def _set_status(self, text: str):
        self.status.config(text=text)
        self.root.update_idletasks()

    def _refresh_api_badge(self):
        if self.settings.uses_claude():
            self.process_btn.config(text="▶ MRZ oku (Claude)")
            if self.settings.has_api_key():
                self.api_badge.config(text="● Claude modu: API anahtarı tanımlı", foreground=GREEN)
            else:
                self.api_badge.config(text="● Claude modu: API anahtarı YOK", foreground=YELLOW)
        else:
            self.process_btn.config(text="✎ Elle giriş kartlarını aç")
            self.api_badge.config(text="● API'siz mod: elle giriş", foreground=GREEN)

    def _autoload_planning(self):
        if self.settings.uses_google_sheets():
            self.plan_var.set(self.settings.google_spreadsheet_id)
            if not self.settings.google_is_configured():
                self.sheet_combo["values"] = []
                self._set_status("Google Sheets modu için Ayarlar'da Sheet ID ve servis hesabı JSON dosyası gerekli.")
                return
            try:
                from app import google_sheets
                sheets = google_sheets.list_sheets(self.settings)
                self.sheet_combo["values"] = sheets
                if sheets:
                    self.sheet_var.set(sheets[-1])
            except Exception as e:
                self.sheet_combo["values"] = []
                self._set_status(f"Google Sheets okunamadı: {e}")
            return

        p = Path(self.plan_var.get())
        if p.exists():
            try:
                sheets = list_sheets(p)
                self.sheet_combo["values"] = sheets
                if sheets:
                    self.sheet_var.set(sheets[-1])  # en güncel gün
            except Exception:
                pass

    # ---------------------------------------------------------------- 1) dosya/gün
    def _pick_planning(self):
        if self.settings.uses_google_sheets():
            messagebox.showinfo(
                "Google Sheets modu",
                "Google Sheet dosyası Ayarlar ekranındaki Sheet ID ile seçilir.\n"
                "Sheet ID ve servis hesabı JSON dosyasını Ayarlar'dan girin.",
            )
            self._open_settings()
            return
        path = filedialog.askopenfilename(title="Planlama Excel'i seç",
                                          filetypes=[("Excel", "*.xlsx")])
        if path:
            self.plan_var.set(path)
            self._autoload_planning()

    def _load_day(self):
        if self.settings.uses_google_sheets():
            if not self.settings.google_is_configured():
                messagebox.showwarning("Eksik", "Google Sheets için Sheet ID ve servis hesabı JSON dosyası gerekli.")
                self._open_settings()
                return
            try:
                from app import google_sheets
                self._set_status("Google Sheet indiriliyor…")
                p = google_sheets.download_as_xlsx(self.settings)
                self._planning_snapshot = p
            except Exception as e:
                messagebox.showerror("Google Sheets hatası", f"Google Sheet okunamadı:\n{e}")
                return
        else:
            p = Path(self.plan_var.get())
            self._planning_snapshot = p
        sheet = self.sheet_var.get()
        if not p.exists() or not sheet:
            messagebox.showwarning("Eksik", "Geçerli planlama dosyası ve gün seç.")
            return
        try:
            self.blocks = read_blocks(p, sheet)
        except Exception as e:
            messagebox.showerror("Hata", f"Gün okunamadı:\n{e}")
            return
        self.block_combo["values"] = [b.label() for b in self.blocks]
        balloons = sorted({b.balloon for b in self.blocks if b.balloon})
        self.balloon_combo["values"] = balloons
        if balloons:
            self.balloon_var.set(balloons[0])
        self._refresh_operation_options()
        self._set_status(f"{sheet}: {len(self.blocks)} rezervasyon yüklendi.")

    def _create_day(self):
        source_sheet = self.sheet_var.get()
        new_sheet = simpledialog.askstring(
            "Yeni gün",
            "Yeni gün adını girin (örn. 24.06.2026):",
            parent=self.root,
        )
        new_sheet = (new_sheet or "").strip()
        if not new_sheet:
            return
        try:
            datetime.strptime(new_sheet, "%d.%m.%Y")
        except ValueError:
            messagebox.showwarning("Tarih formatı", "Gün adını gg.aa.yyyy şeklinde girin. Örn. 24.06.2026")
            return

        try:
            if self.settings.uses_google_sheets():
                if not self.settings.google_is_configured():
                    messagebox.showwarning("Eksik", "Google Sheets için Sheet ID ve servis hesabı JSON dosyası gerekli.")
                    self._open_settings()
                    return
                from app import google_sheets
                google_sheets.create_day_sheet(self.settings, new_sheet, source_sheet)
                sheets = google_sheets.list_sheets(self.settings)
            else:
                plan = Path(self.plan_var.get())
                if not plan.exists():
                    messagebox.showwarning("Eksik", "Önce geçerli planlama Excel dosyasını seçin.")
                    return
                backup = plan.with_suffix(f".bak-new-day-{datetime.now():%Y%m%d-%H%M%S}.xlsx")
                shutil.copy2(plan, backup)
                create_day_sheet(plan, new_sheet, source_sheet)
                sheets = list_sheets(plan)
                self._set_status(f"{new_sheet} oluşturuldu. Yedek: {backup.name}")
        except PermissionError:
            messagebox.showerror("Dosya kilitli", "Planlama Excel'i açık görünüyor. Excel'i kapatıp tekrar dene.")
            return
        except Exception as e:
            messagebox.showerror("Yeni gün oluşturulamadı", str(e))
            return

        self.sheet_combo["values"] = sheets
        self.sheet_var.set(new_sheet)
        self.blocks = []
        self.current_block = None
        self.block_combo["values"] = []
        self.block_var.set("")
        self.balloon_combo["values"] = []
        self.balloon_var.set("")
        self._refresh_operation_options()
        self._set_status(f"{new_sheet} günü oluşturuldu. Liste boş ve kullanıma hazır.")
        messagebox.showinfo("Tamam", f"{new_sheet} günü oluşturuldu.")

    def _on_block_select(self, _evt=None):
        i = self.block_combo.current()
        if 0 <= i < len(self.blocks):
            self.current_block = self.blocks[i]
            self._load_operation_form(self.current_block)
            if self.current_block.balloon:
                self.balloon_var.set(self.current_block.balloon)
            self._set_status(f"Rezervasyon seçildi: {self.current_block.label()}")

    def _load_operation_form(self, block: ReservationBlock):
        values = {
            "pax": "" if block.pax is None else str(block.pax),
            "room": block.room,
            "hotel": block.hotel,
            "pickup": block.pickup,
            "reserved_by": block.reserved_by,
            "agency": block.agency,
            "company": block.company,
            "balloon": block.balloon,
            "pilot": block.pilot,
            "driver": block.driver,
            "coming_place": block.coming_place,
            "note": block.note,
        }
        for key, value in values.items():
            if key in self.op_vars:
                self.op_vars[key].set(value or "")
        self._refresh_operation_options()

    def _operation_fields(self) -> dict:
        fields = {}
        for key, var in self.op_vars.items():
            value = var.get().strip()
            if value == ADD_OPTION_LABEL:
                value = ""
            if key in {"balloon", "pilot", "coming_place"}:
                value = value.upper()
            fields[key] = value
        return fields

    def _refresh_operation_options(self):
        for field in SELECT_OPERATION_FIELDS:
            widget = self.op_widgets.get(field)
            if not isinstance(widget, ttk.Combobox):
                continue
            widget["values"] = self._operation_options_for(field) + [ADD_OPTION_LABEL]

    def _operation_options_for(self, field: str) -> list[str]:
        seen: set[str] = set()
        values: list[str] = []

        def add(value):
            text = "" if value is None else str(value).strip()
            norm = text.upper()
            if text and text != ADD_OPTION_LABEL and norm not in seen:
                values.append(text)
                seen.add(norm)

        for value in self.settings.operation_options.get(field, []):
            add(value)
        for block in self.blocks:
            add(getattr(block, field, ""))

        if field in {"balloon", "pilot", "coming_place"}:
            values.sort(key=lambda x: x.upper())
        else:
            values.sort()
        return values

    def _on_operation_option(self, field: str):
        value = self.op_vars[field].get()
        if value != ADD_OPTION_LABEL:
            if field == "balloon":
                self._set_manifest_balloon(value)
            return

        new_value = simpledialog.askstring(
            "Yeni seçenek",
            f"{field} için yeni değer:",
            parent=self.root,
        )
        new_value = (new_value or "").strip()
        if not new_value:
            self.op_vars[field].set("")
            return
        if field in {"balloon", "pilot", "coming_place"}:
            new_value = new_value.upper()

        options = self.settings.operation_options.setdefault(field, [])
        if new_value.upper() not in {str(v).strip().upper() for v in options}:
            options.append(new_value)
            settings_mod.save(self.settings.normalized())
        self._refresh_operation_options()
        self.op_vars[field].set(new_value)
        if field == "balloon":
            self._set_manifest_balloon(new_value)

    def _set_manifest_balloon(self, value: str):
        value = value.strip()
        if not value:
            return
        values = list(self.balloon_combo["values"])
        if value not in values:
            values.append(value)
            values.sort()
            self.balloon_combo["values"] = values
        self.balloon_var.set(value)

    # ---------------------------------------------------------------- 3) foto/işle
    def _add_photos(self):
        paths = filedialog.askopenfilenames(
            title="Pasaport fotoğrafları",
            filetypes=[("Görsel", "*.jpg *.jpeg *.png *.webp"), ("Tümü", "*.*")])
        self.photos.extend(paths)
        self.photo_lbl.config(text=f"{len(self.photos)} foto")

    def _clear_photos(self):
        self.photos.clear()
        self.photo_lbl.config(text="0 foto")

    def _process(self):
        if not self.photos:
            messagebox.showinfo("Foto yok", "Önce pasaport fotoğrafı ekle.")
            return
        if not self.settings.uses_claude():
            self._process_manual()
            return
        if not self.settings.has_api_key():
            messagebox.showwarning("API anahtarı yok",
                                   "Pasaport okuma için Ayarlar'dan Claude API anahtarı gir.")
            self._open_settings()
            return
        self.process_btn.config(state="disabled")
        self._set_status("MRZ okunuyor…")
        threading.Thread(target=self._process_worker, daemon=True).start()

    def _process_manual(self):
        from app.vision.extractor import PassportRecord
        from app.validation.flags import Flag, ValidationOutcome

        self.records = [
            PassportRecord(
                source=ph,
                mrz=None,
                outcome=ValidationOutcome(flags=[Flag.UNREADABLE]),
                error="API'siz mod: bilgileri elle doldurup onaylayın.",
            )
            for ph in self.photos
        ]
        self._render_cards()
        self._set_status(f"{len(self.records)} foto için elle giriş kartı açıldı.")

    def _process_worker(self):
        # ağ işleri thread'de; sonuçları root.after ile UI'ya taşı
        from app.vision.extractor import process_file
        import anthropic
        key = self.settings.anthropic_api_key.strip() or None
        client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        results, seen = [], set()
        total = len(self.photos)
        for i, ph in enumerate(self.photos, 1):
            self.root.after(0, self.prog.config, {"text": f"{i}/{total}"})
            try:
                rec = process_file(ph, client=client, model=self.settings.model,
                                   seen_document_numbers=seen)
                if rec.mrz and rec.mrz.document_number:
                    seen.add(rec.mrz.document_number)
            except Exception as e:  # beklenmedik — kartı hata olarak göster
                from app.vision.extractor import PassportRecord
                from app.validation.flags import Flag, ValidationOutcome
                rec = PassportRecord(source=ph, mrz=None,
                                     outcome=ValidationOutcome(flags=[Flag.UNREADABLE]),
                                     error=str(e))
            results.append(rec)
        self.root.after(0, self._process_done, results)

    def _process_done(self, results):
        self.records = results
        self.prog.config(text="")
        self.process_btn.config(state="normal")
        self._render_cards()
        greens = sum(1 for r in results if r.is_green)
        self._set_status(f"{len(results)} okundu — {greens} yeşil, {len(results) - greens} sarı.")

    # ---------------------------------------------------------------- 4) kartlar
    def _render_cards(self):
        for w in self.cards_frame.winfo_children():
            w.destroy()
        self._cards.clear()
        self._thumbs.clear()
        for rec in self.records:
            self._render_card(rec)

    def _render_card(self, rec):
        f = rec.to_fields()
        green = f["green"]
        card = ttk.Frame(self.cards_frame, padding=6, relief="ridge", borderwidth=1)
        card.pack(fill=X, pady=3, padx=3)

        # sol: thumbnail
        try:
            img = Image.open(rec.source); img.thumbnail((110, 150))
            ph = ImageTk.PhotoImage(img); self._thumbs.append(ph)
            ttk.Label(card, image=ph).grid(row=0, column=0, rowspan=2, padx=6)
        except Exception:
            ttk.Label(card, text="[görsel\nyok]", foreground=GREY).grid(row=0, column=0, rowspan=2, padx=6)

        # orta: 4 düzenlenebilir alan
        fields = ttk.Frame(card); fields.grid(row=0, column=1, sticky=W)
        vars_ = {}
        field_help = {
            "nationality": "Pasaport MRZ uyruğu. Üç harfli kod girilir: örn. ITA, CHN, RUS.",
            "sex": "Pasaport cinsiyet alanı. Sadece M veya F girilir.",
            "name": "Pasaporttaki ad soyad. Manifestoya bu isim gider; büyük harf önerilir.",
            "passport_no": "Pasaport veya kimlik numarası. Manifestoya aynen yazılır.",
        }
        for col, (key, lbl) in enumerate(
                [("nationality", "UYRUK"), ("sex", "M/F"),
                 ("name", "İSİM"), ("passport_no", "PASAPORT NO")]):
            ttk.Label(fields, text=lbl, font=("Segoe UI", 8), foreground=GREY).grid(row=0, column=col, sticky=W, padx=3)
            v = StringVar(value=str(f.get(key) or ""))
            width = 30 if key == "name" else 10
            ttk.Entry(fields, textvariable=v, width=width).grid(row=1, column=col, padx=3, sticky=W)
            add_help(fields, field_help[key]).grid(row=2, column=col, sticky=W, padx=3)
            vars_[key] = v

        # sağ: durum + onay
        right = ttk.Frame(card); right.grid(row=0, column=2, rowspan=2, padx=10, sticky=W)
        flags = ", ".join(f["flags"]) if f["flags"] else ""
        status_txt = "● YEŞİL" if green else "● SARI"
        ttk.Label(right, text=status_txt, foreground=(GREEN if green else YELLOW),
                  font=("Segoe UI", 10, "bold")).pack(anchor=W)
        detail = flags or (f.get("error") or "")
        if detail:
            ttk.Label(right, text=detail, foreground=GREY, font=("Segoe UI", 8),
                      wraplength=180).pack(anchor=W)
        approve = BooleanVar(value=green)  # yeşiller varsayılan onaylı
        ttk.Checkbutton(right, text="Onayla", variable=approve).pack(anchor=W, pady=2)
        add_help(
            right,
            "Bu kutu işaretliyse kart Planlamaya yaz düğmesiyle ana listeye aktarılır. "
            "Sarı kayıtları kontrol edip düzelttikten sonra işaretleyin.",
        ).pack(anchor=W)

        self._cards.append({"rec": rec, "vars": vars_, "approve": approve})

    # ---------------------------------------------------------------- 5) yaz/üret
    def _write_planning(self):
        if not self.current_block:
            messagebox.showwarning("Rezervasyon yok", "Önce bir rezervasyon bloğu seç.")
            return
        approved = [c for c in self._cards if c["approve"].get()]
        block = self.current_block
        rows = block.rows
        if len(approved) > len(rows):
            messagebox.showwarning(
                "Fazla yolcu",
                f"Onaylı {len(approved)} pasaport var ama blokta {len(rows)} satır.\n"
                "Sadece ilk satırlar doldurulacak.")
        if approved and block.pax is not None and len(approved) != block.pax:
            if not messagebox.askyesno(
                    "PAX uyuşmuyor",
                    f"Beklenen PAX {block.pax}, onaylı {len(approved)}. Yine de yazılsın mı?"):
                return

        operation_fields = self._operation_fields()
        updates = {}
        for c, row in zip(approved, rows):
            v = c["vars"]
            updates[row] = {
                "nationality": v["nationality"].get().strip().upper(),
                "sex": v["sex"].get().strip().upper(),
                "name": v["name"].get().strip().upper(),
                "passport_no": v["passport_no"].get().strip(),
            }
        if self.settings.uses_google_sheets():
            try:
                from app import google_sheets
                google_sheets.write_operation_details(
                    self.settings,
                    self.sheet_var.get(),
                    block.lead_row,
                    rows,
                    operation_fields,
                )
                google_sheets.write_identity(self.settings, self.sheet_var.get(), updates)
            except Exception as e:
                messagebox.showerror("Hata", f"Google Sheet'e yazılamadı:\n{e}")
                return
            self._planning_snapshot = None
            self._set_status(f"{len(updates)} yolcu Google Sheet'e yazıldı.")
            messagebox.showinfo("Tamam", f"{len(updates)} yolcu Drive'daki Google Sheet'e yazıldı.")
            if self.settings.delete_images_after_write:
                self._maybe_delete_images()
            return

        plan = Path(self.plan_var.get())
        try:
            backup = plan.with_suffix(f".bak-{datetime.now():%Y%m%d-%H%M%S}.xlsx")
            shutil.copy2(plan, backup)
            write_operation_details(plan, self.sheet_var.get(), block.lead_row, rows, operation_fields)
            write_identity(plan, self.sheet_var.get(), updates)
        except PermissionError:
            messagebox.showerror("Dosya kilitli",
                                 "Planlama Excel'i açık görünüyor. Excel'i kapatıp tekrar dene.")
            return
        except Exception as e:
            messagebox.showerror("Hata", f"Yazılamadı:\n{e}")
            return
        self._set_status(f"{len(updates)} yolcu planlamaya yazıldı (yedek: {backup.name}).")
        messagebox.showinfo("Tamam", f"{len(updates)} yolcu ana uçuş listesine yazıldı.\n"
                                     f"Yedek alındı: {backup.name}")
        if self.settings.delete_images_after_write:
            self._maybe_delete_images()

    def _maybe_delete_images(self):
        if messagebox.askyesno("KVKK", "İşlenen pasaport fotoğrafları silinsin mi?"):
            for ph in self.photos:
                try:
                    Path(ph).unlink()
                except OSError:
                    pass
            self._clear_photos()

    def _export(self):
        if self.settings.uses_google_sheets():
            try:
                from app import google_sheets
                self._set_status("Google Sheet güncel kopyası indiriliyor…")
                plan = google_sheets.download_as_xlsx(self.settings)
                self._planning_snapshot = plan
            except Exception as e:
                messagebox.showerror("Google Sheets hatası", f"Manifesto için Google Sheet indirilemedi:\n{e}")
                return
        else:
            plan = Path(self.plan_var.get())
        sheet, balloon = self.sheet_var.get(), self.balloon_var.get()
        if not (plan.exists() and sheet and balloon):
            messagebox.showwarning("Eksik", "Planlama, gün ve balon gerekli.")
            return
        out_dir = self.settings.output_path(); out_dir.mkdir(parents=True, exist_ok=True)
        try:
            path = export_manifest(plan, sheet, balloon, out_dir, self.settings.template_path())
        except Exception as e:
            messagebox.showerror("Hata", f"Manifesto üretilemedi:\n{e}\n\n{traceback.format_exc()}")
            return
        self._set_status(f"Manifesto: {path}")
        if messagebox.askyesno("Tamam", f"{balloon} manifestosu üretildi:\n{path}\n\nKlasörü aç?"):
            try:
                import os
                os.startfile(out_dir)  # Windows
            except Exception:
                pass

    # ---------------------------------------------------------------- Ayarlar
    def _open_settings(self):
        SettingsDialogV2(self.root, self.settings, on_save=self._on_settings_saved)

    def _on_settings_saved(self, s: settings_mod.Settings):
        self.settings = s
        self._refresh_api_badge()
        if s.uses_google_sheets():
            self.plan_var.set(s.google_spreadsheet_id)
            self._autoload_planning()
        elif s.planning_xlsx:
            self.plan_var.set(s.planning_xlsx)
            self._autoload_planning()


class SettingsDialog:
    def __init__(self, parent, settings: settings_mod.Settings, on_save):
        self.on_save = on_save
        self.win = ttk.Frame  # placeholder
        import tkinter as tk
        self.top = tk.Toplevel(parent)
        self.top.title("Ayarlar")
        self.top.geometry("680x390")
        self.top.transient(parent); self.top.grab_set()
        self.vars = {}
        self.mode_labels = {
            "API'siz / elle giriş": settings_mod.VISION_MODE_MANUAL,
            "Claude Vision / otomatik okuma": settings_mod.VISION_MODE_CLAUDE,
        }
        current_mode = next(
            (label for label, value in self.mode_labels.items() if value == settings.vision_mode),
            "API'siz / elle giriş",
        )
        self.mode_var = StringVar(value=current_mode)
        ttk.Label(self.top, text="Pasaport okuma modu").grid(row=0, column=0, sticky=W, padx=8, pady=6)
        ttk.Combobox(
            self.top,
            textvariable=self.mode_var,
            values=list(self.mode_labels.keys()),
            state="readonly",
            width=49,
        ).grid(row=0, column=1, padx=8, sticky=W)
        rows = [
            ("anthropic_api_key", "Claude API anahtarı", settings.anthropic_api_key, True),
            ("model", "Model", settings.model, False),
            ("planning_xlsx", "Planlama Excel (boş=otomatik)", settings.planning_xlsx, False),
            ("manifest_template", "Manifesto şablonu (boş=varsayılan)", settings.manifest_template, False),
            ("output_dir", "Manifesto çıktı klasörü (boş=./out)", settings.output_dir, False),
        ]
        for i, (key, lbl, val, secret) in enumerate(rows):
            grid_row = i + 1
            ttk.Label(self.top, text=lbl).grid(row=grid_row, column=0, sticky=W, padx=8, pady=6)
            v = StringVar(value=val); self.vars[key] = v
            ttk.Entry(self.top, textvariable=v, width=52,
                      show="*" if secret else "").grid(row=grid_row, column=1, padx=8, sticky=W)
        self.del_var = BooleanVar(value=settings.delete_images_after_write)
        ttk.Checkbutton(self.top, text="Yazımdan sonra fotoğrafları sormadan silmeyi öner (KVKK)",
                        variable=self.del_var).grid(row=len(rows) + 1, column=1, sticky=W, padx=8, pady=6)
        ttk.Label(self.top, text="Anahtar: console.anthropic.com → API Keys",
                  foreground=GREY, font=("Segoe UI", 8)).grid(row=len(rows) + 2, column=1, sticky=W, padx=8)
        bar = ttk.Frame(self.top); bar.grid(row=len(rows) + 3, column=0, columnspan=2, pady=12)
        ttk.Button(bar, text="Kaydet", command=self._save).pack(side=LEFT, padx=6)
        ttk.Button(bar, text="İptal", command=self.top.destroy).pack(side=LEFT, padx=6)

    def _save(self):
        s = settings_mod.Settings(
            vision_mode=self.mode_labels.get(self.mode_var.get(), settings_mod.VISION_MODE_MANUAL),
            anthropic_api_key=self.vars["anthropic_api_key"].get().strip(),
            model=self.vars["model"].get().strip() or settings_mod.DEFAULT_MODEL,
            planning_xlsx=self.vars["planning_xlsx"].get().strip(),
            manifest_template=self.vars["manifest_template"].get().strip(),
            output_dir=self.vars["output_dir"].get().strip(),
            delete_images_after_write=self.del_var.get(),
        )
        settings_mod.save(s)
        self.on_save(s)
        self.top.destroy()


class SettingsDialogV2:
    def __init__(self, parent, settings: settings_mod.Settings, on_save):
        self.on_save = on_save
        import tkinter as tk
        self.top = tk.Toplevel(parent)
        self.top.title("Ayarlar")
        self.top.geometry("760x520")
        self.top.transient(parent)
        self.top.grab_set()
        self.vars = {}
        self.existing_operation_options = settings.operation_options

        self.mode_labels = {
            "API'siz / elle giriş": settings_mod.VISION_MODE_MANUAL,
            "Claude Vision / otomatik okuma": settings_mod.VISION_MODE_CLAUDE,
        }
        self.source_labels = {
            "Excel dosyası": settings_mod.DATA_SOURCE_EXCEL,
            "Google Sheets": settings_mod.DATA_SOURCE_GOOGLE_SHEETS,
        }
        current_mode = next(
            (label for label, value in self.mode_labels.items() if value == settings.vision_mode),
            "API'siz / elle giriş",
        )
        current_source = next(
            (label for label, value in self.source_labels.items() if value == settings.data_source),
            "Excel dosyası",
        )
        self.mode_var = StringVar(value=current_mode)
        self.source_var = StringVar(value=current_source)

        self._combo_row(
            0,
            "Pasaport okuma modu",
            self.mode_var,
            list(self.mode_labels.keys()),
            "API'siz modda pasaport bilgileri elle girilir. Claude Vision modunda fotoğraftaki MRZ "
            "otomatik okunur; bunun için Claude API anahtarı gerekir.",
        )
        self._combo_row(
            1,
            "Planlama kaynağı",
            self.source_var,
            list(self.source_labels.keys()),
            "Excel dosyası seçilirse ana planlama bilgisayardaki xlsx dosyasından okunur. "
            "Google Sheets seçilirse Drive'daki Sheet okunur ve onaylanan 4 kimlik alanı oraya yazılır.",
        )

        rows = [
            ("anthropic_api_key", "Claude API anahtarı", settings.anthropic_api_key, True,
             "Sadece Claude Vision modunda gerekir. API'siz modda boş kalabilir."),
            ("model", "Model", settings.model, False,
             "Claude Vision modunda kullanılacak model adı. Emin değilseniz varsayılan kalsın."),
            ("planning_xlsx", "Planlama Excel", settings.planning_xlsx, False,
             "Excel modunda kullanılacak ana uçuş planlama dosyası. Boş bırakılırsa Downloads içindeki varsayılan dosya aranır."),
            ("google_spreadsheet_id", "Google Sheet ID", settings.google_spreadsheet_id, False,
             "Google Sheets modunda Drive'daki dosyanın URL içindeki ID kısmı. Sheet servis hesabıyla paylaşılmış olmalı."),
            ("google_credentials_json", "Google servis hesabı JSON", settings.google_credentials_json, False,
             "Google Cloud servis hesabı JSON anahtar dosyası. Bu dosya programın Sheet'i okuyup yazmasını sağlar."),
            ("manifest_template", "Manifesto şablonu", settings.manifest_template, False,
             "Manifesto biçimi için kullanılacak şablon. Boş bırakılırsa programın kendi şablonu kullanılır."),
            ("output_dir", "Manifesto çıktı klasörü", settings.output_dir, False,
             "Üretilen manifesto dosyalarının kaydedileceği klasör. Boşsa Documents/Irtifa kullanılır."),
        ]
        for i, (key, label, value, secret, help_text) in enumerate(rows, start=2):
            self._entry_row(i, key, label, value, secret, help_text)

        self.del_var = BooleanVar(value=settings.delete_images_after_write)
        ttk.Checkbutton(
            self.top,
            text="Yazımdan sonra fotoğrafları silmeyi sor (KVKK)",
            variable=self.del_var,
        ).grid(row=len(rows) + 2, column=1, sticky=W, padx=8, pady=6)
        add_help(
            self.top,
            "Ham pasaport fotoğraflarının gereksiz saklanmaması için yazma işleminden sonra silmeyi sorar.",
        ).grid(row=len(rows) + 2, column=2, padx=4)

        ttk.Label(
            self.top,
            text="Google Sheets için: Sheet'i servis hesabı e-postasıyla paylaşın.",
            foreground=GREY,
            font=("Segoe UI", 8),
        ).grid(row=len(rows) + 3, column=1, sticky=W, padx=8)

        bar = ttk.Frame(self.top)
        bar.grid(row=len(rows) + 4, column=0, columnspan=3, pady=12)
        ttk.Button(bar, text="Kaydet", command=self._save).pack(side=LEFT, padx=6)
        ttk.Button(bar, text="İptal", command=self.top.destroy).pack(side=LEFT, padx=6)

    def _combo_row(self, row: int, label: str, variable: StringVar, values: list[str], help_text: str):
        ttk.Label(self.top, text=label).grid(row=row, column=0, sticky=W, padx=8, pady=6)
        ttk.Combobox(
            self.top,
            textvariable=variable,
            values=values,
            state="readonly",
            width=49,
        ).grid(row=row, column=1, padx=8, sticky=W)
        add_help(self.top, help_text).grid(row=row, column=2, padx=4)

    def _entry_row(self, row: int, key: str, label: str, value: str, secret: bool, help_text: str):
        ttk.Label(self.top, text=label).grid(row=row, column=0, sticky=W, padx=8, pady=6)
        variable = StringVar(value=value)
        self.vars[key] = variable
        ttk.Entry(
            self.top,
            textvariable=variable,
            width=52,
            show="*" if secret else "",
        ).grid(row=row, column=1, padx=8, sticky=W)
        add_help(self.top, help_text).grid(row=row, column=2, padx=4)

    def _save(self):
        s = settings_mod.Settings(
            vision_mode=self.mode_labels.get(self.mode_var.get(), settings_mod.VISION_MODE_MANUAL),
            data_source=self.source_labels.get(self.source_var.get(), settings_mod.DATA_SOURCE_EXCEL),
            anthropic_api_key=self.vars["anthropic_api_key"].get().strip(),
            model=self.vars["model"].get().strip() or settings_mod.DEFAULT_MODEL,
            planning_xlsx=self.vars["planning_xlsx"].get().strip(),
            google_spreadsheet_id=self.vars["google_spreadsheet_id"].get().strip(),
            google_credentials_json=self.vars["google_credentials_json"].get().strip(),
            operation_options=self.existing_operation_options,
            manifest_template=self.vars["manifest_template"].get().strip(),
            output_dir=self.vars["output_dir"].get().strip(),
            delete_images_after_write=self.del_var.get(),
        ).normalized()
        settings_mod.save(s)
        self.on_save(s)
        self.top.destroy()


def main():
    root = Tk()
    try:
        ttk.Style().theme_use("vista")  # Windows'ta modern görünüm
    except Exception:
        pass
    ManifestoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
