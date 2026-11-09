#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from build_openmeteo_forecast_features import CITIES, ForecastCity


BASE_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"


@dataclass(frozen=True)
class EvalConfig:
    lead_days: int
    earliest_api_date: str

    @property
    def hourly_field(self) -> str:
        return f"temperature_2m_previous_day{self.lead_days}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Open-Meteo day+4 forecast daily-max win rate by city.")
    parser.add_argument(
        "--baseline-dataset",
        default="outputs/baseline_dataset.csv",
        help="Observed baseline dataset CSV. Default: outputs/baseline_dataset.csv",
    )
    parser.add_argument("--lead-days", type=int, default=4, help="Forecast lead in full days. Default: 4")
    parser.add_argument(
        "--earliest-api-date",
        default="2024-01-01",
        help="Earliest usable Previous Runs date. Default: 2024-01-01",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/open-meteo-previous-runs-cache",
        help="Directory for cached Previous Runs payloads. Default: data/open-meteo-previous-runs-cache",
    )
    parser.add_argument(
        "--predictions-output",
        default="outputs/day4_forecast_eval/day4_forecast_predictions.csv",
        help="Per-day predictions CSV. Default: outputs/day4_forecast_eval/day4_forecast_predictions.csv",
    )
    parser.add_argument(
        "--summary-output",
        default="outputs/day4_forecast_eval/day4_forecast_summary.csv",
        help="Per-city summary CSV. Default: outputs/day4_forecast_eval/day4_forecast_summary.csv",
    )
    parser.add_argument(
        "--metrics-output",
        default="outputs/day4_forecast_eval/day4_forecast_metrics.csv",
        help="Global metrics CSV. Default: outputs/day4_forecast_eval/day4_forecast_metrics.csv",
    )
    parser.add_argument(
        "--html-output",
        default="outputs/day4_forecast_eval/day4_forecast_report.html",
        help="HTML report path. Default: outputs/day4_forecast_eval/day4_forecast_report.html",
    )
    return parser.parse_args()


def build_url(city: ForecastCity, start_date: str, end_date: str, cfg: EvalConfig) -> str:
    query = urlencode(
        {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": cfg.hourly_field,
            "timezone": city.timezone,
        }
    )
    return f"{BASE_URL}?{query}"


def fetch_payload(city: ForecastCity, start_date: str, end_date: str, cfg: EvalConfig, cache_dir: Path) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_name = f"{city.icao}_{start_date}_{end_date}_day{cfg.lead_days}.json"
    cache_path = cache_dir / cache_name
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    with urlopen(build_url(city, start_date, end_date, cfg), timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8"))
    cache_path.write_text(json.dumps(payload))
    return payload


def load_actuals(baseline_dataset_path: Path, cfg: EvalConfig) -> tuple[pd.DataFrame, str, str]:
    df = pd.read_csv(
        baseline_dataset_path,
        usecols=["city", "icao", "timezone", "local_day", "final_max_c", "final_max_rounded_c"],
    ).drop_duplicates(["city", "local_day"])
    df["local_day"] = pd.to_datetime(df["local_day"]).dt.strftime("%Y-%m-%d")
    start_date = max(df["local_day"].min(), cfg.earliest_api_date)
    end_date = df["local_day"].max()
    filtered = df[(df["local_day"] >= start_date) & (df["local_day"] <= end_date)].copy()
    filtered = filtered.rename(
        columns={
            "final_max_c": "actual_final_max_c",
            "final_max_rounded_c": "actual_final_max_rounded_c",
        }
    )
    return filtered, start_date, end_date


def payload_to_daily_predictions(city: ForecastCity, payload: dict, cfg: EvalConfig) -> pd.DataFrame:
    hourly = pd.DataFrame(payload["hourly"])
    hourly["local_day"] = pd.to_datetime(hourly["time"]).dt.strftime("%Y-%m-%d")
    forecast_col = cfg.hourly_field
    daily = (
        hourly.groupby("local_day", as_index=False)[forecast_col]
        .max()
        .rename(columns={forecast_col: "predicted_daily_max_c"})
    )
    daily = daily[daily["predicted_daily_max_c"].notna()].copy()
    daily["predicted_daily_max_rounded_c"] = daily["predicted_daily_max_c"].round().astype(int)
    daily["city"] = city.city
    daily["icao"] = city.icao
    daily["timezone"] = city.timezone
    return daily[
        [
            "city",
            "icao",
            "timezone",
            "local_day",
            "predicted_daily_max_c",
            "predicted_daily_max_rounded_c",
        ]
    ]


def build_predictions(actuals: pd.DataFrame, start_date: str, end_date: str, cfg: EvalConfig, cache_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for city in CITIES:
        payload = fetch_payload(city, start_date, end_date, cfg, cache_dir)
        frames.append(payload_to_daily_predictions(city, payload, cfg))

    predicted = pd.concat(frames, ignore_index=True)
    merged = actuals.merge(predicted, on=["city", "icao", "timezone", "local_day"], how="inner")
    merged["abs_error_c"] = (merged["predicted_daily_max_c"] - merged["actual_final_max_c"]).abs()
    merged["signed_error_c"] = merged["predicted_daily_max_c"] - merged["actual_final_max_c"]
    merged["hit_exact_tenth"] = (
        merged["predicted_daily_max_c"].round(1) == merged["actual_final_max_c"].round(1)
    ).astype(int)
    merged["hit_rounded_c"] = (
        merged["predicted_daily_max_rounded_c"] == merged["actual_final_max_rounded_c"]
    ).astype(int)
    rounded_abs_error = (merged["predicted_daily_max_rounded_c"] - merged["actual_final_max_rounded_c"]).abs()
    merged["hit_within_1c"] = (rounded_abs_error <= 1).astype(int)
    merged["hit_within_2c"] = (rounded_abs_error <= 2).astype(int)
    return merged.sort_values(["city", "local_day"]).reset_index(drop=True)


def build_summary(predictions: pd.DataFrame, cfg: EvalConfig) -> pd.DataFrame:
    summary = (
        predictions.groupby(["city", "icao", "timezone"], as_index=False)
        .agg(
            sample_days=("local_day", "size"),
            exact_tenth_win_rate=("hit_exact_tenth", "mean"),
            rounded_c_win_rate=("hit_rounded_c", "mean"),
            within_1c_win_rate=("hit_within_1c", "mean"),
            within_2c_win_rate=("hit_within_2c", "mean"),
            mae_c=("abs_error_c", "mean"),
            bias_c=("signed_error_c", "mean"),
            median_abs_error_c=("abs_error_c", "median"),
            actual_mean_max_c=("actual_final_max_c", "mean"),
            predicted_mean_max_c=("predicted_daily_max_c", "mean"),
        )
        .sort_values(["rounded_c_win_rate", "exact_tenth_win_rate", "mae_c"], ascending=[False, False, True])
        .reset_index(drop=True)
    )
    summary["lead_days"] = cfg.lead_days
    return summary


def build_metrics(predictions: pd.DataFrame, start_date: str, end_date: str, cfg: EvalConfig) -> pd.DataFrame:
    metrics = pd.DataFrame(
        [
            {
                "lead_days": cfg.lead_days,
                "start_date": start_date,
                "end_date": end_date,
                "sample_days": len(predictions),
                "cities": predictions["city"].nunique(),
                "global_exact_tenth_win_rate": predictions["hit_exact_tenth"].mean(),
                "global_rounded_c_win_rate": predictions["hit_rounded_c"].mean(),
                "global_within_1c_win_rate": predictions["hit_within_1c"].mean(),
                "global_within_2c_win_rate": predictions["hit_within_2c"].mean(),
                "global_mae_c": predictions["abs_error_c"].mean(),
                "global_bias_c": predictions["signed_error_c"].mean(),
            }
        ]
    )
    return metrics


def render_html(summary: pd.DataFrame, metrics: pd.DataFrame, predictions: pd.DataFrame, output_path: Path) -> None:
    metric = metrics.iloc[0]
    best = summary.head(6)
    worst = summary.sort_values(["rounded_c_win_rate", "mae_c"], ascending=[True, False]).head(6)

    def rows_html(frame: pd.DataFrame) -> str:
        rows = []
        for row in frame.itertuples(index=False):
            rows.append(
                "<tr>"
                f"<td>{html.escape(row.city)}</td>"
                f"<td>{html.escape(row.timezone)}</td>"
                f"<td>{int(row.sample_days)}</td>"
                f"<td>{row.exact_tenth_win_rate * 100:.1f}%</td>"
                f"<td>{row.rounded_c_win_rate * 100:.1f}%</td>"
                f"<td>{row.within_1c_win_rate * 100:.1f}%</td>"
                f"<td>{row.within_2c_win_rate * 100:.1f}%</td>"
                f"<td>{row.mae_c:.2f}</td>"
                f"<td>{row.bias_c:+.2f}</td>"
                "</tr>"
            )
        return "\n".join(rows)

    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Day+4 Forecast Win Rate</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f3ea;
      --panel: #fffdf8;
      --ink: #1e1d1a;
      --muted: #6e675b;
      --accent: #0c7c59;
      --border: #d8d0c2;
      --bad: #a43a2f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Iowan Old Style", serif;
      background: radial-gradient(circle at top left, #fff7df, var(--bg) 55%);
      color: var(--ink);
    }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 32px 20px 48px; }}
    h1, h2 {{ margin: 0 0 12px; }}
    p {{ margin: 0; line-height: 1.45; color: var(--muted); }}
    .grid {{
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      margin: 20px 0 28px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px 18px;
      box-shadow: 0 10px 28px rgba(60, 44, 18, 0.06);
    }}
    .value {{ font-size: 32px; font-weight: 700; color: var(--accent); }}
    .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }}
    .section {{ margin-top: 28px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      font-size: 14px;
    }}
    th {{ background: #f0eadc; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }}
    tr:last-child td {{ border-bottom: none; }}
    .note {{ margin-top: 10px; font-size: 13px; }}
    .bad {{ color: var(--bad); }}
  </style>
</head>
<body>
  <main>
    <h1>Day+4 Forecast Daily-Max Backtest</h1>
    <p>
      Open-Meteo Previous Runs API, using hourly <code>temperature_2m_previous_day4</code> and taking the
      daily max for each local calendar day. Actuals come from station observations in the NOAA baseline dataset.
    </p>

    <div class="grid">
      <div class="card"><div class="label">Sample Period</div><div class="value">{metric.start_date}</div><p>through {metric.end_date}</p></div>
      <div class="card"><div class="label">Cities</div><div class="value">{int(metric.cities)}</div><p>same set as the baseline report</p></div>
      <div class="card"><div class="label">Rounded Win Rate</div><div class="value">{metric.global_rounded_c_win_rate * 100:.1f}%</div><p>predicted rounded max == actual rounded max</p></div>
      <div class="card"><div class="label">Exact Tenth Win Rate</div><div class="value">{metric.global_exact_tenth_win_rate * 100:.1f}%</div><p>predicted 0.1°C max == actual 0.1°C max</p></div>
      <div class="card"><div class="label">Within ±1°C</div><div class="value">{metric.global_within_1c_win_rate * 100:.1f}%</div><p>rounded forecast within 3-degree window</p></div>
      <div class="card"><div class="label">Within ±2°C</div><div class="value">{metric.global_within_2c_win_rate * 100:.1f}%</div><p>rounded forecast within 5-degree window</p></div>
      <div class="card"><div class="label">Global MAE</div><div class="value">{metric.global_mae_c:.2f}°C</div><p>absolute error of day+4 daily max</p></div>
      <div class="card"><div class="label">Global Bias</div><div class="value">{metric.global_bias_c:+.2f}°C</div><p>signed forecast bias</p></div>
    </div>

    <div class="section">
      <h2>Best Cities</h2>
      <table>
        <thead>
          <tr>
            <th>City</th>
            <th>Timezone</th>
            <th>Days</th>
            <th>Exact Tenth</th>
            <th>Rounded</th>
            <th>±1°C</th>
            <th>±2°C</th>
            <th>MAE</th>
            <th>Bias</th>
          </tr>
        </thead>
        <tbody>{rows_html(best)}</tbody>
      </table>
    </div>

    <div class="section">
      <h2>Weakest Cities</h2>
      <table>
        <thead>
          <tr>
            <th>City</th>
            <th>Timezone</th>
            <th>Days</th>
            <th>Exact Tenth</th>
            <th>Rounded</th>
            <th>±1°C</th>
            <th>±2°C</th>
            <th>MAE</th>
            <th>Bias</th>
          </tr>
        </thead>
        <tbody>{rows_html(worst)}</tbody>
      </table>
      <p class="note bad">
        This is a pure day+4 forecast backtest. It is not using same-day information, current max, or late-day observations.
      </p>
    </div>

    <div class="section">
      <h2>All Cities</h2>
      <table>
        <thead>
          <tr>
            <th>City</th>
            <th>Timezone</th>
            <th>Days</th>
            <th>Exact Tenth</th>
            <th>Rounded</th>
            <th>±1°C</th>
            <th>±2°C</th>
            <th>MAE</th>
            <th>Bias</th>
          </tr>
        </thead>
        <tbody>{rows_html(summary)}</tbody>
      </table>
      <p class="note">Merged days: {len(predictions)}.</p>
    </div>
  </main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body, encoding="utf-8")


def main() -> None:
    args = parse_args()
    cfg = EvalConfig(lead_days=args.lead_days, earliest_api_date=args.earliest_api_date)
    cache_dir = Path(args.cache_dir)

    actuals, start_date, end_date = load_actuals(Path(args.baseline_dataset), cfg)
    predictions = build_predictions(actuals, start_date, end_date, cfg, cache_dir)
    summary = build_summary(predictions, cfg)
    metrics = build_metrics(predictions, start_date, end_date, cfg)

    predictions_output = Path(args.predictions_output)
    summary_output = Path(args.summary_output)
    metrics_output = Path(args.metrics_output)
    html_output = Path(args.html_output)

    predictions_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.parent.mkdir(parents=True, exist_ok=True)

    predictions.to_csv(predictions_output, index=False)
    summary.to_csv(summary_output, index=False)
    metrics.to_csv(metrics_output, index=False)
    render_html(summary, metrics, predictions, html_output)

    print(f"Saved predictions: {predictions_output}")
    print(f"Saved summary: {summary_output}")
    print(f"Saved metrics: {metrics_output}")
    print(f"Saved HTML: {html_output}")
    print(
        "Global rounded win rate="
        f"{metrics.iloc[0]['global_rounded_c_win_rate']:.4f}, "
        f"exact tenth win rate={metrics.iloc[0]['global_exact_tenth_win_rate']:.4f}, "
        f"MAE={metrics.iloc[0]['global_mae_c']:.3f}"
    )


if __name__ == "__main__":
    main()
