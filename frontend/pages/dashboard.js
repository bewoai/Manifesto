import { api, toast, renderHeader } from '/app.js';

export async function render(container) {
  renderHeader('Bugünün Operasyonu', 'Günü hazırlayın, eksikleri tamamlayın ve çıktıları alın');
  container.innerHTML = `
    <div id="today-weather" class="mb-5"></div>
    <div class="card mb-6">
      <div class="card-header">
        <div class="card-title"><span class="material-symbols-outlined">route</span> Operasyon Akışı</div>
        <select class="form-select max-w-[220px]" id="dash-sheet" onchange="window.__dashLoad()"></select>
      </div>
      <div id="operation-steps" class="grid grid-cols-1 xl:grid-cols-5 gap-3"></div>
    </div>
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
      <div class="card lg:col-span-2">
        <div class="card-header"><div class="card-title"><span class="material-symbols-outlined">warning</span> Tamamlanması Gerekenler</div></div>
        <div id="dash-issues"></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="material-symbols-outlined">monitoring</span> Gün Özeti</div></div>
        <div id="dash-summary" class="space-y-3"></div>
      </div>
    </div>`;
  await loadDashboard();
}

async function loadDashboard() {
  try {
    const sheetsData = await api.get('/api/planning/sheets');
    const sheets = sheetsData.sheets || [];
    const select = document.getElementById('dash-sheet');
    select.innerHTML = sheets.map(sheet => `<option value="${esc(sheet)}">${esc(sheet)}</option>`).join('');
    if (sheets.length) select.value = sheets[sheets.length - 1];
    await Promise.all([window.__dashLoad(), loadWeather()]);
  } catch (err) {
    toast.error('Operasyon paneli yüklenemedi', err.message);
  }
}

window.__dashLoad = async function() {
  const sheet = document.getElementById('dash-sheet')?.value;
  if (!sheet) return;
  try {
    const data = await api.get(`/api/planning/load?sheet=${encodeURIComponent(sheet)}`);
    renderSteps(data);
    renderIssues(data.readiness || {});
    renderSummary(data);
  } catch (err) {
    toast.error('Gün yüklenemedi', err.message);
  }
};

async function loadWeather() {
  const root = document.getElementById('today-weather');
  try {
    const data = await api.get('/api/weather/status');
    const decision = data.decision || {};
    root.innerHTML = `
      <div class="glass-panel rounded-2xl px-5 py-3 flex flex-wrap items-center gap-4">
        <span class="material-symbols-outlined text-primary">partly_cloudy_day</span>
        <strong class="text-on-surface">Hava tavsiyesi: ${esc(decision.title || 'Veri bekleniyor')}</strong>
        <span class="text-sm text-on-surface-variant flex-1">${esc(decision.summary || '')}</span>
        <a href="#/weather" class="btn-ghost px-3 py-1.5">Detay</a>
      </div>`;
  } catch (err) {
    root.innerHTML = `<div class="glass-panel rounded-2xl px-5 py-3 text-on-surface-variant">Hava verisi çevrimdışı. Son kayıt kullanılamadı.</div>`;
  }
}

function renderSteps(data) {
  const readiness = data.readiness || {};
  const total = readiness.total_passengers || 0;
  const missingIdentity = readiness.counts?.missing_identity || 0;
  const steps = [
    ['1', 'Gün Seçimi', data.sheet, 'planning', true],
    ['2', 'Rezervasyonlar', `${data.total_blocks || 0} blok`, 'planning', (data.total_blocks || 0) > 0],
    ['3', 'Pasaportlar', missingIdentity ? `${missingIdentity} eksik` : `${total} hazır`, 'passport', missingIdentity === 0 && total > 0],
    ['4', 'Hazır Kontrolü', readiness.ready ? 'Hazır' : `${readiness.issue_count || 0} uyarı`, 'planning', readiness.ready],
    ['5', 'Çıktılar', 'Manifesto ve şoför listeleri', 'manifest', readiness.ready],
  ];
  document.getElementById('operation-steps').innerHTML = steps.map(([no, title, sub, route, done]) => `
    <a href="#/${route}" class="rounded-lg border ${done ? 'border-success/30 bg-success/5' : 'border-warning/25 bg-warning/5'} p-4">
      <div class="flex items-center justify-between mb-2">
        <span class="w-7 h-7 rounded-full flex items-center justify-center ${done ? 'bg-success text-surface' : 'bg-warning text-surface'} font-bold">${no}</span>
        <span class="material-symbols-outlined ${done ? 'text-success' : 'text-warning'}">${done ? 'check_circle' : 'pending'}</span>
      </div>
      <strong class="block text-on-surface">${title}</strong>
      <span class="text-xs text-on-surface-variant">${esc(sub)}</span>
    </a>`).join('');
}

function renderIssues(readiness) {
  const root = document.getElementById('dash-issues');
  const issues = readiness.issues || [];
  if (!issues.length) {
    root.innerHTML = `<div class="empty-state py-8"><span class="material-symbols-outlined text-success text-5xl">task_alt</span><div class="empty-title">Operasyon hazır</div><div class="empty-desc">Zorunlu kontrollerde eksik bulunmadı.</div></div>`;
    return;
  }
  root.innerHTML = `<div class="space-y-2 max-h-[430px] overflow-auto">${issues.slice(0, 30).map(issue => `
    <div class="flex items-start gap-3 rounded-lg bg-warning/5 border border-warning/15 p-3">
      <span class="material-symbols-outlined text-warning">warning</span>
      <span class="text-sm text-on-surface">${esc(issue.message)}</span>
    </div>`).join('')}</div>`;
}

function renderSummary(data) {
  const readiness = data.readiness || {};
  const items = [
    ['Rezervasyon', data.total_blocks || 0],
    ['Toplam Yolcu', readiness.total_passengers || 0],
    ['Hazır Durum', readiness.ready ? 'Hazır' : 'Kontrol gerekli'],
    ['Dosya Revizyonu', (data.workbook_revision || '').slice(0, 8) || '—'],
  ];
  document.getElementById('dash-summary').innerHTML = items.map(([label, value]) => `
    <div class="flex justify-between gap-4 border-b border-white/5 pb-3">
      <span class="text-on-surface-variant">${label}</span><strong class="text-on-surface">${esc(value)}</strong>
    </div>`).join('');
}

function esc(value) {
  return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
