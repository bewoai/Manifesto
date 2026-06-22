from __future__ import annotations

import datetime as dt
import json
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import settings as settings_mod
from app.db import connect

try:
    LOCAL_TZ = ZoneInfo("Europe/Istanbul")
except ZoneInfoNotFoundError:
    LOCAL_TZ = dt.timezone(dt.timedelta(hours=3), name="Europe/Istanbul")

STATUS_FLYABLE = "flyable"
STATUS_CAUTION = "caution"
STATUS_NO_GO = "no_go"
STATUS_UNKNOWN = "unknown"

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_UNKNOWN = "unknown"


@dataclass
class WeatherPoint:
    measured_at: str
    temperature_c: float | None
    wind_speed_kmh: float | None
    wind_gust_kmh: float | None
    wind_direction_deg: float | None
    visibility_m: float | None
    precipitation_mm: float | None
    cloud_cover_pct: float | None
    weather_code: int | None
    risk_level: str
    flight_status: str
    summary: str


def _now() -> dt.datetime:
    return dt.datetime.now(LOCAL_TZ).replace(microsecond=0)


def _parse_time(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(LOCAL_TZ)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hourly_value(hourly: dict[str, Any], key: str, index: int) -> Any:
    values = hourly.get(key) or []
    if index >= len(values):
        return None
    return values[index]


def assess_weather(
    *,
    wind_speed_kmh: float | None,
    wind_gust_kmh: float | None,
    visibility_m: float | None,
    precipitation_mm: float | None,
    cloud_cover_pct: float | None,
) -> tuple[str, str, str]:
    reasons: list[str] = []
    blockers: list[str] = []

    wind = wind_speed_kmh or 0
    gust = wind_gust_kmh or wind
    visibility = visibility_m if visibility_m is not None else 10_000
    rain = precipitation_mm or 0
    cloud = cloud_cover_pct or 0

    if wind >= 22:
        blockers.append("Ruzgar yuksek")
    elif wind >= 14:
        reasons.append("Ruzgar sinira yakin")

    if gust >= 30:
        blockers.append("Ani ruzgar cok yuksek")
    elif gust >= 22:
        reasons.append("Ani ruzgar takip edilmeli")

    if visibility < 2500:
        blockers.append("Gorus dusuk")
    elif visibility < 5000:
        reasons.append("Gorus orta")

    if rain >= 1:
        blockers.append("Yagis var")
    elif rain > 0:
        reasons.append("Hafif yagis ihtimali")

    if cloud >= 85:
        reasons.append("Bulutluluk yuksek")

    if blockers:
        return RISK_HIGH, STATUS_NO_GO, "; ".join(blockers)
    if reasons:
        return RISK_MEDIUM, STATUS_CAUTION, "; ".join(reasons)
    return RISK_LOW, STATUS_FLYABLE, "Kosullar uygun gorunuyor"


def _open_meteo_url(s: settings_mod.Settings) -> str:
    params = {
        "latitude": s.weather_latitude,
        "longitude": s.weather_longitude,
        "timezone": "Europe/Istanbul",
        "forecast_days": 3,
        "current": ",".join([
            "temperature_2m",
            "wind_speed_10m",
            "wind_gusts_10m",
            "wind_direction_10m",
            "precipitation",
            "weather_code",
            "cloud_cover",
        ]),
        "hourly": ",".join([
            "temperature_2m",
            "wind_speed_10m",
            "wind_gusts_10m",
            "wind_direction_10m",
            "visibility",
            "precipitation",
            "weather_code",
            "cloud_cover",
        ]),
    }
    return "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)


def _fetch_json(s: settings_mod.Settings) -> dict[str, Any]:
    if s.weather_provider == "custom" and s.weather_api_url:
        url = s.weather_api_url
    else:
        url = _open_meteo_url(s)
    req = urllib.request.Request(url, headers={"User-Agent": "BalonManifesto/0.1"})
    if s.weather_api_key:
        req.add_header("Authorization", f"Bearer {s.weather_api_key}")
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _point_from_hourly(hourly: dict[str, Any], index: int) -> WeatherPoint:
    wind = _safe_float(_hourly_value(hourly, "wind_speed_10m", index))
    gust = _safe_float(_hourly_value(hourly, "wind_gusts_10m", index))
    visibility = _safe_float(_hourly_value(hourly, "visibility", index))
    rain = _safe_float(_hourly_value(hourly, "precipitation", index))
    cloud = _safe_float(_hourly_value(hourly, "cloud_cover", index))
    risk, status, summary = assess_weather(
        wind_speed_kmh=wind,
        wind_gust_kmh=gust,
        visibility_m=visibility,
        precipitation_mm=rain,
        cloud_cover_pct=cloud,
    )
    return WeatherPoint(
        measured_at=_parse_time(hourly["time"][index]).isoformat(),
        temperature_c=_safe_float(_hourly_value(hourly, "temperature_2m", index)),
        wind_speed_kmh=wind,
        wind_gust_kmh=gust,
        wind_direction_deg=_safe_float(_hourly_value(hourly, "wind_direction_10m", index)),
        visibility_m=visibility,
        precipitation_mm=rain,
        cloud_cover_pct=cloud,
        weather_code=_safe_int(_hourly_value(hourly, "weather_code", index)),
        risk_level=risk,
        flight_status=status,
        summary=summary,
    )


def _nearest_current_point(data: dict[str, Any]) -> WeatherPoint | None:
    current = data.get("current") or {}
    if not current:
        return None
    wind = _safe_float(current.get("wind_speed_10m"))
    gust = _safe_float(current.get("wind_gusts_10m"))
    visibility = None
    rain = _safe_float(current.get("precipitation"))
    cloud = _safe_float(current.get("cloud_cover"))
    risk, status, summary = assess_weather(
        wind_speed_kmh=wind,
        wind_gust_kmh=gust,
        visibility_m=visibility,
        precipitation_mm=rain,
        cloud_cover_pct=cloud,
    )
    return WeatherPoint(
        measured_at=_parse_time(current.get("time", _now().isoformat())).isoformat(),
        temperature_c=_safe_float(current.get("temperature_2m")),
        wind_speed_kmh=wind,
        wind_gust_kmh=gust,
        wind_direction_deg=_safe_float(current.get("wind_direction_10m")),
        visibility_m=visibility,
        precipitation_mm=rain,
        cloud_cover_pct=cloud,
        weather_code=_safe_int(current.get("weather_code")),
        risk_level=risk,
        flight_status=status,
        summary=summary,
    )


def build_forecast(data: dict[str, Any], *, hours: int = 36) -> list[WeatherPoint]:
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        point = _nearest_current_point(data)
        return [point] if point else []

    start = _now() - dt.timedelta(hours=1)
    end = _now() + dt.timedelta(hours=hours)
    points: list[WeatherPoint] = []
    for idx, raw_time in enumerate(times):
        t = _parse_time(raw_time)
        if start <= t <= end:
            points.append(_point_from_hourly(hourly, idx))
    return points


def next_flight_window(points: list[WeatherPoint]) -> tuple[list[WeatherPoint], dt.date | None]:
    now = _now()
    window_start = dt.time(3, 30)
    window_end = dt.time(7, 30)
    target_date = now.date() if now.time() <= window_end else now.date() + dt.timedelta(days=1)
    window: list[WeatherPoint] = []
    for p in points:
        t = _parse_time(p.measured_at)
        if t.date() == target_date and window_start <= t.time() <= window_end:
            window.append(p)
    return window, target_date


def flight_window(points: list[WeatherPoint]) -> list[WeatherPoint]:
    window, _ = next_flight_window(points)
    return window


def decide_today(points: list[WeatherPoint]) -> dict[str, Any]:
    window, target_date = next_flight_window(points)
    if not window:
        return {
            "flight_status": STATUS_UNKNOWN,
            "risk_level": RISK_UNKNOWN,
            "title": "Tahmin bekleniyor",
            "summary": "Bir sonraki sabah ucus penceresi icin yeterli hava verisi yok.",
        }
    prefix = "Bugun" if target_date == _now().date() else "Yarin sabah"
    statuses = {p.flight_status for p in window}
    risks = {p.risk_level for p in window}
    if STATUS_NO_GO in statuses or RISK_HIGH in risks:
        title = f"{prefix} ucus riskli"
        status = STATUS_NO_GO
        risk = RISK_HIGH
    elif STATUS_CAUTION in statuses or RISK_MEDIUM in risks:
        title = f"{prefix} dikkatli takip"
        status = STATUS_CAUTION
        risk = RISK_MEDIUM
    else:
        title = f"{prefix} ucus yapilabilir gorunuyor"
        status = STATUS_FLYABLE
        risk = RISK_LOW
    worst = next((p for p in window if p.risk_level == risk), window[0])
    return {
        "flight_status": status,
        "risk_level": risk,
        "title": title,
        "summary": worst.summary,
    }


def enrich_current_from_forecast(current: WeatherPoint | None, points: list[WeatherPoint]) -> WeatherPoint | None:
    if current is None or not points:
        return current
    current_time = _parse_time(current.measured_at)
    nearest = min(points, key=lambda p: abs((_parse_time(p.measured_at) - current_time).total_seconds()))
    current.visibility_m = current.visibility_m if current.visibility_m is not None else nearest.visibility_m
    current.precipitation_mm = current.precipitation_mm if current.precipitation_mm is not None else nearest.precipitation_mm
    current.cloud_cover_pct = current.cloud_cover_pct if current.cloud_cover_pct is not None else nearest.cloud_cover_pct
    current.weather_code = current.weather_code if current.weather_code is not None else nearest.weather_code
    current.risk_level, current.flight_status, current.summary = assess_weather(
        wind_speed_kmh=current.wind_speed_kmh,
        wind_gust_kmh=current.wind_gust_kmh,
        visibility_m=current.visibility_m,
        precipitation_mm=current.precipitation_mm,
        cloud_cover_pct=current.cloud_cover_pct,
    )
    return current


def _insert_measurement(s: settings_mod.Settings, point: WeatherPoint, payload: dict[str, Any]) -> None:
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO weather_measurement (
                measured_at, provider, location_name, latitude, longitude,
                temperature_c, wind_speed_kmh, wind_gust_kmh, wind_direction_deg,
                visibility_m, precipitation_mm, cloud_cover_pct, weather_code,
                risk_level, flight_status, summary, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                point.measured_at,
                s.weather_provider,
                s.weather_location_name,
                s.weather_latitude,
                s.weather_longitude,
                point.temperature_c,
                point.wind_speed_kmh,
                point.wind_gust_kmh,
                point.wind_direction_deg,
                point.visibility_m,
                point.precipitation_mm,
                point.cloud_cover_pct,
                point.weather_code,
                point.risk_level,
                point.flight_status,
                point.summary,
                json.dumps(payload)[:50_000],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def latest_measurements(limit: int = 24) -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT measured_at, provider, location_name, temperature_c, wind_speed_kmh,
                   wind_gust_kmh, wind_direction_deg, visibility_m, precipitation_mm,
                   cloud_cover_pct, weather_code, risk_level, flight_status, summary
            FROM weather_measurement
            ORDER BY measured_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def refresh_weather(s: settings_mod.Settings | None = None) -> dict[str, Any]:
    s = (s or settings_mod.load()).normalized()
    if not s.weather_enabled:
        raise RuntimeError("Weather monitor kapali.")
    data = _fetch_json(s)
    points = build_forecast(data)
    current = _nearest_current_point(data) or (points[0] if points else None)
    current = enrich_current_from_forecast(current, points)
    if current:
        _insert_measurement(s, current, data)
    decision = decide_today(points)
    return {
        "location": {
            "name": s.weather_location_name,
            "latitude": s.weather_latitude,
            "longitude": s.weather_longitude,
        },
        "provider": s.weather_provider,
        "updated_at": _now().isoformat(),
        "current": asdict(current) if current else None,
        "decision": decision,
        "forecast": [asdict(p) for p in points],
        "history": latest_measurements(24),
    }


def cached_weather() -> dict[str, Any]:
    history = latest_measurements(24)
    latest = history[0] if history else None
    return {
        "location": {"name": settings_mod.load().weather_location_name},
        "provider": settings_mod.load().weather_provider,
        "updated_at": latest["measured_at"] if latest else None,
        "current": latest,
        "decision": {
            "flight_status": latest["flight_status"] if latest else STATUS_UNKNOWN,
            "risk_level": latest["risk_level"] if latest else RISK_UNKNOWN,
            "title": "Son kayit" if latest else "Veri bekleniyor",
            "summary": latest["summary"] if latest else "Henuz hava olcumu yok.",
        },
        "forecast": [],
        "history": history,
    }


def start_weather_worker() -> None:
    def run() -> None:
        while True:
            s = settings_mod.load().normalized()
            if s.weather_enabled:
                try:
                    refresh_weather(s)
                except Exception:
                    pass
            time.sleep(max(10, s.weather_poll_minutes * 60))

    thread = threading.Thread(target=run, daemon=True, name="weather-monitor")
    thread.start()
