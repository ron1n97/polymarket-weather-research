#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
CLOB_HISTORY_URL = "https://clob.polymarket.com/prices-history"
PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
DATA_API_TRADES_URL = "https://data-api.polymarket.com/trades"


@dataclass(frozen=True)
class CityConfig:
    name: str
    series_slug: str
    latitude: float
    longitude: float
    timezone: str
    settlement_unit: str


CITIES: tuple[CityConfig, ...] = (
    CityConfig("Tokyo", "tokyo-daily-weather", 35.5494, 139.7798, "Asia/Tokyo", "C"),
    CityConfig("Seoul", "seoul-daily-weather", 37.4602, 126.4407, "Asia/Seoul", "C"),
    CityConfig("Singapore", "singapore-daily-weather", 1.3644, 103.9915, "Asia/Singapore", "C"),
    CityConfig("Shanghai", "shanghai-daily-weather", 31.1443, 121.8083, "Asia/Shanghai", "C"),
    CityConfig("Beijing", "beijing-daily-weather", 40.0799, 116.6031, "Asia/Shanghai", "C"),
    CityConfig("Shenzhen", "shenzhen-daily-weather", 22.6393, 113.8107, "Asia/Shanghai", "C"),
    CityConfig("Chongqing", "chongqing-daily-weather", 29.7192, 106.6416, "Asia/Shanghai", "C"),
    CityConfig("Wuhan", "wuhan-daily-weather", 30.7766, 114.2081, "Asia/Shanghai", "C"),
    CityConfig("Chengdu", "chengdu-daily-weather", 30.5785, 103.9471, "Asia/Shanghai", "C"),
    CityConfig("Hong Kong", "hong-kong-daily-weather", 22.3080, 113.9185, "Asia/Hong_Kong", "C"),
    CityConfig("Taipei", "taipei-daily-weather", 25.0797, 121.2342, "Asia/Taipei", "C"),
    CityConfig("Kuala Lumpur", "kuala-lumpur-daily-weather", 2.7456, 101.7072, "Asia/Kuala_Lumpur", "C"),
    CityConfig("Paris", "paris-daily-weather", 49.0097, 2.5479, "Europe/Paris", "C"),
    CityConfig("London", "london-daily-weather", 51.5053, 0.0553, "Europe/London", "F"),
    CityConfig("Dallas", "dallas-daily-weather", 32.8471, -96.8518, "America/Chicago", "F"),
    CityConfig("New York City", "nyc-daily-weather", 40.7769, -73.8740, "America/New_York", "F"),
)

CITY_BY_SERIES = {city.series_slug: city for city in CITIES}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch historical Polymarket weather market snapshots for backtesting.")
    parser.add_argument(
        "--output",
        default="outputs/polymarket/historical_weather_markets.csv",
        help="Output CSV path. Default: outputs/polymarket/historical_weather_markets.csv",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/polymarket-backtest-cache",
        help="Cache directory. Default: data/polymarket-backtest-cache",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=300,
        help="Maximum closed weather events to inspect. Default: 300",
    )
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=50,
        help="Small delay between remote calls. Default: 50",
    )
    return parser.parse_args()


def fetch_json(url: str, cache_path: Path) -> dict | list:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; weather-backtest/1.0)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    cache_path.write_text(json.dumps(payload))
    return payload


def parse_bucket_bounds(label: str) -> tuple[int | None, int | None, str | None]:
    low_match = re.fullmatch(r"(-?\d+)°([CF]) or below", label)
    if low_match:
        value = int(low_match.group(1))
        return None, value, low_match.group(2)
    high_match = re.fullmatch(r"(-?\d+)°([CF]) or higher", label)
    if high_match:
        value = int(high_match.group(1))
        return value, None, high_match.group(2)
    exact_match = re.fullmatch(r"(-?\d+)°([CF])", label)
    if exact_match:
        value = int(exact_match.group(1))
        return value, value, exact_match.group(2)
    range_match = re.fullmatch(r"(-?\d+)-(-?\d+)°([CF])", label)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2)), range_match.group(3)
    return None, None, None


def fetch_closed_weather_events(cache_dir: Path, max_events: int) -> list[dict]:
    events: list[dict] = []
    offset = 0
    limit = 200
    while len(events) < max_events:
        cache_path = cache_dir / "gamma-events" / f"closed_weather_offset_{offset}.json"
        url = f"{GAMMA_EVENTS_URL}?closed=true&tag_slug=weather&limit={limit}&offset={offset}"
        batch = fetch_json(url, cache_path)
        if not batch:
            break
        events.extend(batch)
        offset += limit
    filtered = [
        event
        for event in events
        if event.get("seriesSlug") in CITY_BY_SERIES and event.get("markets")
    ]
    filtered.sort(key=lambda event: event.get("closedTime") or event.get("endDate") or "", reverse=True)
    return filtered[:max_events]


def parse_yes_token_id(clob_token_ids_raw: str) -> str:
    token_ids = json.loads(clob_token_ids_raw)
    return token_ids[0]


def fetch_opening_price(condition_id: str, cache_dir: Path) -> tuple[float | None, int | None]:
    cache_path = cache_dir / "data-api-trades" / f"{condition_id}.json"
    url = f"{DATA_API_TRADES_URL}?market={condition_id}&limit=10000&offset=0"
    trades = fetch_json(url, cache_path)
    if not trades:
        return None, None
    earliest = min(trades, key=lambda trade: int(trade["timestamp"]))
    if earliest.get("outcome") == "Yes":
        yes_price = float(earliest["price"])
    else:
        yes_price = 1.0 - float(earliest["price"])
    return yes_price, int(earliest["timestamp"])


def fetch_forecast_center(city: CityConfig, market_date: str, cache_dir: Path) -> tuple[float | None, int | None]:
    query = urlencode(
        {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "start_date": market_date,
            "end_date": market_date,
            "hourly": "temperature_2m_previous_day4",
            "timezone": city.timezone,
        }
    )
    cache_path = cache_dir / "previous-runs" / f"{city.series_slug}_{market_date}.json"
    payload = fetch_json(f"{PREVIOUS_RUNS_URL}?{query}", cache_path)
    hourly = payload.get("hourly", {})
    temps = hourly.get("temperature_2m_previous_day4") or []
    temps = [temp for temp in temps if temp is not None]
    if not temps:
        return None, None
    max_c = max(temps)
    if city.settlement_unit == "F":
        return max_c, round((max_c * 9 / 5) + 32)
    return max_c, round(max_c)


def resolved_yes_from_market(market: dict) -> int | None:
    prices = json.loads(market.get("outcomePrices", "[]"))
    if len(prices) < 2:
        return None
    yes_price = float(prices[0])
    no_price = float(prices[1])
    if yes_price == 1.0 and no_price == 0.0:
        return 1
    if yes_price == 0.0 and no_price == 1.0:
        return 0
    return None


def main() -> None:
    args = parse_args()
    cache_dir = Path(args.cache_dir)
    output_path = Path(args.output)

    events = fetch_closed_weather_events(cache_dir, args.max_events)
    rows: list[dict[str, str | float | int]] = []

    for event in events:
        city = CITY_BY_SERIES[event["seriesSlug"]]
        market_date = str(event["endDate"])[:10]
        forecast_max_c, center_bin = fetch_forecast_center(city, market_date, cache_dir)
        time.sleep(args.sleep_ms / 1000)

        for market in event["markets"]:
            resolved_yes = resolved_yes_from_market(market)
            if resolved_yes is None:
                continue
            label = market.get("groupItemTitle") or market.get("title") or ""
            low, high, unit = parse_bucket_bounds(label)
            token_id = parse_yes_token_id(market["clobTokenIds"])
            opening_price, opening_ts = fetch_opening_price(market["conditionId"], cache_dir)
            time.sleep(args.sleep_ms / 1000)

            rows.append(
                {
                    "city": city.name,
                    "series_slug": city.series_slug,
                    "market_date": market_date,
                    "event_slug": event["slug"],
                    "market_slug": market["slug"],
                    "bucket_label": label,
                    "bucket_low_c": "" if low is None else low,
                    "bucket_high_c": "" if high is None else high,
                    "bucket_unit": unit or city.settlement_unit,
                    "yes_price": "" if opening_price is None else opening_price,
                    "opening_price_ts": "" if opening_ts is None else opening_ts,
                    "center_bin": "" if center_bin is None else center_bin,
                    "forecast_max_c": "" if forecast_max_c is None else round(forecast_max_c, 1),
                    "resolved_yes": resolved_yes,
                    "market_opened_at": market.get("startDate", ""),
                    "market_closed_at": market.get("closedTime", ""),
                    "condition_id": market["conditionId"],
                    "token_id": token_id,
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "city",
        "series_slug",
        "market_date",
        "event_slug",
        "market_slug",
        "bucket_label",
        "bucket_low_c",
        "bucket_high_c",
        "bucket_unit",
        "yes_price",
        "opening_price_ts",
        "center_bin",
        "forecast_max_c",
        "resolved_yes",
        "market_opened_at",
        "market_closed_at",
        "condition_id",
        "token_id",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} historical market rows to {output_path}")
    print(f"Cities={len({row['city'] for row in rows})} Events={len({(row['city'], row['market_date']) for row in rows})}")


if __name__ == "__main__":
    main()
