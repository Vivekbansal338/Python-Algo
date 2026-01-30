# Issue: Remove VIX-Based Trading Halt

## Status

**Resolved** ✅ (2026-01-26)

## 1. Description

The current system logic intends to halt trading completely when the VIX percentile exceeds the 90th percentile (`VIX_PCTL_HALT_THRESHOLD`). The requirement is to **disable this halt feature** while preserving the "Extreme" regime classification for informational purposes and position sizing.

## 2. Requirements

### A. Remove Halt Logic

- The system must **never** halt trading based solely on the absolute VIX percentile level.
- The "Kill Switch" in `RiskManager` corresponding to VIX Percentile must be removed.

### B. Preserve "Extreme" Regime

- The system should still classify the market as `EXTREME` when VIX > 90th percentile.
- **UI:** Display `EXTREME 🛑` (or similar warning) in the dashboard.
- **Sizing:** Apply `VIX_MULT_HIGH` (0.75x) sizing during this regime instead of 0.00x.

## 3. Implementation Plan

### Phase 1: Configuration Update (`core_v5/config_v5.py`)

- Rename `VIX_PCTL_HALT_THRESHOLD` -> `VIX_PCTL_EXTREME_THRESHOLD`.
- Delete `VIX_MULT_HALT` constant.

### Phase 2: Risk Manager Update (`execution_v5/risk_v5.py`)

- In `check_kill_switches()`:
  - Remove the code block checking `current_vix_pctl`.
  - Retain only the Daily Drawdown check.

### Phase 3: Strategy Update (`analysis_v5/strategy_v5.py`)

- In `get_regime()`: Update reference to `VIX_PCTL_EXTREME_THRESHOLD`.
- In `get_vix_multiplier()`: Update reference to `VIX_PCTL_EXTREME_THRESHOLD`.

### Phase 4: Backtest Compatibility (`backtest_v5/sector_engine_v5.py`)

- Update any references from `VIX_PCTL_HALT_THRESHOLD` to `VIX_PCTL_EXTREME_THRESHOLD` to ensure the backtest engine runs without errors.

## 3.1 Implementation Notes (Completed)

- Updated constant names and removed halt sizing in `core_v5/config_v5.py`.
- Removed VIX-based kill switch logic from `execution_v5/risk_v5.py`.
- Updated regime + sizing threshold usage in `analysis_v5/strategy_v5.py`.
- Updated backtest VIX threshold usage and regime detection in `backtest_v5/sector_engine_v5.py`.

## 4. Expected Outcome

The bot will continue to trade through high-volatility environments (top 10% VIX) with reduced position sizing (0.75x) rather than stopping completely. The UI will continue to alert the user to the extreme conditions.
