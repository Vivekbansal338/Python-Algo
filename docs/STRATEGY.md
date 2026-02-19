# V6 Trading Strategy (Code-Observed)

> Source of truth: `v6/config.py`, `v6/brain.py`, `v6/execution.py`, `v6/main.py`.
> Last verified against code: February 19, 2026.

---

## 1. Session Structure and Playbooks

Playbook dispatch is driven by `TradingBotV6.get_playbook()`.

| Time (IST) | Playbook | New Entries |
| --- | --- | --- |
| Before 09:15 | `PRE_MARKET` | No |
| 09:15-09:19:59 | `WAIT` | No |
| 09:20-09:33:59 | `OR_FORMATION` | No |
| 09:34-10:04:59 | `ORB` | Yes |
| 10:05-10:09:59 | `GAP` | No |
| 10:10-14:04:59 | `MAIN` | Yes |
| 14:05-15:04:59 | `EXIT_ONLY` | No |
| 15:05 onward | `FORCE_EXIT` | No |

Notes:

- In current code, `FORCE_EXIT` persists after 15:05 unless process stops.
- `config.ORB_START_TIME` (09:35) is defined but not used by `get_playbook()`; ORB currently starts at 09:34 boundary (right after `OR_END_TIME`).
- `ORB_END_TIME`, `MAIN_START_TIME`, `MAIN_END_TIME`, and `MARKET_CLOSE_TIME` are config constants but are not directly used by playbook routing.

---

## 2. Regime and Volatility Adaptation

`MarketRegimeDetector` uses VIX 20-day percentile.

Regime labels:

- `<= 20`: `TRENDING`
- `> 20 and < 75`: `NEUTRAL`
- `>= 75 and < 90`: `MEAN_REVERT`
- `>= 90`: `EXTREME`

Sizing multiplier mapping (`get_vix_multiplier`):

- `<= 20`: `VIX_MULT_LOW` (1.20)
- `> 20 and <= 50`: `VIX_MULT_NORMAL` (1.00)
- `> 50 and < 75`: `VIX_MULT_ELEVATED` (0.80)
- `>= 75`: `VIX_MULT_HIGH` (0.75)

Known behavior gap:

- Extreme (`>= 90`) currently uses same 0.75 multiplier as high-vol (`>= 75`) (`issues/005_vix_multiplier_flat.md`).

---

## 3. Sector Selection Logic

`SectorScorer.score_all()` computes composite sector score from:

- Structural RS (20d)
- Short-term RS (3d)
- Intraday RS (daily)
- Breadth (net VWAP breadth)
- Nifty daily contribution

Selection behavior:

- Rank by absolute score magnitude.
- Dynamic N: top 3 or top 5 based on spread between rank #1 and #5.
- Only directional sectors (`LONG` / `SHORT`) are marked selected.

---

## 4. Stock Grading and Entry Conditions

Pipeline in `_scan_tradeable_stocks()`:

1. Liquidity gate via ADV (`MIN_ADV_CRORES`).
2. ATR + microstructure gate (`ExecutionFilters.check_gate`).
3. HMA alignment + StochRSI + RVOL.
4. Grade via `StockGrader.calculate_grade()`.
5. Sector bias alignment post-check in `main.py`.

Execution gate in current code:

- Actual entries require `grade in ["A+", "A"]`, `gate_passed`, and playbook in `ORB` or `MAIN`.

---

## 5. Risk and Sizing

`RiskManager.calculate_position_size()`:

- Base risk from equity (`BASE_RISK_PER_TRADE_PCT = 0.5%`).
- Multiplier stack: Grade x VIX x Day state.
- Lunch multiplier (`12:00-13:15`): 0.70.
- Drawdown warning multiplier (<= -1%): 0.50 (requires non-zero `daily_start_equity`).

Portfolio checks in `can_open_new_trade()`:

- Max concurrent positions.
- Max per sector.
- Reject duplicate symbol already in active set.

Gaps:

- `CORRELATION_THRESHOLD` not enforced (`issues/003_correlation_not_enforced.md`).
- `MAX_POSITIONS_PER_STOCK` constant is defined but not consumed as an explicit rule (`issues/019_max_positions_per_stock_constant_unused.md`).

---

## 6. Kill Switch and Safety

Two separate mechanisms exist:

1. Risk kill-switch (`RiskManager.check_kill_switches`) for drawdown halt.
2. Safety monitor (`SafetyMonitor.update`) for flash crash / VIX spike / breadth collapse.

Current runtime behavior:

- `check_kill_switches()` is not called from the main loop (`issues/015_drawdown_killswitch_not_invoked.md`).
- `daily_start_equity` baseline is not initialized in fresh sessions, so drawdown guards are effectively bypassed (`issues/016_daily_start_equity_never_initialized.md`).
- `SafetyMonitor.update(...)` is called with breadth input hardcoded `0.0`, disabling breadth-collapse trigger (`issues/006_safety_breadth_unwired.md`).

---

## 7. Trade Lifecycle

`LifecycleManager`:

- Entry creates trade record, places paper entry + SL order.
- Stage `ACTIVE`: stop or target-1 checks.
- Target-1 hit: partial exit (`TARGET_1_EXIT_PCT`), move stop to breakeven, stage `PARTIAL`.
- Stage `PARTIAL`: chandelier trailing stop updates.
- `FORCE_EXIT` path closes all open trades.

---

## 8. State Persistence (Exact)

`StateManager` save/restore contains:

- trades
- paper orders
- paper positions
- `daily_start_equity`
- `daily_high_equity`

Precision note:

- It restores `daily_start_equity`; it does not restore a validated "full daily equity ledger" with realized PnL roll-up.
- `daily_high_equity` is stored but not consumed by `RiskManager` kill-switch logic (`issues/004_daily_highwater_unused.md`).

---

## 9. Entry Checklist (Current Runtime)

A new trade can execute only if all are true:

1. Playbook is `ORB` or `MAIN`.
2. Safety monitor is not halted.
3. Symbol is in candidate set from selected sectors (or active set context).
4. ADV threshold passes.
5. Microstructure gate passes.
6. Grade is `A+` or `A`.
7. Signal direction aligns with sector bias.
8. `RiskManager.can_open_new_trade()` returns true.
9. Position sizing yields at least 1 share.
10. Symbol is not under rejection cooldown.

---

## 10. Operational Caveats

- Strategy/scanner updates are timer-driven every 5 seconds, not strict tick-by-tick.
- State save trigger is modulo-based and can run multiple times in one second.
- Equity handling currently does not propagate realized PnL cleanly into risk baseline (`issues/010_equity_tracking.md`).
