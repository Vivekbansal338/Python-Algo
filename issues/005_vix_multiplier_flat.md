# Issue: VIX Multiplier Identical for 75th and 90th+ Percentile

## Status: Completed (2026-02-20)

## Severity: Low

## Location: `v6/brain.py` -> `MarketRegimeDetector.get_vix_multiplier()`

---

## Description

The sizing function returns the same multiplier for high volatility (`>= 75`) and extreme volatility (`>= 90`), so regime severity is not reflected in risk sizing.

## Current Behavior

- 76th percentile -> 0.75x
- 95th percentile -> 0.75x

## Impact

- Extreme-volatility sessions are not sized more conservatively than high-volatility sessions.

## Proposed Fix (Detailed)

1. Add explicit extreme multiplier in config:

```python
VIX_MULT_EXTREME = 0.50
```

2. Update sizing map:

- `>= EXTREME_THRESHOLD` -> `VIX_MULT_EXTREME`
- `>= HIGH_THRESHOLD` -> `VIX_MULT_HIGH`

3. Optional policy hardening:

- if regime is `EXTREME`, disable fresh entries and allow only exit management.

4. Log applied regime + multiplier for each entry decision.

## Acceptance Criteria

- 90th+ percentile yields lower multiplier than 75-89 percentile.
- Entry logs show correct percentile bucket and multiplier.

---

## Resolution Summary

- Added `VIX_MULT_EXTREME = 0.50` in `v6/config.py`.
- Updated `MarketRegimeDetector.get_vix_multiplier()` in `v6/brain.py`:
  - `>= EXTREME_THRESHOLD` -> `VIX_MULT_EXTREME`
  - `>= HIGH_THRESHOLD` -> `VIX_MULT_HIGH`
- Entry logs in `v6/main.py` now include VIX percentile and applied multiplier.
