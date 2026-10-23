# Balon Uçuş Planlama & Manifesto Sistemi — Proje Brief'i (Claude Code başlangıç)

> Claude Code proje belleği. Prose Türkçe, kod/değişken/alan adları İngilizce.
> Aşağıdaki brief orijinaldir; **güncel kararlar ve durum için en alttaki "Karar günlüğü & durum" bölümüne** bakın.

---

## 1. Amaç ve doğru iş akışı

Balon tur operasyonunda **asıl belge günlük uçuş planlama sayfasıdır**
("GENERAL BOOKING LIST" / "THK BALON SABAH UÇUŞU PLANLAMASI"), her tarih için bir sayfa.
**Manifesto bunun türevidir:** balon koduna göre filtrelenmiş 4 kolonluk export
(örn. `BZR.xlsx` = BZR balonunun manifestosu).

İki veri kaynağı tek planlama sayfasında birleşir:

1. **Operasyon/rezervasyon (insan girişi):** PAX, otel, pick-up, acente, balon ataması,
   pilot, şoför vb. Balonu **insan atar**, sistem değil.
2. **Pasaport kimliği (WhatsApp foto → MRZ):** sadece 4 kolon — UYRUK, M/F, İSİM, PASAPORT NO.

Sistemin otomatikleştirdiği şey: acentenin WhatsApp'tan attığı pasaport fotoğraflarını
okuyup **doğru rezervasyon satırlarının kimlik kolonlarını** doldurmak, operatör onayından
geçirmek ve gün sonunda **balon başına manifestoyu** üretmek. İnsan-onaylı (human-in-the-loop).

---

## 2. Planlama sayfası kolon haritası (master)

Her gün sayfası, başlık satırı (row 3) + rezervasyon blokları. PAX, bir rezervasyonun
ilk satırına yazılır; altındaki boş-PAX satırlar aynı rezervasyonun yolcularıdır.

| # | Kolon | Kaynak | Not |
|---|---|---|---|
| 1 | `PAX` | OPS | Rezervasyon grubu boyutu (lead satırda) |
| 2 | `UYRUK` | **PASAPORT** | 3 harf kod (ITA, CHN, MYS, RUS) |
| 3 | `M/F` | **PASAPORT** | MRZ sex |
| 4 | `REHBER & MÜŞTERİ İSMİ` | **PASAPORT** | MRZ ad+soyad, UPPERCASE |
| 5 | `İRTİBAT VE ODA NO` | OPS | |
| 6 | `OTEL` | OPS | |
| 7 | `PICK-UP` | OPS | Saat |
| 8 | `REZERVE YAPAN` | OPS | |
| 9 | `ACENTE` | OPS | Eşleştirme anahtarı (bkz §5) |
| 10 | `UÇACAĞI FİRMA` | OPS | THK |
| 11 | `BALON` | OPS | **Balon kodu** — manifesto filtresi (BYF/BTK/BYJ/BZR/BZV) |
| 12 | `PİLOT` | OPS | |
| 13 | `NOT` | OPS | |
| 14 | `ALIŞ ŞÖFÖR` | OPS | Şoför no (1–5) |
| 15 | `GELECEĞİ YER` | OPS | DİREKT ALAN vb. |
| 16–19 | (boş) | — | |
| 20 | `PASSAPORT NO` | **PASAPORT** | MRZ belge no, checksum'lı |

> Pasaport pipeline'ı YALNIZCA col 2, 3, 4, 20'yi doldurur. Diğer her şey operasyon girişidir.

`Sayfa2` = günlük kapasite/satış özeti (KAPASİTE 112, acente bazında satış). Bilgi amaçlı.

---

## 3. Manifesto türetme (downstream export)

Tek iş: bir gün + bir balon kodu için planlama satırlarını filtrele, 4 kolonu al,
iki dönüşüm uygula, `MANİFESTO` formatına yaz.

| Manifest alanı | Kaynak (planlama) | Dönüşüm |
|---|---|---|
| `AD SOYAD` | col 4 İSİM | aynen (UPPERCASE) |
| `CİNSİYET` | col 3 M/F | `M`→Erkek, `F`→Kadın |
| `UYRUK` | col 2 UYRUK | 3 harf kod → `ULKELER` İngilizce adı |
| `PASAPORT/KİMLİK NO` | col 20 | aynen |

Çıktı, mevcut manifest şablonunun `MANİFESTO` sayfasına yazılır; `ULKELER` açılır listesi
ve biçim korunur. Dosya balon koduyla adlandırılır (`BZR.xlsx`, `BYF.xlsx`, …).

---

## 4. country_map.json — iki yönlü

MRZ, uyruğu ISO 3166-1 alpha-3 verir. İki çıktıya da lazım:
- **Planlama (col 2):** MRZ kod → operasyonun kullandığı 3 harf kod (çoğu birebir: ITA, CHN…).
- **Manifesto (UYRUK):** 3 harf kod → `ULKELER` sayfasındaki İngilizce ad (ITA→Italy).

Tek tablo, iki alan: `{ "ITA": {"code":"ITA","name":"Italy"}, ... }`.
Bewo'nun `ULKELER` listesinden üretilecek (250 ülke).

---

## 5. Pasaport → planlama eşleştirme (akıllı gruplama)

Acente fotoğrafları gönderince sistem her pasaportu **doğru rezervasyon bloğuna** yerleştirmeli:
- Anahtar: `ACENTE` + rezervasyon (lead müşteri / mesaj başlığı).
- `PAX` checksum: rezervasyonun beklenen yolcu sayısı vs gelen pasaport sayısı.
- Eksikse / fazlaysa flag + (Faz 2) WhatsApp'tan otomatik geri-sor.

---

## 6. MRZ okuma katmanı

- Vision LLM ile MRZ satırlarını çıkar → **checksum doğrulamasını kodda** yap (deterministik).
- TD3 (pasaport, 2 satır) ve TD1 (kimlik, 3 satır) desteklensin.
- `M`/`F` → cinsiyet; alpha-3 → uyruk; belge no checksum'la doğrulanır.

---

## 7. Validation kapıları (flag)

`checksum_fail`, `expired` (son geçerlilik geçmiş), `duplicate` (aynı belge no),
`pax_mismatch` (PAX ≠ gelen yolcu), `unreadable` (MRZ okunamadı).

---

## 8. Kontrol ekranı (exception-based)

Solda görsel, sağda 4 alan. MRZ+checksum doğrulanan **yeşil**, şüpheli/flag'li **sarı**.
Operatör sadece sarıları gözden geçirir, onaylar → satır planlamaya yazılır.

---

## 9. WhatsApp entegrasyonu — notlar

- Gelen-ağırlıklı akış → 24 saatlik **ücretsiz servis penceresi**; eksik belgeyi bu pencerede
  otomatik geri sormak Meta tarafına ≈ ücretsiz.
- **Numara tuzağı:** Cloud API numarası normal WhatsApp uygulamasında açık olamaz → yeni numara.
- `media_id` → geçici medya URL → indir → işle.
- Resmi Cloud API. Gayriresmi kütüphane yok.

---

## 10. KVKK / saklama

İzin acente üzerinden var; yine de: manifesto kesinleşince ham görselleri otomatik sil
(veya X gün), sadece metin alanları kalsın, `AuditLog` (kim-ne-zaman-onayladı), erişim kısıtlı.

---

## 11. Teknik yığın

- Backend: Python + FastAPI. DB: SQLite → Postgres. xlsx: openpyxl (biçim+dropdown korunur).
- MRZ: vision LLM + kod tarafı checksum (yedek: fastmrz/PassportEye).
- Frontend: sade web panel (HTMX veya küçük React/Vite).
- WhatsApp: Meta Cloud API.

---

## 12. AÇIK SORULAR — build öncesi netleştir

1. **Planlama sayfası nerede yaşayacak?** (EN ÖNEMLİ MİMARİ KARAR)
   (a) Excel'de kalır, sistem sadece kimlik kolonlarını doldurup geri yazar; ya da
   (b) planlama tamamen uygulama DB'sine taşınır, Excel sadece import/export olur.
2. `col 5/6` bazı satırlarda otel yerine isim içeriyor (ör. "MUSTAFA") — ne demek?
3. `ALIŞ ŞÖFÖR` 1–5 = şoför numarası mı, başka bir gruplama mı?
4. İsim çakışırsa esas hangisi: pasaporttan okunan mı, acente booking'indeki mi?
5. Sayfa2'deki "65" kişi başı fiyat mı (rapor için lazım mı, yoksa kapsam dışı mı)?

---

## 13. Faz planı

**MVP (Faz 1):**
- Vision LLM ile MRZ çıkarımı + checksum.
- `country_map.json` üretimi.
- 4 kimlik alanını çıkarma; elle yüklenen test görselleriyle uçtan uca.
- Kontrol ekranı (yeşil/sarı, onay).
- Onaylı yolcuları planlama satırlarına yazma + manifesto export (balon koduna göre).
- Flag'ler: checksum_fail, duplicate, expired.

**Faz 2:** Pasaport→rezervasyon eşleştirme (acente+PAX checksum), WhatsApp ingest +
geri-besleme döngüsü, caption parsing.

**Faz 3:** Operasyon paneli (Gelenler / İşlenenler / Kontrol gerekli / Manifestoya yazıldı /
Hatalı-eksik), acente bazlı eksik görünümü, kapasite (Sayfa2) entegrasyonu.

---

## 14. Claude Code — ilk görevler (sırayla)

1. Repo iskeleti: FastAPI + SQLite + frontend klasörü.
2. `country_map.json` üret (ULKELER → ISO alpha-3 + İngilizce ad).
3. `mrz_parser.py` — TD3/TD1 parse + checksum.
4. Vision LLM çağrısı: görsel → MRZ satırları → parser → 4 alan.
5. Manifesto writer (openpyxl): balon koduna göre filtre + 2 dönüşüm + şablona yazım.
6. Kontrol ekranı (yeşil/sarı, onay).
7. (En son) WhatsApp webhook + medya indirme.

> Sıra mantığı: önce 1–5 ile WhatsApp OLMADAN, elle yüklenen test görselleriyle
> "görsel → 4 alan → manifesto" hattını uçtan uca çalıştır. WhatsApp en sona, girdi kanalı olarak eklenir.

---

## 15. Karar günlüğü & durum (2026-06-22)

### Alınan kararlar
- **§12.1 mimari → HİBRİT (Excel kaynak kalır).** Sistem planlama xlsx'ini okur, yalnızca
  4 kimlik kolonunu (col 2/3/4/20) geri yazar, manifestoyu export eder. SQLite yalnızca
  pasaport çıkarımı + flag + audit tutar; planlama sayfasını tutmaz.
- **Vision sağlayıcı → Claude** (en güncel vision modeli). Model SADECE MRZ satırlarını OCR
  eder; checksum doğrulaması kodda (`app/mrz`) deterministik yapılır.

### Gerçek veriyle doğrulanan / cevaplanan açık sorular
- **Golden pair:** `Downloads/BZR.xlsx`, `Downloads/HAZİRAN AYI UÇUŞ PLANLAMASI 2026.xlsx`
  içindeki **22.06.2026** sayfasının `BALON=BZR` 28 satırının birebir türevi (aynı isim/
  pasaport/uyruk, aynı sıra). `test_manifest_golden.py` bunu doğrular.
- Planlama kolon haritası birebir doğru: header **row 3**, veri row 4+, `PASSAPORT NO` **col 20**.
  Uyruk kodları temiz ISO-3.
- **§12.3 `ALIŞ ŞÖFÖR`** = pickup aracı/şoför no; rezervasyonları araç bazında gruplar.
- **§12.5 "65"** = kişi başı fiyat; `Sayfa2` son kolon = ciro; `Sayfa2` bilgi amaçlı, güne göre
  güncellenmiyor.
- **§12.2 `col5/6`**: col6 = OTEL, col5 = İRTİBAT VE ODA NO (ör. "ODA 202").
- **§12.4 isim çakışması**: kolon haritasına göre isim kaynağı PASAPORT → manifestoda
  pasaporttan okunan isim esas; booking ismi yalnızca eşleştirme anahtarı.

### Bilinen veri sorunu (kaynakta düzeltilmeli)
- **`ULKELER` sayfasında "India" satırı BOŞ** (Iceland ile Indonesia arası). `country_map.json`'a
  `IND → India` elle eklendi; ama manifesto dropdown'ı (varsa) India'yı içermez. Kaynak
  `ULKELER` listesine "India" eklenmeli.
- BZR.xlsx'te MANİFESTO sayfasında **data validation (dropdown) yok**; biçim = bold header +
  sabit kolon genişlikleri. Writer şablonu yükleyip yalnız hücre değeri yazar (biçim korunur).

### Tamamlanan (Faz 1 deterministik çekirdek)
- `app/mrz` TD3/TD1 parse + ICAO 9303 checksum (referans örnekleriyle test).
- `scripts/build_country_map.py` → `data/country_map.json`.
- `app/manifest/writer.py` filtre + 2 dönüşüm + şablona yazım; golden pair testi.
- `app/validation/flags.py` (checksum_fail, expired, duplicate, pax_mismatch, unreadable).
- `app/db.py` SQLite şema; `app/main.py` FastAPI iskeleti (health + manifest preview/export).

### Karar revizyonu (2026-06-22) — operatör akışı + otomatik balon atama
- **§12.1/§15 "balonu insan atar" REVİZE:** Balon atamasını artık **sistem otomatik** yapar
  (kullanıcı onayı). Bir rezervasyonun tüm yolcuları **aynı balona** (grup bölünmez); balon
  doluysa (kapasite **28**, Settings'ten değiştirilir) **tüm grup** yer olan başka balona —
  `first-fit`. Hiçbiri sığmazsa en boş balona + `overflow` uyarısı.
  - `app/manifest/planning.py`: `balloon_load`, `assign_balloon`, `pilot_for_balloon`,
    `next_free_row`, `create_reservation` (boş satıra append; lider-gösterim kolonları
    A/F/G/H/I/M `config.LEAD_MERGE_COLS` yeniden birleştirilir — kaynak günden miras birleşmeler
    çözülür). Test: `tests/test_assign_balloon.py`.
  - `app/main.py`: `POST /api/planning/create-block`; `/api/planning/load` → `balloon_load`+`capacity`.
  - `app/settings.py`: `balloon_capacity` (28), `balloon_codes` (BYF/BTK/BYJ/BZR/BZV).
- **Akış düzeltmesi (pasaport-merkezli):** Rezervasyon, pasaport girilirken **o an açılır**.
  Pasaport ekranı: Uçuş Günü + **PAX** (pasaport sayısına göre otomatik, düzenlenebilir) + Otel +
  Acente; "Rezervasyon Oluştur & Yaz" → `create-block` (balon otomatik) sonra `write-identity`.
  Önce blok seçme akışı kaldırıldı (aykırıydı). **Pickup ve kaptan rezervasyonda YOK** — en son,
  rota belli olunca Planlama'nın operasyon-düzenleme formundan girilir. **Clipboard paste**
  (WhatsApp → Ctrl+V) pasaport ekranında.
- **Araç (kaptan) kuralı:** araç başına max **16** kişi (`config.VEHICLE_CAPACITY`); kaptan ataması
  şimdilik **manuel** (pasaport ekranı). Kaptan otomatik atama + 16 zorlaması sonraki faz.
- **Manifesto "yapamıyorum" kök neden:** planlama yolu uzantısızdı; kodda bug yoktu.
- **Kalıcı "Listeler" (📚):** balon kodları + otel/şoför/acente/pilot/geleceği yer Settings'te
  saklanır (`balloon_codes`, `operation_options`). `frontend/pages/lists.js` ekle/sil UI;
  `GET/POST /api/lists`, `/api/lists/add|delete`. Rezervasyon & pasaport formları datalist ile
  öneri verir; formda yazılan yeni değer `_remember_values` ile otomatik öğrenilir. Test:
  `tests/test_lists.py`. **Kaptan/şoför = rota bazlı, en son adım** (şimdilik isim listesi tutulur).
- **Combobox + uyruk otomatik tamamlama:** `frontend/combobox.js` (singleton, body'e fixed panel —
  kartların `overflow:hidden`'ı kırpmaz). Uyruk alanı `GET /api/countries` (country_map'ten 250
  alpha-3 kod+ad) ile yaz-filtrele; TUR→Türkiye zaten country_map'te. Otel/acente alanları kayıtlı
  Listeler'den combobox ile seçilir (datalist görünmüyordu → combobox). Pasaport kartında cinsiyet
  **Erkek/Kadın** (değer M/F; manifesto SEX_TR ile zaten Türkçe).

### Sıradaki (yapılmadı)
- Vision LLM çağrısı: görsel → MRZ satırları → parser (Claude).
- Kontrol ekranı (yeşil/sarı onay) — `frontend/`.
- Kaptan otomatik atama + 16 kişi araç kapasite zorlaması; blok rebalance.
- Faz 2: pasaport→rezervasyon eşleştirme + WhatsApp ingest.

### Karar günlüğü (2026-10-22) — doğrulama ve veri kaynağı
- **Sunucu OCR sonucu kodda doğrulanır (brief §6 zorunlu):** `irtifa_client._verify_against_local_mrz`
  sunucunun `raw_text`inden MRZ satırlarını çıkarıp `app/mrz` ile check digit doğrular; ayrıca
  `server_document_match` (sunucu belge no == MRZ belge no). MRZ bulunamazsa `checks` boş kalır.
- **Boş `checks` asla yeşil değil:** `MRZResult.checks_ok` boş sözlükte False; `validate_mrz` boş
  `checks` için `FREE_TEXT_UNVERIFIED` (sarı), dolu-ama-hatalı için `CHECKSUM_FAIL` verir.
- **Okuma yolunda tek kaynak Excel:** `/api/planning/load` ve `manifest.writer.build_rows` artık
  SQLite aynasını tercih etmez; her zaman planlama xlsx okunur. SQLite yalnız arka planda
  güncellenen ayna + pasaport çıkarımı/audit. (Dışarıdan düzenlenen Excel eski DB kopyasıyla
  gölgeleniyordu.) `load_blocks_from_sqlite` / `build_planning_rows_from_sqlite` kullanılmıyor.
- Not: "Sıradaki" listesindeki Vision çağrısı ve kontrol ekranı aslında yapılmıştı; güncel durum
  için git log ve `tests/` esas alınmalı.
- **Planlama veri bütünlüğü:** `create_reservation` artık `next_free_rows(ws, pax)` ile PAX kadar
  ardışık boş satır arar (tek satırlık boşluk 3 kişilik bloğa verilmez; sonraki bloğun üzerine
  yazma bitti). `reorder_reservation` hedefi `_is_block_boundary` ile doğrular (blok ortası → 422)
  ve `insert_rows`/`delete_rows` çevresinde birleşik hücreleri `_detach_merges`/`_reattach_merges`
  ile kaydırır (openpyxl birleşmeleri taşımaz; diğer blokların PAX/otel birleşmeleri kayıyordu).

### Uygulama (2026-10-23) — OcrProvider arayüzü + claude_direct (mimari v2, PR 1+2)
- `app/vision/providers/`: `OcrResult` + `OcrProvider` protokolü (`base.py`), sunucu sarıcı
  (`irtifa_server.py`), doğrudan Claude (`claude_direct.py`, yalnız-MRZ prompt, `output_config.format`
  yapılandırılmış çıktı; zorunlu `tool_choice` güncel modellerde 400 olduğu için kullanılmıyor).
- `to_mrz()` sağlayıcıdan bağımsız doğrulama: boş checks asla yeşil; belge no ≠ MRZ → CHECKSUM_FAIL;
  expired/duplicate yerel. `extractor.process_image` sağlayıcıyı `vision_mode`dan seçer
  (`make_provider`), `ocr_provider=` ile enjekte edilebilir; `client=` eski çok-yolcu yol (test/dev).
- `vision_mode`: `irtifa_server` (varsayılan, değişmedi) | `claude_direct` | `manual`; eski `claude`→
  `claude_direct`, `google_vision`→`irtifa_server`. Modeller `claude-sonnet-5-5` / `claude-opus-5-5`.
- Ayarlar > OCR: sağlayıcı seçimi, Claude API anahtarı (DPAPI) + model, "Anahtarı Doğrula".
  `/api/app/status` claude_direct modunda lisans = API anahtarı var mı.
- Sözleşme testleri: `tests/contract/fixtures/*.json` tek doğruluk kaynağı; ileride `server/` aynı
  fixture'larla test edilir. Varsayılanı `claude_direct`e çevirmek PR 4 (benchmark sonrası).
- **Sözleşme çok yolculu (2026-10-23, saha örnekleri sonrası):** gerçek girdilerin çoğu MRZ'siz (el yazısı/basılı
  listeler, kimlik ön yüzleri, WhatsApp rezervasyon mesajı; listelerde ✓/fosfor/B/sıra no/SI işaretleri uçanı
  gösteriyor, acenteye göre değişir). `OcrResult.kind` + `group` (tarih/otel/acente/pax/uyruk ipucu) +
  `passengers[]` (format, lines, fields, confidence, annotation, selected); `to_records()` her satırı ayrı
  kayıt yapar, MRZ varsa checksum (yeşil mümkün), yoksa alanlar + FREE_TEXT_UNVERIFIED (sarı). İşaretler
  yorumlanmaz, `annotation` olarak taşınır; kural seçimi UI'da (liste bazında, acenteye kaydedilir) — sıradaki.
  Görsel ön işleme `providers/image_prep.py` (EXIF yön + 2000 px). Benchmark seti: `%USERPROFILE%\Irtifa-benchmark\`.

### Koltuk şablonu (2026-10-23, gerçek Ekim planlaması sonrası)
- Arkadaşın gerçek gün sayfası 112 satırı önceden balonlara dağıtır: balon başına 28 satırlık ardışık
  bant, boş koltukta firma/balon/pilot (bazen geleceği yer/şoför) dolu, isim/pasaport/PAX boş.
- `PlanningRow.is_seat` = balon var, isim/pasaport/PAX yok. `group_blocks` boş koltuğu bloğa yalnız PAX
  dolmadıysa ve aynı balondaysa katar; aksi hâlde serbest koltuktur. Manifesto (`writer.build_rows`)
  yalnız isim ya da pasaport no'su olan satırları yazar.
- `free_seat_runs` / `free_seat_summary`: balon → ardışık serbest koltuk dizileri; `/api/planning/load`
  `free_seats` döner. `choose_balloon`: önce istenen, sonra `balloon_codes` sırası, ≥ PAX ardışık koltuğu
  olan ilk balon ("seat"); koltuk şablonunda yer yoksa overflow (onayla şablonun altına eklenir);
  ekleme şablonunda eski first-fit ("append"). `is_seat_template`: serbest koltuğu olan bir balonun
  sayfada ≥ kapasite satırı var.
- Silme/küçültme/yolcu silme `_clear_row` ile firma/balon/pilot/geleceği yer'i KORUR → satır o balonun
  serbest koltuğu olarak kalır (başka balonun grubu oraya yazılmaz).
- Test: `tests/fixtures/seat_template_ekim.xlsx` gerçek dosyanın PII'siz kopyası (21/22/23 Ekim; isim,
  pasaport, otel, acente, pilot, oda, not maskeli). Gerçek planlama dosyaları repoya konmaz.

### Arayüz yeniden tasarımı (2026-10-24) — "Kısık Tüf"
- Kullanıcı: gündüz ofiste bilgisayarda; turuncu ve cam/parlama istemiyor; bembeyaz zemin göz yoruyor;
  Kapadokya "belirgin ama sakin". Ürün bilgisi `PRODUCT.md`te.
- **İki tema, aynı bileşenler:** `:root` = Kısık Tüf (taş grisi #d9d4cc zemin, #e4e0d9 panel, kömür #2e2b28
  metin, tek vurgu soluk lapis #3d5a8a; saf beyaz yok), `[data-theme="graphite"]` = Yumuşak Grafit.
  Seçim bilgisayar başına `localStorage('irtifa-theme')` (pywebview kalıcı depolama); Ayarlar > Görünüm ve
  menüdeki yarım daire düğmesi. `index.html` ilk boyamadan önce uygular.
- **Token sistemi:** `tailwind.config.js` renkleri `rgb(var(--x) / <alpha-value>)`; değerler `style.css`
  başında. Eski token adları (surface, on-surface, primary, tertiary…) korunur → sayfalar otomatik uyar.
- **Biçim dili (kullanıcının beğendiği üç yönün birleşimi):** balon başına sabit zarf mürekkebi
  (`env-1…env-8`; `app.js` `balloonInk/balloonBadge/envStripe`, sıra Ayarlar'daki balon kodlarından),
  kapı panosu tablosu (`.board`, dar ekranda kolonlar önceliğe göre düşer), segmentli biniş kartı (`.pass`),
  sabah uçuş bayrağı (`.flag-strip`; hava tavsiyesidir, resmî izin değildir).
- Ana sayfa (`pages/dashboard.js`) baştan yazıldı: bayrak · gün başlığı · bugün yapılacaklar + 4 metrik ·
  balon panosu (değişen satır `localStorage` anlık görüntüsüyle işaretli) · seçili balonun kartı.
- Yazı tipleri yerel: Source Serif 4 (başlık), Source Sans 3 (metin), JetBrains Mono (kod/belge no).
  Plus Jakarta / Bricolage ve 3D ikon seti (`icons.js`) kaldırıldı; menü Material Symbols çizgi ikonları.
- Hata düzeltmesi: `index.html` `app.js?v=N` yüklüyordu, sayfalar `/app.js` → derlemede iki modül kopyası
  (kullanıcı/sürüm bilgisi kayboluyordu). Artık sorgu eki yok.
- Dar ekranda menü üstten açılır (`__toggleNav`). Tasarım kararları ve tasarım sistemi: `DESIGN.md`.

### Takvim doluluğu (2026-10-24)
- `GET /api/planning/month-load?month=YYYY-AA` → gün (`GG.AA.YYYY`) → `{used, free, total}`; hesap
  `planning.month_load/day_seat_load` (`balloon_load` + `free_seat_summary`, kitap bir kez açılır).
  Toplam: koltuk şablonunda sayfadaki koltuklar (dolu + serbest); ekleme şablonunda kapasite ×
  (Ayarlar kodları ∪ sayfadaki balonlar).
- Önbellek `main._MONTH_LOAD_CACHE`, anahtar (dosya, ay, `workbook_revision`, kapasite, kodlar); Excel
  değişince revizyon değişir, kaynak yine Excel. Yanıtta `cached`. Google Sheets modunda her indirme
  yeni mtime → önbellek isabet etmez (bilinen sınır).
- Takvim (`pages/planning.js`): plan günlerinin altında `.seat-bar.day-load` (lapis; aşımda tuğla;
  zarf mürekkebi değil — Envelope Rule). İstemci, ay verisini `state.revision` değişene dek yeniden istemez.
  Bugün lapis çerçeveli.

### Kapasite kuralları (2026-10-24, backend)
- **Balon başına kapasite:** planlama fonksiyonları `capacity: int | Callable[[kod], int]` alır
  (`planning.capacity_fn`); main `Settings.capacity_for` geçirir. Koltuk modunda da balon yükü + PAX
  kapasiteyi aşamaz. Bant tespiti (`_is_seat_layout_rows`) varsayılan kapasiteyle kalır.
- **Günlük balon sınırı:** `daily_max_balloons > 0` ve yolcu taşıyan balon sayısı sınıra ulaştıysa
  `choose_balloon(allowed=uçan balonlar)`; sığmazsa 409 `capacity_confirmation_required` + "Günlük balon
  sınırı (N) dolu…" mesajı. `allow_overflow`+`requested_balloon` yeni balona izin verir; readiness
  `daily_balloon_limit` ile işaretler.
- **Acente kotası:** create-block / create-with-identities, kapasiteden ÖNCE; aşımda 409
  `agency_quota_exceeded` (`allow_quota_override` ile geçilir). Acente adları `settings.fold_agency`
  ile katlanır (İ/ı→I, Ş→S, Ğ→G, Ü→U, Ö→O, Ç→C, büyük harf, tek boşluk); `agency_quotas` anahtarları
  katlanmış saklanır.
- Readiness: `lead_row` taşıyan her uyarıda `lead_name`; mesajlar "Satır 83 · AD SOYAD: …".
  `/api/planning/load` → `capacities`, `daily_max_balloons`, `balloons_in_use`, `agency_usage`.
  Test: `tests/test_capacity_rules.py`.

### Otel gruplaması (2026-10-24, backend)
- Aynı otelin yolcuları aynı balona (pickup kolaylığı). `choose_balloon(..., hotel=)` ve
  `assign_balloon(..., hotel=, blocks=)`: otelin yolcularını zaten taşıyan balonlar (o otelden çok
  koltuktan aza, `hotel_seats_by_balloon`) `requested`'tan sonra, `codes` sırasından önce denenir.
  Kapasite (balon başına), günlük balon sınırı (`allowed`) ve koltuk modunda ≥ PAX ardışık koltuk
  kuralları aynen geçerli; sığmazsa eski davranış. Dönüşte `hotel_match`.
- Ad karşılaştırması ortak `app/textfold.fold_name` (acente kotası `fold_agency` de onu kullanır).
- create-block / create-with-identities lider otelini geçirir; yanıtta `hotel_match`, mesajda
  "… X otelinin diğer yolcularıyla aynı balona (KOD) atandı." (create-with-identities artık `message` döner).
- `/api/planning/load` → `hotel_split` [{hotel, balloons, seats}]: 2+ balona dağılmış oteller, öneri;
  readiness uyarısı DEĞİL (çıktıyı engellemez). Test: `tests/test_hotel_grouping.py`.
