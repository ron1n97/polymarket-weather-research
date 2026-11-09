# Weather Prediction Trading Workflow

This repo contains research, backtests, and operational scripts for trading Polymarket weather markets.

The current live mode is:

- `paper + tiny live` in parallel
- live only on `tradable` cities
- current live size: `$1` per trade
- current default exit: hold to resolution


## Current Policy

Read these first:

- [live_policy_v1.md](/Users/ron1n97/projects/ml/weather-prediction/live_policy_v1.md)
- [strategy_v1.md](/Users/ron1n97/projects/ml/weather-prediction/strategy_v1.md)
- [city_whitelist_v1.md](/Users/ron1n97/projects/ml/weather-prediction/city_whitelist_v1.md)

Current whitelist:

- `tradable`: `Seoul`, `Paris`
- `experimental`: `Singapore`, `Shanghai`
- `avoid`: `Dallas`, `Tokyo`


## Main Outputs

Daily documents:

- [daily_signal_brief.html](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/daily_signal_brief.html)
- [paper_trading_dashboard.html](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/paper_trading_dashboard.html)
- [current_edge_table.html](/Users/ron1n97/projects/ml/weather-prediction/outputs/edges/current_edge_table.html)

Live tracking:

- [live_trade_log.csv](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/live_trade_log.csv)
- [live_pnl_summary.html](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/live_pnl_summary.html)
- [paper_session_log.csv](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/paper_session_log.csv)

Archives:

- [outputs/paper/archive](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/archive)
- [outputs/paper/latest](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/latest)


## Daily Workflow

### 1. Run Daily Paper Cycle

This refreshes the whole stack, archives the day, updates `latest`, and prints a short summary.

```bash
./.venv/bin/python scripts/run_paper_cycle.py --market-date 2026-04-08 --bankroll 50
```

If you want to rebuild from existing fetched data only:

```bash
./.venv/bin/python scripts/run_paper_cycle.py --market-date 2026-04-08 --bankroll 50 --skip-fetch
```


### 2. Read The Brief

Primary document:

- [daily_signal_brief.html](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/daily_signal_brief.html)

Interpretation:

- `trade`: allowed for live / tiny live
- `paper only`: observe, do not execute live
- `no trade`: ignore


### 3. Log New Live Trades

If you manually place trades from the brief, they should be present in:

- [live_trade_log.csv](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/live_trade_log.csv)

To append new `trade` rows from the brief automatically:

```bash
./.venv/bin/python scripts/append_live_trades_from_brief.py
```

This script deduplicates by:

- `market_date`
- `city`
- `bucket_label`
- `side`


### 4. Settle Open Trades

After markets resolve:

```bash
./.venv/bin/python scripts/settle_live_trades.py
./.venv/bin/python scripts/build_live_pnl_summary.py
```

Outputs:

- [live_pnl_summary.csv](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/live_pnl_summary.csv)
- [live_daily_pnl.csv](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/live_daily_pnl.csv)
- [live_pnl_summary.html](/Users/ron1n97/projects/ml/weather-prediction/outputs/paper/live_pnl_summary.html)


## Core Scripts

Pipeline:

- [scripts/run_daily_pipeline.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/run_daily_pipeline.py)
- [scripts/run_paper_cycle.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/run_paper_cycle.py)

Signal generation:

- [scripts/fetch_polymarket_weather_markets.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/fetch_polymarket_weather_markets.py)
- [scripts/fetch_current_forecast_snapshot.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/fetch_current_forecast_snapshot.py)
- [scripts/build_current_market_monitor.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/build_current_market_monitor.py)
- [scripts/calc_market_edge.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/calc_market_edge.py)
- [scripts/filter_trade_candidates.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/filter_trade_candidates.py)
- [scripts/build_paper_trading_dashboard.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/build_paper_trading_dashboard.py)
- [scripts/build_daily_signal_brief.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/build_daily_signal_brief.py)

Live tracking:

- [scripts/append_live_trades_from_brief.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/append_live_trades_from_brief.py)
- [scripts/settle_live_trades.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/settle_live_trades.py)
- [scripts/build_live_pnl_summary.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/build_live_pnl_summary.py)

Backtests and bankroll:

- [scripts/backtest_edge_strategy.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/backtest_edge_strategy.py)
- [scripts/simulate_bankroll.py](/Users/ron1n97/projects/ml/weather-prediction/scripts/simulate_bankroll.py)


## Important Notes

- Current practical live size is `$1` because minimum Polymarket stake is binding.
- At a `$50` bankroll, this is effectively `2%` per trade.
- Current live strategy is `NO-heavy`.
- Backtests and live logs are different layers; do not mix backtest PnL with live journal PnL.
