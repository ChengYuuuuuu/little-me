# Digital Bonsai — Open-Meteo collector

This module collects current conditions and versioned hourly forecasts for London using the official
`openmeteo-requests` SDK. It also backfills hourly reanalysis data from Open-Meteo's archive API,
stores everything in SQLite using UTC timestamps, analyses the series, and produces plant-ready 0–1 features.

## Setup (Windows PowerShell, Python 3.11+)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Newer supported Python versions can be used by replacing `py -3.11` with `py`.

Optional environment variables include `BONSAI_DB_PATH`, `BONSAI_LATITUDE`,
`BONSAI_LONGITUDE`, `BONSAI_TIMEZONE`, and `BONSAI_INTERVAL_SECONDS`.

## Commands

```powershell
# One request: current snapshot plus seven-day hourly forecast
python -m weather.collector

# Run until Ctrl+C, collecting every 30 minutes
python -m weather.collector --continuous

# Previous seven complete days from the historical/reanalysis archive
python -m weather.backfill --days 7

# Explicit inclusive archive range
python -m weather.backfill --start 2026-10-01 --end 2026-10-31

# Summaries and three plots in outputs/
python -m weather.analysis

# Tests
python -m pytest -q
```

The default database is `data/bonsai.db`. To confirm collection, run:

```powershell
python -c "import sqlite3; d=sqlite3.connect('data/bonsai.db'); print(d.execute('select status, completed_at_utc, response_count from api_requests order by id desc limit 5').fetchall())"
```

Successful cycles appear as `success`. Errors are retained in `api_requests.error_message`; the continuous
collector logs them, backs off, and keeps running. Ctrl+C performs a graceful shutdown.

## Data semantics

- All database timestamps are ISO-8601 UTC. `weather_timestamp_utc` is the API value's valid time;
  `retrieval_timestamp_utc` is when this program received it. `Europe/London` is for presentation only.
- `current_weather` contains API current-condition snapshots. `hourly_weather` distinguishes `forecast`
  from `historical`. Archive records are reanalysis/model-derived historical weather, not raw station readings.
- A content hash prevents identical repeated records. If the forecast for a valid hour changes, the revised
  values get another immutable row instead of overwriting the earlier version. Analysis prefers historical
  rows, otherwise the latest forecast version for each hour.
- Units are stored in every row as documented metadata: °C, %, mm, seconds, WMO code, km/h, and boolean.
  Missing API values remain null and mark a row `partial`; analysis never interpolates or fabricates them.
- Precipitation and sunshine are preceding-hour sums, while common fields such as temperature and cloud
  cover are instantaneous at the valid time.

## Plant feature mapping

`weather.plant_features.normalized_features` preserves missing values and uses explicit artistic mappings:
sunshine seconds / 3600, cloud cover / 100, precipitation / 5 mm per hour, and temperature linearly from
-5 °C (0) to 30 °C (1). Brightness is a day/night-gated blend of 70% sunshine and 30% inverse cloudiness.
All values are clamped to 0–1. These bounds and weights are visual-design choices, not measured weather indices.

The SDK client follows Open-Meteo's recommended `requests-cache` plus `retry-requests` setup. Forecast cache
entries expire after 15 minutes; archive requests cache indefinitely. No TouchDesigner integration is included.

## Automated cloud collection (GitHub Actions + Supabase)

Cloud mode is optional. Local SQLite remains the default; no credentials are stored in this repository.
The workflow runs one collection at minute 7 and 37 of every hour, avoiding the busiest top-of-hour period.
Its concurrency group allows only one collector run at a time. Scheduled jobs can start later than their nominal
cron time, so judge success by persisted request timestamps rather than exact start time.

You must create the external resources yourself before enabling this:

1. Create or choose a GitHub repository and push this project, including
   `.github/workflows/weather-collector.yml`, to its default branch.
2. Create a Supabase project. In **Connect**, copy the **Session pooler** connection string. GitHub-hosted
   runners use IPv4, so do not use the direct IPv6-only connection unless your Supabase project has IPv4 support.
3. Replace the password placeholder. Percent-encode reserved password characters. Add `?sslmode=require` if
   the copied URL has no SSL option (the application also enforces this automatically).
4. In GitHub: **Settings → Secrets and variables → Actions → New repository secret**. Name it exactly
   `SUPABASE_DB_URL` and paste the full PostgreSQL connection string. Never put it in a file or workflow YAML.
5. Open **Actions → Collect London weather → Run workflow** once. This safely creates/migrates the tables and
   performs one collection. Only after that succeeds should you rely on the 30-minute schedule.

The workflow deliberately invokes `python -m weather.collector` once, without `--continuous`. Each new GitHub
runner exits after collection. The PostgreSQL schema uses `TIMESTAMPTZ`, JSONB metadata, the same quality/source
fields, and the same content hashes and uniqueness keys as SQLite. Identical reruns are ignored; revised forecast
values for the same valid hour remain separate records.

### Cloud administration and synchronization

For local commands, set the connection string only for the current PowerShell process:

```powershell
$env:SUPABASE_DB_URL = 'postgresql://...your Session pooler URL...?sslmode=require'

# Apply the repeatable schema migration explicitly
python -m weather.cloud migrate

# Upload existing data/bonsai.db weather rows; safe to repeat
python -m weather.cloud upload

# Download new cloud rows into local SQLite; safe to repeat
python -m weather.cloud download

# Display cloud row counts and the five latest request results
python -m weather.cloud status

# Use another local database if desired
python -m weather.cloud download --db data/cloud-copy.db

Remove-Item Env:SUPABASE_DB_URL
```

Upload/download copy weather data idempotently and preserve valid time, retrieval time, source, data type,
quality, units, values, and revision hash. Request audit IDs are database-local and are not copied; cloud requests
created by scheduled collection retain their own complete audit metadata. Local analysis and TouchDesigner-facing
work can continue to use `data/bonsai.db` after a download.

### Verifying scheduled persistence

After manually dispatching the workflow:

1. Confirm the GitHub Actions run has green checks for secret validation and collection.
2. Run `python -m weather.cloud status`. `api_requests` should increase by one per successful run, and the newest
   entry should have `status: success`, a completion time, and `response_count: 169`.
3. Wait for another scheduled run and repeat the status command. The latest request timestamp must advance.
   Weather row counts may increase by less than 169 because unchanged forecast values are intentionally deduplicated.
4. Run `python -m weather.cloud download`, then `python -m weather.analysis` to verify the persisted cloud data
   can still drive local analysis and plotting.

If the secret is absent, the workflow fails at **Validate cloud secret** instead of silently writing to an ephemeral
runner database. GitHub and Supabase setup cannot be verified locally without your repository and database credentials.
