#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Filter current edge table into trade candidates.")
    parser.add_argument(
        "--input",
        default="outputs/edges/current_edge_table.csv",
        help="Current edge table CSV. Default: outputs/edges/current_edge_table.csv",
    )
    parser.add_argument(
        "--output",
        default="outputs/edges/trade_candidates.csv",
        help="Filtered trade candidates CSV. Default: outputs/edges/trade_candidates.csv",
    )
    parser.add_argument(
        "--html-output",
        default="outputs/edges/trade_candidates.html",
        help="Filtered trade candidates HTML. Default: outputs/edges/trade_candidates.html",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=40,
        help="Minimum center-bin historical sample. Default: 40",
    )
    parser.add_argument(
        "--min-edge-pp",
        type=float,
        default=8.0,
        help="Minimum absolute edge in percentage points. Default: 8.0",
    )
    parser.add_argument(
        "--max-yes-price",
        type=float,
        default=0.95,
        help="Drop near-certain yes buckets above this price. Default: 0.95",
    )
    return parser.parse_args()


def label_side(edge_pp: float) -> str:
    return "bet yes" if edge_pp > 0 else "bet no"


def render_html(df: pd.DataFrame, output_path: Path) -> None:
    rows = "\n".join(
        (
            "<tr>"
            f"<td>{row.city}</td>"
            f"<td>{row.bucket_label}</td>"
            f"<td>{row.forecast_max_c:.1f}</td>"
            f"<td>{row.rounded_center_bin_c}</td>"
            f"<td>{row.yes_price * 100:.1f}%</td>"
            f"<td>{row.fair_probability * 100:.1f}%</td>"
            f"<td>{row.edge_pp:+.1f}pp</td>"
            f"<td>{int(row.center_sample_days)}</td>"
            f"<td>{row.side}</td>"
            "</tr>"
        )
        for row in df.itertuples(index=False)
    )

    output_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Trade Candidates</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 24px; background: #f5f1e8; color: #1e1d1a; }}
    table {{ border-collapse: collapse; width: 100%; background: #fffdf8; }}
    th, td {{ border-bottom: 1px solid #ddd2c4; padding: 10px 8px; text-align: left; }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #6b665d; }}
  </style>
</head>
<body>
  <h1>Trade Candidates</h1>
  <p>Filtered bucket-level candidates after edge and sample thresholds.</p>
  <table>
    <thead>
      <tr>
        <th>City</th>
        <th>Bucket</th>
        <th>Forecast Max</th>
        <th>Center Bin</th>
        <th>Market</th>
        <th>Fair</th>
        <th>Edge</th>
        <th>Samples</th>
        <th>Side</th>
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
    df = pd.read_csv(args.input)
    df["yes_price"] = pd.to_numeric(df["yes_price"], errors="coerce")
    df["fair_probability"] = pd.to_numeric(df["fair_probability"], errors="coerce")
    df["edge_pp"] = pd.to_numeric(df["edge_pp"], errors="coerce")
    df["center_sample_days"] = pd.to_numeric(df["center_sample_days"], errors="coerce")
    df["forecast_max_c"] = pd.to_numeric(df["forecast_max_c"], errors="coerce")

    filtered = df[
        df["fair_probability"].notna()
        & (df["center_sample_days"] >= args.min_samples)
        & (df["edge_pp"].abs() >= args.min_edge_pp)
        & (df["yes_price"] <= args.max_yes_price)
    ].copy()
    filtered["side"] = filtered["edge_pp"].apply(label_side)
    filtered = filtered.sort_values(["edge_pp", "center_sample_days"], ascending=[False, False]).reset_index(drop=True)

    output_path = Path(args.output)
    html_output_path = Path(args.html_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(output_path, index=False)
    render_html(filtered, html_output_path)

    print(filtered.to_string(index=False))
    print(f"\nSaved candidates to {output_path}")
    print(f"Saved HTML candidates to {html_output_path}")


if __name__ == "__main__":
    main()
