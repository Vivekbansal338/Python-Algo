# Plan: Fixing Percentage Change Calculation Logic (V4)

## 1. Diagnosis: The "Open Price" Fallacy
*   **Current Issue:** The Orchestrator (`main_v4.py`) calculates all percentage changes using the formula: `(Current_Price - Today_Open) / Today_Open`.
*   **Consequence:** This measures "Intraday Movement" only. It completely ignores the "Gap" (overnight price jump).
*   **Symptoms:** Bot shows `0.00%` when Zerodha shows `+1.50%`. The strategy is blind to overnight institutional demand.
*   **The Fix:** Shift the system's "Zero Point" from **Today's Open** to **Yesterday's Close** (Previous Close).

---

## 2. The Strategy: "The Golden Anchor"
We will establish **Yesterday's Close** as the single source of truth for all directional strength calculations.

*   **Anchor Source:** The Zerodha **Quote API** (`/quote`) and **WebSocket** (`ohlc.close`).
*   **Standardization:** All % Change metrics in the Header, Sector Table, and Signal Table will align with standard market views.

---

## 3. Implementation Phases

### Phase 1: Initialization (The Golden Anchor)
*   **Location:** `main_v4.py` -> `initialize()`
*   **Action:** Immediately after connecting, perform a batch `get_quote()` call for the entire universe (Nifty, VIX, Sectors, Stocks).
*   **Logic:** Populate `self.baselines` with the official `ohlc.close` from the Quote API.
*   **Reason:** Ensures the bot knows the exact market reference point before the first 9:15 AM tick arrives.

### Phase 2: Logic Update (The Formula Swap)
Modify the math in three areas of `main_v4.py`:
1.  **Header:** Change Nifty/VIX % change to `((LTP - PrevClose) / PrevClose) * 100`.
2.  **Sectors:** Change `change_pct` and `intraday_rs` to use `PrevClose`. This makes the "Intraday" score component reflect **Daily Momentum** (Gap + Trend).
3.  **Signals:** Change `signal.change_pct` in the scanner to use `PrevClose`.

### Phase 3: Real-Time Maintenance (The WebSocket)
*   **Location:** `main_v4.py` -> `_recalculate_live_metrics()`
*   **Action:** Since we use `full` mode, extract `ohlc.close` from incoming live ticks.
*   **Logic:** Use this to keep `self.baselines` updated. This provides a robust fallback if the startup API call fails or if the bot is restarted mid-session.

### Phase 4: UI Standardization
*   **Location:** `ui_v4.py`
*   **Action:** Update column labels to reflect the new logic.
    *   Rename **"Chg%"** to **"Day%"** (Daily Change).
    *   Rename **"RS-D"** (Intraday RS) to **"RS-D"** (Daily RS).

---

## 4. Verification Checklist
1.  **Gap Check:** Run bot at 9:15 AM. If market gaps +1%, the Header must immediately show `+1.00%` (Green).
2.  **Comparison Check:** Verify that Nifty % and Stock % values match Zerodha Kite Web precisely.
3.  **Sector Check:** Ensure sectors that gap up are ranked appropriately by the scoring engine.

---

## 5. Impact Analysis on Sector Table Metrics
A review of existing formulas ensures this change enhances, rather than disrupts, the scoring engine:
*   **Market Breadth (Safe):** Uses `LTP vs VWAP`. Since VWAP is purely intraday (resets at 9:15 AM), Breadth remains a perfect measure of intraday participation regardless of the overnight gap.
*   **Historical RS (3d/20d) (Safe):** These metrics use long-term historical anchors. Shifting the 1-day anchor to Previous Close has no meaningful impact on 3-day or 20-day calculations.
*   **Intraday RS (Enhanced):** By shifting to Previous Close, this metric effectively becomes **Daily RS**. It will now correctly award leadership points to sectors that gap up and hold their strength, which were previously "invisible" to the 9:15 AM Open-based logic.

## 6. Impact Analysis on Signals Table Metrics
*   **HMA (Safe):** Uses absolute price levels and slope. The reference point (Open vs Prev Close) does not affect the trend line calculation or alignment logic.
*   **StochRSI (Safe):** Calculated on a rolling window of closing prices. The latest price point is absolute (LTP), so the indicator value remains consistent.
*   **RVOL (Safe):** Compares current volume to historical average. Volume is an absolute number and accumulates from 9:15 AM, so it is unaffected by price anchors.
*   **Gate Logic (Safe):**
    *   **Spread:** Uses absolute `(Ask - Bid) / ATR`. Safe.
    *   **Circuit Check:** Circuits are absolute price levels set by the exchange. Safe.
    *   **Liquidity (ADV):** Uses historical value. Safe.
*   **Change % (Enhanced):** This column will now align with the user's broker terminal, showing the true daily gain/loss (including gap). This prevents "Cognitive Dissonance" where a strong gap-up stock might show 0.00% change.

**Summary Observation:** The Signals Table is structurally robust because its primary filters (HMA, StochRSI, RVOL, and Gate logic) operate on **Absolute Price** and **Volume** data. Shifting the reference point for the "Change %" metric does not interfere with the mathematical validity of these indicators.

## 7. Impact Analysis on Active Monitor & Portfolio
*   **Active Monitor Table:**
    *   **Chg% (Enhanced):** Will now display **Daily Change** instead of Intraday. This is a positive change, allowing the user to see the stock's full strength (including gap) while holding the position.
    *   **HMA & Price (Safe):** Rely on absolute prices. Unaffected.
*   **Portfolio Table:**
    *   **P&L (Safe):** Calculated as `(LTP - Entry_Price) * Qty`. This is purely based on trade execution levels and is **completely independent** of Yesterday's Close.
    *   **Targets/Stops (Safe):** Derived from Entry Price and ATR. Unaffected.
