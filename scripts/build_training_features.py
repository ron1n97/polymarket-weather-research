#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build engineered model features from the baseline city/day/hour dataset."
    )
    parser.add_argument(
        "--input",
        default="outputs/baseline_dataset.csv",
        help="Input baseline dataset CSV. Default: outputs/baseline_dataset.csv",
    )
    parser.add_argument(
        "--output",
        default="outputs/model_features.csv",
        help="Output features CSV. Default: outputs/model_features.csv",
    )
    parser.add_argument(
        "--forecast-input",
        default="outputs/openmeteo_forecast_features.csv",
        help="Optional external forecast features CSV. Default: outputs/openmeteo_forecast_features.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    forecast_input_path = Path(args.forecast_input)

    df = pd.read_csv(input_path)
    df["local_day"] = pd.to_datetime(df["local_day"])
    df["cutoff_timestamp_utc"] = pd.to_datetime(df["cutoff_timestamp_utc"], utc=True)
    df["cutoff_hour"] = df["cutoff_hour_local"].str.slice(0, 2).astype(int)
    df["cutoff_utc_hour"] = df["cutoff_timestamp_utc"].dt.hour
    df["month"] = df["local_day"].dt.month
    df["day_of_year"] = df["local_day"].dt.dayofyear
    df["year"] = df["local_day"].dt.year
    df["day_of_week"] = df["local_day"].dt.dayofweek

    df = df.sort_values(["city", "local_day", "cutoff_hour"]).reset_index(drop=True)
    day_key = ["city", "local_day"]
    grouped = df.groupby(day_key, sort=False)

    df["observations_remaining"] = df["total_observations_day"] - df["observations_seen"]
    df["observations_seen_ratio"] = df["observations_seen"] / df["total_observations_day"]
    df["hours_since_midnight"] = df["cutoff_hour"].astype(float)
    df["hours_until_local_end"] = 23.0 - df["cutoff_hour"]
    df["hours_until_cutoff_utc"] = 12.0 - (
        df["cutoff_timestamp_utc"].dt.hour + df["cutoff_timestamp_utc"].dt.minute / 60.0
    )
    df["current_vs_final_gap_c"] = df["final_max_c"] - df["current_max_c"]
    df["current_vs_final_gap_rounded_c"] = df["final_max_rounded_c"] - df["current_max_rounded_c"]

    if forecast_input_path.exists():
        forecast_df = pd.read_csv(forecast_input_path)
        forecast_df["local_day"] = pd.to_datetime(forecast_df["local_day"])
        df = df.merge(
            forecast_df,
            on=["city", "icao", "timezone", "local_day", "cutoff_hour_local"],
            how="left",
        )
        df["forecast_gap_dailymax_minus_current_c"] = df["forecast_daily_max_2m"] - df["current_max_c"]
        df["forecast_gap_remaining_minus_current_c"] = df["forecast_remaining_max_2m"] - df["current_max_c"]
        df["forecast_gap_hourly_minus_current_c"] = df["forecast_temp_2m"] - df["current_max_c"]
        df["forecast_gap_next3hmax_minus_current_c"] = df["forecast_remaining_max_temp_3h"] - df["current_max_c"]
        df["forecast_dewpoint_depression_c"] = df["forecast_temp_2m"] - df["forecast_dew_point_2m"]
        df["forecast_heat_potential_proxy"] = (
            df["forecast_remaining_max_shortwave_radiation"] * (1 - df["forecast_remaining_mean_cloud_cover"] / 100.0)
        )
        df["forecast_drying_proxy"] = 100.0 - df["forecast_remaining_mean_relative_humidity"]
        df["forecast_temp_dew_gap_remaining_c"] = df["forecast_remaining_max_2m"] - df["forecast_dew_point_2m"]
        df["forecast_tailwind_cooling_proxy"] = (
            df["forecast_remaining_mean_wind_speed_10m"] * df["forecast_remaining_mean_cloud_cover"] / 100.0
        )

    df["current_max_prev_1h"] = grouped["current_max_c"].shift(1)
    df["current_max_prev_2h"] = grouped["current_max_c"].shift(2)
    df["current_max_prev_3h"] = grouped["current_max_c"].shift(3)
    df["delta_current_max_1h"] = df["current_max_c"] - df["current_max_prev_1h"].fillna(df["current_max_c"])
    df["delta_current_max_3h"] = df["current_max_c"] - df["current_max_prev_3h"].fillna(df["current_max_c"])
    df["delta_obs_1h"] = df["observations_seen"] - grouped["observations_seen"].shift(1).fillna(0)

    first_temp = grouped["current_max_c"].transform("first")
    df["rise_from_start_c"] = df["current_max_c"] - first_temp
    day_so_far_hours = df["cutoff_hour"].clip(lower=1)
    df["rise_rate_c_per_hour"] = df["rise_from_start_c"] / day_so_far_hours

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved features to {output_path}")
    print(f"Rows={len(df)} City-days={df.groupby(day_key).ngroups}")


if __name__ == "__main__":
    main()
