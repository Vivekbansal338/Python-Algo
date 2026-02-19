# Issue: Zero Test Coverage

## Status: Open

## Severity: High

## Location: Entire `v6/` runtime

---

## Description

There is no unit/integration test coverage for core V6 trading logic.

## Current Behavior

- `tests/` has no V6 test suite.
- Indicator math, grading, sizing, and lifecycle behavior are unguarded by regression tests.

## Impact

- Silent behavioral regressions are likely during refactors.
- Risk-control changes are hard to validate safely.

## Proposed Fix (Detailed)

1. Add baseline test package structure:

- `tests/v6/test_indicators.py`
- `tests/v6/test_grading.py`
- `tests/v6/test_risk.py`
- `tests/v6/test_lifecycle.py`
- `tests/v6/test_playbook_timing.py`

2. Start with deterministic pure-function tests:

- `calculate_hma`, `calculate_atr`, `calculate_stoch_rsi`, `calculate_rsi`,
- `MarketRegimeDetector` percentile/regime mapping,
- `StockGrader` boundary tests (A+, A, B, C).

3. Add risk invariants:

- no shares for zero stop width,
- lunch multiplier application,
- drawdown warning multiplier behavior.

4. Add lifecycle scenario tests:

- stop hit full close,
- target1 partial and breakeven stop update,
- trailing ratchet only moves favorably.

5. Add smoke integration test for `get_playbook()` boundaries.

## Acceptance Criteria

- CI/local run executes tests with deterministic pass/fail.
- Coverage includes critical decision branches (grading + sizing + lifecycle).
- Any change in grade thresholds or risk multipliers causes test failure unless explicitly updated.
