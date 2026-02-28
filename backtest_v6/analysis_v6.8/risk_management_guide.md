# Sector Engine V6.8 - Risk Management & Exit Strategy Guide

## Table of Contents

1. [What is MFE?](#what-is-mfe)
2. [What is MAE?](#what-is-mae)
3. [The Three Types of Stops](#the-three-types-of-stops)
4. [Chandelier Trailing Stop Explained](#chandelier-trailing-stop-explained)
5. [Target 1 Partial Exit](#target-1-partial-exit)
6. [Exit Trigger Flow Chart](#exit-trigger-flow-chart)
7. [Key Thresholds Reference](#key-thresholds-reference)
8. [Real-World Example](#real-world-example)

---

## What is MFE?

**MFE = Maximum Favorable Excursion**

**Simple Definition:** How far did the price go in your favor (your direction) before the trade ended?

### Example:

```
You BUY at: ₹100
Price goes up to: ₹110
Then falls and you exit at: ₹105

Your MFE = ₹10 (from ₹100 to ₹110)
Your Actual Profit = ₹5
```

### In "R" Terms (Risk Units):

The code normalizes everything by your initial risk:

```
If you risked ₹2 per share (stop at ₹98)
And price went ₹10 in your favor
Your MFE = 10 ÷ 2 = 5R
```

**Why it matters:** MFE shows you how much profit you "left on the table." If your MFE is always much higher than your actual profits, your exit strategy needs work.

---

## What is MAE?

**MAE = Maximum Adverse Excursion**

**Simple Definition:** How far did the price go AGAINST you before recovering or hitting your stop?

### Example:

```
You BUY at: ₹100
Price drops to: ₹97  ← Worst point (MAE)
Then recovers to: ₹108
You exit at: ₹108

Your MAE = ₹3 (from ₹100 to ₹97)
Your Actual Profit = ₹8
```

### Why MAE Matters:

- Shows if your stop-loss is in the right place
- If MAE is always hitting your stop but then price recovers → your stop is too tight
- If MAE is tiny but you get stopped out anyway → your stop might be working correctly

---

## The Three Types of Stops

The V6.8 engine uses a **three-layer protection system**:

### 1. Hard Stop (The Safety Net)

| Aspect            | Details                              |
| ----------------- | ------------------------------------ |
| **When Set**      | Immediately when you enter the trade |
| **Calculation**   | Entry Price ± (1.6 × 5-min ATR)      |
| **Minimum**       | At least 0.35% away from entry       |
| **Does it Move?** | NO - Never moves, your last defense  |

```python
Example:
Entry: ₹100
5-min ATR: ₹1.25
Hard Stop = 100 - (1.6 × 1.25) = 100 - 2 = ₹98
```

### 2. Breakeven Stop (The Guarantee)

| Aspect             | Details                                   |
| ------------------ | ----------------------------------------- |
| **When Activated** | When price moves 0.6R in your favor       |
| **What Happens**   | Stop moves to entry price + 3 bps buffer  |
| **Result**         | Worst case = small profit instead of loss |

```python
Example:
Entry: ₹100
Initial Risk: ₹2 per share (stop at ₹98)

Price moves to ₹101.20 (0.6 × ₹2 = ₹1.20 profit = 0.6R)
→ Breakeven triggers
→ New Stop = ₹100 + (100 × 0.0003) = ₹100.03
```

### 3. Trailing Stop (The Profit Protector)

| Aspect             | Details                                     |
| ------------------ | ------------------------------------------- |
| **When Activated** | When price moves 0.8R in your favor         |
| **What Happens**   | Stop follows price using Chandelier formula |
| **Goal**           | Lock in profits while giving room to run    |

---

## Chandelier Trailing Stop Explained

The Chandelier stop is like a **ratchet** - it only moves in your favor, never against you.

### The Formula:

```
For LONG trades:
Anchor = Highest High of last 10 bars
ATR_Buffer = ATR × Multiplier
Trailing Stop = Anchor - ATR_Buffer

For SHORT trades:
Anchor = Lowest Low of last 10 bars
ATR_Buffer = ATR × Multiplier
Trailing Stop = Anchor + ATR_Buffer
```

### Dynamic Multiplier (Adapts to Profit Level):

| Your MFE Level | Multiplier Used | Stop Distance | Purpose                     |
| -------------- | --------------- | ------------- | --------------------------- |
| MFE < 1R       | 2.2× ATR        | Wide          | Early trade - give it room  |
| 1R ≤ MFE < 2R  | 1.8× ATR        | Medium        | Lock in some profit         |
| MFE ≥ 2R       | 1.4× ATR        | Tight         | Deep profit - protect gains |

### Visual Example:

```
Price Action:    ₹100 → ₹105 → ₹110 → ₹108 → ₹115 → ₹112 → ₹109 → ₹108
                 │      │      │      │      │      │      │      │
MFE (in R):      0R    2.5R    5R    3.5R   7.5R    6R    4.5R   4R
                 │      │      │      │      │      │      │      │
Active Stop:     ₹98    ₹98   ₹102   ₹102   ₹108   ₹108   ₹108   EXIT
                 │      │      │      │      │      │      │      │
Stop Type:      Hard   Hard   Trail  Trail  Trail  Trail  Trail  Hit!
                        │             │             │
                   Breakeven      Trail      Tighter Trail
                   Armed (0.6R)   Armed (0.8R)  (2R+ hit)
```

---

## Target 1 Partial Exit

When price hits **1.5R profit**, the system takes **partial profits** automatically.

### What Happens:

1. **Price hits 1.5R target** → Sell 50% of your position
2. **Move stop to breakeven** on remaining 50%
3. **Let the rest run** with trailing stop

### Example:

```
Position: 100 shares at ₹100
Target 1: ₹103 (assuming ₹2 risk per share, 1.5R = ₹3)

When price hits ₹103:
→ Sell 50 shares @ ₹103 = ₹5,150 realized
→ Keep 50 shares
→ Move stop on remaining to ₹100 (entry)
→ Activate trailing stop if not already active

Result: You have:
- ₹150 locked profit from first 50 shares
- 50 shares still running with zero risk
```

### Why Do This?

- **Secures profit quickly** - you're booking gains
- **Eliminates risk** - remaining position is "house money"
- **Lets winners run** - you still capture big moves
- **Reduces regret** - you took SOME profit at target

---

## Exit Trigger Flow Chart

```
                    ┌─────────────────────────────────────┐
                    │           TRADE ENTRY               │
                    │  Set Hard Stop at Entry ± 1.6×ATR   │
                    └─────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   Price Moves Next    │
                    └───────────────────────┘
                          │           │
            ┌─────────────┘           └─────────────┐
            ▼                                       ▼
   ┌─────────────────┐                    ┌─────────────────┐
   │  AGAINST You    │                    │   IN Favor      │
   │  (Hits Stop)    │                    │   (Profitable)  │
   └─────────────────┘                    └─────────────────┘
            │                                       │
            ▼                                       ▼
   ┌─────────────────┐                    ┌─────────────────┐
   │  EXIT:          │                    │ MFE >= 0.6R?    │
   │  STOP_LOSS      │                    │ (60% of risk)   │
   │  PnL: -1R       │                    └─────────────────┘
   └─────────────────┘                          │
                                                 ▼
                                      ┌─────────────────┐
                                      │     YES         │
                                      │ Move Stop to    │
                                      │ BREAKEVEN       │
                                      │ (entry + buffer)│
                                      └─────────────────┘
                                                 │
                                                 ▼
                                      ┌─────────────────┐
                                      │ MFE >= 0.8R?    │
                                      │ (80% of risk)   │
                                      └─────────────────┘
                                                 │
                    ┌────────────────────────────┴────────────────────────────┐
                    │ NO (Stay with BE Stop)                                   │ YES
                    ▼                                                          ▼
        ┌─────────────────────┐                                  ┌─────────────────────┐
        │ Price pulls back    │                                  │ ACTIVATE TRAILING   │
        │ to breakeven?       │                                  │ STOP (Chandelier)   │
        └─────────────────────┘                                  └─────────────────────┘
                    │                                                          │
        ┌───────────┴───────────┐                                  ┌───────────┴───────────┐
        │ YES                   │ NO                                 │ YES                   │ NO
        ▼                       ▼                                  ▼                       ▼
┌───────────────┐    ┌─────────────────────┐              ┌───────────────┐    ┌─────────────────────┐
│ EXIT:         │    │ Continue holding    │              │ UPDATE TRAIL  │    │ Price hits target?  │
│ BREAKEVEN     │    │ at breakeven stop   │              │ STOP level    │    │ (1.5R target hit?)    │
│ PnL: ~0       │    └─────────────────────┘              │ (higher)      │    └─────────────────────┘
└───────────────┘                                         └───────────────┘              │
                                                                                ┌───────┴───────┐
                                                                                │ YES           │ NO
                                                                                ▼               ▼
                                                                      ┌─────────────────┐  ┌─────────────────────┐
                                                                      │ PARTIAL EXIT    │  │ Continue with trail │
                                                                      │ - Sell 50%      │  │ stop                │
                                                                      │ - Move rest to  │  └─────────────────────┘
                                                                      │   breakeven     │
                                                                      └─────────────────┘
```

---

## Key Thresholds Reference

| Constant              | Value | What It Controls                        |
| --------------------- | ----- | --------------------------------------- |
| `STOP_ATR_MULT_5M`    | 1.6×  | Initial stop distance from entry        |
| `STOP_MIN_PCT`        | 0.35% | Minimum stop distance (percentage)      |
| `BE_ARM_R`            | 0.6R  | When to move stop to breakeven          |
| `BE_BUFFER_BPS`       | 3 bps | Small profit buffer above entry         |
| `TRAIL_ARM_R`         | 0.8R  | When to activate trailing stop          |
| `TRAIL_LOOKBACK_BARS` | 10    | Bars to look back for chandelier anchor |
| `TRAIL_MULT_LOW`      | 2.2×  | Loose trail multiplier (early trade)    |
| `TRAIL_MULT_MID`      | 1.8×  | Medium trail (after 1R profit)          |
| `TRAIL_MULT_HIGH`     | 1.4×  | Tight trail (after 2R profit)           |
| `TARGET_1_MULT`       | 1.5R  | First profit target                     |

---

## Real-World Example

### Trade Scenario: Long on RELIANCE

```
Entry Price:     ₹2,500
ATR (5-min):     ₹15
Initial Risk:    1.6 × 15 = ₹24 per share
Stop Loss:       ₹2,476 (hard stop)
Target 1:        ₹2,536 (1.5R = ₹36 above entry)
Position Size:   100 shares
Capital at Risk: ₹2,400
```

### Trade Timeline:

| Time  | Price  | MFE  | What Happens           | Active Stop | Status          |
| ----- | ------ | ---- | ---------------------- | ----------- | --------------- |
| 9:30  | ₹2,500 | 0R   | Entry                  | ₹2,476      | Hard Stop       |
| 9:35  | ₹2,515 | 0.6R | BE trigger armed       | ₹2,476      | Hard Stop       |
| 9:38  | ₹2,525 | 1.0R | **Breakeven Stop Set** | ₹2,503      | BE + Buffer     |
| 9:40  | ₹2,536 | 1.5R | **Target 1 Hit!**      | ₹2,503      | Partial Exit    |
| 9:45  | ₹2,560 | 2.5R | Trail armed            | ₹2,530      | Trailing (2.2×) |
| 10:00 | ₹2,580 | 3.3R | Trail tightens         | ₹2,550      | Trailing (1.8×) |
| 10:15 | ₹2,600 | 4.2R | Trail very tight       | ₹2,580      | Trailing (1.4×) |
| 10:30 | ₹2,590 | 3.8R | Pullback               | ₹2,580      | Hold            |
| 10:35 | ₹2,575 | 3.1R | Pullback continues     | ₹2,580      | **EXIT!**       |

### Final Results:

```
First 50 shares:  Sold @ ₹2,536 = ₹126,800
                 Cost basis = ₹125,000
                 Profit = ₹1,800

Last 50 shares:   Sold @ ₹2,580 = ₹129,000
                 Cost basis = ₹125,000
                 Profit = ₹4,000

GROSS PROFIT:     ₹5,800 (2.42R)

Charges (approx):
  - Brokerage:    ₹40
  - STT:          ₹64
  - Transaction:  ₹38
  - SEBI:         ₹3
  - GST:          ₹15
  TOTAL CHARGES:  ₹160

NET PROFIT:       ₹5,640 (2.35R after charges)
```

---

## Summary

The V6.8 exit strategy is designed to:

1. **Cut losses quickly** - Hard stop at 1.6× ATR
2. **Guarantee breakeven** - Once you have 0.6R profit
3. **Trail winners** - Dynamic chandelier that tightens as profit grows
4. **Take partial profits** - At 1.5R target to reduce risk
5. **Protect deep profits** - 1.4× multiplier when MFE > 2R

**The goal:** Lose small, win big, never give back significant profits.

---

_Document generated for Sector Engine V6.8 Analysis_
