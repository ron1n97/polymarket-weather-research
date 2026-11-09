#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd


BASE_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
CACHE_VERSION = "v2"
HOURLY_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "cloud_cover",
    "wind_speed_10m",
    "shortwave_radiation",
]
DAILY_FIELDS = ["temperature_2m_max"]


@dataclass(frozen=True)
class ForecastCity:
    city: str
    icao: str
    timezone: str
    latitude: float
    longitude: float


CITIES: tuple[ForecastCity, ...] = (
    ForecastCity("Tokyo", "RJTT", "Asia/Tokyo", 35.5494, 139.7798),
    ForecastCity("Seoul", "RKSI", "Asia/Seoul", 37.4602, 126.4407),
    ForecastCity("Singapore", "WSSS", "Asia/Singapore", 1.3644, 103.9915),
    ForecastCity("Shanghai", "ZSPD", "Asia/Shanghai", 31.1443, 121.8083),
    ForecastCity("Beijing", "ZBAA", "Asia/Shanghai", 40.0799, 116.6031),
    ForecastCity("Shenzhen", "ZGSZ", "Asia/Shanghai", 22.6393, 113.8107),
    ForecastCity("Chongqing", "ZUCK", "Asia/Shanghai", 29.7192, 106.6416),
    ForecastCity("Wuhan", "ZHHH", "Asia/Shanghai", 30.7766, 114.2081),
    ForecastCity("Chengdu", "ZUUU", "Asia/Shanghai", 30.5785, 103.9471),
    ForecastCity("Hong Kong", "VHHH", "Asia/Hong_Kong", 22.3080, 113.9185),
    ForecastCity("Taipei", "RCTP", "Asia/Taipei", 25.0797, 121.2342),
    ForecastCity("Kuala Lumpur", "WMKK", "Asia/Kuala_Lumpur", 2.7456, 101.7072),
    ForecastCity("Paris", "LFPG", "Europe/Paris", 49.0097, 2.5479),
    ForecastCity("London", "EGLC", "Europe/London", 51.5053, 0.0553),
    ForecastCity("Dallas", "KDAL", "America/Chicago", 32.8471, -96.8518),
    ForecastCity("New York City", "KLGA", "America/New_York", 40.7769, -73.8740),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch archived Open-Meteo forecast features for all cities.")
    parser.add_argument("--start-date", default="2023-01-01", help="Start date inclusive. Default: 2023-01-01")
    parser.add_argument("--end-date", default="2025-12-31", help="End date inclusive. Default: 2025-12-31")
    parser.add_argument(
        "--cache-dir",
        default="data/open-meteo-cache",
        help="Cache directory for raw API payloads. Default: data/open-meteo-cache",
    )
    parser.add_argument(
        "--output",
        default="outputs/openmeteo_forecast_features.csv",
        help="Output CSV path. Default: outputs/openmeteo_forecast_features.csv",
    )
    return parser.parse_args()


def build_url(city: ForecastCity, start_date: str, end_date: str) -> str:
    query = urlencode(
        {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(HOURLY_FIELDS),
            "daily": ",".join(DAILY_FIELDS),
            "timezone": city.timezone,
        }
    )
    return f"{BASE_URL}?{query}"


def fetch_payload(city: ForecastCity, start_date: str, end_date: str, cache_dir: Path) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{city.icao}_{start_date}_{end_date}_{CACHE_VERSION}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    with urlopen(build_url(city, start_date, end_date), timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    cache_path.write_text(json.dumps(payload))
    return payload


def payload_to_frame(city: ForecastCity, payload: dict) -> pd.DataFrame:
    hourly = pd.DataFrame(payload["hourly"])
    daily = pd.DataFrame(payload["daily"])

    hourly["timestamp_local"] = pd.to_datetime(hourly["time"])
    hourly["local_day"] = hourly["timestamp_local"].dt.date.astype(str)
    hourly["cutoff_hour_local"] = hourly["timestamp_local"].dt.strftime("%H:00")
    hourly = hourly.rename(
        columns={
            "temperature_2m": "forecast_temp_2m",
            "relative_humidity_2m": "forecast_relative_humidity_2m",
            "dew_point_2m": "forecast_dew_point_2m",
            "cloud_cover": "forecast_cloud_cover",
            "wind_speed_10m": "forecast_wind_speed_10m",
            "shortwave_radiation": "forecast_shortwave_radiation",
        }
    )
    hourly["forecast_remaining_max_2m"] = hourly.groupby("local_day")["forecast_temp_2m"].transform(
        lambda s: s[::-1].cummax()[::-1]
    )
    hourly["forecast_remaining_max_shortwave_radiation"] = hourly.groupby("local_day")[
        "forecast_shortwave_radiation"
    ].transform(lambda s: s[::-1].cummax()[::-1])
    hourly["forecast_remaining_mean_cloud_cover"] = hourly.groupby("local_day")["forecast_cloud_cover"].transform(
        lambda s: s[::-1].expanding().mean().iloc[::-1].to_numpy()
    )
    hourly["forecast_remaining_mean_relative_humidity"] = hourly.groupby("local_day")[
        "forecast_relative_humidity_2m"
    ].transform(lambda s: s[::-1].expanding().mean().iloc[::-1].to_numpy())
    hourly["forecast_remaining_mean_wind_speed_10m"] = hourly.groupby("local_day")[
        "forecast_wind_speed_10m"
    ].transform(lambda s: s[::-1].expanding().mean().iloc[::-1].to_numpy())
    hourly["forecast_remaining_max_temp_3h"] = hourly.groupby("local_day")["forecast_temp_2m"].transform(
        lambda s: s.rolling(3, min_periods=1).max().shift(-2).ffill()
    )

    daily = daily.rename(columns={"time": "local_day", "temperature_2m_max": "forecast_daily_max_2m"})
    merged = hourly.merge(daily, on="local_day", how="left")
    merged["city"] = city.city
    merged["icao"] = city.icao
    merged["timezone"] = city.timezone
    return merged[
        [
            "city",
            "icao",
            "timezone",
            "local_day",
            "cutoff_hour_local",
            "forecast_temp_2m",
            "forecast_relative_humidity_2m",
            "forecast_dew_point_2m",
            "forecast_cloud_cover",
            "forecast_wind_speed_10m",
            "forecast_shortwave_radiation",
            "forecast_remaining_max_2m",
            "forecast_remaining_max_shortwave_radiation",
            "forecast_remaining_mean_cloud_cover",
            "forecast_remaining_mean_relative_humidity",
            "forecast_remaining_mean_wind_speed_10m",
            "forecast_remaining_max_temp_3h",
            "forecast_daily_max_2m",
        ]
    ]


def main() -> None:
    args = parse_args()
    cache_dir = Path(args.cache_dir)
    output_path = Path(args.output)
    frames = []
    for city in CITIES:
        payload = fetch_payload(city, args.start_date, args.end_date, cache_dir)
        frames.append(payload_to_frame(city, payload))

    df = pd.concat(frames, ignore_index=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved forecast features to {output_path}")
    print(f"Rows={len(df)} Cities={df['city'].nunique()} Range={df['local_day'].min()}..{df['local_day'].max()}")


if __name__ == "__main__":
    main()
