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
    sel.innerHTML = state.sheets.map(s => `<option value="${s}">${s}</option>`).join('');
    if (state.sheets.length) {
      sel.value = state.sheets[state.sheets.length - 1];
      // Load balloons for the last sheet
      loadBalloons(sel.value);
    }
    sel.addEventListener('change', () => loadBalloons(sel.value));
  } catch (err) {
    toast.error('Sayfalar yüklenemedi', err.message);
  }
}

async function loadBalloons(sheet) {
  try {
    const data = await api.get(`/api/planning/load?sheet=${encodeURIComponent(sheet)}`);
    state.balloons = data.balloon_codes || [];
    const sel = document.getElementById('mf-balloon');
    sel.innerHTML = state.balloons.length
      ? state.balloons.map(b => `<option value="${b}">${b}</option>`).join('')
      : '<option value="">Balon bulunamadı</option>';
  } catch (err) { /* silent */ }
}

window.__mfPreview = async function() {
  const sheet = document.getElementById('mf-sheet')?.value;
  const balloon = document.getElementById('mf-balloon')?.value;
  if (!sheet || !balloon) { toast.warning('Gün ve balon seçin'); return; }

  state.currentSheet = sheet;
  state.currentBalloon = balloon;

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
  const url = `/api/manifest/export?sheet=${encodeURIComponent(state.currentSheet)}&balloon=${encodeURIComponent(state.currentBalloon)}`;
  window.open(url, '_blank');
  toast.success('İndirme başladı', `${state.currentBalloon}.xlsx`);
};

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
