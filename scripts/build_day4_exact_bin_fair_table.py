#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

FAHRENHEIT_CITIES = {"London", "Dallas", "New York City"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build day+4 exact-bin fair probability table from historical predictions.")
    parser.add_argument(
        "--input",
        default="outputs/day4_forecast_eval/day4_forecast_predictions.csv",
        help="Day+4 predictions CSV. Default: outputs/day4_forecast_eval/day4_forecast_predictions.csv",
    )
    parser.add_argument(
        "--output",
        default="outputs/fair_value/day4_exact_bin_fair.csv",
        help="Output CSV. Default: outputs/fair_value/day4_exact_bin_fair.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.input)
    df["settlement_unit"] = df["city"].apply(lambda city: "F" if city in FAHRENHEIT_CITIES else "C")
    df["forecast_center_bin_c"] = df["predicted_daily_max_rounded_c"]
    df["actual_bin_c"] = df["actual_final_max_rounded_c"]
    df["forecast_center_bin_f"] = ((df["predicted_daily_max_c"] * 9 / 5) + 32).round().astype(int)
    df["actual_bin_f"] = ((df["actual_final_max_c"] * 9 / 5) + 32).round().astype(int)
    df["forecast_center_bin"] = df.apply(
        lambda row: row["forecast_center_bin_f"] if row["settlement_unit"] == "F" else row["forecast_center_bin_c"],
        axis=1,
    )
    df["actual_bin"] = df.apply(
        lambda row: row["actual_bin_f"] if row["settlement_unit"] == "F" else row["actual_bin_c"],
        axis=1,
    )

    grouped = (
        df.groupby(["city", "settlement_unit", "forecast_center_bin", "actual_bin"], as_index=False)
        .agg(sample_days=("local_day", "size"))
        .rename(
            columns={
                "forecast_center_bin": "forecast_center_bin",
                "actual_bin": "actual_bin",
            }
        )
    )

    totals = (
        grouped.groupby(["city", "settlement_unit", "forecast_center_bin"], as_index=False)["sample_days"]
        .sum()
        .rename(columns={"sample_days": "center_sample_days"})
    )
    fair = grouped.merge(totals, on=["city", "settlement_unit", "forecast_center_bin"], how="left")
    fair["probability"] = fair["sample_days"] / fair["center_sample_days"]
    fair = fair.sort_values(["city", "forecast_center_bin", "actual_bin"]).reset_index(drop=True)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fair.to_csv(output_path, index=False)
    print(f"Saved exact-bin fair table to {output_path}")
    print(f"Rows={len(fair)} Cities={fair['city'].nunique()}")


if __name__ == "__main__":
    main()
