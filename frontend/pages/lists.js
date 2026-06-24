/* ═══════════════════════════════════════════════════════════════════
   Listeler — Kalıcı referans verisi (balon kodları, otel, şoför, acente,
   pilot, geleceği yer). Ekle / sil; rezervasyon & pasaport formlarında öneri.
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, renderHeader } from '/app.js';

let state = { balloons: [], capacity: 28, options: {} };

// kategori anahtarı → başlık / ikon / yer tutucu
const CATEGORIES = [
  { key: 'balloon',      title: 'Balon Kodları',      icon: 'air', ph: 'ör. BYF' },
  { key: 'hotel',        title: 'Oteller',            icon: 'hotel', ph: 'ör. ARGOS' },
  { key: 'driver',       title: 'Şoförler / Kaptanlar', icon: 'airport_shuttle', ph: 'ör. AHMET' },
  { key: 'agency',       title: 'Acenteler',          icon: 'domain', ph: 'ör. BEDEL TURIZM' },
  { key: 'pilot',        title: 'Pilotlar',           icon: 'flight', ph: 'ör. GAMZE' },
  { key: 'reserved_by',  title: 'Rezerve Yapanlar',   icon: 'person', ph: 'ör. MAHMUT' },
  { key: 'coming_place', title: 'Geleceği Yer',       icon: 'place', ph: 'ör. DİREKT ALAN' },
];

export async function render(container) {
  renderHeader('Listeler', 'Tekrar eden verileri kaydet — formlarda öneri olarak çıkar');
  container.innerHTML = `
    <div id="lists-root" class="max-w-[860px] mx-auto flex flex-col gap-6 pb-12 w-full">
      <div class="glass-panel p-6 rounded-3xl flex items-center justify-between animate-in">
        <div>
          <h3 class="text-on-surface font-medium text-lg mb-1">Mevcut Excel'den Listeleri Doldur</h3>
          <p class="text-on-surface-variant text-sm">Excel dosyanızdaki geçmiş tüm operasyon günlerini tarayarak acente, otel ve diğer listeleri otomatik doldurur.</p>
        </div>
        <button class="btn-primary flex items-center gap-2 whitespace-nowrap" id="btn-scan-lists" onclick="window.__scanLists()">
          <span class="material-symbols-outlined">radar</span>
          Otomatik Tara
        </button>
      </div>
      <div id="lists-cards" class="flex flex-col gap-6"></div>
    </div>
  `;
  await load();
}

async function load() {
  try {
    const data = await api.get('/api/lists');
    state.balloons = data.balloons || [];
    state.capacity = data.capacity || 28;
    state.options = data.options || {};
    renderCards();
  } catch (err) {
    toast.error('Listeler yüklenemedi', err.message);
  }
}

function valuesFor(key) {
  return key === 'balloon' ? state.balloons : (state.options[key] || []);
}

function renderCards() {
  const root = document.getElementById('lists-cards');
  if (!root) return;
  root.innerHTML = CATEGORIES.map(cat => {
    const values = valuesFor(cat.key);
    const sub = cat.key === 'balloon'
      ? `<span class="text-sm text-on-surface-variant font-medium">Kapasite ${state.capacity}/balon • ${values.length} balon</span>`
      : `<span class="text-sm text-on-surface-variant font-medium">${values.length} kayıt</span>`;
    
    const chips = values.length
      ? values.map(v => `
          <span class="badge badge-amber flex items-center gap-1.5 m-1 py-1 px-3">
            ${esc(v)}
            <button title="Sil" onclick="window.__listDel('${cat.key}', this)" data-val="${esc(v)}"
                    class="opacity-70 hover:opacity-100 hover:text-red-400 transition-opacity flex items-center outline-none cursor-pointer">
              <span class="material-symbols-outlined text-[16px]">close</span>
            </button>
          </span>`).join('')
      : `<span class="text-sm text-on-surface-variant/50 italic px-2">Henüz kayıt yok</span>`;

    return `
      <div class="glass-panel rounded-3xl p-6 flex flex-col gap-5 animate-in">
        <div class="flex items-center justify-between border-b border-white/5 pb-3">
          <div class="flex items-center gap-3">
            <span class="material-symbols-outlined text-primary text-[28px]">${cat.icon}</span>
            <h2 class="font-headline text-headline-sm text-on-surface m-0">${cat.title}</h2>
          </div>
          ${sub}
        </div>
        
        <div class="flex flex-wrap -m-1" id="chips-${cat.key}">
          ${chips}
        </div>
        
        <div class="flex gap-3 mt-2">
          <input class="form-input flex-1" id="add-${cat.key}" placeholder="${cat.ph}"
                 onkeydown="if(event.key==='Enter'){window.__listAdd('${cat.key}')}" />
          <button class="btn-primary flex items-center gap-2" onclick="window.__listAdd('${cat.key}')">
            <span class="material-symbols-outlined text-[20px]">add</span>
            <span>Ekle</span>
          </button>
        </div>
      </div>`;
  }).join('');
}

window.__listAdd = async function(category) {
  const input = document.getElementById(`add-${category}`);
  const value = input?.value.trim();
  if (!value) { toast.warning('Bir değer girin'); return; }
  try {
    const data = await api.post('/api/lists/add', { category, value });
    state.balloons = data.balloons || [];
    state.capacity = data.capacity || state.capacity;
    state.options = data.options || {};
    renderCards();
    toast.success('Eklendi', value);
  } catch (err) {
    toast.error('Eklenemedi', err.message);
  }
};

window.__listDel = async function(category, btn) {
  const value = btn?.getAttribute('data-val');
  if (!value) return;
  try {
    const data = await api.post('/api/lists/delete', { category, value });
    state.balloons = data.balloons || [];
    state.options = data.options || {};
    renderCards();
    toast.info('Silindi', value);
  } catch (err) {
    toast.error('Silinemedi', err.message);
  }
};

window.__scanLists = async function() {
  const btn = document.getElementById('btn-scan-lists');
  const oldHtml = btn.innerHTML;
  btn.innerHTML = '<span class="material-symbols-outlined animate-spin">progress_activity</span> Taranıyor...';
  btn.disabled = true;
  
  try {
    const data = await api.post('/api/lists/scan', {});
    state.balloons = data.balloons || [];
    state.capacity = data.capacity || state.capacity;
    state.options = data.options || {};
    renderCards();
    toast.success('Tarama Tamamlandı', 'Tüm geçmiş veriler listelere eklendi!');
  } catch (err) {
    toast.error('Tarama Başarısız', err.message);
  } finally {
    btn.innerHTML = oldHtml;
    btn.disabled = false;
  }
};

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
