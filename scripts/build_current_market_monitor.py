#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Join current Polymarket markets with current forecast snapshot.")
    parser.add_argument(
        "--markets",
        default="outputs/polymarket/current_weather_markets.csv",
        help="Current markets CSV. Default: outputs/polymarket/current_weather_markets.csv",
    )
    parser.add_argument(
        "--forecast",
        default="outputs/forecast/current_forecast_snapshot.csv",
        help="Current forecast CSV. Default: outputs/forecast/current_forecast_snapshot.csv",
    )
    parser.add_argument(
        "--output",
        default="outputs/market_monitor/current_market_monitor.csv",
        help="Joined CSV output. Default: outputs/market_monitor/current_market_monitor.csv",
    )
    parser.add_argument(
        "--html-output",
        default="outputs/market_monitor/current_market_monitor.html",
        help="HTML output. Default: outputs/market_monitor/current_market_monitor.html",
    )
    return parser.parse_args()


def classify_bucket(row: pd.Series) -> str:
    center = row.get("rounded_center_bin_c")
    low = row.get("bucket_low_c")
    high = row.get("bucket_high_c")
    if pd.isna(center):
        return "no forecast"
    if pd.notna(low) and pd.notna(high) and low == high == center:
        return "forecast center"
    if pd.notna(low) and pd.notna(high) and low == center - 1 and high == center - 1:
        return "near forecast"
    if pd.notna(low) and pd.notna(high) and low == center + 1 and high == center + 1:
        return "near forecast"
    if pd.isna(low) and pd.notna(high) and high == center - 1:
        return "left tail"
    if pd.notna(low) and pd.isna(high) and low == center + 1:
        return "right tail"
    return "other"


def render_html(df: pd.DataFrame, output_path: Path) -> None:
    focus = df[df["status"].eq("ok")].copy()
    focus = focus[focus["bucket_role"].isin(["forecast center", "near forecast"])]
    focus = focus.sort_values(["city", "bucket_label"])

    rows = "\n".join(
        (
            "<tr>"
            f"<td>{row.city}</td>"
            f"<td>{row.market_date}</td>"
            f"<td>{row.forecast_max_c:.1f}</td>"
            f"<td>{int(row.rounded_center_bin_c)}°C</td>"
            f"<td>{row.bucket_label}</td>"
            f"<td>{float(row.yes_price) * 100:.1f}%</td>"
            f"<td>{row.bucket_role}</td>"
            f"<td>{row.event_url}</td>"
            "</tr>"
        )
        for row in focus.itertuples(index=False)
    )
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Current Market Monitor</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 24px; background: #f5f1e8; color: #1e1d1a; }}
    table {{ border-collapse: collapse; width: 100%; background: #fffdf8; }}
    th, td {{ border-bottom: 1px solid #ddd2c4; padding: 10px 8px; text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #6b665d; }}
  </style>
</head>
<body>
  <h1>Current Market Monitor</h1>
  <p>Forecast center and adjacent bins for the current tracked cities.</p>
  <table>
    <thead>
      <tr>
        <th>City</th>
        <th>Date</th>
        <th>Forecast Max</th>
        <th>Center Bin</th>
        <th>Bucket</th>
        <th>Yes Price</th>
        <th>Role</th>
        <th>Event URL</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""
    output_path.write_text(html_doc, encoding="utf-8")


def main() -> None:
    args = parse_args()
    markets = pd.read_csv(args.markets)
    forecast = pd.read_csv(args.forecast)

    joined = markets.merge(
        forecast,
        left_on=["city", "market_date"],
        right_on=["city", "forecast_date"],
        how="left",
    )
    if "status_x" in joined.columns and "status_y" in joined.columns:
        joined["market_status"] = joined["status_x"]
        joined["forecast_status"] = joined["status_y"]
        joined["status"] = joined["status_x"]
    elif "status" not in joined.columns:
        joined["status"] = "ok"
    joined["bucket_low_c"] = pd.to_numeric(joined["bucket_low_c"], errors="coerce")
    joined["bucket_high_c"] = pd.to_numeric(joined["bucket_high_c"], errors="coerce")
    joined["yes_price"] = pd.to_numeric(joined["yes_price"], errors="coerce")
    joined["forecast_max_c"] = pd.to_numeric(joined["forecast_max_c"], errors="coerce")
    joined["rounded_center_bin_c"] = pd.to_numeric(joined["rounded_center_bin_c"], errors="coerce")
    joined["bucket_role"] = joined.apply(classify_bucket, axis=1)

    output_path = Path(args.output)
    html_output_path = Path(args.html_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joined.to_csv(output_path, index=False)
    render_html(joined, html_output_path)
    print(f"Saved joined monitor to {output_path}")
    print(f"Saved HTML monitor to {html_output_path}")


if __name__ == "__main__":
    main()
