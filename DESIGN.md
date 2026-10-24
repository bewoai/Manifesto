---
name: İrtifa
description: Kapadokya balon operasyonu için uçuş planlama ve manifesto masaüstü uygulaması — "Kısık Tüf"
colors:
  ground: "#d9d4cc"
  rail: "#cfc9c0"
  panel: "#e4e0d9"
  raised: "#eae7e1"
  well: "#ddd8d1"
  line: "#c4bdb3"
  outline: "#8f887f"
  ink: "#2e2b28"
  ink-2: "#625c55"
  primary: "#3d5a8a"
  primary-hover: "#344e79"
  primary-soft: "#cbd3e0"
  on-primary: "#eef0f3"
  success: "#3f6e44"
  warning: "#7a5c12"
  danger: "#9a3e34"
  info: "#3e6487"
  flag-go: "#4f7550"
  flag-hold: "#876b22"
  flag-stop: "#9a483e"
  on-flag: "#f4f2ec"
  env-1: "#4a6fa5"
  env-2: "#5f8a5f"
  env-3: "#a14a6a"
  env-4: "#6f5a9a"
  env-5: "#3f7f7f"
  env-6: "#8c702a"
  env-7: "#5c6b7a"
  env-8: "#a8676f"
  graphite-ground: "#1f1e1c"
  graphite-panel: "#282725"
  graphite-ink: "#e4e0d9"
  graphite-primary: "#7d9bd1"
typography:
  display:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "38px"
    fontWeight: 600
    lineHeight: 1.16
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.27
  metric:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "40px"
    fontWeight: 600
    lineHeight: 1.05
    fontFeature: "tnum"
  body:
    fontFamily: "Source Sans 3, Segoe UI, system-ui, sans-serif"
    fontSize: "15.5px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum"
  label:
    fontFamily: "Source Sans 3, Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.33
    letterSpacing: "0.08em"
  code:
    fontFamily: "JetBrains Mono, Consolas, monospace"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.9
rounded:
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "12px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  nav-item-active:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
  panel:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.xl}"
    padding: "24px"
  input:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px 14px"
  flag-go:
    backgroundColor: "{colors.flag-go}"
    textColor: "{colors.on-flag}"
    height: "64px"
  balloon-chip:
    rounded: "{rounded.sm}"
    padding: "2px 8px"
---

# Design System: İrtifa

## Overview

**Creative North Star: "Kısık Tüf"** — gün ışığında, gölgeli bir taş odada çalışmak.

İrtifa'yı bir balon işletmesinin operasyon sorumlusu gündüz, ofiste kullanır. Ekrana uzun süre bakar. Bu yüzden zemin orta tonlu bir tüf taşı grisidir ve kontrast düşüktür. Saf beyaz hiçbir yerde kullanılmaz. Tek arayüz vurgusu, Göreme kaya kiliselerinin soluk lapis mavisidir. Renk yalnız anlam taşır: uçuş bayrağı, balonun zarf rengi ve durum (doğrulandı, kontrol, hata).

Biçim dili üç tanıdık nesneden gelir:
- **Balon zarfı:** Her balonun sabit bir zarf mürekkebi vardır. Kullanıcı balonu her ekranda aynı renkten tanır.
- **Havalimanı kapı panosu:** Kolonlar sabittir, satır durumu değişse de ızgara bozulmaz. Değişen satır görülene dek işaretli kalır.
- **Biniş kartı:** Ayrıntı, delikli ayraçla bölünmüş segmentli bir kart olarak açılır.

Sayfanın üstündeki sabah uçuş bayrağı günün hava tavsiyesini gösterir: yeşil uygun, sarı dikkat, kırmızı riskli.

İkinci tema **Yumuşak Grafit** (`[data-theme="graphite"]`) aynı bileşenleri sıcak gri koyu zeminde gösterir. Lacivert ve neon kullanılmaz.

**Key Characteristics:**
- Taş katmanları: zemin, ray, panel, giriş alanı, gömük alan. Hepsi düz ve mat.
- Tek vurgu: soluk lapis. Turuncu ve amber vurgu olarak kullanılmaz.
- Başlıklar ve büyük rakamlar Source Serif 4, metin Source Sans 3, belge ve kod JetBrains Mono.
- Tablo rakamları her yerde `tnum`.
- Cam, bulanıklık, gradyan, parıltı ve 3D ikon yoktur.

## Colors

Strateji: **Restrained**. Nötr taş katmanları, tek bir lapis vurgusu, anlam taşıyan küçük renk aileleri. Tüm değerler `frontend/style.css` başındaki CSS değişkenlerinden gelir (RGB kanalları). `frontend/tailwind.config.js` bunları `rgb(var(--x) / <alpha-value>)` olarak okur. Eski token adları (`surface`, `on-surface`, `primary`, `tertiary`…) uyumluluk için korunur.

### Primary
- **Soluk Lapis** (`#3d5a8a`, graphite: `#7d9bd1`): Aktif menü satırını, ana düğmeyi, bağlantıları ve odak halkasını boyar. Ana eylem her zaman lapistir. "İndir", "Kaydet" ve "Rezervasyon oluştur" da buna dahildir.

### Neutral
- **Tüf Zemin** (`#d9d4cc`): Sayfa zemini.
- **Tüf Ray** (`#cfc9c0`): Menü rayı.
- **Tüf Panel** (`#e4e0d9`): Kartlar, tablolar, biniş kartı.
- **Açık Tüf** (`#eae7e1`): Giriş alanları, ikincil düğme, açılır menü ve bildirim.
- **Gömük Tüf** (`#ddd8d1`): İç alanlar, bırakma alanı, pasif bayrak.
- **Kıl Çizgi** (`#c4bdb3`): Tüm ayırıcılar ve 1px kenarlıklar.
- **Kömür** (`#2e2b28`) ve **İkincil Kömür** (`#625c55`): Metin. Siyah kullanılmaz.

### Anlam renkleri
- **Durum:** adaçayı (`#3f6e44`) doğrulandı, okr (`#7a5c12`) kontrol gerekli, tuğla (`#9a3e34`) hata, bilgi mavisi (`#3e6487`). Arka plan olarak yalnız %12–14 tonla kullanılır.
- **Uçuş bayrağı:** `flag-go` / `flag-hold` / `flag-stop` düz bez bloklarıdır. Üzerindeki metin `on-flag` rengindedir ve kontrastı en az 4,5:1'dir.
- **Balon zarf mürekkepleri** (`env-1…env-8`): Mavi, adaçayı, ahududu, menekşe, deniz yeşili, okr, arduvaz ve gül. Sıra, Ayarlar'daki balon kodlarından gelir. Bilinmeyen kod kararlı bir hash ile renk alır.

### Named Rules
**The One Accent Rule.** Arayüzde eylem rengi yalnız lapistir. Yeşil bir düğme "başarılı" anlamı taşır, eylem için kullanılmaz.

**The Envelope Rule.** Bir balonun rengi her ekranda aynıdır: rozet, zarf şeridi, koltuk çubuğu, biniş kartı kodu. Zarf mürekkepleri balon dışında hiçbir şeyi boyamaz.

**The No-White Rule.** Açık temada bile en açık yüzey Açık Tüf'tür (`#eae7e1`). Saf beyaz kullanılmaz.

## Typography

**Başlık:** Source Serif 4 (yerel, değişken ağırlık).
**Metin:** Source Sans 3 (yerel, değişken ağırlık).
**Kod ve belge numarası:** JetBrains Mono.

Gövde metni 15,5px'tir ve tablo rakamları açıktır. Sayfa başlığı ile gün başlığı serif, 600 ağırlıktadır. Metrik rakamları serif 40px'tir. Etiketler 12px, büyük harf, 0,08em aralıklı ve 600 ağırlıktadır.

### Hierarchy
- **Display** (38px/600, serif): Ana sayfadaki gün başlığı. Örnek: "Dün · 23 Ekim 2026 Cuma". Gün adı ikincil renkte ve normal ağırlıktadır.
- **Headline** (22px/600, serif): Panel başlıkları ("Bugün yapılacaklar", "Balonlar").
- **Metric** (40px/600, serif, tnum): Ana sayfadaki dört metrik.
- **Body** (15,5px/400): Tüm metin.
- **Label** (12px/600, büyük harf): Tablo başlıkları, biniş kartı alan adları, metrik adları.
- **Code** (12,5px mono): Pasaport ve kimlik numaraları, biniş kartı koçanı.

### Named Rules
**The Mono-Means-Data Rule.** Monospace yalnız belge numarası ve kart koçanı gibi okunacak veri için kullanılır. Süs amaçlı kullanılmaz.

## Layout

- Kabuk: solda 256px menü rayı (`md` ve üstü), üstte 64px başlık çubuğu, içerikte 32px kenar boşluğu (mobilde 16px).
- Ana sayfa en fazla 1440px genişliktedir. Sırası şöyle: bayrak şeridi, gün başlığı ve gün seçici, yapılacaklar ile metrikler (`xl` ve üstünde 1,35fr / 1fr), pano ile biniş kartı (`xl` ve üstünde kart 340px yan sütun).
- Pano kolonları önceliğe göre düşer. Pilot `sm` altında, Rezervasyon ve Şoför `2xl` altında gizlenir, çünkü bu bilgiler biniş kartında da vardır. Manifesto tablosunda satır numarası `lg` altında gizlenir.
- `md` altında menü üst üste açılan bir paneldir (`__toggleNav`).
- Uygulama penceresi 1360×860'tır. Bu boyutta ana sayfa kaydırmadan bayrak, yapılacaklar, metrikler ve panoyu gösterir.

## Elevation & Depth

Sistem **düzdür**. Derinlik tonal katmanlarla verilir: zemin, panel, açık yüzey. Gölge yalnız gerçekten üstte duran öğelerde kullanılır: bildirim, açılır menü, pencere ve sürükleme çubuğu. Bunlar yumuşak, ofsetli ve mürekkep tonlu gölgelerdir. Kartlarda gölge yoktur. Durum, kenarlığın tamamında ince bir tonla gösterilir. Yan veya üst şerit kullanılmaz.

## Shapes

- Köşeler küçük ve sakindir: rozet 6px, düğme ve giriş alanı 8px, kart 10–12px. Hap biçimli düğme yoktur.
- Kenarlıklar 1px Kıl Çizgi'dir.
- Zarf şeridi, balonun mürekkebinde 4px genişliğinde üç dilimden oluşur. Ortadaki dilim %62 tondadır.
- Biniş kartı ayracı kesikli 2px bir çizgidir. İki yanında zemin renginde yarım daire çentikler bulunur.

## Components

### Buttons
- **Ana** (`.btn-primary`): Lapis zemin, açık metin, 8px köşe, 10×20px iç boşluk. Üzerine gelince koyu lapis olur, basınca 1px aşağı iner.
- **İkincil** (`.btn-secondary`): Açık Tüf zemin, kıl çizgi kenarlık. Üzerine gelince kenarlık koyulaşır.
- **Hayalet** (`.btn-ghost`): Zemin yoktur. Üzerine gelince %7 mürekkep tonu alır.
- **Tehlike** (`.btn-danger`): Tuğla zemin. Yalnız geri alınamaz eylemlerde kullanılır.
- `.btn-success` tanımlıdır ama sayfalarda kullanılmaz (bkz. One Accent Rule).

### Navigation
Menü satırları çerçevesizdir: ikon ve metin. Üzerine gelince %6 mürekkep tonu alır. Aktif satır dolu lapis bloktur ve `aria-current="page"` taşır. Alt bölümde kullanıcı adı, tema düğmesi ve kapatma düğmesi bulunur. "Manuel mod" sıradan bir satırdır, yanında okr renkli bir nokta vardır.

### Cards / Containers
`.glass-panel` adı korunmuştur, ama artık düz bir paneldir (Tüf Panel ve kıl çizgi kenarlık). İç içe kart kullanılmaz. Boş durum tek bir başlık ve bir satırdan oluşur.

### Inputs / Fields
Açık Tüf zemin, kıl çizgi kenarlık, 8px köşe. Odakta lapis halka (%30) ve lapis kenarlık görünür.

### Sabah uçuş bayrağı (`.flag-strip`)
Üç düz bez bloğundan oluşur. Aktif blok genişler ve şunları taşır: başlık (serif), konum, ölçüm saati, rüzgâr, özet ve "Hava ayrıntısı" bağlantısı. Pasif bloklar Gömük Tüf'tür, yanlarında renk noktası ve büyük harf adları vardır. Mobilde yalnız aktif blok görünür. Altında "Hava tavsiyesidir; resmî uçuş izni yerine geçmez." notu yer alır.

### Kapı panosu (`.board`)
Sabit kolonlu tablodur, kıl çizgi satır ayırıcıları vardır. Satırın üzerine gelince %3,5 mürekkep tonu alır. Değişen satırda `.changed` sınıfıyla lapis ton ve "Değişti" etiketi görünür. Değişiklik `localStorage` anlık görüntüsüyle bir kez gösterilir. `.sticky-head` sınıfıyla başlık 64px'te yapışır.

### Biniş kartı (`.pass`)
Üstte zarf şeridi ve 34px serif balon kodu, sağda koltuk sayısı bulunur. Altında alan listesi gelir (etiket ve değer, kıl çizgi ayırıcılı). Ardından delikli ayraç, en altta mono koçan (GÜN, BLN, RZV) ve "Manifesto →" düğmesi yer alır. `role="region"` ve `aria-label="<KOD> balonu"` taşır.

### Balon kodu
- Küçük rozet (`.balloon-code`, `balloonBadge`): Balon mürekkebiyle metin, %13 ton zemin ve %35 kenarlık.
- Pano satırında: 17px yarı kalın metin, balon mürekkebiyle, rozetsiz.

## Do's and Don'ts

### Do:
- **Do** renkleri her zaman CSS değişkenleri üzerinden kullanın (`bg-panel`, `text-ink-2`, `rgb(var(--env))`). Ham hex yalnız `style.css` başındaki tema bloklarında bulunur.
- **Do** balon kodlarını `balloonInk` / `balloonBadge` / `envStripe` ile çizin.
- **Do** ana eylem için `.btn-primary`, ikincil eylem için `.btn-secondary` kullanın.
- **Do** dar ekranda tablo kolonlarını önceliğe göre gizleyin. Tabloyu yatay kaydırmaya zorlamayın.
- **Do** durumu kenarlık tonu, rozet ve metinle birlikte gösterin. Durumu yalnız renkle anlatmayın.

### Don't:
- **Don't** turuncu ya da amber vurgu, cam, bulanıklık, gradyan, parıltı ya da 3D ikon kullanmayın.
- **Don't** saf beyaz zemin kullanmayın.
- **Don't** yeşili eylem düğmesi olarak kullanmayın.
- **Don't** kartlarda yan veya üst renk şeridi kullanmayın.
- **Don't** başlık üstüne küçük etiket (kicker) ya da iç içe kart koymayın.
- **Don't** `app.js`'i sorgu ekiyle (`?v=`) yüklemeyin. Derlemede iki modül kopyası oluşur.
