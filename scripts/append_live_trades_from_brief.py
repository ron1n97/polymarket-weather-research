#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


KEY_COLS = ["market_date", "city", "bucket_label", "side"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append current trade signals from the daily brief into the live trade log.")
    parser.add_argument(
        "--brief",
        default="outputs/paper/daily_signal_brief.csv",
        help="Daily signal brief CSV.",
    )
    parser.add_argument(
        "--log",
        default="outputs/paper/live_trade_log.csv",
        help="Live trade log CSV.",
    )
    parser.add_argument(
        "--source",
        default="brief_auto",
        help="Source label written to the log. Default: brief_auto",
    )
    parser.add_argument(
        "--status",
        default="open",
        help="Status written to appended rows. Default: open",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    brief = pd.read_csv(args.brief)
    candidates = brief[brief["signal"] == "trade"].copy()
    if candidates.empty:
        print("No trade rows found in brief.")
        return

    log_path = Path(args.log)
    if log_path.exists():
        log = pd.read_csv(log_path)
    else:
        log = pd.DataFrame(
            columns=[
                "logged_at_utc",
                "market_date",
                "city",
                "bucket_label",
                "side",
                "stake_usd",
                "fill_yes_price",
                "entry_rule",
                "event_url",
                "source",
                "status",
                "settled_at_utc",
                "resolved_yes",
                "pnl_usd",
                "notes",
            ]
        )

    existing = log[KEY_COLS].astype(str).agg("|".join, axis=1).tolist() if not log.empty else []
    candidates["composite_key"] = candidates[KEY_COLS].astype(str).agg("|".join, axis=1)
    new_rows = candidates[~candidates["composite_key"].isin(existing)].copy()

    if new_rows.empty:
        print("No new live trades to append.")
        return

    ts = pd.Timestamp.now("UTC").isoformat()
    append_df = pd.DataFrame(
        {
            "logged_at_utc": ts,
            "market_date": new_rows["market_date"],
            "city": new_rows["city"],
            "bucket_label": new_rows["bucket_label"],
            "side": new_rows["side"],
            "stake_usd": new_rows["paper_stake_usd"],
            "fill_yes_price": new_rows["yes_price"],
            "entry_rule": new_rows["entry_rule"],
            "event_url": new_rows.get("event_url", ""),
            "source": args.source,
            "status": args.status,
            "settled_at_utc": "",
            "resolved_yes": "",
            "pnl_usd": "",
            "notes": "Appended from daily_signal_brief trade rows",
        }
    )

    updated = pd.concat([log, append_df], ignore_index=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    updated.to_csv(log_path, index=False)
    print(f"Appended {len(append_df)} new trades to {log_path}")


if __name__ == "__main__":
    main()
