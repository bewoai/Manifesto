import { api, toast, renderHeader } from '/app.js';

let state = { data: null };

export async function render(container) {
  renderHeader('Hava Durumu', 'Yarım saatlik takip, risk takvimi ve uçuş kararı');

  container.innerHTML = `
    <div class="space-y-6">
      <div class="weather-hero animate-fade-in">
        <div class="flex flex-col sm:flex-row justify-between items-start gap-4 w-full">
          <div>
            <div class="text-xs font-bold tracking-widest text-primary mb-2">BALON UÇUŞ OPERASYONU</div>
            <h2 id="weather-title" class="font-headline text-headline-md text-on-surface mb-2">Hava verisi yükleniyor</h2>
            <p id="weather-summary" class="text-on-surface-variant">Rüzgar, ani rüzgar, görüş ve yağış kontrol ediliyor.</p>
          </div>
          <div class="flex items-center gap-3 shrink-0">
            <span class="badge badge-blue" id="weather-updated">--</span>
            <button class="btn-primary flex items-center gap-2" onclick="window.__refreshWeather()">
              <span class="material-symbols-outlined text-[18px]">refresh</span>
              Yenile
            </button>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4" id="weather-metrics">
        ${metricSkeleton(4)}
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="card animate-fade-in">
          <div class="card-header">
            <div class="card-title">
              <span class="material-symbols-outlined">calendar_month</span>
              7 Günlük Risk Takvimi
            </div>
            <span class="text-sm text-on-surface-variant">03:30 - 07:30</span>
          </div>
          <div class="weather-calendar" id="weather-calendar"></div>
        </div>
        <div class="card animate-fade-in">
          <div class="card-header">
            <div class="card-title">
              <span class="material-symbols-outlined">history</span>
              Son Ölçümler
            </div>
            <span class="text-sm text-on-surface-variant">30 dk takip</span>
          </div>
          <div class="weather-history" id="weather-history"></div>
        </div>
      </div>
    </div>
  `;

  await loadWeather();
}

function metricSkeleton(n) {
  return Array(n).fill('').map(() => `
    <div class="weather-metric animate-pulse">
      <div class="skeleton" style="width:44px;height:18px"></div>
      <div class="skeleton skeleton-title mt-4"></div>
      <div class="skeleton skeleton-text"></div>
    </div>
  `).join('');
}

async function loadWeather(force = false) {
  try {
    const data = force
      ? await api.post('/api/weather/refresh', {})
      : await api.get('/api/weather/status');
    state.data = data;
    renderWeather(data);
    if (data.error) toast.warning('Hava verisi', 'Yeni veri alınamadı, son kayıt gösteriliyor');
  } catch (err) {
    toast.error('Hava durumu alınamadı', err.message);
  }
}

window.__refreshWeather = function() {
  loadWeather(true);
};

function renderWeather(data) {
  const current = data.current || {};
  const decision = data.decision || {};
  const status = decision.flight_status || current.flight_status || 'unknown';
  const risk = decision.risk_level || current.risk_level || 'unknown';

  const titleEl = document.getElementById('weather-title');
  if (!titleEl) return;

  titleEl.textContent = decision.title || statusLabel(status);
  document.getElementById('weather-summary').textContent = decision.summary || current.summary || 'Veri bekleniyor.';
  document.getElementById('weather-updated').textContent = data.updated_at ? `Son: ${fmtTime(data.updated_at)}` : 'Ölçüm yok';

  const hero = document.querySelector('.weather-hero');
  hero.classList.remove('risk-low', 'risk-medium', 'risk-high', 'risk-unknown');
  hero.classList.add(`risk-${risk}`);

  const metrics = document.getElementById('weather-metrics');
  metrics.innerHTML = [
    metric('Rüzgar', kmh(current.wind_speed_kmh), '10m hız', riskClass(current.wind_speed_kmh, 14, 22)),
    metric('Ani Rüzgar', kmh(current.wind_gust_kmh), 'gust', riskClass(current.wind_gust_kmh, 22, 30)),
    metric('Görüş', visibility(current.visibility_m), 'metre', riskClassReverse(current.visibility_m, 5000, 2500)),
    metric('Yağış', mm(current.precipitation_mm), 'mm', riskClass(current.precipitation_mm, 0.1, 1)),
  ].join('');

  renderCalendar(data.forecast || [], data.daily_forecast || []);
  renderHistory(data.history || []);
}

function metric(label, value, sub, cls) {
  return `
    <div class="weather-metric animate-fade-in ${cls}">
      <div class="metric-label">${label}</div>
      <div class="metric-value">${value}</div>
      <div class="metric-sub">${sub}</div>
    </div>
  `;
}

function renderCalendar(points, dailyForecast = []) {
  const el = document.getElementById('weather-calendar');
  if (!points.length && !dailyForecast.length) {
    el.innerHTML = `<div class="empty-state">
      <span class="material-symbols-outlined empty-icon text-on-surface-variant/50">calendar_today</span>
      <div class="empty-title">Tahmin yok</div>
      <div class="empty-desc">API bağlantısı kurulduğunda burada saatlik risk takvimi görünecek.</div>
    </div>`;
    return;
  }

  // Filter to 03:30–07:30 flight window per day and group by date
  const grouped = {};
  for (const p of points) {
    const d = new Date(p.measured_at);
    const h = d.getHours();
    const m = d.getMinutes();
    const totalMin = h * 60 + m;
    // 03:30 = 210 min, 07:30 = 450 min
    if (totalMin < 210 || totalMin > 450) continue;
    const dayKey = isoDate(d);
    if (!grouped[dayKey]) grouped[dayKey] = [];
    grouped[dayKey].push(p);
  }

  const days = dailyForecast.length
    ? dailyForecast.slice(0, 7)
    : Object.keys(grouped).slice(0, 7).map(date => ({
        date,
        flight_status: worstStatus(grouped[date]),
        risk_level: worstRisk(grouped[date]),
        summary: grouped[date][0]?.summary || 'Saatlik tahmin var.',
      }));

  if (!days.length) {
    el.innerHTML = `<div class="empty-state">
      <span class="material-symbols-outlined empty-icon text-on-surface-variant/50">event_busy</span>
      <div class="empty-title">Uçuş penceresi verisi yok</div>
      <div class="empty-desc">03:30–07:30 aralığı için tahmin bulunamadı.</div>
    </div>`;
    return;
  }

  el.innerHTML = days.map(day => {
    const slots = grouped[day.date] || [];
    return `
    <div class="calendar-day-label ${day.risk_level || 'unknown'}">
      <div>
        <span>${fmtDateLabel(day.date)}</span>
        <small>${day.window_start || '03:30'} - ${day.window_end || '07:30'}</small>
      </div>
      <strong>${statusLabel(day.flight_status)}</strong>
    </div>
    <div class="calendar-day-slots mt-2 mb-4 last:mb-0">
      ${slots.length ? slots.map(p => `
        <div class="weather-slot ${p.risk_level || 'unknown'}">
          <div class="slot-time">${fmtTime(p.measured_at)}</div>
          <div class="slot-status">${statusLabel(p.flight_status)}</div>
          <div class="slot-values">${kmh(p.wind_speed_kmh)} / ${kmh(p.wind_gust_kmh)}</div>
        </div>
      `).join('') : `
        <div class="weather-slot unknown">
          <div class="slot-time">Tahmin yok</div>
          <div class="slot-status">${day.summary || 'Veri bekleniyor'}</div>
          <div class="slot-values">03:30 - 07:30</div>
        </div>
      `}
    </div>
  `;
  }).join('');
}

function renderHistory(items) {
  const el = document.getElementById('weather-history');
  if (!items.length) {
    el.innerHTML = `<div class="empty-state">
      <span class="material-symbols-outlined empty-icon text-on-surface-variant/50">history</span>
      <div class="empty-title">Ölçüm yok</div>
      <div class="empty-desc">İlk otomatik ölçümden sonra liste dolacak.</div>
    </div>`;
    return;
  }
  el.innerHTML = items.slice(0, 12).map(p => `
    <div class="history-row border-b border-white/5 last:border-0 hover:bg-white/5 rounded px-2 -mx-2 transition-colors">
      <span>${fmtDayTime(p.measured_at)}</span>
      <strong>${statusLabel(p.flight_status)}</strong>
      <span>${kmh(p.wind_speed_kmh)} / ${kmh(p.wind_gust_kmh)}</span>
    </div>
  `).join('');
}

function statusLabel(status) {
  return {
    flyable: 'Uygun',
    caution: 'Riskli',
    no_go: 'Uçuş Yok',
    unknown: 'Beklemede',
  }[status] || 'Beklemede';
}

function worstRisk(points) {
  const risks = new Set((points || []).map(p => p.risk_level));
  if (risks.has('high')) return 'high';
  if (risks.has('medium')) return 'medium';
  if (risks.has('low')) return 'low';
  return 'unknown';
}

function worstStatus(points) {
  const statuses = new Set((points || []).map(p => p.flight_status));
  if (statuses.has('no_go')) return 'no_go';
  if (statuses.has('caution')) return 'caution';
  if (statuses.has('flyable')) return 'flyable';
  return 'unknown';
}

function riskClass(v, warn, stop) {
  if (v == null) return 'risk-unknown';
  if (v >= stop) return 'risk-high';
  if (v >= warn) return 'risk-medium';
  return 'risk-low';
}

function riskClassReverse(v, warn, stop) {
  if (v == null) return 'risk-unknown';
  if (v < stop) return 'risk-high';
  if (v < warn) return 'risk-medium';
  return 'risk-low';
}

function kmh(v) { return v == null ? '--' : `${Number(v).toFixed(1)} km/h`; }
function mm(v) { return v == null ? '--' : `${Number(v).toFixed(1)} mm`; }
function visibility(v) { return v == null ? '--' : `${(Number(v) / 1000).toFixed(1)} km`; }
function isoDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}
function fmtDateLabel(v) {
  return new Date(`${v}T12:00:00`).toLocaleDateString('tr-TR', {
    weekday: 'long',
    day: '2-digit',
    month: '2-digit',
  });
}
function fmtTime(v) { return new Date(v).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }); }
function fmtDayTime(v) {
  return new Date(v).toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}
