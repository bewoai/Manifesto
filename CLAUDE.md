# Manifesto (Irtifa)

Kapadokya balon firmaları için uçuş planlama + manifesto sistemi: WhatsApp'tan gelen pasaport/kimlik görsellerini OCR ile okur, planlama Excel'ine kimlik kolonlarını yazar, balon başına manifesto ve şoför listeleri üretir. Windows masaüstü (`Irtifa.exe`) + yerel web arayüzü.

Prose Türkçe; kod, değişken ve alan adları İngilizce.
Tam brief, kolon haritası ve karar günlüğü: `docs/proje-brief.md` (gerektiğinde ilgili bölümü oku; yeni kararları oraya ekle). `AGENTS.md` aynı brief'in Codex için eski kopyasıdır.

## Komutlar
```bash
pip install -r requirements.txt              # .venv önerilir
python desktop_launcher.py                   # masaüstü uygulaması (pywebview)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000   # yalnız API + web arayüzü
pytest                                       # tests/ (pytest.ini)
cd frontend && npm install && npm run build  # Vite + Tailwind arayüz derlemesi
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1 -Clean   # frontend + PyInstaller + smoke test -> dist/Irtifa.exe
```

## Yapı
- `app/main.py`: FastAPI; `app/manifest/` (planlama okuma, balon atama, manifesto yazımı), `app/mrz/` (TD3/TD1 parse + ICAO 9303 checksum), `app/vision/providers/` (OcrProvider: `irtifa_server`, `claude_direct`, `manual`), `app/validation/flags.py`
- `app/excel_store.py`, `db.py` (SQLite ayna + audit), `settings.py`, `secret_store.py` (DPAPI), `updater.py` (imzalı güncelleme), `reports.py` (şoför PDF), `weather.py`
- `frontend/`: vanilla JS sayfaları (`pages/`), `combobox.js`; `data/country_map.json` (`scripts/build_country_map.py` üretir)
- `tests/contract/fixtures/*.json`: OCR sözleşmesinin tek doğruluk kaynağı; `test_manifest_golden.py` gerçek golden pair'i doğrular

## Değişmez kurallar
- Excel planlama dosyası tek veri kaynağı; sistem yalnız kimlik kolonlarını (UYRUK, M/F, İSİM, PASAPORT NO; col 2/3/4/20) yazar. SQLite yalnız ayna + pasaport çıkarımı + audit.
- Model yalnız OCR yapar; MRZ checksum doğrulaması kodda, deterministik. Boş `checks` asla yeşil değil (`FREE_TEXT_UNVERIFIED`).
- Rezervasyon grubu bölünmez; balon kapasitesi ve kodları Settings'ten gelir, koda gömülmez.
- openpyxl birleşik hücreleri taşımaz: satır ekle/sil yaparken `_detach_merges`/`_reattach_merges` kullan.
- KVKK: pasaport görselleri işlem sonrası silinir; gerçek pasaport verisi, görsel veya API anahtarı repoya girmez.
- Davranış değiştiren her iş için test ekle; `pytest` yeşil olmadan bitti sayma.
