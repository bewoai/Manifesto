/* ═══════════════════════════════════════════════════════════════════
   Pasaport Tarama — Drag & drop, MRZ okuma, kontrol kartları
   Brief §8: sol görsel, sağ 4 alan, yeşil/sarı status
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, renderHeader } from '/app.js';
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
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-on-surface-variant ml-1">Uçuş Günü</label>
          <select class="form-select" id="pp-sheet-select">
            <option value="">Yükleniyor...</option>
          </select>
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-on-surface-variant ml-1">PAX (kişi sayısı)</label>
          <input class="form-input" id="pp-pax" type="number" min="1" max="28" />
          <div class="text-xs text-on-surface-variant/70 mt-1 ml-1">Bu rezervasyondaki kişi sayısı — pasaport sayısına göre otomatik gelir, değiştirebilirsin.</div>
        </div>
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-on-surface-variant ml-1">Otel</label>
          <input class="form-input" id="pp-hotel" list="dl-pp-hotel" placeholder="ör. ARGOS" />
          <datalist id="dl-pp-hotel"></datalist>
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-on-surface-variant ml-1">Acente</label>
          <input class="form-input" id="pp-agency" placeholder="ör. BEDEL TURIZM" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium text-on-surface-variant ml-1">Rezerve Yapan</label>
          <input class="form-input" id="pp-reserved" placeholder="ör. MAHMUT" />
        </div>
      </div>
      
      <div class="mt-6 text-xs text-on-surface-variant bg-primary/5 border border-primary/10 p-4 rounded-2xl flex items-start gap-3">
        <span class="material-symbols-outlined text-primary text-[20px]">info</span>
        <div class="leading-relaxed">Balon PAX'a göre <strong class="text-primary font-semibold">otomatik atanır</strong>. Kaptan ve pickup saati en son (rota belli olunca) Planlama'dan girilir.</div>
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
      <input type="file" id="file-input" multiple accept="image/*" style="display:none"
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
          <button class="btn-primary flex items-center gap-2" id="btn-process" onclick="window.__processFiles()">
            <span class="material-symbols-outlined text-[20px]">play_arrow</span> MRZ Oku
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

  loadContext();
  setupPaste();
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
    sel.innerHTML = state.sheets.length
      ? state.sheets.map(s => `<option value="${s}">${s}</option>`).join('')
      : '<option value="">Sayfa yok</option>';
    if (state.sheets.length) sel.value = state.sheets[state.sheets.length - 1];
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
  for (const f of fileList) {
    if (f.type.startsWith('image/')) state.files.push(f);
  }
  renderFileList();
}

window.__clearFiles = function() {
  state.files = [];
  state.records = [];
  renderFileList();
  document.getElementById('cards-section').style.display = 'none';
};

function renderFileList() {
  const section = document.getElementById('file-section');
  const list = document.getElementById('file-list');
  section.style.display = state.files.length ? '' : 'none';

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
  state.files.splice(i, 1);
  renderFileList();
};

// ─── Process ───
window.__processFiles = async function() {
  if (!state.files.length) return;
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
    state.records = data.records || data || [];

    fill.style.width = '100%';
    text.textContent = `${state.records.length} pasaport işlendi`;

    renderCards();
    toast.success('İşlem tamamlandı',
      `${state.records.filter(r => r.green).length} yeşil, ${state.records.filter(r => !r.green).length} sarı`);
  } catch (err) {
    toast.error('İşlem hatası', err.message);
    // If API not available, create empty manual records
    state.records = state.files.map((f, i) => ({
      source: f.name,
      nationality: '', sex: '', name: '', passport_no: '',
      green: false, flags: ['unreadable'],
      error: 'API bağlantısı kurulamadı — elle doldurun',
      _fileIndex: i,
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
  const total = state.records.length;
  summary.innerHTML = `<span class="text-success font-bold">${greens} yeşil</span> <span class="opacity-50">/</span> <span class="text-warning font-bold">${total - greens} sarı</span> <span class="opacity-50">—</span> toplam ${total}`;

  // PAX'ı veri içeren pasaport sayısına göre otomatik öner (kullanıcı değiştirmediyse)
  const dataCount = state.records.filter(r => r.name || r.passport_no).length || total;
  const paxEl = document.getElementById('pp-pax');
  if (paxEl && dataCount && (!paxEl.value || paxEl.dataset.auto !== 'off')) {
    paxEl.value = dataCount;
    paxEl.dataset.auto = 'on';
    paxEl.onchange = () => { paxEl.dataset.auto = 'off'; };
  }

  list.innerHTML = state.records.map((rec, i) => {
    const isGreen = rec.green;
    const flags = (rec.flags || []).join(', ');

    // Try to create object URL for thumbnail
    let thumbHtml;
    if (state.files[i]) {
      const url = URL.createObjectURL(state.files[i]);
      thumbHtml = `<img src="${url}" class="w-full md:w-32 h-32 object-cover rounded-2xl border border-white/5" alt="Passport ${i+1}" />`;
    } else {
      thumbHtml = `<div class="w-full md:w-32 h-32 bg-surface-light rounded-2xl border border-white/5 flex flex-col items-center justify-center text-on-surface-variant"><span class="material-symbols-outlined text-3xl mb-1 opacity-50">image</span><span class="text-[10px] text-center px-2 w-full truncate opacity-70">${esc(rec.source || '')}</span></div>`;
    }

    return `
      <div class="glass-panel p-5 flex flex-col md:flex-row gap-5 relative animate-fade-in overflow-hidden" id="pcard-${i}">
        <!-- Status Indicator Edge -->
        <div class="absolute left-0 top-0 bottom-0 w-1.5 ${isGreen ? 'bg-success' : 'bg-warning'} shadow-[0_0_10px_rgba(${isGreen ? '74,222,128' : '250,204,21'},0.5)]"></div>
        
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
              <div class="font-medium text-sm flex items-center justify-end gap-1.5 mb-3 px-3 py-1.5 rounded-lg border ${isGreen ? 'bg-success/10 text-success border-success/20' : 'bg-warning/10 text-warning border-warning/20'}">
                <span class="material-symbols-outlined text-[18px]">${isGreen ? 'check_circle' : 'warning'}</span> 
                ${isGreen ? 'YEŞİL — DOĞRULANDI' : 'SARI — KONTROL ET'}
              </div>
              ${flags ? `<div class="flex flex-wrap justify-end gap-1.5 mb-2">${flags.split(', ').map(f => `<span class="bg-surface-light border border-white/5 text-on-surface-variant text-[11px] font-medium px-2 py-1 rounded-md uppercase tracking-wide">${f}</span>`).join('')}</div>` : ''}
              ${rec.error ? `<div class="text-[11px] text-danger font-medium mt-1 text-right bg-danger/10 px-2 py-1.5 rounded-md border border-danger/20">${esc(rec.error)}</div>` : ''}
            </div>
            
            <label class="flex items-center justify-center gap-2 mt-4 text-sm font-medium text-on-surface cursor-pointer hover:bg-primary/10 hover:text-primary transition-colors bg-surface-light/50 px-4 py-2.5 rounded-xl border border-white/5 w-full group select-none">
              <input type="checkbox" class="w-4 h-4 rounded border-white/10 bg-surface text-primary focus:ring-primary focus:ring-offset-surface group-hover:border-primary/50" id="pc-approve-${i}" ${(isGreen || rec.name || rec.passport_no) ? 'checked' : ''} />
              Onayla ve Ekle
            </label>
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

// ─── Rezervasyon oluştur + kimlikleri yaz (pasaport girerken o an açılır) ───
window.__writePlanning = async function() {
  const sheet = document.getElementById('pp-sheet-select')?.value;
  if (!sheet) { toast.warning('Uçuş günü seçin'); return; }

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
  let pax = parseInt(document.getElementById('pp-pax')?.value, 10);
  if (!pax || pax < 1) pax = approved.length;
  if (pax > 28) { toast.warning('PAX en fazla 28'); return; }
  // PAX onaylı yolcu sayısından az ise otomatik yükselt (pasaport kaybolmasın)
  if (approved.length > pax) {
    pax = approved.length;
    toast.info('PAX güncellendi', `PAX ${pax} olarak ayarlandı (${approved.length} onaylı yolcu)`);
  }
  // PAX, yazılacak yolcudan fazlaysa: boş satırlar kalır — operatöre bildir
  if (pax > approved.length) {
    if (!confirm(`PAX ${pax} ama ${approved.length} yolcu yazılacak. ${pax - approved.length} satır boş kalacak. Devam?`)) return;
  }

  const hotel = document.getElementById('pp-hotel')?.value.trim() || '';
  const agency = document.getElementById('pp-agency')?.value.trim() || '';
  const reserved_by = document.getElementById('pp-reserved')?.value.trim() || '';

  const btn = document.getElementById('btn-write');
  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined animate-spin text-[20px]">progress_activity</span> Oluşturuluyor...';

  try {
    // 1) Rezervasyonu oluştur (balon otomatik atanır)
    const res = await api.post('/api/planning/create-block', { sheet, pax, hotel, agency, reserved_by });

    // 2) Onaylı kimlikleri bloğun satırlarına yaz
    const updates = {};
    for (let i = 0; i < approved.length && i < res.rows.length; i++) {
      updates[res.rows[i]] = approved[i];
    }
    await api.post('/api/planning/write-identity', { sheet, updates });

    const msg = `${res.balloon} balonuna atandı (${(res.load?.[res.balloon]) ?? pax}/${res.capacity}) — ${approved.length} yolcu yazıldı`;
    if (res.overflow) toast.warning('Rezervasyon açıldı (taşma)', msg);
    else toast.success('Rezervasyon oluşturuldu', msg);

    // Temizle: bir sonraki rezervasyona hazır
    window.__clearFiles();
    const paxEl = document.getElementById('pp-pax');
    if (paxEl) { paxEl.value = ''; paxEl.dataset.auto = 'on'; }
    const hEl = document.getElementById('pp-hotel'); if (hEl) hEl.value = '';
    const aEl = document.getElementById('pp-agency'); if (aEl) aEl.value = '';
    const rEl = document.getElementById('pp-reserved'); if (rEl) rEl.value = '';
  } catch (err) {
    toast.error('Hata', err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="material-symbols-outlined text-[20px]">save</span> Rezervasyon Oluştur & Yaz';
  }
};

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
