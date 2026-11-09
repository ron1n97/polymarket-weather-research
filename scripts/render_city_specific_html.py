#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render city-specific model results as HTML.")
    parser.add_argument(
        "--summary",
        default="outputs/city_specific_eval/city_specific_summary.csv",
        help="Path to city-specific summary CSV",
    )
    parser.add_argument(
        "--output",
        default="outputs/city_specific_eval/city_specific_models.html",
        help="HTML output path",
    )
    return parser.parse_args()


def fmt_pct(v: float | None) -> str:
    if pd.isna(v):
        return "n/a"
    return f"{v * 100:.1f}%"


def fmt_hour(v: float | None) -> str:
    if pd.isna(v):
        return "not reached"
    h = int(v)
    m = int(round((v - h) * 60))
    return f"{h:02d}:{m:02d}"


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.summary)
    df["hour_gap_vs_baseline"] = df["model_mean_first_hour_99"] - df["baseline_mean_first_hour_99"]
    df = df.sort_values("model_mean_first_hour_99", na_position="last")

    rows = "\n".join(
        f"""
<tr>
  <td>{html.escape(row['city'])}</td>
  <td>{int(row['sample_days'])}</td>
  <td>{int(row['model_days_with_99'])}</td>
  <td>{int(row['baseline_days_with_99'])}</td>
  <td>{fmt_hour(row['model_mean_first_hour_99'])}</td>
  <td>{fmt_hour(row['baseline_mean_first_hour_99'])}</td>
  <td>{'n/a' if pd.isna(row['hour_gap_vs_baseline']) else f"{row['hour_gap_vs_baseline']:+.2f}h"}</td>
  <td>{fmt_pct(row['model_cutoff_99_hit_rate'])}</td>
  <td>{fmt_pct(row['baseline_cutoff_99_hit_rate'])}</td>
</tr>
""".strip()
        for _, row in df.iterrows()
    )

    best = df.head(5)
    best_list = "\n".join(
        f"<li><strong>{html.escape(row['city'])}</strong>: first 99% at {fmt_hour(row['model_mean_first_hour_99'])}, baseline {fmt_hour(row['baseline_mean_first_hour_99'])}</li>"
        for _, row in best.iterrows()
    )

    output = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>City-Specific Models</title>
  <style>
    body {{
      margin: 0;
      background: linear-gradient(180deg, #e8efe7 0%, #f5f0e8 32%, #f3e4d4 100%);
      color: #1e232b;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
    }}
    main {{
      width: min(1260px, calc(100% - 28px));
      margin: 0 auto;
      padding: 28px 0 56px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(2rem, 4vw, 3.5rem);
      letter-spacing: -0.04em;
      line-height: 0.95;
    }}
    p {{
      color: #626973;
      max-width: 900px;
    }}
    .card {{
      background: rgba(255,255,255,0.82);
      border: 1px solid rgba(30,35,43,0.12);
      border-radius: 18px;
      padding: 18px 20px;
      box-shadow: 0 12px 28px rgba(30,35,43,0.08);
      margin-top: 20px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.94rem;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid rgba(30,35,43,0.1);
    }}
    th {{
      color: #626973;
      font-size: 0.79rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
  </style>
</head>
<body>
  <main>
    <h1>City-Specific Models</h1>
    <p>
      Separate boosted model per city. This is the cleanest check of whether pooled modeling was the bottleneck
      for reaching the 99% confidence threshold earlier.
    </p>
    <section class="card">
      <h2>Best City-Specific Results</h2>
      <ul>
        {best_list}
      </ul>
    </section>
    <section class="card">
      <h2>City Breakdown</h2>
      <table>
        <thead>
          <tr>
            <th>City</th>
            <th>Days</th>
            <th>Model Days ≥99%</th>
            <th>Baseline Days ≥99%</th>
            <th>Model First 99%</th>
            <th>Baseline First 99%</th>
            <th>Hour Gap</th>
            <th>Model Cutoff Hit</th>
            <th>Baseline Cutoff Hit</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(output, encoding="utf-8")
    print(f"Saved HTML report to {out}")


if __name__ == "__main__":
    main()
