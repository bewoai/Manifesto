/* ═══════════════════════════════════════════════════════════════════
   Balon Manifesto — App Core (Aetheria Flights Theme)
   Router, State, API Client, Toast, Sidebar, Modal
   ═══════════════════════════════════════════════════════════════════ */

// ─── API Client ───
const api = {
  async get(url) {
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
  async post(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
  async put(url, body) {
    const res = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
  async upload(url, files, extraFields = {}) {
    const form = new FormData();
    for (const f of files) form.append('files', f);
    for (const [k, v] of Object.entries(extraFields)) form.append(k, v);
    const res = await fetch(url, { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
  downloadUrl(url) { return url; },
};

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
        <div class="toast-title">${title}</div>
        ${message ? `<div class="toast-message">${message}</div>` : ''}
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

window.addEventListener('beforeunload', (event) => {
  if (appShutdownRequested) return;
  event.preventDefault();
  event.returnValue = 'Uygulamayı kapatmadan tarayıcıyı kapatma.';
  return event.returnValue;
});

// ─── Sidebar ───
function renderSidebar(activeRoute) {
  const sidebar = document.getElementById('sidebar');
  const navItems = [
    { id: 'dashboard', icon: 'rocket_launch', label: 'Dashboard', route: 'dashboard' },
    { id: 'weather',   icon: 'cloudy_snowing', label: 'Hava Durumu', route: 'weather' },
    { id: 'planning',  icon: 'calendar_month', label: 'Planlama', route: 'planning' },
    { id: 'passport',  icon: 'badge',          label: 'Pasaport', route: 'passport' },
    { id: 'manifest',  icon: 'description',    label: 'Manifesto', route: 'manifest' },
    { id: 'lists',     icon: 'list_alt',       label: 'Listeler', route: 'lists' },
  ];
  const bottomItems = [
    { id: 'settings', icon: 'settings', label: 'Ayarlar', route: 'settings' },
  ];

  sidebar.innerHTML = `
    <div class="px-8 mb-4">
      <h2 class="font-headline text-headline-sm text-primary tracking-tight">Balon Manifesto</h2>
      <p class="text-label-md text-on-surface-variant opacity-70">Uçuş Planlama Sistemi</p>
    </div>
    <nav class="flex-1 px-4 space-y-1">
      ${navItems.map(item => `
        <a class="${activeRoute === item.route
          ? 'flex items-center gap-4 bg-primary-container text-on-primary-container rounded-full px-6 py-3 shadow-lg shadow-primary-container/20 transition-transform scale-105'
          : 'flex items-center gap-4 text-on-surface-variant px-6 py-3 hover:bg-white/10 hover:rounded-full transition-all duration-500'
        }" href="#/${item.route}" data-route="${item.route}" id="nav-${item.id}">
          <span class="material-symbols-outlined">${item.icon}</span>
          <span class="text-label-md">${item.label}</span>
        </a>
      `).join('')}
    </nav>
    <div class="px-4 mt-auto space-y-2">
      ${bottomItems.map(item => `
        <a class="${activeRoute === item.route
          ? 'flex items-center gap-4 bg-primary-container text-on-primary-container rounded-full px-6 py-3 shadow-lg shadow-primary-container/20'
          : 'flex items-center gap-4 text-on-surface-variant px-6 py-2 opacity-60 hover:opacity-100 hover:bg-white/5 rounded-lg transition-all'
        }" href="#/${item.route}" id="nav-${item.id}">
          <span class="material-symbols-outlined">${item.icon}</span>
          <span class="text-label-md">${item.label}</span>
        </a>
      `).join('')}
      <button class="w-full mt-6 bg-error-container text-on-error-container py-3 rounded-full text-label-md hover:brightness-110 transition-all" onclick="window.__shutdownApp()">
        Kapat
      </button>
    </div>
    <div class="px-8 mt-4">
      <span class="text-xs text-on-surface-variant/40">v0.1.0 — Faz 1</span>
    </div>
  `;
}

window.__shutdownApp = async function() {
  if (!confirm('Balon Manifesto kapatılsın mı?')) return;
  appShutdownRequested = true;
  try {
    await api.post('/api/app/shutdown', {});
  } catch (err) {
    appShutdownRequested = false;
    toast.error('Kapatılamadı', err.message);
  }
};

function renderHeader(title, subtitle = '') {
  const header = document.getElementById('page-header');
  header.innerHTML = `
    <div class="flex items-center gap-4">
      <h1 class="font-headline text-headline-md text-primary tracking-tight">${title}</h1>
      ${subtitle ? `<span class="hidden lg:block text-on-surface-variant text-sm">— ${subtitle}</span>` : ''}
    </div>
    <div class="flex items-center gap-4">
      <button class="btn-ghost btn-icon" id="hdr-refresh" style="display:none">
        <span class="material-symbols-outlined">refresh</span>
      </button>
      <div class="w-9 h-9 rounded-full bg-primary-container/30 flex items-center justify-center">
        <span class="material-symbols-outlined text-primary text-lg">person</span>
      </div>
    </div>
  `;
}

// ─── Router ───
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
  const pageName = route || 'dashboard';

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
        <div class="empty-icon">😵</div>
        <div class="empty-title">Sayfa yüklenemedi</div>
        <div class="empty-desc">${err.message}</div>
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
  navigateTo(getRoute());
});

// Export for pages
export { api, toast, modal, renderHeader };
