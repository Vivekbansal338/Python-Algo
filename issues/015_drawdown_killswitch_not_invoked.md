# Issue: Drawdown Kill-Switch Logic Not Invoked in Runtime Loop

## Status: Open

## Severity: High

## Location: `v6/main.py`, `v6/brain.py`

---

## Description

`RiskManager.check_kill_switches()` exists but is not called during runtime loop execution.

## Current Behavior

- Drawdown halt logic is defined in risk layer.
- Main loop does not invoke it, so kill-switch state is not updated from drawdown path.

## Impact

- Daily drawdown policy is defined but not actively enforced.

## Proposed Fix (Detailed)

1. Call `self.risk.check_kill_switches(self.vix_percentile)` in the 5-second refresh block.
2. If halted:

- block new entries immediately,
- log explicit kill-switch reason,
- optionally execute forced liquidation policy (config-driven).

3. Expose kill-switch state in UI header.
4. Implement baseline initialization from issue `016` in same release to make drawdown math active.

## Acceptance Criteria

- Breach scenario sets `kill_switch_active=True` and prevents new entries.
- Halt reason appears in logs/UI.
- With baseline fix present, warning/halt logic triggers at configured thresholds.

## Related

- `issues/016_daily_start_equity_never_initialized.md`
- `issues/010_equity_tracking.md`
