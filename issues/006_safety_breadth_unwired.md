# Issue: Safety Monitor Breadth Collapse Detection Not Wired

## Status: Open

## Severity: Medium

## Location: `v6/main.py` (`TradingBotV6.run()`), `v6/brain.py` (`SafetyMonitor`)

---

## Description

`SafetyMonitor.update()` supports breadth-collapse halting, but runtime passes a hardcoded `0.0` breadth value.

## Current Behavior

- Breadth trigger exists in monitor.
- Runtime call is `self.safety.update(self.nifty_ltp, self.vix_ltp, 0.0)`.
- Breadth-collapse branch never activates.

## Impact

- System can continue entering trades during broad market deterioration.

## Plain-English Explanation

The safety monitor has logic for “too many stocks are red,” but runtime always sends `0.0` as input.  
That means this safeguard can never trigger, even if the market is broadly collapsing.

## Proposed Fix (Detailed)

1. Compute live red-stock percentage from tracked stock universe:

- iterate symbols from `self.stocks`,
- for each tick with valid `average_price`, classify red if `last_price < average_price`.

2. Require minimum sample size before using breadth (example: >= 20 valid stocks).

3. Pass computed `red_stock_pct` into `SafetyMonitor.update()`.

4. Add log entries:

- current breadth %, sample size,
- halt reason when breadth trigger fires.

5. UI: show breadth metric in header or logs so operators can validate trigger context.

## Acceptance Criteria

- Breadth percentage is non-zero in normal market conditions.
- Simulated broad selloff with red >= 70% triggers safety halt.
- Halt reason includes `BREADTH_COLLAPSE` and measured percentage.
