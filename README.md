# Irtifa - Balon Uçuş Planlama & Manifesto Sistemi

Irtifa, Kapadokya'daki balon firmaları ve acenteler için geliştirilmiş, manuel ve hataya açık olan "uçuş manifestosu" sürecini otomatize eden akıllı bir masaüstü (ve web) uygulamasıdır. 

Mevcut Excel tabanlı uçuş planlamalarınızla **tam entegre** çalışır; mevcut düzeninizi bozmadan iş akışınızı hızlandırır, hataları sıfıra indirir ve havacılık otoriteleri (SHGM vb.) için gereken resmi manifestoları tek tıkla oluşturmanızı sağlar.

## 🚀 Temel Özellikler

- **Akıllı Pasaport Okuma (OCR):** Pasaport veya kimlik fotoğraflarını sisteme yüklediğinizde, Google Vision AI veya Anthropic Claude 3 altyapısı ile MRZ (Makine Okunabilir Alan) kodlarını anında okur. Uyruk, Cinsiyet, İsim ve Pasaport Numarası gibi kritik bilgileri hata yapmadan doğrudan sisteme kaydeder.
- **Excel ile Çift Yönlü Senkronizasyon:** Halihazırda kullandığınız "Uçuş Planlama Excel'inizi" sisteme bağlarsınız. Irtifa bu dosyayı okur, rezervasyonları ekrana getirir, okunan kimlik bilgilerini ilgili Excel satırlarına geri yazar. Herhangi bir veritabanı taşıması gerektirmez, veriniz her zaman Excel'inizde kalır.
- **Tek Tıkla Manifesto Üretimi:** Hazırlanan planlamaya göre "hangi balona kimlerin bineceğini" gruplayıp, balon başına özel Excel manifestolarını saniyeler içinde oluşturur. Çıktılar önceden belirlediğiniz resmi formata birebir uyar.
- **Şoför / Alış (Pickup) Listeleri:** Otel, acente ve alış saatine göre gruplanmış otomatik PDF veya Excel şoför listeleri üretir. Sabah operasyonunun kusursuz yürümesini sağlar.
- **Akıllı Formlar & Otomatik Tamamlama:** Oteller, acenteler, şoförler ve pilotlar gibi geçmişte girdiğiniz verileri otomatik öğrenir (Otomatik Tara özelliği ile eski Excel'inizden tüm listeyi çekebilirsiniz). Veri girişinde saniyeler kazandırır.
- **Modern ve Akıcı Arayüz:** Aetheria Tasarım Dili (Tailwind CSS tabanlı, Warm Amber renkleri, Glassmorphism detayları) kullanılarak hazırlanan göz yormayan, son derece hızlı ve kullanıcı dostu arayüz.
- **Çevrimdışı/Yerel Çalışma ve Gizlilik:** Sistem SQLite veritabanı kullanarak masaüstünüzde (`Irtifa.exe` olarak) yerel çalışır. (Yalnızca pasaport OCR işlemi sırasında cloud AI kullanılır). KVKK kapsamında, işlemler bittikten sonra pasaport fotoğraflarını sistemden otomatik olarak siler.
- **Günlük Hava Durumu (Aviation Weather):** Open-Meteo destekli altyapı ile Göreme Vadisi'ne ait 03:30 - 07:30 arası kritik sabah saatlerindeki rüzgar (m/s, yön), sıcaklık ve yağış durumlarını ana ekranda canlı olarak sunar.

## 🛠️ Kurulum ve Kullanım

Uygulamanın hazır derlenmiş versiyonu (Windows), doğrudan çalıştırılabilir bir EXE dosyasıdır. Github `Releases` sayfasından `Irtifa.exe` dosyasını indirebilirsiniz.

### Kaynak Koddan Çalıştırmak İçin (Geliştiriciler)

1. Depoyu klonlayın ve bağımlılıkları yükleyin:
   ```bash
   git clone https://github.com/bewoai/Manifesto.git
   cd Manifesto
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Geliştirme sunucusunu veya masaüstü versiyonunu başlatın:
   ```bash
   python desktop_launcher.py
   ```

## 📦 Build (Derleme)

Windows için tek tıklanabilir EXE dosyası (`Irtifa.exe`) üretmek için:
```bash
python -m PyInstaller Irtifa.spec --noconfirm --clean
```
Üretilen uygulama `dist/Irtifa.exe` altında olacaktır.

## 🏗️ Mimari Altyapı
- **Backend:** Python, FastAPI, SQLite (Yerel veritabanı)
- **Frontend:** Vanilla JS, HTML, Tailwind CSS (Vite aracılığıyla derlenmiştir)
- **OCR Motorları:** Google Cloud Vision veya Anthropic Claude (Ayarlanabilir)
- **Desktop Çerçevesi:** pywebview (Chromium WebView2 altyapısı)
