#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate bankroll growth from per-trade fraction sizing.")
    parser.add_argument("--trades", required=True, help="Backtest trades CSV.")
    parser.add_argument("--output-dir", required=True, help="Directory for outputs.")
    parser.add_argument("--initial-bankroll", type=float, default=50.0, help="Starting bankroll.")
    parser.add_argument(
        "--fractions",
        default="0.002,0.003,0.005,0.007,0.01,0.015,0.02,0.025,0.03",
        help="Comma-separated fractions of bankroll to risk per trade.",
    )
    parser.add_argument(
        "--max-dd-threshold",
        type=float,
        default=25.0,
        help="Max drawdown threshold in percent for recommended fraction.",
    )
    parser.add_argument(
        "--max-trades-per-day",
        type=int,
        default=6,
        help="Maximum number of trades allowed per market_date. Default: 6",
    )
    parser.add_argument(
        "--max-trades-per-city-day",
        type=int,
        default=2,
        help="Maximum number of trades allowed per city per market_date. Default: 2",
    )
    parser.add_argument(
        "--max-daily-fraction",
        type=float,
        default=0.012,
        help="Maximum total fraction of bankroll risked per day. Default: 0.012",
    )
    parser.add_argument(
        "--min-stake",
        type=float,
        default=0.0,
        help="Minimum USD stake per trade. Default: 0.0",
    )
    return parser.parse_args()


def select_trades(df: pd.DataFrame, max_trades_per_day: int, max_trades_per_city_day: int) -> pd.DataFrame:
    ranked = df.copy()
    ranked["abs_edge_pp"] = ranked["edge_pp"].abs()
    ranked = ranked.sort_values(["market_date", "abs_edge_pp"], ascending=[True, False]).reset_index(drop=True)

    selected_parts: list[pd.DataFrame] = []
    for _, day_frame in ranked.groupby("market_date", sort=True):
        city_limited = day_frame.groupby("city", group_keys=False).head(max_trades_per_city_day)
        selected_parts.append(city_limited.head(max_trades_per_day))

    selected = pd.concat(selected_parts, ignore_index=True) if selected_parts else ranked.iloc[0:0].copy()
    return selected.sort_values(["market_date", "abs_edge_pp"], ascending=[True, False]).reset_index(drop=True)


def simulate(
    df: pd.DataFrame,
    initial_bankroll: float,
    fraction: float,
    max_trades_per_day: int,
    max_trades_per_city_day: int,
    max_daily_fraction: float,
    min_stake: float,
) -> tuple[pd.DataFrame, dict]:
    bank = initial_bankroll
    peak = bank
    max_dd = 0.0
    rows: list[dict[str, object]] = []

    ordered = select_trades(df, max_trades_per_day, max_trades_per_city_day)
    for i, row in enumerate(ordered.itertuples(index=False), start=1):
        cost = row.yes_price if row.action == "bet yes" else (1 - row.yes_price)
        if cost <= 0:
            continue
        day_trade_count = min(max_trades_per_day, max(1, len(ordered[ordered["market_date"] == row.market_date])))
        per_trade_fraction = min(fraction, max_daily_fraction / day_trade_count)
        target_stake = bank * per_trade_fraction
        stake = max(target_stake, min_stake)
        shares = stake / cost
        pnl = shares * row.pnl_per_share
        bank_before = bank
        bank += pnl
        peak = max(peak, bank)
        drawdown = (1 - bank / peak) * 100 if peak else 0.0
        max_dd = max(max_dd, drawdown)
        rows.append(
            {
                "trade_number": i,
                "market_date": row.market_date,
                "city": row.city,
                "bucket_label": row.bucket_label,
                "action": row.action,
                "edge_pp": row.edge_pp,
                "bank_before": bank_before,
                "target_stake_usd": target_stake,
                "stake_usd": stake,
                "min_bet_binding": stake > target_stake,
                "shares": shares,
                "pnl_usd": pnl,
                "bank_after": bank,
                "drawdown_pct": drawdown,
            }
        )
        if bank <= 0:
            bank = 0.0
            max_dd = 100.0
            break

    equity = pd.DataFrame(rows)
    summary = {
        "fraction": fraction,
        "trades": len(equity),
        "initial_bankroll": initial_bankroll,
        "terminal_bankroll": bank,
        "return_pct": (bank / initial_bankroll - 1) * 100,
        "max_drawdown_pct": max_dd,
        "max_trades_per_day": max_trades_per_day,
        "max_trades_per_city_day": max_trades_per_city_day,
        "max_daily_fraction": max_daily_fraction,
        "min_stake": min_stake,
    }
    return equity, summary


def render_html(summary: pd.DataFrame, recommended: pd.Series | None, output_path: Path) -> None:
    rec_html = "<p>No fraction met the drawdown threshold.</p>"
    if recommended is not None:
        rec_html = (
            f"<p>Recommended fraction: <strong>{recommended['fraction'] * 100:.2f}%</strong> of bankroll per trade. "
            f"Terminal bankroll: <strong>${recommended['terminal_bankroll']:.2f}</strong>. "
            f"Max drawdown: <strong>{recommended['max_drawdown_pct']:.2f}%</strong>. "
            f"Trade cap/day: <strong>{int(recommended['max_trades_per_day'])}</strong>. "
            f"City cap/day: <strong>{int(recommended['max_trades_per_city_day'])}</strong>. "
            f"Daily risk cap: <strong>{recommended['max_daily_fraction'] * 100:.2f}%</strong>. "
            f"Min stake: <strong>${recommended['min_stake']:.2f}</strong>.</p>"
        )
    output_path.write_text(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Bankroll Simulation</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 32px; }
    table { border-collapse: collapse; width: 100%%; margin-top: 16px; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: right; }
    th:first-child, td:first-child { text-align: left; }
  </style>
</head>
<body>
  <h1>Bankroll Simulation</h1>
  %s
  %s
</body>
</html>
"""
        % (rec_html, summary.to_html(index=False, float_format=lambda x: f"{x:.4f}")),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades = pd.read_csv(args.trades)
    fractions = [float(item.strip()) for item in args.fractions.split(",") if item.strip()]

    summaries: list[dict[str, object]] = []
    for fraction in fractions:
        equity, summary = simulate(
            trades,
            args.initial_bankroll,
            fraction,
            args.max_trades_per_day,
            args.max_trades_per_city_day,
            args.max_daily_fraction,
            args.min_stake,
        )
        summaries.append(summary)
        equity.to_csv(output_dir / f"equity_{fraction:.3f}.csv", index=False)

    summary_df = pd.DataFrame(summaries).sort_values("fraction")
    eligible = summary_df[summary_df["max_drawdown_pct"] <= args.max_dd_threshold]
    recommended = None if eligible.empty else eligible.sort_values("terminal_bankroll", ascending=False).iloc[0]

    summary_df.to_csv(output_dir / "bankroll_summary.csv", index=False)
    if recommended is not None:
        pd.DataFrame([recommended]).to_csv(output_dir / "bankroll_recommendation.csv", index=False)
    render_html(summary_df, recommended, output_dir / "bankroll_report.html")

    if recommended is not None:
        print(
            f"Recommended fraction={recommended['fraction']:.4f} "
            f"terminal_bankroll=${recommended['terminal_bankroll']:.2f} "
            f"max_dd={recommended['max_drawdown_pct']:.2f}%"
        )
    print(f"Saved outputs to {output_dir}")


if __name__ == "__main__":
    main()
