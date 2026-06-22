/* ═══════════════════════════════════════════════════════════════════
   Combobox — bir <input>'u yaz-filtrele + tıkla-seç açılır listesine çevirir.
   Serbest metin de kabul eder (yeni değer). Açılır panel body'e eklenir ve
   position:fixed ile konumlanır → kartların overflow:hidden'ı kırpamaz.
   ═══════════════════════════════════════════════════════════════════ */

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
const lower = (s) => String(s || '').toLocaleLowerCase('tr');

// Tüm comboboxlar için tek paylaşılan panel (aynı anda yalnız bir input aktif)
let listEl = null;
let activeInput = null;
let activeGet = null;
let activeOnPick = null;

function ensureList() {
  if (listEl) return listEl;
  listEl = document.createElement('div');
  listEl.className = 'cb-list';
  listEl.style.display = 'none';
  document.body.appendChild(listEl);
  listEl.addEventListener('mousedown', (e) => {
    const opt = e.target.closest('.cb-opt');
    if (!opt || !activeInput) return;
    e.preventDefault();
    const input = activeInput;
    input.value = opt.getAttribute('data-v');
    const onPick = activeOnPick;
    hide();
    if (onPick) onPick(input.value);
    input.dispatchEvent(new Event('change'));
  });
  window.addEventListener('scroll', position, true);
  window.addEventListener('resize', position);
  return listEl;
}

function hide() {
  if (listEl) listEl.style.display = 'none';
  activeInput = null;
}

function position() {
  if (!activeInput || !listEl || listEl.style.display === 'none') return;
  const r = activeInput.getBoundingClientRect();
  listEl.style.left = `${r.left}px`;
  listEl.style.top = `${r.bottom + 4}px`;
  listEl.style.width = `${r.width}px`;
}

function renderFor() {
  if (!activeInput) return;
  const raw = (typeof activeGet === 'function' ? activeGet() : activeGet) || [];
  const items = raw.map(o => (typeof o === 'string' ? { value: o, label: o } : o));
  const q = lower(activeInput.value);
  const f = items
    .filter(o => !q || lower(o.label).includes(q) || lower(o.value).startsWith(q))
    .slice(0, 60);
  if (!f.length) { listEl.style.display = 'none'; return; }
  listEl.innerHTML = f.map(o => `<div class="cb-opt" data-v="${esc(o.value)}">${esc(o.label)}</div>`).join('');
  listEl.style.display = '';
  position();
}

/**
 * @param {HTMLInputElement} input
 * @param {() => Array<string|{value:string,label:string}>} getOptions
 * @param {{onPick?: (v:string)=>void}} [opts]
 */
export function attachCombobox(input, getOptions, opts = {}) {
  if (!input || input.dataset.cb === '1') return;
  input.dataset.cb = '1';
  input.setAttribute('autocomplete', 'off');
  input.removeAttribute('list');
  ensureList();

  const open = () => { activeInput = input; activeGet = getOptions; activeOnPick = opts.onPick; renderFor(); };
  input.addEventListener('focus', open);
  input.addEventListener('input', () => { if (activeInput !== input) open(); else renderFor(); });
  input.addEventListener('blur', () => setTimeout(() => { if (activeInput === input) hide(); }, 160));
}
