# Issue: `daily_start_equity` Baseline Never Initialized on Fresh Start

## Status: Completed (2026-02-20)

## Severity: High

## Location: `v6/main.py`, `v6/brain.py`, `v6/execution.py`

---

## Description

Fresh-session initialization does not set `daily_start_equity`, so drawdown checks guarded by `daily_start_equity > 0` never activate.

## Current Behavior

- Account state starts with baseline `0.0`.
- Fresh path sets equity but leaves `daily_start_equity` unchanged.
- Persisted state can continue carrying baseline `0.0`.

## Impact

- Drawdown warning and halt logic can remain permanently inactive.

## Proposed Fix (Detailed)

1. On fresh start after `update_account(...)`, initialize:

```python
self.risk.state.daily_start_equity = self.risk.state.equity
```

2. On restore:

- if restored baseline `<= 0`, backfill from restored/current equity.

3. On new-day rollover:

- reset baseline to opening equity for that day,
- reset intraday high-water state accordingly.

4. Add invariant log:

- at startup print baseline value and source (`restored` vs `initialized`).

## Acceptance Criteria

- New session has non-zero `daily_start_equity`.
- Drawdown warning/halt branches become reachable in runtime.
- Baseline persists and restores correctly.

---

## Resolution Summary

- Added startup baseline normalization in `v6/main.py` via `_ensure_daily_baselines(...)`.
- Fresh start now initializes:
  - `starting_equity`
  - `daily_start_equity`
  - `daily_high_equity`
- Restore path now backfills missing baselines safely from restored equity context.
- Startup logs now include baseline source (`initialized` or `restored`) and values.
