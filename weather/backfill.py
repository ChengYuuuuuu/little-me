"""Backfill reanalysis data from Open-Meteo's Historical Weather API."""
from __future__ import annotations
import argparse
from datetime import date, datetime, timedelta, timezone

import config
from weather.client import create_client, parse_hourly
from weather.database import begin_request, connect, finish_request, insert_hourly

def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def backfill(start: date, end: date, db_path=config.DB_PATH, client=None) -> dict:
    if start > end:
        raise ValueError("start date must not be after end date")
    if end >= date.today():
        raise ValueError("archive end date must be before today")
    client = client or create_client(cache_seconds=-1)
    params = {"latitude": config.LATITUDE, "longitude": config.LONGITUDE,
              "timezone": "GMT", "start_date": start.isoformat(), "end_date": end.isoformat(),
              "hourly": config.HOURLY_VARIABLES}
    db = connect(db_path)
    request_id = begin_request(db, now_utc(), config.ARCHIVE_URL, "historical", params)
    try:
        response = client.weather_api(config.ARCHIVE_URL, params=params)[0]
        retrieved = now_utc()
        rows = parse_hourly(response, retrieved, "historical")
        added = insert_hourly(db, rows, config.UNITS, request_id)
        finish_request(db, request_id, now_utc(), "success", len(rows))
        return {"inserted": added, "received": len(rows), "start": start.isoformat(), "end": end.isoformat()}
    except Exception as exc:
        finish_request(db, request_id, now_utc(), "error", error=str(exc))
        raise
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--days", type=int, default=7, help="Previous N complete days (default: 7)")
    parser.add_argument("--db", default=str(config.DB_PATH))
    args = parser.parse_args()
    end = args.end or (date.today() - timedelta(days=1))
    start = args.start or (end - timedelta(days=args.days - 1))
    print(backfill(start, end, args.db))

if __name__ == "__main__":
    main()
