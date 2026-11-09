#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


NUMERIC_COLUMNS = [
    "predicted_daily_max_c",
    "predicted_daily_max_rounded_c",
    "month",
    "day_of_year",
    "city_bias_train",
    "city_month_bias_train",
]
CATEGORICAL_COLUMNS = ["city", "timezone"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a day+4 forecast correction model for rounded daily max.")
    parser.add_argument(
        "--input",
        default="outputs/day4_forecast_eval/day4_forecast_predictions.csv",
        help="Input day+4 predictions CSV. Default: outputs/day4_forecast_eval/day4_forecast_predictions.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/day4_correction_eval",
        help="Output directory. Default: outputs/day4_correction_eval",
    )
    parser.add_argument(
        "--train-until-year",
        type=int,
        default=2024,
        help="Train rows with local_day year <= this value. Default: 2024",
    )
    return parser.parse_args()


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), NUMERIC_COLUMNS),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_COLUMNS),
        ]
    )
    model = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_depth=5,
        max_iter=300,
        min_samples_leaf=20,
        random_state=42,
    )
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def add_features(df: pd.DataFrame, train_until_year: int) -> pd.DataFrame:
    enriched = df.copy()
    enriched["local_day"] = pd.to_datetime(enriched["local_day"])
    enriched["year"] = enriched["local_day"].dt.year
    enriched["month"] = enriched["local_day"].dt.month
    enriched["day_of_year"] = enriched["local_day"].dt.dayofyear
    enriched["raw_residual_rounded"] = (
        enriched["actual_final_max_rounded_c"] - enriched["predicted_daily_max_rounded_c"]
    )

    train_df = enriched[enriched["year"] <= train_until_year].copy()
    city_bias = train_df.groupby("city")["raw_residual_rounded"].mean().rename("city_bias_train")
    city_month_bias = (
        train_df.groupby(["city", "month"])["raw_residual_rounded"]
        .mean()
        .rename("city_month_bias_train")
    )

    enriched = enriched.merge(city_bias, on="city", how="left")
    enriched = enriched.merge(city_month_bias, on=["city", "month"], how="left")
    return enriched


def evaluate_split(df: pd.DataFrame, mask: pd.Series, label: str) -> dict:
    part = df.loc[mask].copy()
    return {
        "split": label,
        "rows": len(part),
        "raw_hit_rate": part["hit_rounded_c"].mean(),
        "model_hit_rate": part["model_hit_rounded_c"].mean(),
        "raw_within_1c": part["raw_within_1c"].mean(),
        "model_within_1c": part["model_within_1c"].mean(),
        "raw_mae_c": mean_absolute_error(part["actual_final_max_rounded_c"], part["predicted_daily_max_rounded_c"]),
        "model_mae_c": mean_absolute_error(part["actual_final_max_rounded_c"], part["model_predicted_rounded_c"]),
    }


def render_html(metrics: pd.DataFrame, summary: pd.DataFrame, output_path: Path) -> None:
    metric_rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(str(row['split']))}</td>"
            f"<td>{int(row['rows'])}</td>"
            f"<td>{row['raw_hit_rate'] * 100:.1f}%</td>"
            f"<td>{row['model_hit_rate'] * 100:.1f}%</td>"
            f"<td>{(row['model_hit_rate'] - row['raw_hit_rate']) * 100:+.1f}pp</td>"
            f"<td>{row['raw_mae_c']:.2f}</td>"
            f"<td>{row['model_mae_c']:.2f}</td>"
            "</tr>"
        )
        for _, row in metrics.iterrows()
    )

    city_rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(row['city'])}</td>"
            f"<td>{int(row['sample_days'])}</td>"
            f"<td>{row['raw_hit_rate'] * 100:.1f}%</td>"
            f"<td>{row['model_hit_rate'] * 100:.1f}%</td>"
            f"<td>{(row['model_hit_rate'] - row['raw_hit_rate']) * 100:+.1f}pp</td>"
            f"<td>{row['raw_within_1c'] * 100:.1f}%</td>"
            f"<td>{row['model_within_1c'] * 100:.1f}%</td>"
            f"<td>{row['raw_mae_c']:.2f}</td>"
            f"<td>{row['model_mae_c']:.2f}</td>"
            "</tr>"
        )
        for _, row in summary.iterrows()
    )

    top = summary.head(6)
    top_rows = "\n".join(
        f"<li><strong>{html.escape(row['city'])}</strong>: raw {row['raw_hit_rate'] * 100:.1f}% -> model {row['model_hit_rate'] * 100:.1f}% ({(row['model_hit_rate'] - row['raw_hit_rate']) * 100:+.1f}pp)</li>"
        for _, row in top.iterrows()
    )

    doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Day+4 Correction Model</title>
  <style>
    :root {{
      --bg: #f3efe6;
      --paper: #fffdf8;
      --ink: #1e1d1a;
      --muted: #6c675f;
      --line: rgba(30,29,26,0.12);
      --good: #146c43;
      --bad: #a83a2a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #eef4e6 0%, var(--bg) 22%, #f5e8da 100%);
      color: var(--ink);
      font-family: Georgia, "Iowan Old Style", serif;
    }}
    main {{ width: min(1180px, calc(100% - 28px)); margin: 0 auto; padding: 28px 0 56px; }}
    .card {{
      background: rgba(255,253,248,0.9);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px 20px;
      box-shadow: 0 12px 28px rgba(30,29,26,0.08);
      margin-top: 18px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.95rem; }}
    th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); }}
    th {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); }}
    tr:last-child td {{ border-bottom: none; }}
    .delta-good {{ color: var(--good); font-weight: 700; }}
    .delta-bad {{ color: var(--bad); font-weight: 700; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(2rem, 4vw, 3.4rem); line-height: 0.95; }}
    p {{ margin: 0; color: var(--muted); line-height: 1.5; }}
    ul {{ margin: 10px 0 0; padding-left: 20px; }}
    li {{ margin: 0 0 8px; }}
  </style>
</head>
<body>
  <main>
    <h1>Day+4 Correction Model</h1>
    <p>
      Raw forecast is Open-Meteo Previous Runs. Model predicts an integer correction on top of the rounded day+4
      forecast using city, season, and train-set bias features.
    </p>

    <section class="card">
      <h2>Global Metrics</h2>
      <table>
        <thead>
          <tr>
            <th>Split</th>
            <th>Rows</th>
            <th>Raw Hit</th>
            <th>Model Hit</th>
            <th>Delta</th>
            <th>Raw MAE</th>
            <th>Model MAE</th>
          </tr>
        </thead>
        <tbody>{metric_rows}</tbody>
      </table>
    </section>

    <section class="card">
      <h2>Best Lift</h2>
      <ul>{top_rows}</ul>
    </section>

    <section class="card">
      <h2>City Breakdown</h2>
      <table>
        <thead>
          <tr>
            <th>City</th>
            <th>Days</th>
            <th>Raw Hit</th>
            <th>Model Hit</th>
            <th>Delta</th>
            <th>Raw ±1C</th>
            <th>Model ±1C</th>
            <th>Raw MAE</th>
            <th>Model MAE</th>
          </tr>
        </thead>
        <tbody>{city_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
    output_path.write_text(doc, encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input)
    df = add_features(df, args.train_until_year)

    train_mask = df["year"] <= args.train_until_year
    test_mask = df["year"] > args.train_until_year

    pipeline = build_pipeline()
    pipeline.fit(df.loc[train_mask], df.loc[train_mask, "raw_residual_rounded"])

    df["predicted_residual_cont"] = pipeline.predict(df)
    df["predicted_residual_rounded"] = df["predicted_residual_cont"].round().clip(-3, 3).astype(int)
    df["model_predicted_rounded_c"] = df["predicted_daily_max_rounded_c"] + df["predicted_residual_rounded"]
    df["model_hit_rounded_c"] = (
        df["model_predicted_rounded_c"] == df["actual_final_max_rounded_c"]
    ).astype(int)
    df["raw_within_1c"] = (
        (df["predicted_daily_max_rounded_c"] - df["actual_final_max_rounded_c"]).abs() <= 1
    ).astype(int)
    df["model_within_1c"] = (
        (df["model_predicted_rounded_c"] - df["actual_final_max_rounded_c"]).abs() <= 1
    ).astype(int)

    metrics = pd.DataFrame(
        [
            evaluate_split(df, train_mask, "train"),
            evaluate_split(df, test_mask, "test"),
        ]
    )

    summary = (
        df.loc[test_mask]
        .groupby("city", as_index=False)
        .agg(
            sample_days=("local_day", "size"),
            raw_hit_rate=("hit_rounded_c", "mean"),
            model_hit_rate=("model_hit_rounded_c", "mean"),
            raw_within_1c=("raw_within_1c", "mean"),
            model_within_1c=("model_within_1c", "mean"),
            raw_mae_c=("predicted_daily_max_rounded_c", lambda s: np.mean(np.abs(s - df.loc[s.index, "actual_final_max_rounded_c"]))),
            model_mae_c=("model_predicted_rounded_c", lambda s: np.mean(np.abs(s - df.loc[s.index, "actual_final_max_rounded_c"]))),
        )
        .sort_values("model_hit_rate", ascending=False)
        .reset_index(drop=True)
    )
    summary["hit_rate_lift_pp"] = (summary["model_hit_rate"] - summary["raw_hit_rate"]) * 100

    predictions_path = output_dir / "day4_correction_predictions.csv"
    metrics_path = output_dir / "day4_correction_metrics.csv"
    summary_path = output_dir / "day4_correction_summary.csv"
    html_path = output_dir / "day4_correction_report.html"

    df.to_csv(predictions_path, index=False)
    metrics.to_csv(metrics_path, index=False)
    summary.to_csv(summary_path, index=False)
    render_html(metrics, summary, html_path)

    print(metrics.to_string(index=False))
    print()
    print(summary[["city", "sample_days", "raw_hit_rate", "model_hit_rate", "hit_rate_lift_pp"]].to_string(index=False))
    print(f"\nSaved outputs to {output_dir}")


if __name__ == "__main__":
    main()
