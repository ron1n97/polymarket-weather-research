#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the daily weather trading research pipeline.")
    parser.add_argument(
        "--market-date",
        default=date.today().strftime("%Y-%m-%d"),
        help="Target market/forecast date in YYYY-MM-DD. Default: today.",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=50.0,
        help="Current bankroll in USD. Default: 50.",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip live market and forecast fetch steps.",
    )
    return parser.parse_args()


def run_step(name: str, cmd: list[str]) -> None:
    print(f"[run_daily_pipeline] {name}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    args = parse_args()

    market_date = args.market_date
    bankroll = f"{args.bankroll:.2f}"

    steps: list[tuple[str, list[str]]] = []
    if not args.skip_fetch:
        steps.extend(
            [
                (
                    "fetch_polymarket_weather_markets",
                    [PYTHON, "scripts/fetch_polymarket_weather_markets.py", "--market-date", market_date],
                ),
                (
                    "fetch_current_forecast_snapshot",
                    [PYTHON, "scripts/fetch_current_forecast_snapshot.py", "--forecast-date", market_date],
                ),
            ]
        )

    steps.extend(
        [
            ("build_current_market_monitor", [PYTHON, "scripts/build_current_market_monitor.py"]),
            ("calc_market_edge", [PYTHON, "scripts/calc_market_edge.py"]),
            ("filter_trade_candidates", [PYTHON, "scripts/filter_trade_candidates.py"]),
            (
                "build_paper_trading_dashboard",
                [PYTHON, "scripts/build_paper_trading_dashboard.py", "--bankroll", bankroll],
            ),
            (
                "build_daily_signal_brief",
                [PYTHON, "scripts/build_daily_signal_brief.py", "--bankroll", bankroll],
            ),
        ]
    )

    for name, cmd in steps:
        run_step(name, cmd)

    print()
    print("[run_daily_pipeline] done")
    print("[run_daily_pipeline] key outputs:")
    print("  outputs/paper/paper_trading_dashboard.html")
    print("  outputs/paper/daily_signal_brief.html")
    print("  outputs/edges/current_edge_table.html")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"[run_daily_pipeline] failed: {' '.join(exc.cmd)}", file=sys.stderr)
        raise SystemExit(exc.returncode)
