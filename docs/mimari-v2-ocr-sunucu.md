# Mimari v2 — OCR ve sunucu katmanı tasarım belgesi

> Durum: **taslak / karar bekliyor** · Tarih: 2026-10-23 · Kapsam: yalnızca OCR + lisans/sunucu katmanı.
> Kod değişikliği içermez. PR #1 (`fix/security-cleanup`) üzerine kurulur, ona dokunmaz.
> Prose Türkçe; kod, alan ve dosya adları İngilizce.

---

## 0. Özet (TL;DR)

- Bugün üretimde her pasaport görseli, kodu **elimizde olmayan** bir Cloud Run sunucusuna (`irtifa-ocr-server`, europe-west1) gidiyor. Sunucu Google Vision + Claude kullanıyor; lisans ve paket mantığı orada. Tek müşteri için bu katman güvenlik değil **risk** üretiyor: kayıp kod, görünmeyen fatura, Bewo'ya bağlı tek hata noktası.
- Operatör başına günde 120 görsel ve 7 aylık sezon varsayımıyla OCR'ın **ham maliyeti ayda 1–25 $ bandında**. Maliyet karar kriteri değil; **operasyon yükü ve kontrol** karar kriteri.
- **Öneri: Seçenek (a) "sunucusuz" — şimdi.** OCR doğrudan Claude'a (Sonnet 5.5, sonra benchmark'a göre Haiku 5.5), anahtar müşteri cihazında DPAPI'de, Anthropic konsolunda harcama tavanı. Mevcut sunucu istemcisi silinmez; aynı JSON sözleşmesini uygulayan bir "provider" olarak kalır.
- **Seçenek (b) ince proxy, ikinci firma imza attığında** açılır; sözleşmesi (endpoint, başlıklar, hata kodları, lisans tablosu) bu belgede **şimdi donduruluyor** ki o gün istemcide tek satır değişsin.
- **Seçenek (c) yerel Tesseract: hayır.** Aylık 1 $'lık tasarruf için exe'ye ~50 MB binary, ön-işleme ve %80 civarı okuma oranı almaya değmez.

---

## 1. Mevcut akış ve sorunları

### 1.1 Şema (bugün, v1.2.0 + PR #1)

```
Operatör (Irtifa.exe, pywebview)
   │  POST /api/passport/upload  (yerel FastAPI, 127.0.0.1)
   ▼
app/vision/extractor.process_image()
   │  client=None → HER ZAMAN irtifa_server (vision_mode ne olursa olsun)
   ▼
app/vision/irtifa_client.call_irtifa_ocr_server()
   │  POST {irtifa_server_url}/ocr/passport
   │  headers: x-license-key, x-device-id ; multipart "file"
   ▼
Cloud Run: irtifa-ocr-server (europe-west1)   ← KOD BU REPODA YOK
   ├─ lisans kontrolü, paket (Basic/Pro/Premium), kota (429)
   ├─ Google Vision OCR  → raw_text
   └─ Claude (şüpheli durumlarda?) → passenger{...}, confidence, warnings
   ▼
istemci: _verify_against_local_mrz()  (PR #1)
   raw_text → app/vision/ocr.mrz_lines_from_text → app/mrz.parse → check digit
   checks boş → FREE_TEXT_UNVERIFIED (sarı); hatalı → CHECKSUM_FAIL
   ▼
validate_mrz (expired / duplicate) → PassportRecord → kontrol ekranı → Excel col 2/3/4/20
```

İstemcide hâlâ iki yol daha var ama **ulaşılamıyor**: `extractor._process_with_injected_client` (Claude doğrudan; yalnız testte `client=` verilince) ve `ocr.extract_with_google_vision` (hiçbir çağıran yok). `requirements.txt` ve `Irtifa.spec` buna rağmen `anthropic` ve `google-cloud-vision` paketlerini exe'ye gömüyor.

### 1.2 Sorunlar

| # | Sorun | Etki | Kanıt |
|---|---|---|---|
| S1 | **Sunucu kodu kayıp.** Başka bilgisayarda yazılmış, repoda yok. | Sunucu bozulursa veya Cloud Run projesi kapanırsa OCR tamamen durur; kimse düzeltemez. | `app/settings.py` yalnız URL'yi bilir; `server/` klasörü yok. |
| S2 | **Güven sınırı ters.** Lisans anahtarı istemcide DPAPI'de ama asıl sır (Google/Anthropic anahtarları) sunucuda; sunucunun ne yaptığı denetlenemiyor. | PR #1 bu yüzden checksum doğrulamasını istemciye zorla geri aldı (`_verify_against_local_mrz`). Brief §6 ancak böyle sağlanıyor. | `irtifa_client.py` satır 16–59 (PR #1). |
| S3 | **Maliyet görünmez.** Hangi görselde Claude'un tetiklendiği, hangi modelin kullanıldığı, aylık fatura bilinmiyor. | Fiyatlandırma yapılamıyor, ikinci müşteriye teklif verilemiyor. | `source` alanı sunucudan geliyor ama loglanmıyor. |
| S4 | **Tek müşteri için gereksiz katman.** Lisans/paket/kota mantığı 1 kullanıcıya hizmet ediyor; Bewo'nun sunucusu her sabah 04:00'te ayakta olmak zorunda. | Operasyonel yük Bewo'da; müşteri Bewo'nun uptime'ına bağımlı. | `saas_plani.md` §3 paketler; `test_irtifa_client.py` yalnız sahte `requests.post` ile test ediyor. |
| S5 | **Ölü kod ve şişkin exe.** `vision_mode` ayarı (google_vision/claude/manual) UI'da var ama `process_image` onu yok sayıyor. | Kullanıcı "Claude" seçer, yine sunucuya gider; kafa karışıklığı + büyük exe. | `extractor.process_image` yorum satırı: "provider ne olursa olsun her zaman Irtifa Server". |

---

## 2. Üç seçenek

### 2.0 Ortak varsayımlar ve birim fiyatlar

Hacim: **120 görsel/gün × 30 gün = 3.600 görsel/ay**, sezon 7 ay (Nisan–Ekim) → **25.200 görsel/sezon**, operatör başına.

Görsel boyutu: WhatsApp sıkıştırması sonrası tipik **1280×960 px**. Claude görseli 28×28 piksellik parçalara böler: ⌈1280/28⌉×⌈960/28⌉ = 46×35 = **1.610 görsel token**. Üzerine ~400 token prompt + ~200 token JSON çıktı. Hesapta **2.000 giriş / 200 çıkış token** alındı. ([Claude vision belgesi](https://platform.claude.com/docs/en/build-with-claude/vision), "Resolution and token cost")

| Birim | Fiyat | Kaynak |
|---|---|---|
| Google Vision TEXT_DETECTION | ilk 1.000 birim/ay ücretsiz, sonra **1,50 $ / 1.000** | [cloud.google.com/vision/pricing](https://cloud.google.com/vision/pricing) |
| Claude Haiku 5.5 | **0,10 $ / 1M giriş**, 0,50 $ / 1M çıkış | [platform.claude.com pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| Claude Sonnet 5.5 | **2 $ / 1M giriş**, 10 $ / 1M çıkış | aynı |
| Claude Opus 5.5 | **4 $ / 1M giriş**, 20 $ / 1M çıkış | aynı |
| Cloud Run (istek bazlı, Tier 1; europe-west1 dahil) | ayda 180.000 vCPU-s, 360.000 GiB-s, 2M istek ücretsiz; sonra 0,000024 $/vCPU-s | [cloud.google.com/run/pricing](https://cloud.google.com/run/pricing) |
| Fly.io shared-cpu-1x 512 MB | **3,69 $/ay**, ücretsiz katman yok | [docs.fly.io/about/pricing](https://docs.fly.io/about/pricing) |
| Railway Hobby | **5 $/ay** (5 $ kullanım dahil); Free: 1 $/ay kredi | [railway.com/pricing](https://railway.com/pricing) |
| Supabase | Free: 0 $, 500 MB, **1 hafta hareketsizlikte duraklatılır**; Pro: 25 $/ay | [supabase.com/pricing](https://supabase.com/pricing) |

Görsel başına Claude maliyeti (2.000 giriş + 200 çıkış):

| Model | $/görsel | $/ay (3.600) | $/sezon (25.200) |
|---|---|---|---|
| Haiku 5.5 | 0,0003 | **1,1** | 7,6 |
| Sonnet 5.5 | 0,006 | **21,6** | 151 |
| Opus 5.5 | 0,012 | 43,2 | 302 |
| Google Vision (tek başına) | 0,0015 (ilk 1.000 ücretsiz) | **3,9** | 27 |

> Mevcut sunucunun Claude'u hangi oranda ve hangi modelle tetiklediği bilinmediğinden bugünkü fatura tahmin edilemiyor; §6'daki sorular bunun için.

### 2.1 Seçenek (a) — Sunucusuz: OCR doğrudan Claude, anahtar cihazda

- `anthropic_api_key` zaten `secret_store.py` ile DPAPI'de saklanıyor; `extractor._process_with_injected_client` zaten Claude'u çağırıyor. Eksik olan: `process_image`'ın `vision_mode`'a göre bu yolu seçmesi ve promptun **yalnız MRZ satırlarını** istemesi (brief §6; bugünkü `SYSTEM_PROMPT` serbest metinden de yolcu çıkarıyor, bu sarı sayılmalı).
- Anahtar müşteri başına ayrı Anthropic **workspace**'ten üretilir; konsolda aylık **harcama tavanı** (ör. 30 $) konur; sızarsa tek tıkla iptal.
- Google Vision bu seçenekte **kaldırılır**: Haiku 5.5 görsel başına Vision'dan 5 kat ucuz ve MRZ'yi doğrudan okur; iki sağlayıcı tutmanın gerekçesi kalmadı.

| | |
|---|---|
| Aylık maliyet | Haiku **≈1 $** / Sonnet **≈22 $**; hosting 0 |
| Bewo operasyon yükü | Sıfır sunucu. Yalnız anahtar üretme + tavan. |
| Güvenlik | Sır müşteri PC'sinde (DPAPI, Windows kullanıcısına bağlı). Tek müşteri için kabul edilebilir; harcama tavanı zararı sınırlar. |
| Lisans/kota | Yok. "Lisans" = anahtar var/yok. Paketleme yapılamaz. |
| Risk | İkinci müşteride anahtar dağıtımı ölçeklenmez → o gün (b)'ye geçilir. |

### 2.2 Seçenek (b) — İnce proxy: `server/` altında küçük FastAPI, anahtarlar sunucuda

- Repoda `server/` (Dockerfile + FastAPI, ~200 satır). Tek uç: `POST /ocr/passport`, istemci sözleşmesi **birebir** bugünkü `irtifa_client.py` beklentisi (§4). Sunucu da Claude'u çağırır; Google Vision burada da gereksiz.
- Lisans + kullanım sayacı **Supabase Postgres**'te (Bewo'da hesap var). Harcama görünürlüğü `usage_events` tablosundan.
- Hosting karşılaştırması (3.600 istek/ay, istek başına ~3 s, 1 vCPU / 512 MiB):

| Platform | Aylık | Artı | Eksi |
|---|---|---|---|
| **Cloud Run** (europe-west1) | **0 $** (10.800 vCPU-s ≪ 180.000 ücretsiz) | Zaten kullanılan platform; ölçek sıfıra iner | Python soğuk başlatma 2–5 s (sabah ilk görsel); GCP projesi Bewo'da olmalı |
| Fly.io (ams) | 3,69 $ | Türkiye'ye yakın; sürekli ayakta, soğuk başlatma yok | Ücretsiz katman yok; ayrı hesap/fatura |
| Railway | 5 $ | En basit deploy | Kredi tabanlı; küçük yük için pahalı |
| Supabase Free (DB) | 0 $ | Hazır Postgres + panel | **Sezon dışı (Kas–Mar) 1 haftada duraklar** → haftalık keep-alive cron ya da Pro 25 $/ay |

| | |
|---|---|
| Aylık maliyet | OCR (1–22 $) + Cloud Run 0 $ + Supabase 0 $ (veya 25 $) → **≈1–47 $** |
| Bewo operasyon yükü | Sunucu + DB + lisans üretimi + sezon dışı duraklama takibi + uptime (sabah 04:00). |
| Güvenlik | Sırlar sunucuda; istemci yalnız lisans anahtarı taşır. Checksum istemcide kalır (PR #1). |
| Lisans/kota | Var: paket, aylık kota, cihaz kilidi, kullanım raporu. |
| Risk | S1'in tekrarı: kod repoda ve CI'da olmazsa aynı kayıp yaşanır. |

### 2.3 Seçenek (c) — Önce yerel/ucuz OCR, yalnız başarısızlıkta LLM

- Tesseract (PassportEye/fastmrz) veya PaddleOCR yerel çalışır → `ocr.mrz_lines_from_text` → `app/mrz` checksum. Checksum geçerse yeşil, geçmezse Claude'a fallback.
- Gerçekçi okuma oranı: PassportEye yazarının kendi tahmini **~%80** ("clearly visible MRZ" koşuluyla), bazı belgelerde 10 s+ süre ([PassportEye docs](https://passporteye.readthedocs.io/)). WhatsApp fotoğrafları (eğik, parlama, kırpık) bu koşulu sık ihlal eder; bağımsız benchmark yok ([fastmrz PyPI](https://pypi.org/project/fastmrz/)).
- Exe'ye Tesseract binary (+ `eng`/`ocrb` traineddata, ~50 MB) ve ön-işleme (deskew, kırpma) girer; PyInstaller'da ayrı bakım kalemi.

| | |
|---|---|
| Aylık maliyet | Fallback %20–30 varsayımıyla Haiku **≈0,3 $** / Sonnet **≈5–6 $** (+ (a) veya (b) altyapısı) |
| Kazanç | Haiku'ya göre ayda **<1 $**, Sonnet'e göre ~16 $. |
| Bedel | ~50 MB exe büyümesi, iki OCR yolu, ön-işleme kodu, Windows build kırılganlığı, %20 görselde yine LLM. |
| Ne zaman mantıklı | Çevrimdışı zorunluluğu veya 10× hacim (günde 1.000+ görsel) olursa. İkisi de yok. |

### 2.4 Karşılaştırma

| Kriter (ağırlık) | (a) Sunucusuz | (b) İnce proxy | (c) Yerel + fallback |
|---|---|---|---|
| Bewo operasyon yükü (yüksek) | **en düşük** | en yüksek | orta (build bakımı) |
| Tek müşteride basitlik (yüksek) | **en iyi** | gereksiz katman | gereksiz katman |
| İkinci müşteriye hazırlık (orta) | zayıf, ama (b)'ye yolu açık | **en iyi** | nötr |
| Aylık $ (düşük) | 1–22 | 1–47 | 0,3–6 |
| Kayıp-kod riski (yüksek) | yok | repo+CI şartıyla yok | yok |
| Checksum garantisi (zorunlu) | kodda | kodda (PR #1) | kodda |

---

## 3. Öneri ve gerekçe

**Şimdi (a). İkinci sözleşmede (b). (c) hiç.**

Gerekçe:

1. **Pazar küçük, müşteri tek.** Kapadokya'da ~25–30 ruhsatlı işletme; bugün bir referans müşteri var. Lisans sunucusu, paketleme ve kota altyapısı sıfır gelir üstüne operasyon yükü ekliyor. Sunucu kodunun zaten kaybolmuş olması bu yükün gerçek olduğunu gösteriyor.
2. **Maliyet karar kriteri değil.** En pahalı makul seçenek (Sonnet 5.5, her görsel) ayda ~22 $, sezonda ~150 $. Bir sabah uçuşunun yolcu geliri bunun katları. Bu yüzden "ucuz OCR" için mühendislik yapmak (c) anlamsız.
3. **Güven sınırı doğru yere gelir.** Brief §6 "model SADECE OCR eder, checksum kodda" diyor; PR #1 bunu istemcide zorladı. Claude'a doğrudan gidince MRZ satırları doğrudan `app/mrz.parse`'a girer, `raw_text` üzerinden ikinci bir çıkarım katmanı (S2) ortadan kalkar.
4. **(b)'ye geçiş ucuz tutulur.** Sunucu sözleşmesi §4'te donduruluyor; istemci tarafında `OcrProvider` arayüzü hem "Claude doğrudan" hem "İrtifa sunucusu" için aynı `OcrResult`'ı döner. İkinci firma geldiğinde yapılacak iş: `server/` klasörünü yazmak ve `vision_mode`'u değiştirmek.

**Model seçimi:** başlangıç **Sonnet 5.5** (kalite), aday **Haiku 5.5** (20× ucuz). Karar, 50 gerçek görsellik benchmark'la (§5, PR 3) verilir; yeşil oranı ve checksum geçme oranı Sonnet'in %2 altına inmezse Haiku'ya geçilir. Sarı kayıtlarda "tekrar oku" butonu bir üst modele (Opus 5.5) gider; bu zaten `ai_confidence_threshold_fallback` mantığının karşılığı.

**Bewo ikinci bir firmaya satmadan önce neye ihtiyacı var (sırayla):**

| # | Gereksinim | Neden |
|---|---|---|
| 1 | `server/` repoda, Docker ile tek komutta ayağa kalkan, CI'da test edilen proxy (§4) | S1 bir daha yaşanmasın; satış = sunucu taahhüdü. |
| 2 | Müşteri başına lisans + aylık kota + kullanım raporu (Supabase) | Fiyat verebilmek ve kötüye kullanımı sınırlamak için. |
| 3 | Fiyat listesi (`saas_plani.md`'de yok) — OCR birim maliyeti artık bilindiğine göre: ör. sezonluk sabit + görsel başı | Teklif PDF'i (Rast Creative markalı) için şart. |
| 4 | KVKK: aydınlatma metni, veri işleyen sözleşmesi, pasaport görsellerinin yurt dışı transferi (Anthropic/Google) için açık dayanak | Pasaport = özel nitelikli olmasa da yüksek riskli kişisel veri; kurumsal müşteri soracak. |
| 5 | İmzalı güncelleme anahtarı üretilmiş ve gömülü (`UPDATE_PUBLIC_KEY_B64`, PR #1'de boş) + yeniden derlenmiş exe | Uzaktan sürüm dağıtmadan iki müşteri desteklenemez. |
| 6 | Destek süreci: sabah 04:00–07:00 kim bakacak, SLA ne | Operasyon saati tatil saatiyle çakışıyor. |

---

## 4. Sözleşme (istemci ↔ OCR sağlayıcı)

İki seviye: (i) **süreç içi arayüz** — (a)'da hemen kullanılır; (ii) **HTTP sözleşmesi** — (b) için şimdi dondurulur. İkisi aynı JSON gövdesini taşır; `irtifa_client.py`'nin bugünkü beklentileri korunur.

### 4.1 Süreç içi arayüz (PR 1)

```python
# app/vision/providers/base.py
@dataclass
class OcrResult:
    status: Literal["success", "error"]
    passenger: dict            # first_name, last_name, nationality, gender,
                               # document_no, birth_date, expiry_date (ISO 8601 | null)
    confidence: Literal["green", "yellow", "red"]
    raw_text: str              # MRZ satırları "\n" ile; checksum BURADAN hesaplanır
    warnings: list[str]        # "expired", "checksum", "low_quality", ...
    source: str                # "claude:claude-sonnet-5-5" | "irtifa_server" | ...
    usage: dict | None         # {"input_tokens":..., "output_tokens":..., "usd": ...}
    error: str | None

class OcrProvider(Protocol):
    name: str
    def read(self, image_bytes: bytes, media_type: str) -> OcrResult: ...
```

`extractor.process_image` sağlayıcıyı `settings.vision_mode`'a göre seçer (`claude_direct` | `irtifa_server` | `manual`), sonucu **her zaman** `_verify_against_local_mrz` + `validate_mrz`'den geçirir. Yeşil yalnız `mrz.checks_ok` ile mümkündür; sağlayıcının `confidence`'ı yalnız sarı/kırmızı ayrımına etki eder.

### 4.2 HTTP sözleşmesi (PR 5, (b) açıldığında)

**İstek**

```
POST {server_url}/ocr/passport
x-license-key: <lisans>          (zorunlu)
x-device-id:   <uuid>            (zorunlu; ilk istekte lisansa kilitlenir)
x-client-version: 1.3.0          (yeni, isteğe bağlı; eski sürümleri uyarmak için)
Content-Type: multipart/form-data; file=<jpeg|png|webp>, ≤ 10 MB
```

**Yanıt 200**

```json
{
  "status": "success",
  "passenger": {
    "first_name": "AYSE", "last_name": "YILMAZ", "nationality": "TUR",
    "gender": "F", "document_no": "U12345678",
    "birth_date": "1990-05-01", "expiry_date": "2031-05-01"
  },
  "confidence": "green",
  "raw_text": "P<TURYILMAZ<<AYSE<<<<...\nU123456785TUR9005018F3105012<<<<<<<<<<<<<<06",
  "warnings": [],
  "source": "claude:claude-sonnet-5-5",
  "usage": { "input_tokens": 2012, "output_tokens": 180, "usd": 0.0058,
             "quota_used": 1843, "quota_limit": 5000, "period": "2026-06" }
}
```

`usage` yeni ve isteğe bağlıdır; mevcut istemci bilmediği alanı yok sayar, bu yüzden geriye uyumludur. `status: "error"` durumunda `error` alanı Türkçe, operatöre gösterilebilir metin taşır.

**Hata kodları** (istemcideki eşleme `irtifa_client.py` 60–80 ile uyumlu)

| HTTP | `detail` | İstemci mesajı (mevcut) | Ne zaman |
|---|---|---|---|
| 400 | `unsupported_media_type` | Desteklenmeyen dosya türü. | MIME jpeg/png/webp/gif dışı |
| 401 | `license key required` | OCR için lisans anahtarı gerekli. | başlık yok |
| 403 | `license invalid` / `license expired` | Lisans anahtarı geçersiz. | bulunamadı / `valid_until` geçmiş / `status != active` |
| 403 | `device mismatch` | Cihaz kimliği oluşturulamadı.* | `device_id` lisanstaki `bound_device_id`'den farklı |
| 413 | — | Dosya boyutu çok büyük. | > 10 MB |
| 429 | `quota exceeded` + `Retry-After` | OCR kullanım kotası doldu… | aylık `quota_limit` aşıldı |
| 502 | `upstream_error` | OCR servisi geçici bir hata verdi. | Anthropic 5xx/timeout |

\* Mevcut istemci metni yanıltıcı ("oluşturulamadı"); PR 1'de "Bu lisans başka bir bilgisayara kilitli" olarak düzeltilir.

**Kullanım ölçümü:** her 200 yanıtı bir `usage_events` satırı yazar (görsel saklanmaz, yalnız sayaç ve token). Kota ay bazında `usage_events` toplamından hesaplanır; `429` eşiğine %90'da `warnings: ["quota_90"]` eklenir ki istemci önceden uyarsın.

**Lisans şeması (Supabase Postgres)**

```sql
create table licenses (
  id              uuid primary key default gen_random_uuid(),
  key_hash        text not null unique,          -- argon2(license_key); düz anahtar saklanmaz
  company_name    text not null,
  plan            text not null check (plan in ('basic','pro','premium')),
  status          text not null default 'active', -- active | suspended | revoked
  bound_device_id text,                           -- ilk istekte dolar; null = henüz kilitlenmedi
  quota_limit     integer not null default 5000,  -- görsel/ay
  valid_from      date not null,
  valid_until     date not null,
  model_primary   text not null default 'claude-sonnet-5-5',
  model_fallback  text,                           -- premium: 'claude-opus-5-5'
  created_at      timestamptz default now()
);

create table usage_events (
  id            bigserial primary key,
  license_id    uuid references licenses(id),
  device_id     text not null,
  occurred_at   timestamptz default now(),
  model         text not null,
  input_tokens  integer, output_tokens integer, usd numeric(8,5),
  confidence    text,                             -- green | yellow | red
  http_status   smallint not null
);
create index on usage_events (license_id, occurred_at);
```

Paket eşlemesi: `basic` → 403 (`ocr_disabled`), `pro` → yalnız `model_primary`, `premium` → sarıda `model_fallback` tetiklenir. `saas_plani.md` §3 ile uyumlu.

---

## 5. Geçiş planı (her adım bir PR)

| PR | İçerik | Kırmadan çalışır mı? | Test |
|---|---|---|---|
| **1 — Provider arayüzü** | `app/vision/providers/{base,irtifa_server}.py`; `irtifa_client.call_irtifa_ocr_server` olduğu gibi kalır, provider onu sarar. `process_image` sağlayıcıyı `vision_mode`'dan seçer; **varsayılan `irtifa_server` kalır** → davranış değişmez. Ölü `google_vision` yolu ve `Irtifa.spec`'ten `google.cloud.vision` kaldırılır. | Evet; mevcut sunucu aynen kullanılır. | `tests/contract/` (aşağıda); `test_irtifa_client.py` aynen geçer. |
| **2 — `claude_direct` provider** | Yalnız-MRZ prompt (`SYSTEM_PROMPT` daraltılır: MRZ satırları + format; serbest metin yolu `FREE_TEXT_UNVERIFIED`'e düşer). `OcrResult.raw_text` = MRZ satırları; `usage` Anthropic `response.usage`'dan. Settings UI'da sağlayıcı seçimi gerçek anlam kazanır. Varsayılan modeller `claude-sonnet-5-5` / `claude-opus-5-5`. | Evet; opt-in. | Sahte Anthropic istemcisi (`client=` enjeksiyonu zaten var) + `test_vision_extractor.py` genişler. |
| **3 — Benchmark** | `scripts/ocr_benchmark.py`: repo dışı klasördeki gerçek görseller (PII) üzerinde Haiku 5.5 / Sonnet 5.5 / mevcut sunucu; çıktı: yeşil oranı, checksum geçme, ortalama $/görsel, p95 süre. Sonuç `docs/ocr-benchmark-2026-xx.md`. | Kod değişikliği yok. | — |
| **4 — Varsayılanı çevir** | `vision_mode` varsayılanı `claude_direct`; `irtifa_server` seçilebilir kalır. `UPDATE_PUBLIC_KEY_B64` üretilip gömülür, sürüm 1.3.0, exe derlenir, müşteriye kurulur, anahtar DPAPI'ye girilir, Anthropic konsolunda tavan. | Evet; geri dönüş = ayar değiştir. | `test_settings.py`; sahada 1 hafta paralel (sunucu sonucu ile karşılaştırma logu). |
| **5 — `server/` iskeleti** *(ikinci müşteri şartıyla)* | FastAPI + Dockerfile + Supabase şeması (§4.2) + Cloud Run deploy (GitHub Actions). Aynı `OcrResult` üretir; Claude çağrısı PR 2'deki provider'ın kendisidir (paylaşılan modül). | Evet; istemci zaten bu sözleşmeyi konuşuyor. | **Aynı** `tests/contract/` fixture'ları sunucuya `TestClient` ile koşulur. |
| **6 — Kullanım raporu** | `GET /license/usage` (aylık özet) + istemcide Ayarlar'da "bu ay X/Y görsel" göstergesi; Bewo için Supabase panelinde basit görünüm. | Evet. | Sözleşme testi + `test_api_hardening.py`. |

### Test stratejisi — sahte sunucu ile sözleşme testleri

- `tests/contract/fake_ocr_server.py`: FastAPI uygulaması, `/ocr/passport` için **senaryo başına** sabit JSON döner (`tests/contract/fixtures/*.json`: `green_td3.json`, `yellow_no_mrz.json`, `expired.json`, `quota_429.json`, `device_403.json`, `upstream_502.json`).
- İstemci testleri `requests.post`'u bu uygulamaya yönlendiren bir monkeypatch ile koşar (uvicorn gerekmez); sunucu PR 5'te aynı fixture'larla `TestClient` üzerinden **yanıt şemasını** doğrular. Tek doğruluk kaynağı: fixture dosyaları + `OcrResult` pydantic şeması.
- Değişmez (invariant) testleri, sağlayıcıdan bağımsız: (1) `checks` boşsa asla yeşil; (2) `raw_text` MRZ'si ile `passenger.document_no` çelişirse `CHECKSUM_FAIL`; (3) `expired`/`duplicate` yerel hesaplanır (bugünkü `test_server_result_gets_local_expiry_and_duplicate_checks` genelleştirilir).
- `usage` alanı eksik/fazla alanla gelince istemci kırılmaz (geriye uyumluluk testi).

---

## 6. Açık sorular (Bewo'ya)

| # | Soru | Neden önemli |
|---|---|---|
| 1 | Cloud Run `irtifa-ocr-server` hâlâ açık mı? Hangi GCP projesinde, faturası kimde, son 3 ayın tutarı ne? | §2.0'daki "bugünkü maliyet" boşluğu; kapatma/geçiş takvimi. |
| 2 | Sunucu kodu hangi bilgisayarda? Git geçmişi var mı? Hangi Claude modelini, hangi koşulda çağırıyor? | PR 5'te sıfırdan yazmak yerine kurtarmak; `source` değerlerinin anlamı. |
| 3 | Arkadaşının firması hangisi, kaç balon, günde gerçekten kaç pasaport (120 varsayımı doğru mu)? Sezon dışı kullanım var mı? | Hacim ve Supabase duraklama riski. |
| 4 | Lisans fiilen **satıldı mı**, yoksa arkadaş ücretsiz mi kullanıyor? Yazılı bir anlaşma/KVKK metni var mı? | §3'teki 2–4 numaralı gereksinimlerin aciliyeti. |
| 5 | Arkadaşın PC'sinde Anthropic anahtarı tutmak kabul edilebilir mi (DPAPI, tek Windows kullanıcısı)? Birden fazla operatör PC'si var mı? | (a) için tek güvenlik varsayımı; birden fazla PC = birden fazla anahtar. |
| 6 | Anthropic hesabı kimin: Bewo'nun mu, Rast'ın mı? Müşteri başına workspace açılabilir mi? | Harcama tavanı ve iptal yetkisi. |
| 7 | İkinci müşteri için somut bir görüşme var mı, tarih ne? | (b)'nin tetikleyicisi; yoksa PR 5–6 ertelenir. |
| 8 | Çevrimdışı çalışma hiç gündemde mi (Kapadokya'da sabah saatinde internet kesintisi yaşandı mı)? | Tek başına (c)'yi yeniden masaya getirebilecek şart. |
