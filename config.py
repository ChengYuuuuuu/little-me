"""Configuration for the Digital Bonsai weather module."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("BONSAI_DB_PATH", ROOT / "data" / "bonsai.db"))
OUTPUT_DIR = Path(os.getenv("BONSAI_OUTPUT_DIR", ROOT / "outputs"))
CACHE_PATH = Path(os.getenv("BONSAI_CACHE_PATH", ROOT / "data" / ".weather_cache"))

LATITUDE = float(os.getenv("BONSAI_LATITUDE", "51.5074"))
LONGITUDE = float(os.getenv("BONSAI_LONGITUDE", "-0.1278"))
TIMEZONE = os.getenv("BONSAI_TIMEZONE", "Europe/London")
COLLECTION_INTERVAL_SECONDS = int(os.getenv("BONSAI_INTERVAL_SECONDS", "1800"))
DATABASE_URL = os.getenv("BONSAI_DATABASE_URL") or os.getenv("SUPABASE_DB_URL")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

CURRENT_VARIABLES = [
    "temperature_2m", "relative_humidity_2m", "cloud_cover", "precipitation",
    "weather_code", "wind_speed_10m", "is_day",
]
HOURLY_VARIABLES = [
    "temperature_2m", "relative_humidity_2m", "cloud_cover", "precipitation",
    "sunshine_duration", "weather_code", "wind_speed_10m",
]

UNITS = {
    "temperature_2m": "°C", "relative_humidity_2m": "%", "cloud_cover": "%",
    "precipitation": "mm", "sunshine_duration": "s", "weather_code": "WMO code",
    "wind_speed_10m": "km/h", "is_day": "boolean",
}
