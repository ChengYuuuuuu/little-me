"""Thin adapter around the official Open-Meteo Python SDK."""
from __future__ import annotations

from datetime import datetime, timezone
import math

from config import CACHE_PATH, CURRENT_VARIABLES, HOURLY_VARIABLES

def create_client(cache_seconds: int = 900):
    import openmeteo_requests
    import requests_cache
    from retry_requests import retry
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cached = requests_cache.CachedSession(str(CACHE_PATH), expire_after=cache_seconds)
    session = retry(cached, retries=5, backoff_factor=0.5)
    return openmeteo_requests.Client(session=session)

def utc_iso(epoch: int | float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")

def _clean(value):
    value = float(value)
    return None if math.isnan(value) else value

def parse_current(response, retrieved_at: str, source: str = "open-meteo") -> dict:
    current = response.Current()
    row = {"weather_timestamp_utc": utc_iso(current.Time()), "retrieval_timestamp_utc": retrieved_at,
           "source": source}
    for i, name in enumerate(CURRENT_VARIABLES):
        value = _clean(current.Variables(i).Value())
        row[name] = int(value) if value is not None and name in ("weather_code", "is_day") else value
    return row

def parse_hourly(response, retrieved_at: str, data_type: str, source: str = "open-meteo") -> list[dict]:
    hourly = response.Hourly()
    arrays = {name: hourly.Variables(i).ValuesAsNumpy() for i, name in enumerate(HOURLY_VARIABLES)}
    times = range(hourly.Time(), hourly.TimeEnd(), hourly.Interval())
    rows = []
    for idx, epoch in enumerate(times):
        row = {"weather_timestamp_utc": utc_iso(epoch), "retrieval_timestamp_utc": retrieved_at,
               "source": source, "data_type": data_type}
        for name, array in arrays.items():
            value = _clean(array[idx])
            row[name] = int(value) if value is not None and name == "weather_code" else value
        rows.append(row)
    return rows
