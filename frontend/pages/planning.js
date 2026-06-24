/* ═══════════════════════════════════════════════════════════════════
   Planlama — Gün seçimi, rezervasyon blokları, operasyon formu
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, modal, renderHeader, helpIcon } from '/app.js';
import { attachCombobox } from '/combobox.js';

let state = {
  sheets: [],
  currentSheet: '',
  blocks: [],
  balloons: [],
  selectedBlock: null,
  source: 'excel',
  revision: '',
  readiness: null,
};

export async function render(container) {
  renderHeader('Planlama', 'Uçuş günü yönetimi ve rezervasyon blokları');

  container.innerHTML = `
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
      <div class="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
        <input class="form-input md:col-span-2" id="block-search" placeholder="İsim, otel, acente, balon veya şoför ara" oninput="window.__renderPlanning()" />
        <select class="form-select" id="block-filter" onchange="window.__renderPlanning()">
          <option value="">Tüm rezervasyonlar</option>
          <option value="missing">Pasaportu eksik</option>
          <option value="ready">Kimliği hazır</option>
        </select>
        <select class="form-select" id="block-sort" onchange="window.__renderPlanning()">
          <option value="row">Liste sırası</option>
          <option value="pickup">Pickup saatine göre</option>
          <option value="pax">PAX'a göre</option>
          <option value="name">İsme göre</option>
        </select>
      </div>
      <div class="flex flex-col gap-3" id="blocks-list"></div>
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
    const selectedLead = state.selectedBlock !== null ? state.blocks[state.selectedBlock]?.lead_row : null;
    const data = await api.get(`/api/planning/load?sheet=${encodeURIComponent(sheet)}`);
    state.blocks = data.blocks || [];
    state.selectedBlock = selectedLead
      ? state.blocks.findIndex(b => b.lead_row === selectedLead)
      : state.selectedBlock;
    if (state.selectedBlock < 0) state.selectedBlock = null;
    state.balloons = data.balloon_codes || [];
    state.balloonLoad = data.balloon_load || {};
    state.capacity = data.capacity || 28;
    state.revision = data.workbook_revision || '';
    state.readiness = data.readiness || null;
    try { state.lists = (await api.get('/api/lists')).options || {}; } catch (e) { state.lists = {}; }
    
    const filterSelect = document.getElementById('block-filter');
    if (filterSelect) {
      const currentVal = filterSelect.value;
      let html = `<option value="">Tüm rezervasyonlar</option>
                  <option value="missing">Pasaportu eksik</option>
                  <option value="ready">Kimliği hazır</option>`;
      state.balloons.forEach(b => {
        if (b) html += `<option value="balloon_${b}">${b} balonu</option>`;
      });
      filterSelect.innerHTML = html;
      if (Array.from(filterSelect.options).some(o => o.value === currentVal)) {
        filterSelect.value = currentVal;
      }
    }

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
  const visible = filteredBlocks();
  count.textContent = `${visible.length}/${state.blocks.length} blok`;

  if (!visible.length) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="material-symbols-outlined empty-icon text-on-surface-variant">inbox</div>
        <div class="empty-title">Rezervasyon bulunamadı</div>
        <div class="empty-desc">Bu güne henüz rezervasyon girilmemiş.</div>
      </div>
    `;
    return;
  }

  list.innerHTML = visible.map(({ block: b, index: i }) => {
    const count = b.rows?.length ?? b.pax ?? 0;
    const passengers = (b.passengers || []).map((p, idx) => {
      const name = p.name || (p.passport_no ? p.passport_no : 'Kimlik boş');
      const sex = p.sex ? ` ${p.sex}` : '';
      const cls = p.name || p.passport_no ? 'block-passenger' : 'block-passenger empty';
      return `<span class="${cls}">${idx + 1}. ${escHtml(name)}${escHtml(sex)}</span>`;
    }).join('');
    
    const detail = state.selectedBlock === i ? renderBlockDetails(b, i) : '';
    const isRowSort = (document.getElementById('block-sort')?.value || 'row') === 'row';
    const dragAttrs = isRowSort ? `draggable="true" ondragstart="window.__onDragStart(event, ${i})" ondragend="window.__onDragEnd(event)" ondragover="window.__onDragOver(event)" ondragleave="window.__onDragLeave(event)" ondrop="window.__onDrop(event, ${i})"` : '';
    return `
    <div class="block-shell ${state.selectedBlock === i ? 'selected' : ''}" id="block-${i}" ${dragAttrs}>
    <div class="block-item ${state.selectedBlock === i ? 'selected' : ''}"
         onclick="window.__selectBlock(${i})">
      <div class="block-pax" ${isRowSort ? 'style="cursor: grab;" title="Sıralamak için sürükleyin"' : ''}>
        ${isRowSort ? '<span class="material-symbols-outlined text-[14px] mr-1 opacity-50">drag_indicator</span>' : ''}
        PAX ${b.pax ?? '?'}
      </div>
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
    ${detail}
    </div>
  `; }).join('');
}

function filteredBlocks() {
  const query = (document.getElementById('block-search')?.value || '').trim().toLocaleUpperCase('tr-TR');
  const filter = document.getElementById('block-filter')?.value || '';
  const sort = document.getElementById('block-sort')?.value || 'row';
  let rows = state.blocks.map((block, index) => ({ block, index }));
  if (query) {
    rows = rows.filter(({ block }) => [
      block.lead_name, block.hotel, block.agency, block.balloon, block.driver,
      ...(block.passengers || []).map(p => p.name),
    ].join(' ').toLocaleUpperCase('tr-TR').includes(query));
  }
  if (filter) {
    rows = rows.filter(({ block }) => {
      if (filter.startsWith('balloon_')) {
        return block.balloon === filter.replace('balloon_', '');
      }
      const missing = (block.passengers || []).some(p => !p.name || !p.passport_no || !p.nationality || !p.sex);
      return filter === 'missing' ? missing : !missing;
    });
  }
  rows.sort((a, b) => {
    if (sort === 'pickup') return String(a.block.pickup || '99:99').localeCompare(String(b.block.pickup || '99:99'));
    if (sort === 'pax') return Number(b.block.pax || 0) - Number(a.block.pax || 0);
    if (sort === 'name') return String(a.block.lead_name || '').localeCompare(String(b.block.lead_name || ''), 'tr');
    return Number(a.block.lead_row) - Number(b.block.lead_row);
  });
  return rows;
}

window.__renderPlanning = renderBlocks;

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
  state.selectedBlock = state.selectedBlock === index ? null : index;
  renderBlocks();
};

window.__onDragStart = function(e, index) {
  e.dataTransfer.setData('text/plain', index);
  e.target.style.opacity = '0.5';
};
window.__onDragEnd = function(e) {
  e.target.style.opacity = '1';
};
window.__onDragOver = function(e) {
  e.preventDefault();
  const shell = e.target.closest('.block-shell');
  if (shell) shell.style.borderTop = '2px solid var(--primary)';
};
window.__onDragLeave = function(e) {
  const shell = e.target.closest('.block-shell');
  if (shell) shell.style.borderTop = '';
};
window.__onDrop = async function(e, targetIndex) {
  e.preventDefault();
  const shell = e.target.closest('.block-shell');
  if (shell) shell.style.borderTop = '';
  
  const sourceIndex = parseInt(e.dataTransfer.getData('text/plain'), 10);
  if (sourceIndex === targetIndex || isNaN(sourceIndex)) return;
  
  const sourceBlock = state.blocks[sourceIndex];
  const targetBlock = state.blocks[targetIndex];
  if (!sourceBlock || !targetBlock) return;
  
  try {
    toast.info('Sıralanıyor', 'Excel satırları güncelleniyor...');
    const res = await api.post('/api/planning/reorder-block', {
      sheet: state.currentSheet,
      source_rows: sourceBlock.rows,
      target_row: targetBlock.lead_row,
      expected_revision: state.revision
    });
    window.__loadDay();
  } catch (err) {
    toast.error('Sıralama hatası', err.message);
  }
};

function renderBlockDetails(block, index) {
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

  const formHtml = fields.map(f => `
    <div class="form-group">
      <label class="form-label">${f.label}${helpIcon(operationHelp[f.key] || `${f.label} alanı planlama Excel'ine yazılır.`)}</label>
      <input class="form-input" id="op-${f.key}" type="${f.type || 'text'}"
             value="${escHtml(f.value)}" placeholder="${f.placeholder || ''}"
             ${f.width ? `style="width:${f.width}"` : ''} />
    </div>
  `).join('');

  const passengerHtml = (block.passengers || []).map((p, idx) => {
    const display = p.name || p.passport_no || 'Kimlik boş';
    const meta = [p.nationality, p.sex, p.passport_no, `Satır ${p.row}`].filter(Boolean).join(' · ');
    return `
      <div class="passenger-row ${p.name || p.passport_no ? '' : 'empty'}">
        <div class="min-w-0">
          <strong>${idx + 1}. ${escHtml(display)}</strong>
          <span>${escHtml(meta)}</span>
        </div>
        <button class="btn-ghost btn-icon danger" title="Yolcuyu sil"
                onclick="event.stopPropagation(); window.__deletePassenger(${index}, ${p.row})">
          <span class="material-symbols-outlined">person_remove</span>
        </button>
      </div>
    `;
  }).join('');

  setTimeout(() => attachOperationComboboxes(), 0);
  return `
    <div class="block-details animate-fade-in" onclick="event.stopPropagation()">
      <div class="detail-panel">
        <div class="detail-header">
          <div class="card-title">
            <span class="material-symbols-outlined">edit</span> Operasyon Bilgileri
          </div>
          <button class="btn-success flex items-center gap-2" onclick="window.__saveOperation()">
            <span class="material-symbols-outlined text-sm">save</span> Kaydet
          </button>
        </div>
        <div class="form-row">${formHtml}</div>
      </div>
      <div class="detail-panel">
        <div class="detail-header">
          <div class="card-title">
            <span class="material-symbols-outlined">groups</span> Yolcular
          </div>
          <span class="badge badge-blue">${block.passengers?.length || 0} kişi</span>
        </div>
        <div class="passenger-list">${passengerHtml || '<div class="empty-desc">Yolcu yok.</div>'}</div>
      </div>
    </div>
  `;
}

const operationHelp = {
  pax: 'Rezervasyondaki toplam kişi sayısıdır. Değiştirildiğinde gerçek yolcu satırları da büyütülür veya küçültülür.',
  room: 'Oda numarası veya acente/otel irtibat bilgisidir.',
  hotel: 'Misafirlerin alınacağı oteldir.',
  pickup: 'Şoförün misafirleri otelden alacağı saattir.',
  reserved_by: 'Rezervasyonu sisteme ileten kişi veya personeldir.',
  agency: 'Rezervasyonu gönderen acentedir.',
  company: 'Misafirin uçacağı işletme bilgisidir.',
  balloon: 'Manifesto ve kapasite hesabında kullanılan balon kodudur.',
  pilot: 'Bu balonda görevli pilottur.',
  driver: 'Pickup aracı veya şoför numarasıdır.',
  coming_place: 'Misafirin pickup sonrası geleceği noktadır.',
  note: 'Operasyon ekibinin görmesi gereken kısa nottur.',
};

function attachOperationComboboxes() {
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
  
  const btn = document.querySelector('button[onclick="window.__saveOperation()"]');
  if (btn) {
    btn.innerHTML = '<span class="material-symbols-outlined animate-spin text-sm" style="vertical-align: text-bottom; margin-right: 4px;">progress_activity</span> Kaydediliyor...';
    btn.disabled = true;
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
      expected_revision: state.revision,
    });
    toast.success('Kaydedildi', 'Operasyon bilgileri planlamaya yazıldı');
    window.__loadDay();
  } catch (err) {
    if (err.status === 409 && String(err.message).includes('Açık onay')) {
      if (confirm(`${err.message}\n\nYolcu bilgileri silinerek devam edilsin mi?`)) {
        try {
          await api.post('/api/planning/write-operation', {
            sheet: state.currentSheet, lead_row: block.lead_row, rows: block.rows,
            fields, expected_revision: state.revision, allow_data_loss: true,
          });
          toast.success('Kaydedildi', 'PAX ve operasyon bilgileri güncellendi');
          return window.__loadDay();
        } catch (retryErr) { 
          if (btn) { btn.innerHTML = '<span class="material-symbols-outlined text-sm">save</span> Kaydet'; btn.disabled = false; }
          return toast.error('Kaydetme hatası', retryErr.message); 
        }
      }
    }
    if (btn) { btn.innerHTML = '<span class="material-symbols-outlined text-sm">save</span> Kaydet'; btn.disabled = false; }
    toast.error('Kaydetme hatası', err.message);
  }
};

window.__deleteBlock = async function(index) {
  const block = state.blocks[index];
  if (!block) return;
  const who = block.lead_name || block.hotel || `PAX ${block.pax ?? '?'}`;
  if (!confirm(`"${who}" rezervasyonu silinsin mi? (${block.rows?.length || 0} satır)`)) return;
  try {
    await api.post('/api/planning/delete-block', { sheet: state.currentSheet, rows: block.rows, expected_revision: state.revision });
    toast.info('Silindi', `${who} rezervasyonu kaldırıldı`);
    state.selectedBlock = null;
    window.__loadDay();
  } catch (err) {
    toast.error('Silme hatası', err.message);
  }
};

window.__deletePassenger = async function(index, row) {
  const block = state.blocks[index];
  if (!block) return;
  const passenger = (block.passengers || []).find(p => Number(p.row) === Number(row));
  const who = passenger?.name || passenger?.passport_no || `Satır ${row}`;
  if (!confirm(`"${who}" bu PAX içinden silinsin mi?`)) return;
  try {
    await api.post('/api/planning/delete-passenger', {
      sheet: state.currentSheet,
      lead_row: block.lead_row,
      rows: block.rows,
      row,
      expected_revision: state.revision,
    });
    toast.info('Yolcu silindi', `${who} rezervasyondan çıkarıldı`);
    window.__loadDay();
  } catch (err) {
    toast.error('Yolcu silinemedi', err.message);
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

  const btn = document.querySelector('button[onclick="window.__submitReservation()"]');
  if (btn) {
    btn.innerHTML = '<span class="material-symbols-outlined animate-spin text-sm" style="vertical-align: text-bottom; margin-right: 4px;">progress_activity</span> Kaydediliyor...';
    btn.disabled = true;
  }

  const body = { sheet: state.currentSheet, pax };
  for (const key of ['hotel','agency','room','reserved_by','note']) {
    const v = document.getElementById(`nr-${key}`)?.value.trim();
    if (v) body[key] = v;
  }

  try {
    body.expected_revision = state.revision;
    const res = await api.post('/api/planning/create-block', body);
    modal.close();
    if (res.overflow) {
      toast.warning('Balon atandı (taşma)', res.message);
    } else {
      toast.success('Rezervasyon oluşturuldu', res.message);
    }
    window.__loadDay();
  } catch (err) {
    if (btn) {
      btn.innerHTML = 'Oluştur & Balon Ata';
      btn.disabled = false;
    }
    if (err.detail?.code === 'capacity_confirmation_required') {
      return showCapacityChoice(body, err.detail);
    }
    toast.error('Oluşturma hatası', err.message);
  }
};

window.__openMonthlyPlanModal = function() {
  const d = new Date();
  const currentYear = d.getFullYear();
  const currentMonth = d.getMonth() + 1;
  const ALLOW_CURRENT_MONTH = true;

  const monthsTR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];

  let yearOptions = '';
  for (let y = currentYear; y <= currentYear + 2; y++) {
    yearOptions += `<option value="${y}">${y}</option>`;
  }

  modal.open('Uçuş Planı Oluştur', `
    <div class="mb-4 text-sm text-on-surface-variant">
      Oluşturmak istediğiniz uçuş planı ayını seçin. Seçilen aya göre şablon çoğaltılarak temiz bir Excel dosyası kaydedilecektir.
    </div>
    <div class="form-group mb-4">
      <label class="form-label">Yıl</label>
      <select class="form-select w-full" id="mp-year" onchange="window.__renderMonthGrid()">
        ${yearOptions}
      </select>
    </div>
    <div class="form-group mb-6">
      <label class="form-label">Ay</label>
      <div id="mp-month-grid" class="grid grid-cols-3 gap-2"></div>
    </div>
    <div class="flex justify-end gap-3">
      <button class="btn-secondary" onclick="modal.close()">İptal</button>
      <button class="btn-primary" onclick="window.__submitMonthlyPlan()" id="btn-mp-submit" disabled>Devam / Oluştur</button>
    </div>
  `);

  window.selectedMonthlyPlan = null;
  window.__renderMonthGrid();
};

window.__renderMonthGrid = function() {
  const d = new Date();
  const currentYear = d.getFullYear();
  const currentMonth = d.getMonth() + 1; // 1-12
  const ALLOW_CURRENT_MONTH = true;

  const yearSel = document.getElementById('mp-year');
  if (!yearSel) return;
  const selectedYear = parseInt(yearSel.value, 10);
  const grid = document.getElementById('mp-month-grid');
  
  const monthsTR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
  
  let html = '';
  for (let m = 1; m <= 12; m++) {
    let disabled = false;
    if (selectedYear < currentYear) {
      disabled = true;
    } else if (selectedYear === currentYear) {
      if (ALLOW_CURRENT_MONTH) {
        if (m < currentMonth) disabled = true;
      } else {
        if (m <= currentMonth) disabled = true;
      }
    }

    const isSelected = window.selectedMonthlyPlan === m;
    const btnClass = disabled 
      ? 'bg-surface-variant opacity-50 cursor-not-allowed text-on-surface-variant' 
      : isSelected 
        ? 'bg-primary text-on-primary ring-2 ring-primary ring-offset-2 ring-offset-surface' 
        : 'bg-surface-variant hover:bg-surface text-on-surface cursor-pointer';

    html += `<div class="p-3 text-center rounded-lg text-sm font-medium transition-all ${btnClass}" 
                 ${!disabled ? `onclick="window.__selectMonthlyPlan(${m})"` : ''}>
               ${monthsTR[m-1]}
             </div>`;
  }
  grid.innerHTML = html;
  
  // Re-check submit button
  const submitBtn = document.getElementById('btn-mp-submit');
  if (submitBtn) {
    submitBtn.disabled = !window.selectedMonthlyPlan;
  }
};

window.__selectMonthlyPlan = function(m) {
  window.selectedMonthlyPlan = m;
  window.__renderMonthGrid();
};

window.__submitMonthlyPlan = async function() {
  const year = parseInt(document.getElementById('mp-year').value, 10);
  const month = window.selectedMonthlyPlan;
  if (!year || !month) return;
  
  const btn = document.getElementById('btn-mp-submit');
  btn.innerHTML = '<span class="material-symbols-outlined animate-spin">progress_activity</span> Bekleniyor...';
  btn.disabled = true;

  try {
    const res = await api.post('/api/planning/generate-monthly', { year, month });
    if (res.success) {
      toast.success('Başarılı', res.message || 'Excel dosyası kaydedildi ve açıldı.');
      modal.close();
    } else {
      toast.info('İptal', res.message || 'İşlem iptal edildi.');
      modal.close();
    }
  } catch (err) {
    toast.error('Oluşturma hatası', err.message);
    btn.innerHTML = 'Devam / Oluştur';
    btn.disabled = false;
  }
};

function showCapacityChoice(body, detail) {
  window.__pendingOverflowBody = body;
  modal.open('Balon Kapasitesi Doldu', `
    <p class="text-on-surface-variant mb-4">Grup hiçbir balona kapasite içinde sığmıyor. Hedef balonu seçip kapasite aşımını açıkça onaylayın veya iptal edin.</p>
    <div class="space-y-2">${(detail.balloon_codes || []).map(code => `
      <label class="flex items-center justify-between rounded-lg border border-white/10 p-3 cursor-pointer">
        <span><input type="radio" name="overflow-balloon" value="${code}" class="mr-3" />${code}</span>
        <strong>${detail.balloon_load?.[code] || 0}/${detail.capacity}</strong>
      </label>`).join('')}</div>
  `, `
    <button class="btn-secondary" onclick="window.__closeModal()">İptal</button>
    <button class="btn-primary" onclick="window.__confirmOverflow()">Seçimi Onayla</button>
  `);
}

window.__confirmOverflow = async function() {
  const body = { ...(window.__pendingOverflowBody || {}) };
  const selected = document.querySelector('input[name="overflow-balloon"]:checked')?.value;
  if (!selected) return toast.warning('Hedef balonu seçin');
  body.requested_balloon = selected;
  body.allow_overflow = true;
  try {
    const res = await api.post('/api/planning/create-block', body);
    modal.close();
    toast.warning('Kapasite aşımı onaylandı', `${res.balloon} balonuna atandı`);
    window.__loadDay();
  } catch (err) { toast.error('Oluşturma hatası', err.message); }
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
    await api.post('/api/planning/create-day', { new_sheet: name, source_sheet: source, expected_revision: state.revision || null });
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
