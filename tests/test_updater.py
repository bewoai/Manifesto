"""Güncelleme imza doğrulaması: açık anahtar koda gömülü, ayarlardan değiştirilemez."""
from __future__ import annotations

import base64
import hashlib
import io
import json

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import settings as settings_mod
from app import updater


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _signed_manifest(private_key: Ed25519PrivateKey, payload: bytes) -> dict:
    version, url = "9.9.9", "https://example.test/Irtifa.exe"
    sha256 = hashlib.sha256(payload).hexdigest()
    signature = private_key.sign(f"{version}\n{url}\n{sha256}".encode("utf-8"))
    return {
        "version": version,
        "url": url,
        "sha256": sha256,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def _public_b64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


@pytest.fixture()
def staged(monkeypatch, tmp_path):
    payload = b"fake-exe-bytes"
    monkeypatch.setattr(updater, "UPDATE_DIR", tmp_path / "updates")
    monkeypatch.setattr(
        updater.urllib.request, "urlopen", lambda url, timeout=0: _FakeResponse(payload)
    )
    return payload


def test_stage_refuses_when_no_key_is_embedded(monkeypatch, staged):
    monkeypatch.setattr(updater, "UPDATE_PUBLIC_KEY_B64", "")
    key = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError, match="imza anahtarı"):
        updater.stage(_signed_manifest(key, staged))
    assert not updater.signing_configured()


def test_stage_accepts_manifest_signed_by_embedded_key(monkeypatch, staged):
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(updater, "UPDATE_PUBLIC_KEY_B64", _public_b64(key))

    target = updater.stage(_signed_manifest(key, staged))
    assert target.read_bytes() == staged
    pending = json.loads((updater.UPDATE_DIR / "pending.json").read_text(encoding="utf-8"))
    assert pending["version"] == "9.9.9"


def test_stage_rejects_manifest_signed_by_another_key(monkeypatch, staged):
    trusted, attacker = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    monkeypatch.setattr(updater, "UPDATE_PUBLIC_KEY_B64", _public_b64(trusted))

    with pytest.raises(InvalidSignature):
        updater.stage(_signed_manifest(attacker, staged))


def test_stage_signature_cannot_be_overridden_by_argument():
    """stage() artık anahtar parametresi almaz; ayar/istek yoluyla anahtar verilemez."""
    import inspect
    assert list(inspect.signature(updater.stage).parameters) == ["manifest"]


def test_settings_no_longer_carry_update_public_key(tmp_path):
    assert "update_public_key" not in settings_mod.Settings.__dataclass_fields__
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"update_public_key": "ZXZpbA=="}), encoding="utf-8")
    loaded = settings_mod.load(path)
    assert not hasattr(loaded, "update_public_key")
