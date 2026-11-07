"""PostgreSQL/Supabase implementation of the weather persistence contract."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

from weather.database import CURRENT_FIELDS, HOURLY_FIELDS, _hash

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "001_postgres_weather.sql"

def secure_dsn(dsn: str) -> str:
    """Require TLS unless the caller already selected an SSL mode."""
    if "sslmode=" not in dsn.lower():
        return dsn + ("&" if "?" in dsn else "?") + "sslmode=require"
    return dsn

class PostgresDatabase:
    is_postgres = True

    def __init__(self, dsn: str, apply_migrations: bool = True, connection=None):
        if connection is None:
            import psycopg
            from psycopg.rows import dict_row
            connection = psycopg.connect(secure_dsn(dsn), row_factory=dict_row,
                                         prepare_threshold=None, connect_timeout=20)
        self.connection = connection
        if apply_migrations:
            self.migrate()

    def migrate(self):
        self.connection.execute(MIGRATION.read_text(encoding="utf-8"), prepare=False)
        self.connection.commit()

    def close(self):
        self.connection.close()

    def begin_request(self, requested_at, endpoint, request_type, params):
        row = self.connection.execute(
            """INSERT INTO api_requests
            (requested_at_utc,endpoint,request_type,parameters_json,status)
            VALUES (%s,%s,%s,%s::jsonb,'started') RETURNING id""",
            (requested_at, endpoint, request_type, json.dumps(params, sort_keys=True))).fetchone()
        self.connection.commit()
        return int(row["id"] if isinstance(row, dict) else row[0])

    def finish_request(self, request_id, completed_at, status, count=0, error=None):
        self.connection.execute(
            """UPDATE api_requests SET completed_at_utc=%s,status=%s,response_count=%s,
            error_message=%s WHERE id=%s""", (completed_at, status, count, error, request_id))
        self.connection.commit()

    def insert_hourly(self, rows: Iterable[Mapping], units: Mapping, request_id):
        inserted = 0
        sql = """INSERT INTO hourly_weather
          (weather_timestamp_utc,retrieval_timestamp_utc,source,data_type,temperature_2m,
           relative_humidity_2m,cloud_cover,precipitation,sunshine_duration,weather_code,
           wind_speed_10m,units_json,data_quality,content_hash,request_id)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
          ON CONFLICT (source,data_type,weather_timestamp_utc,content_hash) DO NOTHING"""
        for row in rows:
            values = [row.get(k) for k in HOURLY_FIELDS]
            quality = row.get("data_quality") or ("valid" if all(v is not None for v in values) else "partial")
            cur = self.connection.execute(sql, (row["weather_timestamp_utc"], row["retrieval_timestamp_utc"],
                row["source"], row["data_type"], *values, json.dumps(units, sort_keys=True), quality,
                row.get("content_hash") or _hash(row, HOURLY_FIELDS), request_id))
            inserted += cur.rowcount
        self.connection.commit()
        return inserted

    def insert_current(self, row: Mapping, units: Mapping, request_id):
        values = [row.get(k) for k in CURRENT_FIELDS]
        quality = row.get("data_quality") or ("valid" if all(v is not None for v in values) else "partial")
        cur = self.connection.execute("""INSERT INTO current_weather
          (weather_timestamp_utc,retrieval_timestamp_utc,source,temperature_2m,relative_humidity_2m,
           cloud_cover,precipitation,weather_code,wind_speed_10m,is_day,units_json,data_quality,content_hash,request_id)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
          ON CONFLICT (source,weather_timestamp_utc,content_hash) DO NOTHING""",
          (row["weather_timestamp_utc"], row["retrieval_timestamp_utc"], row["source"], *values,
           json.dumps(units, sort_keys=True), quality,
           row.get("content_hash") or _hash(row, CURRENT_FIELDS), request_id))
        self.connection.commit()
        return cur.rowcount

    def weather_rows(self, table: str):
        if table not in ("hourly_weather", "current_weather"):
            raise ValueError("unsupported table")
        return list(self.connection.execute(f"SELECT * FROM {table} ORDER BY weather_timestamp_utc"))
