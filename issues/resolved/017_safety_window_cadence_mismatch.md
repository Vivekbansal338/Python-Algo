# Issue: Safety Monitor Window Assumption Mismatches Runtime Cadence

## Status: Completed (2026-02-20)

## Severity: Medium

## Location: `v6/brain.py`, `v6/main.py`

---

## Description

Safety monitor comments and deque sizing assume near 1-second sampling, but runtime currently calls `SafetyMonitor.update()` at ~5-second intervals.

## Current Behavior

- Fixed deque length (`maxlen=300`) is treated as 5-minute history.
- With 5-second calls, effective lookback becomes about 25 minutes.

## Impact

- Flash-crash/VIX-spike triggers are not calibrated to intended 5-minute window.

## Proposed Fix (Detailed)

1. Keep timestamped points, but make window explicitly time-based.
2. On each update:

- append `(ts, value)`,
- prune points older than 300 seconds,
- compute change from earliest remaining point.

3. Remove/replace comments that imply fixed 1-second resolution.
4. Add runtime cadence metric in logs (median update interval) for observability.

## Acceptance Criteria

- Regardless of call frequency, monitor uses true last 5 minutes.
- Trigger behavior is consistent under both 1-second and 5-second update cadence.

---

## Resolution Summary

- Refactored `SafetyMonitor` (`v6/brain.py`) from fixed-length assumption to timestamp-pruned windows.
- On each update, histories are pruned to true `SAFETY_WINDOW_SEC` age (default 300s).
- Flash-crash and VIX-spike checks now compare against earliest point in current time window.
- Added cadence observability log (median update interval + sample count) at periodic intervals.
