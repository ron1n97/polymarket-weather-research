# Weather Trading Strategy V1

## Objective

Build a weather-market strategy that trades only when market-implied probabilities differ materially from our fair value.

The strategy is not:

- "predict the exact temperature"
- "always buy the center bin"
- "always buy the 3-bin window around the forecast"

The strategy is:

- estimate `fair_prob`
- compare it to `market_implied_prob`
- trade only when `edge` is large enough after model risk, spread, liquidity, and calibration penalties

Formula:

`edge = fair_prob - market_implied_prob`


## Core Thesis

There are three different alpha regimes, and they should not be mixed into one rule set.

### 1. Day+4 Selective

Use archived weather forecasts and market prices.

Properties:

- low confidence
- sparse valid edges
- mostly useful for finding overpriced crowd consensus

Default posture:

- mostly `NO`
- small size
- many `no trade`

### 2. Day+1 / Day+2

This is the intermediate regime where forecast quality is materially better.

Properties:

- more tradable than day+4
- fair value can support both `YES` and `NO`
- strong candidate for systematic pre-market trading

Default posture:

- selective directional trades
- medium size

### 3. Same-Day Asia Before 12:00 UTC

This is the strongest regime because the market deadline is `12:00 UTC`, while the local day in `UTC+8/+9` cities is already far advanced.

Properties:

- real information asymmetry
- current-day observations matter a lot
- strongest edge in our current research

Default posture:

- highest priority
- largest size
- model should use observed temperature path, not just forecast


## What To Trade

The unit of decision is a market-native bin or group of bins.

Examples:

- exact bin: `32°C`
- 3-bin cluster: `31°C + 32°C + 33°C`
- tail: `34°C or higher`

The system should always work in Polymarket's actual bucket structure, not in abstract temperature space.


## Current Findings

From the current backtests:

- raw `day+4` exact rounded hit rate is too low to support naive single-bin buying
- `3-bin` windows are much better, but broad "buy around forecast" still looks weak or negative on current markets
- same-day Asia remains the strongest structural opportunity
- on day+4, market crowd often appears to overpay for the obvious center cluster

Practical implication:

- `day+4` is not a broad long strategy
- it may still support selective `NO` or tail trades


## Fair Value Framework

Fair value should not come from a single forecast source.

### Inputs

- archived forecast sources
- current forecast sources
- city-specific and station-specific bias history
- seasonal features
- market bucket structure
- same-day observations where relevant

### Fair Value Layers

1. Forecast Layer

- forecast max temp
- forecast hourly curve
- forecast uncertainty / dispersion

2. Bias Correction Layer

- city bias
- month bias
- station bias
- forecast-regime bias

3. Market Translation Layer

- convert fair distribution over temperatures into Polymarket buckets
- compute fair probability per bucket


## Decision Rules

### Global Rules

Never trade if:

- sample size is too small
- spread is too wide
- liquidity is too low
- market bucket structure is ambiguous
- source disagreement is too high
- edge is too close to zero

### Suggested Thresholds

#### Day+4

- minimum center-bin sample: `50`
- minimum edge: `10pp`
- default bias: look for `NO`

#### Day+2

- minimum center-bin sample: `40`
- minimum edge: `7pp`

#### Same-Day Asia

- minimum edge: `5pp`
- allow larger size
- use current observed max path and cutoff-time context


## Position Sizing

Sizing should depend on regime quality.

### Day+4

- smallest size
- many trades should be skipped

### Day+1 / Day+2

- medium size

### Same-Day Asia

- largest size
- only when signal and liquidity both confirm


## Preferred Trade Types

### Most Likely To Work

- `NO` on overpriced center bins
- `NO` on overpriced 3-bin clusters
- `YES` on neglected adjacent bins
- same-day Asia directional trades after real intraday information arrives

### Least Likely To Work

- broad "always buy 3 bins around forecast"
- pure single-source forecast following
- day+4 exact-bin `YES` without large edge


## Risk Rules

Always enforce:

- max size per market
- max size per city/day
- max correlated exposure per date
- daily stop-loss
- trade blacklist for thin markets


## V1 Architecture

### Data

1. Current Polymarket prices by bucket
2. Archived historical Polymarket bucket prices if obtainable
3. Forecast ensemble
4. NOAA / settlement-style actuals
5. Same-day observed hourly temperatures

### Models

1. `day+4/day+2` fair distribution model
2. city-specific correction models
3. same-day Asia lock-in model

### Outputs

- fair probability per exact bucket
- fair probability per 3-bin cluster
- fair probability per tail
- `bet yes / bet no / no trade`
- expected edge
- confidence label


## V1 Execution Plan

### Phase 1

Build fair-value monitor.

Deliverables:

- current forecast pull
- current market pull
- bucket alignment
- edge table

### Phase 2

Upgrade from one-source forecast to ensemble fair value.

Deliverables:

- multi-source forecast collector
- bucket-level calibration
- city/station correction

### Phase 3

Build same-day Asia model.

Deliverables:

- intraday lock-in probabilities
- cutoff-aware trading rules
- size scaling by information quality


## Immediate Build Priorities

1. Stable parser for current Polymarket bucket prices
2. Exact-bin fair probability model
3. Bucket EV calculator after spread/slippage
4. Trade filter engine
5. Daily report:

- tradable
- not tradable
- overpriced center
- underpriced tail


## Working Summary

The most likely profitable strategy is not a blanket forecast-following system.

It is a selective market-mispricing strategy with:

- forecast ensemble as input
- market-native bucket valuation
- heavy filtering
- separate treatment for `day+4`, `day+2`, and `same-day Asia`

The likely edge hierarchy is:

1. same-day Asia
2. day+1/day+2 selective
3. day+4 selective `NO` only
