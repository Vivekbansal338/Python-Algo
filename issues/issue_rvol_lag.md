# RVOL 5-Minute Candle Lag Issue

## The Problem
The current Relative Volume (RVOL) calculation relies on **historical data** only. This creates a critical "blind spot" for real-time trading.

### How it works now:
1.  The bot fetches historical 5-minute candles from Zerodha (e.g., at 10:14 AM).
2.  The API returns only **completed** candles. The last available candle is from **10:05 to 10:10 AM**.
3.  The bot calculates RVOL using that completed candle's volume.

### The Consequence:
*   **Time:** 10:14 AM.
*   **Reality:** A massive breakout is happening *right now* (10:10-10:15 candle). Volume is exploding.
*   **Bot's View:** The bot looks at the 10:05-10:10 candle (which might have been quiet).
*   **Result:** The bot calculates Low RVOL -> **REJECTS the trade**.

### Why it matters:
You are trading breakouts. Breakouts are defined by a surge in volume *at the moment of the break*. By waiting for the candle to close (up to 5 minutes later) to see that volume, you miss the entry.

## The Fix (Concept)
We need **Live Projected Volume**.

1.  **Snapshot:** At the start of every 5-minute block (e.g., 10:10:00), record the `Total Daily Volume` from the WebSocket.
2.  **Live Calculation:** 
    *   `Current 5m Vol` = `Live Total Vol` (from WebSocket) - `Snapshot Vol` (at 10:10:00).
3.  **Projection:** If we are 2 minutes into the candle, we can project the volume:
    *   `Projected Vol` = `Current 5m Vol` * (5 / Time Elapsed).

This allows the bot to say "Volume is *tracking* to be huge" and take the trade instantly.
