/* ═══════════════════════════════════════════════════════════════════
   Ana Sayfa — "bugün ne yapmalıyım"
   Sabah uçuş bayrağı (hava tavsiyesi) · gün başlığı · bugün yapılacaklar + 4 metrik ·
   balon kapı panosu (zarf şeridi, koltuk çubuğu, değişen satır işaretli) · seçili balonun
   biniş kartı. Veri: /api/planning/sheets, /api/planning/load, /api/weather/status.
   ═══════════════════════════════════════════════════════════════════ */
import { api, toast, renderHeader, modal, balloonInk, envStripe, setBalloonCodes } from '/app.js';

let renderId = 0;
let state = { data: null, selected: null, changed: new Set() };

const TR_MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];
const TR_DAYS = ['Pazar', 'Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi'];

export async function render(container) {
  const myRenderId = ++renderId;
  renderHeader('Ana Sayfa');
  container.innerHTML = `
    <div class="max-w-[1440px] mx-auto space-y-6">
      <div id="dash-flag"></div>
      <div class="flex flex-wrap items-end justify-between gap-4">
        <h2 id="dash-title" class="font-headline text-headline-lg text-on-surface">Bugün</h2>
        <label class="flex items-center gap-2 text-sm text-on-surface-variant">
          <span class="font-semibold">Uçuş günü</span>
          <select class="form-select !w-auto !py-2 min-w-[150px]" id="dash-sheet" onchange="window.__dashLoad()"></select>
        </label>
      </div>
      <div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-5">
        <section class="glass-panel rounded-xl" aria-labelledby="todo-h">
          <h3 id="todo-h" class="px-5 pt-4 pb-3 font-headline text-headline-sm text-on-surface border-b border-line">Bugün yapılacaklar</h3>
          <div id="dash-todo"></div>
        </section>
        <section class="rounded-xl overflow-hidden border border-line bg-line grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-2 gap-px" id="dash-metrics" aria-label="Gün özeti"></section>
      </div>
      <div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-5 items-start">
        <section class="glass-panel rounded-xl overflow-hidden" aria-labelledby="board-h">
          <div class="flex items-center justify-between gap-3 px-5 pt-4 pb-3">
            <h3 id="board-h" class="font-headline text-headline-sm text-on-surface">Balonlar</h3>
            <a href="#/planning" class="btn-link text-sm">Planlamada aç <span class="material-symbols-outlined text-[18px]">arrow_forward</span></a>
          </div>
          <div id="dash-board"></div>
        </section>
        <aside id="dash-pass" aria-live="polite"></aside>
      </div>
    </div>`;
  await loadDashboard(myRenderId);
}

function isCurrent(token) {
  return token === renderId && !!document.getElementById('dash-sheet');
}

// ─── Tarih yardımcıları ───
function parseSheetDate(name) {
  const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(String(name || '').trim());
  return m ? new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1])) : null;
}
function dayDiff(d) {
  const t = new Date(); t.setHours(0, 0, 0, 0);
  return Math.round((d - t) / 86400000);
}
function sheetTitle(name) {
  const d = parseSheetDate(name);
  if (!d) return esc(name);
  const diff = dayDiff(d);
  const rel = diff === 0 ? 'Bugün' : diff === 1 ? 'Yarın' : diff === -1 ? 'Dün' : '';
  const long = `${d.getDate()} ${TR_MONTHS[d.getMonth()]} ${d.getFullYear()} <span class="text-on-surface-variant font-normal">${TR_DAYS[d.getDay()]}</span>`;
  return rel ? `${rel} <span class="text-outline">·</span> ${long}` : long;
}
function pickDefaultSheet(sheets) {
  const dated = sheets.map((s) => [s, parseSheetDate(s)]).filter(([, d]) => d);
  if (!dated.length) return sheets[sheets.length - 1];
  const today = dated.find(([, d]) => dayDiff(d) === 0);
  if (today) return today[0];
  const upcoming = dated.filter(([, d]) => dayDiff(d) > 0).sort((a, b) => a[1] - b[1]);
  if (upcoming.length) return upcoming[0][0];
  return dated.sort((a, b) => a[1] - b[1])[dated.length - 1][0];
}

// ─── Yükleme ───
function showSkeletons() {
  const sk = (h) => `<div class="skeleton ${h} m-5"></div>`;
  const set = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
  set('dash-todo', sk('h-36'));
  set('dash-metrics', `<div class="col-span-full bg-panel">${sk('h-28')}</div>`);
  set('dash-board', sk('h-48'));
  set('dash-pass', '');
}

async function loadDashboard(token = renderId) {
  showSkeletons();
  loadWeather(token);
  try {
    const sheetsData = await api.get('/api/planning/sheets');
    if (!isCurrent(token)) return;
    const sheets = sheetsData.sheets || [];
    const select = document.getElementById('dash-sheet');
    if (!sheets.length) { showEmptyState(token); return; }
    select.innerHTML = sheets.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
    select.value = pickDefaultSheet(sheets);
    await window.__dashLoad(token);
  } catch (err) {
    if (!isCurrent(token)) return;
    if (err.status === 404) showEmptyState(token);
    else toast.error('Ana sayfa yüklenemedi', err.message);
  }
}

window.__dashLoad = async function(token = renderId) {
  const sheet = document.getElementById('dash-sheet')?.value;
  if (!sheet) return;
  document.getElementById('dash-title').innerHTML = sheetTitle(sheet);
  showSkeletons();
  try {
    const data = await api.get(`/api/planning/load?sheet=${encodeURIComponent(sheet)}`);
    if (!isCurrent(token)) return;
    setBalloonCodes(data.balloon_codes);
    state.data = data;
    const balloons = summarizeBalloons(data);
    state.changed = diffSnapshot(sheet, balloons);
    if (!state.selected || !balloons.some((b) => b.code === state.selected)) {
      state.selected = (balloons.find((b) => b.issues) || balloons[0] || {}).code || null;
    }
    renderTodo(data, balloons);
    renderMetrics(data, balloons);
    renderBoard(balloons);
    renderPass(balloons);
  } catch (err) {
    if (!isCurrent(token)) return;
    toast.error('Gün yüklenemedi', err.message);
  }
};

// ─── Sabah uçuş bayrağı (hava tavsiyesi) ───
const FLAGS = [
  { key: 'go', status: 'flyable', name: 'Uygun' },
  { key: 'hold', status: 'caution', name: 'Dikkat' },
  { key: 'stop', status: 'no_go', name: 'Riskli' },
];

async function loadWeather(token = renderId) {
  const root = document.getElementById('dash-flag');
  if (!root) return;
  root.innerHTML = '<div class="skeleton h-16"></div>';
  let decision = {};
  let offline = false;
  let detail = '';
  try {
    const data = await api.get('/api/weather/status');
    decision = data.decision || {};
    offline = !!data.error;
    const cur = data.current || {};
    const rawPlace = typeof data.location === 'string' ? data.location : (data.location?.name || '');
    const place = rawPlace.replace(/^goreme( valley)?$/i, 'Göreme').replace(/^urgup$/i, 'Ürgüp').replace(/^uchisar$/i, 'Uçhisar');
    const t = cur.measured_at ? new Date(cur.measured_at) : null;
    const hhmm = t && !isNaN(t) ? t.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : '';
    const wind = cur.wind_speed_kmh != null ? `rüzgâr ${Math.round(cur.wind_speed_kmh)} km/sa` : '';
    detail = [place, hhmm, wind].filter(Boolean).join(' · ');
  } catch (err) {
    offline = true;
  }
  if (!isCurrent(token)) return;
  const active = FLAGS.find((f) => f.status === decision.flight_status);
  const caption = `<a href="#/weather" aria-label="Hava ayrıntısı" class="ml-auto shrink-0 inline-flex items-center gap-1 text-[13px] font-semibold underline-offset-4 hover:underline"><span class="hidden sm:inline">Hava ayrıntısı</span> <span class="material-symbols-outlined text-[17px]">arrow_forward</span></a>`;
  if (!active) {
    root.innerHTML = `
      <div class="flag-strip" role="status">
        <div class="flag unknown on rounded-xl">
          <span class="material-symbols-outlined">cloud_off</span>
          <div class="min-w-0"><div class="flag-name">${esc(decision.title || 'Hava verisi bekleniyor')}</div>
          <div class="flag-sub">${esc(offline ? 'Hava servisine ulaşılamadı. Son kayıt kullanılamıyor.' : (decision.summary || 'Sabah uçuş penceresi için yeterli veri yok.'))}</div></div>
          ${caption}
        </div>
      </div>`;
    return;
  }
  root.innerHTML = `
    <div class="flag-strip" role="status" aria-label="Hava tavsiyesi: ${esc(active.name)}">
      ${FLAGS.map((f) => f === active ? `
        <div class="flag ${f.key} on">
          <span class="material-symbols-outlined">${f.key === 'go' ? 'flag' : f.key === 'hold' ? 'flag' : 'block'}</span>
          <div class="min-w-0">
            <div class="flag-name">${esc(decision.title || f.name)}</div>
            <div class="flag-sub truncate">${esc([detail, decision.summary].filter(Boolean).join(' · '))}${offline ? ' · çevrimdışı, son kayıt' : ''}</div>
          </div>
          ${caption}
        </div>` : `
        <div class="flag ${f.key} off" aria-hidden="true"><span class="flag-name">${f.name}</span></div>`).join('')}
    </div>
    <p class="mt-1.5 text-xs text-on-surface-variant">Hava tavsiyesidir; resmî uçuş izni yerine geçmez.</p>`;
}

// ─── Balon özeti ───
function summarizeBalloons(data) {
  const cap = data.capacity || 28;
  const codes = new Set([...(data.balloon_codes || []), ...Object.keys(data.balloon_load || {})]);
  const blocks = data.blocks || [];
  const issues = (data.readiness || {}).issues || [];
  const leadToBalloon = new Map(blocks.map((b) => [b.lead_row, b.balloon]));
  const out = [];
  for (const code of codes) {
    if (!code) continue;
    const own = blocks.filter((b) => b.balloon === code);
    const pilots = mostCommon(own.map((b) => b.pilot).filter(Boolean));
    const drivers = [...new Set(own.map((b) => b.driver).filter(Boolean))].sort();
    const places = [...new Set(own.map((b) => b.coming_place).filter(Boolean))];
    const used = (data.balloon_load || {})[code] || 0;
    const passengers = own.reduce((n, b) => n + (b.passengers || []).filter((p) => p.name || p.passport_no).length, 0);
    const issueCount = issues.filter((i) => (i.balloon === code) || (i.lead_row && leadToBalloon.get(i.lead_row) === code)).length;
    out.push({
      code, cap, used, passengers, pilot: pilots[0] || '', drivers, places,
      reservations: own.length, free: Math.max(0, cap - used), issues: issueCount,
      overflow: used > cap,
    });
  }
  return out;
}

function mostCommon(values) {
  const c = new Map();
  values.forEach((v) => c.set(v, (c.get(v) || 0) + 1));
  return [...c.entries()].sort((a, b) => b[1] - a[1]).map(([v]) => v);
}

// Değişen satır: balonun yük/rezervasyon/sorun özeti son görülenden farklıysa işaretli kalır.
function diffSnapshot(sheet, balloons) {
  const key = `irtifa-board:${sheet}`;
  const now = Object.fromEntries(balloons.map((b) => [b.code, `${b.used}|${b.reservations}|${b.issues}|${b.pilot}`]));
  let prev = null;
  try { prev = JSON.parse(localStorage.getItem(key) || 'null'); } catch (e) { prev = null; }
  try { localStorage.setItem(key, JSON.stringify(now)); } catch (e) { /* yalnız bu oturum */ }
  if (!prev) return new Set();
  return new Set(balloons.filter((b) => prev[b.code] !== undefined && prev[b.code] !== now[b.code]).map((b) => b.code));
}

// ─── Bugün yapılacaklar ───
function renderTodo(data, balloons) {
  const root = document.getElementById('dash-todo');
  if (!root) return;
  const r = data.readiness || {};
  const c = r.counts || {};
  const items = [];
  const push = (tone, text, route, action) => items.push({ tone, text, route, action });

  if (c.pending_ocr_review) {
    const msg = (r.issues || []).find((i) => i.code === 'pending_ocr_review')?.message || 'Sarı OCR sonuçları onay bekliyor.';
    push('warn', msg, 'manual_review', 'İncele');
  }
  if (c.missing_identity) push('warn', `${c.missing_identity} yolcunun kimlik bilgisi eksik`, 'planning', 'Tamamla');
  if (c.duplicate_document) push('danger', `${c.duplicate_document} belge numarası birden fazla satırda`, 'planning', 'Düzelt');
  balloons.filter((b) => b.overflow).forEach((b) => push('danger', `${b.code} kapasitesi aşıldı: ${b.used}/${b.cap}`, 'planning', 'Dağıt'));
  if (c.pax_mismatch) push('warn', `${c.pax_mismatch} rezervasyonda PAX ile yolcu sayısı tutmuyor`, 'planning', 'Düzenle');
  const opsMissing = [
    ['missing_pickup', 'pickup saati'], ['missing_driver', 'şoför'], ['missing_hotel', 'otel'],
    ['missing_coming_place', 'geleceği yer'], ['missing_pilot', 'pilot'], ['missing_balloon', 'balon'],
  ].filter(([k]) => c[k]);
  opsMissing.forEach(([k, label]) => push('warn', `${c[k]} rezervasyonda ${label} eksik`, 'planning', 'Düzenle'));
  const freeTotal = balloons.reduce((n, b) => n + b.free, 0);
  if (freeTotal > 0 && balloons.length) {
    const detail = balloons.filter((b) => b.free).map((b) => `${b.code} ${b.free}`).join(', ');
    push('info', `${freeTotal} boş koltuk · ${detail}`, 'passport', 'Rezervasyon ekle');
  }
  if (r.ready && (data.total_blocks || 0) > 0) push('ok', 'Gün hazır. Manifesto ve şoför listelerini alabilirsiniz.', 'manifest', 'Çıktıları hazırla');
  else if (!r.ready) push('neutral', 'Eksikler tamamlanınca manifestolar hazırlanabilir', 'manifest', 'Manifestoya git');
  if (!(data.total_blocks || 0)) push('neutral', 'Bu günde henüz rezervasyon yok', 'passport', 'Pasaport okut');

  const dot = { warn: 'bg-warning', danger: 'bg-danger', ok: 'bg-success', info: 'bg-primary', neutral: 'bg-outline' };
  root.innerHTML = `<ul class="divide-y divide-line">${items.slice(0, 7).map((it) => `
    <li>
      <a href="#/${it.route}" class="flex items-center gap-3.5 px-5 py-3 hover:bg-tertiary/[.035] transition-colors group">
        <span class="w-2.5 h-2.5 rounded-full shrink-0 ${dot[it.tone]}" aria-hidden="true"></span>
        <span class="flex-1 text-on-surface">${esc(it.text)}</span>
        <span class="text-sm font-semibold text-primary whitespace-nowrap group-hover:underline underline-offset-4">${esc(it.action)}</span>
      </a>
    </li>`).join('')}</ul>`;
}

// ─── Metrikler ───
function renderMetrics(data, balloons) {
  const root = document.getElementById('dash-metrics');
  if (!root) return;
  const r = data.readiness || {};
  const seats = balloons.reduce((n, b) => n + b.cap, 0);
  const pax = balloons.reduce((n, b) => n + b.used, 0);
  const free = balloons.reduce((n, b) => n + b.free, 0);
  const metrics = [
    ['Koltuk', seats, `${balloons.length} balon`],
    ['Yolcu', pax, `${data.total_blocks || 0} rezervasyon`],
    ['Boş', free, free ? 'satışa açık' : 'tam dolu'],
    ['Kontrol', r.issue_count || 0, r.ready ? 'eksik yok' : 'bekleyen uyarı'],
  ];
  root.innerHTML = metrics.map(([label, value, sub], i) => `
    <div class="bg-panel px-5 py-4">
      <div class="text-label-md uppercase text-on-surface-variant">${label}</div>
      <div class="font-headline text-[40px] leading-[1.05] font-semibold tnum mt-1 ${label === 'Kontrol' && value ? 'text-warning' : 'text-on-surface'}">${value}</div>
      <div class="text-[13px] text-on-surface-variant">${sub}</div>
    </div>`).join('');
}

// ─── Kapı panosu ───
function renderBoard(balloons) {
  const root = document.getElementById('dash-board');
  if (!root) return;
  if (!balloons.length) {
    root.innerHTML = '<div class="empty-state"><div class="empty-title">Bu günde balon yok</div><div class="empty-desc">Ayarlar &gt; Listeler\'den balon kodlarını ekleyin ya da planlamaya rezervasyon girin.</div></div>';
    return;
  }
  root.innerHTML = `
    <table class="board">
      <thead><tr>
        <th class="w-[132px]">Balon</th><th class="hidden sm:table-cell">Pilot</th><th class="w-[38%]">Koltuk</th>
        <th class="hidden 2xl:table-cell text-right">Rezervasyon</th><th class="hidden 2xl:table-cell">Şoför</th><th>Durum</th>
      </tr></thead>
      <tbody>${balloons.map((b) => {
        const pct = Math.min(100, Math.round((b.used / Math.max(1, b.cap)) * 100));
        const sel = b.code === state.selected;
        const status = b.overflow ? `<span class="badge badge-red">Kapasite aşıldı</span>`
          : b.issues ? `<span class="badge badge-yellow">${b.issues} eksik</span>`
          : b.reservations ? `<span class="badge badge-green"><span class="material-symbols-outlined">check</span>Hazır</span>`
          : `<span class="text-sm text-on-surface-variant">Boş</span>`;
        return `
        <tr class="cursor-pointer ${state.changed.has(b.code) ? 'changed' : ''}" onclick="window.__dashSelect('${esc(b.code)}')" aria-selected="${sel}">
          <td>
            <div class="flex items-center gap-3 h-9">
              ${envStripe(b.code)}
              <span class="text-[17px] font-semibold tracking-wide" style="${balloonInk(b.code)}; color: rgb(var(--env))">${esc(b.code)}</span>
              ${sel ? '<span class="material-symbols-outlined text-[18px] text-primary" aria-label="seçili">chevron_right</span>' : ''}
            </div>
          </td>
          <td class="hidden sm:table-cell text-on-surface whitespace-nowrap">${esc(b.pilot) || '<span class="text-on-surface-variant">—</span>'}</td>
          <td>
            <div class="flex items-center gap-3">
              <div class="seat-bar flex-1" style="${balloonInk(b.code)}"><span style="width:${pct}%"></span></div>
              <span class="num text-sm ${b.overflow ? 'text-danger' : 'text-on-surface'}">${b.used}/${b.cap}</span>
            </div>
          </td>
          <td class="hidden 2xl:table-cell num text-right text-on-surface">${b.reservations}</td>
          <td class="hidden 2xl:table-cell text-on-surface-variant text-sm">${b.drivers.length ? esc(b.drivers.join(', ')) : '—'}</td>
          <td><div class="flex flex-wrap items-center gap-1.5">${status}${state.changed.has(b.code) ? '<span class="changed-tag">Değişti</span>' : ''}</div></td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
}

window.__dashSelect = function(code) {
  state.selected = code;
  const balloons = summarizeBalloons(state.data || {});
  renderBoard(balloons);
  renderPass(balloons);
};

// ─── Balon biniş kartı ───
function renderPass(balloons) {
  const root = document.getElementById('dash-pass');
  if (!root) return;
  const b = balloons.find((x) => x.code === state.selected);
  if (!b) { root.innerHTML = ''; return; }
  const sheet = state.data?.sheet || '';
  root.innerHTML = `
    <div class="pass" style="${balloonInk(b.code)}" role="region" aria-label="${esc(b.code)} balonu">
      <div class="pass-seg flex items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          ${envStripe(b.code)}
          <div class="font-headline text-[34px] leading-none font-semibold" style="color: rgb(var(--env))">${esc(b.code)}</div>
        </div>
        <div class="text-right">
          <div class="text-label-md uppercase text-on-surface-variant">Koltuk</div>
          <div class="font-headline text-[26px] leading-none font-semibold tnum ${b.overflow ? 'text-danger' : 'text-on-surface'}">${b.used}<span class="text-on-surface-variant text-[18px]">/${b.cap}</span></div>
        </div>
      </div>
      <dl class="pass-seg pt-0">
        <div class="pass-field"><dt>Pilot</dt><dd>${esc(b.pilot) || '—'}</dd></div>
        <div class="pass-field"><dt>Yolcu</dt><dd class="tnum">${b.passengers} kimlikli · ${b.reservations} rezervasyon</dd></div>
        <div class="pass-field"><dt>Şoför</dt><dd>${b.drivers.length ? esc(b.drivers.join(', ')) : '—'}</dd></div>
        <div class="pass-field"><dt>Geleceği yer</dt><dd>${b.places.length ? esc(b.places.join(', ')) : '—'}</dd></div>
        <div class="pass-field"><dt>Boş koltuk</dt><dd class="tnum">${b.free}</dd></div>
      </dl>
      <div class="pass-perf" aria-hidden="true"></div>
      <div class="pass-seg flex items-end justify-between gap-3">
        <div class="pass-code">
          <div>GÜN&nbsp;&nbsp;${esc(sheet)}</div>
          <div>BLN&nbsp;&nbsp;${esc(b.code)}-${String(b.used).padStart(2, '0')}/${b.cap}</div>
          <div>RZV&nbsp;&nbsp;${b.reservations} rezervasyon</div>
        </div>
        <a href="#/manifest" class="btn-secondary !px-3 !py-2 text-sm">Manifesto <span class="material-symbols-outlined text-[18px]">arrow_forward</span></a>
      </div>
    </div>`;
}

// ─── Plan dosyası yokken ───
function showEmptyState(token = renderId) {
  if (!isCurrent(token)) return;
  const title = document.getElementById('dash-title');
  if (title) title.textContent = 'Uçuş planı bağlı değil';
  const todo = document.getElementById('dash-todo');
  if (todo) {
    todo.innerHTML = `
      <div class="px-5 py-8">
        <p class="text-on-surface mb-1">İrtifa, arkadaşınızın aylık uçuş planlama Excel dosyası üzerinde çalışır.</p>
        <p class="text-on-surface-variant text-sm mb-6">Yeni bir aylık dosya oluşturun ya da var olan dosyayı bağlayın.</p>
        <div class="flex flex-wrap gap-3">
          <button class="btn-primary" onclick="window.__dashImportPlan()"><span class="material-symbols-outlined text-[19px]">link</span> Mevcut Excel dosyasını bağla</button>
          <button class="btn-secondary" onclick="window.__dashCreatePlan()"><span class="material-symbols-outlined text-[19px]">add</span> Yeni aylık dosya oluştur</button>
        </div>
      </div>`;
  }
  ['dash-metrics', 'dash-board', 'dash-pass'].forEach((id) => { const el = document.getElementById(id); if (el) el.innerHTML = ''; });
  const metrics = document.getElementById('dash-metrics');
  if (metrics) metrics.innerHTML = '<div class="col-span-full bg-panel px-5 py-8 text-on-surface-variant text-sm">Plan bağlanınca koltuk ve yolcu sayıları burada görünür.</div>';
}

window.__dashCreatePlan = async function() {
  const now = new Date();
  modal.open('Yeni aylık uçuş planı', `
    <div class="space-y-4">
      <div class="form-group">
        <label class="form-label" for="dash-modal-year">Yıl</label>
        <select id="dash-modal-year" class="form-select">
          <option value="${now.getFullYear()}">${now.getFullYear()}</option>
          <option value="${now.getFullYear() + 1}">${now.getFullYear() + 1}</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label" for="dash-modal-month">Ay</label>
        <select id="dash-modal-month" class="form-select">
          ${TR_MONTHS.map((name, i) => `<option value="${i + 1}" ${now.getMonth() === i ? 'selected' : ''}>${name}</option>`).join('')}
        </select>
      </div>
    </div>
  `, `
    <button class="btn-secondary" onclick="window.__closeModal()">Vazgeç</button>
    <button class="btn-primary" onclick="window.__dashDoCreatePlan()">Oluştur ve kaydet</button>
  `);
};

window.__dashDoCreatePlan = async function() {
  const y = parseInt(document.getElementById('dash-modal-year').value, 10);
  const m = parseInt(document.getElementById('dash-modal-month').value, 10);
  window.__closeModal();
  try {
    const res = await api.post('/api/planning/generate-monthly', { year: y, month: m });
    if (res.success) {
      toast.success('Plan oluşturuldu', res.message);
      await loadDashboard(renderId);
    } else if (res.message !== 'İptal edildi') {
      toast.error('Plan oluşturulamadı', res.message);
    }
  } catch (err) {
    toast.error('Plan oluşturulamadı', err.message);
  }
};

window.__dashImportPlan = async function() {
  try {
    const res = await api.post('/api/planning/import-existing', {});
    if (res.success) {
      toast.success('Dosya bağlandı', res.message);
      await loadDashboard(renderId);
    } else if (res.message !== 'İptal edildi') {
      toast.error('Dosya bağlanamadı', res.message);
    }
  } catch (err) {
    toast.error('Dosya bağlanamadı', err.message);
  }
};

function esc(value) {
  return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
