/* ═══════════════════════════════════════════════════════════════════
   Uygulama içi Excel görünümü — planlama gün sayfası
   Sütun harfleri + Excel'deki gerçek satır numaraları; çift tık / Enter ile hücre
   düzenleme, değişiklikler "Kaydet" ile toplu yazılır (POST /api/planning/cells,
   tek yedek + revizyon çakışma kontrolü). Kaynak: GET /api/planning/view.
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, balloonInk, escapeHtml as esc } from '/app.js';

const COL_LETTERS = (n) => {
  let s = '';
  for (let c = n; c > 0; c = Math.floor((c - 1) / 26)) s = String.fromCharCode(65 + ((c - 1) % 26)) + s;
  return s;
};

let grid = null;   // { sheet, data, dirty: Map<"r:c", value>, root, onSaved, focusRow }

/** Excel görünümünü `root` içine çizer. */
export async function mountSheetGrid(root, { sheet, onSaved, focusRow } = {}) {
  if (!root || !sheet) return;
  grid = { sheet, data: null, dirty: new Map(), root, onSaved, focusRow };
  root.innerHTML = '<div class="skeleton h-72"></div>';
  try {
    grid.data = await api.get(`/api/planning/view?sheet=${encodeURIComponent(sheet)}`);
  } catch (err) {
    root.innerHTML = `<p class="text-danger">Excel sayfası okunamadı: ${esc(err.message)}</p>`;
    return;
  }
  render();
}

export function sheetGridDirty() {
  return !!(grid && grid.dirty.size);
}

function visibleColumns(data) {
  const width = Math.max(data.max_col || 20, data.header.length);
  const cols = [];
  for (let c = 1; c <= width; c++) {
    const used = (data.header[c - 1] || '').trim() || data.rows.some(r => (r.cells[c - 1] || '').trim());
    if (used) cols.push(c);
  }
  return cols;
}

function render() {
  const { data, root, dirty } = grid;
  const cols = visibleColumns(data);
  const balloonCol = data.columns?.balloon;
  const nameCol = data.columns?.name;
  const passportCol = data.columns?.passport;
  const cellVal = (row, c) => {
    const key = `${row.row}:${c}`;
    return dirty.has(key) ? dirty.get(key) : (row.cells[c - 1] || '');
  };
  root.innerHTML = `
    <div class="flex flex-wrap items-center gap-3 mb-3">
      <div class="text-sm text-on-surface-variant min-w-0 flex-1">
        <span class="font-semibold text-on-surface">${esc(data.file)}</span> · ${esc(data.sheet)} · ${data.rows.length} satır
        <span class="block text-xs">Hücreye çift tıklayın ya da seçip Enter'a basın. Değişiklikler "Kaydet" ile Excel'e yazılır, öncesinde yedek alınır.</span>
      </div>
      <span class="text-sm font-semibold text-primary" id="sg-dirty">${dirty.size ? `${dirty.size} değişiklik` : ''}</span>
      <button class="btn-secondary btn-sm" onclick="window.__sgDiscard()" ${dirty.size ? '' : 'disabled'}>Vazgeç</button>
      <button class="btn-primary btn-sm" id="sg-save" onclick="window.__sgSave()" ${dirty.size ? '' : 'disabled'}>
        <span class="material-symbols-outlined text-[18px]">save</span> Kaydet
      </button>
      <button class="btn-ghost btn-sm" onclick="window.__sgOpenExcel()" title="Dosyayı Microsoft Excel'de aç. Excel açıkken uygulama dosyaya yazamaz.">
        <span class="material-symbols-outlined text-[18px]">open_in_new</span> Excel'de aç
      </button>
    </div>
    <div class="sg-wrap max-h-[70vh] overflow-auto rounded-lg border border-line bg-raised" role="grid" aria-label="Planlama sayfası ${esc(data.sheet)}">
      <table class="sg-table">
        <thead>
          <tr>
            <th class="sg-corner" scope="col"></th>
            ${cols.map(c => `<th scope="col" class="sg-col"><span class="sg-letter">${COL_LETTERS(c)}</span><span class="sg-head">${esc(data.header[c - 1] || '')}</span></th>`).join('')}
          </tr>
        </thead>
        <tbody>
          ${data.rows.map(row => {
            const seat = !(row.cells[nameCol - 1] || '').trim() && !(row.cells[passportCol - 1] || '').trim();
            const balloon = (row.cells[balloonCol - 1] || '').trim();
            return `<tr data-row="${row.row}" class="${seat ? 'sg-seat' : ''} ${grid.focusRow === row.row ? 'sg-focus' : ''}">
              <th scope="row" class="sg-rownum">${row.row}</th>
              ${cols.map(c => {
                const v = cellVal(row, c);
                const isDirty = dirty.has(`${row.row}:${c}`);
                const ink = c === balloonCol && balloon ? ` style="${balloonInk(balloon)}"` : '';
                return `<td tabindex="0" data-r="${row.row}" data-c="${c}" class="sg-cell ${isDirty ? 'sg-dirty' : ''} ${c === passportCol ? 'font-mono' : ''} ${c === balloonCol && balloon ? 'sg-balloon' : ''}"${ink}>${esc(v)}</td>`;
              }).join('')}
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>`;
  const wrap = root.querySelector('.sg-wrap');
  wrap.addEventListener('dblclick', (e) => { const td = e.target.closest('td.sg-cell'); if (td) beginEdit(td); });
  wrap.addEventListener('keydown', onKey);
  if (grid.focusRow) {
    const tr = wrap.querySelector(`tr[data-row="${grid.focusRow}"]`);
    if (tr) tr.scrollIntoView({ block: 'center' });
  }
}

function onKey(e) {
  const td = e.target.closest?.('td.sg-cell');
  if (!td || e.target.tagName === 'INPUT') return;
  const move = { ArrowDown: [1, 0], ArrowUp: [-1, 0], ArrowRight: [0, 1], ArrowLeft: [0, -1] }[e.key];
  if (move) { e.preventDefault(); focusNeighbor(td, ...move); return; }
  if (e.key === 'Enter' || e.key === 'F2') { e.preventDefault(); beginEdit(td); return; }
  if (e.key === 'Delete') { e.preventDefault(); setValue(td, ''); return; }
  if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); beginEdit(td, e.key); }
}

function focusNeighbor(td, dr, dc) {
  const tr = td.parentElement;
  if (dc) {
    const sib = dc > 0 ? td.nextElementSibling : td.previousElementSibling;
    if (sib && sib.matches('td.sg-cell')) sib.focus();
    return;
  }
  const idx = [...tr.children].indexOf(td);
  const next = dr > 0 ? tr.nextElementSibling : tr.previousElementSibling;
  next?.children[idx]?.focus();
}

function beginEdit(td, firstChar) {
  if (td.querySelector('input')) return;
  const old = td.textContent;
  const input = document.createElement('input');
  input.className = 'sg-input';
  input.value = firstChar ?? old;
  td.textContent = '';
  td.appendChild(input);
  input.focus();
  if (firstChar == null) input.select();
  let done = false;
  const finish = (commit, move) => {
    if (done) return;
    done = true;
    const value = input.value;
    td.textContent = commit ? value : old;
    if (commit && value !== old) setValue(td, value);
    if (move) focusNeighbor(td, ...move); else td.focus();
  };
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); finish(true, [1, 0]); }
    else if (e.key === 'Tab') { e.preventDefault(); finish(true, [0, e.shiftKey ? -1 : 1]); }
    else if (e.key === 'Escape') { e.preventDefault(); finish(false); }
  });
  input.addEventListener('blur', () => finish(true));
}

function setValue(td, value) {
  const r = Number(td.dataset.r), c = Number(td.dataset.c);
  const row = grid.data.rows.find(x => x.row === r);
  const original = row ? (row.cells[c - 1] || '') : '';
  const key = `${r}:${c}`;
  if (value === original) grid.dirty.delete(key); else grid.dirty.set(key, value);
  td.textContent = value;
  td.classList.toggle('sg-dirty', grid.dirty.has(key));
  const n = grid.dirty.size;
  const label = grid.root.querySelector('#sg-dirty');
  if (label) label.textContent = n ? `${n} değişiklik` : '';
  grid.root.querySelectorAll('#sg-save, [onclick="window.__sgDiscard()"]').forEach(b => { b.disabled = !n; });
}

window.__sgDiscard = function() {
  if (!grid) return;
  grid.dirty.clear();
  render();
};

window.__sgSave = async function() {
  if (!grid || !grid.dirty.size) return;
  const changes = [...grid.dirty].map(([key, value]) => {
    const [row, col] = key.split(':').map(Number);
    return { row, col, value };
  });
  const btn = grid.root.querySelector('#sg-save');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="btn-spinner"></span> Kaydediliyor'; }
  try {
    const res = await api.post('/api/planning/cells', {
      sheet: grid.sheet, expected_revision: grid.data.workbook_revision, changes,
    });
    toast.success(`${res.count} hücre kaydedildi`, `Yedek: ${res.backup}`);
    const { root, sheet, onSaved } = grid;
    await mountSheetGrid(root, { sheet, onSaved });
    onSaved?.();
  } catch (err) {
    if (err.status === 409) {
      toast.warning('Dosya bu arada değişti', 'Değişiklikleriniz yazılmadı. Sayfayı yenileyip tekrar girin. Excel açıksa kapatın.');
    } else {
      toast.error('Kaydedilemedi', err.message);
    }
    if (btn) { btn.disabled = false; btn.innerHTML = '<span class="material-symbols-outlined text-[18px]">save</span> Kaydet'; }
  }
};

window.__sgOpenExcel = async function() {
  try {
    await api.post('/api/planning/open-excel', {});
    toast.info("Excel'de açıldı", 'Excel açıkken uygulama dosyaya yazamaz; işiniz bitince kaydedip kapatın.');
  } catch (err) { toast.error('Excel açılamadı', err.message); }
};
