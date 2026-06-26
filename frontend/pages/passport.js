/* ═══════════════════════════════════════════════════════════════════
   Pasaport Tarama — Drag & drop, MRZ okuma, kontrol kartları
   Brief §8: sol görsel, sağ 4 alan, yeşil/sarı status
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, renderHeader, modal, helpIcon, appStatus } from '/app.js';
import { attachCombobox } from '/combobox.js';

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
};

export async function render(container) {
  renderHeader('Pasaport Tarama', 'Fotoğraf yükle, MRZ oku, kontrol et ve planlamaya yaz');

  container.innerHTML = `
    <!-- Rezervasyon: pasaport girerken o an açılır -->
    <div class="glass-panel rounded-[40px] p-6 md:p-8 mb-6 animate-fade-in">
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
    <div class="glass-panel rounded-[40px] border-2 border-dashed border-primary-container/30 p-12 text-center cursor-pointer transition-all duration-300 hover:border-primary hover:bg-primary/5 hover:shadow-[0_0_30px_rgba(255,182,141,0.05)] mb-6 animate-fade-in" id="dropzone"
         ondragover="event.preventDefault(); this.classList.add('border-primary', 'bg-primary/10')"
         ondragleave="this.classList.remove('border-primary', 'bg-primary/10')"
         ondrop="window.__handleDrop(event)"
         onclick="document.getElementById('file-input').click()">
      <div class="bg-surface-light w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4 border border-white/5">
        <span class="material-symbols-outlined text-4xl text-primary">add_a_photo</span>
      </div>
      <div class="text-lg text-on-surface mb-2"><strong>Pasaport fotoğraflarını sürükle</strong> veya tıkla</div>
      <div class="text-sm text-on-surface-variant">JPG, PNG, WEBP • Birden fazla dosya seçilebilir</div>
      <input type="file" id="file-input" multiple accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" style="display:none"
             onchange="window.__handleFiles(this.files)" />
    </div>

    <!-- File list + action -->
    <div class="glass-panel rounded-[40px] p-6 md:p-8 mb-6 animate-fade-in" id="file-section" style="display:none">
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
      <div id="progress-area" class="mt-6 p-5 rounded-3xl bg-surface-light border border-white/5" style="display:none">
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
          <div class="flex items-center gap-2 bg-surface-light px-4 py-2 rounded-full border border-white/5">
            <span class="material-symbols-outlined text-[20px] text-on-surface-variant">analytics</span>
            <span class="text-sm font-medium text-on-surface-variant" id="cards-summary"></span>
          </div>
          <button class="btn-success flex items-center gap-2" id="btn-write" onclick="window.__writePlanning()">
            <span class="material-symbols-outlined text-[20px]">save</span> Rezervasyon Oluştur & Yaz
          </button>
        </div>
      </div>
      <div class="flex flex-col gap-4" id="cards-list"></div>
    </div>
  `;

  if (!appStatus.licensed && appStatus.skipped) {
    const processButton = document.getElementById('btn-process');
    if (processButton) {
      processButton.innerHTML = '<span class="material-symbols-outlined text-[20px]">edit_document</span> Manuel Kartları Oluştur';
    }
  }
  consumeManualReviewQueue();
  loadContext();
  setupPaste();
}

function consumeManualReviewQueue() {
  const queueKey = 'irtifa_manual_review_queue';
  try {
    const queued = JSON.parse(localStorage.getItem(queueKey) || '[]');
    if (!Array.isArray(queued) || !queued.length) return;
    const existingIds = new Set(state.records.map(item => item.extraction_id).filter(Boolean));
    const additions = queued.filter(item => !existingIds.has(item.extraction_id));
    state.records.push(...additions);
    localStorage.removeItem(queueKey);
    if (additions.length) {
      renderCards();
      toast.info(
        'Manuel kontrol kayıtları hazır',
        `${additions.length} onaylı yolcu rezervasyona yazılmak üzere eklendi.`,
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

window.__clearFiles = function() {
  releaseObjectUrls();
  state.files = [];
  state.records = [];
  renderFileList();
  document.getElementById('cards-section').style.display = 'none';
};

function renderFileList() {
  const section = document.getElementById('file-section');
  const list = document.getElementById('file-list');
  section.style.display = state.files.length ? '' : 'none';

  if (!list) return;
  list.innerHTML = state.files.map((f, i) => `
    <div class="flex items-center gap-4 p-3 rounded-2xl bg-surface-light/30 hover:bg-surface-light transition-colors border border-white/5 group">
      <div class="bg-surface w-10 h-10 rounded-xl flex items-center justify-center border border-white/5">
        <span class="material-symbols-outlined text-primary">image</span>
      </div>
      <span class="truncate flex-1 text-on-surface font-medium">${esc(f.name)}</span>
      <span class="text-sm text-on-surface-variant/70 whitespace-nowrap bg-surface px-3 py-1 rounded-lg border border-white/5">${(f.size / 1024).toFixed(0)} KB</span>
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
    else document.getElementById('cards-section').style.display = 'none';
  }
  renderFileList();
};

window.__createManualCards = function() {
  if (!state.files.length) return;
  
  state.records = state.files.map((f, i) => ({
    source: f.name,
    nationality: '', sex: '', name: '', passport_no: '',
    green: false, flags: [],
    error: '',
    _source_file_index: i,
    _source_file_name: f.name,
    is_manual: true
  }));
  
  renderCards();
  toast.success('Manuel Giriş', `${state.records.length} adet manuel giriş kartı oluşturuldu.`);
};

// ─── Process ───
window.__processFiles = async function() {
  if (!state.files.length) return;
  if (!appStatus.licensed && appStatus.skipped) {
    window.__createManualCards();
    return;
  }
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
    text.textContent = `${state.files.length} fotoğraf gönderiliyor...`;

    const data = await api.upload('/api/passport/upload', state.files);
    let newRecords = data.records || data || [];

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
            `<button class="btn-ghost px-4 py-2 rounded-xl hover:bg-white/5 transition-colors text-on-surface-variant font-medium" onclick="window.__closeModal()">Kapat</button>
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

    state.records = newRecords;

    fill.style.width = '100%';
    text.textContent = `${state.records.length} pasaport işlendi`;

    renderCards();
    toast.success('İşlem tamamlandı',
      `${state.records.filter(r => r.green).length} yeşil, ${state.records.filter(r => !r.green).length} sarı`);
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
            `<button class="btn-ghost px-4 py-2 rounded-xl hover:bg-white/5 transition-colors text-on-surface-variant font-medium" onclick="window.__closeModal()">Kapat</button>
             <button class="btn-primary px-4 py-2 rounded-xl transition-colors font-medium" onclick="window.__closeModal(); window.__createManualCards()">Manuel Devam Et</button>`
        );
        return;
    }

    toast.error('İşlem hatası', err.message);
    // If API not available, create empty manual records
    state.records = state.files.map((f, i) => ({
      source: f.name,
      nationality: '', sex: '', name: '', passport_no: '',
      green: false, flags: ['unreadable'],
      error: 'API bağlantısı kurulamadı — elle doldurun',
      _source_file_index: i,
      _source_file_name: f.name,
    }));
    renderCards();
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="material-symbols-outlined text-[20px]">play_arrow</span> MRZ Oku';
    state.processing = false;
    setTimeout(() => { prog.style.display = 'none'; }, 2000);
  }
};

// ─── Control Cards ───
function renderCards() {
  const section = document.getElementById('cards-section');
  const list = document.getElementById('cards-list');
  const summary = document.getElementById('cards-summary');
  section.style.display = '';

  const greens = state.records.filter(r => r.green).length;
  const manuals = state.records.filter(r => r.is_manual).length;
  const total = state.records.length;
  const warnings = total - greens - manuals;
  summary.innerHTML = manuals > 0
    ? `<span class="text-info font-bold">${manuals} manuel</span> <span class="opacity-50">/</span> <span class="text-success font-bold">${greens} yeşil</span> <span class="opacity-50">/</span> <span class="text-warning font-bold">${warnings} sarı</span> <span class="opacity-50">—</span> toplam ${total}`
    : `<span class="text-success font-bold">${greens} yeşil</span> <span class="opacity-50">/</span> <span class="text-warning font-bold">${total - greens} sarı</span> <span class="opacity-50">—</span> toplam ${total}`;

  // PAX'ı veri içeren pasaport sayısına göre otomatik öner (kullanıcı değiştirmediyse)
  const dataCount = state.records.filter(r => r.name || r.passport_no).length || total;
  const paxEl = document.getElementById('pp-pax');
  if (paxEl && dataCount && (!paxEl.value || paxEl.dataset.auto !== 'off')) {
    paxEl.value = dataCount;
    paxEl.dataset.auto = 'on';
    paxEl.onchange = () => { paxEl.dataset.auto = 'off'; };
  }

  releaseObjectUrls();
  if (!list) return;
  list.innerHTML = state.records.map((rec, i) => {
    const isGreen = rec.green;
    const flags = (rec.flags || []).join(', ');

    // Try to create object URL for thumbnail
    let thumbHtml;
    const sourceFile = Number.isInteger(rec._source_file_index)
      ? state.files[rec._source_file_index]
      : state.files.find(f => f.name === rec._source_file_name);
    if (sourceFile) {
      const url = URL.createObjectURL(sourceFile);
      state.objectUrls.push(url);
      thumbHtml = `<img src="${url}" class="w-full md:w-32 h-32 object-cover rounded-2xl border border-white/5" alt="Passport ${i+1}" />`;
    } else {
      thumbHtml = `<div class="w-full md:w-32 h-32 bg-surface-light rounded-2xl border border-white/5 flex flex-col items-center justify-center text-on-surface-variant"><span class="material-symbols-outlined text-3xl mb-1 opacity-50">image</span><span class="text-[10px] text-center px-2 w-full truncate opacity-70">${esc(rec._source_file_name || rec.source || '')}</span></div>`;
    }

    return `
      <div class="glass-panel p-5 flex flex-col md:flex-row gap-5 relative animate-fade-in overflow-hidden" id="pcard-${i}">
        <!-- Status Indicator Edge -->
        <div class="absolute left-0 top-0 bottom-0 w-1.5 ${rec.is_manual ? 'bg-info shadow-[0_0_10px_rgba(56,189,248,0.5)]' : isGreen ? 'bg-success shadow-[0_0_10px_rgba(74,222,128,0.5)]' : 'bg-warning shadow-[0_0_10px_rgba(250,204,21,0.5)]'}"></div>

        <!-- Bu taramayı sil -->
        <button onclick="window.__removeCard(${i})" title="Bu taramayı sil" aria-label="Bu taramayı sil"
                class="absolute top-3 left-4 z-20 w-8 h-8 rounded-full flex items-center justify-center bg-surface/80 backdrop-blur border border-white/10 text-on-surface-variant hover:text-danger hover:bg-danger/20 hover:border-danger/30 transition-colors">
          <span class="material-symbols-outlined text-[18px]">close</span>
        </button>

        <div class="pl-1 flex flex-col md:flex-row gap-5 w-full">
          ${thumbHtml}
          
          <div class="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="flex flex-col gap-1">
              <label class="text-xs font-medium text-on-surface-variant ml-1">Uyruk (kod)</label>
              <input class="form-input font-mono text-sm uppercase" id="pc-nat-${i}" value="${esc(rec.nationality || '')}" placeholder="TUR, ITA..." />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-xs font-medium text-on-surface-variant ml-1">Cinsiyet</label>
              <select class="form-select text-sm py-[9px]" id="pc-sex-${i}">
                <option value="" ${!rec.sex ? 'selected' : ''}>—</option>
                <option value="M" ${rec.sex === 'M' ? 'selected' : ''}>Erkek</option>
                <option value="F" ${rec.sex === 'F' ? 'selected' : ''}>Kadın</option>
              </select>
            </div>
            <div class="flex flex-col gap-1 col-span-2">
              <label class="text-xs font-medium text-on-surface-variant ml-1">İsim</label>
              <input class="form-input text-sm uppercase" id="pc-name-${i}" value="${esc(rec.name || '')}" placeholder="AD SOYAD" />
            </div>
            <div class="flex flex-col gap-1 col-span-2 md:col-span-4">
              <label class="text-xs font-medium text-on-surface-variant ml-1">Pasaport No</label>
              <input class="form-input font-mono text-sm tracking-widest uppercase" id="pc-ppno-${i}" value="${esc(rec.passport_no || '')}" />
            </div>
          </div>
          
          <div class="md:w-56 flex flex-col border-t md:border-t-0 md:border-l border-white/5 pt-5 md:pt-0 md:pl-5 justify-between">
            <div class="w-full">
              <div class="font-medium text-sm flex items-center justify-end gap-1.5 mb-3 px-3 py-1.5 rounded-lg border ${rec.is_manual ? 'bg-info/10 text-info border-info/20' : isGreen ? 'bg-success/10 text-success border-success/20' : 'bg-warning/10 text-warning border-warning/20'}">
                <span class="material-symbols-outlined text-[18px]">${rec.is_manual ? 'edit_document' : isGreen ? 'check_circle' : 'warning'}</span> 
                ${rec.is_manual ? 'MANUEL GİRİŞ' : isGreen ? 'YEŞİL — DOĞRULANDI' : 'SARI — KONTROL ET'}
              </div>
              ${flags ? `<div class="flex flex-wrap justify-end gap-1.5 mb-2">${flags.split(', ').map(f => `<span class="bg-surface-light border border-white/5 text-on-surface-variant text-[11px] font-medium px-2 py-1 rounded-md uppercase tracking-wide">${esc(f)}</span>`).join('')}</div>` : ''}
              ${rec.error ? `<div class="text-[11px] text-danger font-medium mt-1 text-right bg-danger/10 px-2 py-1.5 rounded-md border border-danger/20">${esc(rec.error)}</div>` : ''}
            </div>
            
            <label class="flex items-center justify-center gap-2 mt-4 text-sm font-medium text-on-surface cursor-pointer hover:bg-primary/10 hover:text-primary transition-colors bg-surface-light/50 px-4 py-2.5 rounded-xl border border-white/5 w-full group select-none">
              <input type="checkbox" class="w-4 h-4 rounded border-white/10 bg-surface text-primary focus:ring-primary focus:ring-offset-surface group-hover:border-primary/50" id="pc-approve-${i}" ${(rec._approved !== undefined ? rec._approved : isGreen) ? 'checked' : ''} />
              Onayla ve Ekle
            </label>
            ${(!isGreen && !rec.is_manual) ? `<button class="btn-secondary w-full mt-2 flex items-center justify-center gap-2" onclick="window.__retryOcr(${i})"><span class="material-symbols-outlined text-sm">refresh</span> OCR ile Tekrar Tara</button>` : ''}
          </div>
        </div>
      </div>
    `;
  }).join('');

  // Her karttaki Uyruk alanına alpha-3 otomatik tamamlama bağla
  for (let i = 0; i < state.records.length; i++) {
    const el = document.getElementById(`pc-nat-${i}`);
    if (el) attachCombobox(el, () => state.countries);
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
    document.getElementById('cards-list').innerHTML = '';
    document.getElementById('cards-section').style.display = 'none';
    return;
  }
  renderCards();
};

// ─── Rezervasyon oluştur + kimlikleri yaz (pasaport girerken o an açılır) ───
window.__writePlanning = async function() {
  const sheet = document.getElementById('pp-sheet-select')?.value;
  if (!sheet) { toast.warning('Uçuş günü seçin'); return; }
  const existingMode = document.getElementById('pp-mode')?.value === 'existing';

  // Onaylı kartları topla + veri olup onaylanmamışları say (veri kaybı uyarısı)
  const approved = [];
  let skippedWithData = 0;
  for (let i = 0; i < state.records.length; i++) {
    const chk = document.getElementById(`pc-approve-${i}`);
    const card = {
      nationality: document.getElementById(`pc-nat-${i}`)?.value.trim().toUpperCase() || '',
      sex: document.getElementById(`pc-sex-${i}`)?.value.trim().toUpperCase() || '',
      name: document.getElementById(`pc-name-${i}`)?.value.trim().toUpperCase() || '',
      passport_no: document.getElementById(`pc-ppno-${i}`)?.value.trim() || '',
      extraction_id: state.records[i]?.extraction_id,
    };
    const hasData = card.name || card.passport_no;
    if (chk?.checked) approved.push(card);
    else if (hasData) skippedWithData++;
  }
  if (!approved.length) {
    toast.warning('Onaylı kart yok', 'En az bir kartı onaylayın');
    return;
  }
  // Veri içeren ama onaylanmamış kart varsa — sessizce kaybolmasın
  if (skippedWithData > 0) {
    if (!confirm(`⚠ ${skippedWithData} pasaportta veri var ama ONAYLI DEĞİL — yazılmayacak ve kaybolacak.\n\nÖnce o kart(lar)ın "Onayla" kutusunu işaretleyin. Yine de sadece ${approved.length} yolcuyu yazmak için devam edilsin mi?`)) return;
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
    if (!confirm(`PAX ${pax} ama ${approved.length} yolcu yazılacak. ${pax - approved.length} satır boş kalacak. Devam?`)) return;
  }

  const hotel = document.getElementById('pp-hotel')?.value.trim() || '';
  const agency = document.getElementById('pp-agency')?.value.trim() || '';
  const reserved_by = document.getElementById('pp-reserved')?.value.trim() || '';

  const btn = document.getElementById('btn-write');
  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined animate-spin text-[20px]">progress_activity</span> Oluşturuluyor...';

  try {
    let res;
    if (existingMode) {
      const leadRow = parseInt(document.getElementById('pp-existing-block')?.value, 10);
      if (!leadRow) throw new Error('Mevcut rezervasyon seçin.');
      res = await api.post('/api/planning/append-identities', {
        sheet, lead_row: leadRow, identities: approved, expected_revision: state.revision,
      });
      toast.success('Kimlikler eklendi', `${approved.length} yolcu mevcut rezervasyona yazıldı`);
    } else {
      res = await api.post('/api/planning/create-with-identities', {
        sheet, pax, hotel, agency, reserved_by, identities: approved,
        expected_revision: state.revision,
      });
      toast.success('Rezervasyon oluşturuldu', `${res.balloon} balonuna atandı — ${approved.length} yolcu yazıldı`);
    }

    // Temizle: bir sonraki rezervasyona hazır
    window.__clearFiles();
    const paxEl = document.getElementById('pp-pax');
    if (paxEl) { paxEl.value = ''; paxEl.dataset.auto = 'on'; }
    const hEl = document.getElementById('pp-hotel'); if (hEl) hEl.value = '';
    const aEl = document.getElementById('pp-agency'); if (aEl) aEl.value = '';
    const rEl = document.getElementById('pp-reserved'); if (rEl) rEl.value = '';
    await loadBlocks(sheet);
  } catch (err) {
    if (err.detail?.code === 'capacity_confirmation_required') {
      btn.disabled = false;
      resetWriteButtonLabel(existingMode);
      return showPassportCapacityChoice({
        sheet, pax, hotel, agency, reserved_by, identities: approved,
        expected_revision: state.revision,
      }, err.detail);
    }
    toast.error('Hata', err.message);
  } finally {
    btn.disabled = false;
    resetWriteButtonLabel(existingMode);
  }
};

function showPassportCapacityChoice(body, detail) {
  window.__pendingPassportOverflow = body;
  modal.open('Balon Kapasitesi Doldu', `
    <p class="text-on-surface-variant mb-4">Grup kapasite içinde hiçbir balona sığmıyor. Hedef balonu seçin.</p>
    <div class="space-y-2">${(detail.balloon_codes || []).map(code => `
      <label class="flex items-center justify-between rounded-lg border border-white/10 p-3 cursor-pointer">
        <span><input type="radio" name="pp-overflow-balloon" value="${esc(code)}" class="mr-3" />${esc(code)}</span>
        <strong>${detail.balloon_load?.[code] || 0}/${detail.capacity}</strong>
      </label>`).join('')}</div>
  `, `
    <button class="btn-secondary" onclick="window.__closeModal()">İptal</button>
    <button class="btn-primary" onclick="window.__confirmPassportOverflow()">Aşımı Onayla</button>
  `);
}

window.__confirmPassportOverflow = async function() {
  const balloon = document.querySelector('input[name="pp-overflow-balloon"]:checked')?.value;
  if (!balloon) return toast.warning('Hedef balonu seçin');
  const body = { ...(window.__pendingPassportOverflow || {}), requested_balloon: balloon, allow_overflow: true };
  try {
    const res = await api.post('/api/planning/create-with-identities', body);
    modal.close();
    toast.warning('Kapasite aşımı onaylandı', `${res.balloon} balonuna atandı`);
    window.__clearFiles();
    await loadBlocks(body.sheet);
  } catch (err) { toast.error('Rezervasyon oluşturulamadı', err.message); }
};

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function releaseObjectUrls() {
  for (const url of state.objectUrls) URL.revokeObjectURL(url);
  state.objectUrls = [];
}
