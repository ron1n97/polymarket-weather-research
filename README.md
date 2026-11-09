# Polymarket Weather Research

[![Research Note PDF](https://img.shields.io/badge/Research%20Note-PDF-red?style=for-the-badge&logo=adobeacrobatreader&logoColor=white)](docs/pdf/research_note.pdf)
[![Markdown](https://img.shields.io/badge/Research%20Note-Markdown-blue?style=for-the-badge)](docs/research_note.md)

Honest research notes and code from building a **selective edge** system on [Polymarket](https://polymarket.com) daily max-temperature markets — not a “always buy the forecast bin” bot.

This is a **curated public extract**, not a dump of the private lab.

**Bottom line (selected backtest `non_legacy_v2_mid`):** **1,123** trades · **52.5%** hit-rate · **+0.026** avg PnL/share · **NO-heavy** book. Live = paper + **$1** tiny-live on **Seoul / Paris** only; at write-up time **0 settled** live trades — not live alpha.

Start here: **[open the PDF](docs/pdf/research_note.pdf)** · or the [Markdown note](docs/research_note.md).

---

## Why this repo exists

Prediction-market / quant screens reward:

1. Venue microstructure thinking (buckets, deadline, ask/edge)
2. Regime separation (day+4 vs same-day Asia)
3. Documented filters and negative results
4. Clear split between backtest, paper, and live

---

## Current policy (short)

| Tier | Cities |
|---|---|
| Tradable (tiny live) | Seoul, Paris |
| Experimental | Singapore, Shanghai |
| Avoid / deprioritize | Dallas, Tokyo |

Details: [`live_policy_v1.md`](live_policy_v1.md) · [`strategy_v1.md`](strategy_v1.md) · [`city_whitelist_v1.md`](city_whitelist_v1.md)

---

## Repository layout

```
docs/
  research_note.md          # main write-up
  pdf/research_note.pdf     # PDF with figures
results/                    # sanitized summary CSVs (for figures)
figures/                    # regenerated plots
scripts/                    # paper cycle, edge backtest, monitors
strategy_v1.md              # full strategy thesis
live_policy_v1.md           # live / paper rules
city_whitelist_v1.md        # city tiers from backtest
markets_research.md         # venue / timezone notes
```

**Not** included: raw `data/`, full `outputs/` archives, `.env`, wallet keys, live order plumbing secrets.

---

## Key findings (short)

- Day+4 **exact-bin** forecast hit rates are too weak for naive YES; 3-bin windows look better but crowd already prices the center.
- Shared **12:00 UTC** deadline creates real **Asia same-day** information advantage.
- Selected edge backtest is profitable on paper metrics, driven by **NO**; YES stays sparse.
- Whitelist prefers sample + stability (Seoul/Paris) over peak avg (Singapore).

---

## Quick start (figures)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/make_figures.py
```

## Daily paper cycle (local lab)

Needs network + local caches under `data/` / `outputs/` (gitignored):

```bash
python scripts/run_paper_cycle.py --market-date YYYY-MM-DD --bankroll 50
```

Primary brief: `outputs/paper/daily_signal_brief.html` (local).

---

## Related public work

- [polymarket-btc-5m-research](https://github.com/ron1n97/polymarket-btc-5m-research) — BTC 5m direction vs Polymarket economics  
- [f1-pitstop-prediction](https://github.com/ron1n97/f1-pitstop-prediction) — Kaggle PS S6E5 (top 18.8%)
