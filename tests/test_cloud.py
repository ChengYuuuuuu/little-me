import json
import sqlite3

import config
from weather.cloud import copy_weather
from weather.cloud_database import PostgresDatabase, secure_dsn
from weather.database import connect, insert_current, insert_hourly

class Cursor:
    def __init__(self, row=None, rows=None, rowcount=1):
        self._row, self._rows, self.rowcount = row, rows or [], rowcount
    def fetchone(self): return self._row
    def fetchall(self): return self._rows

class FakeConnection:
    def __init__(self): self.calls, self.commits, self.closed = [], 0, False
    def execute(self, sql, params=None, **kwargs):
        self.calls.append((sql, params))
        if "RETURNING id" in sql: return Cursor({"id": 42})
        return Cursor(rowcount=1)
    def commit(self): self.commits += 1
    def close(self): self.closed = True

def hourly(temp=10):
    return {"weather_timestamp_utc":"2024-01-01T00:00:00Z", "retrieval_timestamp_utc":"2024-01-01T01:00:00Z",
            "source":"open-meteo", "data_type":"forecast", "temperature_2m":temp}

def current(temp=10):
    return {"weather_timestamp_utc":"2024-01-01T00:15:00Z", "retrieval_timestamp_utc":"2024-01-01T01:00:00Z",
            "source":"open-meteo", "temperature_2m":temp}

def test_cloud_migration_and_operations_use_conflict_deduplication():
    fake = FakeConnection(); db = PostgresDatabase("unused", connection=fake)
    assert "CREATE TABLE IF NOT EXISTS hourly_weather" in fake.calls[0][0]
    assert db.begin_request("2024-01-01T00:00:00Z", "endpoint", "forecast", {}) == 42
    assert db.insert_hourly([hourly()], config.UNITS, 42) == 1
    assert db.insert_current(current(), config.UNITS, 42) == 1
    db.finish_request(42, "2024-01-01T01:00:00Z", "success", 2)
    sql = "\n".join(call[0] for call in fake.calls)
    assert "ON CONFLICT (source,data_type,weather_timestamp_utc,content_hash) DO NOTHING" in sql
    assert "ON CONFLICT (source,weather_timestamp_utc,content_hash) DO NOTHING" in sql

def test_secure_dsn_requires_tls_without_overriding_explicit_mode():
    assert secure_dsn("postgresql://example/db").endswith("?sslmode=require")
    assert secure_dsn("postgresql://example/db?x=1").endswith("&sslmode=require")
    assert secure_dsn("postgresql://example/db?sslmode=verify-full").endswith("sslmode=verify-full")

def test_sqlite_to_cloud_upload_preserves_rows_and_is_repeatable(tmp_path):
    source = connect(tmp_path / "source.db")
    insert_hourly(source, [hourly()], config.UNITS, None)
    insert_current(source, current(), config.UNITS, None)
    destination = connect(tmp_path / "destination.db")
    first = copy_weather(source, destination); second = copy_weather(source, destination)
    assert first["hourly_weather"] == 1 and first["current_weather"] == 1
    assert second["hourly_weather"] == 0 and second["current_weather"] == 0
    assert destination.execute("select count(*) from hourly_weather").fetchone()[0] == 1
    assert destination.execute("select data_quality from hourly_weather").fetchone()[0] == "partial"
