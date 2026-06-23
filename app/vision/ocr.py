"""OCR provider helpers for MRZ extraction.

All providers return raw MRZ lines only. Parsing, checksums and flags stay in
``app.mrz`` / ``app.validation`` so a weak OCR result cannot silently pass.
"""
from __future__ import annotations

import os
import re
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional


MRZ_CHARS_RE = re.compile(r"[^A-Z0-9<]")


def _clean_candidate(line: str) -> str:
    line = line.strip().upper()
    line = line.replace(" ", "").replace("\t", "")
    return MRZ_CHARS_RE.sub("", line)


def _fit_mrz_line(line: str, width: int) -> str:
    if len(line) > width:
        return line[:width]
    return line.ljust(width, "<")


def _mrz_lines_by_sliding(flat: str) -> tuple[str, list[str]]:
    """Son çare: yalnız MRZ bölgesi (basılı metin AYIKLANMIŞ) üzerinde kayan pencere.
    OCR'ın MRZ satırını düzensiz parçaladığı durumları toparlar."""
    for i in range(len(flat)):  # TD3
        l2 = flat[i:]
        if not (40 <= len(l2) <= 60):
            continue
        if not re.match(r'^[A-Z<]{3}$', l2[10:13]) or l2[20] not in 'MFX<':
            continue
        if len(l2) > 44:
            mid = l2[28:-16]
            l2 = (l2[:28] + l2[-16:]) if all(c == '<' for c in mid) else l2[:44]
        cc = l2[10:13]
        l1 = flat[:i]
        m = list(re.finditer(r'P[A-Z<]?' + cc, l1[-150:]))
        if m:
            l1 = l1[-150:][m[-1].start():]
        else:
            j = l1.rfind('P')
            l1 = l1[j:] if j != -1 else l1[-44:]
        return "TD3", [l1.ljust(44, '<')[:44], l2.ljust(44, '<')[:44]]
    for i in range(len(flat)):  # TD1
        l2 = flat[i:]
        if not (20 <= len(l2) <= 70):
            continue
        if len(l2) > 17 and l2[7] in 'MFX<' and re.match(r'^[A-Z<]{3}$', l2[15:18]):
            cc = l2[15:18]
            l1 = flat[:i]
            m = list(re.finditer(r'[IAC][A-Z<]?' + cc, l1[-100:]))
            if not m:
                continue
            l1 = l1[-100:][m[-1].start():]
            l3 = l2[30:] if len(l2) > 30 else ""
            l2 = l2[:30]
            return "TD1", [l1.ljust(30, '<')[:30], l2.ljust(30, '<')[:30], l3.ljust(30, '<')[:30]]
    return "NONE", []


def mrz_lines_from_text(text: str) -> tuple[str, list[str]]:
    """OCR metninden MRZ satırlarını çıkarır — SATIR YAPISI öncelikli.

    MRZ satırları '<' dolgu karakteri içerir; basılı kart metni (isim, başlık,
    'IDENTITY CARD' vb.) içermez. Önce '<'li yüksek-saflıkta satırları MRZ bölgesi
    olarak ayırırız → basılı metnin yanlış eşleşmesi (TC kimlik sorunu) biter.
    """
    # 1) MRZ-aday satırlar (sırayı koru): '<' içeren, yüksek-saflıkta [A-Z0-9<].
    frags: list[str] = []
    for raw in text.replace('\r', '\n').split('\n'):
        compact = re.sub(r'\s+', '', raw.upper())
        if not compact:
            continue
        cleaned = MRZ_CHARS_RE.sub('', compact)
        if '<' in cleaned and len(cleaned) >= 5 and len(cleaned) >= 0.75 * len(compact):
            frags.append(cleaned)
    if not frags:
        return "NONE", []

    # 2) OCR'ın böldüğü kısa / yalnız-'<' parçaları önceki satıra ekle.
    merged: list[str] = []
    for f in frags:
        if merged and len(merged[-1]) < 44 and (set(f) <= {'<'} or len(f) <= 12):
            merged[-1] += f
        else:
            merged.append(f)

    def alpha3(s: str, a: int, b: int) -> bool:
        return len(s) >= b and re.fullmatch(r'[A-Z<]{3}', s[a:b]) is not None

    # 3) TD1 — 3 satır ~30; orta satır: doğum(6 hane)+cinsiyet(7)+uyruk(15:18)
    c30 = [f for f in merged if 28 <= len(f) <= 34]
    if len(c30) >= 3:
        l1, l2, l3 = c30[0], c30[1], c30[2]
        if l2[:6].isdigit() and l2[7] in 'MFX<' and alpha3(l2, 15, 18):
            return "TD1", [_fit_mrz_line(l1, 30), _fit_mrz_line(l2, 30), _fit_mrz_line(l3, 30)]

    # 4) TD3 — 'P' ile başlayan satır = line1, sonraki uyruk-imzalı satır = line2
    for k, f in enumerate(merged):
        if f.startswith('P') and len(f) >= 20:
            for j in range(k + 1, len(merged)):
                if len(merged[j]) >= 28 and alpha3(merged[j], 10, 13) and merged[j][20] in 'MFX<':
                    return "TD3", [_fit_mrz_line(f, 44), _fit_mrz_line(merged[j], 44)]
    # 'P' yoksa: line2 imzasına göre (uyruk 10:13 + cinsiyet 20), line1 = önceki satır
    for k, l2 in enumerate(merged):
        if len(l2) >= 40 and not l2.startswith('P<') and alpha3(l2, 10, 13) and l2[20] in 'MFX<':
            l1 = merged[k - 1] if k >= 1 else ''
            return "TD3", [_fit_mrz_line(l1, 44), _fit_mrz_line(l2, 44)]

    # 5) Son çare: MRZ bölgesini birleştirip kayan pencere.
    return _mrz_lines_by_sliding(''.join(merged))


def parse_tr_id_front_from_text(text: str) -> tuple[str, dict]:
    import re
    if 'IDENTITY CARD' not in text.upper() and 'KMLK' not in text.upper() and 'KİMLİK' not in text.upper():
        return "NONE", {}
        
    fields = {}
    
    m = re.search(r'(?:Identity No)[\s\S]*?(\d{11})', text, re.IGNORECASE)
    if not m:
        m = re.search(r'\b(\d{11})\b', text)
    if m: fields['tc_no'] = m.group(1)
        
    m = re.search(r'(?:Surname)[\s\S]*?\n([A-ZÇĞİÖŞÜ]+(?: [A-ZÇĞİÖŞÜ]+)*)', text, re.IGNORECASE)
    if m: fields['surname'] = m.group(1).strip()
        
    m = re.search(r'(?:Given Name)[\s\S]*?\n([A-ZÇĞİÖŞÜ]+(?: [A-ZÇĞİÖŞÜ]+)*)', text, re.IGNORECASE)
    if m: fields['name'] = m.group(1).strip()
        
    m = re.search(r'(?:Gender)[\s\S]*?\n\s*([EK]\s*/\s*[MF]|[EKMF])', text, re.IGNORECASE)
    if m:
        s = m.group(1).replace(' ', '').upper()
        if 'E' in s or 'M' in s: fields['gender'] = 'M'
        elif 'K' in s or 'F' in s: fields['gender'] = 'F'
        
    if "tc_no" in fields and "surname" in fields:
        return "TR_ID_FRONT", fields
    return "NONE", {}


def extract_with_google_vision(
    image_bytes: bytes,
    *,
    credentials_json: str = "",
    use_document_text: bool = False,
) -> tuple[str, list[str], dict]:
    """Google Cloud Vision OCR -> MRZ lines.

    Supports:
    1. Service account JSON file path.
    2. Service account raw JSON string content (automatically writes to temp file).
    3. Google Cloud API Key (starts with 'AIzaSy' or does not exist as file).
    """
    client_options = {}
    temp_json_path = None
    old_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    creds = credentials_json.strip() if credentials_json else ""

    if creds:
        # Case 1: Raw JSON content
        if creds.startswith("{") and creds.endswith("}"):
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as f:
                f.write(creds)
                temp_json_path = Path(f.name)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(temp_json_path)
        # Case 2: Existing file path
        elif Path(creds).exists() and Path(creds).is_file():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(Path(creds).resolve())
        # Case 3: API Key or invalid path
        else:
            if "\\" in creds or "/" in creds or creds.endswith(".json"):
                raise RuntimeError(f"Google servis hesabı dosyası bulunamadı: {creds}")
            client_options["api_key"] = creds
    elif not old_credentials:
        raise RuntimeError("Google Servis Hesabı JSON yolu Ayarlar'dan belirtilmemiş.")

    try:
        from google.cloud import vision

        client = vision.ImageAnnotatorClient(client_options=client_options)
        image = vision.Image(content=image_bytes)
        if use_document_text:
            response = client.document_text_detection(image=image)
            text = getattr(getattr(response, "full_text_annotation", None), "text", "") or ""
        else:
            response = client.text_detection(image=image)
            annotations = getattr(response, "text_annotations", None) or []
            text = annotations[0].description if annotations else ""
        if getattr(response, "error", None) and response.error.message:
            raise RuntimeError(response.error.message)
            
        # Hata-ayıklama dökümü — sabit yol başka makinede yoksa OCR'ı ASLA bozmasın.
        try:
            with open(r"C:\Users\pc\Desktop\Manifesto\ocr_debug.txt", "a", encoding="utf-8") as df:
                df.write("=== GOOGLE VISION OCR ===\n")
                df.write(text + "\n======================\n")
        except OSError:
            pass


        fmt, lines = mrz_lines_from_text(text)
        if fmt == "NONE":
            tr_fmt, fields = parse_tr_id_front_from_text(text)
            if tr_fmt != "NONE":
                return tr_fmt, [], fields
        return fmt, lines, {"raw_text": text}

    finally:
        # Restore environment variable
        if old_credentials is None:
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        else:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = old_credentials

        # Clean up temp file if created
        if temp_json_path and temp_json_path.exists():
            try:
                temp_json_path.unlink()
            except OSError:
                pass


def extract_with_tesseract(
    image_bytes: bytes,
    *,
    tesseract_cmd: str = "",
) -> tuple[str, list[str], dict]:
    """Local Tesseract OCR -> MRZ lines."""
    from PIL import Image
    import pytesseract

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    img = Image.open(BytesIO(image_bytes))
    config = (
        "--psm 6 "
        "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
    )
    text = pytesseract.image_to_string(img, lang="eng", config=config)
    
    fmt, lines = mrz_lines_from_text(text)
    if fmt == "NONE":
        tr_fmt, fields = parse_tr_id_front_from_text(text)
        if tr_fmt != "NONE":
            return tr_fmt, [], fields
    return fmt, lines, {}

def extract_with_paddleocr(image_bytes: bytes) -> tuple[str, list[str], dict]:
    """Optional local PaddleOCR provider.

    PaddleOCR is intentionally lazy-imported because its runtime and model files
    are large. If the operator installs it later, this mode starts working.
    """
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = Path(tmp.name)
    try:
        result = ocr.ocr(str(tmp_path), cls=True)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    lines: list[str] = []
    for page in result or []:
        for item in page or []:
            if len(item) >= 2 and isinstance(item[1], (list, tuple)):
                lines.append(str(item[1][0]))
    
    text = "\\n".join(lines)
    fmt, lines = mrz_lines_from_text(text)
    if fmt == "NONE":
        tr_fmt, fields = parse_tr_id_front_from_text(text)
        if tr_fmt != "NONE":
            return tr_fmt, [], fields
    return fmt, lines, {}

