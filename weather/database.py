"""SQLite persistence with immutable weather versions and request auditing."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Mapping, Any

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS api_requests (
 id INTEGER PRIMARY KEY,
 requested_at_utc TEXT NOT NULL,
 completed_at_utc TEXT,
 endpoint TEXT NOT NULL,
 request_type TEXT NOT NULL,
 parameters_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('started','success','error')),
 response_count INTEGER NOT NULL DEFAULT 0,
 error_message TEXT
);
CREATE TABLE IF NOT EXISTS hourly_weather (
 id INTEGER PRIMARY KEY,
 weather_timestamp_utc TEXT NOT NULL,
 retrieval_timestamp_utc TEXT NOT NULL,
 source TEXT NOT NULL,
 data_type TEXT NOT NULL CHECK(data_type IN ('forecast','historical')),
 temperature_2m REAL, relative_humidity_2m REAL, cloud_cover REAL,
 precipitation REAL, sunshine_duration REAL, weather_code INTEGER,
 wind_speed_10m REAL,
 units_json TEXT NOT NULL, data_quality TEXT NOT NULL,
 content_hash TEXT NOT NULL,
 request_id INTEGER REFERENCES api_requests(id),
 UNIQUE(source, data_type, weather_timestamp_utc, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_hourly_time ON hourly_weather(weather_timestamp_utc);
CREATE TABLE IF NOT EXISTS current_weather (
 id INTEGER PRIMARY KEY,
 weather_timestamp_utc TEXT NOT NULL,
 retrieval_timestamp_utc TEXT NOT NULL,
 source TEXT NOT NULL,
 temperature_2m REAL, relative_humidity_2m REAL, cloud_cover REAL,
 precipitation REAL, weather_code INTEGER, wind_speed_10m REAL, is_day INTEGER,
 units_json TEXT NOT NULL, data_quality TEXT NOT NULL,
 content_hash TEXT NOT NULL,
 request_id INTEGER REFERENCES api_requests(id),
 UNIQUE(source, weather_timestamp_utc, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_current_time ON current_weather(weather_timestamp_utc);
"""

def connect(path: Path | str):
    if isinstance(path, str) and path.startswith(("postgres://", "postgresql://")):
        from weather.cloud_database import PostgresDatabase
        return PostgresDatabase(path)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db

@contextmanager
def transaction(db: sqlite3.Connection):
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise

def begin_request(db, requested_at: str, endpoint: str, request_type: str, params: Mapping) -> int:
    if getattr(db, "is_postgres", False):
        return db.begin_request(requested_at, endpoint, request_type, params)
    cur = db.execute(
        "INSERT INTO api_requests(requested_at_utc,endpoint,request_type,parameters_json,status) VALUES(?,?,?,?,?)",
        (requested_at, endpoint, request_type, json.dumps(params, sort_keys=True), "started"),
    )
    db.commit()
    return int(cur.lastrowid)

def finish_request(db, request_id: int, completed_at: str, status: str, count: int = 0, error: str | None = None):
    if getattr(db, "is_postgres", False):
        return db.finish_request(request_id, completed_at, status, count, error)
    db.execute("UPDATE api_requests SET completed_at_utc=?,status=?,response_count=?,error_message=? WHERE id=?",
               (completed_at, status, count, error, request_id))
    db.commit()

def _hash(row: Mapping[str, Any], fields: Iterable[str]) -> str:
    payload = {key: row.get(key) for key in fields}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

HOURLY_FIELDS = ("temperature_2m", "relative_humidity_2m", "cloud_cover", "precipitation",
                 "sunshine_duration", "weather_code", "wind_speed_10m")
CURRENT_FIELDS = ("temperature_2m", "relative_humidity_2m", "cloud_cover", "precipitation",
                  "weather_code", "wind_speed_10m", "is_day")

def insert_hourly(db, rows: Iterable[Mapping], units: Mapping, request_id: int) -> int:
    if getattr(db, "is_postgres", False):
        return db.insert_hourly(rows, units, request_id)
    inserted = 0
    sql = """INSERT OR IGNORE INTO hourly_weather
      (weather_timestamp_utc,retrieval_timestamp_utc,source,data_type,temperature_2m,
       relative_humidity_2m,cloud_cover,precipitation,sunshine_duration,weather_code,
       wind_speed_10m,units_json,data_quality,content_hash,request_id)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    for row in rows:
        values = [row.get(k) for k in HOURLY_FIELDS]
        quality = "valid" if all(v is not None for v in values) else "partial"
        cur = db.execute(sql, (row["weather_timestamp_utc"], row["retrieval_timestamp_utc"],
            row["source"], row["data_type"], *values, json.dumps(units, sort_keys=True), quality,
            _hash(row, HOURLY_FIELDS), request_id))
        inserted += cur.rowcount
    db.commit()
    return inserted

def insert_current(db, row: Mapping, units: Mapping, request_id: int) -> int:
    if getattr(db, "is_postgres", False):
        return db.insert_current(row, units, request_id)
    values = [row.get(k) for k in CURRENT_FIELDS]
    quality = "valid" if all(v is not None for v in values) else "partial"
    cur = db.execute("""INSERT OR IGNORE INTO current_weather
      (weather_timestamp_utc,retrieval_timestamp_utc,source,temperature_2m,relative_humidity_2m,
       cloud_cover,precipitation,weather_code,wind_speed_10m,is_day,units_json,data_quality,content_hash,request_id)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (row["weather_timestamp_utc"], row["retrieval_timestamp_utc"], row["source"], *values,
       json.dumps(units, sort_keys=True), quality, _hash(row, CURRENT_FIELDS), request_id))
    db.commit()
    return cur.rowcount
