# Issue: No Tick Staleness Detection

## Status: Completed (2026-02-20)

## Severity: Critical

## Location: `v6/data_engine.py`, `v6/main.py`

---

## Description

Ticks in `live_ticks` do not carry a receive timestamp and are consumed without age checks.

## Current Behavior

- Latest tick replaces prior tick in cache.
- Call sites read tick fields directly, regardless of age.

## Impact

- Stale prices can drive entries, exits, and risk metrics.
- Feed stalls can remain undetected.

## Proposed Fix (Detailed)

1. Stamp ticks on ingest:

```python
tick_copy = dict(tick)
tick_copy["_received_at"] = time.monotonic()
self.live_ticks[token] = tick_copy
```

2. Add accessor in `DataManager`:

```python
def get_fresh_tick(token: int, max_age_sec: float = 30.0) -> Optional[Dict]
```

- returns `None` if missing or stale.

3. Replace direct `live_ticks.get(...)` in main/execution with `get_fresh_tick(...)` for all trading decisions.

4. Policy on stale tick:

- scanner: skip symbol,
- entry logic: block new entries,
- lifecycle: if stale for active position, fetch REST quote fallback.

5. Add staleness counters/logs for operator visibility.

## Acceptance Criteria

- Tick older than threshold is rejected by accessor.
- Scanner does not process stale symbols.
- Active positions still receive fallback price path when websocket is stale.

---

## Resolution Summary

- Tick ingest in `v6/data_engine.py` stamps `_received_at` on every websocket tick.
- Added `get_fresh_tick(...)` and migrated runtime decision paths in `v6/main.py` to use it.
- Added stale/missing/fresh tick counters and periodic stale-filter warnings in `v6/data_engine.py`.
- Added periodic tick-health observability logs in `v6/main.py`.
- Lifecycle path already uses REST quote fallback in degraded/stale conditions for active trades.
