/* ═══════════════════════════════════════════════════════════════════
   Manuel Kontrol (Manual Review) — Review UI for low confidence AI extractions
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, renderHeader, modal } from '/app.js';
import { attachCombobox } from '/combobox.js';

let state = {
  items: [],
  loading: true,
  countries: [],
};

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
  renderContent(document.getElementById('manual-review-content'));
}

async function loadData() {
  state.loading = true;
  try {
    const [reviewRes, countriesRes] = await Promise.all([
      api.get('/api/passport/manual-review'),
      api.get('/api/countries')
    ]);
    state.items = reviewRes.items || [];
    state.countries = countriesRes.countries || [];
  } catch (err) {
    toast.error('Veri alınamadı', err.message);
  } finally {
    state.loading = false;
  }
}

function renderContent(container) {
  if (state.loading) return;

  if (state.items.length === 0) {
    container.innerHTML = `
      <div class="empty-state glass-panel rounded-[40px] p-12">
        <div class="empty-icon text-green-400">task_alt</div>
        <div class="empty-title">Bekleyen Kontrol Yok</div>
        <div class="empty-desc">Harika! Şu anda manuel kontrole düşen hiçbir kimlik bulunmuyor.</div>
      </div>
    `;
    return;
  }

  const itemsHtml = state.items.map((item, index) => {
    return `
      <div class="glass-panel rounded-[30px] p-6 mb-6 animate-fade-in" style="animation-delay: ${index * 50}ms" id="review-item-${item.id}">
        <div class="flex flex-col xl:flex-row gap-6">
          <!-- Sol Görsel -->
          <div class="xl:w-[400px] flex-shrink-0">
            <div class="bg-black/20 rounded-2xl overflow-hidden border border-white/10 relative group h-full min-h-[250px] flex items-center justify-center cursor-zoom-in"
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
              <div class="flex items-center gap-3 mb-4">
                <span class="material-symbols-outlined text-yellow-400">warning</span>
                <h3 class="text-lg font-semibold text-on-surface">Kontrol Gerekli</h3>
                <span class="text-sm px-2 py-1 bg-surface-light rounded-md border border-white/5 font-mono text-on-surface-variant">
                  ${item.fallback_reason || 'Düşük Güven Skoru'}
                </span>
                <span class="text-sm px-2 py-1 bg-primary/20 text-primary rounded-md border border-primary/20 ml-auto font-medium">
                  Güven: ${Math.round(item.confidence_score * 100)}%
                </span>
              </div>
              
              <div class="grid grid-cols-2 gap-4 mb-6">
                <!-- Uyruk -->
                <div class="form-group">
                  <label class="form-label">Uyruk</label>
                  <input type="text" class="form-input font-mono uppercase tracking-widest" id="nat-${item.id}" value="${item.nationality || ''}" list="dl-nat-${item.id}" placeholder="TUR" maxlength="3" />
                  <datalist id="dl-nat-${item.id}">
                    ${state.countries.map(c => `<option value="${c.code}">${c.name}</option>`).join('')}
                  </datalist>
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
                  <input type="text" class="form-input font-mono uppercase tracking-wide" id="name-${item.id}" value="${item.name || ''}" placeholder="ÖR. AHMET YILMAZ" />
                </div>
                <!-- Pasaport No -->
                <div class="form-group col-span-2">
                  <label class="form-label">Pasaport / Kimlik No</label>
                  <input type="text" class="form-input font-mono uppercase tracking-wider" id="pass-${item.id}" value="${item.document_number || ''}" placeholder="A1234567" />
                </div>
              </div>
            </div>
            
            <div class="flex items-center gap-3 pt-4 border-t border-white/5">
              <button class="btn-primary flex-1 py-3" onclick="window.__resolveManualReview(${item.id}, 'approve')">
                <span class="material-symbols-outlined">check</span>
                Onayla & Kaydet
              </button>
              <button class="btn-secondary py-3 text-red-400 hover:text-red-300 hover:bg-red-400/10 border-red-400/20" onclick="window.__resolveManualReview(${item.id}, 'reject')">
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
    <div class="flex justify-between items-end mb-6">
      <div class="text-on-surface-variant text-sm">
        Bekleyen <strong class="text-on-surface">${state.items.length}</strong> belge bulundu.
      </div>
    </div>
    ${itemsHtml}
  `;

  // Attach comboboxes
  setTimeout(() => {
    state.items.forEach(item => {
      const el = document.getElementById(`nat-${item.id}`);
      if (el) attachCombobox(el, state.countries.map(c => ({ value: c.code, label: `${c.code} — ${c.name}` })));
    });
  }, 50);
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
  }

  container.style.opacity = '0.5';
  container.style.pointerEvents = 'none';

  try {
    await api.post('/api/passport/manual-review/resolve', { id, action, corrected_data });
    toast.success(action === 'approve' ? 'Onaylandı' : 'Reddedildi', 'Kayıt başarıyla güncellendi.');
    
    // Animasyonlu sil
    container.style.transform = 'scale(0.95)';
    container.style.opacity = '0';
    setTimeout(() => {
      state.items = state.items.filter(i => i.id !== id);
      renderContent(document.getElementById('manual-review-content'));
    }, 300);
  } catch (err) {
    container.style.opacity = '1';
    container.style.pointerEvents = 'auto';
    toast.error('Hata', err.message);
  }
};
