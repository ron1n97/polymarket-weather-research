#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest bucket-level edge strategy against resolved outcomes.")
    parser.add_argument(
        "--snapshots",
        default="outputs/polymarket/historical_weather_markets.csv",
        help="Historical market snapshots CSV. Default: outputs/polymarket/historical_weather_markets.csv",
    )
    parser.add_argument(
        "--fair",
        default="outputs/fair_value/day4_exact_bin_fair.csv",
        help="Exact-bin fair table CSV. Default: outputs/fair_value/day4_exact_bin_fair.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/backtest_edge_strategy",
        help="Output directory. Default: outputs/backtest_edge_strategy",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=40,
        help="Minimum center-bin historical sample. Default: 40",
    )
    parser.add_argument(
        "--min-edge-pp",
        type=float,
        default=8.0,
        help="Minimum absolute edge in percentage points. Default: 8.0",
    )
    return parser.parse_args()


def classify(edge_pp: float, center_sample_days: float, min_samples: int, min_edge_pp: float) -> str:
    if pd.isna(center_sample_days) or center_sample_days < min_samples:
        return "skip"
    if edge_pp >= min_edge_pp:
        return "bet yes"
    if edge_pp <= -min_edge_pp:
        return "bet no"
    return "skip"


def bucket_probability(city_fair: pd.DataFrame, low: float | None, high: float | None) -> float:
    mask = pd.Series(True, index=city_fair.index)
    if low == low:
        mask &= city_fair["actual_bin"] >= int(low)
    if high == high:
        mask &= city_fair["actual_bin"] <= int(high)
    return city_fair.loc[mask, "probability"].sum()


def main() -> None:
    args = parse_args()
    snapshots_path = Path(args.snapshots)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not snapshots_path.exists():
        summary = pd.DataFrame(
            [
                {
                    "status": "missing historical snapshots",
                    "snapshots_path": str(snapshots_path),
                    "note": "Backtest engine is ready, but realized PnL backtest needs historical market prices collected at entry time.",
                }
            ]
        )
        summary.to_csv(output_dir / "backtest_summary.csv", index=False)
        (output_dir / "backtest_report.html").write_text(
            f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><title>Backtest Unavailable</title></head>
<body>
  <h1>Backtest Unavailable</h1>
  <p>Historical market snapshots were not found at <code>{snapshots_path}</code>.</p>
  <p>The backtest engine is implemented, but realized PnL requires bucket prices captured before resolution.</p>
</body>
</html>""",
            encoding="utf-8",
        )
        print(f"Historical snapshots not found: {snapshots_path}")
        print(f"Saved placeholder outputs to {output_dir}")
        return

    snapshots = pd.read_csv(snapshots_path)
    fair = pd.read_csv(args.fair)
    joined = snapshots.copy()
    joined["bucket_low_c"] = pd.to_numeric(joined["bucket_low_c"], errors="coerce")
    joined["bucket_high_c"] = pd.to_numeric(joined["bucket_high_c"], errors="coerce")
    joined["yes_price"] = pd.to_numeric(joined["yes_price"], errors="coerce")
    joined["center_bin"] = pd.to_numeric(joined["center_bin"], errors="coerce")
    joined["resolved_yes"] = pd.to_numeric(joined["resolved_yes"], errors="coerce")

    records = []
    for row in joined.itertuples(index=False):
        city_fair = fair[
            (fair["city"] == row.city)
            & (fair["settlement_unit"] == row.bucket_unit)
            & (fair["forecast_center_bin"] == row.center_bin)
        ]
        if city_fair.empty:
            continue

        fair_probability = bucket_probability(city_fair, row.bucket_low_c, row.bucket_high_c)
        center_sample_days = float(city_fair["center_sample_days"].iloc[0])
        edge_pp = (fair_probability - row.yes_price) * 100
        action = classify(edge_pp, center_sample_days, args.min_samples, args.min_edge_pp)
        if action == "skip":
            continue

        resolved_yes = int(row.resolved_yes)
        pnl = (1 - row.yes_price) if action == "bet yes" and resolved_yes else -row.yes_price if action == "bet yes" else row.yes_price if not resolved_yes else -(1 - row.yes_price)
        records.append(
            {
                "city": row.city,
                "market_date": row.market_date,
                "bucket_label": row.bucket_label,
                "action": action,
                "yes_price": row.yes_price,
                "fair_probability": fair_probability,
                "edge_pp": edge_pp,
                "center_sample_days": center_sample_days,
                "resolved_yes": resolved_yes,
                "pnl_per_share": pnl,
            }
        )

    trades = pd.DataFrame(records)
    if trades.empty:
        summary = pd.DataFrame(
            [
                {
                    "status": "no trades",
                    "note": "No historical rows passed the current filters.",
                }
            ]
        )
    else:
        summary = pd.DataFrame(
            [
                {
                    "status": "ok",
                    "trades": len(trades),
                    "win_rate": ((trades["action"] == "bet yes") & (trades["resolved_yes"] == 1) | (trades["action"] == "bet no") & (trades["resolved_yes"] == 0)).mean(),
                    "avg_pnl_per_share": trades["pnl_per_share"].mean(),
                    "total_pnl_per_share": trades["pnl_per_share"].sum(),
                }
            ]
        )

    trades.to_csv(output_dir / "backtest_trades.csv", index=False)
    summary.to_csv(output_dir / "backtest_summary.csv", index=False)
    (output_dir / "backtest_report.html").write_text(
        f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><title>Edge Strategy Backtest</title></head>
<body>
  <h1>Edge Strategy Backtest</h1>
  <p>Trades file: <code>{output_dir / 'backtest_trades.csv'}</code></p>
  <p>Summary file: <code>{output_dir / 'backtest_summary.csv'}</code></p>
</body>
</html>""",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print(f"Saved outputs to {output_dir}")


if __name__ == "__main__":
    main()
