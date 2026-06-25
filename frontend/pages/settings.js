/* ═══════════════════════════════════════════════════════════════════
   Ayarlar — Vision modu, API key, dosya yolları, KVKK
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, renderHeader } from '/app.js';

let currentSettings = {};

export async function render(container) {
  renderHeader('Ayarlar', 'Sistem yapılandırması ve tercihler');

  container.innerHTML = `
    <div class="max-w-3xl pb-12">
      <!-- Irtifa OCR Servisi -->
      <div class="glass-panel rounded-3xl p-6 mb-6 animate-in">
        <div class="flex items-center gap-3 mb-6">
          <span class="material-symbols-outlined text-primary text-3xl">document_scanner</span>
          <h2 class="font-headline text-headline-sm text-on-surface">İrtifa OCR Servisi</h2>
        </div>
        <div class="form-group" style="display:none;">
          <input type="hidden" id="s-vision-mode" value="irtifa_server" />
        </div>
        <div class="form-group">
          <label class="form-label">Sunucu Adresi</label>
          <input class="form-input" id="s-irtifa-url" type="url" placeholder="https://..." />
          <div class="form-help">İrtifa merkezi OCR sunucu adresi.</div>
        </div>
        <div class="form-group">
          <label class="form-label">Lisans Anahtarı</label>
          <input class="form-input" id="s-irtifa-key" type="password" placeholder="Lisans anahtarınızı girin..." />
          <div class="form-help">Uygulama sağlayıcınız tarafından verilen lisans kodu.</div>
        </div>
        <div class="form-row">
          <div class="form-group flex-1">
            <label class="form-label">Cihaz Kimliği</label>
            <input class="form-input font-mono text-sm" id="s-irtifa-device" readonly />
            <div class="form-help">Bu bilgisayara özel otomatik oluşturulan cihaz kimliği. (Salt Okunur)</div>
          </div>
          <div class="form-group flex items-end">
            <button class="btn-secondary" onclick="window.__testConnection('irtifa_server')">
              <span class="material-symbols-outlined text-base">verified</span>
              Bağlantıyı Test Et ve Kaydet
            </button>
          </div>
        </div>
      </div>
      <!-- Firma ve Operasyon Ayarları -->
      <div class="glass-panel rounded-3xl p-6 mb-6 animate-in" style="animation-delay: 25ms">
        <div class="flex items-center gap-3 mb-6">
          <span class="material-symbols-outlined text-primary text-3xl">storefront</span>
          <h2 class="font-headline text-headline-sm text-on-surface">Firma ve Operasyon Ayarları</h2>
        </div>
        <div class="form-group">
          <label class="form-label">Firmanızın Adı</label>
          <input class="form-input" id="s-company-name" placeholder="Örn: Kapadokya Balloons" />
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="form-group">
            <label class="form-label">Acenteleriniz</label>
            <textarea id="s-agencies" class="form-input h-24" placeholder="Acente 1, Acente 2..."></textarea>
            <div class="form-help">Virgülle ayırın.</div>
          </div>
          <div class="form-group">
            <label class="form-label">Şoförleriniz</label>
            <textarea id="s-drivers" class="form-input h-24" placeholder="Ahmet, Mehmet..."></textarea>
            <div class="form-help">Virgülle ayırın.</div>
          </div>
        </div>
      </div>

      <!-- Veri Kaynağı -->
      <div class="glass-panel rounded-3xl p-6 mb-6 animate-in" style="animation-delay: 50ms">
        <div class="flex items-center gap-3 mb-6">
          <span class="material-symbols-outlined text-primary text-3xl">database</span>
          <h2 class="font-headline text-headline-sm text-on-surface">Veri Kaynağı</h2>
        </div>
        <div class="form-group">
          <label class="form-label">Planlama kaynağı</label>
          <select class="form-select" id="s-data-source">
            <option value="excel">Excel Dosyası</option>
          </select>
          <div class="form-help">Google Sheets desteği deneysel olduğu için operatör arayüzünde geçici olarak gizlenmiştir.</div>
        </div>
        <div class="form-group">
          <label class="form-label">Planlama Excel yolu</label>
          <div class="flex gap-2">
            <input class="form-input flex-1" id="s-planning-xlsx" placeholder="Boş = varsayılan Downloads yolu" />
            <button class="btn-secondary whitespace-nowrap" onclick="window.__settingsImportPlan()">Dosya Seç...</button>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">Google Servis Hesabı JSON</label>
          <input class="form-input" id="s-gsheet-json" placeholder="JSON dosya yolu veya JSON içeriği" />
          <div class="form-help">Bilgi kaydedildiğinde Windows korumalı deposuna taşınır.</div>
        </div>
        <button class="btn-secondary" onclick="window.__testConnection('planning')">Excel Bağlantısını Test Et</button>
      </div>

      <!-- Balon -->
      <div class="glass-panel rounded-3xl p-6 mb-6 animate-in" style="animation-delay: 100ms">
        <div class="flex items-center gap-3 mb-6">
          <span class="material-symbols-outlined text-primary text-3xl">air</span>
          <h2 class="font-headline text-headline-sm text-on-surface">Balon Ayarları</h2>
        </div>
        <div class="form-group">
          <label class="form-label">Balon kapasitesi (kişi)</label>
          <input class="form-input" id="s-balloon-capacity" type="number" min="1" max="28" placeholder="28" />
          <div class="form-help">Her balona en fazla kaç kişi binebilir. Otomatik atama bu sınırı kullanır.</div>
        </div>
        <div class="form-group">
          <label class="form-label">Balon kodları</label>
          <input class="form-input" id="s-balloon-codes" placeholder="BYF, BTK, BYJ, BZR, BZV" />
          <div class="form-help">Virgülle ayır. Yeni rezervasyon bu balonlara sırayla (first-fit) atanır.</div>
        </div>
      </div>

      <!-- Hava Durumu -->
      <div class="glass-panel rounded-3xl p-6 mb-6 animate-in" style="animation-delay: 150ms">
        <div class="flex items-center gap-3 mb-6">
          <span class="material-symbols-outlined text-primary text-3xl">partly_cloudy_day</span>
          <h2 class="font-headline text-headline-sm text-on-surface">Hava Durumu API</h2>
        </div>
        <label class="flex items-center gap-3 cursor-pointer mb-6">
          <input type="checkbox" id="s-weather-enabled" class="w-5 h-5 rounded border-on-surface-variant/30 bg-surface/50 text-primary focus:ring-primary focus:ring-offset-surface" />
          <span class="text-on-surface">Yarım saatte bir hava durumunu takip et</span>
        </label>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Sağlayıcı</label>
            <select class="form-select" id="s-weather-provider">
              <option value="open_meteo">Open-Meteo (anahtarsız)</option>
              <option value="custom">Özel API URL</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Ölçüm aralığı (dk)</label>
            <input class="form-input" id="s-weather-poll" type="number" min="10" max="180" />
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">API URL (custom için)</label>
          <input class="form-input" id="s-weather-url" placeholder="Boşsa Open-Meteo kullanılır" />
        </div>
        <div class="form-group">
          <label class="form-label">Weather API Key</label>
          <input class="form-input" id="s-weather-key" type="password" placeholder="Opsiyonel" />
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Lokasyon adı</label>
            <input class="form-input" id="s-weather-location" placeholder="Goreme Valley" />
          </div>
          <div class="form-group">
            <label class="form-label">Latitude</label>
            <input class="form-input" id="s-weather-lat" placeholder="38.6431" />
          </div>
          <div class="form-group">
            <label class="form-label">Longitude</label>
            <input class="form-input" id="s-weather-lon" placeholder="34.8289" />
          </div>
        </div>
      </div>

      <!-- Çıktı -->
      <div class="glass-panel rounded-3xl p-6 mb-6 animate-in" style="animation-delay: 200ms">
        <div class="flex items-center gap-3 mb-6">
          <span class="material-symbols-outlined text-primary text-3xl">folder_open</span>
          <h2 class="font-headline text-headline-sm text-on-surface">Çıktı Ayarları</h2>
        </div>
        <div class="form-group">
          <label class="form-label">Manifesto şablonu</label>
          <input class="form-input" id="s-template" placeholder="Boş = varsayılan şablon" />
        </div>
        <div class="form-group">
          <label class="form-label">Manifesto çıktı klasörü</label>
          <div class="flex gap-2">
            <input class="form-input flex-1" id="s-output-dir" placeholder="Boş = Documents/Irtifa" />
            <button class="btn-secondary whitespace-nowrap" onclick="window.__settingsImportDir()">Klasör Seç...</button>
          </div>
        </div>
      </div>

      <div class="glass-panel rounded-3xl p-6 mb-6 animate-in">
        <div class="flex items-center gap-3 mb-6">
          <span class="material-symbols-outlined text-primary text-3xl">system_update</span>
          <h2 class="font-headline text-headline-sm text-on-surface">Otomatik Güncelleme</h2>
        </div>
        <div class="form-group"><label class="form-label">Sürüm manifesti URL</label><input class="form-input" id="s-update-url" placeholder="https://.../update.json" /></div>
        <div class="form-group"><label class="form-label">Ed25519 açık anahtar</label><input class="form-input font-mono" id="s-update-key" placeholder="Base64 açık anahtar" /></div>
      </div>

      <!-- KVKK -->
      <div class="glass-panel rounded-3xl p-6 mb-6 animate-in" style="animation-delay: 250ms">
        <div class="flex items-center gap-3 mb-6">
          <span class="material-symbols-outlined text-primary text-3xl">shield_lock</span>
          <h2 class="font-headline text-headline-sm text-on-surface">Gizlilik (KVKK)</h2>
        </div>
        <label class="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" id="s-delete-images" class="w-5 h-5 rounded border-on-surface-variant/30 bg-surface/50 text-primary focus:ring-primary focus:ring-offset-surface" />
          <span class="text-on-surface">Yazımdan sonra pasaport fotoğraflarını silmeyi sor</span>
        </label>
        <div class="form-help mt-2">Ham pasaport fotoğraflarının gereksiz saklanmaması için planlamaya yazma işleminden sonra silmeyi sorar.</div>
      </div>

      <!-- Save -->
      <div class="flex gap-4 animate-in" style="animation-delay: 300ms">
        <button class="btn btn-primary" onclick="window.__saveSettings()">
          <span class="material-symbols-outlined text-xl">save</span>
          Ayarları Kaydet
        </button>
        <button class="btn btn-secondary" onclick="window.__reloadSettings()">
          <span class="material-symbols-outlined text-xl">refresh</span>
          Yenile
        </button>
      </div>
    </div>
  `;

  loadSettings();
}


async function loadSettings() {
  try {
    const s = await api.get('/api/settings');
    currentSettings = s;
    fillForm(s);
  } catch (err) {
    toast.error('Ayarlar yüklenemedi', err.message);
  }
}

function fillForm(s) {
  const val = (id, v) => { const el = document.getElementById(id); if (el) el.value = (v === null || v === undefined) ? '' : v; };
  const chk = (id, v) => { const el = document.getElementById(id); if (el) el.checked = !!v; };

  val('s-irtifa-url', s.irtifa_server_url);
  val('s-irtifa-key', ''); // Don't show masked key
  val('s-irtifa-device', s.irtifa_device_id);
  val('s-data-source', s.data_source);
  val('s-planning-xlsx', s.planning_xlsx);
  val('s-gsheet-json', s.google_credentials_json);

  // Firma ve Operasyon
  val('s-company-name', s.company_name);
  if (s.operation_options) {
    val('s-agencies', s.operation_options.agency ? s.operation_options.agency.join(', ') : '');
    val('s-drivers', s.operation_options.driver ? s.operation_options.driver.join(', ') : '');
  }

  val('s-update-url', s.update_manifest_url);
  val('s-update-key', s.update_public_key);
  val('s-template', s.manifest_template);
  val('s-output-dir', s.output_dir);
  val('s-balloon-capacity', s.balloon_capacity);
  val('s-balloon-codes', Array.isArray(s.balloon_codes) ? s.balloon_codes.join(', ') : '');
  chk('s-weather-enabled', s.weather_enabled);
  val('s-weather-provider', s.weather_provider);
  val('s-weather-poll', s.weather_poll_minutes);
  val('s-weather-url', s.weather_api_url);
  val('s-weather-key', '');
  val('s-weather-location', s.weather_location_name);
  val('s-weather-lat', s.weather_latitude);
  val('s-weather-lon', s.weather_longitude);
  chk('s-delete-images', s.delete_images_after_write);
}

window.__settingsImportPlan = async function() {
  const { toast } = await import('/app.js');
  try {
    const res = await api.post('/api/planning/import-existing', {});
    if (res.success) {
      document.getElementById('s-planning-xlsx').value = res.path;
      toast.success('Başarılı', res.message + " (Değişiklikleri kaydetmeyi unutmayın)");
    } else {
      if (res.message !== 'İptal edildi') toast.error('Hata', res.message);
    }
  } catch (err) {
    toast.error('Hata', err.message);
  }
};

window.__settingsImportDir = async function() {
  const { toast } = await import('/app.js');
  try {
    const res = await api.post('/api/settings/import-directory', {});
    if (res.success) {
      document.getElementById('s-output-dir').value = res.path;
      toast.success('Başarılı', res.message + " (Değişiklikleri kaydetmeyi unutmayın)");
    } else {
      if (res.message !== 'İptal edildi') toast.error('Hata', res.message);
    }
  } catch (err) {
    toast.error('Hata', err.message);
  }
};

window.__saveSettings = async function() {
  const gv = (id) => document.getElementById(id)?.value?.trim() || '';
  const gc = (id) => document.getElementById(id)?.checked || false;

  const body = {
    vision_mode: 'irtifa_server',
    irtifa_server_url: gv('s-irtifa-url'),
    data_source: gv('s-data-source'),
    planning_xlsx: gv('s-planning-xlsx'),
    google_credentials_json: gv('s-gsheet-json'),
    company_name: gv('s-company-name'),
    operation_options: {
      agency: gv('s-agencies').split(',').map(s => s.trim()).filter(Boolean),
      driver: gv('s-drivers').split(',').map(s => s.trim()).filter(Boolean)
    },
    update_manifest_url: gv('s-update-url'),
    update_public_key: gv('s-update-key'),
    manifest_template: gv('s-template'),
    output_dir: gv('s-output-dir'),
    delete_images_after_write: gc('s-delete-images'),
    weather_enabled: gc('s-weather-enabled'),
    weather_provider: gv('s-weather-provider'),
    weather_api_url: gv('s-weather-url'),
    weather_location_name: gv('s-weather-location'),
    weather_latitude: gv('s-weather-lat'),
    weather_longitude: gv('s-weather-lon'),
  };

  // Balon ayarları
  const cap = parseInt(gv('s-balloon-capacity'), 10);
  if (cap) body.balloon_capacity = cap;
  const codes = gv('s-balloon-codes');
  if (codes) body.balloon_codes = codes.split(',').map(c => c.trim().toUpperCase()).filter(Boolean);
  const poll = parseInt(gv('s-weather-poll'), 10);
  if (poll) body.weather_poll_minutes = poll;

  // Only include API key if user typed something new
  const irtifaKey = gv('s-irtifa-key');
  if (irtifaKey) body.irtifa_license_key = irtifaKey;
  
  const weatherKey = gv('s-weather-key');
  if (weatherKey) body.weather_api_key = weatherKey;

  try {
    const saved = await api.put('/api/settings', body);
    currentSettings = saved;
    toast.success('Ayarlar kaydedildi', 'Tüm değişiklikler uygulandı');
    
    const { appStatus } = await import('/app.js');
    const status = await api.get('/api/app/status');
    if (status.licensed !== appStatus.licensed) {
      setTimeout(() => window.location.reload(), 1000);
    }
  } catch (err) {
    toast.error('Kaydetme hatası', err.message);
  }
};

window.__reloadSettings = function() {
  loadSettings();
  toast.info('Yenilendi', 'Ayarlar sunucudan tekrar yüklendi');
};

window.__testConnection = async function(target) {
  try {
    const payload = { target };
    if (target === 'irtifa_server') {
      payload.irtifa_server_url = document.getElementById('s-irtifa-url')?.value?.trim();
      payload.irtifa_license_key = document.getElementById('s-irtifa-key')?.value?.trim();
    }
    const data = await api.post('/api/settings/test', payload);
    toast.success('Bağlantı başarılı', data.message);
    
    // Test başarılıysa otomatik kaydet
    await window.__saveSettings();
  } catch (err) { toast.error('Bağlantı testi başarısız', err.message); }
};
