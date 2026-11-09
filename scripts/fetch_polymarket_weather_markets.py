#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class CityMarket:
    city: str
    slug_city: str


CITIES: tuple[CityMarket, ...] = (
    CityMarket("Tokyo", "tokyo"),
    CityMarket("Seoul", "seoul"),
    CityMarket("Singapore", "singapore"),
    CityMarket("Shanghai", "shanghai"),
    CityMarket("Beijing", "beijing"),
    CityMarket("Shenzhen", "shenzhen"),
    CityMarket("Chongqing", "chongqing"),
    CityMarket("Wuhan", "wuhan"),
    CityMarket("Chengdu", "chengdu"),
    CityMarket("Hong Kong", "hong-kong"),
    CityMarket("Taipei", "taipei"),
    CityMarket("Kuala Lumpur", "kuala-lumpur"),
    CityMarket("Paris", "paris"),
    CityMarket("London", "london"),
    CityMarket("Dallas", "dallas"),
    CityMarket("New York City", "nyc"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch current Polymarket weather market buckets and prices.")
    parser.add_argument(
        "--market-date",
        default=date.today().strftime("%Y-%m-%d"),
        help="Target market date in YYYY-MM-DD. Default: today",
    )
    parser.add_argument(
        "--output",
        default="outputs/polymarket/current_weather_markets.csv",
        help="Output CSV path. Default: outputs/polymarket/current_weather_markets.csv",
    )
    return parser.parse_args()


def slug_date(market_date: str) -> str:
    dt = datetime.strptime(market_date, "%Y-%m-%d").date()
    return f"{dt.strftime('%B').lower()}-{dt.day}-{dt.year}"


def fetch_html(url: str) -> str:
    result = subprocess.run(
        ["curl", "-L", url],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def parse_event_payload(html_doc: str) -> tuple[dict, str]:
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', html_doc)
    if not match:
        raise ValueError("Could not find __NEXT_DATA__ in Polymarket page.")
    payload = json.loads(match.group(1))
    event_slug = payload["query"]["slug"][0]
    queries = payload["props"]["pageProps"]["dehydratedState"]["queries"]
    for query in queries:
        candidate = query["state"].get("data")
        if isinstance(candidate, dict) and candidate.get("slug") == event_slug:
            return candidate, event_slug
    raise ValueError(f"Could not find event payload for {event_slug}.")


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


def main() -> None:
    args = parse_args()
    market_date_slug = slug_date(args.market_date)
    rows: list[dict[str, str | float | int]] = []

    for city in CITIES:
        url = f"https://polymarket.com/event/highest-temperature-in-{city.slug_city}-on-{market_date_slug}"
        try:
            event, event_slug = parse_event_payload(fetch_html(url))
        except Exception as exc:
            rows.append(
                {
                    "city": city.city,
                    "market_date": args.market_date,
                    "event_slug": "",
                    "event_url": url,
                    "bucket_label": "",
                    "bucket_low_c": "",
                    "bucket_high_c": "",
                    "yes_price": "",
                    "no_price": "",
                    "volume_usd": "",
                    "market_opened_at": "",
                    "resolution_source": "",
                    "status": f"error: {exc}",
                }
            )
            continue

        resolution_source = event.get("resolutionSource", "")
        for market in event.get("markets", []):
            label = market.get("groupItemTitle") or market.get("title") or market.get("slug", "")
            outcome_prices = market.get("outcomePrices") or []
            yes_price = float(outcome_prices[0]) if len(outcome_prices) >= 1 else None
            no_price = float(outcome_prices[1]) if len(outcome_prices) >= 2 else None
            low_c, high_c, bucket_unit = parse_bucket_bounds(label)
            rows.append(
                {
                    "city": city.city,
                    "market_date": args.market_date,
                    "event_slug": event_slug,
                    "event_url": url,
                    "bucket_label": label,
                    "bucket_low_c": "" if low_c is None else low_c,
                    "bucket_high_c": "" if high_c is None else high_c,
                    "bucket_unit": "" if bucket_unit is None else bucket_unit,
                    "yes_price": "" if yes_price is None else f"{yes_price:.6f}",
                    "no_price": "" if no_price is None else f"{no_price:.6f}",
                    "volume_usd": market.get("volume", ""),
                    "market_opened_at": market.get("createdAt", ""),
                    "resolution_source": resolution_source,
                    "status": "ok",
                }
            )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "city",
        "market_date",
        "event_slug",
        "event_url",
        "bucket_label",
        "bucket_low_c",
        "bucket_high_c",
        "bucket_unit",
        "yes_price",
        "no_price",
        "volume_usd",
        "market_opened_at",
        "resolution_source",
        "status",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    ok_rows = sum(1 for row in rows if row["status"] == "ok")
    print(f"Saved {len(rows)} rows to {output_path} ({ok_rows} ok)")


if __name__ == "__main__":
    main()
