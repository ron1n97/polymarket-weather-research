#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render model-vs-baseline evaluation as HTML.")
    parser.add_argument(
        "--metrics",
        default="outputs/model_eval/metrics.csv",
        help="Path to metrics CSV. Default: outputs/model_eval/metrics.csv",
    )
    parser.add_argument(
        "--summary",
        default="outputs/model_eval/city_summary.csv",
        help="Path to city summary CSV. Default: outputs/model_eval/city_summary.csv",
    )
    parser.add_argument(
        "--output",
        default="outputs/model_eval/model_vs_baseline.html",
        help="HTML output path. Default: outputs/model_eval/model_vs_baseline.html",
    )
    return parser.parse_args()


def fmt_pct(value: float | None) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value * 100:.1f}%"


def fmt_hour(value: float | None) -> str:
    if pd.isna(value):
        return "not reached"
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    return f"{hours:02d}:{minutes:02d}"


def badge_class(delta: float | None) -> str:
    if pd.isna(delta):
        return "bad"
    if delta <= 0:
        return "good"
    if delta <= 2:
        return "warn"
    return "bad"


def main() -> None:
    args = parse_args()
    metrics = pd.read_csv(args.metrics)
    summary = pd.read_csv(args.summary)

    summary["hour_gap_vs_baseline"] = summary["model_mean_first_hour_99"] - summary["baseline_mean_first_hour_99"]
    summary["cutoff_hit_gap"] = summary["model_cutoff_99_hit_rate"] - summary["baseline_cutoff_99_hit_rate"]
    summary = summary.sort_values(["hour_gap_vs_baseline", "city"], ascending=[True, True], na_position="last")

    metrics_rows = "\n".join(
        f"""
<tr>
  <td>{html.escape(str(row['model']))}</td>
  <td>{html.escape(str(row['split']))}</td>
  <td>{int(row['rows'])}</td>
  <td>{row['positive_rate']:.3f}</td>
  <td>{row['roc_auc']:.3f}</td>
  <td>{row['brier_score']:.3f}</td>
</tr>
""".strip()
        for _, row in metrics.iterrows()
    )

    city_rows = "\n".join(
        f"""
<tr>
  <td>{html.escape(row['city'])}</td>
  <td>{int(row['sample_days'])}</td>
  <td>{int(row['model_days_with_99'])}</td>
  <td>{int(row['baseline_days_with_99'])}</td>
  <td>{fmt_hour(row['model_mean_first_hour_99'])}</td>
  <td>{fmt_hour(row['baseline_mean_first_hour_99'])}</td>
  <td><span class="pill {badge_class(row['hour_gap_vs_baseline'])}">{'n/a' if pd.isna(row['hour_gap_vs_baseline']) else f"{row['hour_gap_vs_baseline']:+.2f}h"}</span></td>
  <td>{fmt_pct(row['model_cutoff_99_hit_rate'])}</td>
  <td>{fmt_pct(row['baseline_cutoff_99_hit_rate'])}</td>
  <td><span class="pill {badge_class(-row['cutoff_hit_gap'])}">{row['cutoff_hit_gap'] * 100:+.1f}pp</span></td>
</tr>
""".strip()
        for _, row in summary.iterrows()
    )

    top_model = summary.sort_values("model_cutoff_99_hit_rate", ascending=False).head(5)
    top_rows = "\n".join(
        f"<li><strong>{html.escape(row['city'])}</strong>: model cutoff hit {fmt_pct(row['model_cutoff_99_hit_rate'])}, first 99% at {fmt_hour(row['model_mean_first_hour_99'])}</li>"
        for _, row in top_model.iterrows()
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Model vs Baseline</title>
  <style>
    :root {{
      --bg: #f3efe7;
      --paper: #fffdf8;
      --ink: #1d232b;
      --muted: #6a7078;
      --line: rgba(29, 35, 43, 0.12);
      --good: #1f7a4f;
      --warn: #a36a00;
      --bad: #b03a2e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #e7efe5 0%, var(--bg) 25%, #f3e6d7 100%);
      color: var(--ink);
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
    }}
    main {{
      width: min(1280px, calc(100% - 28px));
      margin: 0 auto;
      padding: 28px 0 56px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(2rem, 4vw, 3.6rem);
      line-height: 0.95;
      letter-spacing: -0.04em;
    }}
    .lede {{
      max-width: 940px;
      margin: 0;
      color: var(--muted);
      font-size: 1.02rem;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.1fr 1.4fr;
      gap: 18px;
      margin-top: 24px;
    }}
    .card {{
      background: rgba(255, 253, 248, 0.88);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px 20px;
      box-shadow: 0 12px 32px rgba(29, 35, 43, 0.08);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.94rem;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 0.79rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    ul {{
      margin: 0;
      padding-left: 20px;
    }}
    li {{
      margin: 0 0 10px;
    }}
    .pill {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 999px;
      font: 600 12px ui-monospace, monospace;
      color: white;
    }}
    .good {{ background: var(--good); }}
    .warn {{ background: var(--warn); }}
    .bad {{ background: var(--bad); }}
    .full {{
      margin-top: 18px;
    }}
    .note {{
      margin-top: 14px;
      color: var(--muted);
      font-size: 0.94rem;
      line-height: 1.5;
    }}
    @media (max-width: 960px) {{
      .grid {{ grid-template-columns: 1fr; }}
      main {{ width: min(100% - 18px, 1280px); }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Model vs Baseline</h1>
      <p class="lede">
        Comparison of the current boosted model against the simple current-max baseline on the KPI that matters:
        how early each city reaches a calibrated 99% confidence threshold.
      </p>
    </header>

    <section class="grid">
      <article class="card">
        <h2>Global Metrics</h2>
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Split</th>
              <th>Rows</th>
              <th>Positive Rate</th>
              <th>ROC-AUC</th>
              <th>Brier</th>
            </tr>
          </thead>
          <tbody>
            {metrics_rows}
          </tbody>
        </table>
      </article>

      <article class="card">
        <h2>Best Model Cities</h2>
        <ul>
          {top_rows}
        </ul>
        <p class="note">
          Even after adding expanded forecast features, the model still lags the baseline on the earliest-99% KPI
          across the strongest UTC+8/+9 cities.
        </p>
      </article>
    </section>

    <section class="card full">
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
            <th>Cutoff Gap</th>
          </tr>
        </thead>
        <tbody>
          {city_rows}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_doc, encoding="utf-8")
    print(f"Saved HTML report to {output_path}")


if __name__ == "__main__":
    main()
