import { api, toast, renderHeader } from '/app.js';

let renderId = 0;

export async function render(container) {
  const myRenderId = ++renderId;
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
  await loadDashboard(myRenderId);
}

function isCurrent(renderToken) {
  return renderToken === renderId && !!document.getElementById('dash-sheet');
}

function showSkeletons() {
  const steps = document.getElementById('operation-steps');
  const issues = document.getElementById('dash-issues');
  const summary = document.getElementById('dash-summary');
  if (steps) {
    steps.innerHTML = `
      <div class="skeleton-card shimmer min-h-[110px]"></div>
      <div class="skeleton-card shimmer min-h-[110px]"></div>
      <div class="skeleton-card shimmer min-h-[110px]"></div>
      <div class="skeleton-card shimmer min-h-[110px]"></div>
      <div class="skeleton-card shimmer min-h-[110px]"></div>
    `;
  }
  if (issues) {
    issues.innerHTML = `
      <div class="p-4 space-y-3">
        <div class="skeleton-text shimmer w-full"></div>
        <div class="skeleton-text shimmer w-5/6"></div>
        <div class="skeleton-text shimmer w-4/5"></div>
      </div>
    `;
  }
  if (summary) {
    summary.innerHTML = `
      <div class="p-4 space-y-4">
        <div class="skeleton-text shimmer w-full"></div>
        <div class="skeleton-text shimmer w-3/4"></div>
        <div class="skeleton-text shimmer w-5/6"></div>
      </div>
    `;
  }
}

async function loadDashboard(renderToken = renderId) {
  showSkeletons();
  try {
    const sheetsData = await api.get('/api/planning/sheets');
    if (!isCurrent(renderToken)) return;
    const sheets = sheetsData.sheets || [];
    const select = document.getElementById('dash-sheet');
    if (!select) return;
    select.innerHTML = sheets.map(sheet => `<option value="${esc(sheet)}">${esc(sheet)}</option>`).join('');
    if (sheets.length) {
      select.value = sheets[sheets.length - 1];
      await Promise.all([window.__dashLoad(renderToken), loadWeather(renderToken)]);
    } else {
      showEmptyState(renderToken);
    }
  } catch (err) {
    if (!isCurrent(renderToken)) return;
    if (err.status === 404) {
      showEmptyState(renderToken);
    } else {
      toast.error('Operasyon paneli yüklenemedi', err.message);
    }
  }
}

function showEmptyState(renderToken = renderId) {
  if (!isCurrent(renderToken)) return;
  const steps = document.getElementById('operation-steps');
  const issues = document.getElementById('dash-issues');
  const summary = document.getElementById('dash-summary');
  if (!steps || !issues || !summary) return;
  steps.innerHTML = `
    <div class="col-span-full bg-surface-variant/30 rounded-2xl p-8 text-center border border-white/5">
      <span class="material-symbols-outlined text-5xl text-primary mb-4 block">description</span>
      <h3 class="text-xl font-headline text-on-surface mb-2">Henüz Uçuş Planı Dosyası Tanımlanmadı</h3>
      <p class="text-on-surface-variant mb-6">İrtifa'yı kullanmaya başlamak için bir Uçuş Planı (Excel) dosyası oluşturmalısınız.</p>
      <div class="flex flex-col items-center gap-4 mt-6">
        <button class="btn-primary" onclick="window.__dashCreatePlan()">Yeni Excel Dosyası Oluştur</button>
        <div class="text-on-surface-variant text-sm">veya</div>
        <button class="btn-ghost shadow" onclick="window.__dashImportPlan()">Mevcut Excel Dosyasını Bağla</button>
      </div>
    </div>
  `;
  issues.innerHTML = '<div class="p-6 text-center text-on-surface-variant">Bekleniyor...</div>';
  summary.innerHTML = '<div class="p-6 text-center text-on-surface-variant">Bekleniyor...</div>';
}

window.__dashCreatePlan = async function() {
  const { modal } = await import('/app.js');
  const now = new Date();
  modal.open('Yeni Uçuş Planı Oluştur', `
    <div class="space-y-4">
      <div class="form-group">
        <label class="form-label">Yıl</label>
        <select id="dash-modal-year" class="form-select">
          <option value="${now.getFullYear()}">${now.getFullYear()}</option>
          <option value="${now.getFullYear() + 1}">${now.getFullYear() + 1}</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Ay</label>
        <select id="dash-modal-month" class="form-select">
          ${[...Array(12)].map((_, i) => {
            const val = i + 1;
            const name = new Date(2000, i, 1).toLocaleString('tr-TR', { month: 'long' });
            return '<option value="' + val + '" ' + (now.getMonth() + 1 === val ? 'selected' : '') + '>' + name + '</option>';
          }).join('')}
        </select>
      </div>
    </div>
  `, `
    <button class="btn-ghost" onclick="window.__closeModal()">İptal</button>
    <button class="btn-primary" onclick="window.__dashDoCreatePlan()">Oluştur ve Kaydet</button>
  `);
};

window.__dashDoCreatePlan = async function() {
  const { toast } = await import('/app.js');
  const y = parseInt(document.getElementById('dash-modal-year').value);
  const m = parseInt(document.getElementById('dash-modal-month').value);
  window.__closeModal();
  try {
    const res = await api.post('/api/planning/generate-monthly', { year: y, month: m });
    if (res.success) {
      toast.success('Başarılı', res.message);
      // Başarıyla oluşturuldu, dashboard'u yeniden yükle
      await loadDashboard(renderId);
    } else {
      if (res.message !== 'İptal edildi') toast.error('Hata', res.message);
    }
  } catch (err) {
    toast.error('Hata', err.message);
  }
};

window.__dashImportPlan = async function() {
  const { toast } = await import('/app.js');
  try {
    const res = await api.post('/api/planning/import-existing', {});
    if (res.success) {
      toast.success('Başarılı', res.message);
      await loadDashboard(renderId);
    } else {
      if (res.message !== 'İptal edildi') toast.error('Hata', res.message);
    }
  } catch (err) {
    toast.error('Hata', err.message);
  }
};

window.__dashLoad = async function(renderToken = renderId) {
  const sheet = document.getElementById('dash-sheet')?.value;
  if (!sheet) return;
  showSkeletons();
  try {
    const data = await api.get(`/api/planning/load?sheet=${encodeURIComponent(sheet)}`);
    if (!isCurrent(renderToken)) return;
    renderSteps(data);
    renderIssues(data.readiness || {});
    renderSummary(data);
  } catch (err) {
    if (!isCurrent(renderToken)) return;
    toast.error('Gün yüklenemedi', err.message);
  }
};

async function loadWeather(renderToken = renderId) {
  const root = document.getElementById('today-weather');
  if (!root) return;
  try {
    const data = await api.get('/api/weather/status');
    if (!isCurrent(renderToken)) return;
    const decision = data.decision || {};
    if (!root) return;
    root.innerHTML = `
      <div class="glass-panel rounded-2xl px-5 py-3 flex flex-wrap items-center gap-4">
        <span class="material-symbols-outlined text-primary">partly_cloudy_day</span>
        <strong class="text-on-surface">Hava tavsiyesi: ${esc(decision.title || 'Veri bekleniyor')}</strong>
        <span class="text-sm text-on-surface-variant flex-1">${esc(decision.summary || '')}</span>
        <a href="#/weather" class="btn-ghost px-3 py-1.5">Detay</a>
      </div>`;
  } catch (err) {
    if (!isCurrent(renderToken) || !root) return;
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
  const el = document.getElementById('operation-steps');
  if (!el) return;
  el.innerHTML = steps.map(([no, title, sub, route, done]) => `
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
  if (!root) return;
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
  const el = document.getElementById('dash-summary');
  if (!el) return;
  el.innerHTML = items.map(([label, value]) => `
    <div class="flex justify-between gap-4 border-b border-white/5 pb-3">
      <span class="text-on-surface-variant">${label}</span><strong class="text-on-surface">${esc(value)}</strong>
    </div>`).join('');
}

function esc(value) {
  return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
