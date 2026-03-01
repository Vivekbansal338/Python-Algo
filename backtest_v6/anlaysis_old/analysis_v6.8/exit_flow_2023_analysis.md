# V6.8 Exit Flow Analysis — 2023 Verified Data

> [!IMPORTANT]
> All numbers in this document are **independently verified** against the raw `backtest_history_27-02-2026_04-55_pm.json` trade records (3,873 closed trades, Jan–Dec 2023).

---

## Executive Summary

| Metric | Value |
|---|---|
| **Total Trades** | 3,873 |
| **Gross PnL** | +₹1,86,044 |
| **Total Charges** | ₹5,07,974 |
| **Net PnL** | **−₹3,21,931** |
| **Win Rate** | 32.53% (1,260 W / 2,613 L) |
| **Profit Factor** | 0.85 |

---

## How Trades Flow Through the Exit System

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     TRADE ENTRY (3,873 trades)                          │
│  Hard Stop = max(1.6 × ATR_5m, Entry × 0.35%) = "1R"                  │
│  Target 1  = Entry ± 1.5R                                              │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
        ┌──────────────────────┐        ┌──────────────────────┐
        │ Price never reaches  │        │ Price reaches ≥0.6R  │
        │ 0.6R — BE never     │        │ → BE Armed           │
        │ arms                │        │ 2,363 trades (61.0%) │
        │ 1,510 trades (39.0%)│        └──────────────────────┘
        └──────────────────────┘                    │
                    │                   ┌───────────┴───────────┐
                    ▼                   ▼                       ▼
    ┌──────────────────────────┐  ┌────────────────┐  ┌──────────────────┐
    │ EXIT A: STOP_HARD        │  │ Price reaches  │  │ Price stays      │
    │ 1,411 trades (36.4%)     │  │ ≥0.8R → Trail  │  │ below 0.8R →    │
    │ Net PnL: −₹20,73,472    │  │ Armed          │  │ BE Stop Only     │
    │ Avg PnL: −₹1,470        │  │ 1,763 (45.5%)  │  │ 586 trades       │
    │ Win Rate: 0.0%           │  └────────────────┘  │ (15.1%)          │
    └──────────────────────────┘          │            └──────────────────┘
                                          │                     │
                              ┌───────────┼─────────┐           ▼
                              ▼           ▼         ▼   ┌───────────────┐
                    ┌──────────────┐ ┌─────────┐ ┌──┐   │ EXIT B:       │
                    │STOP_TRAIL    │ │TARGET1  │ │FE│   │ STOP_TRAIL    │
                    │1,587 trades  │ │118      │ │57│   │ (BE, no trail)│
                    │Net:+₹17.27L │ │Net:+₹290│ │  │   │ 586 trades    │
                    └──────────────┘ └─────────┘ └──┘   │ Net:−₹26,878 │
                                                        │ Avg: −₹46    │
                                                        └───────────────┘
```

---

## Verified Exit Reason Breakdown

| Exit Reason | Trades | % | Net PnL | Avg PnL | Win Rate |
|---|---|---|---|---|---|
| **STOP_TRAIL** | 2,173 | 56.1% | +₹17,00,346 | +₹782 | 48.6% |
| **STOP_HARD** | 1,411 | 36.4% | −₹20,73,472 | −₹1,470 | 0.0% |
| **FORCE_EXIT** | 170 | 4.4% | +₹41,249 | +₹243 | 50.0% |
| **TARGET1_FULL** | 118 | 3.0% | +₹290 | +₹2 | 100.0% |
| **SAFETY_HALT** | 1 | 0.0% | +₹9,657 | +₹9,657 | 100.0% |

> [!WARNING]
> **STOP_HARD has 0% win rate** — every single STOP_HARD exit is a loss. This is by design (the hard stop is the worst-case exit), but 36.4% of all trades hitting it is concerning.

---

## STOP_HARD Deep Dive (1,411 Trades)

### How much favorable movement did these trades see before hitting the hard stop?

| MFE Range | Trades | % of STOP_HARD | Description |
|---|---|---|---|
| **MFE = 0** (no movement) | 233 | 16.5% | Immediate reversal from entry |
| **MFE 0.01–0.10R** | 173 | 12.3% | Tiny blip before stop |
| **MFE 0.10–0.20R** | 288 | 20.4% | Small favorable move |
| **MFE 0.20–0.30R** | 228 | 16.2% | Moderate initial move |
| **MFE 0.30–0.40R** | 166 | 11.8% | Almost reached 0.4R |
| **MFE 0.40–0.50R** | 167 | 11.8% | Almost reached 0.5R |
| **MFE 0.50–0.60R** | 150 | 10.6% | Almost reached BE trigger |
| **MFE ≥ 0.60R** | 6 | 0.4% | Rare: went through BE then back to hard stop |

**Key Finding:** 1,172 trades (83.1% of STOP_HARD) had MFE between 0.01R and 0.6R — they moved in the right direction but never triggered breakeven protection.

**Total damage from these 1,172 trades: −₹17,46,672 (Avg: −₹1,490 each)**

---

## STOP_TRAIL Deep Dive (2,173 Trades)

### Sub-categories:

| Sub-path | Trades | % of All | Net PnL | Avg PnL | Description |
|---|---|---|---|---|---|
| **BE armed, trail NOT armed** | 586 | 15.1% | −₹26,878 | −₹46 | BE triggered, reversed before 0.8R |
| **Trail armed via STOP_TRAIL** | 1,587 | 41.0% | +₹17,27,224 | +₹1,088 | Trailing stop captured profit |

> [!CAUTION]
> **The existing report claimed "Trail never loses" — this is FALSE.** Of 1,587 trail-armed STOP_TRAIL exits, 531 (33.5%) were losses. Trail-armed trades had a 69.9% win rate overall, **not 100%**.

---

## BE Armed Analysis (2,363 Trades)

| Metric | Value |
|---|---|
| Trades reaching BE (0.6R) | 2,363 (61.0% of all) |
| BE-armed that eventually won | 1,245 (52.7%) |
| BE-armed that eventually lost | 1,118 (47.3%) |
| BE-armed avg PnL | +₹758 |
| BE-armed total PnL | +₹17,90,050 |

### BE-Armed → Stopped Out (2,173 trades):

| Metric | Value |
|---|---|
| Avg MFE_R at stop | 1.47R |
| Median MFE_R at stop | 1.12R |
| MFE ≥ 2R before stop | 431 (19.8%) |
| MFE 1–2R before stop | 839 (38.6%) |

**This means trades reached an average of 1.47R favorable move before the trailing/BE stop caught them, giving back 0.47R on average.**

---

## Trail Armed Analysis (1,763 Trades)

| Exit Type | Trades | Net PnL | Avg PnL | Wins | Losses |
|---|---|---|---|---|---|
| STOP_TRAIL | 1,587 | +₹17,27,224 | +₹1,088 | 1,056 | 531 |
| TARGET1_FULL | 118 | +₹290 | +₹2 | 118 | 0 |
| FORCE_EXIT | 57 | +₹73,743 | +₹1,294 | 57 | 0 |
| SAFETY_HALT | 1 | +₹9,657 | +₹9,657 | 1 | 0 |
| **Total** | **1,763** | **+₹18,10,914** | **+₹1,027** | **1,232** | **531** |

---

## R-Multiple and Stop Mechanics

### Stop Calculation (from code line 1597)

```python
R0 = max(ATR_5min × 1.6, Entry_Price × 0.35%)
```

| R-Multiple | Price Level (₹100 entry, R=₹2) | Event |
|---|---|---|
| 0R | ₹100.00 | Entry |
| −1R | ₹98.00 | **Hard Stop** (max loss) |
| +0.6R | ₹101.20 | **BE Armed** → stop moves to ₹100.03 |
| +0.8R | ₹101.60 | **Trail Armed** → Chandelier trailing activates |
| +1.5R | ₹103.00 | **Target 1** → 50% position exit |

### Key Thresholds (from config)

| Constant | Value | Description |
|---|---|---|
| `STOP_ATR_MULT_5M` | 1.6× | Hard stop distance (ATR multiple) |
| `STOP_MIN_PCT` | 0.35% | Minimum stop distance |
| `BE_ARM_R` | 0.6R | Breakeven activation |
| `BE_BUFFER_BPS` | 3 bps | Buffer above entry for BE stop |
| `TRAIL_ARM_R` | 0.8R | Trailing stop activation |
| `TRAIL_LOOKBACK_BARS` | 10 | Chandelier lookback bars |
| `TRAIL_MULT_LOW` | 2.2× | Trail when MFE < 1R |
| `TRAIL_MULT_MID` | 1.8× | Trail when 1R ≤ MFE < 2R |
| `TRAIL_MULT_HIGH` | 1.4× | Trail when MFE ≥ 2R |
| `TARGET_1_MULT` | 1.5R | Target 1 distance |

---

## PnL Distribution

| PnL Range | Trades | % | Total PnL |
|---|---|---|---|
| < −₹5,000 | 26 | 0.7% | −₹1,34,156 |
| −₹5,000 to −₹1,000 | 726 | 18.7% | −₹18,48,096 |
| −₹1,000 to −₹100 | 220 | 5.7% | −₹1,29,452 |
| **−₹100 to +₹100** | **2,114** | **54.6%** | **−₹46,958** |
| +₹100 to +₹500 | 155 | 4.0% | +₹43,437 |
| +₹500 to +₹1,000 | 126 | 3.3% | +₹91,517 |
| +₹1,000 to +₹5,000 | 419 | 10.8% | +₹10,78,485 |
| > +₹5,000 | 87 | 2.2% | +₹6,23,292 |

**54.6% of trades close within ±₹100 — effectively breakeven, but net −₹46,958 from charges.**

---

## 💰 Brokerage Impact Analysis

### Per-Trade Charge Statistics

| Metric | Value |
|---|---|
| Mean charge per trade | ₹131 |
| Median charge per trade | ₹124 |
| Min / Max | ₹0.03 / ₹423 |

### Charge as % of Risk (R)

| Bucket | Trades | % |
|---|---|---|
| < 5% of R | 108 | 2.8% |
| 5–10% of R | 808 | 20.9% |
| 10–20% of R | 1,785 | 46.1% |
| 20–50% of R | 1,172 | 30.3% |
| > 50% of R | 0 | 0.0% |

**76.4% of trades pay 10–50% of their risk in charges alone.**

### By Trade Outcome

| Outcome | Trades | Avg Charge | Charge % of R | Total |
|---|---|---|---|---|
| Winners (PnL > ₹100) | 787 | ₹215 | 12.5% | ₹1,69,492 |
| Losers (PnL < −₹100) | 972 | ₹196 | 11.7% | ₹1,90,678 |
| Breakeven (±₹100) | 2,114 | ₹70 | 19.9% | ₹1,47,804 |

### By Risk Size

| Category | Trades | % | Avg Charge % of R |
|---|---|---|---|
| Small (R < ₹2,000) | 2,743 | 70.8% | 19.5% |
| Medium (R ₹2K–5K) | 1,118 | 28.9% | 8.9% |
| Large (R > ₹5,000) | 12 | 0.3% | 4.4% |

---

## 🚨 Key Concerns (Ranked by PnL Impact)

### 1. STOP_HARD Losses — ₹20.7L Damage 🔴

All 1,411 STOP_HARD exits are losses. Combined PnL: **−₹20,73,472**.

Of these, 1,172 (83%) had favorable MFE between 0.01R and 0.6R before reversing to the stop — they moved in the right direction but couldn't reach the 0.6R breakeven threshold.

### 2. Near-Zero Trades Masking Losses — 54.6% 🔴

2,114 trades close within ±₹100. Their combined PnL is −₹46,958 (from charges).
These feel like "no harm done" but collectively they drain capital through transaction costs.

### 3. TARGET1_FULL Has Near-Zero Net PnL 🔴

Despite 118 trades hitting the 1.5R target at 100% win rate, the **total net PnL is only +₹290**. This means charges almost entirely consume the target profits for partial exits.

### 4. Trail-Armed Losses Exist — 531 Trades 🟡

531 trail-armed trades ended in loss (33.5% of trail exits via STOP_TRAIL). The trailing stop doesn't guarantee profit — it can still pull back to below entry after being armed.

### 5. Afternoon Entries Are Worst — −₹1.29L 🟡

Entries after 13:15 produce −₹1,28,639 net PnL with 30.2% win rate vs morning entries (09:25–10:30) which are marginally positive at +₹13,073.

---

## Recommended Remedies

| Current | Problem | Suggested Fix | Expected Impact |
|---|---|---|---|
| BE at 0.6R | 1,172 trades miss it, hit stop | **Lower to 0.4R** | Save ~333 trades (0.4–0.6R band) |
| Trail at 0.8R | Many trades reverse 0.6–0.8R | **Lower to 0.6R** | More trades reach trailing |
| Target at 1.5R | Only 3% hit, +₹290 net | **Lower to 1.0R** | Higher hit rate, meaningful PnL |
| No time filter | Afternoon entries lose | **Cutoff entries at 13:15** | Avoid 536 losing entries |
| No BE partial | 54.6% give back all gains | **Sell 25–30% at BE** | Lock in some profit |

---

## Data Verification

| Field | Source | Verified Value |
|---|---|---|
| Total trades | `trade_records` array length | 3,873 |
| Net PnL | Sum of `realized_pnl` | −₹3,21,930.64 |
| Gross PnL | Sum of `gross_pnl` | +₹1,86,043.50 |
| Total charges | Sum of `total_charges` | ₹5,07,974.14 |
| Total turnover | Sum of `total_turnover` | ₹214.02 Cr |

**This is an independently verified document. All numbers are computed directly from trade records, not from summary fields.**

---

_Analysis Date: February 28, 2026_
_Source: `backtest_history_27-02-2026_04-55_pm.json` (2023 data, V6.8 engine)_
