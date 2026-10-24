/* ═══════════════════════════════════════════════════════════════════
   Kapasite kuralları — balon başına kapasite, günlük balon sınırı, günlük toplam kapasite.
   Saf yardımcılar (DOM yok): Ayarlar, Ana sayfa, Planlama ve Pasaport ortak kullanır.
   Node ile test edilir: tests/test_capacity_rules_js.py
   ═══════════════════════════════════════════════════════════════════ */

export const DEFAULT_CAPACITY = 28;

/** Balonun kapasitesi: balona özel değer, yoksa günün/ayarın varsayılanı. */
export function capacityFor(source, code) {
  const own = source?.capacities?.[code];
  const n = Number(own);
  if (own !== undefined && own !== null && own !== '' && Number.isFinite(n) && n > 0) return n;
  return Number(source?.capacity) || DEFAULT_CAPACITY;
}

/** [{name, value}] → {ad: sayı}; boş, 0 ve geçersiz değerler atlanır. */
export function collectIntMap(entries = [], { upperKey = false } = {}) {
  const out = {};
  for (const { name, value } of entries) {
    const key = String(name ?? '').trim();
    const n = parseInt(String(value ?? '').trim(), 10);
    if (!key || !Number.isFinite(n) || n <= 0) continue;
    out[upperKey ? key.toUpperCase() : key] = n;
  }
  return out;
}

/** Günlük balon sınırı ölçüsü: "3/4 balon" (sınır varsa) ya da "5 balon". */
export function balloonLimitText(inUse, max, total) {
  const limit = Number(max) || 0;
  if (limit > 0) return `${Number(inUse) || 0}/${limit} balon`;
  return `${Number(total) || 0} balon`;
}

/**
 * Günün satılabilir koltukları. Günlük balon sınırı doluysa uçmayan balonlar sayılmaz
 * (sınıra yer varsa en büyük kapasiteli boş balonlar eklenir). Günlük toplam kapasite
 * (ör. 112 kişi) tanımlıysa koltuk ve boş yer onunla sınırlanır.
 * balloons: [{ code, cap, used }]. Dönüş: { seats, free, pax, usable: [kod] }.
 */
export function daySeats(balloons = [], { maxBalloons = 0, dailyCapacity = 0 } = {}) {
  const num = (v) => Number(v) || 0;
  const limit = num(maxBalloons);
  const flying = balloons.filter((b) => num(b.used) > 0);
  const idle = balloons.filter((b) => num(b.used) <= 0).sort((x, y) => num(y.cap) - num(x.cap));
  const usable = limit > 0 ? [...flying, ...idle.slice(0, Math.max(0, limit - flying.length))] : [...flying, ...idle];
  const pax = balloons.reduce((n, b) => n + num(b.used), 0);
  let seats = usable.reduce((n, b) => n + num(b.cap), 0);
  let free = usable.reduce((n, b) => n + Math.max(0, num(b.cap) - num(b.used)), 0);
  const cap = num(dailyCapacity);
  if (cap > 0) {
    seats = Math.min(seats, cap);
    free = Math.min(free, Math.max(0, cap - pax));
  }
  return { seats, free, pax, usable: usable.map((b) => b.code) };
}

export function isDailyCapacityExceeded(err) {
  return err?.status === 409 && err?.detail?.code === 'daily_capacity_exceeded';
}

/** 409 daily_capacity_exceeded için modal.confirm seçenekleri. esc: HTML kaçış fonksiyonu. */
export function dailyCapacityConfirmOptions(detail = {}, esc = (s) => String(s ?? '')) {
  const used = Number(detail.used) || 0;
  const pax = Number(detail.pax) || 0;
  const cap = Number(detail.capacity) || 0;
  const message = detail.message || 'Günlük kapasite aşılıyor.';
  const numbers = cap
    ? `<p class="text-sm text-on-surface-variant mt-2">Bu günde ${used} kişi + bu rezervasyon ${pax} kişi = <strong class="text-danger tnum">${used + pax}/${cap}</strong></p>`
    : '';
  return {
    title: 'Günlük kapasite aşılıyor',
    bodyHtml: `<p class="text-on-surface">${esc(message)}</p>${numbers}`,
    confirmLabel: 'Kapasiteyi aşarak ekle',
    cancelLabel: 'Vazgeç',
    tone: 'danger',
  };
}
