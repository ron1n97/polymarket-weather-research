#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import pandas as pd


INPUT = Path("outputs/backtest_edge_strategy_non_legacy_v2_mid/backtest_trades.csv")
OUTPUT_CSV = Path("outputs/strategy/city_whitelist_v1.csv")
OUTPUT_MD = Path("city_whitelist_v1.md")


def classify(row: pd.Series) -> str:
    if row["trades"] >= 200 and row["avg_pnl_per_share"] >= 0.025 and row["stability_score"] >= 0.07:
        return "tradable"
    if row["trades"] >= 50 and row["avg_pnl_per_share"] >= 0.015 and row["stability_score"] >= 0.05:
        return "experimental"
    return "avoid"


def note(row: pd.Series) -> str:
    if row["tier"] == "tradable":
        return "usable now"
    if row["tier"] == "experimental":
        return "positive but still thin or less stable"
    return "do not prioritize"


def main() -> None:
    trades = pd.read_csv(INPUT)
    summary = (
        trades.groupby("city")
        .agg(
            trades=("city", "size"),
            avg_pnl_per_share=("pnl_per_share", "mean"),
            total_pnl=("pnl_per_share", "sum"),
            pnl_std=("pnl_per_share", "std"),
            positive_share=("pnl_per_share", lambda s: (s > 0).mean()),
        )
        .reset_index()
    )
    summary["stability_score"] = summary["avg_pnl_per_share"] / summary["pnl_std"]
    summary["tier"] = summary.apply(classify, axis=1)
    summary["note"] = summary.apply(note, axis=1)
    summary = summary.sort_values(["tier", "total_pnl"], ascending=[True, False])

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT_CSV, index=False)

    tradable = summary[summary["tier"] == "tradable"]
    experimental = summary[summary["tier"] == "experimental"]
    avoid = summary[summary["tier"] == "avoid"]

    lines = [
        "# City Whitelist V1",
        "",
        "Built from `outputs/backtest_edge_strategy_non_legacy_v2_mid/backtest_trades.csv`.",
        "",
        "## Tradable",
        "",
    ]
    for row in tradable.itertuples(index=False):
        lines.append(
            f"- {row.city}: trades={row.trades}, avg_pnl/share={row.avg_pnl_per_share:.4f}, "
            f"stability={row.stability_score:.4f}, note={row.note}"
        )
    lines.extend(["", "## Experimental", ""])
    for row in experimental.itertuples(index=False):
        lines.append(
            f"- {row.city}: trades={row.trades}, avg_pnl/share={row.avg_pnl_per_share:.4f}, "
            f"stability={row.stability_score:.4f}, note={row.note}"
        )
    lines.extend(["", "## Avoid", ""])
    for row in avoid.itertuples(index=False):
        lines.append(
            f"- {row.city}: trades={row.trades}, avg_pnl/share={row.avg_pnl_per_share:.4f}, "
            f"stability={row.stability_score:.4f}, note={row.note}"
        )

    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved {OUTPUT_CSV}")
    print(f"Saved {OUTPUT_MD}")


if __name__ == "__main__":
    main()
