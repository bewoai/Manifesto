import json

from app import settings as settings_mod


def test_device_id_stays_stable_before_settings_are_saved(tmp_path):
    path = tmp_path / "settings.json"
    first = settings_mod.load(path)
    second = settings_mod.load(path)
    assert first.irtifa_device_id
    assert second.irtifa_device_id == first.irtifa_device_id


def test_existing_device_id_is_preserved_in_separate_store(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"irtifa_device_id": "registered-device"}),
        encoding="utf-8",
    )
    settings_mod.load(path)
    path.unlink()
    reloaded = settings_mod.load(path)
    assert reloaded.irtifa_device_id == "registered-device"
