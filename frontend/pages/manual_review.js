/* ═══════════════════════════════════════════════════════════════════
   Manuel Kontrol (Manual Review) — Review UI for low confidence AI extractions
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, renderHeader, modal } from '/app.js';
import { attachCombobox } from '/combobox.js';
import { KIND_LABELS } from '/list_marks.js';

let state = {
  items: [],
  loading: true,
  countries: [],
  selected: new Set(),
};

function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export async function render(container) {
  renderHeader('Manuel Kontrol', 'Yapay zeka tarafından düşük güven skorlu olarak işaretlenen kimlik ve pasaportları doğrulayın');

  container.innerHTML = `
    <div id="manual-review-content">
      <div class="flex justify-center p-12">
        <div class="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
      </div>
    </div>
  `;

  await loadData();
  const content = document.getElementById('manual-review-content');
  if (content) renderContent(content); // kullanıcı bu arada başka sayfaya geçtiyse çizme
}

async function loadData() {
  state.loading = true;
  state.error = null;
  try {
    // Ülke listesi yalnız öneri içindir; o düşerse kuyruk yine gösterilir.
    const [reviewRes, countriesRes] = await Promise.allSettled([
      api.get('/api/passport/manual-review'),
      api.get('/api/countries')
    ]);
    if (reviewRes.status === 'fulfilled') {
      state.items = reviewRes.value.items || [];
      const live = new Set(state.items.map(i => i.id));
      state.selected = new Set([...state.selected].filter(id => live.has(id)));
    } else {
      state.items = [];
      state.error = reviewRes.reason?.message || 'Bilinmeyen hata';
      toast.error('Veri alınamadı', state.error);
    }
    state.countries = countriesRes.status === 'fulfilled' ? (countriesRes.value.countries || []) : [];
  } finally {
    state.loading = false;
  }
}

window.__reloadManualReview = async function() {
  const container = document.getElementById('manual-review-content');
  if (!container) return;
  container.innerHTML = `
    <div class="flex justify-center p-12">
      <div class="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
    </div>`;
  await loadData();
  const current = document.getElementById('manual-review-content');
  if (current) renderContent(current);
};

function renderContent(container) {
  if (state.loading) return;

  // Veri çekilemediyse "bekleyen yok" demek yanıltıcı olur → ayrı hata durumu
  if (state.error) {
    container.innerHTML = `
      <div class="empty-state glass-panel rounded-xl p-12">
        <div class="empty-icon material-symbols-outlined text-danger">cloud_off</div>
        <div class="empty-title">Manuel kontrol listesi alınamadı</div>
        <div class="empty-desc">${esc(state.error)}</div>
        <div class="empty-desc mt-1">Bekleyen kayıt olabilir; liste yüklenene kadar pasaportları onaylı saymayın.</div>
        <button class="btn-secondary mt-6" onclick="window.__reloadManualReview()">
          <span class="material-symbols-outlined text-[18px] align-middle">refresh</span> Tekrar dene
        </button>
      </div>
    `;
    return;
  }

  if (state.items.length === 0) {
    container.innerHTML = `
      <div class="empty-state glass-panel rounded-xl p-12">
        <div class="empty-icon material-symbols-outlined text-success">task_alt</div>
        <div class="empty-title">Bekleyen Kontrol Yok</div>
        <div class="empty-desc">Harika! Şu anda manuel kontrole düşen hiçbir kimlik bulunmuyor.</div>
      </div>
    `;
    return;
  }

  const itemsHtml = state.items.map((item, index) => {
    return `
      <div class="glass-panel rounded-xl p-6 mb-6 animate-fade-in" style="animation-delay: ${index * 50}ms" id="review-item-${item.id}">
        <div class="flex flex-col xl:flex-row gap-6">
          <!-- Sol Görsel -->
          <div class="xl:w-[400px] flex-shrink-0">
            <div class="bg-well rounded-2xl overflow-hidden border border-line relative group h-full min-h-[250px] flex items-center justify-center cursor-zoom-in"
                 onclick="window.__openImageModal('/api/passport/image/${item.id}')">
              <img src="/api/passport/image/${item.id}" class="w-full h-full object-contain max-h-[400px]" alt="Belge Görseli" onerror="this.outerHTML='<div class=\\'text-on-surface-variant\\'>Görsel Yüklenemedi</div>'" />
              <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <span class="material-symbols-outlined text-white text-3xl">zoom_in</span>
              </div>
            </div>
          </div>
          
          <!-- Sağ Form -->
          <div class="flex-1 flex flex-col justify-between">
            <div>
              <div class="flex flex-wrap items-center gap-3 mb-4">
                <label class="checkbox-label !text-on-surface" title="Toplu kaldırma için seç">
                  <input type="checkbox" class="mr-select" data-id="${item.id}" ${state.selected.has(item.id) ? 'checked' : ''}
                         onchange="window.__mrToggle(${item.id}, this.checked)" aria-label="Bu kaydı seç" />
                </label>
                <span class="material-symbols-outlined text-warning">warning</span>
                <h3 class="text-lg font-semibold text-on-surface">Kontrol Gerekli</h3>
                <span class="text-sm px-2 py-1 bg-surface-light rounded-md border border-line font-mono text-on-surface-variant">
                  ${esc(item.fallback_reason || 'Düşük Güven Skoru')}
                </span>
                ${sourceChipsHtml(item)}
                <span class="text-sm px-2 py-1 bg-primary/20 text-primary rounded-md border border-primary/20 ml-auto font-medium">
                  Güven: ${Math.round(Number(item.confidence_score || 0) * 100)}%
                </span>
              </div>
              
              <div class="grid grid-cols-2 gap-4 mb-6">
                <!-- Uyruk -->
                <div class="form-group">
                  <label class="form-label">Uyruk</label>
                  <input type="text" class="form-input font-mono uppercase tracking-widest" id="nat-${item.id}" value="${esc(item.nationality || '')}" placeholder="TUR" maxlength="3" />
                </div>
                <!-- Cinsiyet -->
                <div class="form-group">
                  <label class="form-label">Cinsiyet</label>
                  <select class="form-select font-mono" id="sex-${item.id}">
                    <option value="M" ${item.sex === 'M' ? 'selected' : ''}>M - Erkek</option>
                    <option value="F" ${item.sex === 'F' ? 'selected' : ''}>F - Kadın</option>
                    <option value="X" ${!['M','F'].includes(item.sex) ? 'selected' : ''}>X - Belirsiz</option>
                  </select>
                </div>
                <!-- İsim -->
                <div class="form-group col-span-2">
                  <label class="form-label">İsim Soyisim</label>
                  <input type="text" class="form-input font-mono uppercase tracking-wide" id="name-${item.id}" value="${esc(item.name || '')}" placeholder="ÖR. AHMET YILMAZ" />
                </div>
                <!-- Pasaport No -->
                <div class="form-group col-span-2">
                  <label class="form-label">Pasaport / Kimlik No</label>
                  <input type="text" class="form-input font-mono uppercase tracking-wider" id="pass-${item.id}" value="${esc(item.document_number || '')}" placeholder="A1234567" />
                </div>
              </div>
            </div>
            
            <div class="flex items-center gap-3 pt-4 border-t border-line">
              <button class="btn-primary flex-1 py-3" onclick="window.__resolveManualReview(${item.id}, 'approve')">
                <span class="material-symbols-outlined">check</span>
                Onayla & Kaydet
              </button>
              <button class="btn-secondary py-3 text-danger hover:bg-danger/10 border-danger/20" onclick="window.__resolveManualReview(${item.id}, 'reject')">
                <span class="material-symbols-outlined">delete</span>
                Reddet
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = `
    <div class="glass-panel rounded-xl px-5 py-3 mb-6 flex flex-wrap items-center gap-3 sticky top-20 z-20" role="toolbar" aria-label="Toplu işlemler">
      <label class="checkbox-label !text-on-surface">
        <input type="checkbox" id="mr-select-all" onchange="window.__mrSelectAll(this.checked)" aria-label="Tümünü seç" />
        <span><strong>${state.items.length}</strong> kayıt kontrol bekliyor</span>
      </label>
      <span class="text-sm text-on-surface-variant" id="mr-selected-count"></span>
      <div class="ml-auto flex flex-wrap gap-2">
        <button class="btn-secondary btn-sm" id="mr-dismiss-selected" onclick="window.__mrDismiss(false)" disabled>
          <span class="material-symbols-outlined text-[18px]">delete</span> Seçilenleri kaldır
        </button>
        <button class="btn-danger btn-sm" onclick="window.__mrDismiss(true)">
          <span class="material-symbols-outlined text-[18px]">delete_sweep</span> Tümünü kaldır
        </button>
      </div>
    </div>
    ${itemsHtml}
  `;
  syncSelectionUi();

  // Uyruk alanı yalnız combobox ile tamamlanır (datalist ile çift öneri paneli açılıyordu)
  const countryOptions = state.countries.map(c => ({ value: c.code, label: `${c.code} — ${c.name}` }));
  state.items.forEach(item => {
    const el = document.getElementById(`nat-${item.id}`);
    if (el) attachCombobox(el, () => countryOptions);
  });
}

// Kaynak türü rozeti + listedeki ham işaret çipi (API: source_kind, annotation, document_type)
function sourceChipsHtml(item) {
  const chips = [];
  const kind = item.source_kind_label || KIND_LABELS[item.source_kind] || '';
  if (kind) chips.push(`<span class="src-chip" title="Kaynak türü">${esc(kind)}</span>`);
  const doc = String(item.document_type || '').toUpperCase();
  if (doc === 'P' || doc === 'I') chips.push(`<span class="src-chip" title="Belge türü">${doc === 'P' ? 'Pasaport' : 'Kimlik'}</span>`);
  if (item.annotation) chips.push(`<span class="mark-chip" title="Listedeki ham işaret">${esc(item.annotation)}</span>`);
  return chips.join('');
}

window.__openImageModal = function(url) {
  modal.open('Belge Detayı', `
    <div class="flex justify-center p-4">
      <img src="${url}" class="max-w-full max-h-[70vh] rounded-xl" />
    </div>
  `);
};

window.__resolveManualReview = async function(id, action) {
  const container = document.getElementById(`review-item-${id}`);
  
  let corrected_data = null;
  if (action === 'approve') {
    corrected_data = {
      nationality: document.getElementById(`nat-${id}`).value.toUpperCase(),
      sex: document.getElementById(`sex-${id}`).value,
      name: document.getElementById(`name-${id}`).value.toUpperCase(),
      document_number: document.getElementById(`pass-${id}`).value.toUpperCase(),
    };
    
    if (!corrected_data.nationality || !corrected_data.name || !corrected_data.document_number) {
      toast.warning('Eksik Bilgi', 'Onaylamak için zorunlu alanları doldurun.');
      return;
    }
  } else if (action === 'reject') {
    const item = state.items.find(i => i.id === id) || {};
    const name = document.getElementById(`name-${id}`)?.value || item.name || '';
    const docNo = document.getElementById(`pass-${id}`)?.value || item.document_number || '';
    const ok = await modal.confirm({
      title: 'Kayıt reddedilsin mi?',
      bodyHtml: `
        <p class="text-on-surface mb-2">Bu belge manuel kontrol listesinden çıkarılacak ve <strong>planlamaya yazılmayacak</strong>.</p>
        <p class="text-sm text-on-surface-variant">${esc(name || '(isimsiz)')} <span class="font-mono">${esc(docNo || '—')}</span></p>
        <p class="text-sm text-on-surface-variant mt-2">Yolcu gerçekse pasaportu yeniden tarayın veya Pasaport ekranında manuel kart oluşturun.</p>`,
      confirmLabel: 'Reddet',
      cancelLabel: 'Vazgeç',
      tone: 'danger',
    });
    if (!ok) return;
  }
  if (!container) return;

  container.style.opacity = '0.5';
  container.style.pointerEvents = 'none';

  try {
    const response = await api.post(
      '/api/passport/manual-review/resolve',
      { id, action, corrected_data },
    );
    if (action === 'approve' && response.record) {
      const queueKey = 'irtifa_manual_review_queue';
      const queue = JSON.parse(localStorage.getItem(queueKey) || '[]');
      if (!queue.some(item => item.extraction_id === response.record.extraction_id)) {
        queue.push({ ...response.record, _approved: true });
        localStorage.setItem(queueKey, JSON.stringify(queue));
      }
      toast.success(
        'Onaylandı',
        'Kayıt Pasaport ekranındaki rezervasyona yazma kuyruğuna eklendi.',
      );
    } else {
      toast.success('Reddedildi', 'Kayıt manuel kontrol listesinden çıkarıldı.');
    }
    
    // Animasyonlu sil
    container.style.transform = 'scale(0.95)';
    container.style.opacity = '0';
    setTimeout(() => {
      state.items = state.items.filter(i => i.id !== id);
      const content = document.getElementById('manual-review-content');
      if (content) renderContent(content);
    }, 300);
  } catch (err) {
    container.style.opacity = '1';
    container.style.pointerEvents = 'auto';
    toast.error('Hata', err.message);
  }
};


// ─── Toplu kaldırma ───
function syncSelectionUi() {
  const n = state.selected.size;
  const btn = document.getElementById('mr-dismiss-selected');
  if (btn) btn.disabled = n === 0;
  const label = document.getElementById('mr-selected-count');
  if (label) label.textContent = n ? `${n} seçili` : '';
  const all = document.getElementById('mr-select-all');
  if (all) {
    all.checked = n > 0 && n === state.items.length;
    all.indeterminate = n > 0 && n < state.items.length;
  }
}

window.__mrToggle = function(id, on) {
  if (on) state.selected.add(id); else state.selected.delete(id);
  syncSelectionUi();
};

window.__mrSelectAll = function(on) {
  state.selected = on ? new Set(state.items.map(i => i.id)) : new Set();
  document.querySelectorAll('.mr-select').forEach(el => { el.checked = on; });
  syncSelectionUi();
};

window.__mrDismiss = async function(all) {
  const ids = all ? state.items.map(i => i.id) : [...state.selected];
  if (!ids.length) return;
  const ok = await modal.confirm({
    title: all ? `${ids.length} kaydın tümü kaldırılsın mı?` : `${ids.length} kayıt kaldırılsın mı?`,
    bodyHtml: `
      <p class="text-on-surface mb-2">Kayıtlar manuel kontrol listesinden çıkarılır ve <strong>planlamaya yazılmaz</strong>. Excel dosyasına dokunulmaz.</p>
      <p class="text-sm text-on-surface-variant">Başka bir kaydın kullanmadığı görseller de bilgisayardan silinir. Gerçek bir yolcu varsa pasaportu yeniden taramanız gerekir.</p>`,
    confirmLabel: all ? 'Tümünü kaldır' : 'Kaldır',
    cancelLabel: 'Vazgeç',
    tone: 'danger',
  });
  if (!ok) return;
  try {
    const res = await api.post('/api/passport/manual-review/dismiss', all ? { all: true } : { ids });
    toast.success(`${res.dismissed} kayıt kaldırıldı`, res.removed_files ? `${res.removed_files} görsel silindi` : '');
    state.selected = new Set();
    await window.__reloadManualReview();
  } catch (err) {
    toast.error('Kaldırılamadı', err.message);
  }
};
