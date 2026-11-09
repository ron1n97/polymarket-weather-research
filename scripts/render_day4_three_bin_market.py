#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render day+4 three-bin market report.")
    parser.add_argument(
        "--predictions",
        default="outputs/day4_forecast_eval/day4_forecast_predictions.csv",
        help="Predictions CSV path. Default: outputs/day4_forecast_eval/day4_forecast_predictions.csv",
    )
    parser.add_argument(
        "--summary-output",
        default="outputs/day4_forecast_eval/day4_three_bin_summary.csv",
        help="Summary CSV path. Default: outputs/day4_forecast_eval/day4_three_bin_summary.csv",
    )
    parser.add_argument(
        "--bin-output",
        default="outputs/day4_forecast_eval/day4_three_bin_by_center.csv",
        help="Per-center-bin CSV path. Default: outputs/day4_forecast_eval/day4_three_bin_by_center.csv",
    )
    parser.add_argument(
        "--html-output",
        default="outputs/day4_forecast_eval/day4_three_bin_market.html",
        help="HTML report path. Default: outputs/day4_forecast_eval/day4_three_bin_market.html",
    )
    return parser.parse_args()


def fair_yes_price(prob: float) -> float:
    return prob


def fair_decimal_odds(prob: float) -> float | None:
    if prob <= 0:
        return None
    return 1.0 / prob


def fmt_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value * 100:.1f}%"


def fmt_odds(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:.2f}x"


def build_city_summary(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.groupby(["city", "timezone"], as_index=False)
        .agg(
            sample_days=("local_day", "size"),
            exact_bin_prob=("hit_rounded_c", "mean"),
            three_bin_prob=("hit_within_1c", "mean"),
            five_bin_prob=("hit_within_2c", "mean"),
            mae_c=("abs_error_c", "mean"),
            mean_center_bin=("predicted_daily_max_rounded_c", "mean"),
        )
        .sort_values("three_bin_prob", ascending=False)
        .reset_index(drop=True)
    )
    summary["fair_yes_price_exact"] = summary["exact_bin_prob"].apply(fair_yes_price)
    summary["fair_yes_price_three_bin"] = summary["three_bin_prob"].apply(fair_yes_price)
    summary["fair_yes_price_five_bin"] = summary["five_bin_prob"].apply(fair_yes_price)
    summary["fair_decimal_odds_exact"] = summary["exact_bin_prob"].apply(fair_decimal_odds)
    summary["fair_decimal_odds_three_bin"] = summary["three_bin_prob"].apply(fair_decimal_odds)
    summary["fair_decimal_odds_five_bin"] = summary["five_bin_prob"].apply(fair_decimal_odds)
    return summary


def build_center_bin_summary(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby(["city", "predicted_daily_max_rounded_c"], as_index=False)
        .agg(
            sample_days=("local_day", "size"),
            exact_bin_prob=("hit_rounded_c", "mean"),
            three_bin_prob=("hit_within_1c", "mean"),
            five_bin_prob=("hit_within_2c", "mean"),
            mean_actual_bin=("actual_final_max_rounded_c", "mean"),
        )
        .rename(columns={"predicted_daily_max_rounded_c": "center_bin_c"})
    )
    grouped["fair_yes_price_three_bin"] = grouped["three_bin_prob"].apply(fair_yes_price)
    grouped["fair_decimal_odds_three_bin"] = grouped["three_bin_prob"].apply(fair_decimal_odds)
    return grouped.sort_values(["city", "center_bin_c"]).reset_index(drop=True)


def render_html(city_summary: pd.DataFrame, bin_summary: pd.DataFrame, output_path: Path) -> None:
    global_three_bin = city_summary["sample_days"].mul(city_summary["three_bin_prob"]).sum() / city_summary["sample_days"].sum()
    global_exact = city_summary["sample_days"].mul(city_summary["exact_bin_prob"]).sum() / city_summary["sample_days"].sum()
    global_five_bin = city_summary["sample_days"].mul(city_summary["five_bin_prob"]).sum() / city_summary["sample_days"].sum()

    top = city_summary.head(6)
    top_rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(row.city)}</td>"
            f"<td>{int(row.sample_days)}</td>"
            f"<td>{fmt_pct(row.exact_bin_prob)}</td>"
            f"<td>{fmt_pct(row.three_bin_prob)}</td>"
            f"<td>{fmt_odds(row.fair_decimal_odds_three_bin)}</td>"
            f"<td>{fmt_pct(row.five_bin_prob)}</td>"
            f"<td>{row.mae_c:.2f}</td>"
            "</tr>"
        )
        for row in top.itertuples(index=False)
    )

    all_rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(row.city)}</td>"
            f"<td>{html.escape(row.timezone)}</td>"
            f"<td>{int(row.sample_days)}</td>"
            f"<td>{fmt_pct(row.exact_bin_prob)}</td>"
            f"<td>{fmt_pct(row.three_bin_prob)}</td>"
            f"<td>{fmt_odds(row.fair_decimal_odds_three_bin)}</td>"
            f"<td>{fmt_pct(row.five_bin_prob)}</td>"
            f"<td>{row.mean_center_bin:.1f}°C</td>"
            f"<td>{row.mae_c:.2f}</td>"
            "</tr>"
        )
        for row in city_summary.itertuples(index=False)
    )

    best_bins = (
        bin_summary[bin_summary["sample_days"] >= 15]
        .sort_values(["three_bin_prob", "sample_days"], ascending=[False, False])
        .head(14)
    )
    bin_rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(row.city)}</td>"
            f"<td>{int(row.center_bin_c)}°C</td>"
            f"<td>{int(row.sample_days)}</td>"
            f"<td>{fmt_pct(row.exact_bin_prob)}</td>"
            f"<td>{fmt_pct(row.three_bin_prob)}</td>"
            f"<td>{fmt_odds(row.fair_decimal_odds_three_bin)}</td>"
            f"<td>{fmt_pct(row.five_bin_prob)}</td>"
            f"<td>{row.mean_actual_bin:.1f}°C</td>"
            "</tr>"
        )
        for row in best_bins.itertuples(index=False)
    )

    doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Day+4 Three-Bin Market</title>
  <style>
    :root {{
      --bg: #f3efe7;
      --paper: #fffdf8;
      --ink: #1d232b;
      --muted: #6a7078;
      --line: rgba(29,35,43,0.12);
      --accent: #1f7a4f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #edf4e8 0%, var(--bg) 22%, #f5e8da 100%);
      color: var(--ink);
      font-family: "Iowan Old Style", Georgia, serif;
    }}
    main {{ width: min(1240px, calc(100% - 28px)); margin: 0 auto; padding: 28px 0 56px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(2rem, 4vw, 3.5rem); line-height: 0.95; letter-spacing: -0.04em; }}
    h2 {{ margin: 0 0 12px; }}
    p {{ margin: 0; color: var(--muted); line-height: 1.5; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-top: 22px;
    }}
    .card {{
      background: rgba(255,253,248,0.9);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px 20px;
      box-shadow: 0 12px 28px rgba(29,35,43,0.08);
    }}
    .value {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
    .label {{ color: var(--muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.07em; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.94rem; }}
    th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); }}
    th {{ color: var(--muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; }}
    tr:last-child td {{ border-bottom: none; }}
    .section {{ margin-top: 18px; }}
  </style>
</head>
<body>
  <main>
    <h1>Day+4 Three-Bin Market</h1>
    <p>
      Market logic for a three-bin temperature position: center bin is the rounded day+4 forecast, and the trade wins
      if the resolved max lands in the center bin or one neighbor on either side.
    </p>

    <section class="grid">
      <div class="card"><div class="label">Global Exact Bin</div><div class="value">{fmt_pct(global_exact)}</div><p>single Polymarket-style bin only</p></div>
      <div class="card"><div class="label">Global Three-Bin</div><div class="value">{fmt_pct(global_three_bin)}</div><p>center bin ±1°C</p></div>
      <div class="card"><div class="label">Fair Odds</div><div class="value">{fmt_odds(fair_decimal_odds(global_three_bin))}</div><p>break-even decimal odds for three-bin yes</p></div>
      <div class="card"><div class="label">Global Five-Bin</div><div class="value">{fmt_pct(global_five_bin)}</div><p>center bin ±2°C</p></div>
    </section>

    <section class="card section">
      <h2>Best Cities For 3-Bin Window</h2>
      <table>
        <thead>
          <tr>
            <th>City</th>
            <th>Days</th>
            <th>Exact</th>
            <th>3-Bin</th>
            <th>Fair Odds</th>
            <th>5-Bin</th>
            <th>MAE</th>
          </tr>
        </thead>
        <tbody>{top_rows}</tbody>
      </table>
    </section>

    <section class="card section">
      <h2>All Cities</h2>
      <table>
        <thead>
          <tr>
            <th>City</th>
            <th>Timezone</th>
            <th>Days</th>
            <th>Exact</th>
            <th>3-Bin</th>
            <th>Fair Odds</th>
            <th>5-Bin</th>
            <th>Mean Center Bin</th>
            <th>MAE</th>
          </tr>
        </thead>
        <tbody>{all_rows}</tbody>
      </table>
    </section>

    <section class="card section">
      <h2>Strongest Center Bins</h2>
      <table>
        <thead>
          <tr>
            <th>City</th>
            <th>Center Bin</th>
            <th>Days</th>
            <th>Exact</th>
            <th>3-Bin</th>
            <th>Fair Odds</th>
            <th>5-Bin</th>
            <th>Mean Actual</th>
          </tr>
        </thead>
        <tbody>{bin_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
    output_path.write_text(doc, encoding="utf-8")


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.predictions)
    city_summary = build_city_summary(df)
    bin_summary = build_center_bin_summary(df)

    Path(args.summary_output).parent.mkdir(parents=True, exist_ok=True)
    city_summary.to_csv(args.summary_output, index=False)
    bin_summary.to_csv(args.bin_output, index=False)
    render_html(city_summary, bin_summary, Path(args.html_output))

    print(city_summary[["city", "exact_bin_prob", "three_bin_prob", "fair_decimal_odds_three_bin"]].to_string(index=False))
    print(f"\nSaved summary: {args.summary_output}")
    print(f"Saved bins: {args.bin_output}")
    print(f"Saved HTML: {args.html_output}")


if __name__ == "__main__":
    main()
