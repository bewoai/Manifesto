"""Belge Sınıflandırma Modülü.

Google Vision'dan dönen OCR raw text'ine bakarak belgenin ne olduğunu anlar.
Buna göre Claude'a gidilip gidilmeyeceğine karar verilir (Fallback mimarisi).
"""

import re

def classify_document(raw_text: str) -> str:
    """OCR metnine göre belge tipini döndürür.
    
    Dönen değerler:
    - passport
    - national_id
    - whatsapp_list
    - flight_list
    - unknown
    """
    if not raw_text or len(raw_text.strip()) < 5:
        return "unknown"
        
    text_upper = raw_text.upper()
    
    # 1. Pasaport (Passport) Kontrolü
    # MRZ satırlarında P<, P<TUR vb. olur.
    # Genelde TD3 44 karakterlik iki satır.
    mrz_p_pattern = re.search(r'P<[A-Z<]{3}[A-Z0-9<]{30,}', text_upper)
    if mrz_p_pattern or "PASSPORT" in text_upper or "PASAPORT" in text_upper:
        return "passport"
        
    # 2. Kimlik (National ID) Kontrolü
    # I<, IDTUR, A< vb.
    mrz_id_pattern = re.search(r'(?:I<|A<|C<|IDTUR)[A-Z<]{2}[A-Z0-9<]{20,}', text_upper)
    if mrz_id_pattern or "IDENTITY CARD" in text_upper or "KİMLİK KARTI" in text_upper or "KMLK" in text_upper:
        return "national_id"
        
    # 3. WhatsApp veya Flight List (Serbest Metin Listeleri)
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    if len(lines) > 5:
        if "PAX" in text_upper or "PICKUP" in text_upper or "HOTEL" in text_upper or "ROOM" in text_upper or "FLIGHT" in text_upper:
            if re.search(r'\d{2}:\d{2}', raw_text): # WhatsApp mesaj saati gibi
                return "whatsapp_list"
            return "flight_list"
        return "whatsapp_list"
        
    return "unknown"
