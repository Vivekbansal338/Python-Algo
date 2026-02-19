# Issue: Paper Equity and Realized PnL Not Propagated into Risk Ledger

## Status: Open

## Severity: High

## Location: `v6/main.py`, `v6/execution.py`, `v6/brain.py`

---

## Description

Paper account equity used by risk logic does not reliably include realized PnL from closed positions, and equity is clamped to never fall below default capital.

## Current Behavior

- Main loop uses:

```python
current_equity = max(self.risk.state.equity, config.DEFAULT_PAPER_EQUITY)
```

- `RiskManager.update_account()` gets `self.risk.state.current_pnl` recycled from prior value.
- Realized PnL on fully closed positions is not maintained in a persistent account-level ledger.

## Impact

- Drawdown and sizing can be materially understated.
- Paper performance path is unrealistic.

## Proposed Fix (Detailed)

1. Introduce explicit account ledger fields:

- `starting_equity`,
- `realized_pnl`,
- `unrealized_pnl`,
- `equity = starting_equity + realized_pnl + unrealized_pnl`.

2. Update `OrderManager.close_position()` to return/emit realized PnL delta for every close/partial close.
3. Accumulate realized PnL in orchestrator or risk state (single source of truth).
4. Remove default-capital clamp from runtime equity computation.
5. Persist and restore ledger fields in `state_v6.json`.
6. Pass computed ledger-backed equity and pnl to `RiskManager.update_account()` each loop.

## Acceptance Criteria

- Closing a losing trade reduces risk equity immediately.
- Subsequent position sizing uses reduced equity.
- State restore resumes with same realized ledger values.
