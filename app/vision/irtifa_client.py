"""Irtifa OCR Server istemcisi."""
import requests
import json
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
import datetime as _dt
from app.mrz.parser import MRZResult
from app.validation.flags import ValidationOutcome, Flag

class IrtifaOcrError(Exception):
    pass

def call_irtifa_ocr_server(
    image_bytes: bytes,
    server_url: str,
    license_key: str,
    device_id: str,
    timeout_seconds: int = 15
) -> Tuple[Optional[MRZResult], ValidationOutcome, Optional[str], float, str, Optional[str]]:
    """
    Sunucuya OCR isteği gönderir ve Irtifa sistemine uygun sonuçları döner.
    Dönüş: (mrz, outcome, error_msg, confidence_score, processing_route, ai_model_used)
    """
    import requests
    from requests.exceptions import Timeout, RequestException
    from app.mrz.parser import MRZResult
    from app.validation.flags import ValidationOutcome, Flag

    if not license_key:
        print("[OCR_DEBUG] No license key provided.")
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), "OCR için lisans anahtarı gerekli.", 0.0, "irtifa_server", None

    # Mask license key for logging
    last_4 = license_key[-4:] if len(license_key) > 4 else license_key
    print(f"[OCR_DEBUG] Mode: VISION_MODE_IRTIFA_SERVER")
    print(f"[OCR_DEBUG] License Exists: True (ends with {last_4})")
    print(f"[OCR_DEBUG] Device ID Exists: {bool(device_id)}")
    
    endpoint = server_url.rstrip("/") + "/ocr/passport"
    print(f"[OCR_DEBUG] Request URL: {endpoint}")
    print(f"[OCR_DEBUG] Fallback Provider Used: False (Hard-disabled in Customer Build)")

    if not device_id:
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), "Cihaz kimliği oluşturulamadı.", 0.0, "irtifa_server", None

    if not server_url:
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), "Sunucu adresi belirtilmedi.", 0.0, "irtifa_server", None

    headers = {
        "x-license-key": license_key.encode("utf-8") if isinstance(license_key, str) else license_key,
        "x-device-id": device_id.encode("utf-8") if isinstance(device_id, str) else device_id,
    }
    files = {
        "file": ("image.jpg", image_bytes, "image/jpeg")
    }

    import logging
    logger = logging.getLogger("irtifa_ocr")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(ch)

    logger.info(f"Calling OCR Server Endpoint: {endpoint}")
    masked_key = f"{license_key[:3]}***{license_key[-3:]}" if license_key and len(license_key) > 6 else ("SET" if license_key else "MISSING")
    logger.info(f"License Key: {masked_key}, Device ID: {'SET' if device_id else 'MISSING'}")

    try:
        print(f"[OCR_DEBUG] Sending POST request...")
        response = requests.post(endpoint, headers=headers, files=files, timeout=timeout_seconds)
        print(f"[OCR_DEBUG] Server Response Status: {response.status_code}")
        logger.info(f"Response Status Code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), "OCR servisine ulaşılamıyor. İnternet bağlantınızı kontrol edin veya daha sonra tekrar deneyin.", 0.0, "irtifa_server", None

    if response.status_code != 200:
        logger.error(f"Error Response Body: {response.text}")
        error_msg = "OCR servisi geçici bir hata verdi. Lütfen tekrar deneyin."
        if response.status_code == 401:
            try:
                err_detail = response.json().get("detail", "").lower()
                if "device" in err_detail:
                    error_msg = "Cihaz kimliği oluşturulamadı."
                elif "required" in err_detail:
                    error_msg = "OCR için lisans anahtarı gerekli."
                else:
                    error_msg = "Lisans anahtarı geçersiz. OCR işlemi başlatılamaz."
            except Exception:
                error_msg = "Lisans anahtarı geçersiz. OCR işlemi başlatılamaz."
        elif response.status_code == 400:
            error_msg = "Desteklenmeyen dosya türü."
        elif response.status_code == 413:
            error_msg = "Dosya boyutu çok büyük."
            
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), error_msg, 0.0, "irtifa_server", None

    try:
        data = response.json()
    except ValueError:
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), "Sunucudan geçersiz yanıt alındı.", 0.0, "irtifa_server", None

    if data.get("status") != "success":
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), data.get("error", "Sunucu bir hata döndürdü."), 0.0, "irtifa_server", None

    p_data = data.get("passenger", {})
    source = data.get("source", "irtifa_server")
    confidence_color = data.get("confidence", "red")
    
    confidence_score = 1.0 if confidence_color == "green" else (0.8 if confidence_color == "yellow" else 0.5)

    name = ""
    if p_data.get("first_name") and p_data.get("last_name"):
        name = f"{p_data['last_name']}<<{p_data['first_name']}"
    elif p_data.get("first_name"):
        name = p_data["first_name"]
    elif p_data.get("last_name"):
        name = p_data["last_name"]
        
    birth_date = None
    if p_data.get("birth_date"):
        try:
            birth_date = _dt.date.fromisoformat(p_data["birth_date"])
        except ValueError:
            pass
            
    expiry_date = None
    if p_data.get("expiry_date"):
        try:
            expiry_date = _dt.date.fromisoformat(p_data["expiry_date"])
        except ValueError:
            pass

    raw_text = data.get("raw_text", "")

    # Eğer sunucu yolcu bilgilerini çıkaramamışsa ancak raw_text varsa, yerel MRZ parser'ı devreye sok
    if not p_data.get("document_no") and not p_data.get("first_name") and not p_data.get("last_name") and raw_text:
        from app.vision.ocr import mrz_lines_from_text
        from app.mrz.parser import parse
        fmt, lines = mrz_lines_from_text(raw_text)
        if fmt != "NONE" and lines:
            try:
                mrz = parse(lines)
                mrz.raw_lines = [raw_text]
                
                flags = []
                if confidence_color != "green":
                    flags.append(Flag.LOW_CONFIDENCE)
                return mrz, ValidationOutcome(flags=flags), None, confidence_score, "irtifa_server_fallback", source
            except Exception:
                pass

    mrz = MRZResult(
        format="SERVER_OCR",
        document_type="ID",
        issuing_country=p_data.get("nationality", "")[:3],
        nationality=p_data.get("nationality", "")[:3],
        document_number=p_data.get("document_no", ""),
        sex=p_data.get("gender", "X"),
        surname=p_data.get("last_name", ""),
        given_names=p_data.get("first_name", ""),
        birth_date=birth_date,
        expiry_date=expiry_date,
        checks={},
        raw_lines=[raw_text]
    )


    flags = []
    if confidence_color != "green":
        flags.append(Flag.LOW_CONFIDENCE)
        
    for w in data.get("warnings", []):
        if "expired" in w.lower():
            flags.append(Flag.EXPIRED)
        elif "checksum" in w.lower():
            flags.append(Flag.CHECKSUM_FAIL)

    outcome = ValidationOutcome(flags=flags)
    return mrz, outcome, None, confidence_score, "irtifa_server", source
