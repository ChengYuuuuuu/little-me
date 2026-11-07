"""Analyse stored weather and generate plots without inventing missing values."""
from __future__ import annotations
import argparse
from pathlib import Path
import sqlite3

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config

def load_series(db_path=config.DB_PATH) -> pd.DataFrame:
    db = sqlite3.connect(db_path)
    # Prefer historical/reanalysis. Otherwise select the latest retrieved forecast version per valid hour.
    query = """WITH ranked AS (
      SELECT *, ROW_NUMBER() OVER(PARTITION BY weather_timestamp_utc ORDER BY
        CASE data_type WHEN 'historical' THEN 0 ELSE 1 END, retrieval_timestamp_utc DESC) AS rn
      FROM hourly_weather)
      SELECT * FROM ranked WHERE rn=1 ORDER BY weather_timestamp_utc"""
    try:
        frame = pd.read_sql_query(query, db)
    finally:
        db.close()
    if not frame.empty:
        frame["time"] = pd.to_datetime(frame.weather_timestamp_utc, utc=True)
        frame = frame.set_index("time")
    return frame

def summaries(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"row_count": 0, "message": "No hourly weather records available"}
    numeric = ["temperature_2m", "cloud_cover", "precipitation", "sunshine_duration"]
    daily = frame[numeric].resample("1D").agg({"temperature_2m": "mean", "cloud_cover": "mean",
        "precipitation": "sum", "sunshine_duration": "sum"})
    expected = int((frame.index.max() - frame.index.min()).total_seconds() // 3600) + 1
    present = frame.index.floor("h").nunique()
    result = {
        "row_count": len(frame), "start_utc": frame.index.min().isoformat(), "end_utc": frame.index.max().isoformat(),
        "average_cloud_cover_pct": frame.cloud_cover.mean(),
        "missing_hour_count": max(0, expected - present), "completeness_pct": 100 * present / expected,
        "hourly_temperature_trend_c_per_hour": _slope(frame.temperature_2m),
        "daily_temperature_trend_c_per_day": _slope(daily.temperature_2m) * 24 if len(daily) > 1 else None,
        "missing_values_by_variable": {name: int(frame[name].isna().sum()) for name in numeric},
        "daily": daily.reset_index().to_dict("records"),
    }
    rolling = frame.temperature_2m.rolling("24h", min_periods=1).mean()
    result["latest_rolling_24h_temperature_c"] = None if rolling.empty else rolling.iloc[-1]
    for days in (3, 7):
        recent = frame.loc[frame.index > frame.index.max() - pd.Timedelta(days=days)]
        result[f"recent_{days}d"] = {"hours": len(recent), "mean_temperature_c": recent.temperature_2m.mean(),
            "mean_cloud_cover_pct": recent.cloud_cover.mean(), "precipitation_total_mm": recent.precipitation.sum(min_count=1),
            "sunshine_total_hours": recent.sunshine_duration.sum(min_count=1) / 3600}
    return result

def _slope(series: pd.Series):
    clean = series.dropna()
    if len(clean) < 2:
        return None
    import numpy as np
    x = (clean.index - clean.index[0]).total_seconds() / 3600
    return float(np.polyfit(x, clean.values, 1)[0])

def create_plots(frame: pd.DataFrame, output_dir=config.OUTPUT_DIR) -> list[Path]:
    if frame.empty:
        return []
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    paths = []
    for column, title, ylabel, filename in [
        ("temperature_2m", "Temperature over time", "Temperature (°C)", "temperature.png"),
        ("cloud_cover", "Cloud cover over time", "Cloud cover (%)", "cloud_cover.png")]:
        fig, ax = plt.subplots(figsize=(10, 4)); frame[column].plot(ax=ax)
        ax.set(title=title, xlabel="Time (UTC)", ylabel=ylabel); fig.tight_layout()
        path = output / filename; fig.savefig(path, dpi=150); plt.close(fig); paths.append(path)
    daily = frame.resample("1D").agg({"precipitation": "sum", "sunshine_duration": "sum"})
    fig, left = plt.subplots(figsize=(10, 4)); daily.precipitation.plot.bar(ax=left, color="steelblue", alpha=.7)
    left.set_ylabel("Precipitation (mm)"); right = left.twinx()
    right.plot(range(len(daily)), daily.sunshine_duration / 3600, color="goldenrod", marker="o")
    right.set_ylabel("Sunshine (hours)"); left.set_title("Daily precipitation and sunshine"); fig.tight_layout()
    path = output / "precipitation_sunshine.png"; fig.savefig(path, dpi=150); plt.close(fig); paths.append(path)
    return paths

def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--db", default=str(config.DB_PATH));
    parser.add_argument("--output", default=str(config.OUTPUT_DIR)); args = parser.parse_args()
    frame = load_series(args.db); result = summaries(frame); paths = create_plots(frame, args.output)
    print(pd.Series(result).to_string()); print("Plots:", *(str(p) for p in paths), sep="\n")

if __name__ == "__main__": main()
