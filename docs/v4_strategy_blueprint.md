# V4 Autonomous Trading System: Comprehensive Strategy Whitepaper

**Version**: 4.0.0
**Target Asset Class**: Indian Equities (NSE)
**Strategy Type**: Absolute Momentum with Sector Confirmation (Intraday Trend Following)
**Execution Mode**: Fully Autonomous (Paper/Live)

---

## 1. Executive Summary & Philosophy

The V4 system is designed to capture **Intraday Trend Extensions** in high-velocity stocks. It relies on a "Top-Down" momentum philosophy:
1.  **Market First**: Respect the Nifty 50 direction ("The Tide").
2.  **Sector Second**: Identify industry groups with broad-based buying pressure ("The Wave").
3.  **Stock Third**: Execute individual stocks with confirmed technical breakouts ("The Swimmer").

Unlike traditional Relative Strength strategies that look back weeks or months, V4 is hyper-focused on **Real-Time Flow**. It prioritizes "Breadth" (how many stocks are participating *now*) over "History" (how much the sector moved last month).

---

## 2. System Architecture & Data Flow

The system follows a strict **Event-Driven Architecture**.

### 2.1 Data Ingestion Pipeline
*   **Source**: Zerodha Kite Connect API.
*   **Historical Data**:
    *   **Daily Candles**: Used for Structural RS (20-day) and ATR calculation. Cached locally in `.parquet` files.
    *   **5-Minute Candles**: Used for Intraday RS, RVOL (Rolling Average), and HMA(20). Cached locally.
*   **Live Data**:
    *   **WebSocket (Tick Data)**: Provides real-time LTP (Last Traded Price), Open, High, Low, and Market Depth (Bid/Ask).
    *   **Update Frequency**: Ticks arrive continuously. The system processes logic in a fast loop (every ~0.5s) but recalculates heavy strategy metrics every **5 seconds**.

### 2.2 File Structure Map
| Module | File Path | Responsibility |
| :--- | :--- | :--- |
| **Orchestrator** | `07.python_practice/main_v4.py` | The central nervous system. Initializes data, manages the infinite loop, and coordinates all sub-modules. |
| **Strategy Core** | `07.python_practice/analysis_v4/strategy_v4.py` | The "Brain". Contains `SectorScorer` (Ranking) and `StockGrader` (Signal Generation). |
| **Indicators** | `07.python_practice/analysis_v4/indicators_v4.py` | Pure math functions. HMA, RSI, ATR, RVOL implementation. |
| **Risk Engine** | `07.python_practice/execution_v4/risk_v4.py` | The "Gatekeeper". Calculates position size and enforces portfolio limits. |
| **Lifecycle** | `07.python_practice/execution_v4/lifecycle_v4.py` | Trade Manager. Handles Stop Loss updates, Target partials, and Exits. |
| **Orders** | `07.python_practice/execution_v4/orders_v4.py` | Broker Interface. Sends actual Buy/Sell API calls. |
| **Config** | `07.python_practice/core_v4/config_v4.py` | The "Constitution". Hard-coded thresholds, timings, and weights. |

---

## 3. The Sector Ranking Engine (The Macro Filter)

**Objective**: Rank 12 Sector Indices (e.g., NIFTY BANK, NIFTY IT) to find the "Hottest" flows.

### 3.1 Ranking Logic: Absolute Intensity
The system calculates a **Composite Score** for each sector. Critically, it ranks sectors by the **Absolute Magnitude** of this score (`abs(score)`).
*   **Why?** A sector crashing violently (Score -80) is just as significant as a sector rallying (Score +80). Both offer trading opportunities. The system ignores low-magnitude sectors (Score near 0) as they represent chop/noise.

### 3.2 The 5 Scoring Components (Detailed)

#### **1. Net Breadth (Weight: 40)**
*   **Concept**: Internal Health.
*   **Formula**: `((Count(Price > VWAP) - Count(Price < VWAP)) / Total_Stocks)`
*   **Range**: -1.0 to +1.0
*   **Implementation**: The system iterates through every stock in the sector universe. It checks the live LTP against the day's Volume Weighted Average Price (VWAP).
*   **Logic**: If 90% of Bank Nifty stocks are above VWAP, the index *must* rise. Breadth is a leading indicator that ignores index manipulation by heavyweight stocks.

#### **2. Market Gravity / Nifty Vector (Weight: 30)**
*   **Concept**: External Bias / Safety Anchor.
*   **Formula**: `Nifty_Intraday_Change_Pct * 30`
*   **Logic**: "Don't fight the tape."
    *   If Nifty is **+1.0%**, every sector gets **+30 points**. This lifts weak bullish sectors into buy territory.
    *   If Nifty is **-1.0%**, every sector gets **-30 points**. This crushes weak bullish signals and amplifies bearish signals.

#### **3. Intraday Relative Strength (Weight: 20)**
*   **Concept**: Daily Velocity.
*   **Formula**: `(Sector_Day_Change% - Nifty_Day_Change%)`
*   **Logic**: Captures immediate outperformance. If Sector is up 2% and Nifty is up 0.5%, the RS is +1.5%. This identifies where the money is rotating *today*.

#### **4. Short-Term Relative Strength (Weight: 10)**
*   **Concept**: Swing Momentum (3-Day).
*   **Formula**: `(Sector_3D_Return - Nifty_3D_Return)`
*   **Logic**: Filters out "One-Day Wonders." It ensures the current move aligns with the momentum of the current week.

#### **5. Structural Relative Strength (Weight: 3)**
*   **Concept**: Historical Legacy (20-Day).
*   **Formula**: `(Sector_20D_Return - Nifty_20D_Return)`
*   **Logic**: Minimal impact. Acts as a slight tie-breaker favoring long-term trend leaders.

### 3.3 Dynamic Selection (`select_top_n`)
The system does not just pick the Top 3. It uses **Score Spreads**:
*   If `Score(Rank 1)` is > 15 points higher than `Score(Rank 5)`, it selects **Top 3** (Concentrated Trend).
*   Otherwise, it selects **Top 5** (Broad Trend).
*   **Bias Check**: Sectors with a score between `-10` and `+10` are labeled **NEUTRAL** and discarded.

---

## 4. The Signal Engine (The Execution Filter)

**Objective**: Filter individual stocks from the "Hot Sectors" to find actionable setups.

### 4.1 The 10-Point Scorecard
Every candidate stock is graded. Only **Grade A (7-8)** and **Grade A+ (9-10)** are traded.

#### **1. HMA Alignment (3 Points)** - *The Golden Rule*
*   **Indicators**:
    *   **Daily HMA(9)**: Tactical Trend.
    *   **Intraday HMA(20)**: Execution Trend (calculated on 5-min candles).
*   **Long Condition**: Price > Both HMAs **AND** `Slope(HMA9) == UP` **AND** `Slope(HMA20) == UP`.
*   **Short Condition**: Price < Both HMAs **AND** `Slope(HMA9) == DOWN` **AND** `Slope(HMA20) == DOWN`.
*   **Why?**: Hull Moving Average (HMA) has extremely low lag compared to SMA/EMA. Aligning two timeframes ensures we are not buying a pullback in a downtrend.

#### **2. Relative Volume / RVOL (2 Points)** - *The Fuel*
*   **Logic**: `Current_5m_Volume / Average_Volume_Last_20_Bars`
*   **Lookback**: Uses a rolling 20-bar (100 minute) window. This is superior to a Daily Average because it compares "Now" vs "Recent Context," automatically adjusting for time-of-day volume curves.
*   **Requirement**: `RVOL > 1.5x` (Variable based on VIX). A breakout without volume is a trap.

#### **3. StochRSI Oscillator (2 Points)** - *The Timing*
*   **Indicator**: StochRSI (14, 14, 3, 3) on 5-min candles.
*   **Logic (Long)**:
    *   **Invalid**: `K > 80` (Overbought - chasing).
    *   **Valid**: `K < 80`. Extra points if `K < 20` (Oversold Bounce).
*   **Why?**: Prevents buying at the exact top of a candle extension.

#### **4. Sector Rank (2 Points)** - *The Tailwind*
*   **Logic**: If the stock belongs to the **Rank #1** sector, it gets max points.
*   **Why?**: Being in the hottest sector acts as a "Probability Multiplier." Even a mediocre technical setup often works if the sector inflow is massive.

#### **5. Spread Quality (1 Point)** - *The Cost*
*   **Formula**: `(Ask_Price - Bid_Price) / ATR`.
*   **Logic**: Awards a point if the spread is tight (`< 10%` of ATR).
*   **Why?**: Slippage kills intraday alpha. We prefer liquid stocks.

### 4.2 The Safety Gate
After grading, a stock must pass a binary **PASS/FAIL** gate.
1.  **Spread Limit**: If Spread > 25% of ATR, **FAIL** (Too expensive).
2.  **Circuit Limit**: If Price is within 2% of Upper/Lower Circuit, **FAIL** (Liquidity Trap risk).

---

## 5. Execution Context: The Playbook

The system adapts its rules based on **Time** and **Volatility**.

### 5.1 Time-Based Phases (IST)
| Phase | Time | Action | Logic Adjustment |
| :--- | :--- | :--- | :--- |
| **PRE** | < 09:15 | Boot | Load Data, Cache History. |
| **WAIT** | 09:15-09:20 | Wait | Volatility Stabilization. No trades. |
| **ORB** | 09:35-10:05 | **Trade** | **Strict Mode**: Spread Limit tightens to 15% ATR. RVOL Threshold increases (need more conviction). |
| **MAIN** | 10:10-14:05 | **Trade** | **Standard Mode**: Spread Limit 25% ATR. Normal RVOL. |
| **LUNCH** | 12:00-13:15 | **Trade** | **Low Vol Mode**: Position Size scaled to **0.7x** to account for chop. |
| **EXIT** | 14:05-15:05 | Manage | No new entries. Only manage existing stops/targets. |
| **FORCE** | > 15:05 | Close | Market Exit all open positions. |

### 5.2 Market Regime (VIX Percentile)
The system calculates the 20-day percentile of **India VIX**.
*   **TRENDING (Low VIX)**: `Multiplier = 1.2x`. Market is calm; trends persist.
*   **NEUTRAL (Normal VIX)**: `Multiplier = 1.0x`.
*   **MEAN REVERT (High VIX)**: `Multiplier = 0.8x`. Trends are whippy.
*   **EXTREME (Panic)**: `Multiplier = 0.75x`. Survival mode.

---

## 6. Lifecycle Management (Trade Handling)

Once a trade is entered, the `LifecycleManager` takes over.

### 6.1 Sizing Formula
`Shares = (Account_Equity * 0.5% * Grade_Mult * VIX_Mult) / (Entry - Stop_Price)`
*   **Base Risk**: 0.5% of Equity per trade.
*   **Grade Mult**: A+ (1.0), A (0.85).

### 6.2 Stop & Target Logic
1.  **Initial Stop**: Placed at `2.0 * ATR` from entry.
2.  **Target 1 (1.5R)**:
    *   Trigger: Price hits `Entry + (Risk * 1.5)`.
    *   Action: Close **50%** of position.
    *   Stop Update: Move Stop Loss to **Breakeven** (`Entry Price`).
3.  **Trailing (Chandelier)**:
    *   Logic: `Highest_High_Last_10_Bars - (3.0 * ATR)`.
    *   Update: Only moves in the direction of profit. Never loosens.

### 6.3 Hard Exits
*   **Time Exit**: At 15:05, all positions are closed.
*   **Signal Flip**: If the Parent Sector flips bias (e.g., Long to Short), the trade is forced closed immediately.

---

## 7. Risk Limits & Kill Switches

**File**: `execution_v4/risk_v4.py`

### 7.1 Portfolio Constraints
*   **Max Concurrent Trades**: 6.
*   **Max Exposure Per Sector**: 2 Stocks. (Prevents over-concentration in one industry).
*   **Max Exposure Per Stock**: 1 Trade (No pyramiding).

### 7.2 Drawdown Kill Switches
*   **Warning (-1.0% Day)**: If daily PnL hits -1%, all future trade sizes are cut by **50%**.
*   **HALT (-2.0% Day)**: If daily PnL hits -2%, the bot **Stops Trading** for the day.
*   **VIX Halt (>90th Pctl)**: If VIX screams into the 90th percentile (Crash Mode), new entries are blocked (or severely restricted).
