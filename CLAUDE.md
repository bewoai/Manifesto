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
