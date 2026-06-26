/* ═══════════════════════════════════════════════════════════════════
   Manifesto — Önizleme tablosu ve Excel export
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, renderHeader } from '/app.js';

let state = {
  sheets: [],
  balloons: [],
  currentSheet: '',
  currentBalloon: '',
  rows: [],
  readiness: null,
  driverSummary: [],
};

export async function render(container) {
  renderHeader('Manifesto', 'Balon bazlı manifesto önizleme ve Excel export');

  container.innerHTML = `
    <!-- Filtre -->
    <div class="glass-panel rounded-[40px] p-6 mb-6 animate-in">
      <div class="flex items-center gap-3 mb-6">
        <span class="material-symbols-outlined text-primary text-3xl">search</span>
        <h2 class="font-headline text-headline-sm text-on-surface">Filtrele</h2>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div class="form-group">
          <label class="form-label">Uçuş Günü</label>
          <select class="form-select" id="mf-sheet"></select>
        </div>
        <div class="form-group">
          <label class="form-label">Balon Kodu</label>
          <select class="form-select" id="mf-balloon">
            <option value="">Önce gün yükleyin</option>
          </select>
        </div>
        <div class="flex items-end gap-3">
          <button class="btn-primary flex-1 flex items-center justify-center gap-2" onclick="window.__mfPreview()">
            <span class="material-symbols-outlined">visibility</span> Önizle
          </button>
          <button class="btn-success flex-1 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed" id="btn-export" onclick="window.__mfExport()" disabled>
            <span class="material-symbols-outlined">download</span> İndir
          </button>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="material-symbols-outlined">fact_check</span> Uçuşa Hazır Kontrolü</div></div>
        <div id="mf-readiness"></div>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="material-symbols-outlined">airport_shuttle</span> Balon - Şoför Özeti</div>
          <button class="btn-secondary" onclick="window.__driverReports()">Şoför Listeleri</button>
        </div>
        <div id="driver-summary" class="space-y-2"></div>
      </div>
    </div>

    <div class="card mb-6">
      <div class="card-header"><div class="card-title"><span class="material-symbols-outlined">inventory_2</span> Gün Sonu İşlemleri</div></div>
      <div class="flex flex-wrap gap-3">
        <button class="btn-primary" onclick="window.__allOutputs()"><span class="material-symbols-outlined">folder_zip</span> Tüm Çıktıları Hazırla</button>
        <button class="btn-secondary" onclick="window.__cleanupPassports()"><span class="material-symbols-outlined">shield_lock</span> Günlük Pasaport Verilerini Temizle</button>
      </div>
    </div>

    <!-- Preview Table -->
    <div class="glass-panel rounded-[40px] p-6 animate-in" id="preview-section" style="display:none">
      <div class="flex items-center justify-between mb-6">
        <div class="flex items-center gap-3">
          <span class="material-symbols-outlined text-primary text-3xl">description</span>
          <h2 class="font-headline text-headline-sm text-on-surface">Manifesto Önizleme</h2>
        </div>
        <span class="badge badge-blue" id="mf-count"></span>
      </div>
      <div class="overflow-x-auto" id="mf-table-container"></div>
    </div>

    <!-- Empty state -->
    <div class="glass-panel rounded-[40px] p-12 text-center animate-in flex flex-col items-center justify-center" id="empty-section">
      <span class="material-symbols-outlined text-6xl text-on-surface-variant/50 mb-4">description</span>
      <h3 class="font-headline text-headline-sm text-on-surface mb-2">Manifesto önizlemek için gün ve balon seçin</h3>
      <p class="text-on-surface-variant max-w-md">
        Planlama listesinden seçilen güne ait yolcular, balon koduna göre filtrelenip
        manifesto formatında gösterilir.
      </p>
    </div>
  `;

  loadSheets();
}

async function loadSheets() {
  try {
    const data = await api.get('/api/planning/sheets');
    state.sheets = data.sheets || [];
    const sel = document.getElementById('mf-sheet');
    if (!sel) return;
    sel.innerHTML = state.sheets.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
    if (state.sheets.length) {
      sel.value = state.sheets[state.sheets.length - 1];
      // Load balloons for the last sheet
      loadBalloons(sel.value);
      loadOperations(sel.value);
    }
    sel.addEventListener('change', () => { loadBalloons(sel.value); loadOperations(sel.value); });
  } catch (err) {
    toast.error('Sayfalar yüklenemedi', err.message);
  }
}

function showManifestSkeletons() {
  const readiness = document.getElementById('mf-readiness');
  const driverSummary = document.getElementById('driver-summary');
  if (readiness) {
    readiness.innerHTML = `
      <div class="p-4 space-y-3">
        <div class="skeleton-text shimmer w-full"></div>
        <div class="skeleton-text shimmer w-3/4"></div>
      </div>
    `;
  }
  if (driverSummary) {
    driverSummary.innerHTML = `
      <div class="p-4 space-y-3">
        <div class="skeleton-text shimmer w-full"></div>
        <div class="skeleton-text shimmer w-5/6"></div>
      </div>
    `;
  }
}

function showTableSkeleton() {
  const section = document.getElementById('preview-section');
  const empty = document.getElementById('empty-section');
  const tbl = document.getElementById('mf-table-container');
  if (section) section.style.display = '';
  if (empty) empty.style.display = 'none';
  if (tbl) {
    tbl.innerHTML = `
      <div class="p-4 space-y-4">
        <div class="skeleton-title shimmer w-1/4 mb-4"></div>
        <div class="skeleton-text shimmer w-full"></div>
        <div class="skeleton-text shimmer w-full"></div>
        <div class="skeleton-text shimmer w-full"></div>
        <div class="skeleton-text shimmer w-full"></div>
      </div>
    `;
  }
}

async function loadOperations(sheet) {
  showManifestSkeletons();
  try {
    const [readiness, reports] = await Promise.all([
      api.get(`/api/readiness?sheet=${encodeURIComponent(sheet)}`),
      api.get(`/api/reports/drivers/preview?sheet=${encodeURIComponent(sheet)}`),
    ]);
    state.readiness = readiness;
    state.driverSummary = reports.summary || [];
    renderReadiness();
    renderDriverSummary();
  } catch (err) {
    toast.error('Operasyon kontrolü yüklenemedi', err.message);
  }
}

function renderReadiness() {
  const root = document.getElementById('mf-readiness');
  const data = state.readiness || {};
  if (data.ready) {
    if (!root) return;
    root.innerHTML = `<div class="rounded-lg bg-success/10 border border-success/20 p-4 text-success flex gap-3"><span class="material-symbols-outlined">task_alt</span><div><strong>Uçuşa hazır</strong><div class="text-sm opacity-80">${data.total_passengers || 0} yolcu kontrol edildi.</div></div></div>`;
    return;
  }
  if (!root) return;
  root.innerHTML = `
    <div class="rounded-lg bg-warning/10 border border-warning/20 p-3 text-warning mb-3">${data.issue_count || 0} uyarı bulundu. Çıktı alınabilir ancak gerekçe istenir.</div>
    <div class="max-h-52 overflow-auto space-y-2">${(data.issues || []).slice(0, 20).map(issue => `<div class="text-sm text-on-surface-variant border-b border-white/5 pb-2">${esc(issue.message)}</div>`).join('')}</div>
    <div class="form-group mt-3"><label class="form-label">Eksiklerle devam gerekçesi</label><input class="form-input" id="mf-override-reason" placeholder="Örn. Eksik pasaport acenteden bekleniyor" /></div>`;
}

function renderDriverSummary() {
  const root = document.getElementById('driver-summary');
  if (!root) return;
  root.innerHTML = state.driverSummary.length ? state.driverSummary.map(row => `
    <div class="grid grid-cols-[80px_1fr] gap-3 items-center">
      <strong class="text-primary">${esc(row.balloon)}</strong>
      <input class="form-input py-2" data-balloon="${escAttr(row.balloon)}" value="${escAttr(row.driver)}" />
    </div>`).join('') : '<div class="empty-desc">Balon/şoför ataması bulunamadı.</div>';
}

function summaryOverrides() {
  const values = {};
  document.querySelectorAll('#driver-summary input[data-balloon]').forEach(input => {
    values[input.dataset.balloon] = input.value.trim();
  });
  return values;
}

async function loadBalloons(sheet) {
  try {
    const data = await api.get(`/api/planning/load?sheet=${encodeURIComponent(sheet)}`);
    state.balloons = data.balloon_codes || [];
    const sel = document.getElementById('mf-balloon');
    if (!sel) return;
    sel.innerHTML = state.balloons.length
      ? state.balloons.map(b => `<option value="${esc(b)}">${esc(b)}</option>`).join('')
      : '<option value="">Balon bulunamadı</option>';
  } catch (err) { /* silent */ }
}

window.__mfPreview = async function() {
  const sheet = document.getElementById('mf-sheet')?.value;
  const balloon = document.getElementById('mf-balloon')?.value;
  if (!sheet || !balloon) { toast.warning('Gün ve balon seçin'); return; }

  state.currentSheet = sheet;
  state.currentBalloon = balloon;
  showTableSkeleton();

  try {
    const data = await api.get(`/api/manifest/preview?sheet=${encodeURIComponent(sheet)}&balloon=${encodeURIComponent(balloon)}`);
    state.rows = data.rows || [];
    renderTable();
    document.getElementById('btn-export').disabled = false;
    toast.info('Önizleme yüklendi', `${state.rows.length} yolcu`);
  } catch (err) {
    toast.error('Önizleme hatası', err.message);
  }
};

function renderTable() {
  const section = document.getElementById('preview-section');
  const empty = document.getElementById('empty-section');
  const tbl = document.getElementById('mf-table-container');
  const count = document.getElementById('mf-count');

  if (!state.rows.length) {
    section.style.display = 'none';
    empty.style.display = '';
    return;
  }

  section.style.display = '';
  empty.style.display = 'none';
  count.textContent = `${state.rows.length} yolcu`;

  if (!tbl) return;
  tbl.innerHTML = `
    <table class="w-full text-left border-collapse">
      <thead>
        <tr class="border-b border-white/10">
          <th class="p-4 text-sm font-medium text-on-surface-variant">#</th>
          <th class="p-4 text-sm font-medium text-on-surface-variant">AD SOYAD</th>
          <th class="p-4 text-sm font-medium text-on-surface-variant">CİNSİYET</th>
          <th class="p-4 text-sm font-medium text-on-surface-variant">UYRUK</th>
          <th class="p-4 text-sm font-medium text-on-surface-variant">PASAPORT / KİMLİK NO</th>
          <th class="p-4 text-sm font-medium text-on-surface-variant">UYARILAR</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-white/5">
        ${state.rows.map((r, i) => `
          <tr class="hover:bg-white/5 transition-colors">
            <td class="p-4 text-on-surface-variant">${i + 1}</td>
            <td class="p-4 text-on-surface font-medium">${esc(r.name)}</td>
            <td class="p-4 text-on-surface-variant">${esc(r.sex)}</td>
            <td class="p-4 text-on-surface-variant">${esc(r.nationality)}</td>
            <td class="p-4 text-on-surface-variant font-mono">${esc(r.passport_no)}</td>
            <td class="p-4">${(r.warnings || []).length
              ? `<span class="badge badge-yellow">${r.warnings.join(', ')}</span>`
              : '<span class="badge badge-green flex items-center gap-1 w-max"><span class="material-symbols-outlined text-[16px]">check</span> Geçerli</span>'
            }</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

window.__mfExport = function() {
  if (!state.currentSheet || !state.currentBalloon) return;
  downloadManifest();
};

async function downloadManifest() {
  const reason = document.getElementById('mf-override-reason')?.value.trim() || '';
  const url = `/api/manifest/export?sheet=${encodeURIComponent(state.currentSheet)}&balloon=${encodeURIComponent(state.currentBalloon)}&override_reason=${encodeURIComponent(reason)}`;
  await downloadFetch(url, { method: 'GET' }, `${state.currentBalloon}.xlsx`);
}

window.__driverReports = async function() {
  const sheet = document.getElementById('mf-sheet')?.value;
  await downloadFetch('/api/reports/drivers/export', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sheet, summary_overrides: summaryOverrides() }),
  }, 'Tum_Sofor_Listeleri.zip');
};

window.__allOutputs = async function() {
  const sheet = document.getElementById('mf-sheet')?.value;
  const override_reason = document.getElementById('mf-override-reason')?.value.trim() || '';
  await downloadFetch('/api/reports/all', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sheet, override_reason, summary_overrides: summaryOverrides() }),
  }, `Irtifa_${sheet}_Tum_Ciktilar.zip`);
};

window.__cleanupPassports = async function() {
  const sheet = document.getElementById('mf-sheet')?.value;
  if (!confirm(`${sheet} için geçici pasaport görselleri ve OCR kayıtları silinsin mi? Excel kimlik alanları korunur.`)) return;
  try {
    const data = await api.post('/api/passport/cleanup', { sheet });
    toast.success('Temizlendi', `${data.removed_files} geçici görsel silindi`);
  } catch (err) { toast.error('Temizleme başarısız', err.message); }
};

async function downloadFetch(url, options, fallbackName) {
  try {
    const response = await fetch(url, options);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: response.statusText }));
      const detail = payload.detail;
      throw new Error(typeof detail === 'string' ? detail : (detail?.message || response.statusText));
    }
    const blob = await response.blob();
    const disposition = response.headers.get('content-disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/i);
    const name = match?.[1] || fallbackName;
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = name;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    toast.success('İndirme hazır', name);
  } catch (err) { toast.error('Çıktı oluşturulamadı', err.message); }
}

function esc(s) {
  return String(s || '')
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
}
const escAttr = esc;
