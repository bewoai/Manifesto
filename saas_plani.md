# İrtifa Yazılımı - Faz 3: SaaS ve Ürünleştirme Planı

Bu belge, İrtifa yazılımının kapalı devre yerel kullanım (Faz 1 & 2) aşamasından, ticari bir B2B SaaS (Hizmet olarak yazılım) ürününe dönüştürülmesi için gereken stratejik ve mimari planları içermektedir.

## 1. Merkezi Mimari ve Aracı Sunucu (Proxy) Modeli

Mevcut durumda masaüstü uygulaması doğrudan Google Vision ve Anthropic API'leri ile iletişim kurmaktadır. Ancak ürünleşme aşamasında API anahtarlarının son kullanıcılara dağıtılması güvenlik ve kullanıcı deneyimi açısından kabul edilemez. 

Bu sorunu çözmek için araya bir **Merkezi Manifesto Sunucusu (Backend)** eklenecektir.

**Çalışma Mantığı:**
1. İrtifa masaüstü uygulaması, taranan pasaport görsellerini kendi sunucumuza iletir.
2. Sunucumuz gizli tutulan Google Cloud ve Claude API anahtarları ile işlemleri gerçekleştirir.
3. Çıkan sonuçlar doğrudan masaüstü uygulamasına geri döndürülür.

**Performans Etkisi:**
Bu mimarinin ekleyeceği gecikme süresi yaklaşık **50-100 milisaniye (0.1 saniye)** olacaktır. Bulut sunucuları arasındaki veri transferi ışık hızında gerçekleştiği için bu ekstra aşama, kullanıcının hissetmeyeceği kadar hızlı işleyecektir. İşlem sürelerinde kayda değer bir yavaşlama yaşanmayacaktır.

## 2. Lisans Kodu ve Cihaz Kilitleme (Hardware Binding) Stratejisi

Klasik kullanıcı adı ve şifre giriş sistemi yerine, ticari masaüstü yazılımlarında endüstri standardı olan **Lisans Kodu** sistemi kullanılacaktır.

**Lisans Sisteminin Avantajları:**
* **Donanım Kilitleme (Hardware Binding):** Kullanıcı, 16 haneli lisans kodunu (`BWA-9XF2-K8M1-PL4Q`) girdiği anda, lisans o bilgisayarın donanım kimliğine (anakart/işlemci) kilitlenir. Kötü niyetli kullanıcıların lisansı başka firmalarla paylaşması engellenir.
* **Şifre Sıfırlama Yükünün Olmaması:** Kullanıcıların "şifremi unuttum" senaryolarıyla müşteri hizmetlerini meşgul etmesi önlenir. 
* **Bayilik/Reseller Uygunluğu:** Lisans kodları topluca üretilip bölge bayilerine (reseller) satılmak üzere kolayca dağıtılabilir.

**Faz 2 ile Uyumu:**
v0.2.0 sürümünde inşa edilen yerel giriş sistemi korunacaktır. Lisans kodu ana bilgisayarı (firmayı) sunucuya karşı doğrular. Yetkiyi alan bilgisayarda personeller, önceden olduğu gibi kendi lokal operatör isimleriyle sisteme giriş yapmaya devam eder ve işlem geçmişi (audit log) eksiksiz tutulur.

## 3. Paket Yönetimi ve 3 Katmanlı Fiyatlandırma

Kullanıcıların Claude ve Google Vision maliyetlerini yönetebilmek adına, sunucu tarafında yönetilecek 3 katmanlı bir paket sistemi kurgulanacaktır:

1. **Temel Paket (Basic):** 
   * Yalnızca Excel stabilizasyonu ve manuel rezervasyon/yolcu girişi.
   * OCR okuma özellikleri kapalıdır (Sunucu işlemleri reddeder).
2. **Pro Paket (Standart):** 
   * Hızlı pasaport taraması için Google Cloud Vision erişimi içerir.
3. **Premium Paket (Kurumsal):** 
   * Google Vision özelliklerine ek olarak, okunamayan/şüpheli (sarı bayraklı) pasaportların Yapay Zeka (Claude) tarafından yeniden değerlendirilmesi ve düzeltilmesi hakkını içerir.

Bu paketler "Super Admin" panelinden tek tıkla acente bazlı olarak değiştirilebilir. Premium yetkisi olmayan bir kullanıcı, zorlu kart okumalarında Claude sistemini tetikleyemez; böylece gereksiz ve öngörülemeyen API masraflarının önüne geçilir.

## 4. Geliştirme Ön Koşulları ve Sonraki Adımlar
Bu fazın geliştirilmesine başlanmadan önce, Faz 2 (v0.2.0) masaüstü sürümünün sahada aktif operasyonda denenerek tüm kullanım senaryolarının kararlılığından emin olunması tavsiye edilmektedir. Saha testleri tamamlandığında, web tabanlı Super Admin Paneli ve API Sunucusunun kodlanması aşamasına geçilecektir.
