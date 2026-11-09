#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a paper trading dashboard from current edge table and whitelist.")
    parser.add_argument(
        "--edges",
        default="outputs/edges/current_edge_table.csv",
        help="Current edge table CSV.",
    )
    parser.add_argument(
        "--monitor",
        default="outputs/market_monitor/current_market_monitor.csv",
        help="Current market monitor CSV.",
    )
    parser.add_argument(
        "--whitelist",
        default="outputs/strategy/city_whitelist_v1.csv",
        help="City whitelist CSV.",
    )
    parser.add_argument(
        "--bankroll-rec",
        default="outputs/bankroll/non_legacy_v2_mid_capped/bankroll_recommendation.csv",
        help="Recommended bankroll sizing CSV.",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=50.0,
        help="Current bankroll in USD.",
    )
    parser.add_argument(
        "--min-stake",
        type=float,
        default=1.0,
        help="Minimum real stake size in USD. Default: 1.0",
    )
    parser.add_argument(
        "--output",
        default="outputs/paper/paper_trading_dashboard.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--html-output",
        default="outputs/paper/paper_trading_dashboard.html",
        help="Output HTML path.",
    )
    return parser.parse_args()


def tier_threshold(tier: str) -> float:
    if tier == "tradable":
        return 6.0
    if tier == "experimental":
        return 10.0
    return 1e9


def entry_buffer_pp(tier: str) -> float:
    if tier == "tradable":
        return 2.0
    if tier == "experimental":
        return 3.0
    return 0.0


def classify_signal(row: pd.Series) -> str:
    if row["tier"] == "avoid":
        return "no trade"
    if pd.isna(row["fair_probability"]) or pd.isna(row["yes_price"]) or pd.isna(row["edge_pp"]):
        return "no trade"
    if row["abs_edge_pp"] < row["required_edge_pp"]:
        return "no trade"
    if row["tier"] == "tradable":
        return "trade"
    return "paper only"


def side_from_edge(edge_pp: float) -> str:
    if edge_pp >= 0:
        return "bet yes"
    return "bet no"


def entry_trigger(row: pd.Series) -> str:
    if row["signal"] == "no trade":
        return "n/a"
    if row["side"] == "bet yes":
        return f"buy YES <= {row['max_yes_entry_price'] * 100:.1f}%"
    return f"buy NO when YES >= {row['min_yes_entry_price'] * 100:.1f}%"


def selection_rank(df: pd.DataFrame) -> pd.DataFrame:
    selected_parts: list[pd.DataFrame] = []
    for _, day_frame in df.groupby("market_date", sort=True):
        ranked = day_frame.sort_values(["signal_priority", "abs_edge_pp", "volume_usd"], ascending=[True, False, False])
        ranked = ranked.groupby("city", group_keys=False).head(2)
        selected_parts.append(ranked.head(6))
    selected = pd.concat(selected_parts, ignore_index=True) if selected_parts else df.iloc[0:0].copy()
    selected["selected_for_sheet"] = True
    return selected[["city", "market_date", "bucket_label", "selected_for_sheet"]]


def render_html(df: pd.DataFrame, output_path: Path, bankroll: float, bankroll_fraction: float) -> None:
    ordered = df.sort_values(["signal_priority", "abs_edge_pp", "volume_usd"], ascending=[True, False, False])
    rows = "\n".join(
        (
            "<tr>"
            f"<td>{row.signal}</td>"
            f"<td>{row.city}</td>"
            f"<td>{row.market_date}</td>"
            f"<td>{row.bucket_label}</td>"
            f"<td>{row.side}</td>"
            f"<td>{row.tier}</td>"
            f"<td>{row.yes_price * 100:.1f}%</td>"
            f"<td>{row.fair_probability * 100:.1f}%</td>"
            f"<td>{row.edge_pp:+.1f}pp</td>"
            f"<td>{row.entry_rule}</td>"
            f"<td>${row.paper_stake_usd:.2f}</td>"
            f"<td>{'min $1' if row.min_bet_binding else 'fractional'}</td>"
            f"<td>{row.volume_usd:,.0f}</td>"
            f"<td><a href='{row.event_url}'>market</a></td>"
            "</tr>"
        )
        for row in ordered.itertuples(index=False)
    )
    output_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Paper Trading Dashboard</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 24px; background: #f5f1e8; color: #1e1d1a; }}
    table {{ border-collapse: collapse; width: 100%; background: #fffdf8; }}
    th, td {{ border-bottom: 1px solid #ddd2c4; padding: 10px 8px; text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #6b665d; }}
  </style>
</head>
<body>
  <h1>Paper Trading Dashboard</h1>
  <p>Bankroll: <strong>${bankroll:.2f}</strong>. Suggested fraction: <strong>{bankroll_fraction * 100:.2f}%</strong> per trade.</p>
  <p>This sheet applies the current whitelist, edge thresholds, and daily selection caps.</p>
  <table>
    <thead>
      <tr>
        <th>Signal</th>
        <th>City</th>
        <th>Date</th>
        <th>Bucket</th>
        <th>Side</th>
        <th>Tier</th>
        <th>Market</th>
        <th>Fair</th>
        <th>Edge</th>
        <th>Entry Rule</th>
        <th>Stake</th>
        <th>Sizing</th>
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
    edges = pd.read_csv(args.edges)
    monitor = pd.read_csv(args.monitor)
    whitelist = pd.read_csv(args.whitelist)
    bankroll_rec = pd.read_csv(args.bankroll_rec).iloc[0]
    bankroll_fraction = float(bankroll_rec["fraction"])

    monitor_cols = ["city", "market_date", "bucket_label", "event_url", "volume_usd", "bucket_role"]
    merged = edges.merge(monitor[monitor_cols], on=["city", "market_date", "bucket_label"], how="left")
    merged = merged.merge(whitelist[["city", "tier", "note"]], on="city", how="left")
    merged["tier"] = merged["tier"].fillna("avoid")
    merged["note"] = merged["note"].fillna("not in whitelist")
    merged["yes_price"] = pd.to_numeric(merged["yes_price"], errors="coerce")
    merged["fair_probability"] = pd.to_numeric(merged["fair_probability"], errors="coerce")
    merged["edge_pp"] = pd.to_numeric(merged["edge_pp"], errors="coerce")
    merged["volume_usd"] = pd.to_numeric(merged["volume_usd"], errors="coerce").fillna(0.0)
    merged["abs_edge_pp"] = merged["edge_pp"].abs()
    merged["required_edge_pp"] = merged["tier"].map(tier_threshold)
    merged["buffer_pp"] = merged["tier"].map(entry_buffer_pp)
    merged["side"] = merged["edge_pp"].apply(side_from_edge)
    merged["signal"] = merged.apply(classify_signal, axis=1)
    merged["signal_priority"] = merged["signal"].map({"trade": 0, "paper only": 1, "no trade": 2}).fillna(9)
    merged["max_yes_entry_price"] = ((merged["fair_probability"] * 100 - merged["buffer_pp"]).clip(lower=0) / 100)
    merged["min_yes_entry_price"] = ((merged["fair_probability"] * 100 + merged["buffer_pp"]).clip(upper=100) / 100)
    merged["entry_rule"] = merged.apply(entry_trigger, axis=1)
    merged["target_stake_usd"] = args.bankroll * bankroll_fraction
    merged["paper_stake_usd"] = merged["target_stake_usd"].clip(lower=args.min_stake)
    merged["min_bet_binding"] = merged["paper_stake_usd"] > merged["target_stake_usd"]
    merged["effective_fraction_pct"] = (merged["paper_stake_usd"] / args.bankroll) * 100

    selected = selection_rank(merged[merged["signal"].isin(["trade", "paper only"])].copy())
    merged = merged.merge(selected, on=["city", "market_date", "bucket_label"], how="left")
    merged["selected_for_sheet"] = merged["selected_for_sheet"].fillna(False)
    merged["signal"] = merged.apply(
        lambda row: row["signal"] if row["selected_for_sheet"] or row["signal"] == "no trade" else "no trade",
        axis=1,
    )
    merged["signal_priority"] = merged["signal"].map({"trade": 0, "paper only": 1, "no trade": 2}).fillna(9)

    result = merged.sort_values(["signal_priority", "abs_edge_pp", "volume_usd"], ascending=[True, False, False]).copy()

    output_path = Path(args.output)
    html_output_path = Path(args.html_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    render_html(result, html_output_path, args.bankroll, bankroll_fraction)
    print(f"Saved paper dashboard to {output_path}")
    print(f"Saved HTML dashboard to {html_output_path}")


if __name__ == "__main__":
    main()
