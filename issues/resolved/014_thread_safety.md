# Issue: Thread Safety - WebSocket and Main Loop Share `live_ticks`

## Status: Completed (2026-02-20)

## Severity: Medium

## Location: `v6/data_engine.py`, `v6/main.py`

---

## Description

WebSocket callback thread writes `live_ticks` while main/runtime logic reads it concurrently without synchronization.

## Current Behavior

- WebSocket thread performs writes in `_on_ticks`.
- Main and lifecycle logic perform concurrent reads.
- CPython GIL reduces crash risk for single dict ops, but consistency/visibility guarantees are weak for multi-step reads.

## Impact

- Non-deterministic reads across rapidly updated tick objects.
- Hard-to-reproduce behavior in signal or lifecycle decisions.

## Proposed Fix (Detailed)

1. Add lock in `DataManager`:

```python
self._tick_lock = threading.RLock()
```

2. Wrap writes under lock in `_on_ticks`.
3. Expose accessor methods:

- `get_tick(token)` returns shallow copy under lock,
- `get_ticks(tokens)` batch read under one lock,
- optional `update_ticks(...)` internal helper.

4. Replace direct `live_ticks.get(...)` usage across `main.py` and `execution.py` with accessor methods.
5. Keep lock section minimal to avoid contention; do not hold lock during heavy computation.

## Acceptance Criteria

- No direct `data_manager.live_ticks.get(...)` reads remain in runtime-critical paths.
- Tick reads/writes are lock-protected.
- Behavior remains functionally identical under normal load.

---

## Resolution Summary

- Added `threading.RLock()` protection in `v6/data_engine.py` for tick writes and reads.
- Wrapped websocket ingest writes under lock and stamped ticks with receive time.
- Added thread-safe accessors:
  - `get_tick(...)`
  - `get_ticks(...)`
  - `get_fresh_tick(...)`
- Replaced runtime direct tick reads in `v6/main.py` with accessor usage.
