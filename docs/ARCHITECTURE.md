# V6 System Architecture & Data Flow (Code-Observed)

> Source of truth: `v6/config.py`, `v6/data_engine.py`, `v6/brain.py`, `v6/execution.py`, `v6/main.py`.
> Last verified against code: February 19, 2026.

---

## 0. Verification Anchors

This document is anchored to these runtime lines:

- `v6/main.py` (`get_playbook`)
- `v6/main.py` (`return "FORCE_EXIT"`)
- `v6/main.py` (5-second refresh gate)
- `v6/main.py` (`self.safety.update(..., 0.0)`)
- `v6/main.py` (state save trigger)
- `v6/brain.py` (`daily_start_equity` initialized to `0.0`)
- `v6/brain.py` (`check_kill_switches`)
- `v6/execution.py` (state save field for `daily_start_equity`)
- `v6/execution.py` (state restore into `daily_start_equity`)
- `v6/config.py` (`ENTRY_START_TIME`)
- `v6/config.py` (`MARKET_CLOSE_TIME`)
- `v6/config.py` (`MAX_POSITIONS_PER_STOCK`)

---

## 1. Architecture Overview

V6 consolidates the prior multi-module stack into 5 runtime files:

| File                | Responsibility                                                                                        |
| ------------------- | ----------------------------------------------------------------------------------------------------- |
| `v6/config.py`      | Constants, timing windows, thresholds, paths                                                          |
| `v6/data_engine.py` | Zerodha connectivity, instrument cache, historical/quote calls, websocket ticker, indicator functions |
| `v6/brain.py`       | Regime detection, sector scoring, stock grading, execution filters, risk logic, safety logic          |
| `v6/execution.py`   | Paper order engine, lifecycle manager, state persistence                                              |
| `v6/main.py`        | Orchestrator loop + Rich TUI                                                                          |

Dependency direction is one-way:

- `config` is imported by all runtime modules.
- `data_engine` depends on `config` only.
- `brain` depends on `config` only.
- `execution` depends on `config` + `data_engine`.
- `main` depends on `config` + `data_engine` + `brain` + `execution`.

---

## 2. Runtime Data Sources

### A. Historical API (`kite.historical_data`)

Used for:

- VIX lookback history on startup.
- Nifty/sector lookbacks for RS baselines.
- Stock daily + 5-minute history for indicator calculations.
- Periodic intraday refresh (`INTRADAY_REFRESH_INTERVAL_SEC = 300`).
- Chandelier anchor refresh inside lifecycle manager.

### B. Quote API (`kite.quote`)

Used for:

- Initial anchor fetch (previous close) at startup.
- Initial sector rank pass.
- Paper exit price fallback in `OrderManager.close_position()`.

### C. WebSocket (`KiteTicker`, `full` mode)

- Latest ticks are written into `DataManager.live_ticks` by websocket callbacks.
- Main loop consumes `live_ticks` as the primary real-time source.
- `is_ws_connected` is maintained in `DataManager`, but main loop currently does not enforce fallback behavior when false.

### D. Instruments API (`kite.instruments("NSE")`)

- Cached at `data/cache/instruments.pkl`.
- TTL from config: 12 hours (`CACHE_INSTRUMENTS_SEC`).

---

## 3. Cadence and Scheduling (Observed Behavior)

Important distinction:

- Tick ingestion can be high-frequency (websocket callback thread).
- Strategy recalculation cadence is gated by main loop timers.

| Activity                                      | Actual Cadence in Code                                                    | Where                   |
| --------------------------------------------- | ------------------------------------------------------------------------- | ----------------------- |
| Main loop iteration                           | Every ~0.5s (`time.sleep(0.5)`)                                           | `v6/main.py`            |
| Metrics recalculation + scanner + safety call | Every 5s (`UI_REFRESH_INTERVAL`)                                          | `v6/main.py:1045` block |
| Intraday 5m historical refresh                | Every 300s                                                                | `v6/main.py`            |
| State persistence                             | `if int(time.time()) % 60 == 0` (can write multiple times in same second) | `v6/main.py:1080`       |

So UI/strategy is not strictly tick-by-tick. It is snapshot-driven at the configured refresh gate.

---

## 4. Playbook State Machine (Current)

`TradingBotV6.get_playbook()` returns:

- `< 09:15` -> `PRE_MARKET`
- `09:15-09:24:59` -> `WAIT`
- `09:25-14:04:59` -> `MAIN`
- `14:05-15:04:59` -> `EXIT_ONLY`
- `15:05-15:29:59` -> `FORCE_EXIT`
- `>= 15:30` -> `AFTER_CLOSE`

The ORB/OR_FORMATION/GAP phases were removed in issue #001 resolution. The system now runs a single unified momentum strategy.

---

## 5. State Persistence Scope (Exact)

`StateManager` persists/restores:

- Active trades
- Paper orders
- Paper positions
- `daily_start_equity`
- `daily_high_equity` (stored)

Important precision:

- It does not restore a separately tracked realized-equity ledger.
- On fresh session path, `daily_start_equity` is not initialized by `initialize()`.

---

## 6. Key Supporting Files

| File                         | Purpose                             |
| ---------------------------- | ----------------------------------- |
| `config/universe.json`       | Sector indices + stock universe     |
| `data/state_v6.json`         | Persistent runtime snapshot         |
| `data/cache/instruments.pkl` | Cached instrument master            |
| `.env`                       | `KITE_API_KEY`, `KITE_ACCESS_TOKEN` |

---

## 7. Observed Gaps Linked to Issues

- Drawdown kill-switch function exists but is not called in runtime loop (`issues/015_drawdown_killswitch_not_invoked.md`).
- `daily_start_equity` baseline is never initialized on fresh start (`issues/016_daily_start_equity_never_initialized.md`).
- Safety monitor breadth input is hardcoded to `0.0` (`issues/006_safety_breadth_unwired.md`).
- Safety monitor window comment assumes 1s updates, but runtime calls every 5s (`issues/017_safety_window_cadence_mismatch.md`).
- `MAX_POSITIONS_PER_STOCK` constant is defined but not explicitly enforced via that constant (`issues/019_max_positions_per_stock_constant_unused.md`).
