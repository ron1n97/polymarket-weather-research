#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

@dataclass(frozen=True)
class ForecastCity:
    city: str
    latitude: float
    longitude: float
    timezone: str


CITIES: tuple[ForecastCity, ...] = (
    ForecastCity("Tokyo", 35.5494, 139.7798, "Asia/Tokyo"),
    ForecastCity("Seoul", 37.4602, 126.4407, "Asia/Seoul"),
    ForecastCity("Singapore", 1.3644, 103.9915, "Asia/Singapore"),
    ForecastCity("Shanghai", 31.1443, 121.8083, "Asia/Shanghai"),
    ForecastCity("Beijing", 40.0799, 116.6031, "Asia/Shanghai"),
    ForecastCity("Shenzhen", 22.6393, 113.8107, "Asia/Shanghai"),
    ForecastCity("Chongqing", 29.7192, 106.6416, "Asia/Shanghai"),
    ForecastCity("Wuhan", 30.7766, 114.2081, "Asia/Shanghai"),
    ForecastCity("Chengdu", 30.5785, 103.9471, "Asia/Shanghai"),
    ForecastCity("Hong Kong", 22.3080, 113.9185, "Asia/Hong_Kong"),
    ForecastCity("Taipei", 25.0797, 121.2342, "Asia/Taipei"),
    ForecastCity("Kuala Lumpur", 2.7456, 101.7072, "Asia/Kuala_Lumpur"),
    ForecastCity("Paris", 49.0097, 2.5479, "Europe/Paris"),
    ForecastCity("London", 51.5053, 0.0553, "Europe/London"),
    ForecastCity("Dallas", 32.8471, -96.8518, "America/Chicago"),
    ForecastCity("New York City", 40.7769, -73.8740, "America/New_York"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch current forecast snapshot for tracked cities.")
    parser.add_argument(
        "--forecast-date",
        default=date.today().strftime("%Y-%m-%d"),
        help="Target date in YYYY-MM-DD. Default: today",
    )
    parser.add_argument(
        "--output",
        default="outputs/forecast/current_forecast_snapshot.csv",
        help="Output CSV path. Default: outputs/forecast/current_forecast_snapshot.csv",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    rows: list[dict[str, str | float | int]] = []

    for city in CITIES:
        query = urlencode(
            {
                "latitude": city.latitude,
                "longitude": city.longitude,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                "timezone": city.timezone,
                "forecast_days": 7,
            }
        )
        url = f"https://api.open-meteo.com/v1/forecast?{query}"
        with urlopen(url, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        daily = payload["daily"]
        times = list(daily["time"])
        if args.forecast_date not in times:
            rows.append(
                {
                    "city": city.city,
                    "forecast_date": args.forecast_date,
                    "source": "Open-Meteo",
                    "forecast_max_c": "",
                    "forecast_min_c": "",
                    "precipitation_sum_mm": "",
                    "weather_code": "",
                    "rounded_center_bin_c": "",
                    "forecast_url": url,
                    "status": "missing target date",
                }
            )
            continue
        idx = times.index(args.forecast_date)
        max_c = float(daily["temperature_2m_max"][idx])
        rows.append(
            {
                "city": city.city,
                "forecast_date": args.forecast_date,
                "source": "Open-Meteo",
                "forecast_max_c": f"{max_c:.1f}",
                "forecast_min_c": f"{float(daily['temperature_2m_min'][idx]):.1f}",
                "precipitation_sum_mm": f"{float(daily['precipitation_sum'][idx]):.2f}",
                "weather_code": int(daily["weather_code"][idx]),
                "rounded_center_bin_c": round(max_c),
                "forecast_url": url,
                "status": "ok",
            }
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    pd.DataFrame(rows).to_csv(output_path, index=False)
    print(f"Saved {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
