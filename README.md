# Balon Uçuş Planlama & Manifesto Sistemi

Acentelerin WhatsApp'tan attığı pasaport fotoğraflarını okuyup (MRZ → 4 kimlik alanı),
operatör onayından geçirip günlük planlama sayfasının kimlik kolonlarını dolduran ve
**balon başına manifestoyu** üreten insan-onaylı (human-in-the-loop) sistem.

Tam brief ve karar günlüğü: [`CLAUDE.md`](CLAUDE.md).

## Mimari kararı (§12.1)

**Hibrit — Excel kaynak kalır.** Sistem planlama xlsx'ini okur, yalnızca 4 kimlik
kolonunu (`UYRUK / M/F / İSİM / PASAPORT NO`) geri yazar ve manifestoyu export eder.
SQLite yalnızca pasaport çıkarımı + flag + audit tutar; planlama sayfasını **tutmaz**.

## Kurulum

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

## Üretilen artefaktlar (bir kez)

```bash
# ULKELER -> country_map.json  (ISO alpha-3 + İngilizce ad)
python -m scripts.build_country_map --source "%USERPROFILE%\Downloads\BZR.xlsx"

# Dolu BZR.xlsx'ten PII'siz manifesto şablonu
python -m scripts.make_manifest_template --source "%USERPROFILE%\Downloads\BZR.xlsx"
```

## Manifesto üretimi (CLI)

```bash
python -m scripts.export_manifest --date 22.06.2026 --balloon BZR --out-dir .
```

## API

```bash
uvicorn app.main:app --reload
# GET /health
# GET /manifest/preview?date=22.06.2026&balloon=BZR
# GET /manifest/export?date=22.06.2026&balloon=BZR   -> BZR.xlsx indirir
```

## Test

```bash
pytest
```

`test_manifest_golden.py` **golden pair** doğrulaması yapar: 22.06 planlama sayfasının
`BALON=BZR` satırlarından üretilen manifesto, gerçek `BZR.xlsx` ile birebir eşleşmelidir.
PII kaynak dosyalar yoksa ilgili testler atlanır (skip).

## Yapı

```
app/
  config.py            yollar + planlama/manifesto kolon haritası
  mrz/                 TD3/TD1 parse + ICAO 9303 checksum
  country/             country_map.json yükleyici
  manifest/            planlama okuma/geri-yazma + manifesto writer
  validation/          flag kapıları (checksum_fail, expired, duplicate, pax_mismatch)
  db.py                SQLite (passport_extraction, audit_log)
  main.py              FastAPI iskeleti
scripts/               country_map / şablon / export CLI
tests/                 MRZ + country_map + golden pair
```

## Yol haritası

- **Faz 1 (bu çekirdek):** country_map, MRZ parser+checksum, manifesto writer, golden test, flag'ler. ✅
- **Faz 1 kalan:** Vision LLM çağrısı (görsel → MRZ satırları), kontrol ekranı (yeşil/sarı onay).
- **Faz 2:** pasaport→rezervasyon eşleştirme (acente + PAX checksum), WhatsApp ingest.
- **Faz 3:** operasyon paneli, kapasite (Sayfa2) entegrasyonu.

> Vision katmanı, MRZ satırlarını çıkarmak için Claude (en güncel vision modeli) kullanacak;
> **checksum doğrulaması kodda** (`app/mrz`) deterministik yapılır — model yalnızca OCR eder.

## Son Güncellemeler (23.06.2026)

- **Aetheria Tasarım Dili (Tailwind CSS):** Vanilla CSS'ten (`style.css` - 1700 satır) tamamen modern **Tailwind CSS v3** altyapısına geçildi. Yeni "Sıcak Kehribar (Warm Amber) & Gün Batımı" renk paleti (Material Design 3) entegre edildi. Bütün sayfalar (`dashboard`, `planning`, `passport`, `manifest`, `weather`, `lists`, `settings`) "glass-panel" bileşenleri, `Material Symbols Outlined` ikonları ve akıcı animasyonlarla baştan aşağı yenilendi.
- **Hata Çözümleri & İşlevsellik:**
  - Planlama (planning.js/planning.py) ekranında aynı rezervasyona ait birden fazla pasaportun kaydedilememesi/görünmemesi (Excel okuma `read_only=True` sınırları kaynaklı) sorunu çözüldü (`read_only=False`).
  - Pasaport yükleme ekranında PAX sayısının, kaydedilen yolcu sayısı kadar otomatik artırılması sağlandı.
  - Hava durumu (weather.js) kartlarındaki saat aralığı, yerel operasyonel gereksinimlere uyacak şekilde **her gün 03:30 - 07:30** arası uçuş slotlarını içerecek biçimde daraltıldı.
- **Build & Yayın:** Vite üzerinden frontend build optimizasyonu (`dist` kütüphanesi güncellendi) yapıldı. Desktop versiyonu olan `BalonManifesto.exe`, PyInstaller kullanılarak başarılı bir şekilde güncellendi. Tüm değişiklikler GitHub repository'sine eklendi.
