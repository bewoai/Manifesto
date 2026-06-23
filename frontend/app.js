/* ═══════════════════════════════════════════════════════════════════
   İrtifa — App Core (Aetheria Flights Theme)
   Router, State, API Client, Toast, Sidebar, Modal
   ═══════════════════════════════════════════════════════════════════ */

import { icon3d } from '/icons.js';

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
  event.returnValue = 'İrtifa penceresi kapatılsın mı?';
  return event.returnValue;
});

// ─── Sidebar ───
function renderSidebar(activeRoute) {
  const sidebar = document.getElementById('sidebar');
  const navItems = [
    { id: 'dashboard', label: 'Panel', route: 'dashboard' },
    { id: 'weather',   label: 'Hava Durumu', route: 'weather' },
    { id: 'planning',  label: 'Planlama', route: 'planning' },
    { id: 'passport',  label: 'Pasaport', route: 'passport' },
    { id: 'manifest',  label: 'Manifesto', route: 'manifest' },
    { id: 'lists',     label: 'Listeler', route: 'lists' },
  ];
  const bottomItems = [{ id: 'settings', label: 'Ayarlar', route: 'settings' }];

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
      <button class="w-full mt-3 bg-error-container/70 text-on-error-container py-2.5 rounded-2xl text-sm font-medium hover:bg-error-container transition-all flex items-center justify-center gap-2" onclick="window.__shutdownApp()">
        <span class="material-symbols-outlined text-base">power_settings_new</span> Kapat
      </button>
      <div class="px-3 pt-1"><span class="text-xs text-on-surface-variant/40">v0.1.0 — Faz 1</span></div>
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
