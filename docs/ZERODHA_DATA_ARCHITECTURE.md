# Zerodha Data Architecture (V4)

## 1. Overview
The V4 system utilizes three distinct communication channels with Zerodha: **Historical API** (REST), **Quote API** (REST), and **WebSocket Ticker** (Streaming).

---

## 2. Component Analysis

### A. Historical API (`get_historical`)
*   **Data Points:** OHLCV Candles (Daily and 5-Minute).
*   **Frequency:**
    *   **Startup/Restart:** Called once for every symbol in the universe (Nifty, Sectors, Stocks).
    *   **Lifecycle:** Called every 60 seconds *per open trade* to calculate Chandelier Stops (10-bar 5m lookback).
*   **Primary Usage:**
    *   **Sector Table:** Historical RS (3-day and 20-day trend).
    *   **Signals Table:** ATR (Volatility), ADV (Liquidity), Daily HMA, Daily StochRSI, and Intraday HMA/RVOL (Stale after startup).
*   **Risk:** High API cost. Subject to rate limits (3 req/sec). Continuous querying for Chandelier stops is a potential bottleneck.

### B. Quote API (`get_quote`)
*   **Data Points:** Full Market Snapshot (LTP, OHLC, Depth, Circuits).
*   **Frequency:**
    *   **Startup Only:** Called once to initialize Sector Ranks and fetch Golden Anchor (Prev Close) for all symbols.
    *   **On-Demand:** Called during a "Paper Exit" to simulate accurate market fills.
*   **Primary Usage:**
    *   **Sector Table:** Establishing initial Sector rankings.
    *   **Baseline:** Fetching reliable `ohlc.close` for daily % change calculations.
*   **Risk:** Moderate API cost. Limited to 1 req/sec.

### C. WebSocket Ticker (`start_ticker`)
*   **Data Points:** Continuous Stream of Ticks (`full` mode).
*   **Frequency:** Real-time (Thousands of updates per second).
*   **Primary Usage:**
    *   **Header:** Real-time Nifty/VIX updates.
    *   **Sector Table:** Real-time Breadth (LTP vs VWAP) and Intraday Change.
    *   **Signals Table:** Drives the live scanner (Spread, HMA alignment, RVOL spikes).
    *   **Portfolio:** Continuous PnL and active trade monitoring.
*   **Risk:** Zero API cost (unlimited bandwidth). The system’s primary engine.

### D. Instruments API (`instruments`)
*   **Data Points:** Master CSV of all symbols and tokens.
*   **Frequency:** Once every 12 hours (Cached locally in `.pkl` format).
*   **Usage:** Essential for mapping human-readable symbols to numeric WebSocket tokens.

---

## 3. Historical Data Lookback Configuration
Configured in `core_v4/config_v4.py`:
*   **Daily History:** 60 days (`LOOKBACK_DAYS_DAILY`) - Used for ATR, HMA (Daily), ADV.
*   **Intraday History:** 5 days (`LOOKBACK_DAYS_INTRA`) - Used for 5-minute HMA and RVOL.
*   **VIX History:** 45 days (`LOOKBACK_DAYS_VIX`) - Used for Regime Percentile calculation.

---

## 4. Data Flow Summary

| Table / View | Data Source | Update Frequency |
| :--- | :--- | :--- |
| **Header** | WebSocket | Real-time |
| **Sector Rankings** | Quote API (Startup) + WebSocket | Rescan: Continuous (5s) |
| **Stock Signals** | WebSocket + Historical | Scan: Continuous / Logic: Snapshotted |
| **Portfolio / PnL** | WebSocket | Real-time |
| **Stops / Targets** | Historical (at entry) | Static (until exit) |

---

## 5. Identified Bottleneck: "Memory Loss"
The system correctly uses WebSocket for live prices but fails to "store" those prices back into the historical candle arrays. This leads to **Continuous Stagnation** where intraday indicators (RVOL, HMA) stop reflecting current reality shortly after startup.
