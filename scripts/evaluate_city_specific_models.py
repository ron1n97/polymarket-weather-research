#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline


NUMERIC_COLUMNS = [
    "cutoff_hour",
    "cutoff_utc_hour",
    "month",
    "day_of_year",
    "day_of_week",
    "observations_seen",
    "total_observations_day",
    "observations_remaining",
    "observations_seen_ratio",
    "hours_since_midnight",
    "hours_until_local_end",
    "hours_until_cutoff_utc",
    "current_max_c",
    "current_max_rounded_c",
    "delta_current_max_1h",
    "delta_current_max_3h",
    "delta_obs_1h",
    "rise_from_start_c",
    "rise_rate_c_per_hour",
    "forecast_temp_2m",
    "forecast_relative_humidity_2m",
    "forecast_dew_point_2m",
    "forecast_cloud_cover",
    "forecast_wind_speed_10m",
    "forecast_shortwave_radiation",
    "forecast_remaining_max_2m",
    "forecast_remaining_max_shortwave_radiation",
    "forecast_remaining_mean_cloud_cover",
    "forecast_remaining_mean_relative_humidity",
    "forecast_remaining_mean_wind_speed_10m",
    "forecast_remaining_max_temp_3h",
    "forecast_daily_max_2m",
    "forecast_gap_dailymax_minus_current_c",
    "forecast_gap_remaining_minus_current_c",
    "forecast_gap_hourly_minus_current_c",
    "forecast_gap_next3hmax_minus_current_c",
    "forecast_dewpoint_depression_c",
    "forecast_heat_potential_proxy",
    "forecast_drying_proxy",
    "forecast_temp_dew_gap_remaining_c",
    "forecast_tailwind_cooling_proxy",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train one separate model per city and compare to baseline.")
    parser.add_argument("--input", default="outputs/model_features.csv", help="Features CSV path")
    parser.add_argument("--output-dir", default="outputs/city_specific_eval", help="Output directory")
    parser.add_argument("--train-until-year", type=int, default=2024, help="Train on rows <= this year")
    parser.add_argument("--threshold", type=float, default=0.99, help="Confidence threshold")
    parser.add_argument(
        "--target",
        choices=["exact", "rounded"],
        default="exact",
        help="Training target. Default: exact",
    )
    return parser.parse_args()


def build_pipeline() -> Pipeline:
    available_numeric = [col for col in NUMERIC_COLUMNS if col in FEATURE_COLUMNS]
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))]),
                available_numeric,
            )
        ]
    )
    base_model = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_depth=6,
        max_iter=300,
        min_samples_leaf=30,
        random_state=42,
    )
    calibrated = CalibratedClassifierCV(estimator=base_model, method="isotonic", cv=3)
    return Pipeline([("preprocessor", preprocessor), ("model", calibrated)])


def summarise_city(test_df: pd.DataFrame, target_col: str, threshold: float) -> dict:
    per_day = []
    for local_day, day_df in test_df.groupby("local_day", sort=True):
        day_df = day_df.sort_values("cutoff_hour")
        model_row = day_df[day_df["model_proba"] >= threshold].head(1)
        baseline_row = day_df[day_df[target_col] == 1].head(1)
        cutoff_row = day_df.iloc[-1]
        per_day.append(
            {
                "local_day": str(local_day.date()),
                "model_first_hour_99": None if model_row.empty else int(model_row.iloc[0]["cutoff_hour"]),
                "baseline_first_hour_99": None if baseline_row.empty else int(baseline_row.iloc[0]["cutoff_hour"]),
                "model_cutoff_hit": int(cutoff_row["model_proba"] >= threshold and cutoff_row[target_col] == 1),
                "baseline_cutoff_hit": int(cutoff_row[target_col] == 1),
            }
        )
    daily_df = pd.DataFrame(per_day)
    return {
        "sample_days": len(daily_df),
        "model_days_with_99": int(daily_df["model_first_hour_99"].notna().sum()),
        "baseline_days_with_99": int(daily_df["baseline_first_hour_99"].notna().sum()),
        "model_mean_first_hour_99": daily_df["model_first_hour_99"].dropna().mean(),
        "baseline_mean_first_hour_99": daily_df["baseline_first_hour_99"].dropna().mean(),
        "model_cutoff_99_hit_rate": daily_df["model_cutoff_hit"].mean(),
        "baseline_cutoff_99_hit_rate": daily_df["baseline_cutoff_hit"].mean(),
    }


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input)
    df["local_day"] = pd.to_datetime(df["local_day"])
    target_col = "hit_final_max_exact" if args.target == "exact" else "hit_final_max_rounded"

    global FEATURE_COLUMNS
    FEATURE_COLUMNS = df.columns.tolist()

    rows = []
    metric_rows = []
    for city, city_df in df.groupby("city", sort=True):
        train_df = city_df[city_df["year"] <= args.train_until_year].copy()
        test_df = city_df[city_df["year"] > args.train_until_year].copy()
        if train_df.empty or test_df.empty:
            continue
        if train_df[target_col].nunique() < 2:
            continue

        pipeline = build_pipeline()
        pipeline.fit(train_df, train_df[target_col])
        train_proba = pipeline.predict_proba(train_df)[:, 1]
        test_proba = pipeline.predict_proba(test_df)[:, 1]
        test_df = test_df.copy()
        test_df["model_proba"] = test_proba

        summary = summarise_city(test_df, target_col=target_col, threshold=args.threshold)
        rows.append(
            {
                "city": city,
                **summary,
            }
        )
        metric_rows.extend(
            [
                {
                    "city": city,
                    "split": "train",
                    "rows": len(train_df),
                    "positive_rate": train_df[target_col].mean(),
                    "roc_auc": roc_auc_score(train_df[target_col], train_proba),
                    "brier_score": brier_score_loss(train_df[target_col], train_proba),
                },
                {
                    "city": city,
                    "split": "test",
                    "rows": len(test_df),
                    "positive_rate": test_df[target_col].mean(),
                    "roc_auc": roc_auc_score(test_df[target_col], test_proba),
                    "brier_score": brier_score_loss(test_df[target_col], test_proba),
                },
            ]
        )

    summary_df = pd.DataFrame(rows).sort_values("model_mean_first_hour_99", na_position="last")
    metrics_df = pd.DataFrame(metric_rows).sort_values(["city", "split"])
    summary_df.to_csv(output_dir / "city_specific_summary.csv", index=False)
    metrics_df.to_csv(output_dir / "city_specific_metrics.csv", index=False)

    print(summary_df.to_string(index=False))
    print(f"\nSaved city-specific outputs to: {output_dir}")


if __name__ == "__main__":
    main()
