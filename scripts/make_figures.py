#!/usr/bin/env python3
"""Regenerate research-note figures from sanitized results/ CSVs."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
FIG = ROOT / "figures"

WHITELIST = {
    "Seoul": "tradable",
    "Paris": "tradable",
    "Singapore": "experimental",
    "Shanghai": "experimental",
    "Dallas": "avoid",
    "Tokyo": "avoid",
}
COLORS = {"tradable": "#2e7d32", "experimental": "#f9a825", "avoid": "#c0392b"}


def style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
        }
    )


def city_edge() -> None:
    df = pd.read_csv(RES / "backtest_by_city_v2_mid.csv").sort_values("avg_pnl_per_share")
    colors = [COLORS[WHITELIST.get(c, "experimental")] for c in df["city"]]
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.barh(df["city"], df["avg_pnl_per_share"], color=colors)
    ax.axvline(0, color="#333", lw=0.8)
    ax.set_xlabel("Avg PnL per share")
    ax.set_title("Edge backtest by city (non-legacy v2 mid filter)")
    for tier, color in COLORS.items():
        ax.plot([], [], color=color, lw=6, label=tier)
    ax.legend(loc="lower right", fontsize=8)
    for y, row in enumerate(df.itertuples()):
        ax.text(
            row.avg_pnl_per_share + 0.001,
            y,
            f"n={row.trades}  WR={row.win_rate:.0%}",
            va="center",
            fontsize=8,
        )
    fig.tight_layout()
    fig.savefig(FIG / "city_avg_pnl.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def side_split() -> None:
    df = pd.read_csv(RES / "backtest_by_side_v2_mid.csv")
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.6))
    labels = df["action"].str.replace("bet ", "", regex=False).str.upper()
    axes[0].bar(labels, df["win_rate"], color=["#4c78a8", "#f58518"])
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Hit rate (PnL > 0)")
    axes[0].set_title("Hit rate by side")
    for i, row in enumerate(df.itertuples()):
        axes[0].text(i, row.win_rate + 0.02, f"{row.win_rate:.1%}\nn={row.trades}", ha="center", fontsize=8)

    axes[1].bar(labels, df["avg_pnl_per_share"], color=["#4c78a8", "#f58518"])
    axes[1].axhline(0, color="#333", lw=0.8)
    axes[1].set_ylabel("Avg PnL / share")
    axes[1].set_title("Avg edge by side")
    for i, row in enumerate(df.itertuples()):
        axes[1].text(i, row.avg_pnl_per_share + 0.002, f"{row.avg_pnl_per_share:+.3f}", ha="center", fontsize=8)
    fig.suptitle("NO carries the book — YES is sparse / low hit-rate", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "side_split.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def cumulative() -> None:
    df = pd.read_csv(RES / "backtest_daily_pnl_v2_mid.csv", parse_dates=["market_date"])
    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    ax.plot(df["market_date"], df["cum_pnl_per_share"], color="#1f4e79", lw=1.8)
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_title("Backtest cumulative PnL per share (not live)")
    ax.set_ylabel("Cumulative PnL / share")
    ax.set_xlabel("Market date")
    summary = pd.read_csv(RES / "backtest_summary_v2_mid.csv").iloc[0]
    ax.text(
        0.02,
        0.98,
        f"trades={int(summary.trades)}  WR={summary.win_rate:.1%}  "
        f"avg={summary.avg_pnl_per_share:+.3f}  total={summary.total_pnl_per_share:+.1f}",
        transform=ax.transAxes,
        va="top",
        fontsize=8,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.85, ec="#ccc"),
    )
    fig.tight_layout()
    fig.savefig(FIG / "cum_pnl.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def day4_bins() -> None:
    df = pd.read_csv(RES / "day4_three_bin_summary.csv").sort_values("exact_bin_prob")
    x = np.arange(len(df))
    w = 0.35
    fig, ax = plt.subplots(figsize=(8.2, 4.0))
    ax.bar(x - w / 2, df["exact_bin_prob"], w, label="Exact rounded bin", color="#4c78a8")
    ax.bar(x + w / 2, df["three_bin_prob"], w, label="±1°C three-bin window", color="#f58518")
    ax.set_xticks(x)
    ax.set_xticklabels(df["city"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Historical hit rate")
    ax.set_ylim(0, 1)
    ax.set_title("Day+4 forecast: exact bin is weak; 3-bin is better — still not a free YES")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "day4_exact_vs_three_bin.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def asia_deadline() -> None:
    df = pd.read_csv(RES / "baseline_deadline_summary.csv").sort_values("baseline_rounded_win_rate")
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    colors = ["#2e7d32" if r > 0.9 else "#f9a825" if r > 0.25 else "#c0392b" for r in df["baseline_rounded_win_rate"]]
    ax.barh(df["city"], df["baseline_rounded_win_rate"], color=colors)
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("P(already know day's max by 12:00 UTC deadline)")
    ax.set_title("Information asymmetry at shared 12:00 UTC deadline")
    for y, row in enumerate(df.itertuples()):
        ax.text(min(row.baseline_rounded_win_rate + 0.01, 0.92), y, row.deadline_hour_local, va="center", fontsize=7)
    fig.tight_layout()
    fig.savefig(FIG / "deadline_info_asymmetry.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def bankroll_frontier() -> None:
    df = pd.read_csv(RES / "bankroll_summary_v2_mid.csv")
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.plot(df["max_drawdown_pct"], df["return_pct"], "o-", color="#1f4e79")
    for _, row in df.iterrows():
        ax.annotate(
            f"{row.fraction:.1%}",
            (row.max_drawdown_pct, row.return_pct),
            textcoords="offset points",
            xytext=(4, 2),
            fontsize=7,
        )
    ax.set_xlabel("Max drawdown % (sim)")
    ax.set_ylabel("Return % (sim)")
    ax.set_title("Bankroll sim frontier — backtest proxy, not live proof")
    fig.tight_layout()
    fig.savefig(FIG / "bankroll_frontier.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def thesis() -> None:
    steps = [
        ("Naive YES\non forecast bin", "weak / neg", "#bdbdbd"),
        ("Day+4\nselective NO", "sparse", "#4c78a8"),
        ("Fair vs market\nedge filter", "core", "#1f4e79"),
        ("Same-day Asia\ninfo edge", "strongest", "#2e7d32"),
        ("Tiny live\n$1 / trade", "n≈4 open", "#f9a825"),
    ]
    fig, ax = plt.subplots(figsize=(8.2, 2.6))
    ax.set_xlim(0, len(steps) + 0.2)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("Working thesis — mispricing filter, not temperature oracle", loc="left")
    for i, (title, note, color) in enumerate(steps):
        x = i + 0.5
        ax.add_patch(plt.Rectangle((x - 0.38, 0.3), 0.76, 0.42, facecolor=color, ec="none", alpha=0.9))
        ax.text(x, 0.51, title, ha="center", va="center", color="white", fontsize=8, fontweight="bold")
        ax.text(x, 0.16, note, ha="center", fontsize=8, color="#333")
        if i < len(steps) - 1:
            ax.annotate("", xy=(x + 0.55, 0.51), xytext=(x + 0.42, 0.51), arrowprops=dict(arrowstyle="->", color="#666"))
    fig.tight_layout()
    fig.savefig(FIG / "research_path.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    style()
    city_edge()
    side_split()
    cumulative()
    day4_bins()
    asia_deadline()
    bankroll_frontier()
    thesis()
    print(f"Wrote figures to {FIG}")


if __name__ == "__main__":
    main()
