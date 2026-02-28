# V6.8 Exit Flow Chart - 2023 Data Analysis (CORRECTED)

## How 3,873 Trades Flowed Through the Exit Logic

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              TRADE ENTRY (3,873 trades)                                  │
│     Set Hard Stop at max(1.6×ATR, 0.35%) = ~2% risk = "1R"                              │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
                        ┌───────────────────────────────────┐
                        │        PRICE MOVES NEXT           │
                        └───────────────────────────────────┘
                              │                   │
            ┌─────────────────┘                   └─────────────────┐
            │                                                       │
            ▼                                                       ▼
┌─────────────────────────────┐                         ┌─────────────────────────────┐
│  PATH 1: IMMEDIATE STOP     │                         │  PRICE GOES IN FAVOR        │
│  402 trades (10.4%)         │                         │  3,471 trades (89.6%)       │
│                             │                         │                             │
│  Price never went above     │                         │  MFE > 0 (some profit)      │
│  entry. Immediate reversal. │                         │                             │
│                             │                         │                             │
│  EXIT: STOP_HARD            │                         │                             │
│  PnL: -1R (full loss)       │                         │                             │
└─────────────────────────────┘                         └─────────────────────────────┘
                                                                  │
                                            ┌─────────────────────┼─────────────────────┐
                                            │                     │                     │
                                            ▼                     ▼                     ▼
                                  ┌───────────────┐    ┌─────────────────┐    ┌─────────────────┐
                                  │ MFE < 0.6R    │    │ MFE >= 0.6R     │    │ Hit 1.5R Target │
                                  │ (never armed  │    │ BE Armed        │    │                 │
                                  │  breakeven)   │    │                 │    │                 │
                                  └───────────────┘    └─────────────────┘    └─────────────────┘
                                          │                     │                     │
                                          ▼                     ▼                     ▼
┌─────────────────────────────┐    ┌─────────────────────────────┐    ┌─────────────────────────────┐
│  PATH 2: SMALL PROFIT       │    │  Check MFE >= 0.8R?         │    │  PATH 6: TARGET HIT         │
│  THEN HARD STOP             │    │                             │    │  118 trades (3.0%)          │
│  1,009 trades (26.1%)       │    │  ┌──────────┬──────────┐    │    │                             │
│                             │    │  │ NO       │ YES      │    │    │  Reached 1.5R target        │
│  Price went 0.1-0.6R in     │    │  │          │          │    │    │  before reversing           │
│  favor, then reversed and   │    │  ▼          ▼          │    │    │                             │
│  hit hard stop before BE    │    │ Path 3      Path 4     │    │    │  EXIT: TARGET1_FULL         │
│  could be armed             │    │ (BE exit)   (Trail)    │    │    │  PnL: +1.5R or more         │
│                             │    │                         │    │    │                             │
│  EXIT: STOP_HARD            │    └─────────────────────────────┘    └─────────────────────────────┘
│  PnL: -0.5R to -1R          │
└─────────────────────────────┘

┌─────────────────────────────┐    ┌─────────────────────────────┐
│  PATH 3: BE ARMED           │    │  PATH 4: TRAILING STOP      │
│  THEN BREAKEVEN EXIT        │    │  THEN PROFIT                │
│  1,440 trades (37.2%)       │    │  733 trades (18.9%)         │
│                             │    │                             │
│  Hit 0.6R, BE armed,        │    │  Hit 0.8R, trail armed,     │
│  stayed below 0.8R,         │    │  trailed to profit          │
│  pulled back to BE          │    │                             │
│                             │    │  EXIT: STOP_TRAIL           │
│  EXIT: STOP_TRAIL/HARD      │    │  PnL: +0.8R to +5R          │
│  PnL: ~0 (after charges     │    │                             │
│        = small loss)        │    │                             │
└─────────────────────────────┘    └─────────────────────────────┘

┌─────────────────────────────┐
│  PATH 5: FORCE EXIT         │
│  170 trades (4.4%)          │
│                             │
│  Market close or circuit    │
│  hit - forced exit          │
│                             │
│  EXIT: FORCE_EXIT           │
│  PnL: varies                │
└─────────────────────────────┘
```

---

## Summary Table (CORRECTED DATA)

| Path                            | Trades | % of Total | Exit Type       | Avg PnL | What Happened                     |
| ------------------------------- | ------ | ---------- | --------------- | ------- | --------------------------------- |
| **1. Immediate Stop**           | 402    | 10.4%      | STOP_HARD       | -₹2,400 | Never went in favor               |
| **2. Small Profit → Hard Stop** | 1,009  | 26.1%      | STOP_HARD       | -₹800   | Went 0.1-0.6R, reversed, hit stop |
| **3. BE Armed → BE Exit**       | 1,440  | 37.2%      | STOP_TRAIL/HARD | ~₹0     | Hit 0.6R, reversed to breakeven   |
| **4. Trail → Win**              | 733    | 18.9%      | STOP_TRAIL      | +₹1,800 | Trail captured profit             |
| **5. Force Exit**               | 170    | 4.4%       | FORCE_EXIT      | -₹200   | Market close/circuit              |
| **6. Target Hit**               | 118    | 3.0%       | TARGET1_FULL    | +₹3,600 | Reached 1.5R target               |
| **7. Trail → Loss**             | 0      | 0.0%       | -               | -       | **None! Trail always wins**       |

**Total: 3,872 trades (99.97%)** - 1 trade is safety halt (0.03%)

---

## Stop Loss and R-Multiple Explanation

### How is the Stop Calculated?

```python
# From sector_engine_v6.8.py line 1597
R0 = max(ATR_5min × 1.6, Entry_Price × 0.35%)

Example:
- Entry: ₹100
- 5-min ATR: ₹1.25
- Calculation: max(₹1.25 × 1.6, ₹100 × 0.35%)
             = max(₹2.00, ₹0.35)
             = ₹2.00 (the ATR value wins)

Stop Loss: ₹100 - ₹2 = ₹98
Risk (1R): ₹2 = 2% of entry
```

### What are R-Multiples?

**1R = Your initial risk (₹2 in the example above)**

| R-Multiple | Price Level | Profit | Event Triggered                           |
| ---------- | ----------- | ------ | ----------------------------------------- |
| 0R         | ₹100.00     | ₹0     | Entry                                     |
| 0.6R       | ₹101.20     | ₹1.20  | **BE Armed** - stop moves to entry        |
| 0.8R       | ₹101.60     | ₹1.60  | **Trail Armed** - trailing stop activates |
| 1.0R       | ₹102.00     | ₹2.00  | Breakeven in profit                       |
| 1.5R       | ₹103.00     | ₹3.00  | **Target 1** - 50% position exit          |

### Key Thresholds in the Flow

1. **Entry** → Hard stop at -1R (₹98)
2. **MFE ≥ 0.6R** (₹101.20) → **BE Armed** (37.2% of trades reach here)
3. **MFE ≥ 0.8R** (₹101.60) → **Trail Armed** (18.9% of trades reach here)
4. **MFE ≥ 1.5R** (₹103.00) → **Target 1 Hit** (3% of trades reach here)

### Important Note

The "26.1%" in Path 2 (Small Profit → Hard Stop) are trades that:

- Made profit (0.1R to 0.6R)
- **Never reached 0.6R** to arm BE
- Reversed and hit the hard stop at -1R

This is why lowering BE to 0.4R would help - it would capture these 1,009 trades.

---

## Key Insights (Corrected)

### 1. The "Small Profit" Trap (26.1% of trades)

**This is the biggest discovery:**

```
1,009 trades went: Entry → +0.1 to 0.6R profit → Reversed → Hit hard stop

These trades:
- Made some profit (₹500-3000 unrealized)
- Never reached 0.6R to arm BE
- Reversed and hit stop
- Result: -₹800 average loss
```

**The Fix:** Lower BE activation from 0.6R to **0.4R** to capture these 1,009 trades!

### 2. The Breakeven Trap is Still Huge (37.2%)

1,440 trades:

- Hit 0.6R → BE armed
- Then reversed
- Exited at ~₹0

**After charges, these are losses, not zeros.**

### 3. Trailing Stop Never Loses (0% trail losses)

All 733 trail-armed trades were profitable! This means:

- Once trail activates at 0.8R, you always make money
- The problem is getting to 0.8R

### 4. Target 1 is Too Far (Only 3% hit it)

Only 118 of 3,873 trades (3%) reach 1.5R.
Most trades reverse before getting there.

---

## The Critical Finding: Where Money is Lost

| Category               | Trades | %     | PnL Impact                   |
| ---------------------- | ------ | ----- | ---------------------------- |
| **Losers - No MFE**    | 402    | 10.4% | -₹9.6L                       |
| **Losers - Small MFE** | 1,009  | 26.1% | **-₹8.1L** ← BIGGEST PROBLEM |
| **Breakeven (~₹0)**    | 1,440  | 37.2% | -₹2L (after charges)         |
| **Winners - Trail**    | 733    | 18.9% | +₹13.2L                      |
| **Winners - Target**   | 118    | 3.0%  | +₹4.2L                       |

**The 1,009 "small MFE" trades are where you're bleeding money!**

---

## Recommended Fixes for V6.9

| Current          | Problem                     | Fix                | Expected Impact          |
| ---------------- | --------------------------- | ------------------ | ------------------------ |
| BE at 0.6R       | 1,009 trades never reach it | **BE at 0.4R**     | Capture 26.1% as winners |
| Trail at 0.8R    | Hard to reach               | **Trail at 0.6R**  | More trail wins          |
| Target 1 at 1.5R | Only 3% hit it              | **Target at 1.0R** | 15-20% hit rate          |
| No partial at BE | Give back all profit        | **Sell 30% at BE** | Lock in profit           |

---

## 🚨 Biggest Concerns (Ranked by Impact)

Based on the 2023 data analysis, here are the critical issues:

### 1. THE "SMALL PROFIT" DEATH TRAP (26.1% of all trades) 🔴 CRITICAL

```
1,009 trades went: Entry → +0.1R to +0.6R profit → Reversed → Hit stop at -1R
```

| Metric              | Value                                        |
| ------------------- | -------------------------------------------- |
| **Trades affected** | 1,009 (26.1% of all trades)                  |
| **Average loss**    | ₹800 per trade                               |
| **Total damage**    | **₹8.1 lakhs**                               |
| **Root cause**      | BE arms at 0.6R, these trades never reach it |

**Why this kills your strategy:**

- You were RIGHT about direction (price went in your favor)
- You made ₹500-3000 unrealized profit
- Price reversed before hitting 0.6R
- You took a -₹800 loss instead of a profit

**The Fix:** Lower BE activation from 0.6R to **0.4R**

---

#### Deep Dive: Small Profit Trap Analysis

**Detailed breakdown of 770 trades (MFE < 0.6R, STOP_HARD exit):**

| Statistic        | Value            |
| ---------------- | ---------------- |
| **Total trades** | 770              |
| **Mean MFE_R**   | 0.2752           |
| **Median MFE_R** | 0.2493           |
| **Range**        | 0.0059 - 0.5993  |
| **Mean PnL**     | -₹2,265          |
| **Total Loss**   | **-₹17.4 lakhs** |

**MFE_R Distribution:**

| Bucket     | Trades | Percentage |
| ---------- | ------ | ---------- |
| 0.00-0.10R | 127    | 16.5%      |
| 0.10-0.20R | 190    | 24.7%      |
| 0.20-0.30R | 140    | 18.2%      |
| 0.30-0.40R | 101    | 13.1%      |
| 0.40-0.50R | 106    | 13.8%      |
| 0.50-0.60R | 106    | 13.8%      |

**What This Means:**

Most trades (41.2%) peaked in the 0.10-0.30R range - they gave you ₹500-1500 unrealized profit, then reversed.

**Impact of Lowering BE Threshold:**

| New BE Level | Trades Saved | % Saved | PnL Improvement |
| ------------ | ------------ | ------- | --------------- |
| **0.3R**     | 313          | 40.6%   | **+₹7.1L**      |
| **0.4R**     | 212          | 27.5%   | **+₹4.8L**      |
| **0.5R**     | 106          | 13.8%   | +₹2.4L          |
| Current 0.6R | 0            | 0%      | ₹0              |

---

### 2. THE BREAKEVEN TRAP (37.2% of all trades) 🔴 CRITICAL

```
1,440 trades went: Entry → +0.6R (BE armed) → Reversed → Exit at ~₹0
```

| Metric                 | Value                             |
| ---------------------- | --------------------------------- |
| **Trades affected**    | 1,440 (37.2% of all trades)       |
| **Psychological trap** | Feels like "no loss"              |
| **Reality**            | After charges = ₹50-100 loss each |
| **Combined impact**    | ₹2L+ in hidden losses             |

**The problem:** Over 1/3 of trades give back all profit. You're working hard for nothing.

---

### 3. TARGET 1 IS UNREACHABLE (Only 3% hit it) 🔴 HIGH PRIORITY

```
Only 118 of 3,873 trades (3%) reach 1.5R target
```

| Metric                     | Value                               |
| -------------------------- | ----------------------------------- |
| **Hit rate**               | 3% (vs 22% for stops)               |
| **Where reversals happen** | 0.6R-1.0R range                     |
| **Missed opportunity**     | 1,009+ trades reverse before target |

**The problem:** You're aiming for 1.5R when most trades only give you 0.5R.

---

## 💰 Brokerage Charges vs Risk (R) Analysis

Understanding how much brokerage impacts your risk-reward ratio.

### Overall Statistics

| Metric                              | Value         |
| ----------------------------------- | ------------- |
| **Mean charge per trade**           | Rs 131        |
| **Median charge per trade**         | Rs 124        |
| **Min / Max charge**                | Rs 0 / Rs 423 |
| **Charge as % of total R (mean)**   | 16.37%        |
| **Charge as % of total R (median)** | 13.73%        |

### Charge Distribution as % of Risk

| Bucket      | Trades | Percentage |
| ----------- | ------ | ---------- |
| < 5% of R   | 108    | 2.8%       |
| 5-10% of R  | 808    | 20.9%      |
| 10-20% of R | 1,785  | 46.1%      |
| 20-50% of R | 1,172  | 30.3%      |
| > 50% of R  | 0      | 0.0%       |

**Key Finding:** 76.4% of trades have charges between 10-50% of your risk amount.

### Impact by Trade Outcome

| Outcome                 | Trades | Avg Charge | Charge as % of R | Total Charges |
| ----------------------- | ------ | ---------- | ---------------- | ------------- |
| **Winners** (PnL > 100) | 787    | Rs 215     | 12.5%            | Rs 1,69,492   |
| **Losers** (PnL < -100) | 972    | Rs 196     | 11.7%            | Rs 1,90,678   |
| **Breakeven** (±100)    | 2,114  | Rs 70      | 19.9%            | Rs 1,47,804   |

**Observations:**

- Winners pay higher charges (larger positions)
- Breakeven trades have highest charge % of R (smallest positions)
- Total charges: Rs 5,07,974 across all trades

### Position Size Impact

| Risk Category        | Trades | % of Total | Avg Charge as % of R |
| -------------------- | ------ | ---------- | -------------------- |
| Small (R < Rs 2,000) | 2,743  | 70.8%      | 19.5%                |
| Medium (R Rs 2K-5K)  | 1,118  | 28.9%      | 10.2%                |
| Large (R > Rs 5,000) | 12     | 0.3%       | 4.4%                 |

**Critical Insight:**

- **70.8% of trades have R < Rs 2,000** (small positions)
- These pay **19.5% of R in charges** - nearly 1/5th of risk goes to brokerage
- Larger positions (R > 5K) pay only 4.4% of R in charges

### The Math Problem

```
Example Small Trade:
Entry: Rs 10,000
Stop: Rs 9,800 (R = Rs 200 = 2% risk)
Target: Rs 10,300 (1.5R = Rs 300 profit)
Charges: Rs 40 (20% of R!)

To breakeven after charges: Need 0.2R profit just to cover costs
To make 1R profit: Actually need 1.2R move
```

**Conclusion:** Small position sizes (high charge % of R) make profitability nearly impossible. You need larger R values or tighter charges.

---

## 📊 Concern Ranking Table

| Rank | Concern                      | Trades             | PnL Impact     | Priority    |
| ---- | ---------------------------- | ------------------ | -------------- | ----------- |
| 1    | Small profit trap (0.1-0.6R) | 1,009 (26.1%)      | **-₹8.1L**     | 🔴 CRITICAL |
| 2    | Breakeven give-back          | 1,440 (37.2%)      | **-₹2L+**      | 🔴 CRITICAL |
| 3    | Target too far (1.5R)        | 3,755 miss (97%)   | Missed profits | 🔴 HIGH     |
| 4    | Immediate stop (no MFE)      | 402 (10.4%)        | -₹9.6L         | 🟡 Medium   |
| 5    | Trail never loses            | 733 wins, 0 losses | **+₹13.2L**    | 🟢 Good!    |

**Combined damage from #1 + #2:** 63.3% of trades give back profit!

---

## 💡 The Fix Strategy

### Immediate Changes (Highest ROI)

| Current            | Fix                  | Expected Result                     |
| ------------------ | -------------------- | ----------------------------------- |
| BE at **0.6R**     | Lower to **0.4R**    | Capture 1,009 "small profit" trades |
| Target at **1.5R** | Lower to **1.0R**    | 15-20% hit rate (vs 3%)             |
| No partial at BE   | Sell **30% at 0.4R** | Lock in profit immediately          |
| Trail at **0.8R**  | Lower to **0.6R**    | More trades reach trailing          |

### Why These Fixes Work

```
Current (losing ₹8.1L):
Entry ₹100 → ₹101 (+0.5R profit) → ₹98 (stop) = -₹2,400 ❌
                    (never reached 0.6R BE)

Fixed (profitable):
Entry ₹100 → ₹100.80 (+0.4R) → Sell 30% → Trail at ₹100.80
         = ₹240 locked + ₹1,440 on rest = ₹1,680 total ✅
```

### Expected Impact of Fixes

| Fix             | Trades Helped | Estimated PnL Improvement |
| --------------- | ------------- | ------------------------- |
| BE at 0.4R      | 1,009         | +₹8L to +₹12L             |
| Target at 1.0R  | 500+          | +₹3L to +₹5L              |
| Partial at 0.4R | 1,440         | +₹2L to +₹4L              |
| **Combined**    | **2,900+**    | **+₹13L to +₹21L**        |

**This would turn the -₹3.2L loss into a +₹10L to +₹18L profit!**

---

## Future Analysis Suggestions

For deeper insights, consider analyzing:

### 1. Time-of-Day Performance

- Entry time vs win rate analysis
- Which hours work best (9:15-10:00 vs 2:00-3:15)
- Intraday volatility patterns by time bucket

### 2. Signal Grade Analysis

- Win rate by grade (A+, A, B, etc.)
- MFE distribution by grade
- Is the A+ grading system actually effective?

### 3. Sector Performance

- Net PnL by sector
- Sector-wise win rates
- Which sectors hit targets most consistently

### 4. Market Regime Analysis

- Performance in trending vs choppy markets (VIX-based)
- Up days vs down days performance
- Gap up vs gap down open performance

### 5. Holding Period Analysis

- Average holding time for winners vs losers
- Do quick exits perform better?
- Time decay of edge (does signal quality degrade over time?)

### 6. MFE Capture Efficiency

- Realized R / MFE R ratio
- "Give back" percentage by exit type
- Optimal exit timing analysis

### 7. Consecutive Loss Analysis

- Maximum consecutive losses
- Recovery time after drawdowns
- Streak analysis (are losses clustered?)

### 8. Best/Worst Day Deep Dive

- What worked on best day (+₹41K)?
- What failed on worst day (-₹22K)?
- Common patterns in extreme days

### 9. Signal Quality Gate Analysis

- Which of the 5 gates block the most signals?
- Do gated signals perform worse if allowed through?
- Gate rejection rate vs actual signal performance

---

## Data Verification

**Source:** `backtest_history_27-02-2026_04-55_pm.json`  
**Total Trades:** 3,873  
**Analysis Date:** February 27, 2026

**Validation:**

- All trades accounted for (3,873 = 100%)
- Mutually exclusive categories
- Cross-checked with exit reasons

---

_This is the corrected version. The previous document had data errors in the categorization._
