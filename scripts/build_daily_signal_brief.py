#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a compact daily brief from the paper trading dashboard.")
    parser.add_argument(
        "--dashboard",
        default="outputs/paper/paper_trading_dashboard.csv",
        help="Paper dashboard CSV.",
    )
    parser.add_argument(
        "--output",
        default="outputs/paper/daily_signal_brief.csv",
        help="Brief CSV output.",
    )
    parser.add_argument(
        "--html-output",
        default="outputs/paper/daily_signal_brief.html",
        help="Brief HTML output.",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=50.0,
        help="Current bankroll in USD.",
    )
    parser.add_argument(
        "--max-trades-per-day",
        type=int,
        default=6,
        help="Max selected trades per day.",
    )
    parser.add_argument(
        "--max-trades-per-city-day",
        type=int,
        default=2,
        help="Max selected trades per city per day.",
    )
    parser.add_argument(
        "--max-daily-fraction",
        type=float,
        default=0.012,
        help="Max daily bankroll fraction.",
    )
    return parser.parse_args()


def render_html(
    df: pd.DataFrame,
    output_path: Path,
    bankroll: float,
    max_trades_per_day: int,
    max_trades_per_city_day: int,
    max_daily_fraction: float,
) -> None:
    actionable = df[df["signal"].isin(["trade", "paper only"])].copy()
    live_actionable = actionable[actionable["signal"] == "trade"].copy()
    paper_actionable = actionable[actionable["signal"] == "paper only"].copy()
    live_risk_used = live_actionable["paper_stake_usd"].sum()
    paper_risk_used = paper_actionable["paper_stake_usd"].sum()
    daily_risk_cap = bankroll * max_daily_fraction
    live_risk_remaining = max(daily_risk_cap - live_risk_used, 0.0)
    rows = "\n".join(
        (
            "<tr>"
            f"<td>{row.signal}</td>"
            f"<td>{row.city}</td>"
            f"<td>{row.bucket_label}</td>"
            f"<td>{row.side}</td>"
            f"<td>{row.tier}</td>"
            f"<td>{row.yes_price * 100:.1f}%</td>"
            f"<td>{row.fair_probability * 100:.1f}%</td>"
            f"<td>{row.edge_pp:+.1f}pp</td>"
            f"<td>{row.entry_rule}</td>"
            f"<td>${row.paper_stake_usd:.2f}</td>"
            f"<td>{int(row.city_trades_today)}/{max_trades_per_city_day}</td>"
            f"<td>{row.volume_usd:,.0f}</td>"
            f"<td><a href='{row.event_url}'>market</a></td>"
            "</tr>"
        )
        for row in actionable.itertuples(index=False)
    )
    trade_count = int((actionable["signal"] == "trade").sum())
    paper_count = int((actionable["signal"] == "paper only").sum())
    output_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Daily Signal Brief</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 24px; background: #f5f1e8; color: #1e1d1a; }}
    table {{ border-collapse: collapse; width: 100%; background: #fffdf8; }}
    th, td {{ border-bottom: 1px solid #ddd2c4; padding: 10px 8px; text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #6b665d; }}
  </style>
</head>
<body>
  <h1>Daily Signal Brief</h1>
  <p>Actionable trades: <strong>{trade_count}</strong>. Paper-only ideas: <strong>{paper_count}</strong>.</p>
  <p>Live risk used: <strong>${live_risk_used:.2f}</strong> / ${daily_risk_cap:.2f}. Remaining: <strong>${live_risk_remaining:.2f}</strong>. Live trade slots used: <strong>{len(live_actionable)}</strong> / {max_trades_per_day}.</p>
  <p>Paper-only risk tracked separately: <strong>${paper_risk_used:.2f}</strong>.</p>
  <table>
    <thead>
      <tr>
        <th>Signal</th>
        <th>City</th>
        <th>Bucket</th>
        <th>Side</th>
        <th>Tier</th>
        <th>Market</th>
        <th>Fair</th>
        <th>Edge</th>
        <th>Entry Rule</th>
        <th>Paper Size</th>
        <th>City Cap</th>
        <th>Volume</th>
        <th>Event</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>""",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.dashboard)
    brief = df[df["signal"].isin(["trade", "paper only"])].copy()
    brief = brief.sort_values(["signal", "abs_edge_pp"], ascending=[True, False])
    brief["city_trades_today"] = brief.groupby("city")["city"].transform("size")
    brief["daily_risk_cap_usd"] = args.bankroll * args.max_daily_fraction
    brief["daily_risk_used_usd"] = brief["paper_stake_usd"].sum()
    brief["daily_risk_remaining_usd"] = max(brief["daily_risk_cap_usd"].iloc[0] - brief["daily_risk_used_usd"].iloc[0], 0.0) if not brief.empty else args.bankroll * args.max_daily_fraction
    brief["city_cap_remaining"] = args.max_trades_per_city_day - brief["city_trades_today"]

    output_path = Path(args.output)
    html_output_path = Path(args.html_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    brief.to_csv(output_path, index=False)
    render_html(
        brief,
        html_output_path,
        args.bankroll,
        args.max_trades_per_day,
        args.max_trades_per_city_day,
        args.max_daily_fraction,
    )
    print(f"Saved brief to {output_path}")
    print(f"Saved HTML brief to {html_output_path}")


if __name__ == "__main__":
    main()
