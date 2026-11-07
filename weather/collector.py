"""One-shot and resilient continuous weather collector."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
import signal
import threading
import time

import config
from weather.client import create_client, parse_current, parse_hourly
from weather.database import begin_request, connect, finish_request, insert_current, insert_hourly

LOG = logging.getLogger("digital_bonsai.weather")

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def collect_once(db_path=config.DB_PATH, client=None) -> dict:
    db = connect(db_path)
    client = client or create_client()
    params = {"latitude": config.LATITUDE, "longitude": config.LONGITUDE,
              "timezone": "GMT", "current": config.CURRENT_VARIABLES,
              "hourly": config.HOURLY_VARIABLES, "forecast_days": 7}
    started = now_utc()
    request_id = begin_request(db, started, config.FORECAST_URL, "forecast", params)
    try:
        response = client.weather_api(config.FORECAST_URL, params=params)[0]
        retrieved = now_utc()
        current = parse_current(response, retrieved)
        hourly = parse_hourly(response, retrieved, "forecast")
        current_added = insert_current(db, current, config.UNITS, request_id)
        hourly_added = insert_hourly(db, hourly, config.UNITS, request_id)
        finish_request(db, request_id, now_utc(), "success", 1 + len(hourly))
        return {"current_inserted": current_added, "hourly_inserted": hourly_added,
                "hourly_received": len(hourly), "retrieved_at_utc": retrieved}
    except Exception as exc:
        finish_request(db, request_id, now_utc(), "error", error=str(exc))
        raise
    finally:
        db.close()

def run_forever(interval: int = config.COLLECTION_INTERVAL_SECONDS):
    stop = threading.Event()
    def request_stop(*_):
        LOG.info("Shutdown requested; finishing cleanly")
        stop.set()
    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    failures = 0
    while not stop.is_set():
        cycle_start = time.monotonic()
        try:
            result = collect_once()
            failures = 0
            LOG.info("Collection complete: %s", result)
        except Exception:
            failures += 1
            LOG.exception("Collection failed; collector will continue")
        normal_wait = max(0, interval - (time.monotonic() - cycle_start))
        wait_for = min(normal_wait, 60 * (2 ** min(failures - 1, 5))) if failures else normal_wait
        stop.wait(wait_for)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--interval", type=int, default=config.COLLECTION_INTERVAL_SECONDS,
                        help="Seconds between cycles (default: 1800)")
    parser.add_argument("--db", default=str(config.DB_PATH))
    parser.add_argument("--database-url", default=config.DATABASE_URL,
                        help="PostgreSQL URL (prefer SUPABASE_DB_URL environment secret)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.continuous:
        run_forever(args.interval)
    else:
        print(collect_once(args.database_url or args.db))

if __name__ == "__main__":
    main()
