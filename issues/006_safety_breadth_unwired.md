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

---

## Final Analysis (Consolidated, 2026-02-20)

This issue is valid and currently a real wiring gap.

- `SafetyMonitor.update()` supports breadth-based action, but runtime calls `self.safety.update(self.nifty_ltp, self.vix_ltp, 0.0)` in `v6/main.py`.
- Result: breadth-collapse logic in `v6/brain.py` is effectively disabled.

Your long/short concern is also correct:

- A broad down market can be favorable for shorts.
- So a blunt `red >= 70% => halt all` is too coarse for this system design.

Consolidated recommendation:

1. First, wire real breadth input (non-negotiable): compute red-stock percentage from live universe ticks with minimum valid-sample guard.
2. Then refine behavior policy:
   - directional control for moderate breadth extremes (e.g., suppress one side),
   - full system halt only for disorder-level extremes (or breadth + other stress confirmation).
3. Add observability: log breadth %, sample size, and resulting action state.

So the issue remains open until real breadth is computed and consumed, then policy tuning can follow.

