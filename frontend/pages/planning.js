/* ═══════════════════════════════════════════════════════════════════
   Planlama — Gün seçimi, rezervasyon blokları, operasyon formu
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, modal, renderHeader, helpIcon, registerUnsavedCheck } from '/app.js';
import { attachCombobox } from '/combobox.js';
import { openIdentityEditor } from '/identity_edit.js';

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

let calState = {
  currentYear: new Date().getFullYear(),
  currentMonth: new Date().getMonth() + 1, // 1-12
};

const monthsTR = [
  "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
  "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
];

// Gün yükleme istek token'ı: hızlı ardışık tıklamada yalnız SON isteğin yanıtı uygulanır.
let loadToken = 0;
let creatingDay = false;

// Seçili bloğu indeks yerine kimliğiyle izlemek için imza. Sürükle-bırak sonrası sunucu
// satırları kaydırdığından lead_row değişir; imza (lider + PAX + yolcular) değişmez.
function blockKey(block) {
  if (!block) return '';
  const people = (block.passengers || []).map(p => p.passport_no || p.name || '').join(',');
  return `${block.lead_name || ''}|${block.pax ?? ''}|${block.hotel || ''}|${people}`;
}

function selectedRef() {
  const block = state.selectedBlock !== null ? state.blocks[state.selectedBlock] : null;
  return block ? { leadRow: block.lead_row, key: blockKey(block) } : null;
}

// Yeni blok listesinde seçimi geri bul. byKey: satırlar kaydıysa (sıralama) imzayla eşle.
function restoreSelection(ref, { byKey = false } = {}) {
  if (!ref) { state.selectedBlock = null; return; }
  let idx = byKey
    ? state.blocks.findIndex(b => blockKey(b) === ref.key)
    : state.blocks.findIndex(b => b.lead_row === ref.leadRow);
  if (idx < 0 && !byKey) idx = state.blocks.findIndex(b => blockKey(b) === ref.key);
  state.selectedBlock = idx < 0 ? null : idx;
}

function applyDayData(data) {
  state.blocks = data.blocks || [];
  state.balloons = data.balloon_codes || [];
  state.balloonLoad = data.balloon_load || {};
  state.capacity = data.capacity || 28;
  state.revision = data.workbook_revision || '';
  state.readiness = data.readiness || null;
}

const OPERATION_KEYS = ['pax','room','hotel','pickup','reserved_by','agency','company','balloon','pilot','driver','coming_place','note'];

// Açık operasyon formunda kaydedilmemiş düzenleme veya kaydı süren sıralama varsa
// pencere yenileme/kapama onay ister.
registerUnsavedCheck('planning', () => {
  if (state.pendingReorder) return true;
  if (!document.getElementById('op-pax')) return false; // form bu ekranda açık değil
  const block = state.selectedBlock !== null ? state.blocks[state.selectedBlock] : null;
  if (!block) return false;
  return OPERATION_KEYS.some(key => {
    const el = document.getElementById(`op-${key}`);
    return el && el.value.trim() !== String(block[key] ?? '').trim();
  });
});

function todayStart() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export async function render(container) {
  loadToken++; // önceki sayfa ziyaretinden kalan yanıtlar uygulanmasın
  renderHeader('Planlama', 'Uçuş günü yönetimi ve rezervasyon blokları');

  container.innerHTML = `
    <div class="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-6 items-start">
      <!-- SOL KOLON: Takvim ve Balon Dolulukları -->
      <div class="flex flex-col gap-6 w-full">
        <!-- Takvim Kartı -->
        <div class="calendar-widget rounded-3xl p-6 w-full animate-in">
          <!-- Takvim Başlığı -->
          <div class="text-center font-bold text-lg mb-4 text-on-surface" id="calendar-month-year">
            Yükleniyor...
          </div>
          
          <!-- Gün Kısaltmaları -->
          <div class="calendar-grid mb-2">
            <div class="calendar-day-header">Pz</div>
            <div class="calendar-day-header">Sa</div>
            <div class="calendar-day-header">Ça</div>
            <div class="calendar-day-header">Pe</div>
            <div class="calendar-day-header">Cu</div>
            <div class="calendar-day-header">Ct</div>
            <div class="calendar-day-header">Pa</div>
          </div>
          
          <!-- Günler Matrisi -->
          <div class="calendar-grid mb-4" id="calendar-days-grid">
            <!-- Dinamik olarak dolacak -->
          </div>
          
          <!-- Gezinme Butonları -->
          <div class="flex justify-center gap-4">
            <button class="calendar-nav-btn" onclick="window.__prevMonth()">
              <span class="material-symbols-outlined text-[18px]">chevron_left</span>
            </button>
            <button class="btn-ghost text-xs px-3 py-1" id="btn-create-remaining" style="display:none" onclick="window.__createRemainingDays()"></button>
            <button class="calendar-nav-btn" onclick="window.__nextMonth()">
              <span class="material-symbols-outlined text-[18px]">chevron_right</span>
            </button>
          </div>
        </div>

        <!-- Balon Dolulukları Kartı -->
        <div class="card p-6 w-full animate-in" id="sidebar-balloon-load-card" style="display:none">
          <div class="card-title text-base mb-4 flex items-center gap-2">
            <span class="material-symbols-outlined text-[20px]">monitoring</span> Balon Dolulukları
          </div>
          <div class="flex flex-col" id="sidebar-balloon-load-list">
            <!-- Dinamik olarak dolacak -->
          </div>
        </div>
      </div>

      <!-- SAĞ KOLON: Boş Durum veya Rezervasyon Listesi -->
      <div class="w-full">
        <!-- Boş Durum (Gün seçilmediğinde) -->
        <div class="card text-center p-12 flex flex-col items-center justify-center min-h-[350px] animate-in" id="empty-planning-state">
          <div class="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-4">
            <span class="material-symbols-outlined text-3xl">calendar_month</span>
          </div>
          <h3 class="font-headline text-headline-sm text-on-surface mb-4">Uçuş Planı Seçilmedi</h3>
          <div class="text-on-surface-variant max-w-lg space-y-4 text-sm text-left bg-surface/30 p-6 rounded-2xl border border-white/5">
            <p><strong class="text-on-surface">Ne yok?</strong> Ekranda henüz görüntülenen bir uçuş planı veya rezervasyon listesi yok.</p>
            <p><strong class="text-on-surface">Neden olabilir?</strong> İşlem yapmak istediğiniz tarih henüz sol taraftaki takvimden seçilmemiş olabilir.</p>
            <p><strong class="text-on-surface">Şimdi ne yapmalıyım?</strong> Sol taraftaki takvimden uçuş tarihinizi seçebilirsiniz. İşlem yapacağınız gün henüz yoksa takvimde bugün veya ileri bir boş güne tıklayıp onaylayarak yeni gün oluşturabilirsiniz.</p>
          </div>
        </div>

        <!-- Rezervasyon Blokları Kartı (Gün seçildiğinde) -->
        <div class="card animate-in w-full" id="blocks-section" style="display:none">
          <div class="card-header">
            <div class="card-title flex items-center">
              <span class="material-symbols-outlined mr-2">group</span> Rezervasyon Blokları
              <span id="reorder-status" style="display: none;"></span>
            </div>
            <div class="flex items-center gap-3">
              <span class="text-sm text-on-surface-variant" id="blocks-count"></span>
              <button class="btn-primary flex items-center gap-2" onclick="window.__newReservation()">
                <span class="material-symbols-outlined text-sm">add</span> Yeni Rezervasyon
              </button>
            </div>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
            <input class="form-input md:col-span-2" id="block-search" placeholder="İsim, otel, acente, balon veya şoför ara" oninput="window.__renderPlanningDebounced()" />
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
      </div>
    </div>
  `;

  loadSheets();
}

function parseSheetDate(sheetName) {
  const parts = sheetName.split('.');
  if (parts.length === 3) {
    return {
      day: parseInt(parts[0], 10),
      month: parseInt(parts[1], 10),
      year: parseInt(parts[2], 10)
    };
  }
  return null;
}

function getDaysInMonth(year, month) {
  return new Date(year, month, 0).getDate();
}

function getFirstDayOfWeek(year, month) {
  let day = new Date(year, month - 1, 1).getDay();
  // Pazar 0'dır, onu 6 yapıp Pazartesi'yi 0 yapalım (Mo ile başlar)
  return day === 0 ? 6 : day - 1;
}

function formatCalendarDate(day, month, year) {
  const dd = String(day).padStart(2, '0');
  const mm = String(month).padStart(2, '0');
  return `${dd}.${mm}.${year}`;
}

window.__prevMonth = function() {
  calState.currentMonth--;
  if (calState.currentMonth < 1) {
    calState.currentMonth = 12;
    calState.currentYear--;
  }
  renderCalendar();
};

window.__nextMonth = function() {
  calState.currentMonth++;
  if (calState.currentMonth > 12) {
    calState.currentMonth = 1;
    calState.currentYear++;
  }
  renderCalendar();
};

function renderCalendar() {
  const monthYearEl = document.getElementById('calendar-month-year');
  const daysGridEl = document.getElementById('calendar-days-grid');
  if (!monthYearEl || !daysGridEl) return;

  monthYearEl.textContent = `${monthsTR[calState.currentMonth - 1]} ${calState.currentYear}`;

  const daysInMonth = getDaysInMonth(calState.currentYear, calState.currentMonth);
  const firstDay = getFirstDayOfWeek(calState.currentYear, calState.currentMonth);

  let html = '';

  // Önceki aydan kalan boşluklar
  for (let i = 0; i < firstDay; i++) {
    html += '<div class="calendar-day empty"></div>';
  }

  // Ayın günleri
  const today = todayStart();
  for (let day = 1; day <= daysInMonth; day++) {
    const formatted = formatCalendarDate(day, calState.currentMonth, calState.currentYear);
    const hasPlan = state.sheets.includes(formatted);
    const isSelected = state.currentSheet === formatted;
    const date = new Date(calState.currentYear, calState.currentMonth - 1, day);
    const isPast = date < today;
    const isToday = date.getTime() === today.getTime();

    let cls = 'calendar-day';
    if (isSelected) {
      cls += ' selected';
    } else if (hasPlan) {
      cls += ' has-plan';
    } else if (isPast) {
      cls += ' past';
    } else {
      cls += ' no-plan';
    }
    if (isToday) cls += ' today';

    if (hasPlan) {
      html += `<div class="${cls}" onclick="window.__loadDayDate('${formatted}')" title="Günü Yükle: ${formatted}">${day}</div>`;
    } else if (isPast) {
      // Geçmiş ve planı olmayan gün: yanlışlıkla gün oluşturulmasın diye tıklanamaz
      html += `<div class="${cls}" title="Geçmiş tarih — uçuş günü yok">${day}</div>`;
    } else {
      html += `<div class="${cls}" onclick="window.__askCreateDay('${formatted}')" title="Uçuş günü yok: ${formatted}">${day}</div>`;
    }
  }

  daysGridEl.innerHTML = html;

  const remainBtn = document.getElementById('btn-create-remaining');
  if (remainBtn) {
    const n = state.sheets.length ? remainingMissingDays(calState.currentYear, calState.currentMonth).length : 0;
    remainBtn.style.display = n ? '' : 'none';
    remainBtn.textContent = `Kalan ${n} günü boş aç`;
  }
}

async function loadSheets() {
  const token = loadToken;
  try {
    const data = await api.get('/api/planning/sheets');
    if (token !== loadToken) return;
    state.sheets = data.sheets || [];
    state.source = data.source || 'excel';

    // Takvim başlangıç tarihini son uçuş gününe eşitleyelim
    if (state.sheets.length) {
      const lastSheet = state.sheets[state.sheets.length - 1];
      const parsed = parseSheetDate(lastSheet);
      if (parsed) {
        calState.currentYear = parsed.year;
        calState.currentMonth = parsed.month;
      }
    }

    renderCalendar();
  } catch (err) {
    if (token !== loadToken) return;
    toast.error('Sayfalar yüklenemedi', err.message);
    renderCalendar(); // takvim "Yükleniyor..." durumunda asılı kalmasın
  }
}

function showPlanningSkeletons() {
  const section = document.getElementById('blocks-section');
  const list = document.getElementById('blocks-list');
  const emptyState = document.getElementById('empty-planning-state');
  if (section) section.style.display = '';
  if (emptyState) emptyState.style.display = 'none';
  if (list) {
    list.innerHTML = `
      <div class="skeleton-card shimmer min-h-[90px] mb-3"></div>
      <div class="skeleton-card shimmer min-h-[90px] mb-3"></div>
      <div class="skeleton-card shimmer min-h-[90px] mb-3"></div>
    `;
  }
}

window.__loadDay = function() {
  if (state.currentSheet) {
    window.__loadDayDate(state.currentSheet);
  }
};

window.__loadDayDate = async function(sheet) {
  const token = ++loadToken;
  const sameDay = state.currentSheet === sheet;
  // Başka güne geçerken seçim taşınmaz (aynı satır no başka günde başka rezervasyondur)
  const ref = sameDay ? selectedRef() : null;
  state.currentSheet = sheet;
  renderCalendar();
  showPlanningSkeletons();

  const monthYearEl = document.getElementById('calendar-month-year');
  if (monthYearEl) {
    monthYearEl.innerHTML = `<span class="btn-spinner mr-2"></span> Yükleniyor...`;
  }

  try {
    const data = await api.get(`/api/planning/load?sheet=${encodeURIComponent(sheet)}`);
    if (token !== loadToken) return; // daha yeni bir istek var — eski yanıtı uygulama
    applyDayData(data);
    restoreSelection(ref);
    let lists = {};
    try { lists = (await api.get('/api/lists')).options || {}; } catch (e) { lists = {}; }
    if (token !== loadToken) return;
    state.lists = lists;

    const filterSelect = document.getElementById('block-filter');
    if (filterSelect) {
      const currentVal = filterSelect.value;
      let html = `<option value="">Tüm rezervasyonlar</option>
                  <option value="missing">Pasaportu eksik</option>
                  <option value="ready">Kimliği hazır</option>`;
      state.balloons.forEach(b => {
        if (b) html += `<option value="balloon_${escHtml(b)}">${escHtml(b)} balonu</option>`;
      });
      filterSelect.innerHTML = html;
      if (Array.from(filterSelect.options).some(o => o.value === currentVal)) {
        filterSelect.value = currentVal;
      }
    }

    renderBlocks();
    renderBalloonLoad();
    // Başarılı yüklemede toast yok: takvimde seçili gün ve liste zaten geri bildirim.
  } catch (err) {
    if (token !== loadToken) return;
    toast.error('Yükleme hatası', err.message);
    const list = document.getElementById('blocks-list');
    if (list) {
      list.innerHTML = `
        <div class="empty-state">
          <div class="material-symbols-outlined empty-icon text-danger">error</div>
          <div class="empty-title">Gün yüklenemedi</div>
          <div class="empty-desc">${escHtml(err.message || '')}</div>
          <button class="btn-secondary mt-4" onclick="window.__loadDay()">Tekrar dene</button>
        </div>`;
    }
  } finally {
    if (token === loadToken) renderCalendar();
  }
};

// Planı olmayan bugün/ileri tarih: önce kısa onay, sonra oluşturma penceresi.
window.__askCreateDay = async function(date) {
  if (!state.sheets.length) {
    toast.warning('Kaynak gün yok', 'Yeni gün mevcut bir günden kopyalanır; önce planlama dosyasını kontrol edin.');
    return;
  }
  const ok = await modal.confirm({
    title: 'Uçuş günü yok',
    bodyHtml: `<p class="text-on-surface"><strong>${escHtml(date)}</strong> için sayfa yok. En yakın önceki günün düzeniyle (balonlar, firma, pilot) boş bir gün açılsın mı?</p>`,
    confirmLabel: 'Boş gün aç',
  });
  if (!ok || creatingDay) return;
  creatingDay = true;
  try {
    await api.post('/api/planning/create-day', { new_sheet: date });
    toast.success('Gün açıldı', `${date} boş şablonla oluşturuldu`);
    await loadSheets();
    window.__loadDayDate(date);
  } catch (err) {
    toast.error('Gün açılamadı', err.message);
  } finally {
    creatingDay = false;
  }
};

window.__createRemainingDays = async function() {
  if (creatingDay) return;
  const y = calState.currentYear, m = calState.currentMonth;
  const missing = remainingMissingDays(y, m);
  if (!missing.length) { toast.info('Eksik gün yok', 'Bu ayın kalan günlerinin hepsi var.'); return; }
  const ok = await modal.confirm({
    title: 'Kalan günleri aç',
    bodyHtml: `<p class="text-on-surface">${escHtml(monthsTR[m - 1])} ${y} için <strong>${missing.length}</strong> gün boş şablonla açılacak (${escHtml(missing[0])} – ${escHtml(missing[missing.length - 1])}). Her gün, kendinden önceki günün balon/pilot düzenini alır.</p>`,
    confirmLabel: `${missing.length} günü aç`,
  });
  if (!ok) return;
  creatingDay = true;
  try {
    const res = await api.post('/api/planning/create-missing-days', { year: y, month: m });
    toast.success('Günler açıldı', `${(res.created || []).length} gün oluşturuldu`);
    await loadSheets();
    renderCalendar();
  } catch (err) {
    toast.error('Günler açılamadı', err.message);
  } finally {
    creatingDay = false;
  }
};

function remainingMissingDays(year, month) {
  const today = todayStart();
  const out = [];
  for (let d = 1; d <= getDaysInMonth(year, month); d++) {
    const date = new Date(year, month - 1, d);
    const name = formatCalendarDate(d, month, year);
    if (date >= today && !state.sheets.includes(name)) out.push(name);
  }
  return out;
}

window.__createDayDate = function(date) {
  modal.open('Yeni Gün Oluştur', `
    <div class="form-group">
      <label class="form-label">Yeni gün adı</label>
      <input class="form-input" id="new-day-name" value="${escHtml(date)}" readonly />
      <div class="form-help">Bu tarihe yeni uçuş günü sayfası oluşturulacak.</div>
    </div>
    <div class="form-group mt-4">
      <label class="form-label">Kaynak gün (kopyalanacak)</label>
      <select class="form-select" id="new-day-source">
        ${state.sheets.map(s => `<option value="${escHtml(s)}">${escHtml(s)}</option>`).join('')}
      </select>
    </div>
  `, `
    <button class="btn-secondary" onclick="window.__closeModal()">İptal</button>
    <button class="btn-primary" id="btn-new-day" onclick="window.__submitNewDayDate()">Oluştur</button>
  `);
};

window.__submitNewDayDate = async function() {
  if (creatingDay) return;
  const name = document.getElementById('new-day-name')?.value.trim();
  const source = document.getElementById('new-day-source')?.value;
  if (!name) { toast.warning('Gün adı girin'); return; }

  const btn = document.getElementById('btn-new-day');
  creatingDay = true;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="material-symbols-outlined animate-spin text-sm" style="vertical-align: text-bottom; margin-right: 4px;">progress_activity</span> Oluşturuluyor...';
  }
  try {
    await api.post('/api/planning/create-day', { new_sheet: name, source_sheet: source });
    toast.success('Gün oluşturuldu', `${name} başarıyla eklendi`);
    modal.close();
    await loadSheets();
    window.__loadDayDate(name);
  } catch (err) {
    toast.error('Oluşturma hatası', err.message);
    if (btn?.isConnected) {
      btn.disabled = false;
      btn.textContent = 'Oluştur';
    }
  } finally {
    creatingDay = false;
  }
};

function renderBlocks() {
  const section = document.getElementById('blocks-section');
  const list = document.getElementById('blocks-list');
  const count = document.getElementById('blocks-count');
  const emptyState = document.getElementById('empty-planning-state');
  const loadSidebar = document.getElementById('sidebar-balloon-load-card');
  if (!section || !list) return;

  if (state.currentSheet) {
    section.style.display = '';
    if (emptyState) emptyState.style.display = 'none';
    if (loadSidebar) loadSidebar.style.display = '';
  } else {
    section.style.display = 'none';
    if (emptyState) emptyState.style.display = '';
    if (loadSidebar) loadSidebar.style.display = 'none';
    return;
  }
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

  list.innerHTML = visible.map(({ block: b, index: i }, listSeq) => {
    const count = b.rows?.length ?? b.pax ?? 0;
    const passengers = (b.passengers || []).map((p, idx) => {
      const name = p.name || (p.passport_no ? p.passport_no : 'Kimlik boş');
      const sex = p.sex ? ` ${p.sex}` : '';
      const cls = p.name || p.passport_no ? 'block-passenger' : 'block-passenger empty';
      return `<span class="${cls}">${idx + 1}. ${escHtml(name)}${escHtml(sex)}</span>`;
    }).join('');
    
    const detail = state.selectedBlock === i ? renderBlockDetails(b, i) : '';
    const isRowSort = (document.getElementById('block-sort')?.value || 'row') === 'row';
    const dragAttrs = (isRowSort && !state.pendingReorder) ? `draggable="true" ondragstart="window.__onDragStart(event, ${i})" ondragend="window.__onDragEnd(event)" ondragover="window.__onDragOver(event)" ondragleave="window.__onDragLeave(event)" ondrop="window.__onDrop(event, ${i})"` : '';
    return `
    <div class="block-shell ${state.selectedBlock === i ? 'selected' : ''}" id="block-${i}" ${dragAttrs}>
    <div class="block-item ${state.selectedBlock === i ? 'selected' : ''}"
         onclick="window.__selectBlock(${i})">
      <div class="block-seq-num">
        ${listSeq + 1}
      </div>
      <div class="block-pax" ${isRowSort ? 'style="cursor: grab;" title="Sıralamak için sürükleyin"' : ''}>
        ${isRowSort ? '<span class="material-symbols-outlined text-[14px] mr-1 opacity-50">drag_indicator</span>' : ''}
        PAX ${b.pax ?? '?'}
      </div>
      <div class="block-main">
        <div class="block-info">
          <span class="flex items-center gap-1 font-bold text-on-surface">
            ${escHtml(b.lead_name || '(isim yok)')}
          </span>
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">hotel</span> ${escHtml(b.hotel || '—')}
          </span>
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">domain</span> ${escHtml(b.agency || '—')}
          </span>
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">schedule</span> ${escHtml(b.pickup || '—')}
          </span>
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">directions_bus</span> Şoför ${escHtml(b.driver || '—')}
          </span>
        </div>
        ${passengers ? `<div class="block-passengers">${passengers}</div>` : ''}
      </div>
      <div class="flex items-center gap-2 ml-auto">
        <span class="badge badge-blue flex items-center gap-1">
          <span class="material-symbols-outlined text-[16px]">person</span> ${count} kişi
        </span>
        ${b.balloon ? `<div class="block-balloon">${escHtml(b.balloon)}</div>` : ''}
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
    return a.index - b.index;
  });
  return rows;
}

window.__renderPlanning = renderBlocks;

function renderBalloonLoad() {
  const el = document.getElementById('sidebar-balloon-load-list');
  if (!el) return;
  const cap = state.capacity || 28;
  const codes = state.balloons || [];
  el.innerHTML = codes.map(code => {
    const used = (state.balloonLoad || {})[code] || 0;
    const full = used >= cap;
    const cls = full ? 'badge-red' : (used > 0 ? 'badge-green' : 'badge-blue');
    return `
      <div class="flex items-center justify-between py-2.5 border-b border-white/5 last:border-0 text-sm">
        <span class="font-semibold text-on-surface">${escHtml(code)} Balonu</span>
        <span class="badge ${cls}">${used} / ${cap}</span>
      </div>
    `;
  }).join('') || '<div class="text-xs text-on-surface-variant italic p-2">Kayıtlı balon yok</div>';
}

window.__selectBlock = function(index) {
  state.selectedBlock = state.selectedBlock === index ? null : index;
  renderBlocks();
};

window.__onDragStart = function(e, index) {
  state.draggedIndex = index;
  e.dataTransfer.setData('text/plain', index);
  const shell = document.getElementById(`block-${index}`);
  if (shell) {
    shell.classList.add('is-dragging');
  }
};

window.__onDragEnd = function(e) {
  state.draggedIndex = null;
  document.querySelectorAll('.block-shell').forEach(el => {
    el.classList.remove('drag-hover-top', 'drag-hover-bottom', 'is-dragging');
  });
};

window.__onDragOver = function(e) {
  e.preventDefault();
  const shell = e.target.closest('.block-shell');
  if (shell) {
    const targetIndex = parseInt(shell.id.replace('block-', ''), 10);
    if (state.draggedIndex === targetIndex || isNaN(targetIndex) || state.draggedIndex === null) return;

    const rect = shell.getBoundingClientRect();
    const isTopHalf = e.clientY < rect.top + rect.height / 2;

    if (isTopHalf) {
      if (!shell.classList.contains('drag-hover-top')) {
        shell.classList.remove('drag-hover-bottom');
        shell.classList.add('drag-hover-top');
        shell.dataset.dropPos = 'before';
      }
    } else {
      if (!shell.classList.contains('drag-hover-bottom')) {
        shell.classList.remove('drag-hover-top');
        shell.classList.add('drag-hover-bottom');
        shell.dataset.dropPos = 'after';
      }
    }
  }
};

window.__onDragLeave = function(e) {
  const shell = e.target.closest('.block-shell');
  if (shell) {
    shell.classList.remove('drag-hover-top', 'drag-hover-bottom');
    delete shell.dataset.dropPos;
  }
};

window.__onDrop = function(e, targetIndex) {
  e.preventDefault();
  const shell = e.target.closest('.block-shell');
  let dropPos = 'before';
  if (shell) {
    dropPos = shell.dataset.dropPos || 'before';
    shell.classList.remove('drag-hover-top', 'drag-hover-bottom');
    delete shell.dataset.dropPos;
  }

  const sourceIndex = parseInt(e.dataTransfer.getData('text/plain'), 10);
  if (sourceIndex === targetIndex || isNaN(sourceIndex)) return;

  const sourceBlock = state.blocks[sourceIndex];
  const targetBlock = state.blocks[targetIndex];
  if (!sourceBlock || !targetBlock) return;

  if (!state.originalBlocks) {
    state.originalBlocks = [...state.blocks];
  }

  // Seçim indeksle değil blok nesnesiyle izlenir; taşıma sonrası yeni indeksi bulunur.
  const selectedObj = state.selectedBlock !== null ? state.blocks[state.selectedBlock] : null;
  const [movedBlock] = state.blocks.splice(sourceIndex, 1);
  let newTargetIdx = state.blocks.findIndex(b => b.lead_row === targetBlock.lead_row);
  if (dropPos === 'after') {
    state.blocks.splice(newTargetIdx + 1, 0, movedBlock);
  } else {
    state.blocks.splice(newTargetIdx, 0, movedBlock);
  }

  if (selectedObj) {
    const idx = state.blocks.indexOf(selectedObj);
    state.selectedBlock = idx < 0 ? null : idx;
  }

  state.pendingReorder = {
    sourceBlock,
    targetBlock,
    dropPos
  };

  renderBlocks();
  window.__autoSaveReorder();
};

window.__autoSaveReorder = async function() {
  if (!state.pendingReorder) return;
  const statusEl = document.getElementById('reorder-status');
  if (statusEl) {
    statusEl.innerHTML = `<span class="material-symbols-outlined animate-spin text-sm mr-1">progress_activity</span> Sıralama kaydediliyor...`;
    statusEl.style.display = 'inline-flex';
    statusEl.className = 'text-xs font-semibold text-primary/80 animate-pulse flex items-center ml-3';
  }

  const p = state.pendingReorder;
  let targetRow = p.targetBlock.lead_row;
  if (p.dropPos === 'after') {
    targetRow = p.targetBlock.rows[p.targetBlock.rows.length - 1] + 1;
  }

  try {
    await api.post('/api/planning/reorder-block', {
      sheet: state.currentSheet,
      source_rows: p.sourceBlock.rows,
      target_row: targetRow,
      expected_revision: state.revision
    });

    state.pendingReorder = null;
    state.originalBlocks = null;

    if (statusEl) {
      statusEl.innerHTML = `<span class="material-symbols-outlined text-[16px] text-success mr-1">check_circle</span> Sıralama kaydedildi`;
      statusEl.className = 'text-xs font-semibold text-success flex items-center ml-3';
      setTimeout(() => {
        if (!state.pendingReorder && statusEl.innerHTML.includes('kaydedildi')) {
          statusEl.style.display = 'none';
        }
      }, 2500);
    }

    // Sunucu satırları kaydırdı → lead_row'lar değişti; seçimi imzayla geri bul.
    await reloadDaySilently({ afterReorder: true });
  } catch (err) {
    toast.error('Sıralama kaydedilemedi', err.message);
    if (statusEl) {
      statusEl.innerHTML = `<span class="material-symbols-outlined text-[16px] text-danger mr-1">error</span> Hata`;
      statusEl.className = 'text-xs font-semibold text-danger flex items-center ml-3';
    }
    if (state.originalBlocks) {
      const selectedObj = state.selectedBlock !== null ? state.blocks[state.selectedBlock] : null;
      state.blocks = state.originalBlocks;
      if (selectedObj) {
        const idx = state.blocks.indexOf(selectedObj);
        state.selectedBlock = idx < 0 ? null : idx;
      }
    }
    state.pendingReorder = null;
    state.originalBlocks = null;
    renderBlocks();
  }
};

async function reloadDaySilently({ afterReorder = false } = {}) {
  if (!state.currentSheet) return;
  const token = ++loadToken;
  const sheet = state.currentSheet;
  try {
    const ref = selectedRef();
    const data = await api.get(`/api/planning/load?sheet=${encodeURIComponent(sheet)}`);
    if (token !== loadToken || sheet !== state.currentSheet) return;
    applyDayData(data);
    restoreSelection(ref, { byKey: afterReorder });

    renderBlocks();
    renderBalloonLoad();
  } catch (err) {
    console.error('Silent reload failed', err);
  }
}


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
        <div class="flex items-center gap-1 shrink-0">
          <button class="btn-ghost btn-icon" title="Kimliği düzelt"
                  onclick="event.stopPropagation(); window.__editPassenger(${index}, ${p.row})">
            <span class="material-symbols-outlined">edit</span>
          </button>
          <button class="btn-ghost btn-icon danger" title="Yolcuyu sil"
                  onclick="event.stopPropagation(); window.__deletePassenger(${index}, ${p.row})">
            <span class="material-symbols-outlined">person_remove</span>
          </button>
        </div>
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
  for (const key of OPERATION_KEYS) {
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

window.__editPassenger = function(index, row) {
  const block = state.blocks[index];
  if (!block) return;
  const p = (block.passengers || []).find(x => Number(x.row) === Number(row)) || { row };
  openIdentityEditor({
    sheet: state.currentSheet,
    row,
    values: p,
    expectedRevision: state.revision,
    onSaved: () => window.__loadDay(),
  });
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

function showCapacityChoice(body, detail) {
  window.__pendingOverflowBody = body;
  modal.open('Balon Kapasitesi Doldu', `
    <p class="text-on-surface-variant mb-4">Grup hiçbir balona kapasite içinde sığmıyor. Hedef balonu seçip kapasite aşımını açıkça onaylayın veya iptal edin.</p>
    <div class="space-y-2">${(detail.balloon_codes || []).map(code => `
      <label class="flex items-center justify-between rounded-lg border border-white/10 p-3 cursor-pointer">
        <span><input type="radio" name="overflow-balloon" value="${escHtml(code)}" class="mr-3" />${escHtml(code)}</span>
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

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function debounce(fn, delay = 200) {
  let timer = null;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

window.__renderPlanningDebounced = debounce(() => {
  if (typeof window.__renderPlanning === 'function') {
    window.__renderPlanning();
  }
}, 200);
