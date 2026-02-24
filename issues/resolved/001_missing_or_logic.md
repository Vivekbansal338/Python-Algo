# Issue: Missing Opening Range (OR) Logic

## Status: Completed (2026-02-20)

## Severity: Medium

## Location: `v6/main.py`, `v6/config.py`, `v6/brain.py`

---

## Description

The runtime labels an `OR_FORMATION` phase and an `ORB` phase, but does not capture opening range levels or enforce breakout conditions before entry.

## Current Behavior

- During `OR_FORMATION`, no OR high/low state is recorded.
- During `ORB`, entries are based on momentum/grade/gate checks only.
- `ORB_START_TIME` is defined in config but not used by `get_playbook()`; ORB starts immediately after `OR_END_TIME`.

## Impact

- ORB window can take trades inside the opening range (chop entries).
- Strategy behavior is momentum-style, not true opening-range breakout behavior.

## Plain-English Explanation

The bot says it is in Opening Range Breakout mode, but it never actually remembers the opening range boundaries.  
So during ORB time, it can still buy/sell while price is inside the first-range box, which defeats the purpose of breakout trading.

## Proposed Fix (Detailed)

1. Add OR state container in `TradingBotV6`:

```python
self.opening_ranges: Dict[str, Dict[str, float]] = {}
# shape: {symbol: {"high": ..., "low": ..., "start_ts": ..., "end_ts": ...}}
```

2. During `OR_FORMATION`, update OR for each candidate stock from live ticks:

- initialize `high=ltp`, `low=ltp` on first valid tick,
- update `high=max(high, ltp)`, `low=min(low, ltp)`.

3. In ORB entry path, enforce breakout gate before `_process_entry`:

- long requires `ltp > or_high`,
- short requires `ltp < or_low`,
- if inside range: reject with reason `INSIDE_OR_RANGE`.

4. Add optional breakout buffer to reduce false breaks:

- `breakout_buffer = max(0.0, 0.05 * atr)` (or configurable),
- long condition `ltp > or_high + breakout_buffer`.

5. Reset OR state once session leaves ORB (or at day rollover).

## Acceptance Criteria

- During `OR_FORMATION`, OR highs/lows are populated for symbols with valid ticks.
- During `ORB`, at least one in-range A/A+ signal is rejected due to OR gate reason.
- Outside ORB (`MAIN`), OR breakout gate is not applied.

---

## Final Analysis (Consolidated, 2026-02-20)

This issue is valid in the current codebase.

- `v6/main.py` exposes `OR_FORMATION` and `ORB` sessions, but no opening-range state (high/low) is tracked for any symbol.
- Entry decisions in `ORB` still use grade/gate/sizing only; there is no breakout condition (`ltp > OR high` / `ltp < OR low`).
- `ORB_START_TIME` exists in `v6/config.py` but `get_playbook()` transitions to `ORB` directly after `OR_END_TIME`, so `ORB_START_TIME` is currently unused.

Consolidated product/engineering conclusion:

1. If ORB is intended as a real strategy, this must be implemented with explicit OR capture + breakout gate.
2. If product wants a single strategy model, ORB/OR_FORMATION/GAP should be removed and the day should be simplified to `WAIT -> MAIN -> EXIT_ONLY -> FORCE_EXIT -> AFTER_CLOSE`.

Recommended direction: remove pseudo-ORB unless the team commits to maintaining true breakout logic. Current behavior is a parameter variant, not a distinct ORB strategy.

Suggested unified timings if ORB is removed:

- `WAIT`: `09:15` to `09:24:59`
- `MAIN`: `09:25` to `14:04:59`
- `EXIT_ONLY`: `14:05` to `15:04:59`
- `FORCE_EXIT`: `15:05` to `15:29:59`
- `AFTER_CLOSE`: `15:30+`

---

## Resolution Summary

This issue is resolved by removing the pseudo-ORB concept entirely and moving to one unified entry playbook.

- Removed OR/ORB/GAP session routing from `get_playbook()` in `v6/main.py`.
- Implemented unified day flow:
  - `PRE_MARKET -> WAIT -> MAIN -> EXIT_ONLY -> FORCE_EXIT -> AFTER_CLOSE`
- Replaced timing config with `ENTRY_START_TIME = 09:25` in `v6/config.py`, and removed unused OR/ORB/GAP timing constants.
- Removed ORB-specific gate/grade branches:
  - `StockGrader` now uses one RVOL threshold table (`RVOL_THRESHOLDS`).
  - `ExecutionFilters` now uses one spread and circuit buffer pair (`SPREAD_ATR_LIMIT`, `CIRCUIT_BUFFER`).
- Removed ORB-specific stop sizing branch and standardized to `STOP_ATR_MULT`.
- Updated UI session mapping/styling to remove ORB/OR_FORMATION labels and show `WAIT`.

Result: behavior now matches product intent (single strategy), with no dangling ORB logic left in runtime code.

