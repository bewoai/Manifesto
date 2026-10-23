/* ═══════════════════════════════════════════════════════════════════
   Kimlik düzeltme penceresi — planlama ve manifesto ekranlarının ortak kullanımı.
   Yalnız 4 kimlik alanını (uyruk, cinsiyet, ad soyad, pasaport/kimlik no) Excel'e
   yazar: POST /api/planning/write-identity. Uyruk sunucuda ISO'ya çevrilir
   (IRE → IRL, UK → GBR, GER → DEU …).
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, modal } from '/app.js';
import { attachCombobox } from '/combobox.js';

let countryOptions = null;
async function loadCountryOptions() {
  if (countryOptions) return countryOptions;
  try {
    const res = await api.get('/api/countries');
    countryOptions = (res.countries || []).map(c => ({ value: c.code, label: `${c.code} — ${c.name}` }));
  } catch (e) { countryOptions = []; }
  return countryOptions;
}

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

const SEX_FROM_TR = { 'ERKEK': 'M', 'KADIN': 'F', 'KADİN': 'F', 'E': 'M', 'K': 'F' };

let saving = false;
let current = null;

/**
 * @param {{sheet:string,row:number,values:{nationality?:string,sex?:string,name?:string,passport_no?:string},
 *          expectedRevision?:string, hint?:string, focus?:'nationality'|'sex'|'name'|'passport_no',
 *          onSaved?:(update:object)=>void}} opts
 */
export function openIdentityEditor(opts) {
  current = opts;
  const v = opts.values || {};
  const sexRaw = String(v.sex || '').trim().toUpperCase();
  const sex = SEX_FROM_TR[sexRaw] || sexRaw;
  modal.open('Yolcu kimliğini düzelt', `
    ${opts.hint ? `<div class="mb-4 p-3 rounded-xl bg-warning/10 border border-warning/20 text-sm text-warning">${esc(opts.hint)}</div>` : ''}
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Uyruk (ISO kodu)</label>
        <input class="form-input font-mono uppercase" id="ie-nat" value="${esc(v.nationality || '')}" placeholder="IRL, GBR, TUR..." autocomplete="off" />
        <div class="form-help">IRE, UK, GER gibi kodlar kaydederken ISO'ya (IRL, GBR, DEU) çevrilir.</div>
      </div>
      <div class="form-group">
        <label class="form-label">Cinsiyet</label>
        <select class="form-select" id="ie-sex">
          <option value="" ${!sex ? 'selected' : ''}>—</option>
          <option value="M" ${sex === 'M' ? 'selected' : ''}>Erkek</option>
          <option value="F" ${sex === 'F' ? 'selected' : ''}>Kadın</option>
        </select>
      </div>
    </div>
    <div class="form-group mt-4">
      <label class="form-label">Ad Soyad</label>
      <input class="form-input uppercase" id="ie-name" value="${esc(v.name || '')}" />
    </div>
    <div class="form-group mt-4">
      <label class="form-label">Pasaport / Kimlik No</label>
      <input class="form-input font-mono uppercase" id="ie-ppno" value="${esc(v.passport_no || '')}" />
      <div class="form-help">${esc(opts.sheet)} · satır ${esc(String(opts.row))} · yalnız bu 4 alan Excel'e yazılır.</div>
    </div>
  `, `
    <button class="btn-secondary" onclick="window.__closeModal()">İptal</button>
    <button class="btn-primary" id="btn-ie-save" onclick="window.__saveIdentityEdit()">Kaydet</button>
  `);
  const natEl = document.getElementById('ie-nat');
  if (natEl) attachCombobox(natEl, () => countryOptions || []);
  loadCountryOptions();
  const focusId = { nationality: 'ie-nat', sex: 'ie-sex', name: 'ie-name', passport_no: 'ie-ppno' }[opts.focus];
  if (focusId) setTimeout(() => document.getElementById(focusId)?.focus(), 50);
}

window.__saveIdentityEdit = async function() {
  if (saving || !current) return;
  const val = (id) => document.getElementById(id)?.value.trim() || '';
  const update = {
    nationality: val('ie-nat').toUpperCase(),
    sex: val('ie-sex').toUpperCase(),
    name: val('ie-name').toUpperCase(),
    passport_no: val('ie-ppno').toUpperCase(),
  };
  if (!update.name && !update.passport_no) { toast.warning('İsim ya da pasaport no gerekli'); return; }
  const btn = document.getElementById('btn-ie-save');
  saving = true;
  if (btn) btn.disabled = true;
  try {
    const body = { sheet: current.sheet, updates: { [current.row]: update } };
    if (current.expectedRevision) body.expected_revision = current.expectedRevision;
    await api.post('/api/planning/write-identity', body);
    toast.success('Kimlik güncellendi', update.name || update.passport_no);
    modal.close();
    const done = current.onSaved;
    current = null;
    if (done) done(update);
  } catch (err) {
    toast.error('Kaydedilemedi', err.message);
    if (btn?.isConnected) btn.disabled = false;
  } finally {
    saving = false;
  }
};
