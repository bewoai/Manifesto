/* ═══════════════════════════════════════════════════════════════════
   Planlama araması — alan adlı sorgu
   "pax 5" → PAX'ı 5 olan rezervasyonlar; "pax 3-5", "pax >4", "pax:2" de olur.
   "isim ahmet", "otel argos", "acente x", "şoför 2", "balon bzr", "pilot ali",
   "pasaport T22", "uyruk TUR", "oda 202", "saat 04:30", "yer alan", "not vip".
   Alan adı yazılmayan kelimeler her alanda aranır; tüm koşullar birlikte (VE) sağlanmalı.
   Büyük/küçük harf ve Türkçe karakter farkı yok sayılır (sofor = ŞOFÖR).
   ═══════════════════════════════════════════════════════════════════ */

export function fold(value) {
  return String(value ?? '')
    .toLocaleUpperCase('tr-TR')
    .replace(/[İIı]/g, 'I').replace(/Ş/g, 'S').replace(/Ğ/g, 'G')
    .replace(/Ü/g, 'U').replace(/Ö/g, 'O').replace(/Ç/g, 'C')
    .normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .trim();
}

// Alan adı (katlanmış) → alan anahtarı. Eş anlamlılar aynı alana gider.
const FIELD_ALIASES = {
  PAX: 'pax', KISI: 'pax', KISILIK: 'pax',
  ISIM: 'name', AD: 'name', ADI: 'name', YOLCU: 'name', MUSTERI: 'name', REHBER: 'name',
  OTEL: 'hotel', HOTEL: 'hotel',
  ACENTE: 'agency', ACENTA: 'agency',
  REZERVE: 'reserved_by', REZERVASYON: 'reserved_by',
  BALON: 'balloon',
  PILOT: 'pilot', KAPTAN: 'pilot',
  SOFOR: 'driver', ARAC: 'driver', SURUCU: 'driver',
  PASAPORT: 'passport', KIMLIK: 'passport', BELGE: 'passport',
  UYRUK: 'nationality', ULKE: 'nationality',
  CINSIYET: 'sex',
  ODA: 'room', IRTIBAT: 'room',
  SAAT: 'pickup', PICKUP: 'pickup', ALIS: 'pickup',
  YER: 'coming_place',
  NOT: 'note',
  SATIR: 'row',
};

/** Sorguyu koşullara ayırır: [{field, op, value, value2?}] — field null ise serbest metin. */
export function parseQuery(raw) {
  const tokens = String(raw ?? '').trim().split(/\s+/).filter(Boolean);
  const terms = [];
  for (let i = 0; i < tokens.length; i++) {
    let tok = tokens[i];
    // "pax:5", "pax=5", "pax>4" ve "pax5" biçimleri
    const glued = /^([A-Za-zÇĞİÖŞÜçğıöşü]+)\s*([:=<>]=?|)(.*)$/.exec(tok);
    let field = null;
    let rest = '';
    if (glued) {
      const key = FIELD_ALIASES[fold(glued[1])];
      if (key) {
        field = key;
        rest = (glued[2] || '') + (glued[3] || '');
      } else if (/^PAX\d+/i.test(tok)) {
        field = 'pax'; rest = tok.slice(3);
      }
    }
    if (field) {
      rest = rest.replace(/^[:=]/, '');
      if (!rest && i + 1 < tokens.length) rest = tokens[++i];
      // "pax > 4" gibi boşluklu operatör
      if (/^[<>]=?$/.test(rest) && i + 1 < tokens.length) rest += tokens[++i];
      if (!rest) { terms.push({ field: null, op: 'has', value: fold(tok) }); continue; }
      terms.push(makeTerm(field, rest));
    } else {
      terms.push({ field: null, op: 'has', value: fold(tok) });
    }
  }
  return terms;
}

function makeTerm(field, rest) {
  if (field === 'pax' || field === 'row') {
    let m = /^(\d+)\s*-\s*(\d+)$/.exec(rest);
    if (m) return { field, op: 'between', value: Number(m[1]), value2: Number(m[2]) };
    m = /^([<>]=?)(\d+)$/.exec(rest);
    if (m) return { field, op: m[1], value: Number(m[2]) };
    if (/^\d+$/.test(rest)) return { field, op: '=', value: Number(rest) };
  }
  // Şoför numarası ve cinsiyet tam eşleşir ("şoför 2" 12'yi bulmasın)
  if (field === 'driver' && /^\d+$/.test(rest)) return { field, op: 'eq', value: fold(rest) };
  if (field === 'sex') {
    const v = fold(rest);
    const sex = /^(E|ERKEK|M|BAY)$/.test(v) ? 'M' : /^(K|KADIN|F|BAYAN)$/.test(v) ? 'F' : v;
    return { field, op: 'eq', value: sex };
  }
  return { field, op: 'has', value: fold(rest) };
}

function blockValues(block, field) {
  const ps = block.passengers || [];
  switch (field) {
    case 'name': return [block.lead_name, ...ps.map(p => p.name)];
    case 'passport': return ps.map(p => p.passport_no);
    case 'nationality': return ps.map(p => p.nationality);
    case 'sex': return ps.map(p => p.sex);
    default: return [block[field]];
  }
}

function paxOf(block) {
  return block.pax != null && block.pax !== '' ? Number(block.pax) : (block.rows || block.passengers || []).length;
}

function allText(block) {
  const ps = block.passengers || [];
  return [
    block.lead_name, block.hotel, block.agency, block.reserved_by, block.room, block.balloon,
    block.pilot, block.driver, block.pickup, block.coming_place, block.note, block.company,
    ...ps.flatMap(p => [p.name, p.passport_no, p.nationality]),
  ].map(fold).join(' ');
}

/** Rezervasyon bloğu tüm koşulları sağlıyor mu? */
export function matchesBlock(block, terms) {
  for (const t of terms) {
    if (!t.field) {
      if (!allText(block).includes(t.value)) return false;
      continue;
    }
    if (t.field === 'pax' || t.field === 'row') {
      const n = t.field === 'pax' ? paxOf(block) : Number(block.lead_row);
      const ok = t.op === '=' ? n === t.value
        : t.op === 'between' ? n >= Math.min(t.value, t.value2) && n <= Math.max(t.value, t.value2)
        : t.op === '>' ? n > t.value : t.op === '>=' ? n >= t.value
        : t.op === '<' ? n < t.value : t.op === '<=' ? n <= t.value
        : String(n).includes(String(t.value));
      if (!ok) return false;
      continue;
    }
    const values = blockValues(block, t.field).map(fold);
    const ok = t.op === 'eq' ? values.some(v => v === t.value) : values.some(v => v.includes(t.value));
    if (!ok) return false;
  }
  return true;
}

/** Arama kutusunun altındaki ipucu için koşulların okunur özeti. */
export function describeTerms(terms) {
  const label = { pax: 'PAX', name: 'isim', hotel: 'otel', agency: 'acente', reserved_by: 'rezerve yapan',
    balloon: 'balon', pilot: 'pilot', driver: 'şoför', passport: 'pasaport', nationality: 'uyruk', sex: 'cinsiyet',
    room: 'oda', pickup: 'saat', coming_place: 'geleceği yer', note: 'not', row: 'satır' };
  return terms.map(t => {
    if (!t.field) return `“${t.value.toLocaleLowerCase('tr-TR')}”`;
    const v = t.op === 'between' ? `${t.value}–${t.value2}` : ['>', '>=', '<', '<='].includes(t.op) ? `${t.op} ${t.value}` : String(t.value).toLocaleLowerCase('tr-TR');
    return `${label[t.field] || t.field}: ${v}`;
  }).join(' · ');
}
