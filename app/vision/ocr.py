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


def mrz_lines_from_text(text: str) -> tuple[str, list[str]]:
    """Find likely TD3/TD1 MRZ lines in free OCR text."""
    candidates: list[str] = []
    for raw in text.replace("\r", "\n").split("\n"):
        line = _clean_candidate(raw)
        if len(line) >= 24 and "<" in line:
            candidates.append(line)

    for i in range(max(0, len(candidates) - 1)):
        first, second = candidates[i], candidates[i + 1]
        if len(first) >= 40 and len(second) >= 40 and first.startswith("P<"):
            return "TD3", [_fit_mrz_line(first, 44), _fit_mrz_line(second, 44)]

    for i in range(max(0, len(candidates) - 2)):
        group = candidates[i:i + 3]
        if all(len(line) >= 26 for line in group) and group[0][0] in {"I", "A", "C"}:
            return "TD1", [_fit_mrz_line(line, 30) for line in group]

    return "NONE", []


def extract_with_google_vision(
    image_bytes: bytes,
    *,
    credentials_json: str = "",
    use_document_text: bool = False,
) -> tuple[str, list[str]]:
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
        return mrz_lines_from_text(text)
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
) -> tuple[str, list[str]]:
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
    return mrz_lines_from_text(text)


def extract_with_paddleocr(image_bytes: bytes) -> tuple[str, list[str]]:
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
    return mrz_lines_from_text("\n".join(lines))
