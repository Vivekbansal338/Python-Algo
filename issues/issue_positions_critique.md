# Positions / Portfolio Logic Critique

## 1. Chandelier Lookback Lag
*   **The Code:** The `_calculate_chandelier` method in `LifecycleManager` fetches 5-minute historical data to determine the "10-candle High" (the anchor for the trailing stop) only if `(now - last_update) > 60s`.
*   **The Issue:** In a hyper-fast market move, a new 5-minute candle might close and establish a new "Highest High," but the bot's Chandelier anchor relies on data that could be up to 59 seconds stale.
*   **Verdict:** This is generally negligible. A 1-minute lag on a trailing stop calculation is usually acceptable and can actually prevent "whipsaw" exits caused by momentary noise.

## 2. Orphaned Positions (Manual Trades)
*   **The Scenario:** If a user manually buys a stock via the Zerodha app (broker side), the `OrderManager` (in a Live scenario) would detect this position.
*   **The Result:** The `LifecycleManager` has no record of this trade (no `Trade` object created). The UI will correctly display the position but label the stage as **"MANUAL"**.
*   **Consequence:** **The bot will NOT manage this trade.** It will not place stops, calculate targets, or trail exits for any position it did not initiate itself. This is a safety feature by design, but users must be aware that manual trades require manual management.

## 3. Partial Fill Complexity (Live Trading Risk)
*   **Current State:** The system is currently in **Paper Mode**, where "Order Placed" effectively equals "Order Filled."
*   **Future Risk:** When transitioning to Live Trading, a partial fill scenario (e.g., trying to exit 50 shares but only 25 get filled) creates a state mismatch.
*   **The Mismatch:** The `LifecycleManager` might transition the trade to **Stage 2 (PARTIAL)** assuming the logic executed, while the `OrderManager` (and the broker) reports a different reality. The current logic does not yet listen for asynchronous "Order Update" events via WebSocket to confirm fill quantities before transitioning states.
