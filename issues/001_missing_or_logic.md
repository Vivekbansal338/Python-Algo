# Issue: Missing Opening Range (OR) Logic

## Status: Open

## Severity: Medium

## Location: `v6/main.py`

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
