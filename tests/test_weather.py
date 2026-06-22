from app.weather import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    STATUS_CAUTION,
    STATUS_FLYABLE,
    STATUS_NO_GO,
    WeatherPoint,
    assess_weather,
    decide_today,
)
import datetime as dt


def _future_point(day_offset: int, hour: int, risk: str = RISK_LOW, status: str = STATUS_FLYABLE) -> WeatherPoint:
    from app import weather

    t = weather._now().replace(hour=hour, minute=0, second=0, microsecond=0) + dt.timedelta(days=day_offset)
    return WeatherPoint(
        measured_at=t.isoformat(),
        temperature_c=12,
        wind_speed_kmh=5,
        wind_gust_kmh=8,
        wind_direction_deg=90,
        visibility_m=10_000,
        precipitation_mm=0,
        cloud_cover_pct=10,
        weather_code=0,
        risk_level=risk,
        flight_status=status,
        summary="ok",
    )


def test_assess_weather_flyable_when_conditions_are_clear():
    risk, status, summary = assess_weather(
        wind_speed_kmh=6,
        wind_gust_kmh=10,
        visibility_m=10_000,
        precipitation_mm=0,
        cloud_cover_pct=20,
    )

    assert risk == RISK_LOW
    assert status == STATUS_FLYABLE
    assert "uygun" in summary.lower()


def test_assess_weather_caution_on_borderline_gust():
    risk, status, summary = assess_weather(
        wind_speed_kmh=10,
        wind_gust_kmh=24,
        visibility_m=8_000,
        precipitation_mm=0,
        cloud_cover_pct=40,
    )

    assert risk == RISK_MEDIUM
    assert status == STATUS_CAUTION
    assert "ruzgar" in summary.lower()


def test_assess_weather_no_go_on_poor_visibility_and_rain():
    risk, status, summary = assess_weather(
        wind_speed_kmh=8,
        wind_gust_kmh=12,
        visibility_m=1_500,
        precipitation_mm=1.2,
        cloud_cover_pct=80,
    )

    assert risk == RISK_HIGH
    assert status == STATUS_NO_GO
    assert "gorus" in summary.lower()


def test_decide_today_uses_next_morning_after_flight_window():
    from app import weather

    now = weather._now()
    offset = 1 if now.time() > dt.time(8, 0) else 0
    result = decide_today([_future_point(offset, 5)])

    assert result["flight_status"] == STATUS_FLYABLE
    assert "ucus yapilabilir" in result["title"]
