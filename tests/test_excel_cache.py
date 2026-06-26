from __future__ import annotations

import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from app.manifest.excel_cache import get_cached_excel_data, clear_excel_cache

def test_excel_cache_hit_and_miss(tmp_path):
    # Test için geçici bir excel dosya yolu taklidi
    test_file = tmp_path / "test_plan.xlsx"
    test_file.write_bytes(b"dummy content 1")

    clear_excel_cache()

    # Okuma fonksiyonu taklidi (Mock)
    read_mock = MagicMock(return_value=["row1", "row2"])

    # 1. Okuma (Cache Miss / Cold Read)
    res1 = get_cached_excel_data(test_file, "mock_read", read_mock, "arg1")
    assert res1 == ["row1", "row2"]
    assert read_mock.call_count == 1

    # 2. Okuma (Cache Hit)
    res2 = get_cached_excel_data(test_file, "mock_read", read_mock, "arg1")
    assert res2 == ["row1", "row2"]
    # Dosya değişmediği için read_fn tekrar çağrılmamalı
    assert read_mock.call_count == 1

    # 3. Dosya Boyutunu Değiştirme (Cache Invalidation)
    time.sleep(0.01) # mtime kayması için ufak bekleme
    test_file.write_bytes(b"dummy content 1 - updated") # Boyut ve mtime değişti
    
    # 3. Okuma (Cache Miss / Re-read)
    read_mock.return_value = ["row1", "row2", "row3"]
    res3 = get_cached_excel_data(test_file, "mock_read", read_mock, "arg1")
    assert res3 == ["row1", "row2", "row3"]
    assert read_mock.call_count == 2


def test_excel_cache_fallback_on_error(tmp_path):
    test_file = tmp_path / "test_fallback.xlsx"
    test_file.write_bytes(b"dummy")

    clear_excel_cache()

    read_mock = MagicMock(return_value=["original_data"])

    # 1. Başarılı ilk okuma ve cache'leme
    res1 = get_cached_excel_data(test_file, "mock_read", read_mock)
    assert res1 == ["original_data"]
    assert read_mock.call_count == 1

    # Dosya değişti (boyut değişti), bu yüzden cache geçersiz
    time.sleep(0.01)
    test_file.write_bytes(b"dummy_changed")

    # 2. Hata fırlatan okuma taklidi (örn: dosya başka program tarafından kilitlenmiş)
    read_mock.side_effect = PermissionError("Dosya kilitli")

    # Okuma normalde hata fırlatmalı, ancak cache'de veri olduğu için fallback yapmalı
    res2 = get_cached_excel_data(test_file, "mock_read", read_mock)
    assert res2 == ["original_data"] # Eski veriyi dönmeli
    assert read_mock.call_count == 2 # mock çağrıldı ama hata verdi
