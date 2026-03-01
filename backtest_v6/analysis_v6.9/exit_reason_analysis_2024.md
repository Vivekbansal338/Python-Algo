# V6.9 Exit Reason Analysis - All Backtests

**Analysis Period**: 2023-2025  
**Data Source**: `backtest_v6/history_v6.9/`

---

## Summary Comparison

| Year | HMA Config | Trades | STOP_HARD % | STOP_HARD PnL | Win% | Total PnL |
|------|------------|--------|-------------|---------------|------|-----------|
| 2023 | 18/126 | 120 | 40.8% | -1,24,476 | 36.7% | +20,007 |
| 2024 | 18/126 | 182 | 42.9% | -2,48,984 | 40.7% | +29,902 |
| 2025-R1 | 18/55 | 267 | 42.3% | -3,14,396 | 40.4% | -76,245 |
| 2025-R2 | 18/126 | 151 | 41.7% | -1,64,624 | 47.7% | +97,734 |

---

## Detailed Exit Reason Tables

### 2023 (18/126) - 2023-01-01 to 2023-12-31 (120 trades)

| Exit Reason        | Trades | Wins | Loss | MFE Avg | MFE Max | MAE Avg | MAE Max | Target | Trail | Avg PnL |
|--------------------|--------|------|------|---------|---------|---------|---------|--------|-------|---------|
| STOP_HARD          |     49 |   11 |   38 |    0.79R |    2.49R |    1.13R |    3.50R |   11/49 |    0/49 |  -2,540 |
| STOP_HMA_TRAIL     |     57 |   19 |   38 |    1.63R |   10.71R |    0.68R |    1.93R |   17/57 |   57/57 |     613 |
| HMA_CROSS_EXIT     |     10 |   10 |    0 |    3.50R |    6.75R |    0.29R |    0.68R |    8/10 |   10/10 |   7,285 |
| FORCE_EXIT         |      4 |    4 |    0 |    7.25R |   13.28R |    0.53R |    0.97R |    4/4 |    4/4 |   9,167 |
| **TOTAL**          |    120 |   44 |   76 |    1.63R |   13.28R |    0.83R |    3.50R |    40   |    71   |     167 |

### 2024 (18/126) - 2024-01-01 to 2024-12-31 (182 trades)

| Exit Reason        | Trades | Wins | Loss | MFE Avg | MFE Max | MAE Avg | MAE Max | Target | Trail | Avg PnL |
|--------------------|--------|------|------|---------|---------|---------|---------|--------|-------|---------|
| STOP_HARD          |     78 |   12 |   66 |    0.80R |    3.52R |    1.21R |    2.79R |   12/78 |    0/78 |  -3,192 |
| STOP_HMA_TRAIL     |     83 |   41 |   42 |    1.95R |   12.87R |    0.59R |    1.59R |   33/83 |   83/83 |   1,451 |
| HMA_CROSS_EXIT     |     14 |   14 |    0 |    2.89R |    4.81R |    0.47R |    0.99R |   11/14 |   14/14 |   6,704 |
| FORCE_EXIT         |      5 |    5 |    0 |    4.54R |   10.80R |    0.25R |    0.41R |    5/5 |    5/5 |   9,408 |
| SAFETY_HALT        |      2 |    2 |    0 |    3.20R |    3.28R |    0.00R |    0.00R |    2/2 |    0/2 |   8,761 |
| **TOTAL**          |    182 |   74 |  108 |    1.61R |   12.87R |    0.83R |    2.79R |    63   |   102   |     164 |

### 2025-R1 (18/55) - 2025-01-01 to 2025-12-31 (267 trades)

| Exit Reason        | Trades | Wins | Loss | MFE Avg | MFE Max | MAE Avg | MAE Max | Target | Trail | Avg PnL |
|--------------------|--------|------|------|---------|---------|---------|---------|--------|-------|---------|
| STOP_HARD          |    113 |   20 |   93 |    0.72R |    4.10R |    1.23R |    2.94R |   20/113|    0/113|  -2,782 |
| STOP_HMA_TRAIL     |    139 |   75 |   64 |    1.93R |   14.54R |    0.55R |    2.00R |   56/139|  139/139|   1,357 |
| HMA_CROSS_EXIT     |     12 |   10 |    2 |    1.81R |    5.88R |    0.35R |    0.96R |    5/12 |   12/12 |   3,429 |
| FORCE_EXIT         |      1 |    1 |    0 |    5.17R |    5.17R |    0.09R |    0.09R |    1/1 |    1/1 |   8,327 |
| **TOTAL**          |    267 |  108 |  159 |    1.42R |   14.54R |    0.83R |    2.94R |    84   |   153   |    -286 |

### 2025-R2 (18/126) - 2025-01-01 to 2025-12-31 (151 trades)

| Exit Reason        | Trades | Wins | Loss | MFE Avg | MFE Max | MAE Avg | MAE Max | Target | Trail | Avg PnL |
|--------------------|--------|------|------|---------|---------|---------|---------|--------|-------|---------|
| STOP_HARD          |     63 |   15 |   48 |    0.76R |    3.43R |    1.20R |    2.37R |   15/63 |    0/63 |  -2,613 |
| STOP_HMA_TRAIL     |     59 |   31 |   28 |    1.98R |   16.94R |    0.52R |    1.22R |   26/59 |   59/59 |   1,963 |
| HMA_CROSS_EXIT     |     21 |   18 |    3 |    2.68R |    6.19R |    0.38R |    0.88R |   16/21 |   21/21 |   4,821 |
| FORCE_EXIT         |      6 |    6 |    0 |    3.11R |    4.58R |    0.49R |    0.88R |    6/6 |    6/6 |   7,544 |
| **TOTAL**          |    151 |   72 |   79 |    1.61R |   16.94R |    0.78R |    2.37R |    65   |    86   |     647 |

---

## Key Observations

1. **STOP_HARD is consistently ~40-43%** of all trades across all runs - this is the main loss maker
2. **HMA_CROSS_EXIT has 100% win rate** (except 2025-R1 with 2 losses)
3. **Lower HMA_SLOW (55)** in 2025-R1 generated more trades but LOWER performance
4. **Higher HMA_SLOW (126)** consistently better - especially 2025-R2 with 47.7% win rate

---

## STOP_HARD Analysis (2024 as reference)

### What is STOP_HARD?

| Exit Reason        | Trades | Wins | Loss | MFE Avg | MFE Max | MAE Avg | MAE Max | Target Hit | Trail Active | Win PnL  | Loss PnL  | Capture % |
|--------------------|--------|------|------|---------|---------|---------|---------|------------|--------------|----------|-----------|-----------|
| STOP_HARD          | 78     | 12   | 66   | 0.80R   | 3.52R   | 1.21R   | 2.79R   | 12/78      | 0/78         | +2,857   | -4,292    | 66%       |
| STOP_HMA_TRAIL     | 83     | 41   | 42   | 1.95R   | 12.87R  | 0.59R   | 1.59R   | 33/83      | 83/83        | +5,400   | -2,403    | 135%      |
| HMA_CROSS_EXIT     | 14     | 14   | 0    | 2.89R   | 4.81R   | 0.47R   | 0.99R   | 11/14      | 14/14        | +6,704   | 0         | 146%      |
| FORCE_EXIT         | 5      | 5    | 0    | 4.54R   | 10.80R  | 0.25R   | 0.41R   | 5/5        | 5/5          | +9,408   | 0         | 254%      |
| SAFETY_HALT        | 2      | 2    | 0    | 3.20R   | 3.28R   | 0.00R   | 0.00R   | 2/2        | 0/2          | +8,761   | 0         | 211%      |
| **TOTAL**          | 182    | 74   | 108  | 1.61R   | 12.87R  | 0.83R   | 2.79R   | 63         | -            | +5,596   | -3,557    | -         |

---

## STOP_HARD Analysis

### What is STOP_HARD?

STOP_HARD occurs when the trade exits via the **initial hard stop** - the stop that was set at entry time. This stop is **static** (never moves unless HMA trail activates or target is hit).

### Conditions for Each STOP_HARD Outcome:

#### 1. STOP_HARD with LOSS (66 trades)
- **Neither HMA trail activated NOR HMA cross happened**
- Price moved against position before either could help
- Trade hit the static initial stop
- Avg MFE: 0.53R (price went in our favor briefly)
- Avg MAE: 1.34R (then reversed and hit stop)

**Flow:**
```
Entry at 100 → Stop at 96 (1.4 × ATR)
Price goes to 98 (MFE = 0.5R) ✓
HMA_SLOW still below 96 → No trail activation ✗
Price drops to 95 → Hits stop → STOP_HARD with LOSS
```

#### 2. STOP_HARD with WIN (12 trades)
- **Target (1.5R) was hit first (be_armed = True)**
- 50% of position sold at profit
- Remaining 50% stop moved to breakeven (entry price)
- Then price reversed and hit the breakeven stop
- Still a WIN because 50% was already taken at profit

**Flow:**
```
Entry at 100 → Stop at 96
Price goes to 106 → Target hit (1.5R) ✓
50% sold at 106 → Profit taken
Remaining 50% stop moved to 100 (breakeven)
Price drops to 100 → Hits stop → STOP_HARD
Final: 50% profit + 50% breakeven = WIN
```

### Key Insight: Why STOP_HARD is Problematic

1. **HMA_SLOW too slow**: With HMA_SLOW = 126, it takes many bars for HMA_SLOW to rise above the initial stop
2. **Quick moves miss HMA**: Trades hitting target in 3-6 bars (avg 5.9 bars) never give HMA time to activate
3. **78 trades (43%)** hit STOP_HARD
4. **Total PnL from STOP_HARD: -248,984** (huge loss maker)

### Summary

| STOP_HARD Type | Count | What Happened |
|----------------|-------|---------------|
| LOSS | 66 | Never hit target, HMA trail never activated, hit initial stop |
| WIN | 12 | Hit target first (be_armed), 50% profit taken, remaining hit breakeven stop |

The be_armed flag indicates the target was hit, which moves the stop to breakeven - this is why some STOP_HARD trades are still winners.
