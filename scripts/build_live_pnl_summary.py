#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build live trade log summary and daily PnL report.")
    parser.add_argument(
        "--log",
        default="outputs/paper/live_trade_log.csv",
        help="Live trade log CSV.",
    )
    parser.add_argument(
        "--output",
        default="outputs/paper/live_pnl_summary.csv",
        help="Summary CSV output.",
    )
    parser.add_argument(
        "--daily-output",
        default="outputs/paper/live_daily_pnl.csv",
        help="Daily PnL CSV output.",
    )
    parser.add_argument(
        "--html-output",
        default="outputs/paper/live_pnl_summary.html",
        help="HTML summary output.",
    )
    return parser.parse_args()


def render_html(summary: pd.DataFrame, daily: pd.DataFrame, output_path: Path) -> None:
    summary_rows = "\n".join(
        f"<tr><td>{row.metric}</td><td>{row.value}</td></tr>"
        for row in summary.itertuples(index=False)
    )
    daily_rows = "\n".join(
        (
            "<tr>"
            f"<td>{row.market_date}</td>"
            f"<td>{int(row.trades)}</td>"
            f"<td>{int(row.settled_trades)}</td>"
            f"<td>{int(row.open_trades)}</td>"
            f"<td>{row.pnl_usd:.4f}</td>"
            "</tr>"
        )
        for row in daily.itertuples(index=False)
    )
    output_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Live PnL Summary</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 24px; background: #f5f1e8; color: #1e1d1a; }}
    table {{ border-collapse: collapse; width: 100%; background: #fffdf8; margin-bottom: 24px; }}
    th, td {{ border-bottom: 1px solid #ddd2c4; padding: 10px 8px; text-align: left; }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #6b665d; }}
  </style>
</head>
<body>
  <h1>Live PnL Summary</h1>
  <h2>Overview</h2>
  <table>
    <thead><tr><th>Metric</th><th>Value</th></tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>
  <h2>By Day</h2>
  <table>
    <thead>
      <tr>
        <th>Date</th>
        <th>Trades</th>
        <th>Settled</th>
        <th>Open</th>
        <th>PnL USD</th>
      </tr>
    </thead>
    <tbody>{daily_rows}</tbody>
  </table>
</body>
</html>""",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    log = pd.read_csv(args.log)
    log["pnl_usd"] = pd.to_numeric(log.get("pnl_usd"), errors="coerce")

    total_trades = len(log)
    settled_trades = int((log["status"] == "settled").sum()) if not log.empty else 0
    open_trades = int((log["status"] == "open").sum()) if not log.empty else 0
    total_pnl = float(log["pnl_usd"].fillna(0).sum()) if not log.empty else 0.0
    settled_pnl = float(log.loc[log["status"] == "settled", "pnl_usd"].fillna(0).sum()) if not log.empty else 0.0

    summary = pd.DataFrame(
        [
            {"metric": "total_trades", "value": total_trades},
            {"metric": "settled_trades", "value": settled_trades},
            {"metric": "open_trades", "value": open_trades},
            {"metric": "total_pnl_usd", "value": round(total_pnl, 6)},
            {"metric": "settled_pnl_usd", "value": round(settled_pnl, 6)},
        ]
    )

    if log.empty:
        daily = pd.DataFrame(columns=["market_date", "trades", "settled_trades", "open_trades", "pnl_usd"])
    else:
        daily = (
            log.groupby("market_date")
            .agg(
                trades=("market_date", "size"),
                settled_trades=("status", lambda s: (s == "settled").sum()),
                open_trades=("status", lambda s: (s == "open").sum()),
                pnl_usd=("pnl_usd", lambda s: s.fillna(0).sum()),
            )
            .reset_index()
            .sort_values("market_date")
        )

    output_path = Path(args.output)
    daily_output_path = Path(args.daily_output)
    html_output_path = Path(args.html_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_path, index=False)
    daily.to_csv(daily_output_path, index=False)
    render_html(summary, daily, html_output_path)
    print(f"Saved summary to {output_path}")
    print(f"Saved daily PnL to {daily_output_path}")
    print(f"Saved HTML summary to {html_output_path}")


if __name__ == "__main__":
    main()
