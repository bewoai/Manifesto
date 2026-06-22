/* ═══════════════════════════════════════════════════════════════════
   Planlama — Gün seçimi, rezervasyon blokları, operasyon formu
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, modal, renderHeader } from '/app.js';
import { attachCombobox } from '/combobox.js';

let state = {
  sheets: [],
  currentSheet: '',
  blocks: [],
  balloons: [],
  selectedBlock: null,
  source: 'excel',
};

export async function render(container) {
  renderHeader('Planlama', 'Uçuş günü yönetimi ve rezervasyon blokları');

  container.innerHTML = `
    <!-- 1) Gün Seçimi -->
    <div class="card mb-6 animate-in">
      <div class="card-header">
        <div class="card-title">
          <span class="material-symbols-outlined">calendar_today</span> Gün Seçimi
        </div>
        <button class="btn-secondary flex items-center gap-2" id="btn-new-day" onclick="window.__createDay()">
          <span class="material-symbols-outlined text-sm">add</span> Yeni Gün
        </button>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Uçuş Günü</label>
          <select class="form-select" id="sheet-select">
            <option value="">Yükleniyor...</option>
          </select>
        </div>
        <div class="form-group flex items-end">
          <button class="btn-primary flex items-center gap-2" id="btn-load-day" onclick="window.__loadDay()">
            <span class="material-symbols-outlined text-sm">download</span> Günü Yükle
          </button>
        </div>
      </div>
    </div>

    <!-- 2) Rezervasyon Blokları -->
    <div class="card mb-6 animate-in" id="blocks-section" style="display:none">
      <div class="card-header">
        <div class="card-title">
          <span class="material-symbols-outlined">group</span> Rezervasyon Blokları
        </div>
        <div class="flex items-center gap-3">
          <span class="text-sm text-on-surface-variant" id="blocks-count"></span>
          <button class="btn-primary flex items-center gap-2" onclick="window.__newReservation()">
            <span class="material-symbols-outlined text-sm">add</span> Yeni Rezervasyon
          </button>
        </div>
      </div>
      <div class="flex flex-wrap gap-2 mb-4" id="balloon-load"></div>
      <div class="flex flex-col gap-3" id="blocks-list"></div>
    </div>

    <!-- 3) Operasyon Bilgileri -->
    <div class="card mb-6 animate-in" id="operation-section" style="display:none">
      <div class="card-header">
        <div class="card-title">
          <span class="material-symbols-outlined">edit</span> Operasyon Bilgileri
        </div>
        <button class="btn-success flex items-center gap-2" onclick="window.__saveOperation()">
          <span class="material-symbols-outlined text-sm">save</span> Kaydet
        </button>
      </div>
      <div class="form-row" id="operation-form"></div>
    </div>
  `;

  loadSheets();
}

async function loadSheets() {
  try {
    const data = await api.get('/api/planning/sheets');
    state.sheets = data.sheets || [];
    state.source = data.source || 'excel';
    const sel = document.getElementById('sheet-select');
    if (!sel) return;
    sel.innerHTML = state.sheets.length
      ? state.sheets.map(s => `<option value="${s}">${s}</option>`).join('')
      : '<option value="">Sayfa bulunamadı</option>';
    if (state.sheets.length) sel.value = state.sheets[state.sheets.length - 1];
  } catch (err) {
    toast.error('Sayfalar yüklenemedi', err.message);
  }
}

window.__loadDay = async function() {
  const sheet = document.getElementById('sheet-select')?.value;
  if (!sheet) { toast.warning('Gün seçin'); return; }
  state.currentSheet = sheet;

  const btn = document.getElementById('btn-load-day');
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-spinner mr-2"></span> Yükleniyor...';

  try {
    const data = await api.get(`/api/planning/load?sheet=${encodeURIComponent(sheet)}`);
    state.blocks = data.blocks || [];
    state.balloons = data.balloon_codes || [];
    state.balloonLoad = data.balloon_load || {};
    state.capacity = data.capacity || 28;
    try { state.lists = (await api.get('/api/lists')).options || {}; } catch (e) { state.lists = {}; }
    renderBlocks();
    renderBalloonLoad();
    toast.success('Gün yüklendi', `${state.blocks.length} rezervasyon bloku bulundu`);
  } catch (err) {
    toast.error('Yükleme hatası', err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="material-symbols-outlined text-sm mr-2">download</span> Günü Yükle';
  }
};

function renderBlocks() {
  const section = document.getElementById('blocks-section');
  const list = document.getElementById('blocks-list');
  const count = document.getElementById('blocks-count');
  if (!section || !list) return;

  section.style.display = '';
  count.textContent = `${state.blocks.length} blok`;

  if (!state.blocks.length) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="material-symbols-outlined empty-icon text-on-surface-variant">inbox</div>
        <div class="empty-title">Rezervasyon bulunamadı</div>
        <div class="empty-desc">Bu güne henüz rezervasyon girilmemiş.</div>
      </div>
    `;
    return;
  }

  list.innerHTML = state.blocks.map((b, i) => {
    const count = b.rows?.length ?? b.pax ?? 0;
    const passengers = (b.passengers || []).map((p, idx) => {
      const name = p.name || (p.passport_no ? p.passport_no : 'Kimlik boş');
      const sex = p.sex ? ` ${p.sex}` : '';
      const cls = p.name || p.passport_no ? 'block-passenger' : 'block-passenger empty';
      return `<span class="${cls}">${idx + 1}. ${escHtml(name)}${escHtml(sex)}</span>`;
    }).join('');
    
    return `
    <div class="block-item ${state.selectedBlock === i ? 'selected' : ''}"
         onclick="window.__selectBlock(${i})" id="block-${i}">
      <div class="block-pax">PAX ${b.pax ?? '?'}</div>
      <div class="block-main">
        <div class="block-info">
          <span class="flex items-center gap-1 font-bold text-on-surface">
            ${b.lead_name || '(isim yok)'}
          </span>
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">hotel</span> ${b.hotel || '—'}
          </span>
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">domain</span> ${b.agency || '—'}
          </span>
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">schedule</span> ${b.pickup || '—'}
          </span>
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">directions_bus</span> Şoför ${b.driver || '—'}
          </span>
        </div>
        ${passengers ? `<div class="block-passengers">${passengers}</div>` : ''}
      </div>
      <div class="flex items-center gap-2 ml-auto">
        <span class="badge badge-blue flex items-center gap-1">
          <span class="material-symbols-outlined text-[16px]">person</span> ${count} kişi
        </span>
        ${b.balloon ? `<div class="block-balloon">${b.balloon}</div>` : ''}
        <button class="btn-ghost btn-icon" title="Rezervasyonu sil"
                onclick="event.stopPropagation(); window.__deleteBlock(${i})">
          <span class="material-symbols-outlined">delete</span>
        </button>
      </div>
    </div>
  `; }).join('');
}

function renderBalloonLoad() {
  const el = document.getElementById('balloon-load');
  if (!el) return;
  const cap = state.capacity || 28;
  const codes = state.balloons || [];
  el.innerHTML = codes.map(code => {
    const used = (state.balloonLoad || {})[code] || 0;
    const full = used >= cap;
    const cls = full ? 'badge-red' : (used > 0 ? 'badge-green' : 'badge-blue');
    return `<span class="badge ${cls}">${code} ${used}/${cap}</span>`;
  }).join('');
}

window.__selectBlock = function(index) {
  state.selectedBlock = index;
  renderBlocks();
  renderOperationForm(state.blocks[index]);
};

function renderOperationForm(block) {
  const section = document.getElementById('operation-section');
  const form = document.getElementById('operation-form');
  if (!section || !form) return;
  section.style.display = '';

  const fields = [
    { key: 'pax', label: 'PAX', value: block.pax ?? '', type: 'number', width: '80px' },
    { key: 'room', label: 'Oda / İrtibat', value: block.room || '' },
    { key: 'hotel', label: 'Otel', value: block.hotel || '' },
    { key: 'pickup', label: 'Pickup Saati', value: block.pickup || '', placeholder: '04:10' },
    { key: 'reserved_by', label: 'Rezerve Yapan', value: block.reserved_by || '' },
    { key: 'agency', label: 'Acente', value: block.agency || '' },
    { key: 'company', label: 'Uçacağı Firma', value: block.company || '' },
    { key: 'balloon', label: 'Balon', value: block.balloon || '', placeholder: 'BYF, BZR...' },
    { key: 'pilot', label: 'Pilot', value: block.pilot || '' },
    { key: 'driver', label: 'Alış Şoför', value: block.driver || '' },
    { key: 'coming_place', label: 'Geleceği Yer', value: block.coming_place || '' },
    { key: 'note', label: 'Not', value: block.note || '' },
  ];

  form.innerHTML = fields.map(f => `
    <div class="form-group">
      <label class="form-label">${f.label}</label>
      <input class="form-input" id="op-${f.key}" type="${f.type || 'text'}"
             value="${escHtml(f.value)}" placeholder="${f.placeholder || ''}"
             ${f.width ? `style="width:${f.width}"` : ''} />
    </div>
  `).join('');

  // Kayıtlı liste önerileri (combobox)
  const L = state.lists || {};
  const sources = {
    balloon: () => state.balloons || [],
    hotel: () => L.hotel || [],
    agency: () => L.agency || [],
    pilot: () => L.pilot || [],
    driver: () => L.driver || [],
    coming_place: () => L.coming_place || [],
    reserved_by: () => L.reserved_by || [],
  };
  for (const [key, getOpts] of Object.entries(sources)) {
    const el = document.getElementById(`op-${key}`);
    if (el) attachCombobox(el, getOpts);
  }
}

window.__saveOperation = async function() {
  if (state.selectedBlock === null || !state.currentSheet) {
    toast.warning('Önce bir gün ve blok seçin');
    return;
  }
  const block = state.blocks[state.selectedBlock];
  const fields = {};
  for (const key of ['pax','room','hotel','pickup','reserved_by','agency','company','balloon','pilot','driver','coming_place','note']) {
    const el = document.getElementById(`op-${key}`);
    if (el) fields[key] = el.value.trim();
  }

  try {
    await api.post('/api/planning/write-operation', {
      sheet: state.currentSheet,
      lead_row: block.lead_row,
      rows: block.rows,
      fields,
    });
    toast.success('Kaydedildi', 'Operasyon bilgileri planlamaya yazıldı');
    // Refresh blocks
    window.__loadDay();
  } catch (err) {
    toast.error('Kaydetme hatası', err.message);
  }
};

window.__deleteBlock = async function(index) {
  const block = state.blocks[index];
  if (!block) return;
  const who = block.lead_name || block.hotel || `PAX ${block.pax ?? '?'}`;
  if (!confirm(`"${who}" rezervasyonu silinsin mi? (${block.rows?.length || 0} satır)`)) return;
  try {
    await api.post('/api/planning/delete-block', { sheet: state.currentSheet, rows: block.rows });
    toast.info('Silindi', `${who} rezervasyonu kaldırıldı`);
    state.selectedBlock = null;
    document.getElementById('operation-section').style.display = 'none';
    window.__loadDay();
  } catch (err) {
    toast.error('Silme hatası', err.message);
  }
};

window.__newReservation = async function() {
  if (!state.currentSheet) { toast.warning('Önce bir gün yükleyin'); return; }
  // Kayıtlı listeleri çek (otel/acente önerileri için)
  let lists = { options: {} };
  try { lists = await api.get('/api/lists'); } catch (e) { /* öneri olmadan da çalışır */ }
  modal.open('Yeni Rezervasyon', `
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">PAX (kişi sayısı) *</label>
        <input class="form-input" id="nr-pax" type="number" min="1" max="28" value="1" />
        <div class="form-help">1–28. Balon otomatik atanır (grup bölünmez).</div>
      </div>
      <div class="form-group">
        <label class="form-label">Otel</label>
        <input class="form-input" id="nr-hotel" placeholder="ör. ARGOS" />
      </div>
    </div>
    <div class="form-row mt-4">
      <div class="form-group">
        <label class="form-label">Acente</label>
        <input class="form-input" id="nr-agency" placeholder="ör. BEDEL TURIZM" />
      </div>
      <div class="form-group">
        <label class="form-label">Oda / İrtibat</label>
        <input class="form-input" id="nr-room" placeholder="ODA 202" />
      </div>
    </div>
    <div class="form-group mt-4">
      <label class="form-label">Rezerve Yapan</label>
      <input class="form-input" id="nr-reserved_by" />
    </div>
    <div class="form-group mt-4">
      <label class="form-label">Not</label>
      <input class="form-input" id="nr-note" />
    </div>
  `, `
    <button class="btn-secondary" onclick="window.__closeModal()">İptal</button>
    <button class="btn-primary" onclick="window.__submitReservation()">Oluştur & Balon Ata</button>
  `);
  // Otel/Acente alanlarına combobox (kayıtlı listelerden seçenek)
  attachCombobox(document.getElementById('nr-hotel'), () => lists.options?.hotel || []);
  attachCombobox(document.getElementById('nr-agency'), () => lists.options?.agency || []);
};

window.__submitReservation = async function() {
  const pax = parseInt(document.getElementById('nr-pax')?.value, 10);
  if (!pax || pax < 1 || pax > 28) { toast.warning('PAX 1–28 arası olmalı'); return; }

  const body = { sheet: state.currentSheet, pax };
  for (const key of ['hotel','agency','room','reserved_by','note']) {
    const v = document.getElementById(`nr-${key}`)?.value.trim();
    if (v) body[key] = v;
  }

  try {
    const res = await api.post('/api/planning/create-block', body);
    modal.close();
    if (res.overflow) {
      toast.warning('Balon atandı (taşma)', res.message);
    } else {
      toast.success('Rezervasyon oluşturuldu', res.message);
    }
    window.__loadDay();
  } catch (err) {
    toast.error('Oluşturma hatası', err.message);
  }
};

window.__createDay = function() {
  modal.open('Yeni Gün Oluştur', `
    <div class="form-group">
      <label class="form-label">Yeni gün adı</label>
      <input class="form-input" id="new-day-name" placeholder="ör. 24.06.2026" />
      <div class="form-help">Tarih formatı: gg.aa.yyyy</div>
    </div>
    <div class="form-group mt-4">
      <label class="form-label">Kaynak gün (kopyalanacak)</label>
      <select class="form-select" id="new-day-source">
        ${state.sheets.map(s => `<option value="${s}">${s}</option>`).join('')}
      </select>
    </div>
  `, `
    <button class="btn-secondary" onclick="window.__closeModal()">İptal</button>
    <button class="btn-primary" onclick="window.__submitNewDay()">Oluştur</button>
  `);
};

window.__submitNewDay = async function() {
  const name = document.getElementById('new-day-name')?.value.trim();
  const source = document.getElementById('new-day-source')?.value;
  if (!name) { toast.warning('Gün adı girin'); return; }

  try {
    await api.post('/api/planning/create-day', { new_sheet: name, source_sheet: source });
    toast.success('Gün oluşturuldu', `${name} başarıyla eklendi`);
    modal.close();
    loadSheets();
  } catch (err) {
    toast.error('Oluşturma hatası', err.message);
  }
};

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
