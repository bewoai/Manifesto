/* ═══════════════════════════════════════════════════════════════════
   Oteller — otel kartları. Aynı otelin farklı yazımları tek kartta,
   bölge ve buluşma noktası notu. Planlama Excel'i değişmez; kart otel
   gruplamasında ve şoför listelerinde kullanılır.
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, modal, renderHeader, escapeHtml as esc } from '/app.js';

const PAGE = 12;
let state = { data: null, query: '', region: '', showAll: false };
let renderToken = 0;

export async function render(container) {
  const token = ++renderToken;
  renderHeader('Oteller', 'Yazımları birleştir, bölge ve buluşma noktası ekle');
  state = { data: null, query: '', region: '', showAll: false };
  container.innerHTML = `
    <div class="max-w-[1180px] mx-auto w-full flex flex-col gap-6 pb-12">
      <section class="card p-5" id="ht-summary" aria-live="polite">
        <div class="skeleton-text shimmer w-1/3"></div>
      </section>
      <section class="card" aria-labelledby="ht-unmatched-title">
        <div class="card-header flex-wrap gap-3">
          <h2 class="card-title" id="ht-unmatched-title"><span class="material-symbols-outlined">merge</span>Karta bağlanmamış yazımlar</h2>
          <input class="form-input form-input-sm w-full sm:w-64 sm:ml-auto" id="ht-search" type="search"
                 placeholder="Otel ara" aria-label="Otel ara" oninput="window.__htSearch(this.value)">
        </div>
        <p class="px-5 pt-3 text-sm text-on-surface-variant">Planlamada geçen ve henüz bir otel kartına bağlı olmayan adlar. Benzer yazımlar birlikte önerilir; aynı otel olmayanların işaretini kaldırın.</p>
        <div id="ht-unmatched" class="p-5 pt-3"></div>
      </section>
      <section class="card" aria-labelledby="ht-cards-title">
        <div class="card-header flex-wrap gap-3">
          <h2 class="card-title" id="ht-cards-title"><span class="material-symbols-outlined">hotel</span>Otel kartları</h2>
          <div class="flex flex-wrap gap-1.5 sm:ml-auto" id="ht-region-filter" role="group" aria-label="Bölgeye göre süz"></div>
        </div>
        <div id="ht-cards" class="overflow-x-auto"></div>
      </section>
    </div>`;
  await load(token);
}

async function load(token = renderToken) {
  try {
    const data = await api.get('/api/hotels');
    if (token !== renderToken) return;
    state.data = data;
    paint();
  } catch (err) {
    if (token === renderToken) toast.error('Oteller yüklenemedi', err.message);
  }
}

function paint() {
  renderSummary();
  renderUnmatched();
  renderRegionFilter();
  renderCards();
}

function regionOptions(selected = '', { blank = 'Bölge seçin' } = {}) {
  const regions = state.data?.regions || [];
  const extra = selected && !regions.includes(selected) ? [selected] : [];
  return [`<option value="">${esc(blank)}</option>`, ...[...regions, ...extra].map((r) =>
    `<option value="${esc(r)}" ${r === selected ? 'selected' : ''}>${esc(r)}</option>`)].join('');
}

// ─── Özet ───
function renderSummary() {
  const root = document.getElementById('ht-summary');
  if (!root) return;
  const s = state.data.stats || {};
  const pct = s.reservations ? Math.round((s.matched / s.reservations) * 100) : 0;
  const open = (state.data.unmatched || []).length;
  root.innerHTML = `
    <div class="flex flex-wrap items-end gap-x-10 gap-y-4">
      <div>
        <div class="text-label-md uppercase text-on-surface-variant">Karta bağlı rezervasyon</div>
        <div class="font-headline text-[32px] leading-tight font-semibold tnum text-on-surface">${s.matched || 0}<span class="text-on-surface-variant text-xl">/${s.reservations || 0}</span></div>
      </div>
      <div>
        <div class="text-label-md uppercase text-on-surface-variant">Otel kartı</div>
        <div class="font-headline text-[32px] leading-tight font-semibold tnum text-on-surface">${s.cards || 0}</div>
      </div>
      <div>
        <div class="text-label-md uppercase text-on-surface-variant">Bölgesi girilmiş</div>
        <div class="font-headline text-[32px] leading-tight font-semibold tnum text-on-surface">${s.with_region || 0}</div>
      </div>
      <div>
        <div class="text-label-md uppercase text-on-surface-variant">Bekleyen yazım öbeği</div>
        <div class="font-headline text-[32px] leading-tight font-semibold tnum ${open ? 'text-warning' : 'text-on-surface'}">${open}</div>
      </div>
    </div>
    <div class="seat-bar mt-4" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="Karta bağlı rezervasyon oranı"><span style="width:${pct}%"></span></div>
    <p class="text-xs text-on-surface-variant mt-2">Sayılar planlama dosyasındaki tüm günlerden. Excel'deki yazımlar değişmez; kart yalnız uygulamada aynı oteli tanır.</p>`;
}

// ─── Bağlanmamış yazımlar ───
function visibleGroups() {
  const q = state.query.trim().toLocaleUpperCase('tr-TR');
  const groups = (state.data.unmatched || []).map((g, i) => ({ ...g, idx: i }));
  return q ? groups.filter((g) => g.names.some((n) => n.name.toLocaleUpperCase('tr-TR').includes(q))) : groups;
}

function renderUnmatched() {
  const root = document.getElementById('ht-unmatched');
  if (!root) return;
  const groups = visibleGroups();
  if (!groups.length) {
    root.innerHTML = `<div class="empty-state"><div class="empty-title">${state.query ? 'Eşleşen yazım yok' : 'Bütün oteller karta bağlı'}</div>
      <div class="empty-desc">${state.query ? 'Aramayı değiştirin.' : 'Planlamaya yeni otel yazıldığında burada görünür.'}</div></div>`;
    return;
  }
  const shown = state.showAll || state.query ? groups : groups.slice(0, PAGE);
  const cards = state.data.cards || [];
  root.innerHTML = `
    <ul class="divide-y divide-line">${shown.map((g) => {
      const target = g.card_id ? cards.find((c) => c.id === g.card_id) : null;
      return `
      <li class="py-3.5 grid gap-3 lg:grid-cols-[1fr_auto] lg:items-center" data-group="${g.idx}">
        <fieldset class="min-w-0">
          <legend class="sr-only">${esc(g.suggested_name)} yazımları</legend>
          <div class="flex flex-wrap gap-x-4 gap-y-1.5">${g.names.map((n, j) => `
            <label class="inline-flex items-center gap-2 text-on-surface cursor-pointer">
              <input type="checkbox" class="w-4 h-4 accent-[rgb(var(--primary))]" data-name="${esc(n.name)}" checked id="ht-n-${g.idx}-${j}">
              <span class="font-medium">${esc(n.name)}</span>
              <span class="text-xs text-on-surface-variant tnum">${n.count} rez.</span>
            </label>`).join('')}
          </div>
          ${target ? `<div class="text-xs text-on-surface-variant mt-1.5">Benzer kart var: <strong class="text-on-surface">${esc(target.name)}</strong></div>` : ''}
        </fieldset>
        <div class="flex flex-wrap items-center gap-2">
          ${target ? `
            <button class="btn-primary btn-sm" onclick="window.__htMerge(${g.idx}, '${esc(target.id)}')">
              <span class="material-symbols-outlined text-[18px]">add_link</span>${esc(target.name)} kartına ekle</button>
            <button class="btn-ghost btn-sm" onclick="window.__htNewFromGroup(${g.idx})">Yeni kart</button>` : `
            <input class="form-input form-input-sm w-56" id="ht-name-${g.idx}" value="${esc(g.suggested_name)}" aria-label="Kart adı">
            <select class="form-select form-input-sm w-40" id="ht-region-${g.idx}" aria-label="Bölge">${regionOptions('')}</select>
            <button class="btn-primary btn-sm" onclick="window.__htMerge(${g.idx}, '')">
              <span class="material-symbols-outlined text-[18px]">add_card</span>Kart yap</button>`}
        </div>
      </li>`;
    }).join('')}</ul>
    ${!state.showAll && !state.query && groups.length > PAGE ? `
      <button class="btn-ghost btn-sm mt-2" onclick="window.__htShowAll()">${groups.length - PAGE} öbek daha göster</button>` : ''}`;
}

function checkedNames(idx) {
  return [...document.querySelectorAll(`[data-group="${idx}"] input[type=checkbox][data-name]`)]
    .filter((el) => el.checked).map((el) => el.dataset.name);
}

window.__htSearch = (value) => { state.query = value || ''; renderUnmatched(); };
window.__htShowAll = () => { state.showAll = true; renderUnmatched(); };

window.__htMerge = async (idx, cardId) => {
  const names = checkedNames(idx);
  if (!names.length) { toast.warning('Yazım seçin', 'Karta bağlanacak en az bir adı işaretleyin.'); return; }
  const body = { names, card_id: cardId || '' };
  if (!cardId) {
    body.name = (document.getElementById(`ht-name-${idx}`)?.value || '').trim() || names[0];
    body.region = document.getElementById(`ht-region-${idx}`)?.value || '';
  }
  try {
    const res = await api.post('/api/hotels/merge', body);
    toast.success(cardId ? `${res.card.name} kartına eklendi` : `${res.card.name} kartı açıldı`,
      body.region || res.card.region ? '' : 'Bölgeyi kart listesinden seçebilirsiniz.');
    await load();
  } catch (err) { toast.error('Kart kaydedilemedi', err.message); }
};

window.__htNewFromGroup = (idx) => {
  const g = (state.data.unmatched || [])[idx];
  if (!g) return;
  openEditor({ name: g.suggested_name, aliases: [], region: '', meeting_point: '', map_url: '' }, checkedNames(idx));
};

// ─── Kartlar ───
function renderRegionFilter() {
  const root = document.getElementById('ht-region-filter');
  if (!root) return;
  const cards = state.data.cards || [];
  const used = [...new Set(cards.map((c) => c.region).filter(Boolean))];
  const order = [...(state.data.regions || []).filter((r) => used.includes(r)), ...used.filter((r) => !(state.data.regions || []).includes(r))];
  const missing = cards.filter((c) => !c.region).length;
  const chip = (value, label, n) => `
    <button class="pv-tab ${state.region === value ? 'is-on' : ''}" aria-pressed="${state.region === value}"
            onclick="window.__htRegion('${esc(value)}')">${esc(label)} <span class="text-on-surface-variant tnum">${n}</span></button>`;
  root.innerHTML = cards.length ? [
    chip('', 'Tümü', cards.length),
    ...order.map((r) => chip(r, r, cards.filter((c) => c.region === r).length)),
    ...(missing ? [chip('__none', 'Bölgesiz', missing)] : []),
  ].join('') : '';
}

window.__htRegion = (value) => { state.region = state.region === value ? '' : value; renderRegionFilter(); renderCards(); };

function renderCards() {
  const root = document.getElementById('ht-cards');
  if (!root) return;
  let cards = [...(state.data.cards || [])];
  if (state.region === '__none') cards = cards.filter((c) => !c.region);
  else if (state.region) cards = cards.filter((c) => c.region === state.region);
  cards.sort((a, b) => (b.count - a.count) || a.name.localeCompare(b.name, 'tr'));
  if (!cards.length) {
    root.innerHTML = `<div class="empty-state"><div class="empty-title">${(state.data.cards || []).length ? 'Bu bölgede kart yok' : 'Henüz otel kartı yok'}</div>
      <div class="empty-desc">${(state.data.cards || []).length ? 'Süzgeci kaldırın.' : 'Yukarıdaki yazımlardan "Kart yap" ile başlayın; en sık geçen oteller önce listelenir.'}</div></div>`;
    return;
  }
  root.innerHTML = `
    <table class="board">
      <thead><tr>
        <th>Otel</th><th class="w-[170px]">Bölge</th><th class="hidden lg:table-cell">Buluşma noktası</th>
        <th class="text-right w-[90px]">Rezervasyon</th><th class="w-[96px]"><span class="sr-only">İşlemler</span></th>
      </tr></thead>
      <tbody>${cards.map((c) => `
        <tr>
          <td>
            <div class="font-semibold text-on-surface">${esc(c.name)}
              ${c.map_url ? `<a href="${esc(c.map_url)}" target="_blank" rel="noopener" class="text-primary align-middle ml-1" title="Haritada aç" aria-label="${esc(c.name)} haritada aç"><span class="material-symbols-outlined text-[17px]">map</span></a>` : ''}
            </div>
            ${c.aliases.length ? `<div class="text-xs text-on-surface-variant mt-0.5">Yazımlar: ${c.aliases.map(esc).join(', ')}</div>` : ''}
            ${c.meeting_point ? `<div class="text-xs text-on-surface-variant mt-0.5 lg:hidden">Buluşma: ${esc(c.meeting_point)}</div>` : ''}
          </td>
          <td>
            <select class="form-select form-input-sm w-full" aria-label="${esc(c.name)} bölgesi" onchange="window.__htSetRegion('${esc(c.id)}', this.value)">
              ${regionOptions(c.region, { blank: 'Bölge yok' })}
            </select>
          </td>
          <td class="hidden lg:table-cell text-on-surface-variant">${c.meeting_point ? esc(c.meeting_point) : '<span class="opacity-60">—</span>'}</td>
          <td class="text-right tnum">${c.count}</td>
          <td class="text-right whitespace-nowrap">
            <button class="btn-ghost btn-icon" title="Düzenle" aria-label="${esc(c.name)} düzenle" onclick="window.__htEdit('${esc(c.id)}')"><span class="material-symbols-outlined">edit</span></button>
            <button class="btn-ghost btn-icon danger" title="Sil" aria-label="${esc(c.name)} sil" onclick="window.__htDelete('${esc(c.id)}')"><span class="material-symbols-outlined">delete</span></button>
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

const cardById = (id) => (state.data.cards || []).find((c) => c.id === id);

window.__htSetRegion = async (id, region) => {
  const card = cardById(id);
  if (!card) return;
  try {
    await api.post('/api/hotels/card', { id, name: card.name, region });
    toast.success(region ? `${card.name}: ${region}` : `${card.name}: bölge kaldırıldı`);
    await load();
  } catch (err) { toast.error('Bölge kaydedilemedi', err.message); }
};

window.__htEdit = (id) => { const card = cardById(id); if (card) openEditor(card); };

function openEditor(card, extraNames = []) {
  window.__htEditing = { id: card.id || '', aliases: [...(card.aliases || [])], extraNames };
  modal.open(card.id ? 'Otel kartını düzenle' : 'Yeni otel kartı', `
    <div class="grid gap-4">
      <div class="form-group">
        <label class="form-label" for="hte-name">Otel adı</label>
        <input class="form-input" id="hte-name" value="${esc(card.name)}">
        <div class="form-help">Şoför listelerinde bu ad yazılır.</div>
      </div>
      <div class="form-group">
        <label class="form-label" for="hte-region">Bölge</label>
        <select class="form-select" id="hte-region">${regionOptions(card.region || '', { blank: 'Bölge yok' })}</select>
      </div>
      <div class="form-group">
        <label class="form-label" for="hte-meeting">Buluşma noktası notu</label>
        <input class="form-input" id="hte-meeting" value="${esc(card.meeting_point || '')}" placeholder="ör. Araç girmiyor, meydanda bekle">
        <div class="form-help">Şoför listesinin NOT kolonunda "Buluşma: …" olarak çıkar.</div>
      </div>
      <div class="form-group">
        <label class="form-label" for="hte-map">Harita linki (isteğe bağlı)</label>
        <input class="form-input" id="hte-map" value="${esc(card.map_url || '')}" placeholder="Google Maps linki">
      </div>
      <div class="form-group">
        <div class="form-label">Bu karta bağlı yazımlar</div>
        <div id="hte-aliases" class="flex flex-wrap gap-1.5"></div>
      </div>
    </div>`, `
    <button class="btn-secondary" onclick="window.__closeModal()">Vazgeç</button>
    <button class="btn-primary" onclick="window.__htSaveCard()">Kaydet</button>`);
  renderAliases();
  document.getElementById('hte-name')?.focus();
}

function renderAliases() {
  const root = document.getElementById('hte-aliases');
  const ed = window.__htEditing;
  if (!root || !ed) return;
  const all = [...ed.aliases, ...ed.extraNames.filter((n) => !ed.aliases.includes(n))];
  root.innerHTML = all.length ? all.map((a, i) => `
    <span class="badge badge-amber">${esc(a)}
      <button type="button" class="ml-1 opacity-70 hover:opacity-100" aria-label="${esc(a)} yazımını karttan çıkar" onclick="window.__htDropAlias(${i})">
        <span class="material-symbols-outlined">close</span></button>
    </span>`).join('') : '<span class="text-sm text-on-surface-variant">Yalnız otel adı</span>';
}

window.__htDropAlias = (i) => {
  const ed = window.__htEditing;
  const all = [...ed.aliases, ...ed.extraNames.filter((n) => !ed.aliases.includes(n))];
  const name = all[i];
  ed.aliases = ed.aliases.filter((a) => a !== name);
  ed.extraNames = ed.extraNames.filter((a) => a !== name);
  renderAliases();
};

window.__htSaveCard = async () => {
  const ed = window.__htEditing;
  const name = document.getElementById('hte-name')?.value.trim();
  if (!name) { toast.warning('Otel adı gerekli'); return; }
  try {
    await api.post('/api/hotels/card', {
      ...(ed.id ? { id: ed.id } : {}),
      name,
      aliases: [...ed.aliases, ...ed.extraNames],
      region: document.getElementById('hte-region')?.value || '',
      meeting_point: document.getElementById('hte-meeting')?.value || '',
      map_url: document.getElementById('hte-map')?.value || '',
    });
    modal.close();
    toast.success(`${name} kaydedildi`);
    await load();
  } catch (err) { toast.error('Kart kaydedilemedi', err.message); }
};

window.__htDelete = async (id) => {
  const card = cardById(id);
  if (!card) return;
  const ok = await modal.confirm({
    title: `${card.name} kartı silinsin mi?`,
    bodyHtml: `<p class="text-on-surface-variant">Planlamadaki yazımlar değişmez; yalnız bölge ve buluşma noktası bilgisi silinir. Yazımlar yeniden "bağlanmamış" listesine düşer.</p>`,
    confirmLabel: 'Sil', tone: 'danger',
  });
  if (!ok) return;
  try {
    await api.post('/api/hotels/delete', { id });
    toast.success(`${card.name} silindi`);
    await load();
  } catch (err) { toast.error('Silinemedi', err.message); }
};
