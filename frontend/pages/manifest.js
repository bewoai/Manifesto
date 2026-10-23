/* ═══════════════════════════════════════════════════════════════════
   Manifesto — Önizleme tablosu ve Excel export
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, renderHeader, balloonBadge } from '/app.js';
import { openIdentityEditor } from '/identity_edit.js';

let state = {
  sheets: [],
  balloons: [],
  currentSheet: '',
  currentBalloon: '',
  rows: [],
  readiness: null,
  driverSummary: [],
};
let renderToken = 0;

export async function render(container) {
  const currentToken = ++renderToken;
  renderHeader('Manifesto', 'Balon bazlı manifesto önizleme ve Excel export');

  container.innerHTML = `
    <!-- Filtre -->
    <div class="glass-panel rounded-xl px-5 py-4 mb-6" role="search" aria-label="Manifesto seçimi">
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-[1fr_1fr_auto] gap-4">
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
        <div class="flex flex-wrap items-end gap-3 md:col-span-2 xl:col-span-1">
          <button class="btn-secondary flex-1 flex items-center justify-center gap-2" onclick="window.__mfPreview()">
            <span class="material-symbols-outlined">visibility</span> Önizle
          </button>
          <button class="btn-primary flex-1 flex items-center justify-center gap-2" id="btn-export" onclick="window.__mfExport()" disabled>
            <span class="material-symbols-outlined">download</span> İndir
          </button>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
      <div class="card">
        <div class="card-header"><h2 class="card-title">Uçuşa hazır kontrolü</h2></div>
        <div id="mf-readiness"></div>
        <!-- Gerekçe alanı her zaman görünür: kontrol yüklenemese de 409'da kullanıcı çıkmaza girmesin -->
        <div class="form-group mt-3">
          <label class="form-label" for="mf-override-reason">Eksiklerle devam gerekçesi</label>
          <input class="form-input" id="mf-override-reason" placeholder="Örn. Eksik pasaport acenteden bekleniyor" />
          <div class="form-help">Uyarı varsa manifesto ve toplu çıktı için zorunludur; uyarı yoksa boş bırakılabilir.</div>
        </div>
      </div>
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">Balon ve şoför özeti</h2>
          <button class="btn-secondary" onclick="window.__driverReports()">Şoför Listeleri</button>
        </div>
        <div id="driver-summary" class="space-y-2"></div>
      </div>
    </div>

    <div class="card mb-6">
      <div class="card-header"><h2 class="card-title">Gün sonu</h2></div>
      <div class="text-sm text-on-surface-variant bg-surface/50 p-3 rounded-xl mb-4 border border-line">
        <strong>Bilgi:</strong> "Tüm Çıktıları Hazırla" işlemi seçili gün için; balon manifestolarını, şoför/araç listelerini, kapasite özetlerini ve tüm bunların bulunduğu toplu ZIP arşivini üretir.
      </div>
      <div class="flex flex-wrap gap-3">
        <button class="btn-primary" onclick="window.__allOutputs()"><span class="material-symbols-outlined">folder_zip</span> Tüm Çıktıları Hazırla</button>
        <button class="btn-secondary" onclick="window.__cleanupPassports()"><span class="material-symbols-outlined">shield_lock</span> Günlük Pasaport Verilerini Temizle</button>
        <button class="btn-ghost" onclick="window.__openOutputFolder()" title="Seçili günün çıktı klasörünü Gezgin'de aç"><span class="material-symbols-outlined">folder_open</span> Çıktı Klasörünü Aç</button>
      </div>
      <div id="mf-output-location" class="hidden mt-4 p-3 rounded-xl bg-success/10 border border-success/20 text-sm"></div>
    </div>

    <!-- Preview Table -->
    <div class="glass-panel rounded-xl p-6 animate-in" id="preview-section" style="display:none">
      <div class="flex items-center justify-between mb-6">
        <h2 class="font-headline text-headline-sm text-on-surface">Manifesto önizleme</h2>
        <span class="badge badge-blue" id="mf-count"></span>
      </div>
      <div id="mf-table-container"></div>
    </div>

    <!-- Empty state -->
    <div class="glass-panel rounded-xl px-6 py-8" id="empty-section">
      <h3 class="font-headline text-headline-sm text-on-surface mb-1.5">Önizleme henüz açılmadı</h3>
      <p class="text-on-surface-variant">Yukarıdan gün ve balon seçip <strong class="text-on-surface">Önizle</strong>'ye basın; yolcu listesi burada açılır.</p>
    </div>
  `;

  loadSheets(currentToken);
}

async function loadSheets(token) {
  try {
    const data = await api.get('/api/planning/sheets');
    if (token !== renderToken) return;
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
    sel.addEventListener('change', () => {
      // Gerekçe güne özeldir; başka güne geçince taşınmasın
      const reason = document.getElementById('mf-override-reason');
      if (reason) reason.value = '';
      loadBalloons(sel.value);
      loadOperations(sel.value);
    });
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
    const root = document.getElementById('mf-readiness');
    if (root) {
      root.innerHTML = `
        <div class="rounded-lg bg-danger/10 border border-danger/20 p-3 text-danger text-sm">
          Uçuşa hazır kontrolü yüklenemedi: ${esc(err.message)}.
          Çıktı alırken uyarı çıkarsa aşağıya gerekçe yazmanız istenebilir.
        </div>`;
    }
    const drivers = document.getElementById('driver-summary');
    if (drivers) drivers.innerHTML = '<div class="empty-desc">Şoför özeti yüklenemedi.</div>';
  }
}

function renderReadiness() {
  const root = document.getElementById('mf-readiness');
  const data = state.readiness || {};
  if (!root) return;
  if (data.ready) {
    root.innerHTML = `<div class="rounded-lg bg-success/10 border border-success/20 p-4 text-success flex gap-3"><span class="material-symbols-outlined">task_alt</span><div><strong>Uçuşa hazır</strong><div class="text-sm opacity-80">${Number(data.total_passengers || 0)} yolcu kontrol edildi.</div></div></div>`;
    return;
  }
  root.innerHTML = `
    <div class="rounded-lg bg-warning/10 border border-warning/20 p-3 text-warning mb-3">${Number(data.issue_count || 0)} uyarı bulundu. Çıktı alınabilir ancak gerekçe istenir.</div>
    <div class="max-h-52 overflow-auto space-y-2">${(data.issues || []).slice(0, 20).map(issue => `<div class="text-sm text-on-surface-variant border-b border-line pb-2">${esc(issue.message)}</div>`).join('')}</div>`;
}

function focusOverrideReason() {
  const input = document.getElementById('mf-override-reason');
  if (!input) return;
  input.scrollIntoView({ behavior: 'smooth', block: 'center' });
  input.focus();
}

function renderDriverSummary() {
  const root = document.getElementById('driver-summary');
  if (!root) return;
  root.innerHTML = state.driverSummary.length ? state.driverSummary.map(row => `
    <div class="grid grid-cols-[80px_1fr] gap-3 items-center">
      <span>${balloonBadge(row.balloon)}</span>
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
    <table class="board sticky-head">
      <thead>
        <tr>
          <th class="hidden lg:table-cell">#</th>
          <th>Ad soyad</th>
          <th>Cinsiyet</th>
          <th>Uyruk</th>
          <th>Pasaport / kimlik no</th>
          <th>Durum</th>
        </tr>
      </thead>
      <tbody>
        ${state.rows.map((r, i) => `
          <tr>
            <td class="hidden lg:table-cell text-on-surface-variant">${i + 1}</td>
            <td class="text-on-surface font-medium whitespace-nowrap">${esc(r.name)}</td>
            <td class="text-on-surface-variant">${esc(r.sex)}</td>
            <td class="text-on-surface-variant whitespace-nowrap">${esc(r.nationality)}</td>
            <td class="text-on-surface-variant font-mono">${esc(r.passport_no)}</td>
            <td><div class="flex items-center gap-1">${(r.warnings || []).length
              ? `<button type="button" class="badge badge-yellow cursor-pointer hover:brightness-110 flex items-center gap-1 w-max" title="Tıklayın ve düzeltin" onclick="window.__mfFix(${i})"><span class="material-symbols-outlined text-[16px]">edit</span>${esc(r.warnings.join(', '))}</button>`
              : '<span class="badge badge-green flex items-center gap-1 w-max"><span class="material-symbols-outlined text-[16px]">check</span> Geçerli</span>'
            }${r.row ? `<button class="btn-ghost btn-icon !w-8 !h-8 shrink-0" title="Kimliği düzelt" aria-label="Kimliği düzelt" onclick="window.__mfFix(${i})"><span class="material-symbols-outlined text-[19px]">edit</span></button>` : ''}</div></td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

window.__mfFix = function(i) {
  const r = state.rows[i];
  if (!r || !r.row) { toast.warning('Satır bulunamadı', 'Önizlemeyi yenileyip tekrar deneyin.'); return; }
  const warn = (r.warnings || []).join(', ');
  openIdentityEditor({
    sheet: state.currentSheet,
    row: r.row,
    values: { nationality: r.raw_nationality, sex: r.raw_sex, name: r.name, passport_no: r.passport_no },
    hint: warn || '',
    focus: /uyruk/i.test(warn) ? 'nationality' : /cinsiyet/i.test(warn) ? 'sex' : undefined,
    onSaved: () => window.__mfPreview(),
  });
};

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
      if (response.status === 409 && detail?.code === 'readiness_override_required') {
        // Kontrol daha önce yüklenemediyse bile sunucunun gönderdiği listeyi göster
        if (detail.readiness) {
          state.readiness = detail.readiness;
          renderReadiness();
        }
        focusOverrideReason();
        toast.warning('Gerekçe gerekli', `${detail.message || 'Uçuşa hazır kontrolünde eksikler var.'} Gerekçeyi yazıp tekrar deneyin.`);
        return;
      }
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
    const outDir = decodeURIComponent(response.headers.get('x-output-dir') || '');
    showOutputLocation(outDir, name);
    toast.success('Çıktılar kaydedildi', outDir ? `${name} → ${outDir}` : name);
  } catch (err) { toast.error('Çıktı oluşturulamadı', err.message); }
}

function showOutputLocation(outDir, name) {
  const el = document.getElementById('mf-output-location');
  if (!el || !outDir) return;
  el.classList.remove('hidden');
  el.innerHTML = `
    <div class="flex flex-wrap items-center gap-3">
      <span class="material-symbols-outlined text-success">folder</span>
      <div class="flex-1 min-w-0">
        <div class="text-on-surface font-medium">${esc(name)} kaydedildi</div>
        <div class="text-on-surface-variant font-mono text-xs break-all">${esc(outDir)}</div>
        <div class="text-on-surface-variant text-xs mt-1">WhatsApp/Drive'a gönderirken dosyayı bu klasörden seçin; ZIP penceresinin içinden sürüklemeyin.</div>
      </div>
      <button class="btn-secondary" onclick="window.__openOutputFolder()"><span class="material-symbols-outlined">folder_open</span> Klasörü Aç</button>
    </div>`;
}

window.__openOutputFolder = async function() {
  const sheet = document.getElementById('mf-sheet')?.value || state.currentSheet || '';
  try {
    await api.post('/api/outputs/open-folder', { sheet });
  } catch (err) { toast.error('Klasör açılamadı', err.message); }
};

function esc(s) {
  return String(s || '')
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
}
const escAttr = esc;
