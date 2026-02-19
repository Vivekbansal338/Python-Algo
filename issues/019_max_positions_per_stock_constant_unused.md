# Issue: `MAX_POSITIONS_PER_STOCK` Constant Defined but Not Explicitly Enforced

## Status: Open

## Severity: Low

## Location: `v6/config.py`, `v6/brain.py`

---

## Description

`MAX_POSITIONS_PER_STOCK` exists in config, but risk checks enforce single-symbol exposure through hardcoded active-symbol logic instead of this config value.

## Current Behavior

- Duplicate symbol is blocked by `if symbol in active_symbols`.
- Changing `MAX_POSITIONS_PER_STOCK` does not alter runtime behavior.

## Impact

- Configuration and runtime are inconsistent.
- Future scaling/pyramiding cannot be enabled safely by config only.

## Proposed Fix (Detailed)

1. Track per-symbol counts in risk state (`symbol_exposure: Dict[str, int]`).
2. Populate this map in `update_account()` from open positions.
3. Enforce with config in `can_open_new_trade()`:

```python
if symbol_exposure.get(symbol, 0) >= config.MAX_POSITIONS_PER_STOCK:
    reject
```

4. Keep `active_symbols` for convenience/UI, but use `symbol_exposure` for enforcement.
5. If intentional policy is fixed one-position-per-symbol, remove `MAX_POSITIONS_PER_STOCK` from config to avoid dead setting.

## Acceptance Criteria

- Runtime behavior changes when `MAX_POSITIONS_PER_STOCK` is changed.
- With value `1`, current behavior is preserved.
