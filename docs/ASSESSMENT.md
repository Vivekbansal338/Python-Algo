# V6 System Assessment (Code-Truth)

> Source of truth: direct audit of `v6/config.py`, `v6/data_engine.py`, `v6/brain.py`, `v6/execution.py`, `v6/main.py`.
> Last verified against code: February 19, 2026.

---

## 1. Executive Summary

V6 has a clean consolidated architecture and clear module boundaries, but runtime risk enforcement and operational resilience still have important gaps.

Overall readiness:

- Paper-trading experimentation: acceptable with caveats.
- Production/live-readiness: not acceptable in current state.

---

## 2. What Is Strong

- Consolidated 5-file design with straightforward dependency direction.
- Rich UI and good runtime visibility for sector/signal/position state.
- Clear trade lifecycle abstraction (entry -> partial -> trailing -> close).
- Defensive paper-mode hard stop (`IS_PAPER_TRADING` guard).

---

## 3. High-Impact Open Findings

### Critical / High

- `issues/007_no_websocket_fallback.md`: websocket disconnect has no fallback action in main runtime flow.
- `issues/008_no_tick_staleness.md`: ticks are consumed without freshness guard.
- `issues/010_equity_tracking.md`: realized PnL does not cleanly propagate to risk equity ledger.
- `issues/015_drawdown_killswitch_not_invoked.md`: drawdown kill-switch function exists but is never invoked.
- `issues/016_daily_start_equity_never_initialized.md`: drawdown baseline stays zero in fresh sessions.

### Medium

- `issues/001_missing_or_logic.md`: ORB removed; unified to single MAIN strategy (Completed).
- `issues/003_correlation_not_enforced.md`: correlation threshold constant is not enforced.
- `issues/006_safety_breadth_unwired.md`: safety breadth collapse input is hardcoded to 0.0.
- `issues/014_thread_safety.md`: shared `live_ticks` access is unsynchronized across threads.
- `issues/017_safety_window_cadence_mismatch.md`: safety monitor window assumption does not match runtime call cadence.
- `issues/018_market_close_playbook_absent.md`: no distinct post-close playbook state; runtime remains in `FORCE_EXIT`.

### Low / Hygiene

- `issues/005_vix_multiplier_flat.md`: extreme and high VIX share same multiplier.
- `issues/009_state_save_race.md`: modulo-based state save can write multiple times in one second.
- `issues/019_max_positions_per_stock_constant_unused.md`: config constant is not explicitly enforced by the risk gate.

---

## 4. Risk-Flow Integrity Notes

The drawdown architecture currently has two independent gaps that compound each other:

1. Runtime does not call `RiskManager.check_kill_switches()`.
2. `daily_start_equity` is not initialized on fresh start.

Result:

- Drawdown halt and warning logic are both effectively bypassed in normal flow.

---

## 5. Timing and Runtime Semantics Clarification

- Strategy scan/safety pass is gated by `UI_REFRESH_INTERVAL` (5s), not per-tick.
- Main loop still iterates every 0.5s.
- Playbook routing ends in persistent `FORCE_EXIT` at/after 15:05.

---

## 6. Data/State Correctness Notes

- `daily_high_equity` is saved, but not used by risk kill-switch logic.
- State restoration restores trades/orders/positions plus `daily_start_equity`; it does not establish a robust realized-equity ledger by itself.

---

## 7. Scope/Repository Hygiene Notes

- This verification pass is intentionally limited to `docs/` and `issues/` against current `v6` code.
- `rough/` directory check: no `rough` folder exists in the current workspace, so there is nothing to remove.

---

## 8. Priority Order (Suggested)

### P0

1. Invoke drawdown kill-switch in runtime loop.
2. Initialize and maintain `daily_start_equity` baseline correctly.
3. Add websocket watchdog/fallback path.
4. Add tick staleness guards.

### P1

5. Wire safety breadth input.
6. Fix safety monitor window logic to true time-based behavior.
7. Repair realized-PnL -> equity propagation.

### P2

8. Add market-close state behavior (or auto-shutdown) after 15:30.
9. Enforce explicit max-per-stock constant usage.
10. Add regression tests for indicators, grading, risk math.
