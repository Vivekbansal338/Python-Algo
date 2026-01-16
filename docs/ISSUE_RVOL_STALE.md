# Issue: RVOL Stale Data & "Memory Loss"

## 1. Symptom

- **Observation:** When the bot is started at 9:15 AM and runs until 10:12 AM, RVOL values remain static or behave inconsistently.
- **Trigger:** Restarting the bot at 10:15 AM causes a drastic shift in RVOL values.
- **Diagnosis:** The bot **does not synthesize 5-minute candles** from live ticks. It only fetches historical candles **once** at startup.

## 2. Root Cause Analysis

The `main_v4.py` script lacks a "Candle Builder" or "Resampler" mechanism.

### A. The Numerator (`Last Closed Volume`)

- **Code:** `last_closed_vol = hist_5m['volume'][-1]`
- **Behavior:** This points to the last candle available **at the moment of startup**.
- **Impact:** If started at 9:15 AM, this value is **Yesterday's 3:25 PM volume**. It _never_ updates to become the 9:20, 9:25, or 10:00 AM volume, no matter how long the bot runs.

### B. The Denominator (`Average Volume`)

- **Code:** `avg_vol_20 = np.mean(hist_5m['volume'][-20:])`
- **Behavior:** This calculates the average of the last 20 candles **fetched at startup**.
- **Impact:** The 20-period window is frozen. As the market moves from 9:15 to 10:00 AM, the average _should_ evolve to include today's opening volatility. Instead, it remains locked on yesterday's data.

## 3. Why Restarting "Fixed" It

When the bot was restarted at 10:15 AM:

1.  `fetch_stock_history` ran again.
2.  Zerodha returned the fresh 5-minute candles generated between 9:15 AM and 10:10 AM.
3.  **Numerator:** Updated to the 10:10 AM candle (Real Intraday Volume).
4.  **Denominator:** Updated to include the heavy 9:15-10:10 AM volume (Real Intraday Average).
5.  **Result:** RVOL calculation suddenly became accurate based on the new dataset.

## 4. Required Fix

To allow the bot to run continuously without restarting, we must implement **Real-Time Candle Synthesis**:

1.  **Accumulate Ticks:** Store live ticks (LTP/Volume) in memory.
2.  **Resample:** At the end of every 5-minute interval (9:20, 9:25...), finalize a new candle.
3.  **Append:** Add this new candle to `self.stock_history_5m`.
4.  **Trim:** Remove the oldest candle to keep the array size manageable (optional but good practice).

## 5. Clarification: Continuous Stagnation

It is important to note that this is **not** a "restart bug". The logic is flawed from the moment the bot starts:

- **Frozen in Time:** If started at 9:15 AM, the bot uses Yesterday's 3:25 PM candle as the "Last Closed Volume" for the **entire duration** of the session.
- **The Illusion:** The restart at 10:15 AM did not "break" the data; it forced a refresh that **exposed** how stale the previous session's data had become.
- **Conclusion:** The bot currently operates on a "static snapshot" rather than a "rolling window". Without the fix, RVOL is mathematically meaningless after the first 5 minutes of trading.

## 6. Alternative Considered: Periodic Re-fetching

We analyzed the option of calling `get_historical` every 5 minutes instead of building candles locally.

- **Scope:** ~50 stocks (Top Sectors + Positions).
- **Cost:** Zerodha allows 3 req/sec. Fetching 50 stocks takes ~20 seconds.

## 7. Broader System Impact

The "Frozen History" issue extends beyond RVOL to other intraday indicators:

- **HMA (Intraday 20-period):** **BROKEN.**
  - **Logic:** `calculate_hma(np.append(history_5m, current_price), 20)`
  - **Failure:** At 3:00 PM, the array consists of `[...Yesterday_Candles, Current_Tick]`. It is missing all candles from 9:15 AM to 2:55 PM. The HMA line will not reflect the actual intraday trend.
- **StochRSI (Daily):** **SAFE.** Uses Daily history + Current Tick to project today's Daily StochRSI.
- **ATR (Daily):** **SAFE.** Uses static daily history.

**Critical Priority:** The "Candle Builder" fix is required not just for volume analysis, but to restore the basic trend-following capability of the bot (HMA).
