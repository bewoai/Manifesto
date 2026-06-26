from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("irtifa.excel_cache")

# RAM Önbelleği
# Yapı: { (file_path_str, func_name, args_tuple, kwargs_tuple): (mtime, size, cached_result) }
_EXCEL_MEMORY_CACHE: dict[tuple, tuple[float, int, Any]] = {}

def get_cached_excel_data(
    file_path: Path,
    func_name: str,
    read_fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any
) -> Any:
    """Excel dosyaları için mtime + size tabanlı RAM cache yönetimi.
    
    Eğer dosya diskte değişmediyse önbellekteki veriyi döner.
    Dosya kilitliyse veya okuma hatası alınırsa son başarılı cache'i fallback olarak kullanır.
    """
    path_str = str(file_path.resolve())
    
    # 1. Dosya boyutu ve değiştirilme tarihini oku
    current_mtime = 0.0
    current_size = 0
    file_exists = False
    
    try:
        if file_path.exists():
            stat = file_path.stat()
            current_mtime = stat.st_mtime
            current_size = stat.st_size
            file_exists = True
    except Exception as exc:
        logger.warning(f"Excel dosya nitelikleri okunamadı (kilitli olabilir): {file_path}. Hata: {exc}")
        
    cache_key = (path_str, func_name, args, tuple(sorted(kwargs.items())))
    
    # 2. Cache kontrolü (Dosya değişmediyse)
    if file_exists and cache_key in _EXCEL_MEMORY_CACHE:
        cached_mtime, cached_size, cached_data = _EXCEL_MEMORY_CACHE[cache_key]
        if cached_mtime == current_mtime and cached_size == current_size:
            start_time = time.perf_counter()
            # Önbellekten dön
            duration = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"[Excel Cache HIT] {func_name} -> RAM'den yüklendi. Dosya: {file_path.name}. "
                f"Süre: {duration:.3f}ms"
            )
            return cached_data
            
    # 3. Cache Miss veya Dosya Değişti -> Yeniden oku
    if file_exists:
        reason = "yoktu" if cache_key not in _EXCEL_MEMORY_CACHE else "dosya değişti"
        logger.info(f"[Excel Cache MISS] {func_name} -> Diskten okunuyor. Sebep: {reason}. Dosya: {file_path.name}")
        
        start_time = time.perf_counter()
        try:
            result = read_fn(file_path, *args, **kwargs)
            duration = (time.perf_counter() - start_time) * 1000
            logger.info(f"[Excel Cold Read] {func_name} -> Diskten okuma tamamlandı. Süre: {duration:.2f}ms")
            
            # Cache'i güncelle
            _EXCEL_MEMORY_CACHE[cache_key] = (current_mtime, current_size, result)
            return result
        except Exception as exc:
            # Okuma hatası durumunda fallback
            if cache_key in _EXCEL_MEMORY_CACHE:
                logger.error(
                    f"[Excel Read Error] Diskten okuma başarısız: {exc}. "
                    f"Son başarılı cache verisi FALLBACK olarak kullanılıyor!"
                )
                return _EXCEL_MEMORY_CACHE[cache_key][2]
            raise exc
    else:
        # Dosya yoksa doğrudan oku (muhtemelen hata fırlatacak)
        return read_fn(file_path, *args, **kwargs)

def clear_excel_cache() -> None:
    """Tüm Excel cache'ini temizler (örneğin manuel yenileme veya toplu yazma sonrası)."""
    _EXCEL_MEMORY_CACHE.clear()
    logger.info("[Excel Cache] RAM önbelleği temizlendi.")
