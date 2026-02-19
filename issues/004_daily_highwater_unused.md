# Issue: Daily High-Water Mark Stored But Not Used

## Status: Open

## Severity: High

## Location: `v6/execution.py` (`StateManager`), `v6/brain.py` (`RiskManager`)

---

## Description

`daily_high_equity` is persisted in state, but risk kill-switch logic only evaluates drawdown from `daily_start_equity`.

## Current Behavior

- State save computes `daily_high_equity`.
- `check_kill_switches()` evaluates only day-start drawdown.
- Intraday peak-to-trough drawdown is not enforced.

## Impact

- Recovery spikes can reset effective risk exposure.
- System can continue after large intraday peak drawdown if day-start drawdown is smaller.

## Proposed Fix (Detailed)

1. Promote `daily_high_equity` into active risk state (not only persisted state file).
2. Update it in `RiskManager.update_account()`:

```python
daily_high_equity = max(daily_high_equity, equity)
```

3. Evaluate both drawdowns in `check_kill_switches()`:

- `dd_from_start = (equity - daily_start_equity) / daily_start_equity`
- `dd_from_high = (equity - daily_high_equity) / daily_high_equity`

4. Halt condition:

- halt if either drawdown <= `DAILY_DRAWDOWN_HALT_PCT`.

5. Persist/restore:

- save `daily_high_equity` from risk state,
- restore into risk state on restart.

6. Include reason codes to distinguish trigger source:

- `DAILY_DD_START_HALT(...)`
- `DAILY_DD_PEAK_HALT(...)`.

## Acceptance Criteria

- Intraday peak drawdown breach triggers kill switch even if day-start drawdown is above threshold.
- `daily_high_equity` increases intraday and survives restart.
- Halt reason indicates whether start-based or peak-based condition fired.
