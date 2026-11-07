"""Migrate, inspect, and synchronize Digital Bonsai cloud weather storage."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sqlite3

import config
from weather.cloud_database import PostgresDatabase
from weather.database import connect, insert_current, insert_hourly

TABLES = ("hourly_weather", "current_weather")

def _iso(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value

def _units(value):
    return json.loads(value) if isinstance(value, str) else value

def sqlite_rows(db: sqlite3.Connection, table: str):
    return [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY weather_timestamp_utc")]

def copy_weather(source, destination) -> dict[str, int]:
    """Idempotently copy weather rows; request audit IDs intentionally remain database-local."""
    result = {}
    for table in TABLES:
        rows = source.weather_rows(table) if getattr(source, "is_postgres", False) else sqlite_rows(source, table)
        inserted = 0
        for raw in rows:
            row = dict(raw)
            row["weather_timestamp_utc"] = _iso(row["weather_timestamp_utc"])
            row["retrieval_timestamp_utc"] = _iso(row["retrieval_timestamp_utc"])
            units = _units(row["units_json"])
            if table == "hourly_weather":
                inserted += insert_hourly(destination, [row], units, None)
            else:
                inserted += insert_current(destination, row, units, None)
        result[table] = inserted
        result[f"{table}_examined"] = len(rows)
    return result

def upload(sqlite_path, database_url: str):
    local = connect(sqlite_path); cloud = PostgresDatabase(database_url)
    try:
        return copy_weather(local, cloud)
    finally:
        local.close(); cloud.close()

def download(database_url: str, sqlite_path):
    cloud = PostgresDatabase(database_url); local = connect(sqlite_path)
    try:
        return copy_weather(cloud, local)
    finally:
        cloud.close(); local.close()

def status(database_url: str):
    cloud = PostgresDatabase(database_url)
    try:
        counts = {}
        for table in (*TABLES, "api_requests"):
            row = cloud.connection.execute(f"SELECT count(*) AS count FROM {table}").fetchone()
            counts[table] = int(row["count"] if isinstance(row, dict) else row[0])
        rows = cloud.connection.execute("""SELECT requested_at_utc,completed_at_utc,status,response_count,
            error_message FROM api_requests ORDER BY id DESC LIMIT 5""").fetchall()
        counts["recent_requests"] = [dict(row) if not isinstance(row, dict) else row for row in rows]
        return counts
    finally:
        cloud.close()

def _url(args):
    url = args.database_url or os.getenv("SUPABASE_DB_URL") or os.getenv("BONSAI_DATABASE_URL")
    if not url:
        raise SystemExit("Set SUPABASE_DB_URL or pass --database-url")
    return url

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("migrate", "upload", "download", "status"))
    parser.add_argument("--database-url", help="Prefer the SUPABASE_DB_URL environment variable")
    parser.add_argument("--db", default=str(config.DB_PATH), help="Local SQLite path")
    args = parser.parse_args(); url = _url(args)
    if args.command == "migrate":
        db = PostgresDatabase(url); db.close(); result = {"migration": "complete"}
    elif args.command == "upload": result = upload(args.db, url)
    elif args.command == "download": result = download(url, args.db)
    else: result = status(url)
    print(json.dumps(result, default=str, indent=2))

if __name__ == "__main__":
    main()
