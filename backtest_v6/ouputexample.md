## Backtest Console Output Example

```text
(.venv) PS ...\TradingBot> python backtest_v6\sector_engine_v6.py --start 2026-02-01 --end 2026-02-23
Universe loaded | indices: 18 | stocks: 190
Loaded data from ...\backtest_v6\data | daily files: 208, 5m files: 208
Run tracking started | run_id=BT_20260223_013512 | range=2026-02-01 -> 2026-02-23

======================================================================================================================================================
DATE         |   START EQUITY |     END EQUITY |      DAY PNL | TRADES | TRADE PNLS
======================================================================================================================================================
...
================================================================================
V6 BACKTEST SUMMARY
--------------------------------------------------------------------------------
...
================================================================================

History output saved: ...\backtest_v6\history\backtest_history_23-02-2026_01-35_pm.json
```

## Auto-Generated History File

Every run now automatically writes one timestamped JSON under:

- `backtest_v6/history/`

Filename pattern:

- `backtest_history_<dd-mm-yyyy>_<hh-mm_am/pm>.json`
- Example: `backtest_history_23-02-2026_01-35_pm.json`

Core sections in the JSON:

- `run`: run id, status, start/end timestamps, range, data root
- `inputs`: important backtest input controls
- `config_snapshot`: full V6 config snapshot for parameter audit
- `summary`: equity/trade stats + decision counts
- `daily_results`: day-level pnl rows
- `signal_records`: config-constrained executed signal path only
- `position_records`: config-constrained executed positions only
- `trade_records`: config-constrained executed closed trades
- `all_signal_records`: all generated `A`/`A+` signals
- `all_position_records`: all potential positions for `A`/`A+` signals
- `all_trade_records`: all potential trade plans for `A`/`A+` signals

Important keys for MAX_CONCURRENT_POSITIONS analysis:

- `open_positions_before`
- `max_positions_limit`
- `max_positions_slot_available`
- `blocked_by_max_positions`
- `executed_within_max_positions`
