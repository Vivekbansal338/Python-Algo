# Issue: No Distinct Post-Close Playbook State (`MARKET_CLOSE_TIME` Unused)

## Status: Open

## Severity: Medium

## Location: `v6/main.py`, `v6/config.py`

---

## Description

`MARKET_CLOSE_TIME` is defined but not used in playbook routing. Runtime remains in `FORCE_EXIT` for all times after 15:05.

## Current Behavior

- `get_playbook()` returns `FORCE_EXIT` for `>= FORCE_EXIT_TIME`.
- No separate `AFTER_CLOSE` or shutdown state at 15:30.

## Impact

- After-market behavior is ambiguous.
- Runtime may continue unnecessary loops after market close.

## Proposed Fix (Detailed)

Preferred option:

1. Add explicit `AFTER_CLOSE` playbook branch at `>= MARKET_CLOSE_TIME`.
2. In `AFTER_CLOSE`:

- disable scanner work,
- keep only minimal housekeeping,
- save state once and stop process cleanly (config-controlled auto-shutdown).

3. Keep `FORCE_EXIT` behavior only for 15:05-15:29:59.

Alternative option:

- keep current playbook map but remove `MARKET_CLOSE_TIME` constant to avoid dead config.

## Acceptance Criteria

- Runtime behavior at/after 15:30 is explicit and deterministic.
- Docs and config exactly match implemented playbook transitions.
