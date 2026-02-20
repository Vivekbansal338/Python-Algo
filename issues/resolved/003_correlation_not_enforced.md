# Issue: Correlation Threshold Defined But Not Enforced

## Status: Completed (2026-02-20)

## Severity: Medium

## Location: `v6/config.py`, `v6/brain.py`, `v6/main.py`

---

## Description

`CORRELATION_THRESHOLD` exists in config, but no runtime path computes cross-position correlation before opening new trades.

## Current Behavior

- `can_open_new_trade()` checks max positions, per-sector cap, and duplicate symbol.
- No return-series comparison is performed against active positions.

## Impact

- Portfolio can become highly clustered by theme/factor.
- Drawdown can exceed intended diversification assumptions.

## Proposed Fix (Detailed)

1. Add correlation gate helper in risk layer:

```python
def check_correlation(candidate: str, active_symbols: List[str], history_5m: Dict[str, np.ndarray]) -> Tuple[bool, str]
```

2. Data source for correlation:

- use 5-minute close series already cached in `self.stock_history_5m`,
- compute returns via `np.diff(np.log(close))`.

3. Minimum data requirement:

- require at least 30 aligned return points for candidate and comparator,
- if insufficient history, return `INSUFFICIENT_CORR_DATA` and allow trade (or apply a conservative size cut, configurable).

4. Gate rule:

- compute Pearson correlation with each active symbol,
- if any absolute correlation exceeds `config.CORRELATION_THRESHOLD`, reject with reason containing offender symbol and value.

5. Integration point:

- call correlation gate in `_process_entry()` before position sizing.

## Acceptance Criteria

- Candidate with |corr| > threshold against any active position is rejected.
- Candidate below threshold passes this gate.
- Gate reasons are visible in logs for rejected entries.

---

## Resolution Summary

- Removed the correlation concept entirely per product decision.
- Deleted `CORRELATION_THRESHOLD` from `v6/config.py`.
- Removed correlation references from `v6/brain.py` risk documentation.
- No correlation gate is present in runtime by design.
