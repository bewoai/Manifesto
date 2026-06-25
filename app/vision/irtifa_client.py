"""İrtifa OCR sunucusu istemcisi."""
import logging
from typing import Optional, Tuple
import datetime as _dt
import requests

from app.mrz.parser import MRZResult
from app.validation.flags import ValidationOutcome, Flag

logger = logging.getLogger("irtifa_ocr")

def call_irtifa_ocr_server(
    image_bytes: bytes,
    server_url: str,
    license_key: str,
    device_id: str,
    media_type: str = "image/jpeg",
    timeout_seconds: int = 45,
) -> Tuple[Optional[MRZResult], ValidationOutcome, Optional[str], float, str, Optional[str]]:
    """
    Sunucuya OCR isteği gönderir ve Irtifa sistemine uygun sonuçları döner.
    Dönüş: (mrz, outcome, error_msg, confidence_score, processing_route, ai_model_used)
    """
    if not license_key:
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), "OCR için lisans anahtarı gerekli.", 0.0, "irtifa_server", None
    if not image_bytes:
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), "Görsel dosyası boş.", 0.0, "irtifa_server", None
    if len(image_bytes) > 10 * 1024 * 1024:
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), "Görsel en fazla 10 MB olabilir.", 0.0, "irtifa_server", None

    if not device_id:
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), "Cihaz kimliği oluşturulamadı.", 0.0, "irtifa_server", None

    if not server_url:
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), "Sunucu adresi belirtilmedi.", 0.0, "irtifa_server", None

    endpoint = server_url.rstrip("/") + "/ocr/passport"
    headers = {
        "x-license-key": license_key,
        "x-device-id": device_id,
    }
    extension = {
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
    }.get(media_type, "jpg")
    files = {
        "file": (f"passport.{extension}", image_bytes, media_type)
    }

    try:
        response = requests.post(endpoint, headers=headers, files=files, timeout=timeout_seconds)
    except requests.exceptions.RequestException as e:
        logger.warning("OCR sunucusuna ulaşılamadı: %s", e)
        return None, ValidationOutcome(flags=[Flag.UNREADABLE]), "OCR servisine ulaşılamıyor. İnternet bağlantınızı kontrol edin veya daha sonra tekrar deneyin.", 0.0, "irtifa_server", None

    if response.status_code != 200:
        error_msg = "OCR servisi geçici bir hata verdi. Lütfen tekrar deneyin."
        if response.status_code in {401, 403}:
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
        elif response.status_code == 429:
            error_msg = "OCR kullanım kotası doldu. Daha sonra tekrar deneyin veya yöneticinizle iletişime geçin."
            
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
