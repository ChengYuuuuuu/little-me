from datetime import date
import sqlite3

import numpy as np
import pytest

from weather.backfill import backfill
from weather.client import parse_current, parse_hourly
from weather.collector import collect_once
from weather.database import connect, insert_hourly
from weather.plant_features import normalized_features
import config

class Variable:
    def __init__(self, value=None, values=None): self.value, self.values = value, values
    def Value(self): return self.value
    def ValuesAsNumpy(self): return np.asarray(self.values, dtype=float)

class Current:
    def Time(self): return 1_700_000_000
    def Variables(self, index): return Variable(value=[12, 80, 75, .2, 3, 10, 1][index])

class Hourly:
    def Time(self): return 1_699_999_200
    def TimeEnd(self): return 1_700_006_400
    def Interval(self): return 3600
    def Variables(self, index):
        return Variable(values=[[10, 11], [80, 81], [70, 60], [0, .5], [0, 900], [3, 61], [8, 9]][index])

class Response:
    def Current(self): return Current()
    def Hourly(self): return Hourly()

class Client:
    def weather_api(self, url, params): return [Response()]

def test_parsing_uses_utc_and_preserves_hourly_time():
    current = parse_current(Response(), "2023-01-01T00:00:00Z")
    rows = parse_hourly(Response(), "2023-01-01T00:00:00Z", "forecast")
    assert current["weather_timestamp_utc"].endswith("Z")
    assert len(rows) == 2
    assert rows[1]["weather_timestamp_utc"] > rows[0]["weather_timestamp_utc"]

def test_collection_is_idempotent_but_preserves_revisions(tmp_path):
    path = tmp_path / "bonsai.db"
    first = collect_once(path, Client()); second = collect_once(path, Client())
    assert first["hourly_inserted"] == 2
    assert second["hourly_inserted"] == 0
    db = sqlite3.connect(path)
    assert db.execute("select count(*) from api_requests").fetchone()[0] == 2
    assert db.execute("select count(*) from current_weather").fetchone()[0] == 1

def test_changed_forecast_is_new_version(tmp_path):
    db = connect(tmp_path / "db.sqlite")
    base = {"weather_timestamp_utc":"2024-01-01T00:00:00Z", "retrieval_timestamp_utc":"2024-01-01T01:00:00Z",
            "source":"open-meteo", "data_type":"forecast", "temperature_2m":10}
    assert insert_hourly(db, [base], config.UNITS, None) == 1
    revised = dict(base, temperature_2m=11, retrieval_timestamp_utc="2024-01-01T02:00:00Z")
    assert insert_hourly(db, [revised], config.UNITS, None) == 1

def test_plant_features_are_bounded_and_missing_is_explicit():
    values = normalized_features(sunshine_duration=5000, cloud_cover=120, precipitation=10,
                                 temperature_2m=50, is_day=1)
    assert all(0 <= value <= 1 for value in values.values())
    missing = normalized_features(sunshine_duration=None, cloud_cover=50, precipitation=0,
                                  temperature_2m=10)
    assert missing["sunlight_level"] is None and missing["environmental_brightness"] is None

def test_backfill_validates_dates(tmp_path):
    with pytest.raises(ValueError):
        backfill(date(2024, 2, 2), date(2024, 2, 1), tmp_path / "x.db", Client())
