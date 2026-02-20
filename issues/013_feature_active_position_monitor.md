# Feature Proposal: Active Position Monitor (APM)

## Status: Proposed

## Priority: P2

---

## Concept

Extend current portfolio panel from PnL accounting to live trade-quality monitoring for open positions.

## Objective

Provide a per-position health score so operator can decide hold/tighten/exit using trend, breadth, momentum, and live-volume context.

## Plain-English Explanation

Right now open positions show PnL, but not trade quality.  
This feature would add a health score so you can quickly see whether a trade is still structurally strong or starting to weaken.

## Proposed Metrics

| Metric | Header | Formula | Notes |
| --- | --- | --- | --- |
| Distance to Stop | `Dist%` | `(LTP - Stop) / LTP` (short: `(Stop - LTP)/LTP`) | Risk cushion |
| Sector Pulse | `SecS` | Sector composite score | Context strength |
| Momentum | `Stoch` | Live StochRSI K | Exhaustion signal |
| Live Volume | `RVOL-L` | Live/projection 5m volume over avg 5m volume | Needs issue `002` fix |
| Relative Strength | `RS-5m` | Stock 5m return - Nifty 5m return | Intraday outperformance |
| Health Score | `Health` | Weighted aggregate 0-100 | Decision summary |

## Proposed Fix / Implementation Plan (Detailed)

1. Add health engine class (`TradeHealthMonitor`) in `v6/brain.py`.
2. Add health inputs to runtime loop for each active trade:

- latest tick,
- current stop,
- sector score,
- intraday history.

3. Scoring model (symmetric for long/short):

- trend/vwap component,
- sector component,
- momentum component,
- volume component,
- relative-strength component.

4. Add thresholds:

- 80-100 `STRONG`,
- 50-79 `WEAK`,
- <50 `CRITICAL`.

5. UI integration:

- add `generate_active_monitor()` panel to `DashboardUI`,
- display health color + reason flags.

6. Optional automation (P3):

- if `CRITICAL` for N consecutive checks, tighten stop automatically.

## Dependencies

- `issues/002_rvol_candle_lag.md` for live RVOL reliability.
- `issues/008_no_tick_staleness.md` so health uses fresh ticks only.

## Acceptance Criteria

- Every active position shows computed health every refresh cycle.
- Health score responds to momentum/sector changes in real time.
- No impact on entry/exit behavior when feature toggle is off.
