# V6.8 Backtest Output Structure

## Overview

`sector_engine_v6.8.py` writes one JSON history file per run in:

- `backtest_v6/history_v6.8/backtest_history_DD-MM-YYYY_HH-MM_am|pm.json`

This schema is optimized for:

- Executed-path analysis (`signal_records`, `position_records`, `trade_records`)
- Opportunity-level counts via `summary` counters
- Full brokerage/statutory charge accounting at run level and trade level

## Root Keys

```json
{
  "run": {},
  "inputs": {},
  "config_snapshot": {},
  "summary": {},
  "daily_results": [],
  "all_trade_records": [],
  "signal_records": [],
  "position_records": [],
  "trade_records": []
}
```

## Important V6.8 Change

These arrays are removed from V6.8 output:

- `all_signal_records`
- `all_position_records`

Equivalent universe-level counts are still available in `summary`:

- `all_a_grade_signals`
- `all_position_candidates`
- `all_trade_candidates`
- `decision_counts`
- `risk_reason_counts`
- `max_positions_slot_available_count`
- `blocked_by_max_positions_count`

## `summary` (Performance + Execution + Brokerage)

Core fields:

- `initial_equity`
- `final_equity`
- `total_return`
- `total_return_pct`
- `gross_return_before_charges`
- `trading_days`
- `closed_trades`
- `a_grade_signals`
- `position_candidates`
- `executed_positions`
- `all_a_grade_signals`
- `all_position_candidates`
- `all_trade_candidates`
- `decision_counts`
- `risk_reason_counts`
- `capital_blocked_count`
- `peak_deployed_notional`
- `peak_utilization_pct`
- `alignment_blocked_count`
- `gate_slope_blocked`
- `gate_freshness_blocked`
- `gate_price_align_blocked`
- `gate_separation_blocked`
- `gate_divergence_blocked`

New brokerage fields in V6.8:

- `exchange`
- `transaction_charge_pct`
- `total_turnover`
- `total_charges`
- `brokerage_pct_of_turnover`
- `brokerage_breakdown`:
  - `brokerage`
  - `stt`
  - `transaction_charge`
  - `sebi_charge`
  - `stamp_charge`
  - `gst`

## `trade_records` (Closed Trades With Net/Gross Decomposition)

Each trade record now includes:

- Existing:
  - `trade_id`, `symbol`, `sector`, `direction`
  - `entry_time`, `entry_price`, `initial_qty`
  - `exit_time`, `exit_price`, `exit_reason`
  - `realized_pnl` (net, after charges)
  - `stage`
  - risk/management fields (`entry_risk_per_share`, `entry_atr_5m`, `mfe_r`, `mae_r`, `be_armed`, `trail_armed`)
  - alignment fields (`index_direction`, `sector_bias_at_entry`, `signal_direction`)
- New in V6.8:
  - `gross_pnl` (before charges)
  - `total_turnover`
  - `total_charges`
  - `brokerage_breakdown`:
    - `brokerage`
    - `stt`
    - `transaction_charge`
    - `sebi_charge`
    - `stamp_charge`
    - `gst`

Relationship:

- `realized_pnl = gross_pnl - total_charges`

## `all_trade_records` (Opportunity-Level Trail)

Contains one record per A+ opportunity:

- Executed opportunities start as active trade snapshots and are updated on close.
- Non-executed opportunities are recorded with:
  - `stage: "NOT_EXECUTED"`
  - `exit_reason` as the entry decision (for example, `RISK_REJECTED:*`, `INSUFFICIENT_CAPITAL`, etc.)

## `signal_records` / `position_records`

Executed-path only (subset of opportunities that became trades):

- `signal_records`: executed signal context (score, regime, gate info, market context)
- `position_records`: executed position sizing/risk context

## `inputs`

V6.8 includes brokerage context in addition to run parameters:

- `synthetic_spread_bps`
- `synthetic_circuit_pct`
- `checkpoint_every_days`
- `exchange`
- `transaction_charge_pct`
- `max_concurrent_positions`
- `max_positions_per_sector`
- `max_positions_per_stock`

## Brokerage Model Applied in V6.8

Per executed order leg (entry, partial exit, final exit):

- Brokerage: `min(0.03% of turnover, Rs.20)`
- STT/CTT: `0.025%` on sell side
- Transaction charges:
  - NSE: `0.00297%`
  - BSE: `0.00375%`
- SEBI: `Rs.10 / crore`
- Stamp: `0.003%` on buy side
- GST: `18% * (brokerage + sebi + transaction)`

All charges are deducted live from realized PnL during backtest execution.
