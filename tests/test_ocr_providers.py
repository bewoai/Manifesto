"""OcrProvider arayüzü: sağlayıcıdan bağımsız değişmezler + claude_direct sağlayıcısı."""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

import pytest

from app import settings as settings_mod
from app.validation.flags import Flag
from app.vision.extractor import make_provider, process_image
from app.vision.providers import ClaudeDirectProvider, IrtifaServerProvider, OcrResult
from app.vision.providers.base import to_mrz

TD3_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
TD3_L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
TD3_RAW = TD3_L1 + "\n" + TD3_L2
TODAY = dt.date(2010, 1, 1)   # specimen son geçerlilik 2012 → expired olmasın


class FakeProvider:
    name = "fake"

    def __init__(self, result: OcrResult):
        self.result = result
        self.calls: list[tuple[int, str]] = []

    def read(self, image_bytes: bytes, media_type: str) -> OcrResult:
        self.calls.append((len(image_bytes), media_type))
        return self.result


def _green_fields(document_no="L898902C3", raw_text=TD3_RAW) -> OcrResult:
    return OcrResult(
        status="success",
        passenger={"first_name": "ANNA MARIA", "last_name": "ERIKSSON", "nationality": "UTO",
                   "gender": "F", "document_no": document_no,
                   "birth_date": "1974-08-12", "expiry_date": "2012-04-15"},
        confidence="green", raw_text=raw_text, source="fake:test",
    )


# ─── Sağlayıcıdan bağımsız değişmezler ───────────────────────────────────

def test_provider_result_is_verified_locally_and_green_only_with_checksum():
    provider = FakeProvider(_green_fields())
    rec = process_image(b"img", source="p.jpg", media_type="image/png", ocr_provider=provider, today=TODAY)[0]
    assert provider.calls == [(3, "image/png")]
    assert rec.is_green
    assert rec.mrz.checks["server_document_match"] is True
    assert rec.processing_route == "fake"
    assert rec.ai_model_used == "fake:test"


def test_empty_checks_are_never_green_even_if_provider_says_green():
    rec = process_image(b"img", ocr_provider=FakeProvider(_green_fields(raw_text="")), today=TODAY)[0]
    assert rec.mrz.checks == {}
    assert Flag.FREE_TEXT_UNVERIFIED in rec.flags
    assert not rec.is_green


def test_document_no_conflicting_with_mrz_is_checksum_fail():
    rec = process_image(b"img", ocr_provider=FakeProvider(_green_fields(document_no="X9999999")), today=TODAY)[0]
    assert Flag.CHECKSUM_FAIL in rec.flags
    assert not rec.is_green


def test_expired_and_duplicate_are_computed_locally():
    rec = process_image(
        b"img", ocr_provider=FakeProvider(_green_fields()),
        today=dt.date(2026, 6, 22), seen_document_numbers={"L898902C3"},
    )[0]
    assert Flag.EXPIRED in rec.flags
    assert Flag.DUPLICATE in rec.flags


def test_mrz_only_result_is_parsed_locally():
    """claude_direct gibi yalnız MRZ satırı dönen sağlayıcı: alanlar parser'dan gelir."""
    result = OcrResult(status="success", passenger={}, confidence="green", raw_text=TD3_RAW, source="claude:x")
    rec = process_image(b"img", ocr_provider=FakeProvider(result), today=TODAY)[0]
    f = rec.to_fields()
    assert (f["nationality"], f["sex"], f["name"], f["passport_no"]) == ("UTO", "F", "ANNA MARIA ERIKSSON", "L898902C3")
    assert rec.is_green


def test_mrz_only_result_with_low_confidence_is_yellow():
    result = OcrResult(status="success", passenger={}, confidence="yellow", raw_text=TD3_RAW, source="claude:x")
    rec = process_image(b"img", ocr_provider=FakeProvider(result), today=TODAY)[0]
    assert rec.mrz is not None and rec.mrz.checks_ok
    assert Flag.LOW_CONFIDENCE in rec.flags
    assert not rec.is_green


def test_provider_error_becomes_unreadable_with_message():
    rec = process_image(b"img", ocr_provider=FakeProvider(OcrResult.failure("Ağ yok.", source="fake")))[0]
    assert rec.mrz is None
    assert Flag.UNREADABLE in rec.flags
    assert rec.error == "Ağ yok."
    assert rec.requires_manual_review


def test_no_mrz_and_no_fields_is_unreadable():
    result = OcrResult(status="success", passenger={}, confidence="red", raw_text="", warnings=["no_mrz"])
    rec = process_image(b"img", ocr_provider=FakeProvider(result))[0]
    assert rec.mrz is None and Flag.UNREADABLE in rec.flags


def test_usage_with_unknown_fields_is_ignored():
    result = _green_fields()
    result.usage = {"input_tokens": 10, "quota_used": 5, "future_field": {"x": 1}}
    mrz, outcome, err, *_ = to_mrz(result, provider_name="fake")
    assert err is None and mrz.checks_ok


# ─── Sağlayıcı seçimi ─────────────────────────────────────────────────────

def test_make_provider_by_vision_mode():
    s = settings_mod.Settings(irtifa_license_key="LIC", irtifa_device_id="DEV")
    assert isinstance(make_provider(s), IrtifaServerProvider)

    s = settings_mod.Settings(vision_mode="claude_direct", anthropic_api_key="k", model="claude-haiku-5-5")
    prov = make_provider(s, client=object())
    assert isinstance(prov, ClaudeDirectProvider) and prov.model == "claude-haiku-5-5"

    assert make_provider(settings_mod.Settings(vision_mode="manual")) is None
    assert isinstance(make_provider(settings_mod.Settings(), mode="claude", client=object()), ClaudeDirectProvider)
    with pytest.raises(ValueError):
        make_provider(settings_mod.Settings(), mode="nope")


def test_manual_mode_returns_error_record():
    rec = process_image(b"img", settings=settings_mod.Settings(vision_mode="manual"))[0]
    assert rec.mrz is None and "Manuel" in rec.error and rec.requires_manual_review


def test_legacy_vision_modes_are_normalized():
    assert settings_mod.Settings(vision_mode="claude").normalized().vision_mode == "claude_direct"
    assert settings_mod.Settings(vision_mode="google_vision").normalized().vision_mode == "irtifa_server"
    assert settings_mod.Settings(vision_mode="??").normalized().vision_mode == "irtifa_server"
    assert settings_mod.Settings(model="claude-sonnet-4-6").normalized().model == settings_mod.DEFAULT_MODEL
    assert settings_mod.Settings(vision_mode="claude_direct").uses_claude()


# ─── ClaudeDirectProvider ────────────────────────────────────────────────

class FakeAnthropic:
    """anthropic.Anthropic yerine: yapılandırılmış çıktı metin bloğu döner."""

    def __init__(self, payload=None, *, raise_exc=None, stop_reason="end_turn"):
        self.payload = payload
        self.raise_exc = raise_exc
        self.stop_reason = stop_reason
        self.kwargs = None
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.kwargs = kwargs
        if self.raise_exc:
            raise self.raise_exc
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=json.dumps(self.payload))],
            usage=SimpleNamespace(input_tokens=1200, output_tokens=60),
        )


def _mrz_payload(lines, confidence=0.97, document_no=""):
    return {
        "kind": "passport_mrz",
        "group": {"date": "", "hotel": "", "agency": "", "booking_code": "", "pax": None,
                  "nationality_hint": "", "note": ""},
        "passengers": [{
            "format": "TD3", "lines": lines,
            "fields": {"first_name": "", "last_name": "", "nationality": "", "gender": "",
                       "document_no": document_no, "document_type": "", "birth_date": "", "expiry_date": ""},
            "confidence": confidence, "annotation": "", "selected": None,
        }],
        "confidence": confidence,
    }


def test_claude_direct_returns_mrz_lines_and_usage():
    client = FakeAnthropic(_mrz_payload([TD3_L1, TD3_L2]))
    result = ClaudeDirectProvider(client, "claude-sonnet-5-5").read(b"img", "image/jpeg")
    assert result.ok and result.confidence == "green" and result.kind == "passport_mrz"
    assert result.raw_text == TD3_RAW
    assert result.passengers[0]["lines"] == [TD3_L1, TD3_L2]
    assert result.source == "claude:claude-sonnet-5-5"
    assert result.usage == {"input_tokens": 1200, "output_tokens": 60}

    kw = client.kwargs
    assert kw["model"] == "claude-sonnet-5-5"
    assert "tool_choice" not in kw and "tools" not in kw          # güncel modellerde zorunlu tool_choice 400
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["output_config"]["effort"] == "medium"
    assert kw["max_tokens"] >= 4096                                 # uzun listeler için
    assert kw["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"


def test_claude_direct_end_to_end_is_green_only_after_local_checksum():
    client = FakeAnthropic(_mrz_payload([TD3_L1, TD3_L2], 0.95))
    s = settings_mod.Settings(vision_mode="claude_direct", anthropic_api_key="k")
    rec = process_image(b"img", settings=s, ocr_provider=ClaudeDirectProvider(client, "claude-sonnet-5-5"), today=TODAY)[0]
    assert rec.is_green and rec.to_fields()["passport_no"] == "L898902C3"
    assert rec.processing_route == "claude_direct" and rec.source_kind == "passport_mrz"

    bad_l2 = TD3_L2[:9] + "5" + TD3_L2[10:]
    client = FakeAnthropic(_mrz_payload([TD3_L1, bad_l2], 0.99))
    rec = process_image(b"img", settings=s, ocr_provider=ClaudeDirectProvider(client, "claude-sonnet-5-5"), today=TODAY)[0]
    assert Flag.CHECKSUM_FAIL in rec.flags and not rec.is_green


def test_claude_direct_no_passengers_and_errors():
    empty = {"kind": "other", "group": {}, "passengers": [], "confidence": 0.2}
    result = ClaudeDirectProvider(FakeAnthropic(empty), "m").read(b"img", "image/jpeg")
    assert result.ok and result.passengers == [] and "no_passengers" in result.warnings
    rec = process_image(b"img", ocr_provider=ClaudeDirectProvider(FakeAnthropic(empty), "m"))[0]
    assert rec.mrz is None and Flag.UNREADABLE in rec.flags

    result = ClaudeDirectProvider(FakeAnthropic(raise_exc=RuntimeError("network down")), "m").read(b"img", "image/jpeg")
    assert not result.ok and "network down" in result.error

    result = ClaudeDirectProvider(FakeAnthropic(_mrz_payload([TD3_L1, TD3_L2]), stop_reason="refusal"), "m").read(b"img", "image/jpeg")
    assert not result.ok and "reddetti" in result.error


def test_claude_direct_maps_sdk_errors_to_turkish_messages():
    import anthropic
    import httpx2 as httpx

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.AuthenticationError(
        "invalid x-api-key", response=httpx.Response(401, request=req), body=None
    )
    result = ClaudeDirectProvider(FakeAnthropic(raise_exc=exc), "m").read(b"img", "image/jpeg")
    assert not result.ok and "anahtar" in result.error.lower()
