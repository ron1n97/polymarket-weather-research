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
from sklearn.preprocessing import OneHotEncoder


BASE_FEATURE_COLUMNS = [
    "city",
    "icao",
    "timezone",
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
]

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
]

OPTIONAL_NUMERIC_COLUMNS = [
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

CATEGORICAL_COLUMNS = ["city", "icao", "timezone"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a first classifier and compare model vs current-max baseline."
    )
    parser.add_argument(
        "--input",
        default="outputs/model_features.csv",
        help="Input features CSV. Default: outputs/model_features.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/model_eval",
        help="Output directory. Default: outputs/model_eval",
    )
    parser.add_argument(
        "--train-until-year",
        type=int,
        default=2024,
        help="Train on rows with local_day year <= this value. Default: 2024",
    )
    parser.add_argument(
        "--target",
        choices=["exact", "rounded"],
        default="exact",
        help="Training target. Default: exact",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.99,
        help="Probability threshold for earliest confident hour. Default: 0.99",
    )
    parser.add_argument(
        "--model",
        choices=["hgbt", "logreg"],
        default="hgbt",
        help="Classifier backend. Default: hgbt",
    )
    return parser.parse_args()


def build_pipeline(model_name: str) -> Pipeline:
    numeric_columns = NUMERIC_COLUMNS + [col for col in OPTIONAL_NUMERIC_COLUMNS if col in FEATURE_COLUMNS]
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                    ]
                ),
                numeric_columns,
            ),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore"),
                CATEGORICAL_COLUMNS,
            ),
        ]
    )
    if model_name == "logreg":
        from sklearn.linear_model import LogisticRegression

        base_model = LogisticRegression(max_iter=3000, class_weight="balanced")
    else:
        base_model = HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_depth=6,
            max_iter=300,
            min_samples_leaf=50,
            random_state=42,
        )
    calibrated_model = CalibratedClassifierCV(estimator=base_model, method="isotonic", cv=3)
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", calibrated_model),
        ]
    )


def add_predictions(df: pd.DataFrame, proba: pd.Series, target_col: str, threshold: float) -> pd.DataFrame:
    scored = df.copy()
    scored["model_proba"] = proba
    scored["model_pred_above_threshold"] = (scored["model_proba"] >= threshold).astype(int)
    scored["baseline_pred"] = scored[target_col.replace("hit_", "current_")].astype(int) if False else 0
    return scored


def summarise(df: pd.DataFrame, target_col: str, threshold: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    daily_rows = []
    for city, city_df in df.groupby("city", sort=True):
        city_df = city_df.sort_values(["local_day", "cutoff_hour"])
        per_day = []
        for local_day, day_df in city_df.groupby("local_day", sort=True):
            day_df = day_df.sort_values("cutoff_hour")
            model_row = day_df[day_df["model_proba"] >= threshold].head(1)
            baseline_row = day_df[day_df[target_col] == 1].head(1)
            cutoff_row = day_df.iloc[-1]
            per_day.append(
                {
                    "city": city,
                    "local_day": str(local_day.date()),
                    "model_first_hour_99": None if model_row.empty else int(model_row.iloc[0]["cutoff_hour"]),
                    "baseline_first_hour_99": None if baseline_row.empty else int(baseline_row.iloc[0]["cutoff_hour"]),
                    "model_win_at_cutoff": int(cutoff_row["model_proba"] >= threshold and cutoff_row[target_col] == 1),
                    "baseline_win_at_cutoff": int(cutoff_row[target_col] == 1),
                    "target_at_cutoff": int(cutoff_row[target_col]),
                    "model_proba_at_cutoff": float(cutoff_row["model_proba"]),
                }
            )
        daily_df = pd.DataFrame(per_day)
        daily_rows.append(daily_df)
        rows.append(
            {
                "city": city,
                "sample_days": len(daily_df),
                "model_days_with_99": int(daily_df["model_first_hour_99"].notna().sum()),
                "baseline_days_with_99": int(daily_df["baseline_first_hour_99"].notna().sum()),
                "model_mean_first_hour_99": daily_df["model_first_hour_99"].dropna().mean(),
                "baseline_mean_first_hour_99": daily_df["baseline_first_hour_99"].dropna().mean(),
                "model_cutoff_99_hit_rate": daily_df["model_win_at_cutoff"].mean(),
                "baseline_cutoff_99_hit_rate": daily_df["baseline_win_at_cutoff"].mean(),
            }
        )

    return pd.DataFrame(rows), pd.concat(daily_rows, ignore_index=True)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path)
    df["local_day"] = pd.to_datetime(df["local_day"])
    df["cutoff_timestamp_utc"] = pd.to_datetime(df["cutoff_timestamp_utc"], utc=True)
    target_col = "hit_final_max_exact" if args.target == "exact" else "hit_final_max_rounded"
    global FEATURE_COLUMNS
    FEATURE_COLUMNS = BASE_FEATURE_COLUMNS + [col for col in OPTIONAL_NUMERIC_COLUMNS if col in df.columns]

    train_df = df[df["year"] <= args.train_until_year].copy()
    test_df = df[df["year"] > args.train_until_year].copy()
    if train_df.empty or test_df.empty:
        raise RuntimeError("Train/test split is empty. Adjust --train-until-year.")

    pipeline = build_pipeline(args.model)
    pipeline.fit(train_df[FEATURE_COLUMNS], train_df[target_col])
    train_proba = pipeline.predict_proba(train_df[FEATURE_COLUMNS])[:, 1]
    test_proba = pipeline.predict_proba(test_df[FEATURE_COLUMNS])[:, 1]

    metrics = pd.DataFrame(
        [
            {
                "model": args.model,
                "split": "train",
                "rows": len(train_df),
                "positive_rate": train_df[target_col].mean(),
                "roc_auc": roc_auc_score(train_df[target_col], train_proba),
                "brier_score": brier_score_loss(train_df[target_col], train_proba),
            },
            {
                "model": args.model,
                "split": "test",
                "rows": len(test_df),
                "positive_rate": test_df[target_col].mean(),
                "roc_auc": roc_auc_score(test_df[target_col], test_proba),
                "brier_score": brier_score_loss(test_df[target_col], test_proba),
            },
        ]
    )

    scored_test = test_df.copy()
    scored_test["model_proba"] = test_proba
    summary, daily = summarise(scored_test, target_col=target_col, threshold=args.threshold)

    metrics.to_csv(output_dir / "metrics.csv", index=False)
    summary.to_csv(output_dir / "city_summary.csv", index=False)
    daily.to_csv(output_dir / "daily_first_99.csv", index=False)
    scored_test.to_csv(output_dir / "test_predictions.csv", index=False)

    print(metrics.to_string(index=False))
    print()
    print(summary.sort_values("model_cutoff_99_hit_rate", ascending=False).to_string(index=False))
    print(f"\nSaved evaluation outputs to: {output_dir}")


if __name__ == "__main__":
    main()
