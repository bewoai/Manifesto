/* ═══════════════════════════════════════════════════════════════════
   Pasaport Tarama — Drag & drop, MRZ okuma, kontrol kartları
   Brief §8: sol görsel, sağ 4 alan, yeşil/sarı status
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, renderHeader, modal, helpIcon, appStatus, registerUnsavedCheck } from '/app.js';
import { attachCombobox } from '/combobox.js';
import { capacityFor, isQuotaExceeded, quotaConfirmOptions } from '/capacity_rules.js';
import {
  annotationMatches, fold, inferRule, isStaffAnnotation, normalizeAgencyKey,
  KIND_LABELS, LIST_KINDS, MARK_RULE_OPTIONS,
} from '/list_marks.js';

let state = {
  files: [],
  records: [],
  processing: false,
  sheets: [],
  currentSheet: '',
  countries: [],   // [{value:'TUR', label:'TUR — Türkiye'}]
  hotels: [],
  agencies: [],
  blocks: [],
  revision: '',
  objectUrls: [],
  markRules: {},        // {acente (fold): kural id} — /api/lists/mark-rules
  markRuleOptions: [],  // [{id, label}]
  hotelChoice: '',      // farklı oteller varsa yazılacak otel (fold anahtarı)
  autoSheet: '',        // grup tarihinden otomatik seçilen son gün sayfası
};

const MANUAL_REVIEW_QUEUE_KEY = 'irtifa_manual_review_queue';
let writing = false;
let overflowSubmitting = false;
let pendingOverflowWritten = [];   // kapasite onayı bekleyen yazımın kart indeksleri
let pendingOverflowRules = [];     // kapasite onayı bekleyen yazımda otomatik kaydedilecek kurallar

// OCR, kaydı Manuel Kontrol kuyruğuna düşürdüyse (requires_manual_review) ve operatör
// henüz orada onaylamadıysa kart pasiftir: aynı kayıt iki yerde onaylanamaz.
function isPendingManual(rec) {
  return !!rec?.requires_manual_review && !rec?.manual_reviewed;
}

// Yüklenmiş dosyalar ve planlamaya yazılmamış kartlar yalnız bellektedir; pencere
// yenilenirse kaybolur. (Manuel Kontrol'de bekleyenler sunucuda durur → sayılmaz.)
registerUnsavedCheck('passport', () =>
  state.files.length > 0
  || state.records.some(rec => !isPendingManual(rec) && (rec.name || rec.passport_no || rec._approved)));

export async function render(container) {
  renderHeader('Pasaport Tarama', 'Fotoğraf yükle, MRZ oku, kontrol et ve planlamaya yaz');
  // Modül seviyesindeki state sayfadan çıkınca da yaşar; önceki DOM gitti → eski URL'ler boşa.
  releaseObjectUrls();
  const previousFiles = state.files.length;
  const previousRecords = state.records.length;

  container.innerHTML = `
    <div id="pp-resume" class="glass-panel rounded-3xl p-5 mb-6 flex flex-wrap items-center gap-4 border-l-4 border-l-info" style="display:none">
      <span class="material-symbols-outlined text-info text-3xl">history</span>
      <div class="flex-1 min-w-[220px]">
        <div class="font-semibold text-on-surface">Önceki tarama duruyor</div>
        <div class="text-sm text-on-surface-variant" id="pp-resume-text"></div>
      </div>
      <div class="flex flex-wrap gap-3">
        <button class="btn-secondary" onclick="window.__passportStartFresh()">Temizle ve yeni başla</button>
        <button class="btn-primary" onclick="window.__passportResume()">Önceki taramayı sürdür</button>
      </div>
    </div>

    <!-- Rezervasyon: pasaport girerken o an açılır -->
    <div class="glass-panel rounded-xl p-6 md:p-8 mb-6 animate-fade-in">
      <div class="flex justify-between items-center mb-6">
        <h2 class="text-headline-sm font-headline text-on-surface flex items-center gap-3">
          <span class="material-symbols-outlined text-primary text-3xl">assignment</span>
          Rezervasyon
        </h2>
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div class="flex flex-col gap-1 md:col-span-2">
          <label class="text-sm font-medium text-on-surface-variant ml-1">Kayıt biçimi${helpIcon('Yeni rezervasyon açabilir veya mevcut rezervasyonun yalnız boş yolcu satırlarına pasaport ekleyebilirsiniz.')}</label>
          <select class="form-select" id="pp-mode" onchange="window.__passportModeChanged()">
            <option value="new">Yeni rezervasyon oluştur</option>
            <option value="existing">Mevcut rezervasyona pasaport ekle</option>
          </select>
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-on-surface-variant ml-1">Uçuş Günü${helpIcon('Pasaportların yazılacağı günlük planlama sayfasıdır.')}</label>
          <select class="form-select" id="pp-sheet-select">
            <option value="">Yükleniyor...</option>
          </select>
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-on-surface-variant ml-1">PAX (kişi sayısı)${helpIcon('Yeni rezervasyondaki toplam kişi sayısıdır. Pasaport sayısından büyük olabilir; kalan satırlar boş bırakılır.')}</label>
          <input class="form-input" id="pp-pax" type="number" min="1" max="28" />
          <div class="text-xs text-on-surface-variant/70 mt-1 ml-1">Bu rezervasyondaki kişi sayısı — pasaport sayısına göre otomatik gelir, değiştirebilirsin.</div>
        </div>
      </div>
      <div class="form-group mb-4" id="existing-block-wrap" style="display:none">
        <label class="form-label">Mevcut Rezervasyon${helpIcon('Yeni kimlikler seçilen rezervasyonun yalnız boş yolcu satırlarına yazılır.')}</label>
        <select class="form-select" id="pp-existing-block"></select>
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-on-surface-variant ml-1">Otel${helpIcon('Misafirlerin pickup yapılacağı oteldir.')}</label>
          <input class="form-input" id="pp-hotel" list="dl-pp-hotel" placeholder="ör. ARGOS" />
          <datalist id="dl-pp-hotel"></datalist>
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-on-surface-variant ml-1">Acente${helpIcon('Rezervasyonu gönderen acente bilgisidir.')}</label>
          <input class="form-input" id="pp-agency" placeholder="ör. BEDEL TURIZM" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-on-surface-variant ml-1">Rezerve Yapan${helpIcon('Rezervasyonu ileten veya sisteme giren kişidir.')}</label>
          <input class="form-input" id="pp-reserved" placeholder="ör. MAHMUT" />
        </div>
      </div>
      
      <div class="mt-6 text-xs text-on-surface-variant bg-primary/5 border border-primary/10 p-4 rounded-2xl flex items-start gap-3">
        <span class="material-symbols-outlined text-primary text-[20px]">info</span>
        <div class="leading-relaxed">Balon PAX\'a göre <strong class="text-primary font-semibold">otomatik atanır</strong>. Kaptan ve pickup saati en son (rota belli olunca) Planlama\'dan girilir.</div>
      </div>
    </div>

    <!-- Drop Zone -->
    <div class="glass-panel rounded-xl border-2 border-dashed border-tertiary/15 p-12 text-center cursor-pointer transition-all duration-300 hover:border-primary/50 hover:bg-primary/5 mb-6 animate-fade-in" id="dropzone"
         ondragover="event.preventDefault(); this.classList.add('border-primary', 'bg-primary/10')"
         ondragleave="this.classList.remove('border-primary', 'bg-primary/10')"
         ondrop="window.__handleDrop(event)"
         onclick="document.getElementById('file-input').click()">
      <div class="bg-surface-light w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4 border border-line">
        <span class="material-symbols-outlined text-4xl text-primary">add_a_photo</span>
      </div>
      <div class="text-lg text-on-surface mb-2"><strong>Pasaport fotoğraflarını sürükle</strong> veya tıkla</div>
      <div class="text-sm text-on-surface-variant">JPG, PNG, WEBP • Birden fazla dosya seçilebilir</div>
      <input type="file" id="file-input" multiple accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" style="display:none"
             onchange="window.__handleFiles(this.files)" />
    </div>

    <!-- File list + action -->
    <div class="glass-panel rounded-xl p-6 md:p-8 mb-6 animate-fade-in" id="file-section" style="display:none">
      <div class="flex flex-wrap justify-between items-center mb-6 gap-4">
        <h2 class="text-headline-sm font-headline text-on-surface flex items-center gap-3">
          <span class="material-symbols-outlined text-primary text-3xl">folder_open</span>
          Yüklenen Dosyalar
        </h2>
        <div class="flex flex-wrap gap-3">
          <button class="btn-secondary flex items-center gap-2" onclick="window.__clearFiles()">
            <span class="material-symbols-outlined text-[20px]">delete_sweep</span> Temizle
          </button>
          <button class="btn-secondary flex items-center gap-2" onclick="window.__createManualCards()">
            <span class="material-symbols-outlined text-[20px]">add_task</span> Manuel Kart Oluştur
          </button>
          <button class="btn-primary flex items-center gap-2" id="btn-process" onclick="window.__processFiles()">
            <span class="material-symbols-outlined text-[20px]">document_scanner</span> MRZ Oku
          </button>
        </div>
      </div>
      <div id="file-list" class="flex flex-col gap-2"></div>
      <div id="progress-area" class="mt-6 p-5 rounded-3xl bg-surface-light border border-line" style="display:none">
        <div class="w-full bg-surface rounded-full h-2 overflow-hidden mb-3">
          <div class="bg-primary h-full transition-all duration-300" id="progress-fill" style="width:0%"></div>
        </div>
        <div class="text-sm text-on-surface-variant font-medium text-center" id="progress-text"></div>
      </div>
    </div>

    <!-- Control Cards -->
    <div id="cards-section" style="display:none" class="animate-fade-in">
      <div class="flex flex-wrap justify-between items-center mb-6 gap-4 px-2">
        <h2 class="text-headline-sm font-headline text-on-surface flex items-center gap-3">
          <span class="material-symbols-outlined text-primary text-3xl">fact_check</span>
          Kontrol Kartları
        </h2>
        <div class="flex flex-wrap items-center gap-4">
          <div class="flex items-center gap-2 bg-surface-light px-4 py-2 rounded-full border border-line">
            <span class="material-symbols-outlined text-[20px] text-on-surface-variant">analytics</span>
            <span class="text-sm font-medium text-on-surface-variant" id="cards-summary"></span>
          </div>
          <button class="btn-primary flex items-center gap-2" id="btn-write" onclick="window.__writePlanning()">
            <span class="material-symbols-outlined text-[20px]">save</span> Rezervasyon Oluştur & Yaz
          </button>
        </div>
      </div>
      <div id="list-hotel-bar"></div>
      <div class="flex flex-col gap-4" id="cards-list"></div>
    </div>
  `;

  if (!appStatus.licensed && appStatus.skipped) {
    const processButton = document.getElementById('btn-process');
    if (processButton) {
      processButton.innerHTML = '<span class="material-symbols-outlined text-[20px]">edit_document</span> Manuel Kartları Oluştur';
    }
  }
  if (previousFiles || previousRecords) {
    // Bilinçli seçim: önceki tarama sessizce geri gelmez, sessizce de silinmez.
    const parts = [];
    if (previousFiles) parts.push(`${previousFiles} dosya`);
    if (previousRecords) parts.push(`${previousRecords} kontrol kartı`);
    document.getElementById('pp-resume-text').textContent =
      `${parts.join(' ve ')} bu sayfadan ayrılmadan önce yazılmadan kaldı.`;
    document.getElementById('pp-resume').style.display = '';
  } else {
    consumeManualReviewQueue();
  }
  loadContext();
  setupPaste();
}

window.__passportResume = function() {
  const banner = document.getElementById('pp-resume');
  if (banner) banner.style.display = 'none';
  renderFileList();
  if (state.records.length) renderCards();
  consumeManualReviewQueue();
};

window.__passportStartFresh = function() {
  const banner = document.getElementById('pp-resume');
  if (banner) banner.style.display = 'none';
  const kept = resetScan({ keepManualReviewed: true });
  renderFileList();
  if (state.records.length) renderCards();
  else hideCards();
  consumeManualReviewQueue();
  if (kept) {
    toast.info('Manuel kontrolden gelenler korundu', `${kept} onaylı yolcu yazılmayı bekliyor.`);
  }
};

function consumeManualReviewQueue() {
  const queueKey = MANUAL_REVIEW_QUEUE_KEY;
  try {
    const queued = JSON.parse(localStorage.getItem(queueKey) || '[]');
    if (!Array.isArray(queued) || !queued.length) return;
    if (state.records.length) syncCardsToState();
    let added = 0;
    let replaced = 0;
    for (const item of queued) {
      const idx = item.extraction_id
        ? state.records.findIndex(rec => rec.extraction_id === item.extraction_id)
        : -1;
      if (idx === -1) {
        state.records.push({ ...item, _approved: true });
        added++;
      } else if (isPendingManual(state.records[idx])) {
        // Pasif "Manuel Kontrol bekliyor" kartı → onaylı haliyle yer değiştirir (görsel korunur).
        const prev = state.records[idx];
        state.records[idx] = {
          ...item,
          _approved: true,
          _source_file_index: prev._source_file_index,
          _source_file_name: prev._source_file_name,
        };
        replaced++;
      }
    }
    localStorage.removeItem(queueKey);
    if (added || replaced) {
      renderCards();
      toast.info(
        'Manuel kontrol kayıtları hazır',
        `${added + replaced} onaylı yolcu rezervasyona yazılmak üzere hazır.`,
      );
    }
  } catch {
    localStorage.removeItem(queueKey);
  }
}

// ─── Clipboard paste (WhatsApp Desktop: kopyala → Ctrl+V) ───
let _pasteHandler = null;
function setupPaste() {
  if (_pasteHandler) document.removeEventListener('paste', _pasteHandler);
  _pasteHandler = (e) => {
    // Sadece pasaport sayfası DOM'dayken çalış
    if (!document.getElementById('dropzone')) return;
    const items = e.clipboardData?.items;
    if (!items) return;
    const imgs = [];
    for (const it of items) {
      if (it.kind === 'file' && it.type.startsWith('image/')) {
        const f = it.getAsFile();
        if (!f) continue;
        // Uzantısız/isimsiz blob'lara MIME'den doğru uzantı ver (backend media_type için)
        const ext = { 'image/png':'png','image/jpeg':'jpg','image/webp':'webp','image/gif':'gif' }[f.type] || 'jpg';
        const hasExt = /\.(png|jpe?g|webp|gif)$/i.test(f.name || '');
        const named = hasExt ? f : new File([f], `pasted-${Date.now()}.${ext}`, { type: f.type });
        imgs.push(named);
      }
    }
    if (imgs.length) {
      e.preventDefault();
      addFiles(imgs);
      toast.success('Yapıştırıldı', `${imgs.length} görsel eklendi`);
    }
  };
  document.addEventListener('paste', _pasteHandler);
}

async function loadContext() {
  try {
    const data = await api.get('/api/planning/sheets');
    state.sheets = data.sheets || [];
    const sel = document.getElementById('pp-sheet-select');
    if (!sel) return;
    if (!sel) return;
    sel.innerHTML = state.sheets.length
      ? state.sheets.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('')
      : '<option value="">Sayfa yok</option>';
    if (state.sheets.length) sel.value = state.sheets[state.sheets.length - 1];
    sel.addEventListener('change', () => loadBlocks(sel.value));
    if (sel.value) await loadBlocks(sel.value);
  } catch (err) { /* silently fail, user can still upload */ }
  // Uyruk (alpha-3) + otel/acente önerileri
  try {
    const [countriesRes, lists] = await Promise.all([
      api.get('/api/countries'),
      api.get('/api/lists'),
    ]);
    state.countries = (countriesRes.countries || []).map(c => ({ value: c.code, label: `${c.code} — ${c.name}` }));
    state.hotels = lists.options?.hotel || [];
    state.agencies = lists.options?.agency || [];
    state.reservedBy = lists.options?.reserved_by || [];
  } catch (e) { /* öneri olmadan da çalışır */ }
  ensureMarkRules();
  // Otel/Acente/Rezerve Yapan alanlarına combobox bağla
  const hotelEl = document.getElementById('pp-hotel');
  const agencyEl = document.getElementById('pp-agency');
  const resEl = document.getElementById('pp-reserved');
  if (hotelEl) attachCombobox(hotelEl, () => state.hotels);
  if (agencyEl) attachCombobox(agencyEl, () => state.agencies);
  if (resEl) attachCombobox(resEl, () => state.reservedBy);
}

async function loadBlocks(sheet) {
  try {
    const data = await api.get(`/api/planning/load?sheet=${encodeURIComponent(sheet)}`);
    state.blocks = data.blocks || [];
    state.revision = data.workbook_revision || '';
    const select = document.getElementById('pp-existing-block');
    if (select) {
      if (!select) return;
      select.innerHTML = state.blocks.map(block => {
        const empty = (block.passengers || []).filter(p => !p.name && !p.passport_no).length;
        return `<option value="${block.lead_row}" ${empty ? '' : 'disabled'}>${esc(block.agency || block.hotel || block.lead_name || `Satır ${block.lead_row}`)} — PAX ${block.pax || block.rows?.length || 0} — ${empty} boş</option>`;
      }).join('');
    }
  } catch (err) {
    toast.error('Rezervasyonlar yüklenemedi', err.message);
  }
}

window.__passportModeChanged = function() {
  const existing = document.getElementById('pp-mode')?.value === 'existing';
  document.getElementById('existing-block-wrap').style.display = existing ? '' : 'none';
  resetWriteButtonLabel(existing);
  for (const id of ['pp-pax', 'pp-hotel', 'pp-agency', 'pp-reserved']) {
    const el = document.getElementById(id);
    if (el) el.disabled = existing;
  }
};

function resetWriteButtonLabel(existing = document.getElementById('pp-mode')?.value === 'existing') {
  const writeButton = document.getElementById('btn-write');
  if (!writeButton) return;
  writeButton.innerHTML = existing
    ? '<span class="material-symbols-outlined text-[20px]">save</span> Mevcut Rezervasyona Yaz'
    : '<span class="material-symbols-outlined text-[20px]">save</span> Rezervasyon Oluştur & Yaz';
}

// ─── File Handling ───
window.__handleDrop = function(e) {
  e.preventDefault();
  e.currentTarget.classList.remove('border-primary', 'bg-primary/10');
  const files = e.dataTransfer?.files;
  if (files?.length) addFiles(files);
};

window.__handleFiles = function(files) {
  if (files?.length) addFiles(files);
};

function addFiles(fileList) {
  // "Önceki tarama" sorusu yanıtlanmadan yeni dosya eklenirse önceki taramayı sürdür.
  const banner = document.getElementById('pp-resume');
  if (banner && banner.style.display !== 'none') window.__passportResume();
  const allowed = new Set(['image/jpeg', 'image/png', 'image/webp']);
  let unsupported = 0;
  let tooLarge = 0;
  let duplicates = 0;
  for (const f of fileList) {
    if (!allowed.has(f.type)) {
      unsupported++;
      continue;
    }
    if (!f.size || f.size > 10 * 1024 * 1024) {
      tooLarge++;
      continue;
    }
    const duplicate = state.files.some(
      existing => existing.name === f.name
        && existing.size === f.size
        && existing.lastModified === f.lastModified
    );
    if (duplicate) {
      duplicates++;
      continue;
    }
    state.files.push(f);
  }
  renderFileList();
  if (unsupported) toast.warning('Desteklenmeyen dosya', `${unsupported} dosya eklenmedi. JPG, PNG veya WEBP kullanın.`);
  if (tooLarge) toast.warning('Dosya çok büyük', `${tooLarge} dosya eklenmedi. Üst sınır 10 MB.`);
  if (duplicates) toast.info('Tekrar dosya atlandı', `${duplicates} dosya zaten listede.`);
}

/**
 * Taramayı sıfırla. keepManualReviewed: Manuel Kontrol'de onaylanıp buraya gelmiş
 * (dosyaya bağlı olmayan) yolcular korunur — "Temizle" onları sessizce kaybetmesin.
 * Dönen değer: korunan kayıt sayısı.
 */
function resetScan({ keepManualReviewed = false } = {}) {
  if (keepManualReviewed && state.records.length) syncCardsToState();
  releaseObjectUrls();
  const kept = keepManualReviewed
    ? state.records
        .filter(rec => rec.manual_reviewed)
        // Dosya bağı koparılır: aynı adla yeni yüklenen bir dosya bu kayda bağlanmasın.
        .map(rec => ({ ...rec, _source_file_index: null, _source_file_name: null }))
    : [];
  state.files = [];
  state.records = kept;
  return kept.length;
}

function hideCards() {
  const list = document.getElementById('cards-list');
  const section = document.getElementById('cards-section');
  const hotelBar = document.getElementById('list-hotel-bar');
  if (list) list.innerHTML = '';
  if (hotelBar) hotelBar.innerHTML = '';
  if (section) section.style.display = 'none';
}

window.__clearFiles = function() {
  const kept = resetScan({ keepManualReviewed: true });
  renderFileList();
  if (kept) {
    renderCards();
    toast.info('Dosyalar temizlendi', `Manuel kontrolden gelen ${kept} onaylı yolcu korundu.`);
  } else {
    hideCards();
  }
};

function renderFileList() {
  const section = document.getElementById('file-section');
  const list = document.getElementById('file-list');
  if (!section || !list) return;
  section.style.display = state.files.length ? '' : 'none';
  list.innerHTML = state.files.map((f, i) => `
    <div class="flex items-center gap-4 p-3 rounded-2xl bg-surface-light/30 hover:bg-surface-light transition-colors border border-line group">
      <div class="bg-surface w-10 h-10 rounded-xl flex items-center justify-center border border-line">
        <span class="material-symbols-outlined text-primary">image</span>
      </div>
      <span class="truncate flex-1 text-on-surface font-medium">${esc(f.name)}</span>
      <span class="text-sm text-on-surface-variant/70 whitespace-nowrap bg-surface px-3 py-1 rounded-lg border border-line">${(f.size / 1024).toFixed(0)} KB</span>
      <button class="text-on-surface-variant group-hover:text-danger hover:bg-danger/10 w-10 h-10 rounded-xl transition-colors flex items-center justify-center" onclick="window.__removeFile(${i})" title="Sil">
        <span class="material-symbols-outlined text-[20px]">close</span>
      </button>
    </div>
  `).join('');
}

window.__removeFile = function(i) {
  if (state.records.length) syncCardsToState();
  const fileToRemove = state.files[i];
  state.files.splice(i, 1);
  if (state.records.length && fileToRemove) {
    // Aynı dosyadan üretilmiş tüm kayıtları (yolcuları) sil
    state.records = state.records
      .filter(r => Number.isInteger(r._source_file_index)
        ? r._source_file_index !== i
        : r._source_file_name !== fileToRemove.name)
      .map(r => ({
        ...r,
        _source_file_index: Number.isInteger(r._source_file_index) && r._source_file_index > i
          ? r._source_file_index - 1
          : r._source_file_index,
      }));
    if (state.records.length) renderCards();
    else hideCards();
  }
  renderFileList();
};

// Henüz kartı olmayan (okunmamış) dosyalar. Yeni yükleme yalnız bunları işler ve
// kartları mevcut listeye EKLER — önceki kartlar ve Manuel Kontrol'den gelenler ezilmez.
function unprocessedFiles() {
  const processed = new Set(
    state.records.map(rec => rec._source_file_index).filter(Number.isInteger),
  );
  return state.files
    .map((file, index) => ({ file, index }))
    .filter(item => !processed.has(item.index));
}

window.__createManualCards = function() {
  if (!state.files.length) return;
  const pending = unprocessedFiles();
  if (!pending.length) {
    toast.info('Yeni dosya yok', 'Listedeki tüm dosyaların kartı zaten var.');
    return;
  }
  if (state.records.length) syncCardsToState();

  state.records.push(...pending.map(({ file, index }) => ({
    source: file.name,
    nationality: '', sex: '', name: '', passport_no: '',
    green: false, flags: [],
    error: '',
    _source_file_index: index,
    _source_file_name: file.name,
    is_manual: true
  })));

  renderCards();
  toast.success('Manuel Giriş', `${pending.length} adet manuel giriş kartı eklendi.`);
};

// ─── Process ───
window.__processFiles = async function() {
  if (!state.files.length || state.processing) return;
  if (!appStatus.licensed && appStatus.skipped) {
    window.__createManualCards();
    return;
  }
  const pending = unprocessedFiles();
  if (!pending.length) {
    toast.info('Yeni dosya yok', 'Listedeki tüm dosyalar zaten okundu. Bir kartı yeniden okumak için "OCR ile Tekrar Tara"yı kullanın.');
    return;
  }
  if (state.records.length) syncCardsToState();
  state.processing = true;

  const btn = document.getElementById('btn-process');
  const prog = document.getElementById('progress-area');
  const fill = document.getElementById('progress-fill');
  const text = document.getElementById('progress-text');

  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined animate-spin text-[20px]">progress_activity</span> İşleniyor...';
  prog.style.display = '';
  fill.style.width = '0%';
  text.textContent = 'Yükleniyor...';

  try {
    // Simulate progress during upload
    fill.style.width = '20%';
    text.textContent = `${pending.length} fotoğraf gönderiliyor...`;

    const data = await api.upload('/api/passport/upload', pending.map(item => item.file));
    // Sunucu _source_file_index'i bu yüklemedeki sıraya göre verir → state.files indeksine çevir.
    let newRecords = (data.records || data || []).map(rec => {
      const name = rec._source_file_name || rec.source;
      const slot = Number.isInteger(rec._source_file_index)
        ? pending[rec._source_file_index]
        : pending.find(item => item.file.name === name);
      return {
        ...rec,
        _source_file_index: slot ? slot.index : null,
        _source_file_name: name,
      };
    });

    // Check for license errors first
    const licenseError = newRecords.find(
      record => record.error && record.error.toLocaleLowerCase('tr-TR').includes('lisans')
    );
    if (licenseError) {
        const isMissing = licenseError.error.toLocaleLowerCase('tr-TR').includes('gerekli');
        const msg = isMissing
            ? "OCR/MRZ okuma için lisans anahtarı gerekli. Fotoğrafları manuel giriş olarak kullanabilirsiniz."
            : "Lisans anahtarı geçersiz. OCR işlemi başlatılamaz.";

        modal.open(
            'Lisans Uyarısı',
            `<div class="py-4 text-on-surface">${msg}</div>`,
            `<button class="btn-ghost px-4 py-2 rounded-xl hover:bg-tertiary/[.05] transition-colors text-on-surface-variant font-medium" onclick="window.__closeModal()">Kapat</button>
             <button class="btn-primary px-4 py-2 rounded-xl transition-colors font-medium" onclick="window.__closeModal(); window.__createManualCards()">Manuel Devam Et</button>`
        );
        return; // Early return, don't create OCR cards
    }
    const serviceError = newRecords.find(record => {
      const message = (record.error || '').toLocaleLowerCase('tr-TR');
      return message.includes('ulaşılamıyor')
        || message.includes('kota')
        || message.includes('geçici bir hata')
        || message.includes('geçersiz yanıt');
    });
    if (serviceError) {
      modal.open(
        'OCR Servisi Kullanılamıyor',
        `<div class="py-4 text-on-surface">${esc(serviceError.error)}</div>
         <div class="text-sm text-on-surface-variant">İnternet gerektirmeyen manuel girişle çalışmaya devam edebilirsiniz.</div>`,
        `<button class="btn-secondary" onclick="window.__closeModal()">Kapat</button>
         <button class="btn-primary" onclick="window.__closeModal(); window.__createManualCards()">Manuel Devam Et</button>`
      );
      return;
    }

    state.records.push(...newRecords);
    await ensureMarkRules();   // liste panelinde acentenin kayıtlı kuralı otomatik seçilsin

    fill.style.width = '100%';
    text.textContent = `${newRecords.length} pasaport işlendi`;

    renderCards();
    const manualCount = newRecords.filter(isPendingManual).length;
    const greenCount = newRecords.filter(r => r.green).length;
    toast.success('İşlem tamamlandı',
      `${greenCount} yeşil, ${newRecords.length - greenCount - manualCount} sarı`
        + (manualCount ? `, ${manualCount} manuel kontrolde` : ''));
  } catch (err) {
    // Check if it's a license error
    const errMsg = (err.message || '').toLowerCase();
    if (errMsg.includes('lisans') || err.status === 401 || err.status === 403) {
        const isMissing = errMsg.includes('gerekli') || errMsg.includes('bulunamadı');
        const msg = isMissing
            ? "OCR/MRZ okuma için lisans anahtarı gerekli. Fotoğrafları manuel giriş olarak kullanabilirsiniz."
            : "Lisans anahtarı geçersiz. OCR işlemi başlatılamaz.";

        modal.open(
            'Lisans Uyarısı',
            `<div class="py-4 text-on-surface">${msg}</div>`,
            `<button class="btn-ghost px-4 py-2 rounded-xl hover:bg-tertiary/[.05] transition-colors text-on-surface-variant font-medium" onclick="window.__closeModal()">Kapat</button>
             <button class="btn-primary px-4 py-2 rounded-xl transition-colors font-medium" onclick="window.__closeModal(); window.__createManualCards()">Manuel Devam Et</button>`
        );
        return;
    }

    toast.error('İşlem hatası', err.message);
    // API yoksa yalnız bu yüklemedeki dosyalar için boş kart ekle (öncekiler korunur)
    state.records.push(...pending.map(({ file, index }) => ({
      source: file.name,
      nationality: '', sex: '', name: '', passport_no: '',
      green: false, flags: ['unreadable'],
      error: 'API bağlantısı kurulamadı — elle doldurun',
      _source_file_index: index,
      _source_file_name: file.name,
    })));
    renderCards();
  } finally {
    if (btn.isConnected) {
      btn.disabled = false;
      btn.innerHTML = '<span class="material-symbols-outlined text-[20px]">document_scanner</span> MRZ Oku';
    }
    state.processing = false;
    setTimeout(() => { if (prog.isConnected) prog.style.display = 'none'; }, 2000);
  }
};

// ─── Control Cards ───
function renderCards() {
  const section = document.getElementById('cards-section');
  const list = document.getElementById('cards-list');
  const summary = document.getElementById('cards-summary');
  if (!section || !list || !summary) return; // sayfadan çıkılmış
  section.style.display = '';

  const pendingManual = state.records.filter(isPendingManual).length;
  const greens = state.records.filter(r => r.green && !isPendingManual(r)).length;
  const manuals = state.records.filter(r => r.is_manual).length;
  const total = state.records.length;
  const warnings = total - greens - manuals - pendingManual;
  const sep = '<span class="opacity-50">/</span>';
  summary.innerHTML = [
    manuals ? `<span class="text-info font-bold">${manuals} manuel giriş</span>` : '',
    `<span class="text-success font-bold">${greens} yeşil</span>`,
    `<span class="text-warning font-bold">${warnings} sarı</span>`,
    pendingManual ? `<span class="text-on-surface-variant font-bold">${pendingManual} manuel kontrolde</span>` : '',
  ].filter(Boolean).join(` ${sep} `) + ` <span class="opacity-50">—</span> toplam ${total}`;

  // Dosya grupları: liste görselleri (≥2 satır veya liste/mesaj türü) panel + kompakt satır,
  // tek pasaport/kimlik görselleri eski kart düzeni. Kart id'leri global indeksle kalır
  // (pc-*-${i}) → readCard / syncCardsToState değişmeden çalışır.
  segments = buildSegments();
  for (const seg of segments) if (seg.isList) ensurePanel(seg);
  enforceHotelChoice();

  releaseObjectUrls();
  list.innerHTML = segments.map((seg, s) => seg.isList
    ? `<section class="flex flex-col gap-2" id="lseg-${s}">
         ${renderListPanel(seg, s)}
         <div class="flex flex-col gap-1.5" id="lrows-${s}">
           ${seg.indices.map(i => renderListRow(state.records[i], i)).join('')}
         </div>
       </section>`
    : seg.indices.map(i => renderFullCard(state.records[i], i)).join('')
  ).join('');

  // Her karttaki Uyruk alanına alpha-3 otomatik tamamlama bağla
  for (let i = 0; i < state.records.length; i++) {
    const el = document.getElementById(`pc-nat-${i}`);
    if (el) attachCombobox(el, () => state.countries);
  }
  segments.forEach((seg, s) => {
    if (!seg.isList) return;
    attachCombobox(document.getElementById(`lp-nat-${s}`), () => state.countries);
    attachCombobox(document.getElementById(`lp-agency-${s}`), () => state.agencies);
    applyRowFilter(s);
  });

  // Onay kutusu değişince: state, panel sayacı, filtre ve PAX anında güncellenir.
  list.onchange = (e) => {
    const m = /^pc-approve-(\d+)$/.exec(e.target?.id || '');
    if (!m) return;
    const i = Number(m[1]);
    if (state.records[i]) state.records[i]._approved = e.target.checked;
    const s = segments.findIndex(seg => seg.indices.includes(i));
    if (s !== -1 && segments[s].isList) {
      updatePanelCounter(s);
      applyRowFilter(s);
    }
    updateAutoPax();
  };

  renderHotelBar();
  autofillReservation();
  updateAutoPax();
}

// PAX'ı otomatik öner (kullanıcı değiştirmediyse). Liste varsa seçili satır sayısı,
// yoksa veri içeren kart sayısı; Manuel Kontrol'de bekleyenler sayılmaz.
function updateAutoPax() {
  const paxEl = document.getElementById('pp-pax');
  if (!paxEl) return;
  const writable = state.records
    .map((rec, i) => ({ rec, i }))
    .filter(({ rec }) => !isPendingManual(rec));
  const count = segments.some(seg => seg.isList)
    ? writable.filter(({ rec }) => isApproved(rec)).length
    : (writable.filter(({ rec }) => rec.name || rec.passport_no).length || writable.length);
  if (count && (!paxEl.value || paxEl.dataset.auto !== 'off')) {
    paxEl.value = count;
    paxEl.dataset.auto = 'on';
    paxEl.onchange = () => { paxEl.dataset.auto = 'off'; };
  }
}

// Kartın onay kutusu durumu: kullanıcı/kural değeri, yoksa kart varsayılanı (yeşil = işaretli).
function isApproved(rec) {
  if (isPendingManual(rec)) return false;
  return rec._approved !== undefined ? !!rec._approved : !!rec.green;
}

function sourceChipsHtml(rec, { withKind = true } = {}) {
  const chips = [];
  const kind = rec.source_kind_label || KIND_LABELS[rec.source_kind] || '';
  if (withKind && kind) chips.push(`<span class="src-chip" title="Kaynak türü">${esc(kind)}</span>`);
  const doc = docTypeLabel(rec.document_type);
  if (doc) chips.push(`<span class="src-chip" title="Belge türü">${doc}</span>`);
  if (rec.annotation) {
    chips.push(`<span class="mark-chip${isStaffRow(rec) ? ' mark-chip-staff' : ''}" title="Listedeki ham işaret">${esc(rec.annotation)}</span>`);
  }
  return chips.join('');
}

function docTypeLabel(type) {
  const t = String(type || '').toUpperCase();
  if (t === 'P') return 'Pasaport';
  if (t === 'I') return 'Kimlik';
  return '';
}

function renderFullCard(rec, i) {
  const pendingManual = isPendingManual(rec);
  const isGreen = rec.green && !pendingManual;
  const flags = (rec.flags || []).join(', ');
  const dis = pendingManual ? 'disabled' : '';
  const status = pendingManual
    ? { edge: 'bg-on-surface-variant/40', border: '', pill: 'bg-tertiary/[.06] text-on-surface-variant border-tertiary/15', icon: 'pending_actions', label: 'MANUEL KONTROL BEKLİYOR' }
    : rec.is_manual
      ? { edge: 'bg-info', border: 'border-info/50', pill: 'bg-info/10 text-info border-info/20', icon: 'edit_document', label: 'MANUEL GİRİŞ' }
      : isGreen
        ? { edge: 'bg-success', border: 'border-success/55', pill: 'bg-success/10 text-success border-success/20', icon: 'check_circle', label: 'YEŞİL — DOĞRULANDI' }
        : { edge: 'bg-warning', border: 'border-warning/60', pill: 'bg-warning/10 text-warning border-warning/20', icon: 'warning', label: 'SARI — KONTROL ET' };

  // Try to create object URL for thumbnail
  let thumbHtml;
  const sourceFile = Number.isInteger(rec._source_file_index)
    ? state.files[rec._source_file_index]
    : state.files.find(f => f.name === rec._source_file_name);
  if (sourceFile) {
    const url = URL.createObjectURL(sourceFile);
    state.objectUrls.push(url);
    thumbHtml = `<img src="${url}" class="w-full md:w-32 h-32 object-cover rounded-2xl border border-line" alt="Passport ${i+1}" />`;
  } else {
    thumbHtml = `<div class="w-full md:w-32 h-32 bg-surface-light rounded-2xl border border-line flex flex-col items-center justify-center text-on-surface-variant"><span class="material-symbols-outlined text-3xl mb-1 opacity-50">image</span><span class="text-[10px] text-center px-2 w-full truncate opacity-70">${esc(rec._source_file_name || rec.source || '')}</span></div>`;
  }
  const chips = sourceChipsHtml(rec);

  return `
    <div class="glass-panel rounded-xl p-5 flex flex-col md:flex-row gap-5 relative animate-fade-in overflow-hidden ${status.border} ${pendingManual ? 'opacity-75' : ''}" id="pcard-${i}">

      <!-- Bu taramayı sil -->
      <button onclick="window.__removeCard(${i})" title="Bu taramayı sil" aria-label="Bu taramayı sil"
              class="absolute top-3 left-4 z-20 w-8 h-8 rounded-full flex items-center justify-center bg-panel border border-line text-on-surface-variant hover:text-danger hover:bg-danger/20 hover:border-danger/30 transition-colors">
        <span class="material-symbols-outlined text-[18px]">close</span>
      </button>

      <div class="pl-1 flex flex-col md:flex-row gap-5 w-full">
        ${thumbHtml}

        <div class="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-on-surface-variant ml-1">Uyruk (kod)</label>
            ${(() => { const h = natHint(rec); return `<input class="form-input font-mono text-sm uppercase ${h.cls}" id="pc-nat-${i}" value="${esc(rec.nationality || '')}" placeholder="TUR, ITA..." title="${esc(h.title)}" ${dis} />`; })()}
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-on-surface-variant ml-1">Cinsiyet</label>
            <select class="form-select text-sm py-[9px]" id="pc-sex-${i}" ${dis}>
              <option value="" ${!rec.sex ? 'selected' : ''}>—</option>
              <option value="M" ${rec.sex === 'M' ? 'selected' : ''}>Erkek</option>
              <option value="F" ${rec.sex === 'F' ? 'selected' : ''}>Kadın</option>
            </select>
          </div>
          <div class="flex flex-col gap-1 col-span-2">
            <label class="text-xs font-medium text-on-surface-variant ml-1">İsim</label>
            <input class="form-input text-sm uppercase" id="pc-name-${i}" value="${esc(rec.name || '')}" placeholder="AD SOYAD" ${dis} />
          </div>
          <div class="flex flex-col gap-1 col-span-2 md:col-span-4">
            <label class="text-xs font-medium text-on-surface-variant ml-1">Pasaport No</label>
            <input class="form-input font-mono text-sm tracking-widest uppercase" id="pc-ppno-${i}" value="${esc(rec.passport_no || '')}" ${dis} />
          </div>
        </div>

        <div class="md:w-56 flex flex-col border-t md:border-t-0 md:border-l border-line pt-5 md:pt-0 md:pl-5 justify-between">
          <div class="w-full">
            <div class="font-medium text-sm flex items-center justify-end gap-1.5 mb-3 px-3 py-1.5 rounded-lg border ${status.pill}">
              <span class="material-symbols-outlined text-[18px]">${status.icon}</span>
              ${status.label}
            </div>
            ${chips ? `<div class="flex flex-wrap justify-end gap-1.5 mb-2">${chips}</div>` : ''}
            ${flags ? `<div class="flex flex-wrap justify-end gap-1.5 mb-2">${flags.split(', ').map(f => `<span class="bg-surface-light border border-line text-on-surface-variant text-[11px] font-medium px-2 py-1 rounded-md tracking-wide">${esc(flagLabel(f))}</span>`).join('')}</div>` : ''}
            ${rec.error ? `<div class="text-[11px] text-danger font-medium mt-1 text-right bg-danger/10 px-2 py-1.5 rounded-md border border-danger/20">${esc(rec.error)}</div>` : ''}
          </div>

          ${pendingManual ? `
          <div class="mt-4 text-xs text-on-surface-variant leading-relaxed text-right">
            Bu kayıt düşük güven nedeniyle Manuel Kontrol kuyruğunda. Orada onaylanınca buraya onaylı olarak gelir.
            <a href="#/manual_review" class="mt-2 inline-flex items-center gap-1 text-info font-semibold hover:underline">
              Manuel Kontrol'e git <span class="material-symbols-outlined text-[16px]">arrow_forward</span>
            </a>
          </div>` : `
          <label class="flex items-center justify-center gap-2 mt-4 text-sm font-medium text-on-surface cursor-pointer hover:bg-primary/10 hover:text-primary transition-colors bg-surface-light/50 px-4 py-2.5 rounded-xl border border-line w-full group select-none">
            <input type="checkbox" class="w-4 h-4 rounded border-line bg-surface text-primary focus:ring-primary focus:ring-offset-surface group-hover:border-primary/50" id="pc-approve-${i}" ${(rec._approved !== undefined ? rec._approved : isGreen) ? 'checked' : ''} />
            Onayla ve Ekle
          </label>`}
          ${(!isGreen && !rec.is_manual && !pendingManual) ? `<button class="btn-secondary w-full mt-2 flex items-center justify-center gap-2" onclick="window.__retryOcr(${i})"><span class="material-symbols-outlined text-sm">refresh</span> OCR ile Tekrar Tara</button>` : ''}
        </div>
      </div>
    </div>
  `;
}

// ─── Liste inceleme (acente listesi / WhatsApp mesajı / çok yolculu görsel) ───
// Panel durumu File nesnesine bağlı: dosya silinince indeksler kaysa da kural/filtre kalır.
const listPanels = new WeakMap();   // File → { rule, agency, agencyFromGroup, onlySelected, bulkNat, bulkSex }
let segments = [];                   // son renderCards'taki dosya grupları; panel handler'ları bu indeksle çalışır
let markRulesPromise = null;

function ensureMarkRules() {
  if (!markRulesPromise) {
    markRulesPromise = api.get('/api/lists/mark-rules')
      .then(res => {
        state.markRules = res.rules || {};
        state.markRuleOptions = res.available || [];
      })
      .catch(() => { markRulesPromise = null; }); // kural olmadan da çalışır; sonra tekrar denenir
  }
  return markRulesPromise;
}

function recordFile(rec) {
  return Number.isInteger(rec?._source_file_index) ? (state.files[rec._source_file_index] || null) : null;
}

function buildSegments() {
  const out = [];
  const byFile = new Map();
  state.records.forEach((rec, i) => {
    const file = recordFile(rec);
    if (!file) { out.push({ file: null, indices: [i], isList: false }); return; }
    let seg = byFile.get(file);
    if (!seg) {
      seg = { file, indices: [], isList: false };
      byFile.set(file, seg);
      out.push(seg);
    }
    seg.indices.push(i);
  });
  for (const seg of out) {
    seg.isList = !!seg.file && (seg.indices.length >= 2
      || seg.indices.some(i => LIST_KINDS.has(state.records[i]?.source_kind)));
  }
  return out;
}

function hasValue(v) {
  return v !== null && v !== undefined && String(v).trim() !== '';
}

function segmentGroup(seg) {
  for (const i of seg.indices) {
    const g = state.records[i]?.group;
    if (g && typeof g === 'object' && Object.values(g).some(hasValue)) return g;
  }
  return {};
}

function segmentKindLabel(seg) {
  const counts = new Map();
  for (const i of seg.indices) {
    const rec = state.records[i];
    const label = rec?.source_kind_label || KIND_LABELS[rec?.source_kind] || '';
    if (label) counts.set(label, (counts.get(label) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || '';
}

function savedRuleFor(agency) {
  const key = normalizeAgencyKey(agency);
  return key ? (state.markRules?.[key] || '') : '';
}

function isStaffRow(rec) {
  return isStaffAnnotation(rec?.annotation);
}

function ruleOptions() {
  return state.markRuleOptions?.length ? state.markRuleOptions : MARK_RULE_OPTIONS;
}

function ruleLabel(rule) {
  return ruleOptions().find(o => o.id === rule)?.label || rule;
}

// Bir satırın kural/varsayılana göre onay durumu. Rehber/kaptan satırları ve başka
// otelde bekleyen satırlar hiçbir kuralla otomatik işaretlenmez (operatör elle işaretleyebilir).
function defaultApproval(rec, rule) {
  if (isPendingManual(rec) || rec._deferredHotel || isStaffRow(rec)) return false;
  if (rule) return annotationMatches(rule, rec.annotation);
  if (typeof rec.selected === 'boolean') return rec.selected;  // listenin kendi evet/hayır kolonu
  return !!rec.green;
}

function ensurePanel(seg) {
  let panel = listPanels.get(seg.file);
  if (panel) return panel;
  const group = segmentGroup(seg);
  const agency = String(group.agency || '').trim();
  // Kural kaynağı: acenteye kayıtlı kural > işaret dağılımından algılanan. Algılama yalnız
  // liste/mesaj görsellerinde ve listenin kendi evet/hayır kolonu (selected) yokken yapılır;
  // çok pasaportlu fotoğrafta işaret dili olmaz.
  const listLike = seg.indices.some(i => LIST_KINDS.has(state.records[i]?.source_kind));
  const hasSelectedColumn = seg.indices.some(i => typeof state.records[i]?.selected === 'boolean');
  const inferred = listLike && !hasSelectedColumn
    ? inferRule(seg.indices.map(i => state.records[i]?.annotation))
    : null;
  const saved = savedRuleFor(agency);
  panel = {
    rule: saved || inferred?.rule || '',
    ruleSource: saved ? 'saved' : (inferred ? 'auto' : ''),   // saved | auto | user
    inferred,
    agency,
    agencyFromGroup: !!agency,
    onlySelected: false,
    bulkNat: String(group.nationality_hint || group.nationality_guess || '').trim().toUpperCase(),
    bulkSex: '',
  };
  listPanels.set(seg.file, panel);
  for (const i of seg.indices) {
    const rec = state.records[i];
    if (rec._approved === undefined) rec._approved = defaultApproval(rec, panel.rule);
  }
  return panel;
}

function applyRule(seg, rule) {
  for (const i of seg.indices) {
    const rec = state.records[i];
    if (isPendingManual(rec)) continue;
    rec._approved = defaultApproval(rec, rule);
  }
}

function panelCounts(seg) {
  let selected = 0;
  for (const i of seg.indices) {
    const rec = state.records[i];
    if (!isPendingManual(rec) && rec._approved) selected++;
  }
  return { selected, total: seg.indices.length };
}

function counterHtml(seg) {
  const { selected, total } = panelCounts(seg);
  // Kural "Hepsi uçuyor" ise PAX karşılaştırması gösterilmez (herkes uçuyor varsayımı).
  const allRule = listPanels.get(seg.file)?.rule === 'all';
  const pax = allRule ? 0 : (parseInt(segmentGroup(seg).pax, 10) || 0);
  const paxNote = !pax ? ''
    : pax === selected
      ? `<div class="text-xs text-success mt-1">Listedeki PAX ${pax} ile eşleşiyor</div>`
      : `<div class="text-xs text-warning bg-warning/10 border border-warning/20 rounded-lg px-2 py-1 mt-1">Listede PAX ${pax} yazıyor, ${selected} satır seçili</div>`;
  return `
    <div class="text-sm text-on-surface-variant">Seçili <strong class="text-on-surface text-lg">${selected}</strong> / Toplam <strong class="text-on-surface">${total}</strong></div>
    ${paxNote}`;
}

function updatePanelCounter(s) {
  const seg = segments[s];
  const el = document.getElementById(`lp-count-${s}`);
  if (seg && el) el.innerHTML = counterHtml(seg);
}

function applyRowFilter(s) {
  const seg = segments[s];
  const panel = seg && listPanels.get(seg.file);
  if (!panel) return;
  let hidden = 0;
  for (const i of seg.indices) {
    const row = document.getElementById(`pcard-${i}`);
    const hide = panel.onlySelected && !state.records[i]?._approved;
    if (hide) hidden++;
    row?.classList.toggle('hidden', hide);
  }
  const note = document.getElementById(`lp-hidden-${s}`);
  if (note) note.textContent = hidden ? `${hidden} satır gizli` : '';
}

function syncPanelsToState() {
  segments.forEach((seg, s) => {
    if (!seg.isList) return;
    const panel = listPanels.get(seg.file);
    if (!panel) return;
    const nat = document.getElementById(`lp-nat-${s}`);
    const sex = document.getElementById(`lp-sex-${s}`);
    const agency = document.getElementById(`lp-agency-${s}`);
    if (nat) panel.bulkNat = nat.value.trim().toUpperCase();
    if (sex) panel.bulkSex = sex.value;
    if (agency) panel.agency = agency.value.trim();
  });
}

function renderListPanel(seg, s) {
  const panel = ensurePanel(seg);
  const group = segmentGroup(seg);
  const kindLabel = segmentKindLabel(seg);
  const staffCount = seg.indices.filter(i => isStaffRow(state.records[i])).length;
  const savedRule = savedRuleFor(panel.agency);

  const url = URL.createObjectURL(seg.file);
  state.objectUrls.push(url);

  const sheetName = groupDateToSheet(group.date);
  const sheetFound = sheetName && findSheet(sheetName);
  const dateText = hasValue(group.date)
    ? `${group.date}${sheetName ? (sheetFound ? ` → ${sheetName}` : ` (${sheetName} sayfası yok)`) : ''}`
    : '';
  const info = [
    ['Acente', group.agency], ['Otel', group.hotel], ['Tarih', dateText],
    ['Kod', group.booking_code], ['PAX', group.pax], ['Uyruk', group.nationality_hint], ['Uyruk tahmini', !group.nationality_hint ? group.nationality_guess : ''], ['Not', group.note],
  ].filter(([, v]) => hasValue(v));

  const options = [`<option value="">Seçim yapılmadı</option>`]
    .concat(ruleOptions().map(o => `<option value="${esc(o.id)}" ${panel.rule === o.id ? 'selected' : ''}>${esc(o.label)}</option>`))
    .join('');
  const inferredText = panel.inferred
    ? `${ruleLabel(panel.inferred.rule)} (${panel.inferred.matched}/${panel.inferred.total})`
    : '';
  let ruleStatus = '';
  if (savedRule && panel.inferred && panel.inferred.rule !== savedRule) {
    ruleStatus = `<span class="text-warning">Kayıtlı: ${esc(ruleLabel(savedRule))} — bu listede ${esc(inferredText)} görünüyor</span>`;
  } else if (savedRule) {
    ruleStatus = savedRule === panel.rule
      ? `<span class="text-success">Bu acente için kayıtlı</span>`
      : `<span class="text-on-surface-variant">Kayıtlı kural: ${esc(ruleLabel(savedRule))}</span>`;
  } else if (panel.inferred) {
    ruleStatus = `<span class="text-info">Otomatik algılandı: ${esc(inferredText)}</span>`;
  }

  return `
    <div class="glass-panel rounded-3xl p-5 border-l-4 border-l-info animate-fade-in" id="lpanel-${s}">
      <div class="flex flex-wrap gap-4 items-start">
        <button type="button" class="shrink-0 rounded-2xl overflow-hidden border border-line w-20 h-20 cursor-zoom-in" onclick="window.__listOpenImage(${s})" title="Görseli büyüt" aria-label="Görseli büyüt">
          <img src="${url}" class="w-full h-full object-cover" alt="" />
        </button>
        <div class="flex-1 min-w-[220px]">
          <div class="flex flex-wrap items-center gap-2">
            <h3 class="font-headline text-lg text-on-surface">Liste inceleme</h3>
            ${kindLabel ? `<span class="src-chip">${esc(kindLabel)}</span>` : ''}
            <span class="text-sm text-on-surface-variant">${seg.indices.length} satır</span>
            <span class="text-xs text-on-surface-variant/70 truncate max-w-[220px]" title="${esc(seg.file.name)}">${esc(seg.file.name)}</span>
          </div>
          ${info.length ? `<div class="flex flex-wrap gap-x-5 gap-y-1 mt-2 text-sm">${info.map(([k, v]) => `<span><span class="text-on-surface-variant">${k}:</span> <span class="text-on-surface">${esc(v)}</span></span>`).join('')}</div>` : ''}
          <div class="text-xs text-on-surface-variant/80 mt-2">Liste satırları MRZ ile doğrulanmadığı için sarıdır; işaretlediğiniz satırlar onayınızla yazılır.${staffCount ? ` ${staffCount} rehber/kaptan satırı varsayılan olarak işaretsiz.` : ''}</div>
        </div>
        <div class="min-w-[160px] text-right" id="lp-count-${s}">${counterHtml(seg)}</div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4 pt-4 border-t border-line">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs font-medium text-on-surface-variant ml-1" for="lp-rule-${s}">İşaret kuralı${helpIcon('Acentenin listede uçanları nasıl işaretlediği. Seçince yalnız eşleşen satırların kutusu işaretlenir; sonra tek tek değiştirebilirsiniz.')}</label>
          <select class="form-select form-input-sm" id="lp-rule-${s}" onchange="window.__listRuleChanged(${s}, this.value)">${options}</select>
          ${panel.agencyFromGroup ? '' : `
          <input class="form-input form-input-sm" id="lp-agency-${s}" value="${esc(panel.agency)}" placeholder="Acente (kuralı hatırlamak için)" onchange="window.__listAgencyChanged(${s}, this.value)" />`}
          <div class="flex flex-wrap items-center gap-2 text-xs">
            <button type="button" class="btn-secondary btn-sm" onclick="window.__listRememberRule(${s})">
              <span class="material-symbols-outlined text-[16px] align-middle">bookmark_add</span> Bu acente için hatırla
            </button>
            ${ruleStatus}
          </div>
        </div>

        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-medium text-on-surface-variant ml-1">Toplu alan${helpIcon('Bu listedeki kartlarda BOŞ olan uyruk/cinsiyet alanlarını doldurur; dolu alanlara dokunmaz.')}</span>
          <div class="flex gap-2">
            <input class="form-input form-input-sm font-mono uppercase flex-1 min-w-0" id="lp-nat-${s}" value="${esc(panel.bulkNat)}" placeholder="Uyruk (TUR…)" aria-label="Toplu uyruk" />
            <select class="form-select form-input-sm w-28" id="lp-sex-${s}" aria-label="Toplu cinsiyet">
              <option value="" ${!panel.bulkSex ? 'selected' : ''}>Cinsiyet</option>
              <option value="M" ${panel.bulkSex === 'M' ? 'selected' : ''}>Erkek</option>
              <option value="F" ${panel.bulkSex === 'F' ? 'selected' : ''}>Kadın</option>
            </select>
          </div>
          <button type="button" class="btn-secondary btn-sm self-start" onclick="window.__listBulkApply(${s})">
            <span class="material-symbols-outlined text-[16px] align-middle">format_color_fill</span> Boş olanlara uygula
          </button>
        </div>

        <div class="flex flex-col gap-1.5 lg:items-end">
          <label class="inline-flex items-center gap-2 text-sm text-on-surface cursor-pointer select-none">
            <input type="checkbox" class="w-4 h-4 rounded" id="lp-only-${s}" ${panel.onlySelected ? 'checked' : ''} onchange="window.__listToggleSelected(${s}, this.checked)" />
            Yalnız seçilileri göster
          </label>
          <span class="text-xs text-on-surface-variant" id="lp-hidden-${s}"></span>
        </div>
      </div>
    </div>`;
}

function renderListRow(rec, i) {
  const pending = isPendingManual(rec);
  const dis = pending ? 'disabled' : '';
  const flags = rec.flags || [];
  const edge = pending ? 'bg-on-surface-variant/40' : rec.green ? 'bg-success' : 'bg-warning';
  const statusTitle = pending
    ? 'Manuel Kontrol bekliyor'
    : rec.green
      ? 'Yeşil — MRZ doğrulandı'
      : `Sarı — kontrol et${flags.length ? `: ${flags.map(flagLabel).join(', ')}` : ''}`;
  // FREE_TEXT_UNVERIFIED her liste satırında var; çip olarak tekrarlanmaz (kenar rengi + ipucu).
  const flagChips = flags
    .filter(f => f !== 'free_text_unverified')
    .map(f => `<span class="flag-chip">${esc(flagLabel(f))}</span>`)
    .join('');
  return `
    <div class="list-row ${pending ? 'opacity-75' : ''} ${rec._deferredHotel ? 'list-row-deferred' : ''}" id="pcard-${i}">
      <span class="list-row-edge ${edge}" title="${esc(statusTitle)}"></span>
      ${pending
        ? `<a href="#/manual_review" class="w-5 h-5 flex items-center justify-center text-on-surface-variant hover:text-info" title="Manuel Kontrol'de bekliyor — oraya git"><span class="material-symbols-outlined text-[20px]">pending_actions</span></a>`
        : `<input type="checkbox" class="w-5 h-5 rounded shrink-0" id="pc-approve-${i}" ${rec._approved ? 'checked' : ''} title="Onayla ve Ekle" aria-label="Onayla ve Ekle" />`}
      <input class="form-input form-input-sm uppercase flex-1 min-w-[180px]" id="pc-name-${i}" value="${esc(rec.name || '')}" placeholder="AD SOYAD" aria-label="İsim" ${dis} />
      ${(() => { const h = natHint(rec); return `<input class="form-input form-input-sm font-mono uppercase w-24 ${h.cls}" id="pc-nat-${i}" value="${esc(rec.nationality || '')}" placeholder="Uyruk" aria-label="Uyruk" title="${esc(h.title)}" ${dis} />`; })()}
      <select class="form-select form-input-sm w-28" id="pc-sex-${i}" aria-label="Cinsiyet" ${dis}>
        <option value="" ${!rec.sex ? 'selected' : ''}>—</option>
        <option value="M" ${rec.sex === 'M' ? 'selected' : ''}>Erkek</option>
        <option value="F" ${rec.sex === 'F' ? 'selected' : ''}>Kadın</option>
      </select>
      <input class="form-input form-input-sm font-mono uppercase w-40" id="pc-ppno-${i}" value="${esc(rec.passport_no || '')}" placeholder="Belge no" aria-label="Belge no" ${dis} />
      <div class="flex flex-wrap items-center gap-1 md:w-56 md:shrink-0">${sourceChipsHtml(rec, { withKind: false })}${flagChips}</div>
      <button type="button" onclick="window.__removeCard(${i})" title="Bu satırı sil" aria-label="Bu satırı sil"
              class="ml-auto w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-on-surface-variant hover:text-danger hover:bg-danger/15 transition-colors">
        <span class="material-symbols-outlined text-[18px]">close</span>
      </button>
    </div>`;
}

window.__listRuleChanged = function(s, rule) {
  const seg = segments[s];
  const panel = seg && listPanels.get(seg.file);
  if (!panel) return;
  syncCardsToState();
  panel.rule = rule;
  panel.ruleSource = 'user';
  if (rule) applyRule(seg, rule);
  renderCards();
};

window.__listAgencyChanged = function(s, value) {
  const seg = segments[s];
  const panel = seg && listPanels.get(seg.file);
  if (!panel) return;
  syncCardsToState();
  panel.agency = String(value || '').trim();
  const saved = savedRuleFor(panel.agency);
  // Operatörün elle seçtiği kural ezilmez; algılanan (auto) kural kayıtlıyla değişir.
  if (saved && panel.ruleSource !== 'user' && panel.rule !== saved) {
    panel.rule = saved;
    panel.ruleSource = 'saved';
    applyRule(seg, saved);
    toast.info('Kayıtlı kural uygulandı', `${panel.agency}: ${ruleLabel(saved)}`);
  }
  renderCards();
};

window.__listRememberRule = async function(s) {
  const seg = segments[s];
  const panel = seg && listPanels.get(seg.file);
  if (!panel) return;
  syncCardsToState();
  const agency = panel.agency.trim();
  if (!agency) {
    toast.warning('Acente gerekli', 'Kuralı hatırlamak için acente adını yazın.');
    document.getElementById(`lp-agency-${s}`)?.focus();
    return;
  }
  try {
    const res = await api.post('/api/lists/mark-rule', { agency, rule: panel.rule });
    state.markRules = res.rules || {};
    if (panel.rule) toast.success('Kural kaydedildi', `${agency}: ${ruleLabel(panel.rule)}`);
    else toast.info('Kural silindi', `${agency} için kayıtlı işaret kuralı kaldırıldı.`);
    renderCards();
  } catch (err) {
    toast.error('Kural kaydedilemedi', err.message);
  }
};

window.__listToggleSelected = function(s, checked) {
  const seg = segments[s];
  const panel = seg && listPanels.get(seg.file);
  if (!panel) return;
  panel.onlySelected = !!checked;
  applyRowFilter(s);
};

window.__listBulkApply = function(s) {
  const seg = segments[s];
  const panel = seg && listPanels.get(seg.file);
  if (!panel) return;
  syncCardsToState();
  const nat = panel.bulkNat;
  const sex = panel.bulkSex;
  if (!nat && !sex) {
    toast.warning('Değer seçin', 'Uygulamak için uyruk veya cinsiyet seçin.');
    return;
  }
  let natFilled = 0;
  let sexFilled = 0;
  for (const i of seg.indices) {
    const rec = state.records[i];
    if (isPendingManual(rec)) continue;
    if (nat && !rec.nationality) { rec.nationality = nat; natFilled++; }
    if (sex && !rec.sex) { rec.sex = sex; sexFilled++; }
    refreshMissingFieldsFlag(rec);
  }
  renderCards();
  if (natFilled || sexFilled) {
    const parts = [];
    if (natFilled) parts.push(`${natFilled} karta uyruk ${nat}`);
    if (sexFilled) parts.push(`${sexFilled} karta cinsiyet ${sex === 'M' ? 'Erkek' : 'Kadın'}`);
    toast.success('Toplu alan uygulandı', parts.join(', '));
  } else {
    toast.info('Boş alan yok', 'Bu listedeki kartların bu alanları zaten dolu.');
  }
};

// 4 zorunlu alan tamamlandıysa MISSING_REQUIRED_FIELDS bayrağını düşür. Kayıt yeşile
// dönmez: liste satırı MRZ'siz olduğu için FREE_TEXT_UNVERIFIED (sarı) kalır.
function refreshMissingFieldsFlag(rec) {
  const complete = rec.nationality && rec.name && rec.passport_no && ['M', 'F'].includes(rec.sex);
  if (complete && Array.isArray(rec.flags)) {
    rec.flags = rec.flags.filter(f => f !== 'missing_required_fields');
  }
}

window.__listOpenImage = function(s) {
  const seg = segments[s];
  if (!seg?.file) return;
  const url = URL.createObjectURL(seg.file);
  state.objectUrls.push(url);
  modal.open(esc(seg.file.name), `
    <div class="flex justify-center">
      <img src="${url}" class="max-w-full max-h-[75vh] rounded-xl" alt="" />
    </div>`);
};

// ─── Otel seçimi (aynı taramada farklı oteller: her rezervasyona tek otel) ───
function listHotels() {
  const hotels = new Map();   // fold(otel) → { label, count }
  for (const rec of state.records) {
    if (isPendingManual(rec)) continue;
    const label = String(rec.group?.hotel || '').trim();
    if (!label) continue;
    const key = fold(label);
    const entry = hotels.get(key) || { label, count: 0 };
    entry.count++;
    hotels.set(key, entry);
  }
  return hotels;
}

function enforceHotelChoice() {
  const hotels = listHotels();
  if (hotels.size < 2) state.hotelChoice = '';
  else if (state.hotelChoice && !hotels.has(state.hotelChoice)) state.hotelChoice = '';
  for (const rec of state.records) {
    const key = fold(rec.group?.hotel || '');
    const other = !!(state.hotelChoice && key && key !== state.hotelChoice);
    if (other && !rec._deferredHotel) {
      rec._deferredHotel = true;
      rec._approved = false;
    } else if (!other && rec._deferredHotel) {
      rec._deferredHotel = false;
      rec._approved = defaultApproval(rec, listPanels.get(recordFile(rec))?.rule || '');
    }
  }
  return hotels;
}

function renderHotelBar() {
  const bar = document.getElementById('list-hotel-bar');
  if (!bar) return;
  const hotels = listHotels();
  if (hotels.size < 2) { bar.innerHTML = ''; return; }
  const deferred = state.records.filter(r => r._deferredHotel);
  const otherNames = [...new Set(deferred.map(r => String(r.group?.hotel || '').trim()))].filter(Boolean);
  const options = [...hotels.entries()]
    .map(([key, h]) => `<option value="${esc(key)}" ${state.hotelChoice === key ? 'selected' : ''}>${esc(h.label)} (${h.count} satır)</option>`)
    .join('');
  bar.innerHTML = `
    <div class="glass-panel rounded-3xl p-5 mb-4 border-l-4 border-l-warning flex flex-wrap items-center gap-4">
      <span class="material-symbols-outlined text-warning text-3xl">apartment</span>
      <div class="flex-1 min-w-[220px]">
        <div class="font-semibold text-on-surface">Bu taramada ${hotels.size} farklı otel var</div>
        <div class="text-sm text-on-surface-variant">Bir rezervasyona tek otel yazılır. Yazılacak oteli seçin; diğer otellerin satırları onaysız kalır ve yazımdan sonra ekranda bekler.</div>
        ${state.hotelChoice && deferred.length
          ? `<div class="text-sm text-info mt-1">${deferred.length} satır başka otelde (${esc(otherNames.join(', '))}) — onayları kaldırıldı. Diğer oteller için tekrar yaz.</div>`
          : ''}
      </div>
      <div class="flex flex-col gap-1 min-w-[240px]">
        <label class="text-xs font-medium text-on-surface-variant ml-1" for="lp-hotel-choice">Yazılacak otel</label>
        <select class="form-select form-input-sm" id="lp-hotel-choice" onchange="window.__listHotelChoice(this.value)">
          <option value="">Seçin…</option>${options}
        </select>
      </div>
    </div>`;
}

window.__listHotelChoice = function(value) {
  syncCardsToState();
  state.hotelChoice = value || '';
  renderCards();
};

// ─── Rezervasyon formunu grup bilgisinden doldur (otel, acente, uçuş günü) ───
function groupDateToSheet(value) {
  const s = String(value || '').trim();
  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(s);
  if (m) return `${m[3].padStart(2, '0')}.${m[2].padStart(2, '0')}.${m[1]}`;
  m = /^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/.exec(s);
  if (m) return `${m[1].padStart(2, '0')}.${m[2].padStart(2, '0')}.${m[3]}`;
  return '';
}

function findSheet(name) {
  return state.sheets.find(sheet => String(sheet).trim() === name) || '';
}

function uniqueGroupValue(records, key) {
  const values = new Map();
  for (const rec of records) {
    const v = String(rec.group?.[key] ?? '').trim();
    if (v) values.set(fold(v), v);
  }
  return values.size === 1 ? [...values.values()][0] : '';
}

// Alan boşsa ya da daha önce otomatik doldurulmuş ve elle değiştirilmemişse doldur.
function autofillInput(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  const prevAuto = el.dataset.autoValue || '';
  const untouched = !el.value.trim() || (prevAuto && el.value === prevAuto);
  if (value && untouched) {
    el.value = value;
    el.dataset.autoValue = value;
  } else if (!value && prevAuto && el.value === prevAuto) {
    el.value = '';
    el.dataset.autoValue = '';
  }
}

function autofillReservation() {
  // Yazım kapsamı: Manuel Kontrol bekleyenler ve başka otelde bekleyenler hariç.
  const scope = state.records.filter(r => !isPendingManual(r) && !r._deferredHotel);
  autofillInput('pp-hotel', uniqueGroupValue(scope, 'hotel'));
  autofillInput('pp-agency', uniqueGroupValue(scope, 'agency'));

  const sheet = findSheet(groupDateToSheet(uniqueGroupValue(scope, 'date')));
  const sel = document.getElementById('pp-sheet-select');
  // Aynı hedefe bir kez geçilir; operatör sonra başka gün seçerse ezilmez.
  if (sheet && sel && state.autoSheet !== sheet) {
    state.autoSheet = sheet;
    if (sel.value !== sheet) {
      sel.value = sheet;
      loadBlocks(sheet);
      toast.info('Uçuş günü seçildi', `Listedeki tarihe göre ${sheet} sayfası seçildi.`);
    }
  }
}

window.__retryOcr = async function(i) {
  const rec = state.records[i];
  const file = Number.isInteger(rec._source_file_index)
    ? state.files[rec._source_file_index]
    : state.files.find(f => f.name === rec._source_file_name);
  if (!file) return toast.warning('Görsel bulunamadı');
  syncCardsToState();
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch('/api/passport/retry-ocr', { method: 'POST', body: form });
    if (!res.ok) {
      const payload = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof payload.detail === 'string' ? payload.detail : payload.detail?.message);
    }
    const data = await res.json();
    // Eger bu da birden fazla record döndürürse, sadece ilkini mevcut karta yazıyoruz:
    state.records[i] = data.records ? data.records[0] : data;
    state.records[i]._source_file_name = file.name;
    state.records[i]._source_file_index = rec._source_file_index;
    renderCards();
    toast.success('Yeniden tarandı', state.records[i].green ? 'Sonuç doğrulandı' : 'Sonuç hâlâ kontrol gerektiriyor');
  } catch (err) { toast.error('OCR taraması başarısız', err.message); }
};

// DOM'daki kart düzenlemelerini state.records'a geri yaz (re-render'da kaybolmasın)
function syncCardsToState() {
  for (let i = 0; i < state.records.length; i++) {
    const nat = document.getElementById(`pc-nat-${i}`);
    if (!nat) continue;
    state.records[i].nationality = nat.value.trim().toUpperCase();
    state.records[i].sex = (document.getElementById(`pc-sex-${i}`)?.value || '').trim().toUpperCase();
    state.records[i].name = (document.getElementById(`pc-name-${i}`)?.value || '').trim().toUpperCase();
    state.records[i].passport_no = (document.getElementById(`pc-ppno-${i}`)?.value || '').trim();
    const chk = document.getElementById(`pc-approve-${i}`);
    if (chk) state.records[i]._approved = chk.checked;
  }
  syncPanelsToState();
}

// Tek tuşla bir taramayı kaldır
window.__removeCard = function(i) {
  syncCardsToState();
  const rec = state.records.splice(i, 1)[0];
  
  // Eğer bu dosyaya ait başka kayıt kalmadıysa dosyayı da silebiliriz
  const sameSourceRemains = rec && state.records.some(r =>
    Number.isInteger(rec._source_file_index)
      ? r._source_file_index === rec._source_file_index
      : r._source_file_name === rec._source_file_name
  );
  if (rec && (Number.isInteger(rec._source_file_index) || rec._source_file_name) && !sameSourceRemains) {
    const fileIndex = Number.isInteger(rec._source_file_index)
      ? rec._source_file_index
      : state.files.findIndex(f => f.name === rec._source_file_name);
    if (fileIndex !== -1) {
      state.files.splice(fileIndex, 1);
      state.records = state.records.map(item => ({
        ...item,
        _source_file_index: Number.isInteger(item._source_file_index)
          && item._source_file_index > fileIndex
          ? item._source_file_index - 1
          : item._source_file_index,
      }));
    }
  }
  
  renderFileList();
  if (!state.records.length) {
    hideCards();
    return;
  }
  renderCards();
};

// ─── Rezervasyon oluştur + kimlikleri yaz (pasaport girerken o an açılır) ───
function readCard(i) {
  return {
    nationality: document.getElementById(`pc-nat-${i}`)?.value.trim().toUpperCase() || '',
    sex: document.getElementById(`pc-sex-${i}`)?.value.trim().toUpperCase() || '',
    name: document.getElementById(`pc-name-${i}`)?.value.trim().toUpperCase() || '',
    passport_no: document.getElementById(`pc-ppno-${i}`)?.value.trim() || '',
    extraction_id: state.records[i]?.extraction_id,
  };
}

// Onaysız (sarı veya işareti kaldırılmış) kayıtları açıkça listeleyen uyarı penceresi.
function unapprovedWarningHtml(skipped, pendingManualCount, approvedCount) {
  const rows = skipped.map(({ index, card, rec }) => {
    const flags = (rec.flags || []).map(f => `<span class="badge badge-yellow">${esc(flagLabel(f))}</span>`).join(' ');
    const kind = rec.green ? '<span class="badge badge-green">yeşil, işaretsiz</span>' : '<span class="badge badge-yellow">sarı</span>';
    return `
      <li class="flex flex-wrap items-center gap-2 py-2 border-b border-tertiary/10 last:border-0">
        <span class="text-on-surface-variant text-xs w-14">Kart ${index + 1}</span>
        <strong class="text-on-surface text-sm">${esc(card.name || '(isimsiz)')}</strong>
        <span class="font-mono text-xs text-on-surface-variant">${esc(card.passport_no || '—')}</span>
        ${kind} ${flags}
      </li>`;
  }).join('');
  return `
    <p class="text-on-surface mb-3">
      Aşağıdaki <strong class="text-warning">${skipped.length}</strong> kayıtta veri var ama <strong>onaylı değil</strong>.
      Devam ederseniz yazılmayacak ve bu ekrandan silinecek.
    </p>
    <ul class="max-h-64 overflow-auto rounded-2xl bg-tertiary/[.04] border border-tertiary/10 px-4 mb-3">${rows}</ul>
    ${pendingManualCount ? `<p class="text-xs text-on-surface-variant mb-2">${pendingManualCount} kayıt Manuel Kontrol'de bekliyor; onlar bu rezervasyona yazılmaz.</p>` : ''}
    <p class="text-sm text-on-surface-variant">Kartları gözden geçirip "Onayla ve Ekle" kutusunu işaretlemek için <strong>Geri dön</strong>; yalnız ${approvedCount} onaylı yolcuyu yazmak için devam edin.</p>`;
}

window.__writePlanning = async function() {
  if (writing) return;
  const sheet = document.getElementById('pp-sheet-select')?.value;
  if (!sheet) { toast.warning('Uçuş günü seçin'); return; }
  const existingMode = document.getElementById('pp-mode')?.value === 'existing';

  // Onaylı kartları topla; veri olup onaylanmamışları ayrıca listele (veri kaybı uyarısı).
  // Manuel Kontrol'de bekleyen kartlar pasiftir — ne yazılır ne de "onaysız" sayılır.
  // Başka otel için bekleyen liste satırları (Yazılacak otel seçimi) da "onaysız" sayılmaz:
  // yazımdan sonra ekranda kalır.
  const approved = [];
  const approvedIdx = [];
  const skipped = [];
  let pendingManualCount = 0;
  for (let i = 0; i < state.records.length; i++) {
    const rec = state.records[i];
    if (isPendingManual(rec)) { pendingManualCount++; continue; }
    const card = readCard(i);
    const chk = document.getElementById(`pc-approve-${i}`);
    if (chk?.checked) { approved.push(card); approvedIdx.push(i); }
    else if (rec._deferredHotel) continue;
    else if (card.name || card.passport_no) skipped.push({ index: i, card, rec });
  }
  if (!approved.length) {
    toast.warning(
      'Onaylı kart yok',
      pendingManualCount
        ? `En az bir kartı onaylayın. ${pendingManualCount} kayıt Manuel Kontrol'de bekliyor.`
        : 'En az bir kartı onaylayın',
    );
    return;
  }
  // Tek rezervasyona tek otel: farklı otellerin satırları birlikte seçiliyse durdur.
  const approvedHotels = new Set(approvedIdx
    .map(i => fold(state.records[i]?.group?.hotel || ''))
    .filter(Boolean));
  if (approvedHotels.size > 1) {
    toast.warning('Farklı oteller seçili', 'Bir rezervasyona tek otel yazılır. Üstteki "Yazılacak otel" seçimini yapın.');
    document.getElementById('list-hotel-bar')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    return;
  }

  const ruleCandidates = ruleSaveCandidates(approvedIdx);

  writing = true;
  try {
    if (skipped.length) {
      const proceed = await modal.confirm({
        title: 'Onaylanmamış kayıtlar var',
        bodyHtml: unapprovedWarningHtml(skipped, pendingManualCount, approved.length),
        confirmLabel: `Yalnız ${approved.length} onaylıyı yaz`,
        cancelLabel: 'Geri dön ve kontrol et',
      });
      if (!proceed) {
        document.getElementById(`pcard-${skipped[0].index}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
    }

    // PAX: alandan oku, boşsa onaylı sayısı
    let pax = existingMode ? approved.length : parseInt(document.getElementById('pp-pax')?.value, 10);
    if (!pax || pax < 1) pax = approved.length;
    if (pax > 28) { toast.warning('PAX en fazla 28'); return; }
    // PAX onaylı yolcu sayısından az ise otomatik yükselt (pasaport kaybolmasın)
    if (approved.length > pax) {
      pax = approved.length;
      toast.info('PAX güncellendi', `PAX ${pax} olarak ayarlandı (${approved.length} onaylı yolcu)`);
    }
    // PAX, yazılacak yolcudan fazlaysa: boş satırlar kalır — operatöre bildir
    if (!existingMode && pax > approved.length) {
      const proceed = await modal.confirm({
        title: 'Boş yolcu satırı kalacak',
        bodyHtml: `<p class="text-on-surface">PAX <strong>${pax}</strong> ama <strong>${approved.length}</strong> yolcu yazılacak. <strong>${pax - approved.length}</strong> satır boş kalacak; eksik pasaportları sonra "Mevcut rezervasyona pasaport ekle" ile tamamlayabilirsiniz.</p>`,
        confirmLabel: 'Devam et',
      });
      if (!proceed) return;
    }

    const hotel = document.getElementById('pp-hotel')?.value.trim() || '';
    const agency = document.getElementById('pp-agency')?.value.trim() || '';
    const reserved_by = document.getElementById('pp-reserved')?.value.trim() || '';

    const btn = document.getElementById('btn-write');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="material-symbols-outlined animate-spin text-[20px]">progress_activity</span> Oluşturuluyor...';
    }
    // Yeni rezervasyon gövdesi; kota onayı (allow_quota_override) yerinde eklenir.
    const createBody = {
      sheet, pax, hotel, agency, reserved_by, identities: approved,
      expected_revision: state.revision,
    };

    try {
      if (existingMode) {
        const leadRow = parseInt(document.getElementById('pp-existing-block')?.value, 10);
        if (!leadRow) throw new Error('Mevcut rezervasyon seçin.');
        await api.post('/api/planning/append-identities', {
          sheet, lead_row: leadRow, identities: approved, expected_revision: state.revision,
        });
        const ruleNote = await autoSaveRules(ruleCandidates);
        toast.success('Kimlikler eklendi', `${approved.length} yolcu mevcut rezervasyona yazıldı${ruleNote}`);
        await resetAfterWrite(sheet, approvedIdx);
      } else {
        const res = await postCreateWithIdentities(createBody);
        if (!res) {   // kota aşımı onaylanmadı: kartlar ekranda kalır
          toast.info('Rezervasyon oluşturulmadı', 'Acente kotası aşılmadı. Kartlar ekranda duruyor.');
          return;
        }
        const ruleNote = await autoSaveRules(ruleCandidates);
        toast.success('Rezervasyon oluşturuldu', `${res.balloon} balonuna atandı — ${approved.length} yolcu yazıldı${ruleNote}`);
        await resetAfterWrite(sheet, approvedIdx);
      }
    } catch (err) {
      if (err.detail?.code === 'capacity_confirmation_required') {
        pendingOverflowWritten = approvedIdx;
        pendingOverflowRules = ruleCandidates;
        return showPassportCapacityChoice({ ...createBody }, err.detail);
      }
      toast.error('Hata', err.message);
    } finally {
      if (btn?.isConnected) {
        btn.disabled = false;
        resetWriteButtonLabel(existingMode);
      }
    }
  } finally {
    writing = false;
  }
};

// Yazılan satırların listelerinde kullanılan kural, acente biliniyor ve o acentenin kayıtlı
// kuralı yoksa yazım başarıyla bitince kaydedilir (bir sonraki listede otomatik gelir).
function ruleSaveCandidates(writtenIdx) {
  const written = new Set(writtenIdx);
  const formAgency = document.getElementById('pp-agency')?.value.trim() || '';
  const out = new Map();
  for (const seg of segments) {
    if (!seg.isList || !seg.indices.some(i => written.has(i))) continue;
    const panel = listPanels.get(seg.file);
    const agency = (panel?.agency || formAgency).trim();
    const key = normalizeAgencyKey(agency);
    if (!panel?.rule || !key || savedRuleFor(agency) || out.has(key)) continue;
    out.set(key, { agency, rule: panel.rule });
  }
  return [...out.values()];
}

// Dönüş: toast mesajına eklenecek not ('' = kaydedilen yok). Hata yazımı bozmaz.
async function autoSaveRules(candidates) {
  let saved = 0;
  for (const { agency, rule } of candidates || []) {
    try {
      const res = await api.post('/api/lists/mark-rule', { agency, rule });
      state.markRules = res.rules || state.markRules;
      saved++;
    } catch { /* kural kaydı isteğe bağlı */ }
  }
  return saved ? ' · Kural acenteye kaydedildi' : '';
}

// Başarılı yazımdan sonra: tarama ve rezervasyon formu bir sonraki rezervasyona hazır.
// Başka otel için bekleyen liste satırları (ve görselleri) ekranda kalır → "diğer oteller
// için tekrar yaz". writtenIdx: bu yazımda gönderilen kartların indeksleri.
async function resetAfterWrite(sheet, writtenIdx = []) {
  const written = new Set(writtenIdx);
  if (state.records.length) syncCardsToState();
  const waiting = state.records.filter((rec, i) => rec._deferredHotel && !written.has(i));
  if (waiting.length) {
    const files = [];
    const next = waiting.map(rec => {
      const file = recordFile(rec);
      let index = null;
      if (file) {
        index = files.indexOf(file);
        if (index === -1) { files.push(file); index = files.length - 1; }
      }
      return { ...rec, _source_file_index: index, _deferredHotel: false };
    });
    releaseObjectUrls();
    state.files = files;
    state.records = next;
    state.hotelChoice = '';
    for (const rec of state.records) {
      rec._approved = defaultApproval(rec, listPanels.get(recordFile(rec))?.rule || '');
    }
  } else {
    resetScan();
    state.hotelChoice = '';
    state.autoSheet = '';
  }
  const paxEl = document.getElementById('pp-pax');
  if (paxEl) { paxEl.value = ''; paxEl.dataset.auto = 'on'; }
  for (const id of ['pp-hotel', 'pp-agency', 'pp-reserved']) {
    const el = document.getElementById(id);
    if (el) { el.value = ''; el.dataset.autoValue = ''; }
  }
  renderFileList();
  if (state.records.length) {
    renderCards();
    toast.info('Diğer oteller bekliyor', `${state.records.length} satır ekranda kaldı. Sıradaki otel için kontrol edip tekrar yazın.`);
  } else {
    hideCards();
  }
  if (sheet) await loadBlocks(sheet);
}

// create-with-identities isteği; 409 agency_quota_exceeded gelirse operatöre sorar ve
// allow_quota_override ile yeniden dener (body yerinde güncellenir). Vazgeçilirse null.
async function postCreateWithIdentities(body) {
  try {
    return await api.post('/api/planning/create-with-identities', body);
  } catch (err) {
    if (!isQuotaExceeded(err) || body.allow_quota_override) throw err;
    const ok = await modal.confirm(quotaConfirmOptions(err.detail, esc));
    if (!ok) return null;
    body.allow_quota_override = true;
    return api.post('/api/planning/create-with-identities', body);
  }
}

function showPassportCapacityChoice(body, detail) {
  window.__pendingPassportOverflow = body;
  const intro = detail.message || 'Grup kapasite içinde hiçbir balona sığmıyor. Hedef balonu seçin.';
  const limit = Number(detail.daily_max_balloons) || 0;
  modal.open('Balon Kapasitesi Doldu', `
    <p class="text-on-surface-variant mb-4">${esc(intro)}</p>
    ${limit ? `<p class="text-sm text-on-surface-variant -mt-2 mb-4">Günlük en fazla ${limit} balon uçabilir.</p>` : ''}
    <div class="space-y-2">${(detail.balloon_codes || []).map(code => `
      <label class="flex items-center justify-between rounded-lg border border-line p-3 cursor-pointer">
        <span><input type="radio" name="pp-overflow-balloon" value="${esc(code)}" class="mr-3" />${esc(code)}</span>
        <strong class="tnum">${Number(detail.balloon_load?.[code] || 0)}/${capacityFor(detail, code)}</strong>
      </label>`).join('')}</div>
  `, `
    <button class="btn-secondary" onclick="window.__closeModal()">İptal</button>
    <button class="btn-primary" id="pp-overflow-confirm" onclick="window.__confirmPassportOverflow()">Aşımı Onayla</button>
  `);
}

window.__confirmPassportOverflow = async function() {
  if (overflowSubmitting) return;
  const balloon = document.querySelector('input[name="pp-overflow-balloon"]:checked')?.value;
  if (!balloon) return toast.warning('Hedef balonu seçin');
  const body = { ...(window.__pendingPassportOverflow || {}), requested_balloon: balloon, allow_overflow: true };
  const btn = document.getElementById('pp-overflow-confirm');
  overflowSubmitting = true;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="material-symbols-outlined animate-spin text-[18px]">progress_activity</span> Kaydediliyor...';
  }
  try {
    const res = await postCreateWithIdentities(body);
    if (!res) {
      toast.info('Rezervasyon oluşturulmadı', 'Acente kotası aşılmadı. Kartlar ekranda duruyor.');
      return;
    }
    window.__pendingPassportOverflow = null;
    modal.close();
    const ruleNote = await autoSaveRules(pendingOverflowRules);
    pendingOverflowRules = [];
    toast.warning('Kapasite aşımı onaylandı', `${res.balloon} balonuna atandı — ${body.identities?.length || 0} yolcu yazıldı${ruleNote}`);
    await resetAfterWrite(body.sheet, pendingOverflowWritten);
    pendingOverflowWritten = [];
  } catch (err) {
    toast.error('Rezervasyon oluşturulamadı', err.message);
    if (btn?.isConnected) {
      btn.disabled = false;
      btn.textContent = 'Aşımı Onayla';
    }
  } finally {
    overflowSubmitting = false;
  }
};

// Bayrak kodları İngilizce sabit etiket: sayfa lang="tr" olduğu için CSS `uppercase` ve
// toUpperCase() 'i'yi 'İ' yapıyordu ("LOW_CONFİDENCE"). Locale sabit en-US.
const FLAG_LABELS_TR = { nationality_inferred: 'UYRUK TAHMİNİ' };
function flagLabel(flag) {
  return FLAG_LABELS_TR[flag] || String(flag || '').toLocaleUpperCase('en-US');
}

// Uyruk belge numarasından / listeden / model tahmininden geldiyse ve operatör değiştirmediyse
// alanı işaretle; gerekçe ipucu olarak gösterilir.
const NAT_DERIVED = ['document', 'pattern', 'list', 'model'];
const NAT_SOURCE_TR = {
  document: 'Belge no kontrol hanesinden (kesin)',
  pattern: 'Belge no biçiminden (olası)',
  list: 'Listedeki diğer satırlardan (olası)',
  model: 'Model tahmini — kontrol edin',
};
function natHint(rec) {
  if (rec._natAuto === undefined) rec._natAuto = rec.nationality || '';
  const derived = NAT_DERIVED.includes(rec.nationality_source) && rec.nationality && rec.nationality === rec._natAuto;
  if (!derived) return { cls: '', title: '' };
  const strong = rec.nationality_source === 'document';
  const title = `${NAT_SOURCE_TR[rec.nationality_source]}${rec.nationality_reason ? ' — ' + rec.nationality_reason : ''}`;
  return { cls: strong ? 'nat-derived' : 'nat-inferred', title };
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function releaseObjectUrls() {
  for (const url of state.objectUrls) URL.revokeObjectURL(url);
  state.objectUrls = [];
}
