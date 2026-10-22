"""Görsel ön işleme: EXIF yönü düzeltme + boyut sınırlama.

Telefon fotoğrafları çoğu zaman 90° dönük EXIF taşır (NZ/AUS pasaport örnekleri);
modele göndermeden önce düzeltmek okuma kalitesini ve tutarlılığını artırır. Uzun kenar
sınırlanarak token maliyeti düşer; MRZ 2000 px'te rahat okunur.
"""
from __future__ import annotations

import io
from typing import Tuple

MAX_LONG_EDGE = 2000
JPEG_QUALITY = 90


def prepare_image(image_bytes: bytes, media_type: str = "image/jpeg") -> Tuple[bytes, str]:
    """(bytes, media_type) döner. Hata hâlinde girdiyi olduğu gibi geri verir."""
    try:
        from PIL import Image, ImageOps
    except Exception:  # pragma: no cover
        return image_bytes, media_type

    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            im.load()
            try:
                orientation = int(im.getexif().get(0x0112, 1) or 1)
            except Exception:
                orientation = 1
            needs_rotation = orientation not in (0, 1)
            oriented = (ImageOps.exif_transpose(im) or im) if needs_rotation else im
            changed = needs_rotation
            w, h = oriented.size
            long_edge = max(w, h)
            if long_edge > MAX_LONG_EDGE:
                scale = MAX_LONG_EDGE / float(long_edge)
                oriented = oriented.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
                changed = True
            if not changed and media_type in ("image/jpeg", "image/png", "image/webp"):
                return image_bytes, media_type
            out = io.BytesIO()
            if oriented.mode not in ("RGB", "L"):
                oriented = oriented.convert("RGB")
            oriented.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            return out.getvalue(), "image/jpeg"
    except Exception:
        return image_bytes, media_type
