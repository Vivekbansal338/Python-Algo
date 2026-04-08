# Sector Engine V6.8 — Risk Management & Exit Strategy Guide

> [!IMPORTANT]
> This guide explains V6.8's risk/exit architecture with 2023 backtest statistics verified against 3,873 trade records.

---

## Table of Contents

1. [Risk Architecture Overview](#risk-architecture-overview)
2. [MFE & MAE Explained](#mfe--mae-explained)
3. [The Three-Layer Stop System](#the-three-layer-stop-system)
4. [Chandelier Trailing Stop](#chandelier-trailing-stop)
5. [Target 1 Partial Exit](#target-1-partial-exit)
6. [Signal Quality Gates (V6.7)](#signal-quality-gates-v67)
7. [Capital & Position Limits](#capital--position-limits)
8. [Brokerage Model (V6.8)](#brokerage-model-v68)
9. [Complete Exit Flow Chart](#complete-exit-flow-chart)
10. [2023 Performance by Exit Path](#2023-performance-by-exit-path)
11. [Key Thresholds Reference](#key-thresholds-reference)
12. [Worked Examples](#worked-examples)

---

## Risk Architecture Overview

V6.8 manages risk through layered systems:

```
┌─────────────────────────────────────────────────────────────┐
│                   SIGNAL GENERATION                         │
│  HMA(9)/HMA(21) crossover + 5 quality gates + alignment    │
│  → Only A+ grade signals pass                              │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   POSITION SIZING                           │
│  Risk per trade = max(1.6× ATR_5m, 0.35% of price) = "1R" │
│  Shares = risk_budget ÷ risk_per_share                     │
│  Capped by available capital (no leverage)                  │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   ACTIVE MANAGEMENT                         │
│  Hard Stop → Breakeven → Trailing → Target partial exit    │
│  Monitored on every 5-min bar throughout the trade          │
└─────────────────────────────────────────────────────────────┘
```

---

## MFE & MAE Explained

### MFE (Maximum Favorable Excursion)

How far price moved **in your favor** at peak, measured in R-multiples:

```
Entry: ₹100, Stop: ₹98 (R = ₹2)
Price goes to ₹103 then reverses → Exit at ₹101

MFE = (₹103 − ₹100) ÷ ₹2 = 1.5R
Actual profit = (₹101 − ₹100) ÷ ₹2 = 0.5R
Give-back = 1.0R
```

| 2023 Verified MFE Stats | Value |
|---|---|
| Mean MFE_R | 1.01 |
| Median MFE_R | 0.74 |
| Max MFE_R | 11.24 |

### MAE (Maximum Adverse Excursion)

How far price moved **against you** before recovery or stop:

```
Entry: ₹100, Stop: ₹98
Price drops to ₹97 → recovers to ₹105

MAE = (₹100 − ₹97) ÷ ₹2 = 1.5R
```

| 2023 Verified MAE Stats | Value |
|---|---|
| Mean MAE_R | 0.71 |
| Median MAE_R | 0.64 |
| Max MAE_R | 5.06 |

---

## The Three-Layer Stop System

### Layer 1: Hard Stop (Safety Net)

| Aspect | Detail |
|---|---|
| **When Set** | At entry |
| **Formula** | `max(1.6 × ATR_5min, 0.35% × entry_price)` |
| **Does it move?** | **Never** — fixed worst-case exit |
| **2023 stats** | 1,411 trades (36.4%) hit hard stop |

```python
# Code reference: line 1597
R0 = max(atr_5m * 1.6, ltp * 0.0035)
stop_price = entry - R0  # for LONG
```

### Layer 2: Breakeven Stop (Profit Protection)

| Aspect | Detail |
|---|---|
| **Activation** | MFE reaches **0.6R** |
| **New Stop** | Entry price + 3 basis points |
| **2023 stats** | 2,363 trades (61.0%) armed breakeven |

```python
# Code reference: lines 1973-1986
if mfe_r >= 0.6 and not be_armed:
    be_stop = entry + (3 * entry / 10000)  # 3 bps buffer
    current_stop = max(current_stop, be_stop)
    be_armed = True
```

### Layer 3: Trailing Stop (Profit Ratchet)

| Aspect | Detail |
|---|---|
| **Activation** | MFE reaches **0.8R** |
| **Formula** | Chandelier: Anchor − (ATR × multiplier) |
| **2023 stats** | 1,763 trades (45.5%) armed trail |

The trailing stop moves only in your favor (ratchet mechanism). Once trail-armed:

```python
# Code reference: lines 1991-1996
if trail_armed:
    new_trail = chandelier(trade, intra_pos)
    if direction == "LONG" and new_trail > current_stop:
        current_stop = new_trail
```

---

## Chandelier Trailing Stop

The Chandelier stop anchors to recent price extremes and adjusts distance by profit level:

### Formula

```
LONG:  Trail = Highest_High(last 10 bars) − ATR_5m × multiplier
SHORT: Trail = Lowest_Low(last 10 bars)  + ATR_5m × multiplier
```

### Dynamic Multiplier

| MFE Level | Multiplier | Stop Distance | Rationale |
|---|---|---|---|
| MFE < 1R | **2.2×** ATR | Wide | Give early trades room |
| 1R ≤ MFE < 2R | **1.8×** ATR | Medium | Lock some profit |
| MFE ≥ 2R | **1.4×** ATR | Tight | Protect deep gains |

### Verified 2023 Performance

| Metric | Value |
|---|---|
| BE-armed trades stopped out | 2,173 |
| Avg MFE_R when stopped | 1.47R |
| Median MFE_R | 1.12R |
| Avg give-back | ~0.47R |
| MFE ≥ 2R before stop | 431 (19.8%) |

**The strategy reaches 1.47R on average before the trail catches — giving back nearly half an R.**

---

## Target 1 Partial Exit

When price hits **1.5R profit**, the system sells a portion:

| Step | Action |
|---|---|
| 1 | Price hits 1.5R target |
| 2 | Sell 50% of position at target price |
| 3 | Move stop on remaining to breakeven |
| 4 | Continue trailing remaining position |

### 2023 Verified Stats

| Metric | Value |
|---|---|
| Target hit count | 118 (3.0% of all trades) |
| Win rate | 100% |
| **Net PnL (all 118)** | **+₹290** |

> [!WARNING]
> Despite 100% win rate, total net PnL is only +₹290 across 118 trades. Charges nearly entirely consume the partial exit profits. The target is set well but the net capture is negligible.

---

## Signal Quality Gates (V6.7)

Five gates filter HMA crossover signals before they become A+ grade:

| Gate | What It Checks | 2023 Rejections |
|---|---|---|
| **1. HMA Slope** | Both HMA(9) and HMA(21) slopes must align with direction | 34,352 |
| **2. Crossover Freshness** | Last HMA cross must be within 15 bars (~75 min) | 2,661 |
| **3. Price-HMA Alignment** | Price > HMA9 > HMA21 (LONG) or reverse | 56,598 |
| **4. HMA Separation** | Gap/ATR ≥ 0.15 (anti-chop filter) | 17,207 |
| **5. HMA Divergence** | Gap must be expanding vs 5 bars ago | 51,394 |

Plus the V6.4 alignment filter (Index/Sector/Signal must agree): **49,922 rejections**

All five gates must pass for a signal to receive A+ grade.

---

## Capital & Position Limits

| Limit | Value | 2023 Impact |
|---|---|---|
| Max concurrent positions | 6 | 252 blocked |
| Max per sector | 2 | 2,358 blocked |
| Max per stock | 1 | 316 blocked |
| No leverage | 100% capital cap | **15,578 blocked** |

**Capital is the biggest blocker** — 15,578 signals rejected due to insufficient capital. The strategy often deploys 100%+ of capital (peak utilization: 149.4%).

---

## Brokerage Model (V6.8)

Applied per executed order leg (entry, partial exit, final exit):

| Charge | Rate |
|---|---|
| Brokerage | min(0.03% of turnover, ₹20) |
| STT/CTT | 0.025% on sell side only |
| Transaction (NSE) | 0.00297% |
| SEBI | ₹10 per crore |
| Stamp duty | 0.003% on buy side only |
| GST | 18% × (brokerage + SEBI + transaction) |

### 2023 Verified Impact

| Component | Amount | % of Total |
|---|---|---|
| STT | ₹2,67,552 | 52.7% |
| Brokerage | ₹1,10,839 | 21.8% |
| Transaction | ₹63,565 | 12.5% |
| Stamp | ₹32,101 | 6.3% |
| GST | ₹31,778 | 6.3% |
| SEBI | ₹2,140 | 0.4% |
| **Total** | **₹5,07,974** | **100%** |

**Avg charge per trade: ₹131 | As % of R: 16.4% mean, 13.7% median**

---

## Complete Exit Flow Chart

```
                ┌──────────────────────────────────────────────────┐
                │              TRADE ENTRY                         │
                │  Set Hard Stop = max(1.6×ATR, 0.35%)             │
                │  Set Target 1 = Entry ± 1.5R                     │
                │  Apply entry-side charges (BUY for LONG)         │
                └────────────────────┬─────────────────────────────┘
                                     │
                        On each 5-min bar:
                                     │
                          ┌──────────┴──────────┐
                          ▼                     ▼
              ┌───────────────────┐   ┌───────────────────┐
              │ Stop hit?         │   │ Price favorable    │
              │ (low ≤ stop for   │   │                    │
              │  LONG)            │   │                    │
              └────────┬──────────┘   └────────┬──────────┘
                       │ YES                   │
                       ▼                       ▼
              ┌───────────────────┐   ┌───────────────────┐
              │ EXIT:             │   │ Update MFE/MAE    │
              │ STOP_HARD (if no  │   │ Check thresholds  │
              │  BE/trail) or     │   │                    │
              │ STOP_TRAIL (if    │   │                    │
              │  BE or trail)     │   │                    │
              └───────────────────┘   └────────┬──────────┘
                                               │
                              ┌────────────────┼────────────────┐
                              ▼                ▼                ▼
                   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                   │ MFE ≥ 0.6R?  │  │ MFE ≥ 0.8R?  │  │ Target 1     │
                   │ → ARM BE     │  │ → ARM TRAIL   │  │ hit (1.5R)?  │
                   │ (move stop   │  │ (chandelier   │  │ → PARTIAL    │
                   │  to entry    │  │  stop starts  │  │   EXIT       │
                   │  + 3bps)     │  │  following)   │  │   (50% qty)  │
                   └──────────────┘  └──────────────┘  └──────────────┘
                                               │
                              ┌────────────────┴────────────────┐
                              ▼                                 ▼
                   ┌──────────────┐                  ┌──────────────┐
                   │ FORCE_EXIT   │                  │ SAFETY_HALT  │
                   │ (end of day  │                  │ (VIX spike / │
                   │  or circuit) │                  │  anomaly)    │
                   └──────────────┘                  └──────────────┘
```

### Execution Order (from code lines 1941–2036):

1. Update highest/lowest price tracking
2. Calculate MFE_R and MAE_R
3. **Check stop hit** → exit immediately if hit
4. **Check BE arm** → if MFE ≥ 0.6R, move stop to entry + 3bps
5. **Check trail arm** → if MFE ≥ 0.8R, enable chandelier
6. **Update trail stop** → ratchet trail if trail armed
7. **Check target hit** → partial exit at 1.5R, move stop to entry

---

## 2023 Performance by Exit Path

| Exit Path | Trades | % | Net PnL | Avg PnL | Win Rate |
|---|---|---|---|---|---|
| STOP_HARD (no BE/trail) | 1,411 | 36.4% | −₹20,73,472 | −₹1,470 | 0% |
| STOP_TRAIL (BE only, no trail) | 586 | 15.1% | −₹26,878 | −₹46 | ~50% |
| STOP_TRAIL (trail armed) | 1,587 | 41.0% | +₹17,27,224 | +₹1,088 | 66.5% |
| TARGET1_FULL | 118 | 3.0% | +₹290 | +₹2 | 100% |
| FORCE_EXIT | 170 | 4.4% | +₹41,249 | +₹243 | 50% |
| SAFETY_HALT | 1 | 0.0% | +₹9,657 | +₹9,657 | 100% |

**Profitable paths: Trail-armed STOP_TRAIL (+₹17.3L) are the only meaningful profit source.**

---

## Key Thresholds Reference

| Constant | Value | Source |
|---|---|---|
| `STOP_ATR_MULT_5M` | 1.6× | Hard stop ATR multiplier |
| `STOP_MIN_PCT` | 0.35% | Minimum stop floor |
| `BE_ARM_R` | 0.6 | Breakeven activation (R-multiple) |
| `BE_BUFFER_BPS` | 3 | Breakeven buffer (basis points) |
| `TRAIL_ARM_R` | 0.8 | Trail activation (R-multiple) |
| `TRAIL_LOOKBACK_BARS` | 10 | Chandelier anchor window |
| `TRAIL_MULT_LOW` | 2.2× | Trail when MFE < 1R |
| `TRAIL_MULT_MID` | 1.8× | Trail when 1R ≤ MFE < 2R |
| `TRAIL_MULT_HIGH` | 1.4× | Trail when MFE ≥ 2R |
| `TARGET_1_MULT` | 1.5 | Target 1 (from `config`) |
| `TARGET_1_EXIT_PCT` | 0.50 | Partial exit % (from `config`) |
| `HMA_FAST` | 9 | Fast HMA period |
| `HMA_SLOW` | 21 | Slow HMA period |
| `SLOPE_LOOKBACK` | 3 | HMA slope measurement bars |
| `SLOPE_MIN_PCT` | 0.01 | Minimum HMA slope %/bar |
| `CROSS_FRESHNESS_BARS` | 15 | Max crossover age (~75 min) |
| `MIN_HMA_SEP_ATR_FRAC` | 0.15 | Min HMA gap as fraction of ATR |
| `DIVERGENCE_LOOKBACK` | 5 | Bars to compare gap expansion |

---

## Worked Examples

### Example 1: LONG Trade — Trail Win

```
Entry: ₹2,500
ATR_5m: ₹15
R = max(15 × 1.6, 2500 × 0.0035) = max(24, 8.75) = ₹24
Hard Stop: ₹2,476
Target 1: ₹2,536 (1.5R = ₹36 above entry)

Timeline:
 9:30  Entry ₹2,500         | Stop: ₹2,476 (HARD)
 9:45  Price → ₹2,515       | MFE = 0.63R → BE ARMED
                             | Stop moves to ₹2,500.75 (entry + 3bps)
10:00  Price → ₹2,520       | MFE = 0.83R → TRAIL ARMED
                             | Chandelier: ₹2,520 − 15×2.2 = ₹2,487
                             | Stop stays at ₹2,500.75 (higher)
10:15  Price → ₹2,540       | MFE = 1.67R → Multiplier tightens to 1.8×
                             | Target 1 hit! Sell 50 shares @ ₹2,536
                             | Trail: ₹2,540 − 15×1.8 = ₹2,513
                             | Stop: ₹2,513
10:30  Price → ₹2,550       | Trail: ₹2,550 − 15×1.8 = ₹2,523
11:00  Price → ₹2,535       | Trail unchanged at ₹2,523
11:15  Price → ₹2,520       | STOP_TRAIL hit at ₹2,523

Result:  50 shares closed at ₹2,536 (partial) + 50 shares at ₹2,523 (trail)
         Gross: (36 × 50) + (23 × 50) = ₹2,950
         Charges: ~₹160
         Net: ₹2,790 (1.16R)
```

### Example 2: LONG Trade — Small Profit Trap (STOP_HARD)

```
Entry: ₹500
ATR_5m: ₹3
R = max(3 × 1.6, 500 × 0.0035) = max(4.80, 1.75) = ₹4.80
Hard Stop: ₹495.20
BE trigger: ₹502.88 (0.6 × 4.80 = 2.88 above entry)

Timeline:
10:00  Entry ₹500           | Stop: ₹495.20 (HARD)
10:15  Price → ₹502         | MFE = 0.42R — not enough for BE
10:30  Price → ₹501         | MFE still 0.42R
10:45  Price → ₹499         | Pulling back
11:00  Price → ₹495         | STOP_HARD hit at ₹495.20

Result:  Loss = (500 − 495.20) × qty = −₹4.80 per share
         The trade was RIGHT (went +₹2 in favor) but never reached
         the 0.6R (₹2.88) threshold to arm breakeven.
         Had BE been at 0.4R (₹500 + 1.92 = ₹501.92), this trade
         would have been protected.
```

---

_Verified Analysis Date: February 28, 2026_
_Source: `sector_engine_v6.8.py` + `backtest_history_27-02-2026_04-55_pm.json`_
