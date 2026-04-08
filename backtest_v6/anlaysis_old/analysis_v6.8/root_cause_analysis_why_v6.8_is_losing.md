# V6.8 Root Cause Analysis — Why the Strategy Loses Money

> [!IMPORTANT]
> All numbers are **independently verified** against raw trade records from `backtest_history_27-02-2026_04-55_pm.json` (3,873 trades, Jan–Dec 2023, ₹10L starting equity).

---

## Executive Summary

| Metric | Verified Value |
|---|---|
| **Net PnL** | −₹3,21,931 (−32.2%) |
| **Gross PnL** | +₹1,86,044 |
| **Total Charges** | ₹5,07,974 |
| **Charges ÷ Gross** | **2.73×** |
| **Win Rate** | 32.5% |
| **Profit Factor** | 0.85 |
| **Max Drawdown** | 32.7% (₹3.30L) |

**The strategy is gross-positive but net-negative. Charges exceed gross profits by 2.73×, making profitability impossible at this trade volume.**

---

## The 5 Root Causes (Ranked by PnL Impact)

### 🔴 1. STOP_HARD Is the Dominant Loss Engine (−₹20.7L)

| Metric | Value |
|---|---|
| Trades hitting hard stop | 1,411 (36.4%) |
| Combined PnL | **−₹20,73,472** |
| Avg loss per trade | −₹1,470 |
| Win rate | **0.0%** |

Every STOP_HARD exit is a full −1R loss. This single exit type accounts for **more loss than the entire strategy produces**.

```
Breakdown of 1,411 STOP_HARD trades by how far price went before reversing:
  MFE = 0 (no move):     233 (16.5%) — immediate reversal
  MFE 0.01–0.20R:        461 (32.7%) — tiny move, then reversed  
  MFE 0.20–0.40R:        394 (27.9%) — moderate move, couldn't reach 0.6R BE
  MFE 0.40–0.60R:        317 (22.5%) — almost reached BE, reversed
  MFE ≥ 0.60R:             6 ( 0.4%) — reached BE range but still hit hard stop
```

**83% of STOP_HARD trades had favorable movement before dying — they were right about direction but couldn't survive long enough.**

---

### 🔴 2. Transaction Costs Kill All Profits (₹5.08L)

| Component | Amount | % of Total |
|---|---|---|
| STT/CTT | ₹2,67,552 | 52.7% |
| Brokerage | ₹1,10,839 | 21.8% |
| Transaction charges | ₹63,565 | 12.5% |
| Stamp duty | ₹32,101 | 6.3% |
| GST | ₹31,778 | 6.3% |
| SEBI | ₹2,140 | 0.4% |
| **Total** | **₹5,07,974** | **100%** |

**The math problem:**
- Gross profit: +₹1.86L
- Charges: ₹5.08L
- **Shortfall: ₹3.22L**
- You need **₹5.08L gross profit just to break even**
- At 32.5% win rate and ₹83 avg loss per trade → impossible at this volume

**STT alone (₹2.68L) exceeds gross profits (₹1.86L).**

---

### 🔴 3. The 54.6% Breakeven Trap

2,114 trades (54.6%) close within ±₹100:

| Metric | Value |
|---|---|
| Trades in ±₹100 range | 2,114 (54.6%) |
| Combined PnL | −₹46,958 |
| Avg charge on these trades | ₹70 |

These trades are **not neutral** — charges convert breakeven into small losses. Over 2,114 trades, this drains ₹1.48L in charges alone with zero profit captured.

**Contributing structure:** The BE-armed trades that don't reach trail (586 trades, avg PnL: −₹46) land squarely in this zone.

---

### 🟡 4. Losing Trades Had Positive MFE (91.2%)

| MFE Range (Losers Only) | Count | % of Losers |
|---|---|---|
| MFE = 0 (no favorable move) | 230 | 8.8% |
| MFE 0.01–0.25R | 598 | 22.9% |
| MFE 0.25–0.50R | 485 | 18.6% |
| MFE 0.50–1.0R | 1,043 | 39.9% |
| MFE ≥ 1.0R | 257 | 9.8% |

**91.2% of losing trades went in the right direction first.** The strategy identifies direction correctly in most cases but cannot convert that into captured profit.

257 losers hit the 1R mark or higher before reversing — they reached the target zone but still ended as losses.

---

### 🟡 5. Signal Volume Creates Unmanageable Turnover

| Metric | Value |
|---|---|
| A+ signals generated | 22,486 |
| Executed | 3,873 (17.2%) |
| Total Turnover | ₹214 Crore |
| Avg charge per trade | ₹131 |
| Capital blocked count | 15,578 |

The engine generates enormous signal volume. Even with 5 quality gates blocking signals, the execution rate is 17.2%. This drives ₹214 Cr turnover on a ₹10L account — **214× leverage in turnover terms** — making charges irrecoverable.

---

## The Death Spiral (Verified Flow)

```
┌────────────────────────────────────────────────────────────────────┐
│  22,486 A+ signals → 3,873 execute (17.2% rate)                  │
└────────────────────────────────────────────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
  ┌───────────────┐   ┌──────────────────┐   ┌──────────────────┐
  │ 1,411 (36.4%) │   │ 2,173 (56.1%)    │   │ 289 other (7.5%) │
  │ STOP_HARD     │   │ STOP_TRAIL       │   │ FORCE/TARGET/    │
  │ −₹20.73L      │   │ +₹17.00L         │   │ SAFETY           │
  └───────────────┘   └──────────────────┘   │ +₹0.51L          │
                              │               └──────────────────┘
              ┌───────────────┼───────────────┐
              ▼                               ▼
    ┌──────────────────┐            ┌──────────────────┐
    │ 586 BE-only exits │           │ 1,587 Trail exits │
    │ −₹26,878          │           │ +₹17.27L          │
    │ (near zero each)  │           │ (1,056 W / 531 L) │
    └──────────────────┘            └──────────────────┘
                                            │
                              ┌─────────────┴──────────┐
                              ▼                        ▼
                    ┌──────────────┐         ┌──────────────┐
                    │ 1,056 wins   │         │ 531 losses   │
                    │ +₹21.74L     │         │ −₹4.47L      │
                    └──────────────┘         └──────────────┘

                    CHARGES APPLIED: −₹5.08L
                    ═══════════════════════════
                    FINAL: −₹3.22L
```

---

## Performance Dimensions

### By Time of Day

| Window | Trades | Net PnL | Win Rate | Verdict |
|---|---|---|---|---|
| 09:25–10:30 | 1,610 | +₹13,073 | 33.8% | ✅ Marginal positive |
| 10:30–12:00 | 905 | −₹1,17,442 | 32.5% | ❌ Major bleed |
| 12:00–13:15 | 822 | −₹88,922 | 31.6% | ❌ Major bleed |
| 13:15–14:05 | 536 | −₹1,28,639 | 30.2% | ❌ Worst period |

**Finding:** Only the first hour is marginally positive. Afternoon entries (13:15+) have the worst win rate (30.2%) and heaviest losses (−₹1.29L from only 536 trades).

### By Market Regime

| Regime | Trades | Net PnL | Win Rate |
|---|---|---|---|
| NEUTRAL | 1,541 | −₹90,196 | 32.6% |
| TRENDING | 947 | −₹96,032 | 33.9% |
| EXTREME | 909 | −₹82,907 | 31.9% |
| MEAN_REVERT | 476 | −₹52,796 | 30.7% |

**Finding:** Losses are uniform across all regimes. No regime is profitable. The strategy doesn't have a regime edge.

### By Sector

| Sector | Trades | Net PnL | Win Rate |
|---|---|---|---|
| NIFTY PSU BANK | 784 | **−₹1,51,350** | 29.6% |
| NIFTY METAL | 713 | −₹77,947 | 31.3% |
| NIFTY FMCG | 298 | −₹35,687 | 32.6% |
| NIFTY AUTO | 371 | −₹34,303 | 34.8% |
| NIFTY OIL AND GAS | 377 | −₹20,354 | 34.7% |
| NIFTY PHARMA | 333 | −₹10,521 | 34.8% |
| NIFTY REALTY | 256 | −₹2,562 | 31.6% |
| NIFTY IT | 564 | +₹3,548 | 36.2% |
| NIFTY MEDIA | 177 | +₹7,245 | 26.6% |

**Finding:** PSU Bank is the worst performer (−₹1.51L, 29.6% WR). Only IT and Media are marginally positive. PSU Bank alone contributes 47% of total losses.

### By Direction

| Direction | Trades | Net PnL | Win Rate |
|---|---|---|---|
| LONG (UP,LONG,LONG) | 2,295 | −₹1,80,359 | 32.5% |
| SHORT (DOWN,SHORT,SHORT) | 1,578 | −₹1,41,571 | 32.5% |

**Finding:** Both directions lose. Win rates are identical. The alignment filter ensures only aligned trades execute, but alignment doesn't provide an edge.

### Holding Period

| Metric | Value |
|---|---|
| Mean holding time | 50 min |
| Median holding time | 35 min |
| Winner avg holding | 70 min |
| Loser avg holding | 40 min |
| Min / Max | 5 min / 350 min |

**Finding:** Winners are held 75% longer than losers. The strategy exits losers quickly (good) but may not give winners enough room.

---

## Monthly Equity Progression

| Month | PnL | Trades | Cumulative |
|---|---|---|---|
| Jan 2023 | −₹3,724 | 330 | −₹3,724 |
| Feb 2023 | −₹53,395 | 313 | −₹57,119 |
| Mar 2023 | −₹17,684 | 317 | −₹74,803 |
| **Apr 2023** | **−₹1,04,658** | 261 | **−₹1,79,461** |
| May 2023 | −₹55,380 | 290 | −₹2,34,841 |
| **Jun 2023** | **+₹17,867** | 289 | −₹2,16,974 |
| Jul 2023 | −₹25,060 | 351 | −₹2,42,034 |
| Aug 2023 | −₹34,681 | 361 | −₹2,76,715 |
| **Sep 2023** | **+₹14,116** | 365 | −₹2,62,599 |
| Oct 2023 | −₹8,809 | 325 | −₹2,71,408 |
| Nov 2023 | −₹12,478 | 301 | −₹2,83,886 |
| Dec 2023 | −₹38,045 | 370 | −₹3,21,931 |

Only 2 of 12 months were positive (Jun, Sep). April was the worst (−₹1.05L).

---

## Streak Analysis

| Metric | Value |
|---|---|
| Max consecutive losses | **18** |
| Max consecutive wins | 8 |

18 consecutive losses is psychologically devastating and would likely trigger a loss of confidence in live trading.

---

## Signal Quality Gate Statistics

| Gate | Rejections |
|---|---|
| Price-HMA alignment | 56,598 |
| HMA divergence (converging) | 51,394 |
| Alignment filter (Index/Sector) | 49,922 |
| HMA slope fail | 34,352 |
| HMA separation (chop) | 17,207 |
| Crossover freshness | 2,661 |
| Insufficient capital | 15,578 |

The gates are doing heavy filtering (212K+ rejections) but the 3,873 that pass still have only 32.5% win rate — the quality gates aren't discriminating enough.

---

## Corrected Claims from Previous Analysis

| Previous Claim | Verified Truth |
|---|---|
| "Stops hit 1.7× more than targets" | **STOP exits are 30.4× more than TARGET exits** (3,584 vs 118) |
| "Charges 3× higher than gross" | **2.73× higher** (₹5.08L vs ₹1.86L) |
| "Trail never loses" | **FALSE — 531 trail-armed trades lost money** |
| "BE activation: 44% win" | **52.7% of BE-armed trades won** |
| "1,009 trades in small profit trap" | **1,172 trades** (MFE 0.01–0.6R, STOP_HARD) |
| "Target hit rate 22%" | **Target first touch: 22% (852/3,873) is correct** but only 118 trades complete as TARGET1_FULL |

---

## Recommendations for V6.9

| Issue | Current | Recommended | Rationale |
|---|---|---|---|
| BE activation too late | 0.6R | **0.4R** | 317 trades had MFE 0.4–0.6R before dying |
| Target too far | 1.5R | **1.0R** | Only 3% hit target; reduce to increase hit rate |
| Trail too wide | 2.2/1.8/1.4× ATR | **1.8/1.4/1.0× ATR** | Avg give-back is 0.47R; tighter trail captures more |
| Too many trades | 3,873/yr | **< 1,500/yr** | Cut turnover by 60% → save ~₹3L in charges |
| Afternoon entries | 13:15–14:05 allowed | **Stop entries at 12:30** | 1,358 post-noon trades lose −₹2.17L |
| PSU Bank overweight | 784 trades (20%) | **Reduce sector cap** | Worst sector, 47% of losses |
| No partial at BE | 100% held through BE | **Exit 25% at 0.4R** | Lock in profit on swing captures |

---

## Conclusion

The V6.8 strategy generates a small positive gross edge (+₹1.86L) but executes 3,873 trades generating ₹214 Cr turnover on a ₹10L account. The resulting ₹5.08L in charges erases all profits and then some. The primary fixes needed are:

1. **Dramatically reduce trade count** (fewer signals = fewer charges)
2. **Protect profits earlier** (lower BE to 0.4R, tighter trail)
3. **Cut losing time windows** (no entries after 12:30)
4. **Reduce PSU Bank exposure** (worst sector by far)

Without structural changes to reduce turnover and capture profits earlier, expect −₹3L to −₹4L annual losses.

---

_Verified Analysis Date: February 28, 2026_
_Source: `backtest_history_27-02-2026_04-55_pm.json`_
_Engine: `sector_engine_v6.8.py`_
