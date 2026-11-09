#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
DATA_API_TRADES_URL = "https://data-api.polymarket.com/trades"

CITY_CONFIG = {
    "tokyo-daily-weather": (35.5494, 139.7798, "Asia/Tokyo"),
    "seoul-daily-weather": (37.4602, 126.4407, "Asia/Seoul"),
    "singapore-daily-weather": (1.3644, 103.9915, "Asia/Singapore"),
    "shanghai-daily-weather": (31.1443, 121.8083, "Asia/Shanghai"),
    "beijing-daily-weather": (40.0799, 116.6031, "Asia/Shanghai"),
    "shenzhen-daily-weather": (22.6393, 113.8107, "Asia/Shanghai"),
    "chongqing-daily-weather": (29.7192, 106.6416, "Asia/Shanghai"),
    "wuhan-daily-weather": (30.7766, 114.2081, "Asia/Shanghai"),
    "chengdu-daily-weather": (30.5785, 103.9471, "Asia/Shanghai"),
    "hong-kong-daily-weather": (22.3080, 113.9185, "Asia/Hong_Kong"),
    "taipei-daily-weather": (25.0797, 121.2342, "Asia/Taipei"),
    "kuala-lumpur-daily-weather": (2.7456, 101.7072, "Asia/Kuala_Lumpur"),
    "paris-daily-weather": (49.0097, 2.5479, "Europe/Paris"),
    "london-daily-weather": (51.5053, 0.0553, "Europe/London"),
    "dallas-daily-weather": (32.8471, -96.8518, "America/Chicago"),
    "nyc-daily-weather": (40.7769, -73.8740, "America/New_York"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prefetch deeper Polymarket weather history and archived forecast cache.")
    parser.add_argument("--offset-max", type=int, default=2000, help="Exclusive max offset for Gamma pages.")
    parser.add_argument("--offset-step", type=int, default=200, help="Gamma page step.")
    parser.add_argument(
        "--series",
        nargs="*",
        default=[
            "seoul-daily-weather",
            "tokyo-daily-weather",
            "shanghai-daily-weather",
            "singapore-daily-weather",
            "hong-kong-daily-weather",
            "paris-daily-weather",
            "dallas-daily-weather",
        ],
        help="Series slugs to prefetch.",
    )
    parser.add_argument("--cache-dir", default="data/polymarket-backtest-cache", help="Cache root.")
    return parser.parse_args()


def fetch_json(url: str, path: Path) -> dict | list:
    if path.exists():
        return json.loads(path.read_text())
    path.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"})
    with urlopen(req, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    path.write_text(json.dumps(payload))
    return payload


def main() -> None:
    args = parse_args()
    cache_root = Path(args.cache_dir)
    gamma_dir = cache_root / "gamma-events"
    previous_runs_dir = cache_root / "previous-runs"
    trades_dir = cache_root / "data-api-trades"
    target_series = set(args.series)

    seen_events = 0
    fetched_forecasts = 0
    fetched_trade_files = 0
    for offset in range(0, args.offset_max, args.offset_step):
        gamma_path = gamma_dir / f"closed_weather_offset_{offset}.json"
        gamma_url = f"{GAMMA_EVENTS_URL}?closed=true&tag_slug=weather&limit={args.offset_step}&offset={offset}"
        batch = fetch_json(gamma_url, gamma_path)
        if not batch:
            break
        for event in batch:
            series_slug = event.get("seriesSlug")
            if series_slug not in target_series or not event.get("markets"):
                continue
            seen_events += 1
            market_date = str(event["endDate"])[:10]
            if series_slug not in CITY_CONFIG:
                continue
            lat, lon, tz = CITY_CONFIG[series_slug]
            forecast_path = previous_runs_dir / f"{series_slug}_{market_date}.json"
            query = urlencode(
                {
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": market_date,
                    "end_date": market_date,
                    "hourly": "temperature_2m_previous_day4",
                    "timezone": tz,
                }
            )
            fetch_json(f"{PREVIOUS_RUNS_URL}?{query}", forecast_path)
            fetched_forecasts += 1
            for market in event["markets"]:
                trades_path = trades_dir / f"{market['conditionId']}.json"
                trades_url = f"{DATA_API_TRADES_URL}?market={market['conditionId']}&limit=10000&offset=0"
                fetch_json(trades_url, trades_path)
                fetched_trade_files += 1
            time.sleep(0.05)

    print(f"Seen events={seen_events}")
    print(f"Forecast files ensured={fetched_forecasts}")
    print(f"Trade files ensured={fetched_trade_files}")


if __name__ == "__main__":
    main()
