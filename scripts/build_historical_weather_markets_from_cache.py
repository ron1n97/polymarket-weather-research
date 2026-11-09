#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path


GAMMA_CACHE_DIR = Path("data/polymarket-backtest-cache/gamma-events")
TRADES_CACHE_DIR = Path("data/polymarket-backtest-cache/data-api-trades")
FORECAST_CACHE_DIR = Path("data/polymarket-backtest-cache/previous-runs")

TRACKED_SERIES = {
    "tokyo-daily-weather": ("Tokyo", "C"),
    "seoul-daily-weather": ("Seoul", "C"),
    "singapore-daily-weather": ("Singapore", "C"),
    "shanghai-daily-weather": ("Shanghai", "C"),
    "beijing-daily-weather": ("Beijing", "C"),
    "shenzhen-daily-weather": ("Shenzhen", "C"),
    "chongqing-daily-weather": ("Chongqing", "C"),
    "wuhan-daily-weather": ("Wuhan", "C"),
    "chengdu-daily-weather": ("Chengdu", "C"),
    "hong-kong-daily-weather": ("Hong Kong", "C"),
    "taipei-daily-weather": ("Taipei", "C"),
    "kuala-lumpur-daily-weather": ("Kuala Lumpur", "C"),
    "paris-daily-weather": ("Paris", "C"),
    "london-daily-weather": ("London", "F"),
    "dallas-daily-weather": ("Dallas", "F"),
    "nyc-daily-weather": ("New York City", "F"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build historical Polymarket weather market rows from local cache only.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument("--max-events", type=int, default=150, help="Maximum resolved events to consider.")
    return parser.parse_args()


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


def parse_yes_token_id(clob_token_ids_raw: str) -> str:
    token_ids = json.loads(clob_token_ids_raw)
    return token_ids[0]


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


def read_opening_price(condition_id: str) -> tuple[float | None, int | None]:
    path = TRADES_CACHE_DIR / f"{condition_id}.json"
    if not path.exists():
        return None, None
    trades = json.loads(path.read_text())
    if not trades:
        return None, None
    earliest = min(trades, key=lambda trade: int(trade["timestamp"]))
    yes_price = float(earliest["price"]) if earliest.get("outcome") == "Yes" else 1.0 - float(earliest["price"])
    return yes_price, int(earliest["timestamp"])


def read_forecast_center(series_slug: str, market_date: str, settlement_unit: str) -> tuple[float | None, int | None]:
    path = FORECAST_CACHE_DIR / f"{series_slug}_{market_date}.json"
    if not path.exists():
        return None, None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None, None
    temps = (payload.get("hourly") or {}).get("temperature_2m_previous_day4") or []
    temps = [temp for temp in temps if temp is not None]
    if not temps:
        return None, None
    max_c = max(temps)
    center = round((max_c * 9 / 5) + 32) if settlement_unit == "F" else round(max_c)
    return max_c, center


def infer_market_date(event: dict) -> str | None:
    end_date = event.get("endDate")
    if end_date:
        return str(end_date)[:10]

    slug = event.get("slug") or ""
    match = re.search(r"-on-([a-z]+)-(\d+)(?:-(\d{4}))?$", slug)
    if not match:
        return None

    month = match.group(1)
    day = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else None
    if year is None:
        closed_time = event.get("closedTime") or event.get("startDate") or ""
        year = int(str(closed_time)[:4]) if closed_time else None
    if year is None:
        return None

    for fmt in ("%B", "%b"):
        try:
            month_num = datetime.strptime(month, fmt).month
            return f"{year:04d}-{month_num:02d}-{day:02d}"
        except ValueError:
            continue
    return None


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)

    gamma_files = sorted(GAMMA_CACHE_DIR.glob("closed_weather_offset_*.json"))
    events: list[dict] = []
    for cache_file in gamma_files:
        events.extend(json.loads(cache_file.read_text()))

    filtered = [event for event in events if event.get("seriesSlug") in TRACKED_SERIES and event.get("markets")]
    filtered.sort(key=lambda event: event.get("closedTime") or event.get("endDate") or "", reverse=True)

    rows: list[dict[str, object]] = []
    included_events: set[tuple[str, str]] = set()
    for event in filtered:
        series_slug = event["seriesSlug"]
        city_name, settlement_unit = TRACKED_SERIES[series_slug]
        market_date = infer_market_date(event)
        if not market_date:
            continue
        forecast_max_c, center_bin = read_forecast_center(series_slug, market_date, settlement_unit)
        if center_bin is None:
            continue
        event_key = (city_name, market_date)
        if event_key not in included_events and len(included_events) >= args.max_events:
            break
        included_events.add(event_key)

        for market in event["markets"]:
            resolved_yes = resolved_yes_from_market(market)
            if resolved_yes is None:
                continue
            opening_price, opening_ts = read_opening_price(market["conditionId"])
            if opening_price is None:
                continue
            label = market.get("groupItemTitle") or market.get("title") or ""
            low, high, unit = parse_bucket_bounds(label)
            rows.append(
                {
                    "city": city_name,
                    "series_slug": series_slug,
                    "market_date": market_date,
                    "event_slug": event["slug"],
                    "market_slug": market["slug"],
                    "bucket_label": label,
                    "bucket_low_c": "" if low is None else low,
                    "bucket_high_c": "" if high is None else high,
                    "bucket_unit": unit or settlement_unit,
                    "yes_price": opening_price,
                    "opening_price_ts": opening_ts,
                    "center_bin": center_bin,
                    "forecast_max_c": round(forecast_max_c, 1),
                    "resolved_yes": resolved_yes,
                    "market_opened_at": market.get("startDate", ""),
                    "market_closed_at": market.get("closedTime", ""),
                    "condition_id": market["conditionId"],
                    "token_id": parse_yes_token_id(market["clobTokenIds"]),
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

    print(f"Saved {len(rows)} rows to {output_path}")
    print(f"Cities={len({row['city'] for row in rows})} Events={len({(row['city'], row['market_date']) for row in rows})}")


if __name__ == "__main__":
    main()
