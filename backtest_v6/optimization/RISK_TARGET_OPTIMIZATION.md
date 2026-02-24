# Risk/Target Optimization — Final Plan

**Date:** 2026-02-23
**Scope:** Evidence locked to `backtest_v6` only — `sector_engine_v6.py`, `analysis/analyze_backtest.py`, `BACKTEST_OUTPUT_STRUCTURE.md`, and `backtest_history_23-02-2026_09-35_am.json` / `advanced_analysis_23-02-2026_07-00_pm.json`.

---

## 1. Problem Diagnosis

### 1.1 What Is Currently Wrong

The trading engine has a fundamental structural problem: **risk management barely engages during trades**. The stop and target levels are set so far from the entry price that almost no trade ever touches them during an intraday session. Every trade enters, drifts, and is force-closed at end-of-day — meaning the stop and target system is functionally non-existent.

Current behavior:

- Entry stop is computed from **daily ATR (period 10)**, producing an average stop distance of **5.09%**.
- Target-1 is fixed at **~7.64%** away from entry.
- The chandelier trailing stop only activates **after target-1 is hit**, which transitions the trade to PARTIAL stage.
- Since target-1 almost never triggers intraday, trailing never engages either.
- The result: almost every trade lives and dies in the ACTIVE stage, waiting for day-end cleanup.

### 1.2 Evidence from Backtest Data

Numbers are sourced directly from `advanced_analysis_23-02-2026_07-00_pm.json` and `backtest_history_23-02-2026_09-35_am.json`:

| Metric                     | Value                    |
| -------------------------- | ------------------------ |
| Closed trades              | 1,121                    |
| Win rate                   | 49.51%                   |
| Net PnL                    | +21,397.75               |
| Profit Factor              | 1.05                     |
| Mean stop distance         | 5.09%                    |
| Mean target distance       | 7.64%                    |
| First-touch NONE           | **99.91%** (1120 / 1121) |
| Exit reason FORCE_EXIT     | **100%** (1121 / 1121)   |
| Median realized R          | 0.0                      |
| Mean realized R            | 0.0073                   |
| Max peak deployed notional | 1,177,909 on 1,000,000   |

Key insight: **every single closed trade** exited via FORCE_EXIT at 15:05. Not one stop, not one target, not one chandelier trail fired meaningfully. The risk system is completely passive.

### 1.3 Root Cause

The stop and target bands are calibrated to **daily volatility** but the trades are held **intraday**. A 5% stop on a stock that moves 0.5–1% per 5-minute bar requires a very large adverse move to touch, which rarely happens within a single session. This creates three cascading problems:

1. **Losses drag too long** — wide stops mean losing trades are held all day without being cut.
2. **Winners underperform** — trailing never starts because target-1 never triggers.
3. **Every trade is dead weight** — median realized R is zero; the system survives only on occasional outliers.

The expected value per trade:

```
E = W × avg_gain - (1 - W) × avg_loss
  = 0.4951 × 856 - 0.5049 × 810
  = 423.80 - 408.97
  = +14.83 per trade (thin)
```

The goal is to reduce average loss while preserving gains, bringing PF from 1.05 to ≥ 1.20.

### 1.4 Critical Code-Level Bugs That Must Be Fixed First

The following bugs were found by reading `sector_engine_v6.py` directly. They make the current backtest results unreliable as an optimization baseline. **None of these were identified in earlier analysis passes.** All must be fixed before any parameter optimization begins.

---

**Bug #1 — Chandelier Uses Entry-Day Daily ATR, Not Intraday ATR (lines 1129–1148)**

```python
atr_buffer = trade.atr_at_entry * config.CHANDELIER_ATR_MULT
```

`trade.atr_at_entry` is the daily ATR(10) at entry time. Daily ATR averages ~5% of price. With `CHANDELIER_ATR_MULT = 3.0`, the chandelier sits 15% from the swing anchor. This band is so wide it will never fire during a single intraday session. The plan to "arm trailing before TP1" is meaningless unless the chandelier geometry is also fixed. Arming a 15% chandelier earlier produces zero behavioral change. **The chandelier must be rewritten to use a rolling 5-minute ATR, not the entry-day daily ATR.**

---

**Bug #2 — Safety Monitor Receives Breadth = 0.0 at Every Tick (line 1301)**

```python
self.safety.update(self.nifty_ltp, self.vix_ltp, 0.0)
```

Market breadth is correctly computed per sector inside `_update_sector_scores` (line 692) and stored in `SectorScore.breadth`, but the value is never passed to `SafetyMonitor`. The monitor always receives zero breadth, so any breadth-based halt threshold is permanently defeated. This means `SAFETY_HALT` almost never fires in backtest, which flatters the backtest result. In live trading, a real breadth signal would trigger halts that the backtest doesn't model. **This is a single-line correctness fix with potentially large behavioral impact.**

---

**Bug #3 — Stop Executes at Stop Price Regardless of Candle Gap (lines 1158–1165)**

```python
stop_hit = (trade.direction == "LONG" and low <= trade.current_stop) or ...
if stop_hit:
    self._close_trade(trade_id, trade, ts, float(trade.current_stop), "STOP")
```

When the candle's low is below the stop price, the trade closes at exactly `trade.current_stop`, not at the candle's open or low. In reality, a gap below the stop fills at the open of the next bar. This produces **optimistic stop fill prices** throughout the backtest, understating true stop-loss magnitude. With ~560 losing trades in the dataset, this systematic optimism is embedded in every PnL figure. The true PF without this optimism may be below 1.0. **A configurable slippage model on stop fills is required before any results are comparable to live trading.**

---

**Bug #4 — Sector NEUTRAL Overwrites Grade to C Regardless of Individual Metrics (lines 857–859)**

```python
elif sec_bias == "NEUTRAL":
    signal.grade = "C"
    signal.reasons.append("Sector Bias NEUTRAL")
```

Any stock in a NEUTRAL-tagged sector has its grade forced to C, overriding all individual signal quality — HMA alignment, RVOL, StochRSI, spread quality. A stock scoring 9/10 on individual metrics is demoted to C purely because its sector is NEUTRAL. The 89.5% signal rejection rate (10,718 generated → 1,121 executed) cannot be fully attributed to position limits alone; NEUTRAL sector suppression is likely a significant contributor at the grading stage. **The true opportunity set lost to NEUTRAL suppression must be measured before any policy change is made.**

---

**Bug #5 — RVOL Denominator Includes the Current Bar (lines 748–758)**

```python
recent = volumes[-20:]
avg = float(np.mean(recent))
last = float(recent[-1])
return calculate_rvol(last, avg) if avg > 0 else 0.0
```

RVOL compares the current bar's volume against the average of the last 20 bars **including itself**. If the current bar is high-volume (exactly the case we want to detect), including it in the denominator suppresses the ratio. Standard RVOL uses same-time-of-day historical volume from prior sessions. This definition is a useful proxy but is not what documentation describes. **The definition must be documented precisely and consistently used as-is, or corrected to proper same-time historical comparison.**

---

### 1.5 Critical Strategic Findings from the Backtest Data

Beyond bugs, the analytics reveal structural problems that affect the optimization order.

**Finding #1 — The OPEN bucket destroys 110% of net profit**

| Bucket              | Trades | Win Rate | Net PnL |
| ------------------- | ------ | -------- | ------- |
| OPEN (09:25–10:30)  | 790    | 48.35%   | −4,235  |
| MID (10:30–12:00)   | 243    | 53.91%   | +23,518 |
| LUNCH (12:00–13:15) | 66     | 48.48%   | +1,756  |
| AFTERNOON           | 22     | 45.45%   | +358    |

790 trades (70.5% of all trades) happen in the OPEN window and generate negative total PnL. 243 trades in MID generate positive PnL that exceeds the entire system's net profit. The system is economically viable only because of a 2-hour MID window. This is not a risk-parameter problem — it is a structural time-of-day problem that must be addressed before stop geometry tuning.

**Finding #2 — The TRENDING regime is net negative despite the strategy using trend indicators**

| Regime      | Trades | Win Rate | Net PnL |
| ----------- | ------ | -------- | ------- |
| TRENDING    | 483    | 48.24%   | −10,946 |
| NEUTRAL     | 319    | 47.65%   | +25,478 |
| EXTREME     | 185    | 57.30%   | +16,121 |
| MEAN_REVERT | 134    | 47.76%   | −9,255  |

HMA alignment is a trend-following indicator. It generates the most signals when markets are trending. Yet TRENDING regime produces the worst aggregate PnL. The strategy is noisiest and least effective precisely when its primary signal is most active. EXTREME regime (high VIX) has the best win rate and strong positive PnL on fewer trades — the strategy appears to work as a mean-reversion play under stress, not as a trend-follow in smooth conditions.

**Finding #3 — First-trade outcome predicts the day with 0.5838 correlation**

| First Trade | Days | Subsequent Day Win Rate |
| ----------- | ---- | ----------------------- |
| FIRST_WIN   | 96   | 72.92%                  |
| FIRST_LOSS  | 105  | 34.29%                  |

When the first trade of the day is a winner, subsequent trades win at 61.74%. When it is a loser, subsequent trades win at only 38.64%. This reflects real market momentum clustering: good conditions early → good conditions throughout the day. The correlation of 0.5838 is actionable — it allows a live day-state machine that reduces risk exposure after a first-trade loss.

**Finding #4 — Deployed notional exceeded 100% of equity**

Max peak deployed notional was 1,177,909 on 1,000,000 equity (117.8% utilization). The system can be implicitly leveraged when multiple trades enter simultaneously before earlier ones have settled. Combined with multi-concurrent losing trades, this creates uncontrolled tail risk. A gross notional cap must be added.

**Finding #5 — Counter-trend trades destroy 53,621 in PnL**

| Scenario                        | Trades | Net PnL |
| ------------------------------- | ------ | ------- |
| ↑↑↑ (all aligned UP)            | 452    | +32,878 |
| ↓↓↓ (all aligned DOWN)          | 328    | +41,347 |
| ↓↑↑ (LONG signal in DOWN index) | 161    | −34,043 |
| ↑↓↓ (SHORT signal in UP index)  | 131    | −19,578 |

Fully-aligned trades generate +74,225 on 780 trades. Counter-trend trades (where stock signal opposes index direction) destroy −53,621 on 292 trades. The index-signal alignment gate should block or heavily size-reduce trades where the signal direction conflicts with the broad market direction. This is the highest PnL-recovery item in the entire backtest and requires no parameter optimization — the data implies the rule directly.

---

## 2. Solution Design

### 2.1 Core Principle

Risk must transition from **static-at-entry** to **stateful-through-time**:

- Hard initial risk cap at entry, sized in intraday terms
- Early invalidation exits for weak trades that fail to confirm
- Progressive stop tightening as trade confirms forward movement
- Asymmetrical upside capture — protect capital on losers, let winners develop

### 2.2 Entry Risk Model — Intraday-Native Stop

**Replace daily ATR with 5-minute ATR at entry timestamp:**

```
atr_5m_entry = ATR_5m(14) using candles up to entry timestamp (inclusive)

Initial stop distance:
R0 = max(ATR_5m_entry × m_stop, entry_price × stop_min_pct)

Starting config values (pending Block A optimization):
  m_stop = 1.6
  stop_min_pct = 0.0035 (0.35%)
```

The 5-minute ATR at a typical NSE mid-cap stock is roughly 0.5–0.8% per bar. With `m_stop = 1.6`, this produces a stop of ~0.8–1.3% — meaningful intraday protection without being so tight it is noise-hit immediately.

All downstream R-multipliers (`mfe_r`, `mae_r`, stop distance, TP levels) are expressed in **units of R0**. This makes all trades comparable regardless of price or volatility level.

Store at entry:

- `entry_risk_per_share = R0` (the fixed risk denominator for the life of the trade)
- `entry_atr_5m` (the ATR value used at entry)

### 2.3 Chandelier Trail Rewrite — Use Rolling 5-Minute ATR

**The chandelier must be rebuilt from scratch.** It currently uses `trade.atr_at_entry` (daily ATR scale), producing 15% bands that never fire intraday. The new chandelier must use a **rolling 5-minute ATR computed at each bar**, not the entry-date daily ATR.

```
At each active bar:
  atr_5m_current = ATR_5m(TRAIL_LOOKBACK_BARS) at current timestamp

  if trade.direction == "LONG":
    swing_anchor = max(high[-TRAIL_LOOKBACK_BARS:])
    trail_stop = swing_anchor - (trail_mult × atr_5m_current)
  else:
    swing_anchor = min(low[-TRAIL_LOOKBACK_BARS:])
    trail_stop = swing_anchor + (trail_mult × atr_5m_current)
```

The trail stop can only move in the favorable direction — it never loosens.

**Trail multiplier schedule based on MFE in R-units:**

```
if mfe_r < 1.0:     trail_mult = TRAIL_MULT_LOW   (default: 2.2)
if 1.0 <= mfe_r < 2.0: trail_mult = TRAIL_MULT_MID (default: 1.8)
if mfe_r >= 2.0:    trail_mult = TRAIL_MULT_HIGH  (default: 1.4)
```

The trail tightens progressively as the trade moves further in profit. A trade hitting 2R gets a tighter trail than a trade just crossing 1R.

### 2.4 Time-Stop Invalidation — Exit Dead Trades Early

Many trades enter and make no meaningful forward progress. Holding them to day-end wastes capital that could be redeployed. The time-stop exits trades that fail to show early momentum:

```
Condition (check every bar while in ACTIVE stage):
  bars_held >= TIME_STOP_BARS    (default: 6 bars = 30 minutes)
  AND mfe_r < TIME_STOP_MIN_MFE_R  (default: 0.35R)

Action:
  Exit at market price
  Record exit_reason = TIME_INVALIDATION
```

This targets the common failure pattern: trade enters, meanders sideways or slightly adverse, and eventually gets force-closed at day-end for a moderate loss. The time-stop converts these into smaller, earlier losses and frees up position slots.

### 2.5 Early Breakeven Arm — Protect Confirmed Winners

When a trade moves favorably enough to validate the direction thesis, move the stop to entry plus a small friction buffer. This converts the trade from a potential loser into a worst-case breakeven:

```
Condition:
  mfe_r >= BE_ARM_R     (default: 0.6R)
  AND stop not yet at breakeven

Action:
  new_stop = entry_price + (BE_BUFFER_BPS × price / 10000) [for LONG]
  new_stop = entry_price - (BE_BUFFER_BPS × price / 10000) [for SHORT]
  Record: be_armed = True
  exit_reason if hit = STOP_TRAIL (stop moved to BE level)
```

Default `BE_ARM_R = 0.6R` means: once the trade has moved 0.6× the initial risk in our favor, the risk of loss is eliminated. This single change has the largest potential impact on the left tail of the P&L distribution.

### 2.6 Adaptive Trailing — Armed Before TP1 Hit

**Trailing must be armed based on MFE reaching `TRAIL_ARM_R`, completely independent of any partial exit (TP1/TP2).** In the current engine, trailing waits for the target-1 price hit which transitions the trade to `PARTIAL` stage. Since target-1 never hits (99.91% NONE), trailing never engages.

```
Condition to arm trail:
  mfe_r >= TRAIL_ARM_R     (default: 0.8R)
  AND trail_armed == False

Action:
  trail_armed = True
  Set initial trail_stop using swing anchor + 5m ATR trail formula above
```

Once armed, the trail is computed at every bar. If the current trail stop level is worse than the existing stop (for the wrong direction), skip — the stop never loosens. The trail only tightens.

**Full active-trade management loop order (per bar):**

1. Update `bars_held`, `mfe_r`, `mae_r` for this bar
2. Check hard stop at current `stop_price` → if hit, close with `STOP_HARD`
3. Check time invalidation condition → if met, close with `TIME_INVALIDATION`
4. Check breakeven arm condition → if met, move stop to entry level
5. Check trail arm condition (MFE ≥ TRAIL_ARM_R) → if met, arm trail
6. If trail is armed, compute updated trail stop; raise stop if improvement
7. If trail stop is hit, close with `STOP_TRAIL`
8. Check TP1/TP2 partial conditions (see section 2.7) → process if applicable
9. If day-end (15:05), close remaining position with `FORCE_EXIT`

### 2.7 Partial Exits — Candidate Architecture, Not Mandatory

A two-step partial exit structure is kept in the parameter search space but is **not locked as baseline doctrine**. It may clip the right tail in trending conditions and will be evaluated as an optional profit extraction layer after core trailing behavior is validated.

The partial exit structure if activated:

```
TP1:
  Condition: mfe_r >= TP1_R     (default: 1.0R)
  Action: close TP1_EXIT_PCT of position (default: 35%)
  Record: tp1_done = True

TP2:
  Condition: tp1_done == True AND mfe_r >= TP2_R   (default: 1.8R)
  Action: close TP2_EXIT_PCT of remaining position  (default: 25% of remaining)
  Record: tp2_done = True

Constraint: Combined TP1 + TP2 partials ≤ 70% of original position
            Remaining runner ≥ 30% must be held until trail fires or day-end
```

Both partials are evaluated last in the loop (after trail), so the trail has priority over partial logic.

### 2.8 Exit Reason Taxonomy

All exits must be recorded with a structured reason code for analysis:

| Reason              | When Applied                                   |
| ------------------- | ---------------------------------------------- |
| `STOP_HARD`         | Price crosses initial hard stop level          |
| `STOP_TRAIL`        | Rolling trail stop is hit (including BE level) |
| `TIME_INVALIDATION` | bars_held ≥ N and mfe_r < threshold            |
| `TARGET1_FULL`      | Full position exits at TP1 (no runner kept)    |
| `TP1_PARTIAL`       | Partial exit at TP1 threshold                  |
| `TP2_PARTIAL`       | Partial exit at TP2 threshold                  |
| `FORCE_EXIT`        | Day-end forced close at 15:05                  |
| `SAFETY_HALT`       | SafetyMonitor triggered halt                   |

Success metric: `FORCE_EXIT` share must drop materially from baseline 100%. First-touch `NONE` must drop materially from baseline 99.91%.

---

## 3. Conditional Risk Controls

These controls are activated **before** any stop/trail parameter optimization. They are data-driven, require minimal or zero new parameters, and address the structural PnL losses identified in the backtest analytics. They are not optimization levers — they are regime-aware and time-aware risk gates.

### 3.1 Time-of-Day Position Sizing

The OPEN window accounts for 70.5% of all trades but generates net negative PnL. MID window generates more PnL than the entire system's net. Position size should reflect this imbalance:

```python
BUCKET_SIZE_MULT = {
    "OPEN":      0.65,   # 09:25–10:30, high noise
    "MID":       1.00,   # 10:30–12:00, highest edge
    "LUNCH":     0.85,   # 12:00–13:15, moderate
    "AFTERNOON": 0.75,   # 13:15–14:05, thin liquidity
}

position_size = base_size × BUCKET_SIZE_MULT[current_bucket]
```

This is a one-parameter-per-bucket change. It does not change entry logic, stop logic, or any other system behavior.

### 3.2 Regime Risk Multiplier

TRENDING regime is the single worst-performing category (−10,946 net PnL on 483 trades) despite the strategy being built on trend indicators (HMA). EXTREME regime is the best (57.3% win rate, +16,121). Risk exposure must be reduced in TRENDING regime:

```python
REGIME_RISK_MULT = {
    "TRENDING":   0.50,   # net negative; reduce exposure
    "NEUTRAL":    1.00,   # best absolute PnL
    "EXTREME":    1.20,   # best win rate; allow slight overweight
    "MEAN_REVERT": 0.70,  # net negative; reduce exposure
}

risk_amount = base_risk × REGIME_RISK_MULT[current_regime]
```

This is applied inside `_process_entry`. No change to signal generation or stop geometry.

### 3.3 Index-Signal Alignment Gate

Counter-trend trades (stock signal direction opposes index direction) destroy −53,621 in PnL on 292 trades. Fully-aligned trades generate +74,225 on 780 trades. The gate is:

```
If nifty_dir == "DOWN" and signal.direction == "LONG":
    Apply COUNTER_TREND_SIZE_MULT (default: 0.0 = block entirely, or 0.4 = allow at small size)

If nifty_dir == "UP" and signal.direction == "SHORT":
    Apply COUNTER_TREND_SIZE_MULT (same)
```

Start with `COUNTER_TREND_SIZE_MULT = 0.0` (full block) and compare against `0.4` (reduced size). The full block saves −53,621 in losses but also removes any counter-trend winners. Measure net effect before locking in.

### 3.4 First-Trade Day-State Machine

First-trade outcome predicts the day with 0.5838 correlation. Implement a session-level state:

```python
first_trade_outcome = None   # resets each day

When first trade closes:
    first_trade_outcome = "WIN" if pnl > 0 else "LOSS"

After first_trade_outcome is set:
    if first_trade_outcome == "WIN":
        day_risk_mult = 1.0   # maintain normal sizing
    elif first_trade_outcome == "LOSS":
        day_risk_mult = 0.5   # reduce subsequent risk
        time_stop_bars = TIME_STOP_BARS - 1   # tighten time invalidation
```

This requires no new parameters beyond a single `day_risk_mult` multiplier and reuses the existing `TIME_STOP_BARS` config.

### 3.5 Gross Notional Cap

A single check before executing any new entry:

```python
current_notional = sum(qty × price for all open trades)
new_trade_notional = proposed_qty × entry_price

if current_notional + new_trade_notional > equity × MAX_NOTIONAL_MULT:
    reject trade, log reason = "NOTIONAL_CAP"
```

Default: `MAX_NOTIONAL_MULT = 1.1` (allow up to 10% above equity; current max is 117.8%). This prevents leverage spikes during dense entry windows.

---

## 4. Implementation Plan

Execution is strictly phased. Each phase validates before the next phase begins. No phase skips forward until the previous phase has produced verified output.

### Phase 0 — Baseline Instrumentation (No Behavior Changes)

**Goal:** Get accurate measurement of what is actually happening before changing anything.

Add to `BacktestTrade` in `sector_engine_v6.py`:

- `entry_risk_per_share`: R0 computed at entry (5m ATR × mult with floor)
- `bars_held`: incremented each active bar
- `mfe_r`: maximum favorable excursion in R-units (running max)
- `mae_r`: maximum adverse excursion in R-units (running min)
- `first_stop_touch_ts`: timestamp of first bar where price touches stop level
- `first_target_touch_ts`: timestamp of first bar where price touches target-1
- `first_touch_type`: `STOP` / `TARGET` / `NONE`
- `exit_candle_open`, `exit_candle_high`, `exit_candle_low`, `exit_candle_close`
- `theoretical_exit_price`: where stop/target was set
- `sector_bias_at_signal`: the sector_bias value at signal time
- `downgraded_by_neutral_bias`: True if grade was overwritten by NEUTRAL bias

Add signal-level diagnostics:

- `neutral_suppressed_count` per day: count of how many A/A+ signals were demoted to C by NEUTRAL sector bias

Add to `analyze_backtest.py`:

- MFE/MAE distribution in R-units
- First-touch type breakdown
- Exit candle slippage (actual exit vs theoretical)
- Day-level first-trade correlation
- Sector-NEUTRAL suppression statistics

**Deliverable:** Re-run baseline with instrumentation. This instrumented output becomes the measurement baseline for all subsequent phases.

---

### Phase 1 — Correctness and Realism Fixes

**Goal:** Ensure the backtest engine reflects realistic trade behavior before any optimization.

**Fix 1 — Safety Monitor Breadth (Bug #2)**

Replace:

```python
self.safety.update(self.nifty_ltp, self.vix_ltp, 0.0)
```

With:

```python
market_breadth = self._compute_market_breadth()  # from VWAP above/below analysis
self.safety.update(self.nifty_ltp, self.vix_ltp, market_breadth)
```

**Fix 2 — Stop Fill Slippage (Bug #3)**

Replace exact-stop-price execution with gap-aware fill:

```python
if stop_hit:
    candle_open = bar["open"]
    # If price gapped through stop at open, fill at open (worse than stop)
    fill_price = candle_open if (direction == "LONG" and candle_open < stop) else stop
    fill_price = fill_price * (1 - STOP_SLIPPAGE_PCT)   # configurable friction
    self._close_trade(trade_id, trade, ts, fill_price, "STOP_HARD")
```

Default: `STOP_SLIPPAGE_PCT = 0.001` (10 bps).

**Fix 3 — Same-Bar Event Priority**

Define a conservative priority when stop and target are both touched in the same bar:

```
Priority order: STOP_HARD > TIME_INVALIDATION > STOP_TRAIL > TP1 > TP2
```

Document this in `BACKTEST_OUTPUT_STRUCTURE.md` as a defined behavioral rule.

**Deliverable:** Re-run corrected baseline. This produces the only valid optimization baseline. All acceptance criteria are relative to this corrected baseline, not the original 1.05 PF figure.

---

### Phase 2 — Core Risk/Target V2 Activation

**Goal:** Rebuild the stop/trail system with intraday-native geometry. Keep parameter count minimal — use the starting config values; do not tune yet.

Files to modify:

- `backtest_v6/sector_engine_v6.py` — all trade logic
- `v6/config.py` — add new config keys behind backward-compatibility flag

**Config additions to `v6/config.py`:**

```python
# Backward compatibility: keep legacy behavior behind a flag
RISK_TARGET_MODEL = "V2_INTRADAY"   # "LEGACY" | "V2_INTRADAY"

# Block A: Stop geometry
USE_INTRADAY_ATR_FOR_STOPS = True
STOP_ATR_MULT_5M = 1.6
STOP_MIN_PCT = 0.0035

# Block B: Early defense
TIME_STOP_BARS = 6
TIME_STOP_MIN_MFE_R = 0.35
BE_ARM_R = 0.6
BE_BUFFER_BPS = 3

# Block C: Partial exits (disabled by default; evaluate after trail is stable)
TP1_ENABLED = False
TP1_R = 1.0
TP1_EXIT_PCT = 0.35
TP2_ENABLED = False
TP2_R = 1.8
TP2_EXIT_PCT = 0.25

# Block D: Trailing
TRAIL_ARM_R = 0.8
TRAIL_LOOKBACK_BARS = 10
TRAIL_MULT_LOW = 2.2    # when mfe_r < 1.0R
TRAIL_MULT_MID = 1.8    # when 1.0R <= mfe_r < 2.0R
TRAIL_MULT_HIGH = 1.4   # when mfe_r >= 2.0R
```

**Trade state fields to add to `BacktestTrade`:**

```python
entry_risk_per_share: float = 0.0
entry_atr_5m: float = 0.0
bars_held: int = 0
mfe_r: float = 0.0
mae_r: float = 0.0
be_armed: bool = False
trail_armed: bool = False
tp1_done: bool = False
tp2_done: bool = False
exit_reason_detail: str = ""
```

**Implementation steps (in this order):**

1. Compute `atr_5m_entry` at each signal timestamp using 5-minute candle data available up to that bar.
2. Compute `R0 = max(atr_5m_entry × STOP_ATR_MULT_5M, entry_price × STOP_MIN_PCT)`.
3. Set initial `current_stop` at `entry_price - R0` (LONG) or `entry_price + R0` (SHORT).
4. Rebuild `_calculate_chandelier` to use rolling 5-minute ATR instead of `atr_at_entry`.
5. Implement trade management loop in the order specified in section 2.6.
6. Wire `exit_reason_detail` throughout all exit paths.

**Deliverable:** Run V2 with starting config values. Compare vs corrected baseline. Measure: FORCE_EXIT share drop, first-touch NONE reduction, STOP_HARD / STOP_TRAIL / TIME_INVALIDATION counts, change in PF and DD.

---

### Phase 3 — Conditional Risk Controls

**Goal:** Apply the time-of-day, regime, alignment, and notional controls from section 3. These are simple toggles implemented as multipliers on existing sizing; they require no new optimization.

**Implementation steps:**

1. Add `BUCKET_SIZE_MULT` dict to config; multiply into position sizing at entry.
2. Add `REGIME_RISK_MULT` dict to config; multiply into risk amount at entry.
3. Add `COUNTER_TREND_SIZE_MULT` config; apply when nifty_dir != signal direction. Start with 0.0 (full block); test 0.4 separately.
4. Add `first_trade_outcome` session state; apply `day_risk_mult` to subsequent trades.
5. Add `MAX_NOTIONAL_MULT` check before any `EXECUTED` decision.

**Deliverable:** Re-run with all Phase 3 controls added at their conservative starting values. Compare vs Phase 2 output. These should improve or hold PnL while reducing tail risk.

---

### Phase 4 — Staged Parameter Optimization

**Goal:** Find the best parameter values for the V2 stop/trail system within the train split only. Validate on both holdout splits before promotion.

**Dataset splits** (period 2025-03-01 to 2025-12-31):

- Train / Selection: March – September
- Holdout-1: October – November
- Holdout-2: December

Promotion requires consistency across all three splits.

**Optimization order — one block at a time:**

| Stage | Tune                                                | All Other Params  |
| ----- | --------------------------------------------------- | ----------------- |
| A     | `STOP_ATR_MULT_5M`, `STOP_MIN_PCT`                  | Fixed at default  |
| B     | `TIME_STOP_BARS`, `TIME_STOP_MIN_MFE_R`, `BE_ARM_R` | Stage A frozen    |
| D     | `TRAIL_LOOKBACK_BARS`, `TRAIL_MULT_*`               | Stages A+B frozen |
| C     | `TP1_R`, `TP1_EXIT_PCT`, `TP2_R`, `TP2_EXIT_PCT`    | All above frozen  |

Block C (partial exits) is optional. Compare the best Block D result (trail-only) against the best Block C+D result (trail + partials). Choose whichever produces better holdout robustness, not just higher train PF.

**Parameter search space:**

Block A — Stop Geometry:

- `STOP_ATR_MULT_5M`: [1.2, 1.4, 1.6, 1.8, 2.0, 2.2]
- `STOP_MIN_PCT`: [0.0025, 0.0035, 0.0045, 0.0060]

Block B — Early Defense:

- `TIME_STOP_BARS`: [4, 6, 8, 10]
- `TIME_STOP_MIN_MFE_R`: [0.20, 0.35, 0.50]
- `BE_ARM_R`: [0.40, 0.60, 0.80]
- `BE_BUFFER_BPS`: [2, 3, 5, 8]

Block D — Adaptive Trailing:

- `TRAIL_LOOKBACK_BARS`: [6, 10, 14]
- `TRAIL_MULT_LOW`: [2.0, 2.2, 2.5]
- `TRAIL_MULT_MID`: [1.6, 1.8, 2.0]
- `TRAIL_MULT_HIGH`: [1.2, 1.4, 1.6]
- Constraint: `TRAIL_MULT_LOW > TRAIL_MULT_MID > TRAIL_MULT_HIGH` must hold

Block C — Partial Exits (optional, run last):

- `TP1_R`: [0.8, 1.0, 1.2]
- `TP1_EXIT_PCT`: [0.25, 0.35, 0.50]
- `TP2_R`: [1.5, 1.8, 2.2]
- `TP2_EXIT_PCT`: [0.15, 0.25, 0.35]
- Constraint: `TP1_EXIT_PCT + TP2_EXIT_PCT ≤ 0.70`; runner ≥ 30%

**Do not run all blocks simultaneously.** Staged single-block tuning is mandatory.

---

## 5. Validation Protocol

### 5.1 Acceptance Criteria (Must-Pass)

All criteria are evaluated against the **corrected Phase 1 baseline**, not the original 1.05 PF figure. Both holdout splits must independently pass all required criteria.

| Criterion                    | Required                                                        |
| ---------------------------- | --------------------------------------------------------------- |
| Profit Factor (train)        | ≥ 1.20                                                          |
| Profit Factor (each holdout) | > 1.0 independently                                             |
| Net PnL                      | ≥ corrected baseline                                            |
| Max Drawdown                 | ≤ corrected baseline (4.22% or revised after Phase 1)           |
| Median realized R            | > 0                                                             |
| FORCE_EXIT share             | Materially below 100%                                           |
| First-touch NONE rate        | Materially below 99.91%                                         |
| Total trades (full period)   | ≥ 700 (trade count floor; high PF on tiny sample is invalid)    |
| Monthly returns              | Majority of months profitable across all three splits           |
| Regime PF                    | PF > 1.0 in at least 3 of 4 regimes                             |
| Neighborhod robustness       | Params ± 1 step in each direction must not collapse PF by > 25% |

### 5.2 Failure Signatures

If the following patterns emerge, reject the candidate without promotion:

- PF up but DD up sharply → over-levered runner logic, trail too loose
- Win rate up but net PnL down → partials too early, right tail clipped
- PF improves only in train period, not in holdouts → overfit; reject
- Trade count drops > 45% from corrected baseline → risk model too restrictive
- PF improves in one holdout but collapses in the other → regime sensitivity; reject

### 5.3 Robustness Check

For any candidate parameter set:

1. Perturb each parameter by ±1 grid step individually.
2. Verify that all perturbations produce PF > 1.0 in holdouts.
3. If any single perturbation collapses performance, the local optimum is fragile and the candidate is rejected.

---

## 6. Expected Outcome

If the implementation plan is followed in strict order (correctness first, then risk activation, then conditional controls, then optimization), the expected improvements are:

| Metric             | Current Baseline | Target After All Phases    |
| ------------------ | ---------------- | -------------------------- |
| Profit Factor      | 1.05             | ≥ 1.20                     |
| Net PnL            | +21,397.75       | ≥ corrected baseline       |
| Max Drawdown       | 4.22%            | ≤ corrected baseline       |
| Median realized R  | 0.0              | > 0                        |
| FORCE_EXIT share   | 100%             | Materially reduced         |
| First-touch NONE   | 99.91%           | Materially reduced         |
| Mean stop distance | 5.09% (daily)    | 0.8–1.3% (intraday-native) |

The core insight is not about finding better entry signals — it is about making risk **stateful-through-time** instead of **static-at-entry**. The current system enters trades with reasonable signals but then abandons all risk management, holding trades passively until day-end. The V2 system will cut weak trades early (time invalidation), protect confirmed moves (breakeven arm), and ride strong trends with an intraday-calibrated trailing stop that actually fires.

The expected left-tail compression (fewer large losing trades) and improved right-tail capture (earlier trail protection of winning trades) is the mechanism for PF improvement, not a change in win rate.

---

## 7. Immediate Next Build Tasks

In execution order:

1. Implement Phase 0 instrumentation fields in `backtest_v6/sector_engine_v6.py` and analysis support in `backtest_v6/analysis/analyze_backtest.py`. No behavior changes.
2. Re-run baseline with instrumentation. Verify new fields populate correctly in output JSONs.
3. Implement Phase 1 correctness fixes: breadth feed, stop-fill slippage model, same-bar event priority documentation.
4. Re-run corrected baseline. This is the new reference point. Compare PF and PnL vs original 1.05.
5. Implement Phase 2: 5m ATR stops, chandelier rewrite, time invalidation, breakeven arm, trail-before-TP1.
6. Run Phase 2 with default config values. Do not optimize yet. Measure FORCE_EXIT drop and first-touch distribution.
7. Implement Phase 3: time-bucket sizing, regime multipliers, alignment gate, first-trade state, notional cap.
8. Run Phase 3. Compare vs Phase 2. These should improve or hold PnL with lower tail risk.
9. Start Phase 4 staged optimization: Block A only on train split. Validate on holdouts before moving to Block B.
10. Promote to Block B, D, and optionally C following the same validate-then-advance discipline.
