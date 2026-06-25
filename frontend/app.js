/* ═══════════════════════════════════════════════════════════════════
   İrtifa — App Core (Aetheria Flights Theme)
   Router, State, API Client, Toast, Sidebar, Modal
   ═══════════════════════════════════════════════════════════════════ */

import { icon3d } from '/icons.js';

// ─── API Client ───
class ApiError extends Error {
  constructor(message, detail, status) {
    super(message);
    this.detail = detail;
    this.status = status;
  }
}

async function parseResponse(res) {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    const message = typeof detail === 'string' ? detail : (detail?.message || `HTTP ${res.status}`);
    throw new ApiError(message, detail, res.status);
  }
  return res.json();
}

const api = {
  async get(url) {
    const res = await fetch(url);
    return parseResponse(res);
  },
  async post(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return parseResponse(res);
  },
  async put(url, body) {
    const res = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return parseResponse(res);
  },
  async upload(url, files, extraFields = {}) {
    const form = new FormData();
    for (const f of files) form.append('files', f);
    for (const [k, v] of Object.entries(extraFields)) form.append(k, v);
    const res = await fetch(url, { method: 'POST', body: form });
    return parseResponse(res);
  },
  downloadUrl(url) { return url; },
};

let currentUser = null;
let appStatus = { licensed: false, skipped: false, version: '' };

// ─── Toast Notification System ───
const toast = {
  _container: null,
  init() { this._container = document.getElementById('toast-container'); },

  show(type, title, message = '', duration = 4000) {
    if (!this._container) this.init();
    const icons = {
      success: '<span class="material-symbols-outlined text-green-400">check_circle</span>',
      error: '<span class="material-symbols-outlined text-red-400">error</span>',
      warning: '<span class="material-symbols-outlined text-yellow-400">warning</span>',
      info: '<span class="material-symbols-outlined text-primary">info</span>',
    };
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `
      <span class="toast-icon">${icons[type] || icons.info}</span>
      <div class="flex-1 min-w-0">
        <div class="toast-title">${escapeHtml(title)}</div>
        ${message ? `<div class="toast-message">${escapeHtml(message)}</div>` : ''}
      </div>
      <button class="toast-close" onclick="this.closest('.toast').remove()">
        <span class="material-symbols-outlined text-sm">close</span>
      </button>
      <div class="toast-progress" style="animation-duration:${duration}ms"></div>
    `;
    this._container.appendChild(el);
    setTimeout(() => {
      el.classList.add('leaving');
      setTimeout(() => el.remove(), 200);
    }, duration);
  },

  success(title, msg) { this.show('success', title, msg); },
  error(title, msg)   { this.show('error', title, msg, 6000); },
  warning(title, msg) { this.show('warning', title, msg, 5000); },
  info(title, msg)    { this.show('info', title, msg); },
};

// ─── Modal System ───
const modal = {
  open(title, contentHtml, footerHtml = '') {
    const root = document.getElementById('modal-root');
    root.innerHTML = `
      <div class="modal-overlay" id="modal-overlay">
        <div class="modal">
          <div class="modal-header">
            <h3>${title}</h3>
            <button class="btn-ghost btn-icon" onclick="window.__closeModal()">
              <span class="material-symbols-outlined">close</span>
            </button>
          </div>
          <div class="modal-body">${contentHtml}</div>
          ${footerHtml ? `<div class="modal-footer">${footerHtml}</div>` : ''}
        </div>
      </div>
    `;
    root.querySelector('.modal-overlay').addEventListener('click', (e) => {
      if (e.target.classList.contains('modal-overlay')) this.close();
    });
  },
  close() {
    document.getElementById('modal-root').innerHTML = '';
  },
};
window.__closeModal = () => modal.close();

let appShutdownRequested = false;

window.__allowReload = () => { appShutdownRequested = true; };

window.addEventListener('beforeunload', (event) => {
  if (appShutdownRequested) return;
  event.preventDefault();
  event.returnValue = 'İrtifa penceresi kapatılsın mı?';
  return event.returnValue;
});

// ─── Sidebar ───

// ─── Sidebar ───
function renderSidebar(activeRoute) {
  const sidebar = document.getElementById('sidebar');
  const navItems = [
    { id: 'dashboard', label: 'Panel', route: 'dashboard' },
    { id: 'weather',   label: 'Hava Durumu', route: 'weather' },
    { id: 'planning',  label: 'Planlama', route: 'planning' },
    { id: 'passport',  label: 'Pasaport', route: 'passport' },
    { id: 'manual_review', label: 'Manuel Kontrol', route: 'manual_review' },
    { id: 'manifest',  label: 'Manifesto', route: 'manifest' },
    { id: 'lists',     label: 'Listeler', route: 'lists' },
  ];
  const bottomItems = [
    ...(currentUser?.role === 'admin'
      ? [
          { id: 'admin', label: 'Yönetim', route: 'admin' },
        ]
      : []),
    { id: 'settings', label: 'Ayarlar', route: 'settings' },
  ];

  const navHtml = (items) => items.map((item) => {
    const on = activeRoute === item.route;
    return `
      <a href="#/${item.route}" id="nav-${item.id}"
         class="group flex items-center gap-3.5 px-3.5 py-2.5 rounded-2xl transition-all ${on
           ? 'bg-white/10 ring-1 ring-white/15 shadow-lg shadow-black/20'
           : 'hover:bg-white/5'}">
        <span class="block transition-transform group-hover:-translate-y-0.5 ${on ? '' : 'opacity-90 group-hover:opacity-100'}">${icon3d(item.id, 30)}</span>
        <span class="text-[15px] font-medium ${on ? 'text-on-surface' : 'text-on-surface-variant group-hover:text-on-surface'}">${item.label}</span>
      </a>`;
  }).join('');

  sidebar.innerHTML = `
    <div class="px-6 flex items-center gap-3">
      <img src="/irtifa-logo.png" alt="İrtifa" class="w-12 h-12 rounded-2xl object-cover shadow-lg shadow-black/25 ring-1 ring-white/10" />
      <div>
        <h2 class="font-headline text-xl text-on-surface leading-tight tracking-tight">İrtifa</h2>
        <p class="text-xs text-on-surface-variant/70">Kapadokya Uçuş Sistemi</p>
      </div>
    </div>
    <nav class="flex-1 px-4 space-y-1.5 mt-6">${navHtml(navItems)}</nav>
    <div class="px-4 mt-auto space-y-2">
      ${navHtml(bottomItems)}
      ${!appStatus.licensed ? '<div class="w-full bg-warning/20 text-warning py-2.5 rounded-2xl text-sm font-medium flex items-center justify-center gap-2 mb-2 mt-2"><span class="material-symbols-outlined text-base">edit_document</span> Manuel Mod</div>' : ''}
      <button class="w-full bg-white/5 text-on-surface-variant py-2.5 rounded-2xl text-sm font-medium hover:bg-white/10 transition-all flex items-center justify-center gap-2" onclick="window.__logout()">
        <span class="material-symbols-outlined text-base">logout</span> Çıkış
      </button>
      <button class="w-full mt-3 bg-error-container/70 text-on-error-container py-2.5 rounded-2xl text-sm font-medium hover:bg-error-container transition-all flex items-center justify-center gap-2" onclick="window.__shutdownApp()">
        <span class="material-symbols-outlined text-base">power_settings_new</span> Kapat
      </button>
      <div class="px-3 pt-1"><span class="text-xs text-on-surface-variant/40">v${escapeHtml(appStatus.version || '—')}</span></div>
    </div>
  `;
}

window.__shutdownApp = async function() {
  if (!confirm('İrtifa kapatılsın mı?')) return;
  appShutdownRequested = true;
  try {
    await api.post('/api/app/shutdown', {});
  } catch (err) {
    appShutdownRequested = false;
    toast.error('Kapatılamadı', err.message);
  }
};

window.__logout = async function() {
  try {
    await api.post('/api/auth/logout', {});
  } finally {
    currentUser = null;
    appStatus = { licensed: false, skipped: false, version: '' };
    await bootAuth();
  }
};

window.__validateLicense = async function() {
  const key = document.getElementById('auth-license').value.trim();
  if (!key) return toast.error('Hata', 'Lisans anahtarı boş olamaz.');
  const button = document.getElementById('license-submit');
  if (button) {
    button.disabled = true;
    button.innerHTML = '<span class="material-symbols-outlined animate-spin">progress_activity</span> Doğrulanıyor...';
  }
  try {
    const res = await api.post('/api/settings/test', {
      target: 'irtifa_server',
      irtifa_server_url: 'https://irtifa-ocr-server-1011336814601.europe-west1.run.app',
      irtifa_license_key: key
    });
    if (res.success) {
      await api.put('/api/settings', {
        irtifa_server_url: 'https://irtifa-ocr-server-1011336814601.europe-west1.run.app',
        irtifa_license_key: key,
        irtifa_license_skipped: false,
        vision_mode: 'irtifa_server'
      });
      toast.success('Başarılı', 'Lisans doğrulandı.');
      await bootWorkspace();
    } else {
      toast.error('Hata', 'Lisans anahtarı geçersiz. Lütfen kontrol edin.');
    }
  } catch (err) {
    toast.error('Hata', err.message || 'Lisans doğrulama başarısız.');
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = 'Lisansı Doğrula ve Devam Et';
    }
  }
};

window.__skipLicense = async function() {
  try {
    await api.post('/api/app/skip_license', {});
    await bootWorkspace();
  } catch (err) { toast.error('Hata', err.message); }
};

function renderHeader(title, subtitle = '') {
  const header = document.getElementById('page-header');
  header.innerHTML = `
    <div class="flex items-center gap-4">
      <h1 class="font-headline text-headline-md text-on-surface tracking-tight">${title}</h1>
      ${subtitle ? `<span class="hidden lg:block text-on-surface-variant text-sm">— ${subtitle}</span>` : ''}
    </div>
    <div class="flex items-center gap-4">
      <button class="btn-ghost btn-icon" id="hdr-refresh" style="display:none">
        <span class="material-symbols-outlined">refresh</span>
      </button>
      <div class="w-9 h-9 rounded-full bg-primary-container/30 flex items-center justify-center">
        <span class="material-symbols-outlined text-primary text-lg" title="${escapeHtml(currentUser?.display_name || currentUser?.username || 'Kullanıcı')}">person</span>
      </div>
    </div>
  `;
}
const pages = {};

async function loadPage(name) {
  if (!pages[name]) {
    const mod = await import(`./pages/${name}.js`);
    pages[name] = mod;
  }
  return pages[name];
}

async function navigateTo(route) {
  const pageBody = document.getElementById('page-body');
  let pageName = route || 'dashboard';
  if (['admin'].includes(pageName) && currentUser?.role !== 'admin') {
    pageName = 'dashboard';
    window.location.hash = '#/dashboard';
  }

  renderSidebar(pageName);

  // Skeleton loading
  pageBody.innerHTML = `
    <div class="space-y-6">
      <div class="skeleton skeleton-title"></div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div class="skeleton skeleton-card"></div>
        <div class="skeleton skeleton-card"></div>
        <div class="skeleton skeleton-card"></div>
      </div>
      <div class="skeleton h-48 rounded-3xl"></div>
    </div>
  `;

  try {
    const page = await loadPage(pageName);
    if (page && page.render) {
      pageBody.innerHTML = '';
      await page.render(pageBody);
    }
  } catch (err) {
    console.error('Page load error:', err);
    pageBody.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon material-symbols-outlined">error</div>
        <div class="empty-title">Sayfa yüklenemedi</div>
        <div class="empty-desc">${escapeHtml(err.message)}</div>
      </div>
    `;
  }
}

function getRoute() {
  const hash = window.location.hash.replace('#/', '').replace('#', '');
  return hash || 'dashboard';
}

// ─── Init ───
window.addEventListener('hashchange', () => navigateTo(getRoute()));

document.addEventListener('DOMContentLoaded', () => {
  toast.init();
  bootAuth();
});

async function bootAuth() {
  const sidebar = document.getElementById('sidebar');
  const header = document.getElementById('page-header');
  const body = document.getElementById('page-body');
  const main = document.querySelector('main');
  try {
    const status = await api.get('/api/auth/status');
    currentUser = status.user || null;
    if (currentUser) {
      await bootWorkspace(status);
      return;
    }
    sidebar.style.display = 'none';
    header.style.display = 'none';
    if (main) main.classList.remove('md:ml-72');
    body.classList.remove('pt-24', 'pb-12');
    renderAuth(body, status.setup_required);
  } catch (err) {
    body.innerHTML = `<div class="empty-state"><div class="empty-title">İrtifa başlatılamadı</div><div class="empty-desc">${escapeHtml(err.message)}</div></div>`;
  }
}

async function bootWorkspace(authStatus = {}) {
  const sidebar = document.getElementById('sidebar');
  const header = document.getElementById('page-header');
  const body = document.getElementById('page-body');
  const main = document.querySelector('main');
  const status = await api.get('/api/app/status');
  appStatus.licensed = status.licensed;
  appStatus.skipped = status.skipped;
  appStatus.version = status.version || '';

  if (!appStatus.licensed) {
    sidebar.style.display = 'none';
    header.style.display = 'none';
    if (main) main.classList.remove('md:ml-72');
    body.classList.remove('pt-24', 'pb-12');
    await renderLicense(body, currentUser?.role === 'admin');
    return;
  }

  sidebar.style.display = '';
  header.style.display = '';
  if (main) main.classList.add('md:ml-72');
  body.classList.add('pt-24', 'pb-12');
  if (!status.is_setup_complete && getRoute() !== 'onboarding') {
    await navigateTo('onboarding');
  } else {
    await navigateTo(getRoute());
  }
}

function renderAuth(container, setupRequired) {
  container.innerHTML = `
    <div class="min-h-[80vh] flex items-center justify-center">
      <div class="glass-panel rounded-3xl p-8 w-full max-w-md">
        <div class="flex items-center gap-4 mb-7">
          <img src="/irtifa-logo.png" class="w-16 h-16 rounded-2xl" alt="İrtifa" />
          <div><h1 class="font-headline text-3xl text-on-surface">İrtifa</h1><p class="text-on-surface-variant">${setupRequired ? 'İlk yönetici kurulumu' : 'Oturum aç'}</p></div>
        </div>
        ${setupRequired ? `
          <div class="form-group"><label class="form-label">Kullanıcı adı</label><input id="auth-user" class="form-input" value="admin" autocomplete="username" /></div>
          <div class="form-group"><label class="form-label">Ad soyad</label><input id="auth-name" class="form-input" autocomplete="name" /></div>
          <div class="form-group"><label class="form-label">Parola</label><input id="auth-pass" type="password" class="form-input" autocomplete="new-password" onkeydown="if(event.key==='Enter')window.__setupAdmin()" /></div>
          <button class="btn-primary w-full mt-4" onclick="window.__setupAdmin()">Yönetici Hesabını Oluştur</button>
        ` : `
          <div class="form-group"><label class="form-label">Kullanıcı adı</label><input id="auth-user" class="form-input" autocomplete="username" autofocus /></div>
          <div class="form-group"><label class="form-label">Parola</label><input id="auth-pass" type="password" class="form-input" autocomplete="current-password" onkeydown="if(event.key==='Enter')window.__login()" /></div>
          <button class="btn-primary w-full mt-4" onclick="window.__login()">Giriş Yap</button>
        `}
      </div>
    </div>`;
}

window.__setupAdmin = async function() {
  try {
    const data = await api.post('/api/auth/setup', {
      username: document.getElementById('auth-user').value.trim(),
      display_name: document.getElementById('auth-name').value.trim(),
      password: document.getElementById('auth-pass').value,
    });
    alert(`Kurtarma kodunuz:\n\n${data.recovery_code}\n\nBu kod yalnızca bir kez gösterilir. Güvenli bir yerde saklayın.`);
    currentUser = data.user;
    await bootWorkspace();
  } catch (err) {
    toast.error('Kurulum başarısız', err.message);
  }
};

window.__login = async function() {
  try {
    const data = await api.post('/api/auth/login', {
      username: document.getElementById('auth-user').value.trim(),
      password: document.getElementById('auth-pass').value,
    });
    currentUser = data.user;
    await bootWorkspace();
  } catch (err) {
    toast.error('Giriş başarısız', err.message);
  }
};

async function renderLicense(container, canConfigure) {
  let deviceId = '';
  try {
    const settings = await api.get('/api/settings');
    deviceId = settings.irtifa_device_id || '';
  } catch(e) {}

  container.innerHTML = `
    <div class="min-h-[80vh] flex items-center justify-center">
      <div class="glass-panel rounded-3xl p-8 w-full max-w-md">
        <div class="flex items-center gap-4 mb-7">
          <img src="/irtifa-logo.png" class="w-16 h-16 rounded-2xl" alt="İrtifa" />
          <div>
            <h1 class="font-headline text-3xl text-on-surface">İrtifa'ya Hoş Geldiniz</h1>
          </div>
        </div>
        <p class="text-sm text-on-surface-variant mb-6 leading-relaxed">${canConfigure
          ? 'Otomatik MRZ/OCR okuma özelliğini kullanmak için lisans anahtarınızı girin. Lisansınız yoksa manuel giriş ile devam edebilirsiniz.'
          : 'Bu bilgisayarda OCR lisansı henüz yapılandırılmamış. Lisans ayarı için bir yöneticiyle oturum açın.'}</p>
        
        <div class="form-group" style="${canConfigure ? '' : 'display:none'}">
          <label class="form-label">Lisans Anahtarı</label>
          <input id="auth-license" class="form-input" placeholder="Örn: IRTIFA-DEMO-001" onkeydown="if(event.key==='Enter')window.__validateLicense()" />
        </div>
        <div class="form-group opacity-60">
          <label class="form-label">Cihaz Kimliği (Salt Okunur)</label>
          <input class="form-input" value="${escapeHtml(deviceId)}" readonly />
        </div>
        
        <div class="flex flex-col gap-3 mt-6">
          ${canConfigure ? `
            <button class="btn-primary w-full flex items-center justify-center gap-2" id="license-submit" onclick="window.__validateLicense()">Lisansı Doğrula ve Devam Et</button>
            <button class="btn-secondary w-full" onclick="window.__skipLicense()">Manuel Modda Devam Et</button>
          ` : `
            <button class="btn-secondary w-full" onclick="window.__logout()">Farklı Kullanıcıyla Giriş Yap</button>
          `}
        </div>
      </div>
    </div>`;
}

function helpIcon(text) {
  return `<button type="button" class="help-icon" aria-label="Alan açıklaması" data-help="${escapeHtml(text)}">?</button>`;
}

function escapeHtml(value) {
  return String(value || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Export for pages
export { api, toast, modal, renderHeader, helpIcon, appStatus, currentUser };
