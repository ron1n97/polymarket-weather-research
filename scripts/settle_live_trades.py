#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Settle open trades in the live trade log from resolved Polymarket event pages.")
    parser.add_argument(
        "--log",
        default="outputs/paper/live_trade_log.csv",
        help="Live trade log CSV.",
    )
    return parser.parse_args()


def fetch_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=120) as response:
        return response.read().decode("utf-8")


def parse_event_payload(html_doc: str) -> dict:
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', html_doc)
    if not match:
        raise ValueError("Could not find __NEXT_DATA__.")
    payload = json.loads(match.group(1))
    event_slug = payload["query"]["slug"][0]
    queries = payload["props"]["pageProps"]["dehydratedState"]["queries"]
    for query in queries:
        candidate = query["state"].get("data")
        if isinstance(candidate, dict) and candidate.get("slug") == event_slug:
            return candidate
    raise ValueError("Could not parse event payload.")


def resolved_yes_from_market(market: dict) -> int | None:
    prices = market.get("outcomePrices") or []
    if len(prices) < 2:
        return None
    yes_price = float(prices[0])
    no_price = float(prices[1])
    if yes_price == 1.0 and no_price == 0.0:
        return 1
    if yes_price == 0.0 and no_price == 1.0:
        return 0
    return None


def pnl_for_row(side: str, stake_usd: float, resolved_yes: int, fill_yes_price: float | None = None) -> float | None:
    if fill_yes_price is None or pd.isna(fill_yes_price):
        return None
    fill_yes_price = float(fill_yes_price)
    if side == "bet yes":
        shares = stake_usd / fill_yes_price if fill_yes_price > 0 else 0.0
        return shares * (1.0 - fill_yes_price) if resolved_yes == 1 else -stake_usd
    if side == "bet no":
        no_price = 1.0 - fill_yes_price
        shares = stake_usd / no_price if no_price > 0 else 0.0
        return shares * fill_yes_price if resolved_yes == 0 else -stake_usd
    return None


def main() -> None:
    args = parse_args()
    log_path = Path(args.log)
    if not log_path.exists():
        print(f"Log not found: {log_path}")
        return

    log = pd.read_csv(log_path)
    if log.empty:
        print("Live log is empty.")
        return

    open_rows = log[log["status"] == "open"].copy()
    if open_rows.empty:
        print("No open trades to settle.")
        return

    event_cache: dict[str, dict] = {}
    settled = 0
    for idx, row in open_rows.iterrows():
        event_url = row.get("event_url")
        if not isinstance(event_url, str) or not event_url:
            continue
        if event_url not in event_cache:
            try:
                event_cache[event_url] = parse_event_payload(fetch_html(event_url))
            except Exception:
                continue
        event = event_cache[event_url]
        markets = event.get("markets") or []
        match = None
        for market in markets:
            label = market.get("groupItemTitle") or market.get("title") or ""
            if label == row["bucket_label"]:
                match = market
                break
        if match is None:
            continue
        resolved_yes = resolved_yes_from_market(match)
        if resolved_yes is None:
            continue

        log.loc[idx, "status"] = "settled"
        log.loc[idx, "settled_at_utc"] = pd.Timestamp.now("UTC").isoformat()
        log.loc[idx, "resolved_yes"] = resolved_yes
        pnl = pnl_for_row(row["side"], row["stake_usd"], resolved_yes, row.get("fill_yes_price"))
        if pnl is not None:
            log.loc[idx, "pnl_usd"] = round(pnl, 6)
        if pd.isna(log.loc[idx, "notes"]) or not str(log.loc[idx, "notes"]).strip():
            log.loc[idx, "notes"] = "Settled from Polymarket event page"
        else:
            log.loc[idx, "notes"] = str(log.loc[idx, "notes"]) + " | Settled from Polymarket event page"
        settled += 1

    log.to_csv(log_path, index=False)
    print(f"Settled {settled} trades in {log_path}")


if __name__ == "__main__":
    main()
