#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate current market edge from fair probabilities and current Polymarket prices.")
    parser.add_argument(
        "--markets",
        default="outputs/polymarket/current_weather_markets.csv",
        help="Current weather markets CSV. Default: outputs/polymarket/current_weather_markets.csv",
    )
    parser.add_argument(
        "--forecast",
        default="outputs/forecast/current_forecast_snapshot.csv",
        help="Current forecast snapshot CSV. Default: outputs/forecast/current_forecast_snapshot.csv",
    )
    parser.add_argument(
        "--fair",
        default="outputs/fair_value/day4_exact_bin_fair.csv",
        help="Exact-bin fair table CSV. Default: outputs/fair_value/day4_exact_bin_fair.csv",
    )
    parser.add_argument(
        "--output",
        default="outputs/edges/current_edge_table.csv",
        help="Output CSV. Default: outputs/edges/current_edge_table.csv",
    )
    parser.add_argument(
        "--html-output",
        default="outputs/edges/current_edge_table.html",
        help="Output HTML. Default: outputs/edges/current_edge_table.html",
    )
    return parser.parse_args()


def bucket_probability(city_fair: pd.DataFrame, low: float | None, high: float | None) -> float:
    mask = pd.Series(True, index=city_fair.index)
    if low == low:
        mask &= city_fair["actual_bin"] >= int(low)
    if high == high:
        mask &= city_fair["actual_bin"] <= int(high)
    return city_fair.loc[mask, "probability"].sum()


def classify(edge_pp: float, center_sample_days: float, threshold_pp: float = 8.0, min_samples: int = 40) -> str:
    if pd.isna(center_sample_days) or center_sample_days < min_samples:
        return "no trade: thin sample"
    if edge_pp >= threshold_pp:
        return "bet yes"
    if edge_pp <= -threshold_pp:
        return "bet no"
    return "no trade: no edge"


def render_html(df: pd.DataFrame, output_path: Path) -> None:
    top = df.sort_values("edge_pp", ascending=False).head(20)
    rows = "\n".join(
        (
            "<tr>"
            f"<td>{row.city}</td>"
            f"<td>{row.bucket_label}</td>"
            f"<td>{row.yes_price * 100:.1f}%</td>"
            f"<td>{row.fair_probability * 100:.1f}%</td>"
            f"<td>{row.edge_pp:+.1f}pp</td>"
            f"<td>{int(row.center_sample_days) if pd.notna(row.center_sample_days) else 'n/a'}</td>"
            f"<td>{row.decision}</td>"
            "</tr>"
        )
        for row in top.itertuples(index=False)
    )
    output_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Current Edge Table</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 24px; background: #f5f1e8; color: #1e1d1a; }}
    table {{ border-collapse: collapse; width: 100%; background: #fffdf8; }}
    th, td {{ border-bottom: 1px solid #ddd2c4; padding: 10px 8px; text-align: left; }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #6b665d; }}
  </style>
</head>
<body>
  <h1>Current Edge Table</h1>
  <p>Top positive edges from fair bucket probability vs current market price.</p>
  <table>
    <thead>
      <tr>
        <th>City</th>
        <th>Bucket</th>
        <th>Market</th>
        <th>Fair</th>
        <th>Edge</th>
        <th>Samples</th>
        <th>Decision</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>""",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    markets = pd.read_csv(args.markets)
    forecast = pd.read_csv(args.forecast)
    fair = pd.read_csv(args.fair)

    markets["bucket_low_c"] = pd.to_numeric(markets["bucket_low_c"], errors="coerce")
    markets["bucket_high_c"] = pd.to_numeric(markets["bucket_high_c"], errors="coerce")
    markets["bucket_unit"] = markets["bucket_unit"].fillna("")
    markets["yes_price"] = pd.to_numeric(markets["yes_price"], errors="coerce")
    forecast["rounded_center_bin_c"] = pd.to_numeric(forecast["rounded_center_bin_c"], errors="coerce")
    forecast["forecast_max_c"] = pd.to_numeric(forecast["forecast_max_c"], errors="coerce")
    forecast["forecast_center_bin_f"] = ((forecast["forecast_max_c"] * 9 / 5) + 32).round()

    joined = markets.merge(
        forecast[["city", "forecast_date", "rounded_center_bin_c", "forecast_center_bin_f", "forecast_max_c"]],
        left_on=["city", "market_date"],
        right_on=["city", "forecast_date"],
        how="left",
    )

    rows = []
    for row in joined.itertuples(index=False):
        settlement_unit = row.bucket_unit if row.bucket_unit in {"C", "F"} else "C"
        center_bin = row.forecast_center_bin_f if settlement_unit == "F" else row.rounded_center_bin_c
        city_fair = fair[
            (fair["city"] == row.city)
            & (fair["settlement_unit"] == settlement_unit)
            & (fair["forecast_center_bin"] == center_bin)
        ]
        if city_fair.empty:
            fair_probability = None
            center_sample_days = None
        else:
            fair_probability = bucket_probability(city_fair, row.bucket_low_c, row.bucket_high_c)
            center_sample_days = float(city_fair["center_sample_days"].iloc[0])
        edge_pp = None if fair_probability is None or pd.isna(row.yes_price) else (fair_probability - row.yes_price) * 100
        rows.append(
            {
                "city": row.city,
                "market_date": row.market_date,
                "bucket_label": row.bucket_label,
                "yes_price": row.yes_price,
                "fair_probability": fair_probability,
                "edge_pp": edge_pp,
                "center_sample_days": center_sample_days,
                "rounded_center_bin_c": center_bin,
                "forecast_max_c": row.forecast_max_c,
                "settlement_unit": settlement_unit,
                "decision": classify(edge_pp, center_sample_days) if edge_pp is not None else "no trade: no fair value",
            }
        )

    result = pd.DataFrame(rows).sort_values("edge_pp", ascending=False, na_position="last")
    output_path = Path(args.output)
    html_output_path = Path(args.html_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    render_html(result[result["fair_probability"].notna()].copy(), html_output_path)
    print(f"Saved edge table to {output_path}")
    print(f"Saved HTML edge table to {html_output_path}")
    print(result.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
