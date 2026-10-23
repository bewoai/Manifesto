/* ═══════════════════════════════════════════════════════════════════
   Kapasite kuralları — balon başına kapasite, günlük balon sınırı, acente kotası.
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

/** Acente adını karşılaştırma anahtarına çevirir: büyük/küçük harf ve Türkçe harf farkı yok. */
export function foldAgency(name) {
  return String(name ?? '')
    .trim()
    .replace(/\s+/g, ' ')
    .toLocaleUpperCase('tr-TR')
    .replace(/İ/g, 'I')
    .replace(/Ş/g, 'S')
    .replace(/Ğ/g, 'G')
    .replace(/Ü/g, 'U')
    .replace(/Ö/g, 'O')
    .replace(/Ç/g, 'C');
}

/**
 * Ayarlar'daki kota tablosu satırları: bilinen acenteler + kotası kayıtlı acenteler,
 * aynı acente bir kez. Ad, listedeki yazımıyla gösterilir.
 * Dönüş: [{ name, quota }] (quota: sayı ya da null = sınırsız).
 */
export function agencyQuotaRows(agencies = [], quotas = {}) {
  const rows = [];
  const byKey = new Map();
  const add = (name, quota) => {
    const clean = String(name ?? '').trim();
    const key = foldAgency(clean);
    if (!key) return;
    const existing = byKey.get(key);
    if (existing) {
      if (quota !== null && existing.quota === null) existing.quota = quota;
      return;
    }
    const row = { name: clean, quota };
    byKey.set(key, row);
    rows.push(row);
  };
  for (const name of agencies || []) add(name, null);
  for (const [name, q] of Object.entries(quotas || {})) {
    const n = parseInt(q, 10);
    add(name, Number.isFinite(n) && n > 0 ? n : null);
  }
  return rows;
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

/** Kotası tanımlı acenteler (quota > 0); kota aşan önce. */
export function quotaRows(agencyUsage = []) {
  return (agencyUsage || [])
    .filter((u) => Number(u?.quota) > 0)
    .map((u) => ({ agency: u.agency, used: Number(u.used) || 0, quota: Number(u.quota), over: Number(u.used) > Number(u.quota) }))
    .sort((a, b) => Number(b.over) - Number(a.over));
}

export function isQuotaExceeded(err) {
  return err?.status === 409 && err?.detail?.code === 'agency_quota_exceeded';
}

/** 409 agency_quota_exceeded için modal.confirm seçenekleri. esc: HTML kaçış fonksiyonu. */
export function quotaConfirmOptions(detail = {}, esc = (s) => String(s ?? '')) {
  const used = Number(detail.used) || 0;
  const pax = Number(detail.pax) || 0;
  const quota = Number(detail.quota) || 0;
  const message = detail.message || `${detail.agency || 'Acente'} günlük kotasını aşıyor.`;
  const numbers = quota
    ? `<p class="text-sm text-on-surface-variant mt-2">${esc(detail.agency || 'Acente')}: bugün ${used} kişi + bu rezervasyon ${pax} kişi = <strong class="text-danger tnum">${used + pax}/${quota}</strong></p>`
    : '';
  return {
    title: 'Acente kotası aşılıyor',
    bodyHtml: `<p class="text-on-surface">${esc(message)}</p>${numbers}`,
    confirmLabel: 'Kotayı aşarak ekle',
    cancelLabel: 'Vazgeç',
    tone: 'danger',
  };
}
