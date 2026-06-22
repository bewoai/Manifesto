import { api, toast, renderHeader } from '/app.js';

export async function render(container) {
  renderHeader('Operations Dashboard', 'Ucus gunu durumu, hava riski ve hizli islemler');

  container.innerHTML = `
    <!-- Hero Section -->
    <div class="relative w-full overflow-hidden rounded-[40px] p-8 md:p-12 mb-8 glass-panel min-h-[320px] flex flex-col justify-center shadow-2xl">
      <div class="absolute inset-0 z-0 overflow-hidden rounded-[40px]">
        <div class="absolute -top-24 -right-24 w-96 h-96 bg-primary/30 liquid-bg blob-shape"></div>
        <div class="absolute -bottom-24 -left-24 w-96 h-96 bg-primary-container/20 liquid-bg blob-shape" style="animation-delay: -5s"></div>
      </div>
      
      <div class="relative z-10">
        <h2 id="ops-title" class="font-headline text-3xl md:text-5xl text-primary mb-4 drop-shadow-md">Operasyon durumu yukleniyor</h2>
        <p id="ops-summary" class="text-on-surface-variant text-lg md:text-xl mb-8 max-w-2xl">Hava verisi ve sistem durumu kontrol ediliyor.</p>
        
        <div class="flex flex-wrap gap-4">
          <a href="#/weather" class="btn-primary flex items-center gap-2">
            <span class="material-symbols-outlined">calendar_month</span>
            Hava Takvimi
          </a>
          <button class="btn-secondary flex items-center gap-2" onclick="window.__dashRefresh()">
            <span class="material-symbols-outlined">refresh</span>
            Yenile
          </button>
        </div>
      </div>
    </div>

    <!-- Ticker -->
    <div class="flex flex-wrap gap-3 mb-8" id="ops-ticker">
      <div class="badge badge-amber text-sm px-4 py-2 flex items-center gap-2"><span class="material-symbols-outlined text-base">air</span>WIND STATUS: --</div>
      <div class="badge badge-blue text-sm px-4 py-2 flex items-center gap-2"><span class="material-symbols-outlined text-base">location_on</span>GOREME VALLEY: --</div>
      <div class="badge badge-green text-sm px-4 py-2 flex items-center gap-2"><span class="material-symbols-outlined text-base">update</span>NEXT CHECK: 30 DK</div>
    </div>

    <!-- Metrics -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8" id="ops-metrics">
      ${skeletonCards(4)}
    </div>

    <!-- Layout -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
      
      <!-- Hizli Ucus Islemleri -->
      <div class="card flex flex-col animate-fade-in">
        <div class="card-header">
          <div class="card-title">
            <span class="material-symbols-outlined">map</span>
            Hizli Ucus Islemleri
          </div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 flex-1">
          <a href="#/passport" class="glass-panel p-5 rounded-3xl hover:bg-white/5 border border-white/5 hover:border-primary/30 transition-all flex flex-col items-start gap-3 group">
            <div class="w-12 h-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center group-hover:scale-110 transition-transform">
              <span class="material-symbols-outlined text-2xl">document_scanner</span>
            </div>
            <div>
              <strong class="text-on-surface block mb-1">Pasaport Tara</strong>
              <span class="text-on-surface-variant text-xs">MRZ oku ve rezervasyon olustur</span>
            </div>
          </a>
          <a href="#/planning" class="glass-panel p-5 rounded-3xl hover:bg-white/5 border border-white/5 hover:border-primary/30 transition-all flex flex-col items-start gap-3 group">
            <div class="w-12 h-12 rounded-2xl bg-primary-container/10 text-primary-container flex items-center justify-center group-hover:scale-110 transition-transform">
              <span class="material-symbols-outlined text-2xl">edit_calendar</span>
            </div>
            <div>
              <strong class="text-on-surface block mb-1">Planlama Ac</strong>
              <span class="text-on-surface-variant text-xs">Rezervasyon bloklarini yonet</span>
            </div>
          </a>
          <a href="#/manifest" class="glass-panel p-5 rounded-3xl hover:bg-white/5 border border-white/5 hover:border-primary/30 transition-all flex flex-col items-start gap-3 group">
            <div class="w-12 h-12 rounded-2xl bg-secondary-container/10 text-secondary-container flex items-center justify-center group-hover:scale-110 transition-transform">
              <span class="material-symbols-outlined text-2xl">ios_share</span>
            </div>
            <div>
              <strong class="text-on-surface block mb-1">Manifesto Uret</strong>
              <span class="text-on-surface-variant text-xs">Balon bazli Excel export</span>
            </div>
          </a>
          <a href="#/weather" class="glass-panel p-5 rounded-3xl hover:bg-white/5 border border-white/5 hover:border-primary/30 transition-all flex flex-col items-start gap-3 group">
            <div class="w-12 h-12 rounded-2xl bg-blue-500/10 text-blue-400 flex items-center justify-center group-hover:scale-110 transition-transform">
              <span class="material-symbols-outlined text-2xl">air</span>
            </div>
            <div>
              <strong class="text-on-surface block mb-1">Weather Charts</strong>
              <span class="text-on-surface-variant text-xs">Risk takvimi ve son olcumler</span>
            </div>
          </a>
        </div>
      </div>

      <!-- Operational Safety -->
      <div class="card flex flex-col animate-fade-in">
        <div class="card-header">
          <div class="card-title">
            <span class="material-symbols-outlined">health_and_safety</span>
            Operational Safety
          </div>
          <span class="badge badge-blue">LIVE</span>
        </div>
        <div class="grid gap-4 flex-1 content-start" id="safety-grid">
          <div class="skeleton skeleton-card"></div>
          <div class="skeleton skeleton-card"></div>
        </div>
      </div>
    </div>

    <!-- Sistem Durumu -->
    <div class="card mb-8 animate-fade-in">
      <div class="card-header">
        <div class="card-title">
          <span class="material-symbols-outlined">memory</span>
          Sistem Durumu
        </div>
        <a href="#/settings" class="btn-ghost text-sm flex items-center gap-1">
          <span class="material-symbols-outlined text-sm">settings</span>
          Ayarlar
        </a>
      </div>
      <div id="system-status" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        ${skeletonCards(4)}
      </div>
    </div>
  `;

  await loadDashboard();
}

window.__dashRefresh = function() {
  loadDashboard(true);
};

function skeletonCards(n) {
  return Array(n).fill('').map(() => `
    <div class="card flex flex-col gap-3 animate-pulse">
      <div class="skeleton" style="width:42px;height:18px"></div>
      <div class="skeleton skeleton-title mt-2"></div>
      <div class="skeleton skeleton-text"></div>
    </div>
  `).join('');
}

async function loadDashboard(force = false) {
  try {
    const [stats, settings, weather] = await Promise.all([
      api.get('/api/stats'),
      api.get('/api/settings'),
      force ? api.post('/api/weather/refresh', {}) : api.get('/api/weather/status'),
    ]);
    renderWeather(weather);
    renderSystem(stats, settings);
    if (weather.error) toast.warning('Hava verisi', 'Yeni veri alinamadi, son kayit gosteriliyor');
  } catch (err) {
    toast.error('Dashboard yuklenemedi', err.message);
  }
}

function renderWeather(data) {
  const titleEl = document.getElementById('ops-title');
  const summaryEl = document.getElementById('ops-summary');
  const tickerEl = document.getElementById('ops-ticker');
  const metrics = document.getElementById('ops-metrics');
  const safety = document.getElementById('safety-grid');
  if (!titleEl || !summaryEl || !tickerEl || !metrics || !safety) return;

  const current = data.current || {};
  const decision = data.decision || {};
  const title = decision.title || 'Hava verisi bekleniyor';
  const summary = decision.summary || 'Yarim saatlik olcum basladiginda karar burada gorunecek.';

  titleEl.textContent = title;
  summaryEl.textContent = summary;
  tickerEl.innerHTML = `
    <div class="badge badge-amber text-sm px-4 py-2 flex items-center gap-2">
      <span class="material-symbols-outlined text-base">air</span>
      WIND STATUS: ${kmh(current.wind_speed_kmh)}
    </div>
    <div class="badge badge-blue text-sm px-4 py-2 flex items-center gap-2">
      <span class="material-symbols-outlined text-base">location_on</span>
      GOREME VALLEY: ${statusLabel(decision.flight_status || current.flight_status)}
    </div>
    <div class="badge badge-green text-sm px-4 py-2 flex items-center gap-2">
      <span class="material-symbols-outlined text-base">update</span>
      LAST CHECK: ${data.updated_at ? fmtTime(data.updated_at) : '--'}
    </div>
  `;

  metrics.innerHTML = [
    metric('TODAY STATUS', statusLabel(decision.flight_status), decision.risk_level || 'unknown'),
    metric('CURRENT WIND', kmh(current.wind_speed_kmh), '10m'),
    metric('WIND GUST', kmh(current.wind_gust_kmh), 'gust'),
    metric('VISIBILITY', visibility(current.visibility_m), 'valley'),
  ].join('');

  safety.innerHTML = `
    <div class="glass-panel rounded-3xl p-6 border-l-4 ${riskClass(decision.risk_level)} flex flex-col gap-2 relative overflow-hidden group">
      <div class="absolute -right-4 -bottom-4 text-white/5 group-hover:scale-110 transition-transform">
        <span class="material-symbols-outlined" style="font-size: 100px; font-variation-settings: 'FILL' 1;">
          ${decision.flight_status === 'no_go' ? 'block' : 'flight_takeoff'}
        </span>
      </div>
      <span class="text-xs font-bold text-on-surface-variant uppercase tracking-wider relative z-10">FLIGHT DECISION</span>
      <strong class="text-3xl font-headline text-on-surface relative z-10">${statusLabel(decision.flight_status)}</strong>
      <small class="text-sm text-on-surface-variant relative z-10">${summary}</small>
    </div>
    <div class="glass-panel rounded-3xl p-6 border-l-4 border-l-blue-500 flex flex-col gap-2 relative overflow-hidden group">
      <div class="absolute -right-4 -bottom-4 text-white/5 group-hover:scale-110 transition-transform">
        <span class="material-symbols-outlined" style="font-size: 100px; font-variation-settings: 'FILL' 1;">cloud</span>
      </div>
      <span class="text-xs font-bold text-on-surface-variant uppercase tracking-wider relative z-10">PRECIP / CLOUD</span>
      <strong class="text-3xl font-headline text-on-surface relative z-10">${mm(current.precipitation_mm)} / ${pct(current.cloud_cover_pct)}</strong>
      <small class="text-sm text-on-surface-variant relative z-10">Weather API forecast</small>
    </div>
  `;
}

function renderSystem(stats, settings) {
  const el = document.getElementById('system-status');
  if (!el) return;
  el.innerHTML = `
    <div class="glass-panel p-6 rounded-3xl border border-white/5 hover:border-white/10 transition-colors flex flex-col gap-2">
      <span class="text-xs font-bold text-on-surface-variant uppercase tracking-wider flex items-center gap-2">
        <span class="material-symbols-outlined text-base">today</span>
        Ucus Gunu
      </span>
      <strong class="text-3xl font-headline text-on-surface">${stats.sheet_count || 0}</strong>
    </div>
    <div class="glass-panel p-6 rounded-3xl border border-white/5 hover:border-white/10 transition-colors flex flex-col gap-2">
      <span class="text-xs font-bold text-on-surface-variant uppercase tracking-wider flex items-center gap-2">
        <span class="material-symbols-outlined text-base">verified_user</span>
        Onayli Pasaport
      </span>
      <strong class="text-3xl font-headline text-on-surface">${stats.extraction_by_status?.approved || 0}</strong>
    </div>
    <div class="glass-panel p-6 rounded-3xl border border-white/5 hover:border-white/10 transition-colors flex flex-col gap-2">
      <span class="text-xs font-bold text-on-surface-variant uppercase tracking-wider flex items-center gap-2">
        <span class="material-symbols-outlined text-base">database</span>
        Veri Kaynagi
      </span>
      <strong class="text-xl font-headline text-on-surface mt-1">${settings.data_source === 'google_sheets' ? 'Google Sheets' : 'Excel'}</strong>
    </div>
    <div class="glass-panel p-6 rounded-3xl border border-white/5 hover:border-white/10 transition-colors flex flex-col gap-2">
      <span class="text-xs font-bold text-on-surface-variant uppercase tracking-wider flex items-center gap-2">
        <span class="material-symbols-outlined text-base">partly_cloudy_day</span>
        Weather API
      </span>
      <strong class="text-xl font-headline text-on-surface mt-1">${settings.weather_enabled ? settings.weather_provider : 'Kapali'}</strong>
    </div>
  `;
}

function metric(label, value, sub) {
  let icon = 'bar_chart';
  if (label.includes('STATUS')) icon = 'flight_takeoff';
  if (label.includes('WIND')) icon = 'air';
  if (label.includes('VISIBILITY')) icon = 'visibility';

  return `
    <div class="card relative overflow-hidden group">
      <div class="absolute -right-4 -bottom-4 text-white/5 group-hover:scale-110 transition-transform">
        <span class="material-symbols-outlined" style="font-size: 80px; font-variation-settings: 'FILL' 1;">
          ${icon}
        </span>
      </div>
      <div class="text-xs font-bold text-on-surface-variant uppercase tracking-wider mb-2 relative z-10">${label}</div>
      <div class="text-3xl font-headline text-on-surface mb-1 relative z-10">${value || '--'}</div>
      <div class="text-sm text-primary relative z-10">${sub || ''}</div>
    </div>
  `;
}

function statusLabel(status) {
  return {
    flyable: 'Uygun',
    caution: 'Riskli',
    no_go: 'Ucus Yok',
    unknown: 'Beklemede',
  }[status] || 'Beklemede';
}

function riskClass(risk) {
  return {
    low: 'border-l-green-500',
    medium: 'border-l-yellow-500',
    high: 'border-l-red-500',
  }[risk] || 'border-l-surface-variant';
}

function kmh(v) { return v == null ? '--' : `${Number(v).toFixed(1)} km/h`; }
function mm(v) { return v == null ? '--' : `${Number(v).toFixed(1)} mm`; }
function pct(v) { return v == null ? '--' : `%${Number(v).toFixed(0)}`; }
function visibility(v) { return v == null ? '--' : `${(Number(v) / 1000).toFixed(1)} km`; }
function fmtTime(v) { return new Date(v).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }); }

