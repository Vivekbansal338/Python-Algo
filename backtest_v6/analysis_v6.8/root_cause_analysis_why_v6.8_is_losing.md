# V6.8 Strategy Root Cause Analysis

## Why the Strategy is Losing Money

**Analysis Date:** February 27, 2026  
**Backtest Period:** 2023-2025  
**Strategy Version:** V6.8 with Signal Quality Gates + Brokerage

---

## Executive Summary

The V6.8 strategy is consistently losing ₹3-4 lakhs per year across all backtested years (2023-2025). The root cause is **not** a single issue but a combination of:

1. **Stops are hit 1.7x more often than targets**
2. **91% of losing trades had positive unrealized profit** (profit given back)
3. **55% of trades exit near breakeven** (₹0 PnL after charges)
4. **Brokerage charges are 3x higher than gross profits**

**Bottom Line:** The strategy captures small wins and medium losses, while charges eat everything.

---

## 1. THE STOP LOSS PROBLEM

### Stops Hit vs Targets Hit

| Year | Total Trades | Stop Hit First | Target Hit First | Neither Hit |
| ---- | ------------ | -------------- | ---------------- | ----------- |
| 2023 | 3,873        | 37.2% (1,439)  | 22.0% (852)      | 40.7%       |
| 2024 | 4,596        | 39.3% (1,804)  | 22.9% (1,051)    | 37.7%       |
| 2025 | 4,039        | 36.2% (1,463)  | 21.9% (885)      | 41.8%       |

**Key Finding:** Stops are hit **1.7 times more often** than targets across all years.

### Exit Reason Breakdown (2023 Detailed)

| Exit Reason  | Count   | Percentage | PnL Impact                     |
| ------------ | ------- | ---------- | ------------------------------ |
| STOP_TRAIL   | 2,173   | 56.1%      | Mixed (some profit, some loss) |
| STOP_HARD    | 1,411   | 36.4%      | Mostly losses                  |
| FORCE_EXIT   | 170     | 4.4%       | Market close exits             |
| TARGET1_FULL | **118** | **3.0%**   | **Profitable**                 |
| SAFETY_HALT  | 1       | 0.0%       | Emergency exit                 |

**Critical Issue:** Only **3% of trades hit Target 1!** The remaining 92.5% are stopped out.

---

## 2. THE "BREAKEVEN TRAP"

### Why You're Seeing So Many ~₹0 PnL Trades

From 2023 data (3,873 trades):

| PnL Range                      | Count     | Percentage | Description     |
| ------------------------------ | --------- | ---------- | --------------- |
| **Near Zero (-₹100 to +₹100)** | **2,114** | **54.6%**  | Breakeven exits |
| Large Loss (< -₹1,000)         | 752       | 19.4%      | Stop loss hits  |
| Large Win (> +₹1,000)          | 506       | 13.1%      | Big runners     |
| Small Win (+₹100 to +₹500)     | 155       | 4.0%       | Minor profits   |
| Medium Win (+₹500 to +₹1,000)  | 126       | 3.3%       | Moderate wins   |

**55% of all trades close near zero!**

### What Happens in the Breakeven Trap

```
Trade Lifecycle:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Entry at ₹100, Stop at ₹98 (2% risk)
        ↓
2. Price moves to ₹101.20 (+1.2% = 0.6R)
        ↓
3. BE ARMED: Stop moves to ₹100.03 (entry + 3 bps)
        ↓
4. Price reverses to ₹100.03
        ↓
5. EXIT at breakeven
        ↓
6. After charges: -₹50 loss (not zero!)
```

### BE Armed Trades Analysis

From 2023 data:

| Metric                               | Value                     |
| ------------------------------------ | ------------------------- |
| Total trades with BE armed           | 2,363 (61% of all trades) |
| BE armed then stopped out            | 2,173 (92% of BE armed)   |
| BE armed exits with profit           | 1,056 (44%)               |
| BE armed exits with loss             | 1,117 (51%)               |
| **Average PnL on BE→stopped trades** | **₹+782**                 |

**The Problem:** Even when breakeven is armed, 51% of exits are still losses, and the average profit is tiny (₹782) compared to the risk taken.

---

## 3. THE "PROFIT GIVEN BACK" PROBLEM

### The Most Painful Statistic

**91% of losing trades had positive MFE (Maximum Favorable Excursion) before exiting at a loss!**

| Metric                   | Value              | Meaning                    |
| ------------------------ | ------------------ | -------------------------- |
| Losing trades with +MFE  | 2,383 out of 2,613 | 91% of losers              |
| Average MFE on losers    | 0.51R              | Went halfway to target     |
| Losers with MFE ≥ 1.0R   | 257 trades         | Hit target, then reversed! |
| Losers with MFE 0.5-1.0R | 1,043 trades       | 44% of losers              |
| Losers with MFE 0-0.5R   | 1,083 trades       | Immediate stop hits        |

### What This Means in Plain English

```
Example Trade:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Entry: ₹100
Stop: ₹98 (2R = ₹4 target at ₹104)

What Happened:
9:30 - Entry at ₹100
9:35 - ₹102 (+0.5R unrealized)
9:40 - ₹103 (+0.75R unrealized) ← PEAK MFE
9:45 - ₹101 (+0.25R unrealized)
9:50 - ₹97 (-₹3 realized LOSS)

You had ₹3 unrealized profit!
But you closed with ₹3 loss.
This happened 2,383 times.
```

### MFE Distribution for Losing Trades

| MFE Range     | Count | % of Losers | What Happened              |
| ------------- | ----- | ----------- | -------------------------- |
| MFE ≥ 1.0R    | 257   | 9.8%        | Hit target level, reversed |
| MFE 0.5-1.0R  | 1,043 | 39.9%       | Went halfway, reversed     |
| MFE 0.25-0.5R | 650   | 24.9%       | Small move, reversed       |
| MFE < 0.25R   | 663   | 25.4%       | Immediate stop hit         |

**Key Insight:** 50% of losers went at least halfway to your target (0.5R+) before reversing. You're right about direction 50% of the time, but you don't capture it.

---

## 4. THE CHARGES DEATH SPIRAL

### Brokerage Impact Across Years

| Year | Gross PnL  | Total Charges | Net PnL        | Charges as % of Gross |
| ---- | ---------- | ------------- | -------------- | --------------------- |
| 2023 | +₹1,86,044 | ₹5,07,974     | **-₹3,21,931** | 273%                  |
| 2024 | +₹1,30,432 | ₹5,48,560     | **-₹4,18,129** | 421%                  |
| 2025 | +₹2,10,486 | ₹5,35,337     | **-₹3,24,850** | 254%                  |

**The Math:**

- You need **₹5+ lakhs in gross profit** just to break even
- With 32-34% win rate, generating ₹5L gross profit is nearly impossible
- Every trade costs ~₹131 in charges (brokerage + STT + GST + etc.)

### Breakdown of 2023 Charges (₹5,07,974 total)

| Charge Type         | Amount    | % of Total |
| ------------------- | --------- | ---------- |
| STT/CTT             | ₹2,67,552 | 52.7%      |
| Brokerage           | ₹1,10,839 | 21.8%      |
| Transaction Charges | ₹63,565   | 12.5%      |
| Stamp Duty          | ₹32,101   | 6.3%       |
| GST                 | ₹31,778   | 6.3%       |
| SEBI Charges        | ₹2,140    | 0.4%       |

**STT alone is ₹2.67L** - you pay 0.025% on every sell, which adds up with high turnover (₹2,140 crores).

---

## 5. THE TRAILING STOP FAILURE

### Trailing Stop Performance

From BE-armed trades that eventually got stopped:

| Metric                     | Value       |
| -------------------------- | ----------- |
| Average MFE_R when stopped | 1.47R       |
| Median MFE_R when stopped  | 1.12R       |
| Trades with MFE ≥ 2R       | 431 (19.8%) |
| Trades with MFE 1-2R       | 984 (45.3%) |

**What This Means:**

- Trailing stop activates at 0.8R
- But by the time the trail is hit, price has already gone 1.47R in your favor
- You give back 0.67R of profit on average
- 20% of trades went 2R+ in your favor before trailing stop hit

### The Chandelier Formula Issue

Current multipliers:

- MFE < 1R: 2.2× ATR (very wide)
- 1R ≤ MFE < 2R: 1.8× ATR (wide)
- MFE ≥ 2R: 1.4× ATR (still wide)

**Problem:** These multipliers may be too wide for Indian market volatility, causing you to give back too much profit.

---

## 6. THE VICIOUS CYCLE (Visual Flow)

```
┌─────────────────────────────────────────────────────────────────┐
│                        V6.8 DEATH SPIRAL                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│  1. SIGNAL FIRES                                              │
│     └─ 22,486 A+ signals generated (2023)                     │
│     └─ Only 3,873 execute (17% execution rate)                │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│  2. TRADE ENTERS                                              │
│     └─ Entry with 1.6× ATR stop (~2% risk)                    │
│     └─ Target 1 at 1.5R (far away - only 22% hit rate)        │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│  3. PRICE MOVES +0.6R                                         │
│     └─ BE ARMED (61% of trades)                               │
│     └─ Stop moved to entry + 3 bps                            │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│  4. PRICE REVERSES                                            │
│     └─ 55% of trades: Hit breakeven or trail (~₹0 PnL)        │
│     └─ 36% of trades: Hit hard stop (loss)                    │
│     └─ 3% of trades: Hit target (win)                         │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│  5. CHARGES APPLIED                                           │
│     └─ ₹131 average per trade                                 │
│     └─ Breakeven trades become losers after charges           │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│  6. RESULT AFTER 3,873 TRADES                                 │
│     └─ Gross PnL: +₹1.86L (barely positive)                   │
│     └─ Charges: ₹5.08L                                        │
│     └─ Net PnL: -₹3.22L (LOSS)                                │
└───────────────────────────────────────────────────────────────┘
```

---

## Summary: The 6 Core Problems

| #   | Problem                | Current Value       | Impact                         |
| --- | ---------------------- | ------------------- | ------------------------------ |
| 1   | **Target too far**     | 1.5R (22% hit rate) | Most trades never reach target |
| 2   | **Stops too loose**    | 1.6× ATR            | 37% immediate stop hits        |
| 3   | **BE activation late** | 0.6R                | Only 61% of trades reach BE    |
| 4   | **Trailing too wide**  | 2.2×/1.8×/1.4× ATR  | Give back 1.47R average        |
| 5   | **Too many signals**   | 22,000 A+ / year    | High turnover = high charges   |
| 6   | **Win rate too low**   | 32-34%              | Can't overcome ₹5L charges     |

---

## Recommendations for V6.9

| Issue                | Current       | Recommended                           | Expected Impact             |
| -------------------- | ------------- | ------------------------------------- | --------------------------- |
| Target 1 distance    | 1.5R          | **1.0R**                              | 40%+ target hit rate        |
| Trailing multipliers | 2.2/1.8/1.4×  | **1.5/1.2/1.0×**                      | Keep more profit            |
| BE activation        | 0.6R          | **0.4R**                              | More trades reach BE        |
| Partial exit timing  | 50% at 1.5R   | **50% at 0.8R**                       | Capture profit earlier      |
| Signal quality       | Current gates | **Tighten by 50%**                    | Fewer trades, lower charges |
| Add time stop        | None          | **Exit if target not hit in 20 bars** | Reduce give-back            |

---

## Conclusion

The V6.8 strategy is not "broken" - it's just **not profitable after charges**. The signal quality is decent (MFE analysis shows 91% of losers had positive unrealized profit), but the **exit management and charge structure** make it impossible to win.

**To become profitable, the strategy needs:**

1. Earlier profit-taking (don't wait for 1.5R)
2. Tighter trailing stops (keep what you make)
3. Fewer trades (reduce charge burden)
4. Higher win rate (tighter entry filters)

**Without these changes, expect similar -₹3L to -₹4L losses every year.**

---

_Document generated: February 27, 2026_  
_Data sources: backtest_history_27-02-2026_04-53/54/55_pm.json_  
_Strategy: V6.8 with Signal Quality Gates + Full Brokerage_
