/* ═══════════════════════════════════════════════════════════════════
   Liste işaret kuralları — app/list_marks.py ile BİREBİR aynı anlam.
   Model işareti yorumlamaz, satır başına ham `annotation` döner; operatör
   kuralı seçer. Burada değişen her şey Python tarafında da değişmeli.
   ═══════════════════════════════════════════════════════════════════ */

const CHECK_TOKENS = ['✓', '✔', '√', '☑', 'tick', 'check'];
const HIGHLIGHT_TOKENS = ['highlight', 'fosfor', 'marker', 'yellow', 'green'];
const YES_TOKENS = new Set(['si', 'sí', 'yes', 'evet', 'ok', 'y', 'x']);
const STRIKE_TOKENS = ['strike', 'üstü çizili', 'crossed'];

// Rehber / kaptan / şoför satırları listede yolcu gibi durur ama uçan yolcu değildir.
const STAFF_TOKENS = ['rehber', 'kaptan', 'guide', 'pilot', 'driver'];

export const LIST_KINDS = new Set(['printed_list', 'handwritten_list', 'chat_message']);

// app/vision/providers/base.py KIND_LABELS (API `source_kind_label` döndürmediği yerler için)
export const KIND_LABELS = {
  passport_mrz: 'Pasaport (MRZ)',
  id_card_mrz: 'Kimlik (MRZ)',
  id_front: 'Kimlik ön yüzü',
  printed_list: 'Basılı liste',
  handwritten_list: 'El yazısı liste',
  chat_message: 'Mesaj / rezervasyon',
  other: 'Diğer',
};

// app/list_marks.py MARK_RULES — /api/lists/mark-rules alınamazsa yedek seçenekler
export const MARK_RULE_OPTIONS = [
  { id: 'all', label: 'Hepsi uçuyor' },
  { id: 'any_mark', label: 'İşaretli satırlar (ne olursa olsun)' },
  { id: 'check', label: 'Tik (✓) olanlar' },
  { id: 'highlight', label: 'Fosforlu satırlar' },
  { id: 'number', label: 'Yanında sıra numarası olanlar' },
  { id: 'yes', label: 'SI / EVET / YES yazanlar' },
  { id: 'letter_b', label: 'B harfi olanlar' },
];

/** Python `_fold`: küçük harf, aksansız (SÍ → si), kırpılmış. */
export function fold(text) {
  return String(text || '')
    .normalize('NFKD')
    .replace(/\p{Mn}/gu, '')
    .trim()
    .toLowerCase();
}

/** Python `normalize_agency_key`: acente → kural sözlüğü anahtarı. */
export const normalizeAgencyKey = fold;

/** Python `annotation_matches`: satırın işareti kurala göre "uçuyor" mu? */
export function annotationMatches(rule, annotation) {
  const a = fold(annotation);
  if (rule === 'all') return true;
  if (!a || STRIKE_TOKENS.some(tok => a.includes(tok))) return false;
  if (rule === 'any_mark') return true;
  if (rule === 'check') return CHECK_TOKENS.some(tok => a.includes(tok));
  if (rule === 'highlight') return HIGHLIGHT_TOKENS.some(tok => a.includes(tok));
  if (rule === 'number') return /^\p{Nd}{1,3}$/u.test(a);
  if (rule === 'yes') return YES_TOKENS.has(a);
  if (rule === 'letter_b') return a === 'b' || a === 'balon' || a === 'balloon';
  return false;
}

/** Rehber/kaptan satırı mı? (annotation içinde rol kelimesi) */
export function isStaffAnnotation(annotation) {
  const a = fold(annotation);
  return !!a && STAFF_TOKENS.some(tok => a.includes(tok));
}
