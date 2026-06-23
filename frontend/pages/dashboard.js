import { api, toast, renderHeader } from '/app.js';
import { icon3d } from '/icons.js';

export async function render(container) {
  renderHeader('Operasyon Paneli', 'Uçuş günü durumu, hava riski ve hızlı işlemler');

  container.innerHTML = `
    <!-- ░░ Hava Durumu Şeridi (sade + ikonlu + uçuş tahmini) ░░ -->
    <div id="wx-strip" class="mb-6">${stripSkeleton()}</div>

    <!-- ░░ Hero — Kapadokya balon illüstrasyonu ░░ -->
    <div class="relative w-full overflow-hidden rounded-[40px] mb-8 glass-panel min-h-[300px] flex">
      <div class="absolute inset-0 z-0">${heroIllustration()}</div>
      <div class="absolute inset-0 z-[1]" style="background:linear-gradient(100deg,#181225 8%,rgba(24,18,37,.82) 42%,rgba(24,18,37,.15) 72%,transparent 100%)"></div>
      <div class="relative z-10 p-8 md:p-12 max-w-2xl flex flex-col justify-center">
        <span class="inline-flex w-fit items-center gap-2 text-xs font-semibold tracking-wider uppercase text-sunrise bg-sunrise/10 border border-sunrise/20 rounded-full px-3 py-1 mb-5">
          <span class="material-symbols-outlined text-sm">location_on</span> Kapadokya • Göreme Vadisi
        </span>
        <h2 id="ops-title" class="font-headline text-3xl md:text-5xl text-on-surface mb-3 leading-tight drop-shadow-md">Operasyon durumu yükleniyor</h2>
        <p id="ops-summary" class="text-on-surface-variant text-base md:text-lg mb-7 max-w-xl">Hava verisi ve sistem durumu kontrol ediliyor.</p>
        <div class="flex flex-wrap gap-3">
          <a href="#/weather" class="btn-primary flex items-center gap-2">
            <span class="material-symbols-outlined">calendar_month</span> Hava Takvimi
          </a>
          <button class="btn-secondary flex items-center gap-2" onclick="window.__dashRefresh()">
            <span class="material-symbols-outlined">refresh</span> Yenile
          </button>
        </div>
      </div>
    </div>

    <!-- ░░ Hızlı İşlemler ░░ -->
    <h3 class="font-headline text-xl text-on-surface mb-4 px-1">Hızlı Uçuş İşlemleri</h3>
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
      ${actionCard('passport', 'Pasaport Tara', 'MRZ oku, kimlik doldur')}
      ${actionCard('planning', 'Planlama Aç', 'Rezervasyon bloklarını yönet')}
      ${actionCard('manifest', 'Manifesto Üret', 'Balon bazlı Excel export')}
      ${actionCard('weather', 'Hava Takvimi', 'Risk takvimi ve ölçümler')}
    </div>

    <!-- ░░ Operasyon Metrikleri ░░ -->
    <h3 class="font-headline text-xl text-on-surface mb-4 px-1">Güncel Hava Metrikleri</h3>
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10" id="ops-metrics">${stripCards(4)}</div>

    <!-- ░░ Sistem Durumu ░░ -->
    <div class="flex items-center justify-between mb-4 px-1">
      <h3 class="font-headline text-xl text-on-surface">Sistem Durumu</h3>
      <a href="#/settings" class="btn-ghost text-sm flex items-center gap-1 px-3 w-auto rounded-full">
        <span class="material-symbols-outlined text-sm">settings</span> Ayarlar
      </a>
    </div>
    <div id="system-status" class="grid grid-cols-2 lg:grid-cols-4 gap-4">${stripCards(4)}</div>
  `;

  await loadDashboard();
}

window.__dashRefresh = function () { loadDashboard(true); };

// ═══════════════════════════ veri ═══════════════════════════

async function loadDashboard(force = false) {
  try {
    const [stats, settings, weather] = await Promise.all([
      api.get('/api/stats'),
      api.get('/api/settings'),
      force ? api.post('/api/weather/refresh', {}) : api.get('/api/weather/status'),
    ]);
    renderStrip(weather);
    renderHero(weather);
    renderMetrics(weather);
    renderSystem(stats, settings);
    if (weather.error) toast.warning('Hava verisi', 'Yeni veri alınamadı, son kayıt gösteriliyor');
  } catch (err) {
    toast.error('Panel yüklenemedi', err.message);
  }
}

function renderStrip(data) {
  const el = document.getElementById('wx-strip');
  if (!el) return;
  const c = data.current || {};
  const d = data.decision || {};
  const cond = wmo(c.weather_code);
  const status = d.flight_status || c.flight_status || 'unknown';
  el.innerHTML = `
    <div class="wx-strip">
      <div class="wx-now">
        ${icon3d(cond.icon, 46)}
        <div>
          <div class="wx-temp">${temp(c.temperature_c)}</div>
          <div class="wx-cond">${cond.label} • Göreme</div>
        </div>
      </div>
      <div class="wx-sep"></div>
      <div class="wx-metric">${icon3d('wind', 30)}<div><div class="lbl">Rüzgar</div><div class="val">${kmh(c.wind_speed_kmh)}</div></div></div>
      <div class="wx-metric">${icon3d('alert', 30)}<div><div class="lbl">Hamle</div><div class="val">${kmh(c.wind_gust_kmh)}</div></div></div>
      <div class="wx-metric">${icon3d('visibility', 30)}<div><div class="lbl">Görüş</div><div class="val">${visibility(c.visibility_m)}</div></div></div>
      <div class="wx-verdict ${status}">
        ${icon3d(status === 'no_go' ? 'alert' : status === 'unknown' ? 'cloud' : 'balloon', 38)}
        <div>
          <div class="v-cap">Uçuş Tahmini</div>
          <div class="v-status">${statusLabel(status)}</div>
          <div class="v-window">Sabah penceresi 03:30–07:30</div>
        </div>
      </div>
    </div>
  `;
}

function renderHero(data) {
  const d = data.decision || {};
  setText('ops-title', d.title || 'Hava verisi bekleniyor');
  setText('ops-summary', d.summary || 'Yarım saatlik ölçüm başladığında karar burada görünecek.');
}

function renderMetrics(data) {
  const el = document.getElementById('ops-metrics');
  if (!el) return;
  const c = data.current || {};
  const d = data.decision || {};
  el.innerHTML = [
    metric('today', 'Bugün', statusLabel(d.flight_status), d.risk_level || '—'),
    metric('wind', 'Rüzgar', kmh(c.wind_speed_kmh), '10m'),
    metric('cloud', 'Yağış / Bulut', `${mm(c.precipitation_mm)} · ${pct(c.cloud_cover_pct)}`, 'tahmin'),
    metric('visibility', 'Görüş', visibility(c.visibility_m), 'vadi'),
  ].join('');
}

function renderSystem(stats, settings) {
  const el = document.getElementById('system-status');
  if (!el) return;
  el.innerHTML = [
    metric('planning', 'Uçuş Günü', stats.sheet_count || 0, 'kayıtlı sayfa'),
    metric('passport', 'Onaylı Pasaport', stats.extraction_by_status?.approved || 0, 'doğrulandı'),
    metric('lists', 'Veri Kaynağı', settings.data_source === 'google_sheets' ? 'Sheets' : 'Excel', 'aktif'),
    metric('weather', 'Hava API', settings.weather_enabled ? (settings.weather_provider || 'açık') : 'Kapalı', 'sağlayıcı'),
  ].join('');
}

// ═══════════════════════════ parçalar ═══════════════════════════

function actionCard(icon, title, sub) {
  const route = { passport: 'passport', planning: 'planning', manifest: 'manifest', weather: 'weather' }[icon];
  return `
    <a href="#/${route}" class="glass-panel rounded-[28px] p-5 flex flex-col gap-4 group hover:border-white/20 hover:-translate-y-1 transition-all">
      <span class="block transition-transform group-hover:scale-110 group-hover:-rotate-3 w-fit">${icon3d(icon, 52)}</span>
      <div>
        <strong class="block text-on-surface text-[15px] mb-0.5">${title}</strong>
        <span class="text-on-surface-variant/80 text-xs">${sub}</span>
      </div>
    </a>`;
}

function metric(icon, label, value, sub) {
  return `
    <div class="glass-panel rounded-[28px] p-5 flex items-start gap-4">
      <span class="block mt-0.5">${icon3d(icon, 40)}</span>
      <div class="min-w-0">
        <div class="text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant/70 mb-1">${label}</div>
        <div class="font-headline text-2xl text-on-surface leading-none truncate">${value ?? '--'}</div>
        <div class="text-xs text-on-surface-variant/60 mt-1">${sub || ''}</div>
      </div>
    </div>`;
}

function stripSkeleton() {
  return `<div class="glass-panel rounded-[28px] h-[88px] animate-pulse"></div>`;
}
function stripCards(n) {
  return Array(n).fill('').map(() => `<div class="glass-panel rounded-[28px] h-[104px] animate-pulse"></div>`).join('');
}

// ═══════════════════════════ Kapadokya illüstrasyonu ═══════════════════════════

function heroIllustration() {
  const chimneys = [chimney(470, 300, 46, 150), chimney(560, 300, 64, 210), chimney(640, 300, 40, 130), chimney(710, 300, 56, 175)];
  const balloons = [
    balloon(520, 120, 2.2, '#FF6B6B', '#ffb3a0'),
    balloon(630, 95, 2.7, '#FFC24B', '#ffe6ad'),
    balloon(700, 150, 1.9, '#36D6C3', '#aef2e9'),
    balloon(575, 185, 1.6, '#5BA8FF', '#bcd9ff'),
    balloon(665, 210, 1.4, '#F074C0', '#fbc4e7'),
    balloon(455, 150, 1.5, '#B493FF', '#ddccff'),
    balloon(745, 95, 1.3, '#FF9F5A', '#ffd6b0'),
  ];
  return `<svg viewBox="0 0 760 300" preserveAspectRatio="xMidYMid slice" class="w-full h-full" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <defs>
      <linearGradient id="hsky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#241a3a"/><stop offset=".5" stop-color="#6b3f63"/><stop offset="1" stop-color="#ffb070"/></linearGradient>
      <radialGradient id="hsun" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#ffeac4"/><stop offset=".45" stop-color="#ffb066" stop-opacity=".75"/><stop offset="1" stop-color="#ffb066" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="760" height="300" fill="url(#hsky)"/>
    <circle cx="600" cy="262" r="135" fill="url(#hsun)"/>
    <circle cx="600" cy="270" r="40" fill="#ffe9c2" opacity=".95"/>
    <g fill="#241326" opacity=".88">${chimneys.join('')}</g>
    ${balloons.join('')}
  </svg>`;
}

function chimney(x, baseY, w, h) {
  const top = baseY - h;
  return `<path d="M${x - w / 2},${baseY} C${x - w / 2.2},${baseY - h * 0.55} ${x - w / 6},${top + w * 0.5} ${x},${top + w * 0.5} C${x + w / 6},${top + w * 0.5} ${x + w / 2.2},${baseY - h * 0.55} ${x + w / 2},${baseY} Z"/>
    <ellipse cx="${x}" cy="${top + w * 0.5}" rx="${w * 0.46}" ry="${w * 0.26}" fill="#3a2240"/>`;
}

function balloon(cx, cy, s, color, light) {
  return `<g transform="translate(${cx} ${cy}) scale(${s})">
    <line x1="-2.4" y1="27" x2="-2" y2="33" stroke="#fff" stroke-opacity=".5" stroke-width=".5"/>
    <line x1="2.4" y1="27" x2="2" y2="33" stroke="#fff" stroke-opacity=".5" stroke-width=".5"/>
    <path d="M-2.6,33 h5.2 l-.7,3.3 a.8 .8 0 0 1 -.8 .6 h-2.2 a.8 .8 0 0 1 -.8 -.6 z" fill="#5a3a26"/>
    <path d="M0,-2 C-9,-2 -13.5,5 -13.5,12.6 C-13.5,20.6 -7,26.6 -2,28.7 L2,28.7 C7,26.6 13.5,20.6 13.5,12.6 C13.5,5 9,-2 0,-2 Z" fill="${color}"/>
    <path d="M0,-2 C-5,-2 -8.4,3 -9.4,9.2 C-7,4 -3,1 0.4,1 Z" fill="${light}" opacity=".55"/>
    <g stroke="#000" stroke-opacity=".13" stroke-width=".7" fill="none"><path d="M0,-1.6 V28.5"/><path d="M-6.2,-.4 C-9.4,6 -9.4,21 -5.2,27.7"/><path d="M6.2,-.4 C9.4,6 9.4,21 5.2,27.7"/></g>
  </g>`;
}

// ═══════════════════════════ yardımcılar ═══════════════════════════

function wmo(code) {
  if (code == null) return { label: 'Bilinmiyor', icon: 'cloud' };
  if (code === 0) return { label: 'Açık', icon: 'weather' };
  if (code <= 3) return { label: 'Parçalı bulutlu', icon: 'weather' };
  if (code === 45 || code === 48) return { label: 'Sisli', icon: 'visibility' };
  if (code >= 51 && code <= 67) return { label: 'Yağmurlu', icon: 'cloud' };
  if (code >= 71 && code <= 77) return { label: 'Karlı', icon: 'cloud' };
  if (code >= 80 && code <= 82) return { label: 'Sağanak', icon: 'cloud' };
  if (code >= 95) return { label: 'Fırtına', icon: 'alert' };
  return { label: 'Bulutlu', icon: 'cloud' };
}

function statusLabel(s) {
  return { flyable: 'Uygun', caution: 'Riskli', no_go: 'Uçuş Yok', unknown: 'Beklemede' }[s] || 'Beklemede';
}

function setText(id, txt) { const el = document.getElementById(id); if (el) el.textContent = txt; }
function temp(v) { return v == null ? '--°' : `${Math.round(Number(v))}°`; }
function kmh(v) { return v == null ? '--' : `${Number(v).toFixed(1)} km/h`; }
function mm(v) { return v == null ? '--' : `${Number(v).toFixed(1)} mm`; }
function pct(v) { return v == null ? '--' : `%${Number(v).toFixed(0)}`; }
function visibility(v) { return v == null ? '--' : `${(Number(v) / 1000).toFixed(1)} km`; }
