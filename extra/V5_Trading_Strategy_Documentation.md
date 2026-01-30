# V5 Trading Strategy - Complete Breakdown

## 1. MARKET STRUCTURE & TIMING (Playbooks)

The trading day is divided into distinct phases with different entry rules:

| Phase | Time (IST) | Strategy |
|-------|-----------|----------|
| **PRE_MARKET** | Before 09:15 | No trading, initialization only |
| **WAIT** | 09:15 - 09:20 | Market open, wait for OR formation |
| **OR_FORMATION** | 09:20 - 09:34 | Opening Range being established |
| **ORB** | 09:35 - 10:05 | **Opening Range Breakout** - Aggressive entries allowed |
| **GAP** | 10:05 - 10:10 | No new entries (gap period) |
| **MAIN** | 10:10 - 14:05 | Normal trading with relaxed criteria |
| **EXIT_ONLY** | 14:05 - 15:05 | No new entries, manage existing positions |
| **FORCE_EXIT** | 15:05 onwards | Hard square-off all positions |

**Key Differences Between Playbooks:**
- **ORB Mode (09:35-10:05)**: Strict microstructure (spread/ATR ≤ 15%), circuit buffer ≥ 3%, RVOL thresholds higher (1.8→1.2 based on VIX), stop distance = 2.4×ATR
- **MAIN Mode (10:10-14:05)**: Relaxed microstructure (spread/ATR ≤ 25%), circuit buffer ≥ 2%, RVOL thresholds lower (1.5→1.0), stop distance = 2.0×ATR

---

## 2. MARKET REGIME DETECTION (VIX-Based)

**VIX Percentile Calculation:**
- Uses 20-day rolling window of VIX closes
- Percentile = (count of days VIX was below current) / 20 × 100

**Regime Classification:**
| VIX Percentile | Regime | Multiplier | Meaning |
|---------------|--------|-----------|---------|
| ≤ 20% | TRENDING | 1.20× | Low volatility, strong trends |
| 20-50% | NEUTRAL | 1.00× | Normal market conditions |
| 50-75% | ELEVATED | 0.80× | Rising volatility, caution |
| ≥ 75% | MEAN_REVERT | 0.75× | High volatility, expect reversions |
| ≥ 90% | EXTREME | 0.75× | Crisis mode, minimal exposure |

**Position Size Formula:**
```
Risk Amount = Equity × 0.5% × GradeMultiplier × VIXMultiplier × DayStateMultiplier
Shares = Risk Amount / |Entry - Stop|
```

---

## 3. SECTOR SELECTION STRATEGY (Rank-Based)

### Step 1: Calculate Sector Metrics (Real-Time)

For each sector, calculate six components using **Previous Close** as anchor (V5 Fix):

1. **Structural RS** (20-day): `(Sector 20d Return - Nifty 20d Return) × 100` (Weight: 3.0)
2. **Short-term RS** (3-day): `(Sector 3d Return - Nifty 3d Return) × 100` (Weight: 10.0)
3. **Daily RS** (vs Prev Close): `(Sector Daily% - Nifty Daily%) × 100` (Weight: 20.0)
4. **Breadth** (Net): `(Above VWAP% - Below VWAP%)` (Weight: 40.0)
5. **Market Gravity**: `Nifty Daily% × 30` (Weight: 30.0)

### Step 2: Composite Score & Ranking

```
Composite Score = Σ(Component × Weight)
```

**Bias Determination:**
- Score ≥ +10.0 → LONG bias
- Score ≤ -10.0 → SHORT bias
- Between -10 and +10 → NEUTRAL

**Sorting:** Sectors ranked by **absolute magnitude** of composite score (strong bears rank alongside strong bulls)

### Step 3: Dynamic N Selection

- Calculate spread between #1 and #5 ranked sectors
- If spread ≥ 15.0 points: Select **Top 3** sectors
- If spread < 15.0 points: Select **Top 5** sectors
- Only select sectors with directional bias (LONG/SHORT, not NEUTRAL)

**V5 Key Fix:** All percentage changes use **Previous Close** (ohlc.close from API) instead of Today's Open, aligning with broker terminal calculations.

---

## 4. STOCK GRADING SYSTEM (A+/A/B/C)

### Pre-Filter: Liquidity Check
- Calculate 20-day Average Daily Value (ADV) in Crores
- ADV = (Price × Volume) / 10^7
- **Minimum ADV: ₹75 Crores** (execution_v5/strategy_v5.py:663)

### Technical Indicators Required

**A. HMA (Hull Moving Average) Alignment - 3 Points**
- Uses 2-layer HMA: Daily HMA-9 + 5-min HMA-20
- **BULLISH**: Price > HMA9 (UP slope) AND Price > HMA20 (UP slope)
- **BEARISH**: Price < HMA9 (DOWN slope) AND Price < HMA20 (DOWN slope)
- **MIXED**: Any other combination

**B. RVOL (Relative Volume) - 2 Points**
- Uses last 20 5-minute volume bars
- RVOL = Current Volume / 20-bar Average
- Thresholds vary by playbook and VIX:
  - ORB: 1.8 (low VIX) → 1.2 (high VIX)
  - MAIN: 1.5 (low VIX) → 1.0 (high VIX)

**C. StochRSI - 2 Points**
- Stochastic RSI (K, D) with 14-period RSI, 14-period Stoch, 3-period smoothing
- **LONG confirmation**: StochK < 20 (oversold)
- **SHORT confirmation**: StochK > 80 (overbought)

**D. Sector Rank - 2 Points**
- Top 3 sector: +2 points
- Top 5 sector: +1 point
- Rank 6+: 0 points

**E. Spread Quality - 1 Point**
- Spread/ATR ratio vs playbook limit:
  - < 50% of limit: +1 point (superior quality)
  - ≥ 50% of limit: 0 points

### Scoring & Grading (0-10 Scale)

| Total Score | Grade | Risk Multiplier | Action |
|-------------|-------|----------------|---------|
| ≥ 9 | A+ | 1.00× | Immediate entry if gate passes |
| 7-8 | A | 0.85× | Entry allowed |
| 4-6 | B | 0.60× | Monitor, no entry |
| < 4 | C | 0.00× | Reject |

**Grade C Immediate Disqualifiers:**
- RVOL below threshold
- HMA direction = NONE (MIXED)
- StochRSI showing divergence (overbought for LONG, oversold for SHORT)

**Directional Filter (V5 Addition):**
- If sector bias = LONG but signal = SHORT → Grade demoted to C
- If sector bias = SHORT but signal = LONG → Grade demoted to C
- If sector bias = NEUTRAL → Grade demoted to C

---

## 5. MICROSTRUCTURE GATE (Binary Pass/Fail)

Before any entry, stock must pass the **Execution Gate**:

### Gate Check 1: Spread/ATR Ratio
- **ORB Mode**: Spread ≤ 15% of ATR
- **MAIN Mode**: Spread ≤ 25% of ATR
- Bid-Ask spread calculated from market depth (top level)

### Gate Check 2: Circuit Buffer
- Distance from price to upper/lower circuit limit
- **ORB Mode**: Buffer ≥ 3% from circuit
- **MAIN Mode**: Buffer ≥ 2% from circuit
- Prevents entries too close to price limits

### Gate Check 3: Market Data Validity
- Price > 0
- ATR > 0
- Market depth available (bid > 0, ask > 0)

**Visibility vs Execution:**
- **ALL signals** (A+, A, B, C) displayed in UI for monitoring
- **ONLY A+ and A grades** with gate_passed = True are eligible for entry

---

## 6. RISK MANAGEMENT ARCHITECTURE

### Layer 1: Position Sizing
```
Base Risk = Equity × 0.5%
Grade Multiplier: A+(1.0), A(0.85), B(0.60), C(0.0)
VIX Multiplier: 1.20 → 0.75 (based on percentile)
Day State Multiplier:
  - Lunch (12:00-13:15): 0.70×
  - Daily DD Warning (-1%): 0.50×
  
Total Risk = Base × Grade × VIX × DayState
Shares = Total Risk / StopDistance
```

**Minimum Size:** Must be ≥ 1 share, else rejected

### Layer 2: Stop Loss Calculation
- **ORB**: Stop = Entry ± (2.4 × ATR)
- **MAIN**: Stop = Entry ± (2.0 × ATR)
- Direction: Long = below entry, Short = above entry

### Layer 3: Target Calculation
- Target 1 = Entry ± (1.5 × Risk)
- Risk = |Entry - Stop|
- Example: Entry 100, Stop 98 (2% risk), Target = 103 (3% gain)

### Layer 4: Portfolio Constraints
- **Max Positions**: 6 concurrent trades
- **Max Per Sector**: 2 positions per sector
- **Max Per Stock**: 1 position per symbol (no doubling up)
- **Correlation**: Threshold 0.70 (not currently enforced in code)

### Layer 5: Kill Switches (System Halts)

**Daily Drawdown Protection:**
- Warning at -1.0%: Reduce size to 50%
- Halt at -2.0%: Stop all new entries

**Safety Monitor Halts (Real-Time):**
- **Flash Crash**: Nifty drops > 3% in 5 minutes
- **VIX Spike**: VIX rises > 15% in 5 minutes
- **Breadth Collapse**: > 70% of stocks below VWAP

---

## 7. TRADE LIFECYCLE MANAGEMENT

### Stage 1: PENDING → ACTIVE
- Entry order placed (limit order at current price)
- Initial stop-loss placed (SL-M order at calculated stop)
- Trade registered with:
  - Entry price, quantity, direction
  - Initial stop, Target 1, ATR at entry
  - Highest/Lowest price tracking (for trailing)

### Stage 2: ACTIVE Monitoring
- Track high/low prices since entry
- Check exit conditions every tick:
  1. **Stop Loss Hit**: Close full position immediately
  2. **Target 1 Hit**: Execute Stage 2 exit

### Stage 3: PARTIAL Exit (Target 1 Hit)
- **Close 50% of position** at 1.5R target
- **Move stop to breakeven** (entry price)
- **Stage changes to PARTIAL**
- Remaining 50% continues with trailing stop

### Stage 4: Trailing Stop (Chandelier)

**Calculation (refreshed every 60 seconds):**
1. Fetch last 10 5-minute bars
2. Find highest high (for LONG) or lowest low (for SHORT)
3. Chandelier Stop = Extreme ± (3.0 × ATR at entry)
4. **Only moves in favor of trade** (ratchet mechanism)

**For LONG:**
- New stop = max(Lookback High, Trade High) - (3 × ATR)
- Only update if new stop > current stop

**For SHORT:**
- New stop = min(Lookback Low, Trade Low) + (3 × ATR)
- Only update if new stop < current stop

### Stage 5: Full Exit
- Stop hit (initial or trailing) → Close remaining 50%
- Manual force exit (15:05 cutoff) → Close all
- Trade status: CLOSED

---

## 8. DATA MANAGEMENT STRATEGY

### Historical Data (Cached)

**Daily History (45-60 days):**
- Nifty 50: Daily OHLCV for regime/RS calculations
- Sectors: Daily closes for RS calculations
- Stocks: Daily OHLCV for ATR, HMA, StochRSI

**Intraday History (5 days):**
- 5-minute candles for RVOL calculation
- 5-minute candles for HMA-20 calculation

### Real-Time Data (WebSocket)

**V5 Fix: Periodic Refresh Strategy**
- WebSocket provides live ticks continuously
- Every **5 minutes (300 seconds)**: Re-fetch 5m history for:
  - Selected sector stocks
  - Active positions
- This prevents RVOL/HMA "memory loss" from stale data

**Live Tick Buffer:**
- Stores latest tick for each instrument token
- Includes: last_price, volume, average_price (VWAP), depth, circuit limits, ohlc

### Percentage Calculation Anchor (V5 Critical Fix)
- **Previous Close** (ohlc.close from quote API) used as baseline
- Not Today's Open (captures gap moves correctly)
- Aligns with broker terminal percentage displays

---

## 9. EXECUTION FLOW (Main Loop)

```
Every 0.5 seconds:
├── Check if 5-minute refresh needed → Update 5m history
├── Check if UI refresh (5 sec) needed:
│   ├── Recalculate live metrics (Nifty, Sectors)
│   ├── Update VIX percentile & multiplier
│   ├── Run safety monitor checks
│   ├── IF halted → Force exit all
│   └── ELSE → Scan for tradeable stocks
├── Update all active trades (lifecycle):
│   ├── Check stop hits
│   ├── Check target 1 hits
│   ├── Update trailing stops
│   └── Execute exits if needed
├── Check force exit time (15:05)
├── Save state every 60 seconds
└── Update UI display
```

**Sector Rank Update:**
- Recalculated every UI refresh (5 seconds)
- Uses live WebSocket ticks for current prices
- Updates composite scores, re-sorts, re-selects Top N

**Stock Scanning:**
- Only scans stocks in selected sectors
- Fetches history for missing symbols on-demand
- Calculates all indicators in real-time
- Grades all signals, displays all, trades only A+/A

---

## 10. KEY STRATEGY NUANCES

### Breadth Calculation
- Net Breadth = (% Above VWAP) - (% Below VWAP)
- Uses real-time average_price from ticks (intraday VWAP)
- Range: -1.0 to +1.0
- Weight: 40% of sector score (highest weight)

### HMA Calculation Details
- Daily HMA-9: Trend direction (strategic)
- 5m HMA-20: Entry timing (tactical)
- Both must align (BULLISH/BEARISH) for full 3 points
- MIXED = 1 point only

### Rejection Cooldown
- If position sizing rejects a symbol (risk too low)
- Symbol enters 5-minute cooldown
- Prevents repeated rejected entry attempts

### State Persistence
- Saves to JSON every 60 seconds
- Archives previous day state on new day
- Restores trades, positions, daily equity on restart
- Handles shutdown/restart gracefully

### Paper Trading Only
- V5 is strictly paper trading (config.IS_PAPER_TRADING = True)
- Simulates instant fills at current price
- Tracks paper P&L separately from real account
- Orders have order_id format: ORD_xxxxxxxx, SL_xxxxxxxx

---

## 11. COMPLETE ENTRY CHECKLIST

For a trade to execute, ALL must be true:

1. ✓ Playbook allows entry (ORB or MAIN phase)
2. ✓ Kill switch not active (daily DD < -2%)
3. ✓ Market not halted (safety monitor)
4. ✓ Portfolio limit not reached (< 6 positions)
5. ✓ Sector limit not reached (< 2 per sector)
6. ✓ Symbol not already in position
7. ✓ Symbol in selected sector (Top 3/5)
8. ✓ ADV ≥ ₹75 Crores
9. ✓ Gate passed (spread/ATR OK, circuit buffer OK)
10. ✓ Grade A+ or A (score ≥ 7)
11. ✓ Direction aligns with sector bias
12. ✓ Position size ≥ 1 share (calculated risk fits)
13. ✓ Not in rejection cooldown

---

This is the **complete V5 trading strategy**—a quantitative, sector-rotation system with real-time microstructure filtering, dynamic risk management, and systematic position sizing based on VIX regime and signal quality.
