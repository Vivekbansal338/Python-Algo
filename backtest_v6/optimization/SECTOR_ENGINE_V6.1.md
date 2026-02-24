# sector_engine_v6.1.py — Changes from V6

**File:** `backtest_v6/sector_engine_v6.1.py`  
**Base:** `backtest_v6/sector_engine_v6.py`  
**Date:** 2026-02-24

---

## Points Covered

### 2.2 Entry Risk Model — Intraday-Native Stop

- Stop distance now uses **5-minute ATR(14)** instead of daily ATR(10).
- Formula: `R0 = max(atr_5m × 1.6, entry_price × 0.35%)`
- New method `_compute_5m_atr(symbol, intra_pos, period=14)` computes ATR from 5-minute candles up to the entry bar.
- `R0` is stored on each trade as `entry_risk_per_share` (the fixed risk denominator for the trade's lifetime).
- `entry_atr_5m` stored on each trade for analysis.
- Target-1 is automatically recalibrated since `sizing.risk_per_share = R0` feeds into `TARGET_1_MULT`.

### 2.3 Chandelier Trail Rewrite — Use Rolling 5-Minute ATR

- `_calculate_chandelier` completely rewritten.
- Uses **rolling 5-minute ATR** at the current bar instead of the daily ATR at entry.
- Swing anchor computed from the last `TRAIL_LOOKBACK_BARS` (10) bars — does not use the trade's all-time high/low.
- **Adaptive trail multiplier** based on MFE in R-units:
  - `mfe_r < 1.0` → 2.2× ATR (wide)
  - `1.0 ≤ mfe_r < 2.0` → 1.8× ATR (medium)
  - `mfe_r ≥ 2.0` → 1.4× ATR (tight)
- Trail stop can only tighten — never loosens.

### 2.5 Early Breakeven Arm — Protect Confirmed Winners

- When `mfe_r >= 0.6` (BE_ARM_R), stop is moved to `entry_price + 3bps` (LONG) or `entry_price - 3bps` (SHORT).
- `be_armed` flag set on the trade — breakeven arm fires once.
- Stop only moves if it tightens (never loosens the stop).
- If the BE-level stop is subsequently hit, exit reason is `STOP_TRAIL`.

### 2.6 Adaptive Trailing — Armed Before TP1 Hit

- Trail is armed when `mfe_r >= 0.8` (TRAIL_ARM_R), **independent of TP1 hit or stage transition**.
- `trail_armed` flag set on the trade.
- Once armed, chandelier trail is computed every bar and stop is tightened if the new trail improves it.
- Trail operates in **both ACTIVE and PARTIAL stages** — no separate PARTIAL-only chandelier block.
- Full per-bar management loop order:
  1. Update highest/lowest, MFE_R, MAE_R
  2. Check stop at current level → `STOP_HARD` or `STOP_TRAIL`
  3. Check breakeven arm → tighten stop to entry + buffer
  4. Check trail arm (MFE ≥ 0.8R) → arm trail
  5. If trail armed, compute chandelier, tighten stop
  6. TP1 partial exit (ACTIVE stage only, existing target logic)

### 2.8 Exit Reason Taxonomy

| Reason         | When Applied                                          |
| -------------- | ----------------------------------------------------- |
| `STOP_HARD`    | Price crosses initial hard stop (before BE/trail arm) |
| `STOP_TRAIL`   | Stop hit after BE arm or trail arm has moved it       |
| `TARGET1_FULL` | Full position exits at TP1 (no runner remaining)      |
| `FORCE_EXIT`   | Day-end forced close at 15:05                         |
| `SAFETY_HALT`  | SafetyMonitor triggered halt                          |

---

## V6.1 Config Constants (defined in module, not in v6/config.py)

```python
STOP_ATR_MULT_5M    = 1.6     # 5m ATR multiplier for initial stop
STOP_MIN_PCT        = 0.0035  # Floor: 0.35% of entry price
BE_ARM_R            = 0.6     # Arm breakeven at 0.6R MFE
BE_BUFFER_BPS       = 3       # Buffer above entry in bps
TRAIL_ARM_R         = 0.8     # Arm trailing at 0.8R MFE
TRAIL_LOOKBACK_BARS = 10      # Swing anchor and ATR lookback
TRAIL_MULT_LOW      = 2.2     # Trail mult when mfe_r < 1.0
TRAIL_MULT_MID      = 1.8     # Trail mult when 1.0 <= mfe_r < 2.0
TRAIL_MULT_HIGH     = 1.4     # Trail mult when mfe_r >= 2.0
```

---

## BacktestTrade New Fields

| Field                  | Type  | Description                          |
| ---------------------- | ----- | ------------------------------------ |
| `entry_risk_per_share` | float | R0 — intraday risk unit per share    |
| `entry_atr_5m`         | float | 5-minute ATR(14) at entry            |
| `mfe_r`                | float | Max favorable excursion in R-units   |
| `mae_r`                | float | Max adverse excursion in R-units     |
| `be_armed`             | bool  | True once breakeven stop is armed    |
| `trail_armed`          | bool  | True once adaptive trailing is armed |

---

## What Is NOT Changed from V6

- Signal generation, grading, sector scoring — identical
- Position sizing via `RiskManager.calculate_position_size` — identical
- Microstructure gate — identical
- Safety monitor — identical (breadth still wired as 0.0)
- TP1 partial exit logic — kept, but stop never loosens on transition
- All data loading, universe parsing, history export — identical
- `_run_day`, `run_backtest` flow — identical
- No TIME_INVALIDATION, no TP1_PARTIAL/TP2_PARTIAL, no conditional risk controls
