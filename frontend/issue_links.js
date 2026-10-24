/* ═══════════════════════════════════════════════════════════════════
   Uçuşa hazır uyarıları → Planlama derin bağlantısı
   "Satır 83: pickup eksik" yerine kişinin adı ve tıklayınca o rezervasyon.
   Biçim:  #/planning?sheet=22.10.2026&row=83        (tek rezervasyon / yolcu)
           #/planning?sheet=22.10.2026&issue=missing_pickup   (o uyarıdaki tüm bloklar)
   Saf modül (DOM yok): Node testinden de çağrılır.
   ═══════════════════════════════════════════════════════════════════ */

export const ISSUE_LABELS = {
  missing_pickup: 'pickup eksik',
  missing_driver: 'şoför eksik',
  missing_hotel: 'otel eksik',
  missing_coming_place: 'geleceği yer eksik',
  missing_pilot: 'pilot eksik',
  missing_balloon: 'balon eksik',
  missing_identity: 'kimlik eksik',
  pax_mismatch: 'PAX ile yolcu sayısı tutmuyor',
  duplicate_document: 'belge no birden fazla satırda',
};

export function issueLabel(code) {
  return ISSUE_LABELS[code] || '';
}

/** "planning?sheet=…&row=…" — dashboard'un `#/${route}` kalıbına doğrudan girer. */
export function planningRoute({ sheet, row, issue } = {}) {
  const params = new URLSearchParams();
  if (sheet) params.set('sheet', sheet);
  if (row != null && row !== '') params.set('row', String(row));
  if (issue) params.set('issue', issue);
  const q = params.toString();
  return q ? `planning?${q}` : 'planning';
}

export function planningHref(params) {
  return `#/${planningRoute(params)}`;
}

/** Uyarının işaret ettiği satır: yolcu satırı, yoksa rezervasyonun ilk satırı. */
export function issueTargetRow(issue) {
  if (!issue) return null;
  if (issue.row != null) return Number(issue.row);
  if (issue.lead_row != null) return Number(issue.lead_row);
  if (Array.isArray(issue.rows) && issue.rows.length) return Number(issue.rows[0]);
  return null;
}

/** Satırı içeren bloğun indeksi (lider satır veya yolcu satırı); yoksa -1. */
export function findBlockIndexForRow(blocks, row) {
  const n = Number(row);
  if (!Number.isFinite(n)) return -1;
  return (blocks || []).findIndex(b => Number(b.lead_row) === n || (b.rows || []).some(r => Number(r) === n));
}

/** Bir uyarı kodunun dokunduğu blokların lider satırları. */
export function issueLeadRows(issues, blocks, code) {
  const leads = new Set();
  for (const issue of issues || []) {
    if (issue.code !== code) continue;
    const rows = [issue.lead_row, issue.row, ...(Array.isArray(issue.rows) ? issue.rows : [])].filter(r => r != null);
    for (const r of rows) {
      const idx = findBlockIndexForRow(blocks, r);
      if (idx >= 0) leads.add(Number(blocks[idx].lead_row));
    }
  }
  return leads;
}

const IDENTITY_FIELDS = [['nationality', 'uyruk'], ['sex', 'cinsiyet'], ['name', 'isim'], ['passport_no', 'pasaport no']];

/**
 * Uyarı satırının gösterimi: { who, label, row, href }.
 * who: yolcu satırıysa yolcunun adı; yoksa issue.lead_name, yoksa bloğun lead_name'i.
 * href yalnız satıra bağlanabilen uyarılarda dolu.
 */
export function describeIssue(issue, blocks, sheet) {
  const row = issueTargetRow(issue);
  const idx = row == null ? -1 : findBlockIndexForRow(blocks, row);
  const block = idx >= 0 ? blocks[idx] : null;
  // Yolcu düzeyindeki uyarılar: missing_identity (row) ve duplicate_document (rows[0])
  const personRow = issue.row != null ? issue.row : (Array.isArray(issue.rows) && issue.rows.length ? issue.rows[0] : null);
  const passenger = block && personRow != null
    ? (block.passengers || []).find(p => Number(p.row) === Number(personRow))
    : null;
  const leadName = issue.lead_name || block?.lead_name || '';
  let who = passenger?.name || leadName;
  if (passenger && !passenger.name && leadName) who = `${leadName} grubu`;

  let label = issueLabel(issue.code);
  if (issue.code === 'missing_identity' && passenger) {
    const missing = IDENTITY_FIELDS.filter(([k]) => !passenger[k]).map(([, l]) => l);
    if (missing.length) label = `${missing.join(', ')} eksik`;
  }
  if (issue.code === 'duplicate_document') {
    const docNo = passenger?.passport_no;
    if (docNo) label = `${docNo} birden fazla satırda`;
  }
  return {
    who,
    label: label || issue.message || '',
    row,
    href: row != null && sheet ? planningHref({ sheet, row }) : '',
  };
}
