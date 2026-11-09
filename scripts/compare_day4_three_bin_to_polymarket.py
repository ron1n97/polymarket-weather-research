#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd


FORECAST_CITIES = [
    ("Tokyo", "tokyo", 35.5494, 139.7798, "Asia/Tokyo"),
    ("Seoul", "seoul", 37.4602, 126.4407, "Asia/Seoul"),
    ("Singapore", "singapore", 1.3644, 103.9915, "Asia/Singapore"),
    ("Shanghai", "shanghai", 31.1443, 121.8083, "Asia/Shanghai"),
    ("Beijing", "beijing", 40.0799, 116.6031, "Asia/Shanghai"),
    ("Shenzhen", "shenzhen", 22.6393, 113.8107, "Asia/Shanghai"),
    ("Chongqing", "chongqing", 29.7192, 106.6416, "Asia/Shanghai"),
    ("Wuhan", "wuhan", 30.7766, 114.2081, "Asia/Shanghai"),
    ("Chengdu", "chengdu", 30.5785, 103.9471, "Asia/Shanghai"),
    ("Hong Kong", "hong-kong", 22.3080, 113.9185, "Asia/Hong_Kong"),
    ("Taipei", "taipei", 25.0797, 121.2342, "Asia/Taipei"),
    ("Kuala Lumpur", "kuala-lumpur", 2.7456, 101.7072, "Asia/Kuala_Lumpur"),
    ("Paris", "paris", 49.0097, 2.5479, "Europe/Paris"),
    ("London", "london", 51.5053, 0.0553, "Europe/London"),
    ("Dallas", "dallas", 32.8471, -96.8518, "America/Chicago"),
    ("New York City", "nyc", 40.7769, -73.8740, "America/New_York"),
]

MARKET_DATE = "2026-04-08"


@dataclass(frozen=True)
class ForecastCity:
    city: str
    slug_city: str
    latitude: float
    longitude: float
    timezone: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare current Polymarket prices against day+4 three-bin fair value.")
    parser.add_argument(
        "--three-bin-summary",
        default="outputs/day4_forecast_eval/day4_three_bin_summary.csv",
        help="City-level three-bin fair summary CSV.",
    )
    parser.add_argument(
        "--three-bin-by-center",
        default="outputs/day4_forecast_eval/day4_three_bin_by_center.csv",
        help="Center-bin-level three-bin fair summary CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/day4_vs_polymarket",
        help="Output directory. Default: outputs/day4_vs_polymarket",
    )
    parser.add_argument(
        "--min-center-sample",
        type=int,
        default=25,
        help="Minimum historical sample days for center-bin fair value. Default: 25",
    )
    parser.add_argument(
        "--edge-threshold-pp",
        type=float,
        default=5.0,
        help="Minimum edge in percentage points to call it a bet. Default: 5.0",
    )
    return parser.parse_args()


def fetch_forecast(city: ForecastCity) -> tuple[float, int]:
    query = urlencode(
        {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "daily": "temperature_2m_max",
            "timezone": city.timezone,
            "forecast_days": 7,
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{query}"
    with urlopen(url, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    daily = payload["daily"]
    idx = daily["time"].index(MARKET_DATE)
    max_c = float(daily["temperature_2m_max"][idx])
    return max_c, round(max_c)


def fetch_event_html(slug_city: str) -> str:
    url = f"https://polymarket.com/event/highest-temperature-in-{slug_city}-on-april-8-2026"
    result = subprocess.run(
        ["curl", "-L", url],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def parse_event_prices(html_doc: str) -> dict[str, float]:
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', html_doc)
    if not match:
        raise ValueError("Could not find __NEXT_DATA__ on Polymarket page.")
    data = json.loads(match.group(1))
    eslug = data["query"]["slug"][0]
    queries = data["props"]["pageProps"]["dehydratedState"]["queries"]
    event = None
    for query in queries:
        candidate = query["state"].get("data")
        if isinstance(candidate, dict) and candidate.get("slug") == eslug:
            event = candidate
            break
    if event is None:
        raise ValueError(f"Could not locate event payload for {eslug}.")

    prices: dict[str, float] = {}
    for market in event["markets"]:
        label = market.get("groupItemTitle") or market.get("title") or market.get("slug")
        outcome_prices = market.get("outcomePrices")
        if not label or not isinstance(outcome_prices, list) or not outcome_prices:
            continue
        prices[label] = float(outcome_prices[0])
    return prices


def market_three_bin_prob(prices: dict[str, float], center_bin: int) -> float:
    low_label = f"{center_bin - 1}°C"
    center_label = f"{center_bin}°C"
    high_label = f"{center_bin + 1}°C"
    total = 0.0

    for label in [low_label, center_label, high_label]:
        if label in prices:
            total += prices[label]

    low_tail = f"{center_bin - 1}°C or below"
    high_tail = f"{center_bin + 1}°C or higher"
    if low_tail in prices:
        total += prices[low_tail]
    if high_tail in prices:
        total += prices[high_tail]
    return total


def market_exact_prob(prices: dict[str, float], center_bin: int) -> float:
    exact_label = f"{center_bin}°C"
    return prices.get(exact_label, 0.0)


def classify(edge_pp: float, center_sample_days: int, min_center_sample: int, edge_threshold_pp: float) -> str:
    if center_sample_days < min_center_sample:
        return "no bet: thin sample"
    if edge_pp >= edge_threshold_pp:
        return "bet yes"
    if edge_pp <= -edge_threshold_pp:
        return "bet no"
    return "no bet: no edge"


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    city_summary = pd.read_csv(args.three_bin_summary)
    center_summary = pd.read_csv(args.three_bin_by_center)

    rows = []
    for city_name, slug_city, lat, lon, timezone in FORECAST_CITIES:
        city = ForecastCity(city_name, slug_city, lat, lon, timezone)
        try:
            forecast_max_c, center_bin = fetch_forecast(city)
            prices = parse_event_prices(fetch_event_html(city.slug_city))
        except Exception as exc:
            rows.append({"city": city.city, "status": f"missing market data: {exc}"})
            continue

        market_three = market_three_bin_prob(prices, center_bin)
        market_exact = market_exact_prob(prices, center_bin)
        city_row = city_summary[city_summary["city"] == city.city].iloc[0]
        center_rows = center_summary[
            (center_summary["city"] == city.city) & (center_summary["center_bin_c"] == center_bin)
        ]

        if center_rows.empty:
            fair_three = float(city_row["three_bin_prob"])
            fair_exact = float(city_row["exact_bin_prob"])
            center_sample_days = 0
            fair_source = "city average"
        else:
            center_row = center_rows.iloc[0]
            fair_three = float(center_row["three_bin_prob"])
            fair_exact = float(center_row["exact_bin_prob"])
            center_sample_days = int(center_row["sample_days"])
            fair_source = "center bin"

        edge_pp = (fair_three - market_three) * 100
        rows.append(
            {
                "city": city.city,
                "forecast_max_c": forecast_max_c,
                "center_bin_c": center_bin,
                "three_bin_window": f"{center_bin-1}..{center_bin+1}°C",
                "market_exact_prob": market_exact,
                "market_three_bin_prob": market_three,
                "fair_exact_prob": fair_exact,
                "fair_three_bin_prob": fair_three,
                "edge_pp": edge_pp,
                "center_sample_days": center_sample_days,
                "fair_source": fair_source,
                "decision": classify(
                    edge_pp=edge_pp,
                    center_sample_days=center_sample_days,
                    min_center_sample=args.min_center_sample,
                    edge_threshold_pp=args.edge_threshold_pp,
                ),
                "status": "ok",
            }
        )

    result = pd.DataFrame(rows)
    result_ok = result[result["status"] == "ok"].copy()
    result_ok = result_ok.sort_values(["edge_pp", "center_sample_days"], ascending=[False, False])

    csv_path = output_dir / "day4_vs_polymarket.csv"
    html_path = output_dir / "day4_vs_polymarket.html"
    result_ok.to_csv(csv_path, index=False)

    rows_html = "\n".join(
        (
            "<tr>"
            f"<td>{row.city}</td>"
            f"<td>{row.forecast_max_c:.1f}</td>"
            f"<td>{row.center_bin_c}°C</td>"
            f"<td>{row.three_bin_window}</td>"
            f"<td>{row.market_three_bin_prob * 100:.1f}%</td>"
            f"<td>{row.fair_three_bin_prob * 100:.1f}%</td>"
            f"<td>{row.edge_pp:+.1f}pp</td>"
            f"<td>{row.center_sample_days}</td>"
            f"<td>{row.fair_source}</td>"
            f"<td>{row.decision}</td>"
            "</tr>"
        )
        for row in result_ok.itertuples(index=False)
    )

    html_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Day+4 vs Polymarket</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 24px; background: #f5f1e8; color: #1e1d1a; }}
    table {{ border-collapse: collapse; width: 100%; background: #fffdf8; }}
    th, td {{ border-bottom: 1px solid #ddd2c4; padding: 10px 8px; text-align: left; }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #6b665d; }}
  </style>
</head>
<body>
  <h1>Day+4 3-Bin Edge vs Polymarket</h1>
  <p>Current April 8, 2026 markets compared against our fair three-bin probabilities.</p>
  <table>
    <thead>
      <tr>
        <th>City</th>
        <th>Forecast Max</th>
        <th>Center</th>
        <th>3-Bin Window</th>
        <th>Market 3-Bin</th>
        <th>Fair 3-Bin</th>
        <th>Edge</th>
        <th>Samples</th>
        <th>Fair Source</th>
        <th>Decision</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
</body>
</html>""",
        encoding="utf-8",
    )

    print(result_ok.to_string(index=False))
    print(f"\nSaved CSV: {csv_path}")
    print(f"Saved HTML: {html_path}")


if __name__ == "__main__":
    main()
