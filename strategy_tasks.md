# Strategy Tasks

## Goal

Turn the current research into a usable trading pipeline for Polymarket weather markets.


## Phase 1: Market Monitor

### 1. Current Market Snapshot

Build a stable collector for currently open Polymarket weather markets.

Create:

- `scripts/fetch_polymarket_weather_markets.py`

Output:

- `outputs/polymarket/current_weather_markets.csv`

Fields:

- city
- market date
- event slug
- bucket label
- yes price
- implied probability
- volume
- liquidity if available
- spread if available
- resolution source

### 2. Forecast Snapshot

Build a script that pulls current forecast max data for all tracked cities.

Create:

- `scripts/fetch_current_forecast_snapshot.py`

Output:

- `outputs/forecast/current_forecast_snapshot.csv`

Fields:

- city
- forecast date
- source
- forecast max
- forecast min
- precipitation
- weather code
- rounded center bin

### 3. Daily Join Report

Join current forecast and current market prices.

Create:

- `scripts/build_current_market_monitor.py`

Output:

- `outputs/market_monitor/current_market_monitor.csv`
- `outputs/market_monitor/current_market_monitor.html`

Purpose:

- one place to inspect current bins and prices
- no modeling yet


## Phase 2: Fair Value Model

### 4. Exact-Bin Historical Fair Table

We already have:

- `day+4` exact hit
- `3-bin`
- `5-bin`

Now build exact bucket-level historical fair values.

Create:

- `scripts/build_day4_exact_bin_fair_table.py`

Output:

- `outputs/fair_value/day4_exact_bin_fair.csv`

Fields:

- city
- forecast center bin
- actual bin
- probability
- sample days

### 5. Bucket Translator

Convert exact-bin distribution into Polymarket bucket probabilities.

Create:

- `scripts/translate_distribution_to_polymarket_buckets.py`

Input:

- exact-bin distribution
- current bucket structure

Output:

- bucket fair probabilities

### 6. Edge Calculator

Compare fair probabilities to market prices.

Create:

- `scripts/calc_market_edge.py`

Output:

- `outputs/edges/current_edge_table.csv`
- `outputs/edges/current_edge_table.html`

Fields:

- city
- market date
- bucket
- market implied probability
- fair probability
- raw edge
- edge after penalty
- recommended side


## Phase 3: Trade Filters

### 7. Tradeability Filter

Add hard filters for invalid trades.

Create:

- `scripts/filter_trade_candidates.py`

Rules:

- minimum historical sample
- minimum liquidity
- maximum spread
- minimum edge
- bucket consistency
- source agreement

Output:

- `outputs/edges/trade_candidates.csv`

### 8. Decision Labels

Label each candidate:

- `bet yes`
- `bet no`
- `no trade`

Create:

- `scripts/label_trade_decisions.py`


## Phase 4: Multi-Source Forecasting

### 9. Forecast Ensemble Collector

Do not rely on one source only.

Create:

- `scripts/fetch_forecast_ensemble.py`

Desired sources:

- Open-Meteo
- TWC / Weather.com if feasible
- other stable public or semi-public sources if feasible

Output:

- `outputs/forecast/forecast_ensemble.csv`

### 10. Ensemble Calibration

Build a model that produces fair exact-bin probabilities from multiple forecasts.

Create:

- `scripts/train_day4_bin_distribution_model.py`

Output:

- calibrated fair distribution over bins


## Phase 5: Same-Day Asia Edge

### 11. Intraday Asia Monitor

Build a same-day market monitor for `UTC+8/+9` cities before `12:00 UTC`.

Create:

- `scripts/build_asia_same_day_monitor.py`

Input:

- current market prices
- latest hourly observations
- current max
- historical lock-in curves

Output:

- `outputs/same_day_asia/asia_same_day_monitor.csv`
- `outputs/same_day_asia/asia_same_day_monitor.html`

### 12. Same-Day Decision Engine

This should become the highest-priority signal layer.

Create:

- `scripts/run_asia_same_day_signals.py`


## Phase 6: Backtesting

### 13. Historical Edge Backtest

Backtest whether edges would have paid off after market resolution.

Create:

- `scripts/backtest_edge_strategy.py`

Output:

- win rate
- average EV
- realized PnL proxy
- by city
- by regime

### 14. Regime Report

Summarize performance by:

- `day+4`
- `day+2`
- `same-day Asia`

Create:

- `scripts/render_strategy_backtest_report.py`


## Recommended Order

Implement in this order:

1. `fetch_polymarket_weather_markets.py`
2. `fetch_current_forecast_snapshot.py`
3. `build_current_market_monitor.py`
4. `build_day4_exact_bin_fair_table.py`
5. `translate_distribution_to_polymarket_buckets.py`
6. `calc_market_edge.py`
7. `filter_trade_candidates.py`
8. `backtest_edge_strategy.py`
9. `fetch_forecast_ensemble.py`
10. `build_asia_same_day_monitor.py`


## Minimum Viable Trading Pipeline

The first usable version only needs:

- current market fetch
- current forecast fetch
- fair probability table
- edge calculator
- trade filter

That is enough to produce a daily shortlist of:

- tradable
- overpriced
- underpriced
- skip


## Most Important Unknowns

These need validation early:

- how reliable the Polymarket parser is
- whether bucket structures vary often
- whether multiple forecast sources materially improve calibration
- whether `NO` trades really dominate on `day+4`
- whether same-day Asia dominates total expected alpha


## Immediate Next Step

Start Phase 1 with:

- `fetch_polymarket_weather_markets.py`
- `fetch_current_forecast_snapshot.py`
- `build_current_market_monitor.py`
