# Live Policy V1

## Current Mode

- run `paper + tiny live` in parallel
- use live only for `tradable` cities
- keep `paper only` ideas in observation mode

## Tradable Cities

- Seoul
- Paris

## Experimental Cities

- Singapore
- Shanghai

## Avoid

- Dallas
- Tokyo
- any city marked `avoid` in the whitelist

## Live Entry Rules

- trade only rows marked `trade` in `outputs/paper/daily_signal_brief.html`
- respect the `entry rule` exactly
- if market price is worse than the entry rule, skip
- do not trade `paper only`

## Live Size

- current live size: `$1` per trade
- minimum Polymarket stake is binding at the current bankroll
- do not increase size yet

## Expansion Rules

- keep live limited to `Seoul` and `Paris` for now
- consider expanding only after `20-30` live trades
- increase city universe before increasing size
- consider adding `Singapore` and `Shanghai` only after more paper confirmation

## Exit Rules

- default exit: hold to market resolution
- no early exit logic is active yet

