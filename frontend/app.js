/* ═══════════════════════════════════════════════════════════════════
   İrtifa — App Core (Aetheria Flights Theme)
   Router, State, API Client, Toast, Sidebar, Modal
   ═══════════════════════════════════════════════════════════════════ */


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
      success: '<span class="material-symbols-outlined text-success">check_circle</span>',
      error: '<span class="material-symbols-outlined text-danger">error</span>',
      warning: '<span class="material-symbols-outlined text-warning">warning</span>',
      info: '<span class="material-symbols-outlined text-info">info</span>',
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
  _resolve: null,
  _settle(value) {
    const resolve = this._resolve;
    this._resolve = null;
    if (resolve) resolve(value);
  },
  open(title, contentHtml, footerHtml = '', opts = {}) {
    // Açık bir onay penceresi başka bir modalla değiştirilirse "vazgeç" sayılır.
    this._settle(false);
    const root = document.getElementById('modal-root');
    root.innerHTML = `
      <div class="modal-overlay" id="modal-overlay">
        <div class="modal ${opts.wide ? 'max-w-6xl' : ''}">
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
    this._settle(false);
  },
  isOpen() {
    return !!document.getElementById('modal-root')?.firstElementChild;
  },
  /**
   * Uygulama içi onay penceresi (window.confirm yerine). Promise<boolean> döner:
   * onay → true; vazgeç / kapat / dışarı tıklama / Esc → false.
   * bodyHtml çağıran tarafından escape edilmiş olmalıdır.
   */
  confirm({ title, bodyHtml = '', confirmLabel = 'Devam Et', cancelLabel = 'Vazgeç', tone = 'primary' } = {}) {
    return new Promise((resolve) => {
      const confirmClass = tone === 'danger' ? 'btn-danger' : 'btn-primary';
      this.open(escapeHtml(title || 'Onay'), bodyHtml, `
        <button type="button" class="btn-secondary" data-modal-cancel>${escapeHtml(cancelLabel)}</button>
        <button type="button" class="${confirmClass}" data-modal-confirm>${escapeHtml(confirmLabel)}</button>
      `);
      this._resolve = resolve;
      const root = document.getElementById('modal-root');
      root.querySelector('[data-modal-cancel]')?.addEventListener('click', () => this.close());
      const ok = root.querySelector('[data-modal-confirm]');
      ok?.addEventListener('click', () => {
        this._settle(true);
        this.close();
      }, { once: true });
      // Güvenli varsayılan: odak "Vazgeç"te (Enter yanlışlıkla onaylamasın)
      root.querySelector('[data-modal-cancel]')?.focus();
    });
  },
};
window.__closeModal = () => modal.close();
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && modal.isOpen()) modal.close();
});

let appShutdownRequested = false;

// ─── Kaydedilmemiş değişiklik kaydı ───
// Sayfalar registerUnsavedCheck(ad, fn) ile "yazılmamış veri var mı?" kontrolü bildirir.
// window.__hasUnsavedChanges() hepsini sorar; pencere yenileme/kapama onayı YALNIZ
// true dönerse istenir (eskiden her yenilemede soruluyordu).
const unsavedChecks = new Map();

function registerUnsavedCheck(name, fn) {
  if (typeof fn === 'function') unsavedChecks.set(name, fn);
  else unsavedChecks.delete(name);
}

window.__hasUnsavedChanges = function() {
  for (const fn of unsavedChecks.values()) {
    try {
      if (fn()) return true;
    } catch (err) {
      console.error('Unsaved-change check failed', err);
    }
  }
  return false;
};

function handleBeforeUnload(event) {
  if (appShutdownRequested) return;
  if (!window.__hasUnsavedChanges()) return;
  event.preventDefault();
  event.returnValue = 'Kaydedilmemiş değişiklikler var. Pencere kapatılsın mı?';
  return event.returnValue;
}

window.__allowReload = () => {
  appShutdownRequested = true;
  window.removeEventListener('beforeunload', handleBeforeUnload);
};

window.addEventListener('beforeunload', handleBeforeUnload);

// ─── Tema ───
// "tuff" (Kısık Tüf, varsayılan) | "graphite" (Yumuşak Grafit). Bilgisayar başına tercih:
// localStorage (pywebview kalıcı depolama kullanır). index.html ilk boyamadan önce uygular.
const THEMES = { tuff: 'Kısık Tüf', graphite: 'Yumuşak Grafit' };
function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'graphite' ? 'graphite' : 'tuff';
}
function applyTheme(theme) {
  const t = theme === 'graphite' ? 'graphite' : 'tuff';
  if (t === 'graphite') document.documentElement.setAttribute('data-theme', 'graphite');
  else document.documentElement.removeAttribute('data-theme');
  try { localStorage.setItem('irtifa-theme', t); } catch (e) { /* depolama kapalıysa yalnız bu oturum */ }
  window.dispatchEvent(new CustomEvent('irtifa-theme', { detail: t }));
  return t;
}
window.__toggleTheme = () => applyTheme(currentTheme() === 'graphite' ? 'tuff' : 'graphite');

// ─── Balon zarf mürekkebi ───
// Her balon kodu sabit bir zarf rengi alır (env-1…env-8). Önce Ayarlar'daki balon sırası,
// bilinmeyen kodlarda kararlı bir hash. style="--env: var(--env-N)" olarak kullanılır.
let knownBalloonCodes = ['BYF', 'BTK', 'BYJ', 'BZR', 'BZV'];
function setBalloonCodes(codes) {
  if (Array.isArray(codes) && codes.length) knownBalloonCodes = codes.map((c) => String(c).toUpperCase());
}
function balloonInkIndex(code) {
  const c = String(code || '').trim().toUpperCase();
  if (!c) return 7;
  const i = knownBalloonCodes.indexOf(c);
  if (i >= 0) return (i % 8) + 1;
  let h = 0;
  for (const ch of c) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return (h % 8) + 1;
}
function balloonInk(code) { return `--env: var(--env-${balloonInkIndex(code)})`; }
function balloonBadge(code, extra = '') {
  const c = String(code || '').trim().toUpperCase();
  if (!c) return '';
  return `<span class="balloon-code ${extra}" style="${balloonInk(c)}">${escapeHtml(c)}</span>`;
}
function envStripe(code) {
  return `<span class="env-stripe" style="${balloonInk(code)}" aria-hidden="true"><i></i><i></i><i></i></span>`;
}

// ─── Menü rayı ───
const NAV_ICONS = {
  dashboard: 'home', weather: 'partly_cloudy_day', planning: 'calendar_month', passport: 'badge',
  manual_review: 'fact_check', manifest: 'assignment', lists: 'format_list_bulleted',
  admin: 'admin_panel_settings', settings: 'settings',
};

// Dar ekranda menü rayı üst üste açılır (md altı); seçimden sonra kapanır.
function setNavOpen(open) {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  sidebar.classList.toggle('hidden', !open);
  sidebar.classList.toggle('flex', open);
  sidebar.classList.toggle('shadow-2xl', open);
  sidebar.classList.toggle('z-[60]', open);
  let scrim = document.getElementById('nav-scrim');
  if (open && !scrim) {
    scrim = document.createElement('div');
    scrim.id = 'nav-scrim';
    scrim.className = 'md:hidden fixed inset-0 z-[55]';
    scrim.style.background = 'rgb(var(--ink) / 0.3)';
    scrim.onclick = () => setNavOpen(false);
    document.body.appendChild(scrim);
  } else if (!open && scrim) {
    scrim.remove();
  }
}
window.__toggleNav = () => setNavOpen(document.getElementById('sidebar')?.classList.contains('hidden'));

function renderSidebar(activeRoute) {
  const sidebar = document.getElementById('sidebar');
  if (window.innerWidth < 768) setNavOpen(false);
  const navItems = [
    { id: 'dashboard', label: 'Ana Sayfa', route: 'dashboard' },
    { id: 'passport',  label: 'Pasaport', route: 'passport' },
    { id: 'manual_review', label: 'Manuel Kontrol', route: 'manual_review' },
    { id: 'planning',  label: 'Planlama', route: 'planning' },
    { id: 'manifest',  label: 'Manifesto', route: 'manifest' },
    { id: 'lists',     label: 'Listeler', route: 'lists' },
    { id: 'weather',   label: 'Hava Durumu', route: 'weather' },
  ];
  const bottomItems = [
    ...(currentUser?.role === 'admin' ? [{ id: 'admin', label: 'Yönetim', route: 'admin' }] : []),
    { id: 'settings', label: 'Ayarlar', route: 'settings' },
  ];

  const navHtml = (items) => items.map((item) => {
    const on = activeRoute === item.route;
    return `
      <a href="#/${item.route}" id="nav-${item.id}" class="nav-item ${on ? 'active' : ''}" ${on ? 'aria-current="page"' : ''}>
        <span class="material-symbols-outlined" aria-hidden="true">${NAV_ICONS[item.id] || 'circle'}</span>
        <span>${item.label}</span>
      </a>`;
  }).join('');

  const user = currentUser?.display_name || currentUser?.username || '';
  sidebar.innerHTML = `
    <a href="#/dashboard" class="px-5 flex items-center gap-3" aria-label="İrtifa ana sayfa">
      <img src="/irtifa-logo.png" alt="" class="w-10 h-10 rounded-lg object-cover" />
      <div class="leading-tight">
        <div class="font-headline text-[22px] font-semibold text-on-surface">İrtifa</div>
        <div class="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">Uçuş planlama</div>
      </div>
    </a>
    <nav class="flex-1 px-3 space-y-0.5 mt-2" aria-label="Ana menü">${navHtml(navItems)}</nav>
    <div class="px-3 mt-auto space-y-0.5">
      ${navHtml(bottomItems)}
      ${!appStatus.licensed ? '<a href="#/settings" class="nav-item" title="OCR kapalı; kimlikler elle girilir. Ayarlar > OCR"><span class="material-symbols-outlined" aria-hidden="true">edit_document</span><span class="flex-1">Manuel mod</span><span class="w-2 h-2 rounded-full bg-warning" aria-hidden="true"></span></a>' : ''}
      <div class="border-t border-line mt-3 pt-3 px-1 flex items-center gap-1">
        <button class="btn-ghost text-sm flex-1 justify-start min-w-0" onclick="window.__logout()" title="Oturumu kapat">
          <span class="material-symbols-outlined text-[19px]">logout</span>
          <span class="truncate">${user ? escapeHtml(user) : 'Çıkış'}</span>
        </button>
        <button class="btn-ghost btn-icon" onclick="window.__toggleTheme()" title="Temayı değiştir (Kısık Tüf / Yumuşak Grafit)" aria-label="Temayı değiştir">
          <span class="material-symbols-outlined text-[19px]">contrast</span>
        </button>
        <button class="btn-ghost btn-icon hover:!text-danger" onclick="window.__shutdownApp()" title="İrtifa'yı kapat" aria-label="Uygulamayı kapat">
          <span class="material-symbols-outlined text-[19px]">power_settings_new</span>
        </button>
      </div>
      <div class="px-3 pt-1 text-[11px] text-on-surface-variant">v${escapeHtml(appStatus.version || '—')}</div>
    </div>
  `;
}

window.__shutdownApp = async function() {
  const ok = await modal.confirm({ title: 'İrtifa kapatılsın mı?', bodyHtml: '<p class="text-on-surface-variant">Açık işlemler yarıda kalabilir.</p>', confirmLabel: 'Kapat', tone: 'danger' });
  if (!ok) return;
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
    button.innerHTML = '<span class="material-symbols-outlined animate-spin">progress_activity</span> Kaydediliyor...';
  }
  try {
    await api.put('/api/settings', {
      irtifa_server_url: 'https://irtifa-ocr-server-1011336814601.europe-west1.run.app',
      irtifa_license_key: key,
      irtifa_license_skipped: false,
      vision_mode: 'irtifa_server'
    });
    toast.success('Başarılı', 'Lisans kaydedildi.');
    await bootWorkspace();
  } catch (err) {
    toast.error('Hata', err.message || 'Lisans kaydetme başarısız.');
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

window.__updateAppStatus = function(status) {
  appStatus.licensed = status.licensed;
  appStatus.skipped = status.skipped;
  if (status.version) appStatus.version = status.version;
  renderSidebar(getRoute());
};

// Kapadokya silueti yalnız giriş/lisans ekranında. Görsel yerel (frontend/public).
const CAPPADOCIA_SVG = '/cappadocia-silhouette.svg';
const cappadociaBackdrop = () =>
  `<img src="${CAPPADOCIA_SVG}" class="cappadocia-backdrop" alt="" aria-hidden="true" />`;

function renderHeader(title, subtitle = '') {
  const header = document.getElementById('page-header');
  header.innerHTML = `
    <div class="flex items-center gap-3 min-w-0">
      <button class="md:hidden btn-ghost btn-icon -ml-2" onclick="window.__toggleNav()" aria-label="Menüyü aç" aria-controls="sidebar">
        <span class="material-symbols-outlined">menu</span>
      </button>
      <h1 class="font-headline text-[24px] font-semibold text-on-surface truncate">${title}</h1>
      ${subtitle ? `<span class="hidden lg:block text-on-surface-variant text-sm truncate">${subtitle}</span>` : ''}
    </div>
    <div class="flex items-center gap-2 shrink-0">
      <button class="btn-ghost btn-icon" id="hdr-refresh" style="display:none" title="Yenile" aria-label="Yenile">
        <span class="material-symbols-outlined">refresh</span>
      </button>
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

  if (pageName !== 'onboarding') {
    // Kurulum sihirbazından başka sayfaya geçilince kabuk geri gelir
    document.getElementById('sidebar').style.display = '';
    document.getElementById('page-header').style.display = '';
    document.querySelector('main')?.classList.add('md:ml-64');
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
      <div class="skeleton h-48"></div>
    </div>
  `;

  try {
    const page = await loadPage(pageName);
    try { sessionStorage.removeItem('irtifa-chunk-reload'); } catch (e) { /* yoksay */ }
    if (page && page.render) {
      pageBody.innerHTML = '';
      await page.render(pageBody);
    }
  } catch (err) {
    console.error('Page load error:', err);
    // Uygulama güncellendikten sonra açık pencere eski parça adlarını ister → bir kez yenile
    if (/dynamically imported module|Importing a module script failed/i.test(String(err?.message))) {
      let reloaded = false;
      try { reloaded = sessionStorage.getItem('irtifa-chunk-reload') === '1'; sessionStorage.setItem('irtifa-chunk-reload', '1'); } catch (e) { /* yoksay */ }
      if (!reloaded) { window.__allowReload?.(); location.reload(); return; }
    }
    pageBody.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon material-symbols-outlined">error</div>
        <div class="empty-title">Sayfa yüklenemedi</div>
        <div class="empty-desc">${escapeHtml(err.message)}</div>
      </div>
    `;
  }
}

// Hash rotası "#/planning?sheet=22.10.2026&row=83" biçiminde sorgu taşıyabilir;
// rota adı "?" öncesidir, parametreler routeParams() ile okunur.
function getRoute() {
  const hash = window.location.hash.replace(/^#\/?/, '');
  return hash.split('?')[0] || 'dashboard';
}

function routeParams() {
  const hash = window.location.hash;
  const q = hash.indexOf('?');
  return new URLSearchParams(q >= 0 ? hash.slice(q + 1) : '');
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
    if (main) main.classList.remove('md:ml-64');
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

  if (!appStatus.licensed && !appStatus.skipped) {
    sidebar.style.display = 'none';
    header.style.display = 'none';
    if (main) main.classList.remove('md:ml-64');
    body.classList.remove('pt-24', 'pb-12');
    await renderLicense(body, currentUser?.role === 'admin');
    return;
  }

  sidebar.style.display = '';
  header.style.display = '';
  if (main) main.classList.add('md:ml-64');
  body.classList.add('pt-24', 'pb-12');
  if (!status.is_setup_complete && getRoute() !== 'onboarding') {
    await navigateTo('onboarding');
  } else {
    await navigateTo(getRoute());
  }
}

function renderAuth(container, setupRequired) {
  container.innerHTML = `
    ${cappadociaBackdrop()}
    <div class="relative z-10 min-h-[80vh] flex items-center justify-center">
      <div class="glass-panel rounded-xl p-8 w-full max-w-md space-y-4">
        <div class="flex items-center gap-4 mb-3">
          <img src="/irtifa-logo.png" class="w-14 h-14 rounded-lg" alt="İrtifa" />
          <div><h1 class="font-headline text-[30px] font-semibold text-on-surface leading-tight">İrtifa</h1><p class="text-on-surface-variant">${setupRequired ? 'İlk yönetici kurulumu' : 'Oturum açın'}</p></div>
        </div>
        ${setupRequired ? `
          <div class="form-group"><label class="form-label">Kullanıcı adı</label><input id="auth-user" class="form-input" value="admin" autocomplete="username" /></div>
          <div class="form-group"><label class="form-label">Ad soyad</label><input id="auth-name" class="form-input" autocomplete="name" /></div>
          <div class="form-group"><label class="form-label">Parola</label><input id="auth-pass" type="password" class="form-input" autocomplete="new-password" onkeydown="if(event.key==='Enter')window.__setupAdmin()" /></div>
          <button class="btn-primary w-full mt-2" onclick="window.__setupAdmin()">Yönetici Hesabını Oluştur</button>
        ` : `
          <div class="form-group"><label class="form-label">Kullanıcı adı</label><input id="auth-user" class="form-input" autocomplete="username" autofocus /></div>
          <div class="form-group"><label class="form-label">Parola</label><input id="auth-pass" type="password" class="form-input" autocomplete="current-password" onkeydown="if(event.key==='Enter')window.__login()" /></div>
          <button class="btn-primary w-full mt-2" onclick="window.__login()">Giriş Yap</button>
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
    ${cappadociaBackdrop()}
    <div class="relative z-10 min-h-[80vh] flex items-center justify-center">
      <div class="glass-panel rounded-xl p-8 w-full max-w-md">
        <div class="flex items-center gap-4 mb-5">
          <img src="/irtifa-logo.png" class="w-14 h-14 rounded-lg" alt="İrtifa" />
          <h1 class="font-headline text-[28px] font-semibold text-on-surface leading-tight">İrtifa'ya hoş geldiniz</h1>
        </div>
        <p class="text-sm text-on-surface-variant mb-6 leading-relaxed">${canConfigure
          ? 'Otomatik MRZ/OCR okuma özelliğini kullanmak için lisans anahtarınızı girin. Lisansınız yoksa manuel giriş ile devam edebilirsiniz.'
          : 'Bu bilgisayarda OCR lisansı henüz yapılandırılmamış. Lisans ayarı için bir yöneticiyle oturum açın.'}</p>
        
        <div class="form-group" style="${canConfigure ? '' : 'display:none'}">
          <label class="form-label">Lisans Anahtarı</label>
          <input id="auth-license" class="form-input" placeholder="Örn: IRTIFA-DEMO-001" onkeydown="if(event.key==='Enter')window.__validateLicense()" />
        </div>
        <div class="form-group mt-4">
          <label class="form-label">Cihaz kimliği (salt okunur)</label>
          <input class="form-input font-mono text-sm text-on-surface-variant" value="${escapeHtml(deviceId)}" readonly />
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
export { api, toast, modal, renderHeader, helpIcon, appStatus, currentUser, registerUnsavedCheck, routeParams,
  applyTheme, currentTheme, THEMES, balloonInk, balloonInkIndex, balloonBadge, envStripe, setBalloonCodes, escapeHtml };
