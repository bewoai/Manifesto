/* ═══════════════════════════════════════════════════════════════════
   Planlama — Gün seçimi, rezervasyon blokları, operasyon formu
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, modal, renderHeader, helpIcon, registerUnsavedCheck, balloonInk, envStripe, setBalloonCodes, routeParams } from '/app.js';
import { parseQuery, matchesBlock, describeTerms } from '/planning_search.js';
import { mountSheetGrid, sheetGridDirty } from '/sheet_grid.js';
import { attachCombobox } from '/combobox.js';
import { openIdentityEditor } from '/identity_edit.js';
import { capacityFor, balloonLimitText, isDailyCapacityExceeded, dailyCapacityConfirmOptions } from '/capacity_rules.js';
import { issueLabel, issueLeadRows, findBlockIndexForRow } from '/issue_links.js';

let state = {
  sheets: [],
  currentSheet: '',
  blocks: [],
  balloons: [],
  selectedBlock: null,
  source: 'excel',
  revision: '',
  readiness: null,
  issueFilter: null, // { sheet, code } — uyarıdan gelen blok filtresi
};

let calState = {
  currentYear: new Date().getFullYear(),
  currentMonth: new Date().getMonth() + 1, // 1-12
  monthLoad: {},        // 'YYYY-AA' → { revision, days: { 'GG.AA.YYYY': {used, free, total} } }
  monthLoadPending: {},
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
  state.hotelSplit = data.hotel_split || [];
  state.balloons = data.balloon_codes || [];
  setBalloonCodes(state.balloons);
  state.balloonLoad = data.balloon_load || {};
  state.capacity = data.capacity || 28;
  state.capacities = data.capacities || {};
  state.dailyMaxBalloons = Number(data.daily_max_balloons) || 0;
  state.balloonsInUse = data.balloons_in_use;
  state.agencyUsage = data.agency_usage || [];
  state.revision = data.workbook_revision || '';
  state.readiness = data.readiness || null;
}

const OPERATION_KEYS = ['pax','room','hotel','pickup','reserved_by','agency','company','balloon','pilot','driver','coming_place','note'];

// Açık operasyon formunda kaydedilmemiş düzenleme veya kaydı süren sıralama varsa
// pencere yenileme/kapama onay ister.
registerUnsavedCheck('planning', () => {
  if (state.pendingReorder) return true;
  if (sheetGridDirty()) return true;
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
  state.view = 'blocks'; excelMountedFor = '';
  renderHeader('Planlama', 'Uçuş günü yönetimi ve rezervasyon blokları');
  const deepLink = readDeepLink();
  state.issueFilter = null;

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
            <span class="material-symbols-outlined text-[20px]">airline_seat_recline_normal</span> Balon doluluğu
          </div>
          <div class="flex flex-col" id="sidebar-balloon-load-list">
            <!-- Dinamik olarak dolacak -->
          </div>
        </div>
      </div>

      <!-- SAĞ KOLON: Boş Durum veya Rezervasyon Listesi -->
      <div class="w-full">
        <!-- Boş Durum (Gün seçilmediğinde) -->
        <div class="card min-h-[220px] flex flex-col justify-center animate-in" id="empty-planning-state">
          <h3 class="font-headline text-headline-sm text-on-surface mb-1.5">Bir gün seçin</h3>
          <p class="text-on-surface-variant">Takvimde planı olan günler mavi görünür. Planı olmayan bir güne tıklarsanız o gün koltuk düzeniyle boş açılır.</p>
        </div>

        <!-- Rezervasyon Blokları Kartı (Gün seçildiğinde) -->
        <div class="card animate-in w-full" id="blocks-section" style="display:none">
          <div class="card-header">
            <div class="card-title flex items-center">
              <span class="material-symbols-outlined mr-2">group</span> Rezervasyon Blokları
              <span id="reorder-status" style="display: none;"></span>
            </div>
            <div class="flex flex-wrap items-center gap-3">
              <div class="inline-flex rounded-lg border border-line bg-raised p-0.5" role="tablist" aria-label="Görünüm">
                <button role="tab" id="pv-blocks" aria-selected="true" class="pv-tab is-on" onclick="window.__planView('blocks')">
                  <span class="material-symbols-outlined text-[18px]">view_agenda</span> Rezervasyonlar
                </button>
                <button role="tab" id="pv-excel" aria-selected="false" class="pv-tab" onclick="window.__planView('excel')" title="Günün Excel sayfasını uygulama içinde göster ve düzenle">
                  <span class="material-symbols-outlined text-[18px]">table_view</span> Excel
                </button>
              </div>
              <span class="text-sm text-on-surface-variant" id="blocks-count"></span>
              <button class="btn-primary flex items-center gap-2" onclick="window.__newReservation()">
                <span class="material-symbols-outlined text-sm">add</span> Yeni Rezervasyon
              </button>
            </div>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4" id="blocks-tools">
            <div class="md:col-span-2">
              <input class="form-input" id="block-search" type="search" autocomplete="off" aria-describedby="block-search-hint"
                     placeholder="Ara: pax 5 · isim ahmet · otel argos · şoför 2" oninput="window.__renderPlanningDebounced()" />
              <div class="form-help" id="block-search-hint">Alan adıyla arayın: pax, isim, otel, acente, balon, pilot, şoför, pasaport, uyruk, oda, saat, not. Örn. <span class="font-mono">pax 3-5</span>, <span class="font-mono">pax &gt;4</span>.</div>
            </div>
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
          <div id="issue-filter-chip"></div>
          <div id="balloon-chips" class="flex flex-wrap items-center gap-2 mb-3" role="group" aria-label="Balona göre süz"></div>
          <div id="hotel-split" class="mb-3"></div>
          <div class="flex flex-col gap-3" id="blocks-list"></div>
          <div id="excel-view" style="display:none"></div>
        </div>
      </div>
    </div>
  `;

  loadSheets().then(() => applyDeepLink(deepLink));
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

function monthKey(year, month) {
  return `${year}-${String(month).padStart(2, '0')}`;
}

// Ayın gün doluluğu: sunucu workbook_revision ile önbellekler; burada yalnız revizyon
// değiştiyse (yazım sonrası) yeniden istenir. Doluluk bilgi amaçlıdır, hata takvimi bozmaz.
async function ensureMonthLoad(year, month) {
  const key = monthKey(year, month);
  const suffix = `.${String(month).padStart(2, '0')}.${year}`;
  if (calState.monthLoadPending[key] || !state.sheets.some(s => s.endsWith(suffix))) return;
  const have = calState.monthLoad[key];
  if (have && (!state.revision || have.revision === state.revision)) return;
  calState.monthLoadPending[key] = true;
  try {
    const data = await api.get(`/api/planning/month-load?month=${key}`);
    const days = data.days || {};
    const changed = !have || JSON.stringify(have.days) !== JSON.stringify(days);
    calState.monthLoad[key] = { revision: data.workbook_revision || '', days };
    if (changed && monthKey(calState.currentYear, calState.currentMonth) === key) renderCalendar();
  } catch (err) {
    // doluluk gösterilmez; takvim yine çalışır
  } finally {
    delete calState.monthLoadPending[key];
  }
}

function dayLoadHtml(load) {
  if (!load || !load.total) return '';
  const pct = Math.min(100, Math.round((load.used / load.total) * 100));
  const over = load.used > load.total ? ' over' : '';
  return `<span class="seat-bar day-load${over}" aria-hidden="true"><span style="width:${pct}%"></span></span>`
    + `<span class="sr-only">, ${load.used}/${load.total} koltuk dolu</span>`;
}

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
  const loadDays = (calState.monthLoad[monthKey(calState.currentYear, calState.currentMonth)] || {}).days || {};
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
      const load = loadDays[formatted];
      const seats = load && load.total ? ` · ${load.used}/${load.total} koltuk` : '';
      html += `<div class="${cls}" onclick="window.__loadDayDate('${formatted}')" title="Günü Yükle: ${formatted}${seats}">${day}${dayLoadHtml(load)}</div>`;
    } else if (isPast) {
      // Geçmiş ve planı olmayan gün: yanlışlıkla gün oluşturulmasın diye tıklanamaz
      html += `<div class="${cls}" title="Geçmiş tarih — uçuş günü yok">${day}</div>`;
    } else {
      html += `<div class="${cls}" onclick="window.__askCreateDay('${formatted}')" title="Uçuş günü yok: ${formatted}">${day}</div>`;
    }
  }

  daysGridEl.innerHTML = html;
  ensureMonthLoad(calState.currentYear, calState.currentMonth);

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
    refreshExcelView();
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
  renderBalloonChips();
  renderHotelSplit();
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
    <div class="block-item ${b.balloon ? 'has-env' : ''} ${state.selectedBlock === i ? 'selected' : ''}"
         ${b.balloon ? `style="${balloonInk(b.balloon)}"` : ''}
         onclick="window.__selectBlock(${i})">
      ${b.balloon ? envStripe(b.balloon) : '<span class="env-stripe env-none" aria-hidden="true"><i></i><i></i><i></i></span>'}
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
        ${b.balloon ? `<div class="block-balloon" style="${balloonInk(b.balloon)}">${escHtml(b.balloon)}</div>` : ''}
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
  const rawQuery = (document.getElementById('block-search')?.value || '').trim();
  const terms = parseQuery(rawQuery);
  const filter = document.getElementById('block-filter')?.value || '';
  const sort = document.getElementById('block-sort')?.value || 'row';
  let rows = state.blocks.map((block, index) => ({ block, index }));
  if (terms.length) rows = rows.filter(({ block }) => matchesBlock(block, terms));
  if (filter) {
    rows = rows.filter(({ block }) => {
      if (filter.startsWith('balloon_')) {
        return block.balloon === filter.replace('balloon_', '');
      }
      const missing = (block.passengers || []).some(p => !p.name || !p.passport_no || !p.nationality || !p.sex);
      return filter === 'missing' ? missing : !missing;
    });
  }
  rows = applyIssueFilter(rows);
  const hint = document.getElementById('block-search-hint');
  if (hint) {
    if (!hint.dataset.default) hint.dataset.default = hint.innerHTML;
    hint.innerHTML = terms.length
      ? `<span class="text-on-surface font-semibold">${rows.length}</span> rezervasyon · ${escHtml(describeTerms(terms))}`
      : hint.dataset.default;
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

// ─── Balon renk filtresi ve aynı otel önerisi ───
function foldName(v) {
  return String(v || '').toLocaleUpperCase('tr-TR').replace(/[İIı]/g, 'I').replace(/Ş/g, 'S').replace(/Ğ/g, 'G')
    .replace(/Ü/g, 'U').replace(/Ö/g, 'O').replace(/Ç/g, 'C').replace(/\s+/g, ' ').trim();
}

function blockSeats(b) {
  return Number(b.pax) || (b.rows || []).length || (b.passengers || []).length || 0;
}

function renderBalloonChips() {
  const root = document.getElementById('balloon-chips');
  if (!root) return;
  const current = document.getElementById('block-filter')?.value || '';
  const codes = [...new Set([...(state.balloons || []), ...state.blocks.map(b => b.balloon).filter(Boolean)])];
  if (!codes.length) { root.innerHTML = ''; return; }
  const count = (code) => state.blocks.filter(b => b.balloon === code).length;
  const chip = (value, label, n, style = '') => {
    const on = current === value;
    return `<button type="button" class="balloon-chip ${on ? 'is-on' : ''}" ${style} aria-pressed="${on}"
      onclick="window.__filterBalloon('${value}')">${label}<span class="balloon-chip-n">${n}</span></button>`;
  };
  root.innerHTML = chip('', 'Tümü', state.blocks.length)
    + codes.map(code => chip(`balloon_${escHtml(code)}`, `${envStripe(code)}<span>${escHtml(code)}</span>`, count(code), `style="${balloonInk(code)}"`)).join('');
}

window.__filterBalloon = function(value) {
  const sel = document.getElementById('block-filter');
  if (!sel) return;
  if (value && !Array.from(sel.options).some(o => o.value === value)) return;
  sel.value = sel.value === value ? '' : value;
  renderBlocks();
};

function renderHotelSplit() {
  const root = document.getElementById('hotel-split');
  if (!root) return;
  // Sunucu hesaplar: aynı otel + aynı pickup saati 2+ balonda (farklı saatler ayrı kalkış sayılır)
  const split = state.hotelSplit || [];
  if (!split.length) { root.innerHTML = ''; return; }
  root.innerHTML = `
    <div class="rounded-lg border border-line bg-well px-4 py-3">
      <div class="flex items-center gap-2 text-sm font-semibold text-on-surface mb-1.5">
        <span class="material-symbols-outlined text-[18px] text-info">airport_shuttle</span>
        Aynı otel ve saatte farklı balonlara dağılmış yolcular
      </div>
      <p class="text-xs text-on-surface-variant mb-2">Aynı saatte aynı otelden alınan yolcuları tek balonda toplamak lojistiği kolaylaştırır. Farklı saatte alınanlar ayrı kalkış sayılır, burada görünmez. Tıklayınca o rezervasyonlar listelenir.</p>
      <div class="flex flex-wrap gap-2">
        ${split.slice(0, 8).map(e => {
          const q = `otel ${e.hotel}${e.pickup ? ` saat ${e.pickup}` : ''}`;
          return `
          <button type="button" class="btn-secondary btn-sm" onclick="window.__searchHotel(${JSON.stringify(q).replace(/"/g, '&quot;')})">
            <span class="font-semibold">${escHtml(e.hotel)}</span>
            <span class="text-on-surface-variant">${e.pickup ? `· ${escHtml(e.pickup)} ` : '· saat yok '}· ${e.seats} kişi ·</span>
            ${(e.balloons || []).map(code => `<span class="balloon-code" style="${balloonInk(code)}">${escHtml(code)}</span>`).join(' ')}
          </button>`;
        }).join('')}
      </div>
    </div>`;
}

window.__searchHotel = function(query) {
  const inp = document.getElementById('block-search');
  if (!inp) return;
  inp.value = query;
  renderBlocks();
  inp.focus();
};

function renderBalloonLoad() {
  const el = document.getElementById('sidebar-balloon-load-list');
  if (!el) return;
  const codes = state.balloons || [];
  const limit = state.dailyMaxBalloons || 0;
  const inUse = state.balloonsInUse ?? codes.filter(code => ((state.balloonLoad || {})[code] || 0) > 0).length;
  const limitLine = limit ? `
      <div class="flex items-center justify-between text-sm pb-2.5 mb-0.5 border-b border-line">
        <span class="text-on-surface-variant">Günlük balon sınırı</span>
        <span class="tnum font-semibold ${inUse > limit ? 'text-danger' : 'text-on-surface'}">${escHtml(balloonLimitText(inUse, limit))}</span>
      </div>` : '';
  el.innerHTML = limitLine + (codes.map(code => {
    const cap = state.capacities?.[code] ?? state.capacity ?? 28;
    const used = (state.balloonLoad || {})[code] || 0;
    const over = used > cap;
    const pct = Math.min(100, Math.round((used / Math.max(1, cap)) * 100));
    return `
      <div class="flex items-center gap-3 py-2.5 border-b border-line last:border-0 text-sm" style="${balloonInk(code)}">
        ${envStripe(code)}
        <span class="font-bold w-11 shrink-0" style="color: rgb(var(--env))">${escHtml(code)}</span>
        <div class="seat-bar flex-1" style="${balloonInk(code)}"><span style="width:${pct}%"></span></div>
        <span class="tnum font-semibold w-14 text-right ${over ? 'text-danger' : 'text-on-surface'}">${used}/${cap}</span>
      </div>
    `;
  }).join('') || '<div class="text-sm text-on-surface-variant p-2">Kayıtlı balon yok. Listeler\'den balon kodu ekleyin.</div>');
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
      <div class="passenger-row ${p.name || p.passport_no ? '' : 'empty'}" data-row="${Number(p.row)}">
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
          <button class="btn-primary flex items-center gap-2" onclick="window.__saveOperation()">
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
    const res = await postCreateBlock(body);
    if (!res) {   // kota aşımı onaylanmadı
      toast.info('Rezervasyon eklenmedi', 'Acente kotası aşılmadı.');
      return;
    }
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

// create-block isteği; 409 daily_capacity_exceeded gelirse operatöre sorar ve
// allow_daily_capacity_override ile yeniden dener. body yerinde güncellenir (sonraki kapasite
// onayı da günlük kapasite onayını taşısın). Vazgeçilirse null döner.
async function postCreateBlock(body) {
  try {
    return await api.post('/api/planning/create-block', body);
  } catch (err) {
    if (!isDailyCapacityExceeded(err) || body.allow_daily_capacity_override) throw err;
    const ok = await modal.confirm(dailyCapacityConfirmOptions(err.detail, escHtml));
    if (!ok) return null;
    body.allow_daily_capacity_override = true;
    return api.post('/api/planning/create-block', body);
  }
}

function showCapacityChoice(body, detail) {
  window.__pendingOverflowBody = body;
  const intro = detail.message
    || 'Grup hiçbir balona kapasite içinde sığmıyor. Hedef balonu seçip kapasite aşımını açıkça onaylayın veya iptal edin.';
  const limit = Number(detail.daily_max_balloons) || 0;
  modal.open('Balon Kapasitesi Doldu', `
    <p class="text-on-surface-variant mb-4">${escHtml(intro)}</p>
    ${limit ? `<p class="text-sm text-on-surface-variant -mt-2 mb-4">Günlük en fazla ${limit} balon uçabilir.</p>` : ''}
    <div class="space-y-2">${(detail.balloon_codes || []).map(code => `
      <label class="flex items-center justify-between rounded-lg border border-line p-3 cursor-pointer">
        <span><input type="radio" name="overflow-balloon" value="${escHtml(code)}" class="mr-3" />${escHtml(code)}</span>
        <strong class="tnum">${Number(detail.balloon_load?.[code] || 0)}/${capacityFor(detail, code)}</strong>
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
    const res = await postCreateBlock(body);
    if (!res) { toast.info('Rezervasyon eklenmedi', 'Acente kotası aşılmadı.'); return; }
    modal.close();
    toast.warning('Kapasite aşımı onaylandı', `${res.balloon} balonuna atandı`);
    window.__loadDay();
  } catch (err) { toast.error('Oluşturma hatası', err.message); }
};

// ─── Uyarılardan derin bağlantı ───
// #/planning?sheet=22.10.2026&row=83         → günü aç, satırın rezervasyonunu seç, vurgula
// #/planning?sheet=22.10.2026&issue=missing_pickup → yalnız o uyarının rezervasyonları
function readDeepLink() {
  const p = routeParams();
  const sheet = (p.get('sheet') || '').trim();
  const row = parseInt(p.get('row') || '', 10);
  const issue = (p.get('issue') || '').trim();
  if (!sheet && !issue && !Number.isFinite(row)) return null;
  return { sheet, row: Number.isFinite(row) ? row : null, issue, token: loadToken };
}

async function applyDeepLink(link) {
  if (!link || link.token !== loadToken) return; // sayfadan çıkıldı ya da başka gün açıldı
  const sheet = link.sheet || state.currentSheet;
  if (!sheet) return;
  if (!state.sheets.includes(sheet)) {
    toast.warning('Gün bulunamadı', `${sheet} planlama dosyasında yok.`);
    return;
  }
  const parsed = parseSheetDate(sheet);
  if (parsed) {
    calState.currentYear = parsed.year;
    calState.currentMonth = parsed.month;
  }
  if (link.issue) state.issueFilter = { sheet, code: link.issue };
  await window.__loadDayDate(sheet);
  if (state.currentSheet !== sheet || !document.getElementById('blocks-list')) return;
  if (link.row != null && !link.issue) focusRow(link.row);
  else if (link.issue) {
    // Dar pencerede liste takvimin altında kalır; süzülmüş listeyi göster
    const reduce = !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    document.getElementById('blocks-section')?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }
}

function focusRow(row) {
  const idx = findBlockIndexForRow(state.blocks, row);
  if (idx < 0) {
    toast.warning('Satır bulunamadı', `Satır ${row} bu günde bir rezervasyona ait değil; liste değişmiş olabilir.`);
    return;
  }
  state.selectedBlock = idx;
  renderBlocks();
  const block = state.blocks[idx];
  const shell = document.getElementById(`block-${idx}`);
  if (!shell) return;
  // Yolcu satırı (ya da kimliği eksik lider) ise o yolcu da vurgulanır
  const passenger = (block.passengers || []).find(p => Number(p.row) === Number(row));
  const incomplete = passenger && (!passenger.name || !passenger.passport_no || !passenger.nationality || !passenger.sex);
  const person = passenger && (Number(row) !== Number(block.lead_row) || incomplete)
    ? shell.querySelector(`.passenger-row[data-row="${Number(row)}"]`)
    : null;
  const reduce = !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  (person || shell).scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: person ? 'center' : 'start' });
  flashFocus(shell.querySelector('.block-item'));
  flashFocus(person);
}

function flashFocus(el) {
  if (!el) return;
  el.classList.remove('deep-link-flash');
  void el.offsetWidth; // animasyonu yeniden başlat
  el.classList.add('deep-link-flash');
  setTimeout(() => el.classList.remove('deep-link-flash'), 2100);
}

// filteredBlocks() içinden çağrılır: uyarı filtresi + üstteki kaldırılabilir çip.
// Seçili blok, uyarısı giderilse de listede kalır (kaydedince kaybolmasın).
function applyIssueFilter(rows) {
  const chip = document.getElementById('issue-filter-chip');
  if (state.issueFilter && state.issueFilter.sheet !== state.currentSheet) {
    state.issueFilter = null; // başka güne geçildi
    clearDeepLinkHash();
  }
  const f = state.issueFilter;
  if (!f) {
    if (chip) chip.innerHTML = '';
    return rows;
  }
  const leads = issueLeadRows(state.readiness?.issues, state.blocks, f.code);
  const out = rows.filter(({ block, index }) => leads.has(Number(block.lead_row)) || index === state.selectedBlock);
  if (chip) {
    const label = issueLabel(f.code) || f.code;
    const countText = leads.size ? `${leads.size} rezervasyon` : 'uyarı kalmadı';
    chip.innerHTML = `
      <div class="issue-filter-chip" role="status">
        <span class="material-symbols-outlined text-[16px]" aria-hidden="true">filter_alt</span>
        <span>Filtre: <strong class="font-semibold">${escHtml(label)}</strong> · ${escHtml(countText)}</span>
        <button type="button" class="issue-filter-clear" onclick="window.__clearIssueFilter()" aria-label="Filtreyi kaldır" title="Filtreyi kaldır">
          <span class="material-symbols-outlined text-[16px]">close</span>
        </button>
      </div>`;
  }
  return out;
}

function clearDeepLinkHash() {
  try { history.replaceState(null, '', '#/planning'); } catch (e) { /* yoksay */ }
}

window.__clearIssueFilter = function() {
  state.issueFilter = null;
  clearDeepLinkHash();
  renderBlocks();
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


// ─── Uygulama içi Excel görünümü (frontend/sheet_grid.js) ───
let excelMountedFor = '';

function refreshExcelView(force = false) {
  if (state.view !== 'excel' || !state.currentSheet) return;
  if (!force && excelMountedFor === state.currentSheet) return;
  excelMountedFor = state.currentSheet;
  mountSheetGrid(document.getElementById('excel-view'), {
    sheet: state.currentSheet,
    // Kaydedince rezervasyon listesi ve doluluk da tazelensin (Excel görünümü zaten yenilendi)
    onSaved: () => window.__loadDayDate(state.currentSheet),
  });
}

window.__planView = async function(mode) {
  if (state.view === 'excel' && mode !== 'excel' && sheetGridDirty()) {
    const ok = await modal.confirm({
      title: 'Kaydedilmemiş hücreler var',
      bodyHtml: '<p class="text-on-surface-variant">Excel görünümünde kaydetmediğiniz değişiklikler kaybolacak.</p>',
      confirmLabel: 'Kaydetmeden çık', tone: 'danger',
    });
    if (!ok) return;
  }
  state.view = mode === 'excel' ? 'excel' : 'blocks';
  const excel = state.view === 'excel';
  for (const [id, on] of [['pv-blocks', !excel], ['pv-excel', excel]]) {
    const b = document.getElementById(id);
    if (b) { b.classList.toggle('is-on', on); b.setAttribute('aria-selected', String(on)); }
  }
  for (const id of ['blocks-tools', 'blocks-list', 'balloon-chips', 'hotel-split']) {
    const el = document.getElementById(id);
    if (el) el.style.display = excel ? 'none' : '';
  }
  const view = document.getElementById('excel-view');
  if (view) view.style.display = excel ? '' : 'none';
  if (excel) refreshExcelView(true);
};
