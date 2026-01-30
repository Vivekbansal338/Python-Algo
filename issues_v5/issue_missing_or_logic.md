# Issue: Missing Opening Range (OR) Logic

## 1. Description
The V5 Trading Bot identifies the "ORB" (Opening Range Breakout) phase (09:35 - 10:05) in its schedule, but currently lacks the core logic to execute a true breakout strategy. It trades generic momentum signals during this window instead of validating price breakouts from a defined range.

## 2. Gaps Identified

### A. Missing State Tracking
*   **Current Behavior:** During the `OR_FORMATION` phase (09:20 - 09:34), the bot idles or processes data but does not record the High and Low prices for candidate stocks.
*   **Required Behavior:** The system must track and store the `OR_HIGH` and `OR_LOW` for all monitored stocks during this 15-minute window.

### B. Missing Breakout Validation
*   **Current Behavior:** The `StockGrader` validates signals based on HMA, RVOL, and StochRSI.
*   **Required Behavior:** During the `ORB` phase, a valid signal must **also** confirm that:
    *   **Long:** `Current_Price > OR_HIGH`
    *   **Short:** `Current_Price < OR_LOW`

## 3. Implementation Plan

### Phase 1: State Management Update
*   Modify `system_v5/state_v5.py` or `main_v5.py` to include a data structure for storing Opening Range levels.
    *   Structure: `self.opening_ranges = { "SYMBOL": {"high": 100.0, "low": 95.0}, ... }`

### Phase 2: Logic Injection
*   **OR Formation (09:20 - 09:34):**
    *   Iterate through incoming ticks/candles.
    *   Update the Max High and Min Low for each stock.
*   **ORB Execution (09:35 - 10:05):**
    *   Pass `OR_HIGH` and `OR_LOW` to the `StockGrader`.
    *   Add a specific check: `is_breakout = price > or_high or price < or_low`.
    *   If not a breakout, downgrade signal to "C" (Reject) or add a specific reason "Inside Range".

## 4. Expected Outcome
The bot will strictly adhere to the ORB strategy during the first 30 minutes of active trading, preventing "chop" entries inside the opening range and focusing capital on stocks showing genuine structural breakouts.
