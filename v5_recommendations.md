# V5 Codebase Recommendations (Analysis Only)

> Scope: `main_v5.py`, `analysis_v5/*`, `core_v5/*`, `execution_v5/*`, `system_v5/*`
> Note: No implementation changes performed.

## 1) `analysis_v5/indicators_v5.py`

- Consider adding unit tests for edge cases (very short series, zero/negative prices, NaNs) to lock behavior.
- In `calculate_hma`, guard against `sqrt_period == 0` when `period` is small; current behavior returns 0 but can be made explicit for clarity.
- In `calculate_rsi`, use a single path for `down == 0` to avoid RSI array partially initialized to 0 for early indices (doesn’t affect last value, but clarity).
- Optionally vectorize loops (ATR/RSI) for speed if running on large arrays.

## 2) `analysis_v5/strategy_v5.py`

- `MarketRegimeDetector.calculate_percentile` uses last 20 values; if VIX history is larger, consider percentile vs full history for stability (optional).
- `StockGrader.calculate_grade` returns grade C with reasons when RVOL below threshold; for transparency, consider adding explicit “HMA conflict” reason when `direction == "NONE"`.
- `ExecutionFilters.check_gate` could log or return a structured reason object to allow easier UI/tooling.
- `SectorScorer.select_top_n` filters out NEUTRAL biases; if all are neutral, nothing is selected—consider a fallback to top N neutral sectors for monitoring only.

## 3) `core_v5/config_v5.py`

- Add comments clarifying that `VIX_PCTL_EXTREME_THRESHOLD` influences regime + sizing only (no halt).
- Consider centralizing all thresholds in a dataclass for easier runtime overrides (env or CLI) and testing.
- If you plan to run live later, separate paper/live settings into a dedicated section or file.

## 4) `core_v5/data_v5.py`

- In `connect`, consider validating `access_token` expiry with a lightweight call or handle 403 explicitly.
- In `start_ticker`, consider reconnect/backoff logic for resilient WebSocket reconnects.
- Add a rate‑limit wrapper for REST requests (`get_quote`, `get_historical`) to honor `RATE_LIMIT_*` config.
- Consider persisting `live_ticks` size or eviction strategy to reduce memory growth if symbol list increases.

## 5) `execution_v5/lifecycle_v5.py`

- `Trade.stage` comment lists `PENDING`, but code uses `ACTIVE`/`PARTIAL`/`CLOSED`; update docstring for clarity.
- `update_trades` uses `market_data` keys with `NSE:` prefix; ensure consistency across callers.
- `Trade` doesn’t record realized PnL per partial exit; consider tracking for better reporting.
- Chandelier lookback uses REST historical calls; consider caching to reduce API usage during heavy trading.

## 6) `execution_v5/orders_v5.py`

- `close_position` uses `get_quote([symbol])` (raw symbol), which relies on prefixing inside data manager—works, but add a comment for clarity.
- `paper_positions` PnL accumulates across closes; consider resetting per‑day if daily PnL is required.
- Consider storing and returning order execution metadata (timestamp, avg price) for audit/tracking.

## 7) `execution_v5/risk_v5.py`

- `check_kill_switches` accepts `current_vix_pctl` but doesn’t use it; either remove the arg or add TODO to avoid confusion.
- `calculate_position_size` uses `BASE_RISK_PER_TRADE_PCT` but comment says “0.35%”; align comment or value.
- Consider incorporating correlation checks if `CORRELATION_THRESHOLD` is intended to be enforced.

## 8) `system_v5/safety_v5.py`

- `red_stock_pct` is passed as `0.0` in `main_v5.py` today; consider wiring actual breadth for full functionality.
- Consider adding a decay/reset policy for `is_halted` so a single spike doesn’t lock the system without manual restart.

## 9) `system_v5/state_v5.py`

- When state file is missing or invalid, log the exception details once for easier debugging.
- Consider versioning the state schema (e.g., `state_version`) to support future migrations safely.

## 10) `system_v5/ui_v5.py`

- If there are no positions, the portfolio table is empty; consider a small placeholder row to avoid a blank panel.
- `gate_reason[:4]` truncates reasons; consider a short mapping for clarity (e.g., `SPRD`, `CIRC`, `NODE`).

## 11) `main_v5.py`

- Safety monitor is used for halts; now that VIX‑based halt was removed, ensure the halt reason list is still aligned with the policy (flash crash, VIX spike, breadth). This is okay and separate from percentile regime.
- `current_equity = max(self.risk.state.equity, DEFAULT_PAPER_EQUITY)` masks drawdown effects; ensure this is intentional for paper mode.
- `state_mgr.save_state` every 60 seconds using `int(time.time()) % 60 == 0` may fire multiple times per second; consider a timestamp guard to avoid repeated writes.
- Consider adding a health summary log at startup: tokens loaded, universe size, and last state date.
