# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

İrtifa bir masaüstü uygulamasıdır: FastAPI sunucusu yerelde çalışır, arayüz pywebview (Edge WebView2)
penceresinde açılır. Tasarım dili web'dir; aynı arayüz tarayıcıda da açılabilir.

## Users

- **Birincil kullanıcı:** Kapadokya'da sıcak hava balonu işletmesinin operasyon sorumlusu (Bewo'nun arkadaşı).
  Uygulamayı **gündüz, ofiste, bilgisayarda** kullanır (2026-10-24, kullanıcı cevabı).
- İş: ertesi sabahın uçuşunu hazırlamak. Acentelerden WhatsApp ile gelen pasaport fotoğrafları,
  el yazısı/basılı yolcu listeleri ve rezervasyon mesajlarını okutup planlama Excel'ine yazmak,
  balonlara dağıtmak, gün sonunda balon başına manifesto ve şoför listelerini üretmek.
- İkincil: aynı işi yapan diğer balon işletmeleri (ürün satılabilir hâle getirilmek isteniyor).

## Product Purpose

Pasaport/liste görsellerinden kimlik alanlarını (uyruk, cinsiyet, ad soyad, pasaport/kimlik no) okuyup
günlük uçuş planlama Excel'ine yazmak ve balon başına manifestoyu üretmek. İnsan onaylı: MRZ checksum'ı
doğrulanan kayıt yeşil, doğrulanamayan her kayıt sarı; operatör yalnız sarıları gözden geçirir.
Başarı: gün sonu manifestoları eksiksiz, hatasız ve hızlı çıkar; operatör Excel'e elle yazmaz.

## Positioning

Arkadaşın mevcut Excel planlama dosyası kaynak olarak kalır (koltuk şablonu, 28 kişilik balon bantları,
şoför numaraları korunur); uygulama onun üzerine çalışır, yerine geçmez. Kimlik doğrulaması kodda,
deterministik (ICAO 9303 checksum); OCR modeli yalnız okur.

## Operating Context

- Günlük planlama Excel'i: her tarih bir sayfa, 112 koltuk (BYF/BTK/BYJ/BZR/BZV balonları, balon başına 28).
- Girdi: WhatsApp'tan gelen görseller (pasaport, kimlik ön yüzü, el yazısı/basılı liste, ekran görüntüsü);
  listelerde uçanı gösteren işaretler (✓, fosfor, sıra no, "SI") acenteye göre değişir.
- Çıktı: balon başına manifesto xlsx (MANİFESTO + ULKELER sayfaları), şoför listeleri (PDF+xlsx),
  araç özeti, hepsi tek ZIP; gün klasörüne kaydedilir ve WhatsApp/Drive ile gönderilir.
- Ekranlar: Ana sayfa, Pasaport (okut ve yaz), Liste inceleme, Planlama (gün takvimi + bloklar),
  Manifesto (önizleme + uyarıdan düzeltme + gün sonu çıktıları), Listeler, Hava durumu, Ayarlar, Yönetici.

## Capabilities and Constraints

- Excel tek doğruluk kaynağı; SQLite yalnız ayna, pasaport çıkarımı ve audit.
- Çevrimdışı çalışmalı: yazı tipleri ve ikonlar yerel (`frontend/public/fonts`).
- Stack: vanilla JS (ES modülleri) + Tailwind + Vite; sayfalar `frontend/pages/*.js` içinde string şablonla çizilir.
- Durum renkleri anlamlıdır ve korunur: yeşil = doğrulandı, sarı = kontrol gerekli, kırmızı = hata.
- Repo public: gerçek planlama dosyaları ve yolcu verisi (PII) repoya konmaz.

## Brand Commitments

- Ad: **İrtifa**. Dil: Türkçe arayüz; teknik terimler (PAX, MRZ, OCR) olduğu gibi.
- Kapadokya kimliği **belirgin ama sakin** hissedilmeli; işi gölgelememeli (2026-10-24).
- Bewo'nun bağlayıcı tercihleri: **turuncu/amber vurgu yok**, **cam/blur/parlama/glow/gradyan yok**,
  neon yok; menü öğeleri çerçevesiz düz satırlar; ana sayfa önce "bugün ne yapmalıyım" + 3-4 metrik.

## Evidence on Hand

- PII'siz test planlaması: `tests/fixtures/seat_template_ekim.xlsx` (21/22/23 Ekim, maskeli isimler).
- Gerçek saha görselleri repoda yok (benchmark seti `%USERPROFILE%\Irtifa-benchmark\`, yerel).
- Müşteri referansı, fiyat veya kullanıcı sayısı yok; uydurulmaz.

## Product Principles

1. Operatörün dikkati yalnız istisnalara gider: doğrulanmış olan sessiz, kontrol gereken belirgin.
2. Excel'deki düzen bozulmaz; uygulama arkadaşın çalışma biçimine uyar.
3. Her uyarı, tek tıkla düzeltilebildiği yerde gösterilir.
4. Gün sonu çıktısı tek adımda ve nereye kaydedildiği açıkça bilinerek alınır.
