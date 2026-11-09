#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one automated paper-trading cycle and archive outputs.")
    parser.add_argument(
        "--market-date",
        default=date.today().strftime("%Y-%m-%d"),
        help="Target market date in YYYY-MM-DD. Default: today.",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=50.0,
        help="Paper bankroll in USD. Default: 50.",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip live fetch steps and rebuild from existing local artifacts.",
    )
    return parser.parse_args()


def run_pipeline(market_date: str, bankroll: float, skip_fetch: bool) -> None:
    cmd = [PYTHON, "scripts/run_daily_pipeline.py", "--market-date", market_date, "--bankroll", f"{bankroll:.2f}"]
    if skip_fetch:
        cmd.append("--skip-fetch")
    subprocess.run(cmd, cwd=ROOT, check=True)


def archive_outputs(market_date: str) -> Path:
    archive_dir = ROOT / "outputs" / "paper" / "archive" / market_date
    archive_dir.mkdir(parents=True, exist_ok=True)

    copies = [
        ("outputs/paper/paper_trading_dashboard.csv", "paper_trading_dashboard.csv"),
        ("outputs/paper/paper_trading_dashboard.html", "paper_trading_dashboard.html"),
        ("outputs/paper/daily_signal_brief.csv", "daily_signal_brief.csv"),
        ("outputs/paper/daily_signal_brief.html", "daily_signal_brief.html"),
        ("outputs/edges/current_edge_table.csv", "current_edge_table.csv"),
        ("outputs/edges/current_edge_table.html", "current_edge_table.html"),
        ("outputs/edges/trade_candidates.csv", "trade_candidates.csv"),
        ("outputs/edges/trade_candidates.html", "trade_candidates.html"),
    ]

    for src_rel, dst_name in copies:
        src = ROOT / src_rel
        if src.exists():
            shutil.copy2(src, archive_dir / dst_name)

    return archive_dir


def update_latest_snapshot(archive_dir: Path) -> Path:
    latest_dir = ROOT / "outputs" / "paper" / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    for child in latest_dir.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink()
    for src in archive_dir.iterdir():
        if src.is_file():
            shutil.copy2(src, latest_dir / src.name)
    return latest_dir


def append_session_log(market_date: str, bankroll: float, archive_dir: Path) -> Path:
    brief_path = ROOT / "outputs" / "paper" / "daily_signal_brief.csv"
    dashboard_path = ROOT / "outputs" / "paper" / "paper_trading_dashboard.csv"

    brief = pd.read_csv(brief_path)
    dashboard = pd.read_csv(dashboard_path)
    trades = brief[brief["signal"] == "trade"].copy()
    paper_only = brief[brief["signal"] == "paper only"].copy()

    live_risk_used = float(trades["paper_stake_usd"].sum()) if not trades.empty else 0.0
    paper_risk_used = float(paper_only["paper_stake_usd"].sum()) if not paper_only.empty else 0.0
    max_abs_edge = float(dashboard["edge_pp"].abs().max()) if not dashboard.empty else 0.0

    row = {
        "run_timestamp_utc": pd.Timestamp.utcnow().isoformat(),
        "market_date": market_date,
        "bankroll_usd": bankroll,
        "trade_count": int((brief["signal"] == "trade").sum()),
        "paper_only_count": int((brief["signal"] == "paper only").sum()),
        "live_risk_used_usd": round(live_risk_used, 4),
        "paper_risk_used_usd": round(paper_risk_used, 4),
        "top_abs_edge_pp": round(max_abs_edge, 4),
        "archive_dir": str(archive_dir),
    }

    log_path = ROOT / "outputs" / "paper" / "paper_session_log.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exists = log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)
    return log_path


def print_terminal_summary() -> None:
    brief_path = ROOT / "outputs" / "paper" / "daily_signal_brief.csv"
    if not brief_path.exists():
        return
    brief = pd.read_csv(brief_path)
    actionable = brief[brief["signal"].isin(["trade", "paper only"])].copy()
    live = actionable[actionable["signal"] == "trade"].copy()
    paper = actionable[actionable["signal"] == "paper only"].copy()

    print()
    print("[paper] summary")
    print(f"  live trades: {len(live)}")
    print(f"  paper-only: {len(paper)}")
    if not live.empty:
        for row in live.itertuples(index=False):
            print(
                f"  LIVE  {row.city:10} | {row.bucket_label:16} | {row.side:7} | "
                f"edge {row.edge_pp:+.1f}pp | {row.entry_rule}"
            )
    if not paper.empty:
        for row in paper.itertuples(index=False):
            print(
                f"  PAPER {row.city:10} | {row.bucket_label:16} | {row.side:7} | "
                f"edge {row.edge_pp:+.1f}pp | {row.entry_rule}"
            )


def main() -> None:
    args = parse_args()
    run_pipeline(args.market_date, args.bankroll, args.skip_fetch)
    archive_dir = archive_outputs(args.market_date)
    latest_dir = update_latest_snapshot(archive_dir)
    log_path = append_session_log(args.market_date, args.bankroll, archive_dir)
    print_terminal_summary()

    print("[run_paper_cycle] done")
    print(f"[run_paper_cycle] archive: {archive_dir}")
    print(f"[run_paper_cycle] latest: {latest_dir}")
    print(f"[run_paper_cycle] session log: {log_path}")


if __name__ == "__main__":
    main()
