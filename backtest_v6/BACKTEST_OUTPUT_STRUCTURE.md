# V6 Backtest Output File Structure

## Overview

The backtest engine generates a comprehensive JSON file (stored in `backtest_v6/history/`) that captures the complete execution history, including all opportunity signals, executed trades, and detailed analytics. Each file is timestamped and contains all information needed to analyze strategy performance.

**File Location:** `backtest_v6/history/backtest_history_DD-MM-YYYY_HH-MM_am|pm.json`

---

## Root-Level Structure

The output JSON is organized into 7 main sections:

```
{
  "run": {...},                      // Run metadata and execution details
  "inputs": {...},                   // Configuration parameters used
  "config_snapshot": {...},          // Full strategy configuration snapshot
  "summary": {...},                  // Backtest performance summary
  "daily_results": [...],            // Per-day results array
  "all_signal_records": [...],       // All A/A+ opportunity signals (complete universe)
  "all_position_records": [...],     // Position analysis for all signals
  "signal_records": [...],           // Only executed signals (config-constrained)
  "position_records": [...],         // Position data for executed signals only
  "trade_records": [...]             // Executed and closed trade details
}
```

---

## Section 1: `run` - Run Metadata

Contains execution metadata about the backtest run.

### Structure

```json
{
  "run": {
    "run_id": "BT_20260223_132942",
    "status": "COMPLETED|RUNNING|INIT_FAILED|VALIDATION_FAILED|NO_TRADING_DAYS|ERROR",
    "error": "",
    "is_checkpoint": false,
    "started_at": "2026-02-23T13:29:42.772471",
    "finished_at": "2026-02-23T13:30:13.699181",
    "duration_seconds": 30.92671,
    "start_date": "2026-01-06",
    "end_date": "2026-01-06",
    "trading_days": ["2026-01-06"],
    "history_file_date_label": "23-02-2026",
    "history_file_time_label": "01:30 pm",
    "data_root": "C:\\...\\backtest_v6\\data",
    "history_file": "C:\\...\\backtest_history_23-02-2026_01-30_pm.json"
  }
}
```

### Field Descriptions

| Field                     | Type              | Description                                                                   |
| ------------------------- | ----------------- | ----------------------------------------------------------------------------- |
| `run_id`                  | string            | Unique run identifier formatted as `BT_YYYYMMDDhhmmss`                        |
| `status`                  | string            | COMPLETED, RUNNING, INIT_FAILED, VALIDATION_FAILED, NO_TRADING_DAYS, or ERROR |
| `error`                   | string            | Error message if status is ERROR; otherwise empty                             |
| `is_checkpoint`           | boolean           | True if this is an incremental save during execution; false for final save    |
| `started_at`              | ISO 8601 datetime | When the backtest started (or None during checkpoint)                         |
| `finished_at`             | ISO 8601 datetime | When the backtest finished (or current time during checkpoint)                |
| `duration_seconds`        | float             | Total execution time in seconds (or None if still running)                    |
| `start_date`              | ISO 8601 date     | Beginning date of backtest period                                             |
| `end_date`                | ISO 8601 date     | Ending date of backtest period                                                |
| `trading_days`            | array of dates    | List of trading days processed (ISO 8601 format)                              |
| `history_file_date_label` | string            | Run date label in DD-MM-YYYY format                                           |
| `history_file_time_label` | string            | Run time label in HH:MM am/pm format                                          |
| `data_root`               | string            | Absolute path to parquet data directory                                       |
| `history_file`            | string            | Absolute path to this output file                                             |

---

## Section 2: `inputs` - Configuration Parameters

Core execution parameters that were applied during the backtest.

### Structure

```json
{
  "inputs": {
    "synthetic_spread_bps": 6.0,
    "synthetic_circuit_pct": 0.1,
    "max_concurrent_positions": 6,
    "max_positions_per_sector": 2,
    "max_positions_per_stock": 1
  }
}
```

### Field Descriptions

| Field                      | Type    | Description                                                                                                                |
| -------------------------- | ------- | -------------------------------------------------------------------------------------------------------------------------- |
| `synthetic_spread_bps`     | float   | Simulated bid-ask spread in basis points (bps). Used to model execution slippage. Default: 6 bps                           |
| `synthetic_circuit_pct`    | float   | Simulated circuit band threshold as a percentage (0.01 - 0.20 typical). Used for circuit breaker simulation. Default: 0.10 |
| `max_concurrent_positions` | integer | Maximum number of simultaneously open positions allowed (global limit)                                                     |
| `max_positions_per_sector` | integer | Maximum positions allowed in a single sector                                                                               |
| `max_positions_per_stock`  | integer | Maximum positions allowed in a single stock symbol                                                                         |

---

## Section 3: `config_snapshot` - Full Strategy Configuration

Complete snapshot of all v6/config.py parameters used during the run. This captures the entire strategy ruleset.

### Key Subsections

#### Time Windows

```json
{
  "MARKET_OPEN_TIME": "09:15:00",
  "ENTRY_START_TIME": "09:25:00",
  "ENTRY_CUTOFF_TIME": "14:05:00",
  "FORCE_EXIT_TIME": "15:05:00",
  "MARKET_CLOSE_TIME": "15:30:00",
  "LUNCH_START_TIME": "12:00:00",
  "LUNCH_END_TIME": "13:15:00"
}
```

#### Risk Parameters

```json
{
  "BASE_RISK_PER_TRADE_PCT": 0.005,
  "RISK_MULT_LUNCH": 0.7,
  "RISK_MULT_WARNING": 0.5,
  "DAILY_DRAWDOWN_WARNING_PCT": -0.01,
  "DAILY_DRAWDOWN_HALT_PCT": -0.02
}
```

#### Indicator Parameters

```json
{
  "POINTS_HMA": 3,
  "POINTS_RVOL": 2,
  "POINTS_STOCH": 2,
  "POINTS_SECTOR_RANK": 2,
  "POINTS_SPREAD": 1,
  "CHANDELIER_LOOKBACK": 10,
  "CHANDELIER_ATR_MULT": 3.0,
  "TARGET_1_EXIT_PCT": 0.25,
  "LOOKBACK_DAYS_DAILY": 60,
  "LOOKBACK_DAYS_INTRA": 5,
  "LOOKBACK_DAYS_VIX": 45
}
```

#### Sector Weights

```json
{
  "SECTOR_WEIGHTS": {
    "NIFTY AUTO": 8.7,
    "NIFTY BANK": 35.9,
    "NIFTY ENERGY": 6.0,
    "NIFTY FMCG": 10.9,
    ... (15 sectors total)
  }
}
```

#### VIX Regime Thresholds

```json
{
  "RVOL_THRESHOLDS": [
    [25, 1.5],
    [50, 1.3],
    [75, 1.1],
    [100, 1.0]
  ],
  "MIN_ADV_CRORES": 75.0
}
```

#### Grade Multipliers

```json
{
  "GRADE_MULTIPLIERS": {
    "A+": 1.0,
    "A": 0.85,
    "B": 0.6,
    "C": 0.0
  }
}
```

---

## Section 4: `summary` - Backtest Performance Summary

High-level analytics and counts aggregating the complete backtest results.

### Structure

```json
{
  "summary": {
    "initial_equity": 1000000.0,
    "final_equity": 1023400.5,
    "total_return": 23400.5,
    "total_return_pct": 2.34,
    "trading_days": 1,
    "closed_trades": 12,
    "a_grade_signals": 12,
    "position_candidates": 12,
    "executed_positions": 12,
    "all_a_grade_signals": 45,
    "all_position_candidates": 45,
    "all_trade_candidates": 45,
    "max_positions_slot_available_count": 32,
    "blocked_by_max_positions_count": 8,
    "decision_counts": {
      "EXECUTED": 12,
      "RISK_REJECTED:INSUFFICIENT_BALANCE": 15,
      "RISK_REJECTED:MAX_POSITIONS": 8,
      "SAFETY_REJECTED:SAFETY_HALT": 10
    },
    "risk_reason_counts": {
      "OK": 12,
      "MAX_POSITIONS": 8,
      "INSUFFICIENT_BALANCE": 15,
      "MAX_SECTOR_LIMIT": 5,
      "MAX_STOCK_LIMIT": 5
    }
  }
}
```

### Field Descriptions

| Field                                | Type    | Description                                                |
| ------------------------------------ | ------- | ---------------------------------------------------------- |
| `initial_equity`                     | float   | Starting account value (INR)                               |
| `final_equity`                       | float   | Ending account value (INR)                                 |
| `total_return`                       | float   | Absolute profit/loss in INR                                |
| `total_return_pct`                   | float   | Return as percentage (e.g., 2.34 for 2.34%)                |
| `trading_days`                       | integer | Number of trading days processed                           |
| `closed_trades`                      | integer | Number of trades that were fully executed and closed       |
| `a_grade_signals`                    | integer | A/A+ signals that were _executed_ (config-constrained)     |
| `position_candidates`                | integer | Position records for executed signals only                 |
| `executed_positions`                 | integer | Count of positions that became actual trades               |
| `all_a_grade_signals`                | integer | Total A/A+ signals across entire opportunity universe      |
| `all_position_candidates`            | integer | All position analysis records (both executed and rejected) |
| `all_trade_candidates`               | integer | All trade candidate records in universe                    |
| `max_positions_slot_available_count` | integer | Count of signals that had position slots available         |
| `blocked_by_max_positions_count`     | integer | Count of signals blocked by max position limit             |
| `decision_counts`                    | object  | Histogram of entry_decision outcomes (see keys below)      |
| `risk_reason_counts`                 | object  | Histogram of risk rejection reasons                        |

#### Decision Count Keys

- `EXECUTED` - Trade was successfully executed
- `RISK_REJECTED:<reason>` - Rejected by risk manager with specific reason
- `SAFETY_REJECTED:<reason>` - Rejected by safety monitor
- Any other entry_decision value

#### Risk Reason Keys

- `OK` - Risk check passed
- `MAX_POSITIONS` - Global max concurrent positions limit hit
- `MAX_SECTOR_LIMIT` - Sector position limit exceeded
- `MAX_STOCK_LIMIT` - Stock-level position limit exceeded
- `INSUFFICIENT_BALANCE` - Account equity insufficient for position sizing
- (Others depending on risk rules)

---

## Section 5: `daily_results` - Per-Day Performance

Array of results for each trading day processed.

### Structure

```json
{
  "daily_results": [
    {
      "day": "2026-01-06",
      "start_equity": 1000000.0,
      "end_equity": 1023400.5,
      "pnl": 23400.5,
      "trades": 12,
      "trade_pnls": [357.2, -138.0, 61.92, -135.0, 284.5, ..., 105.3]
    }
  ]
}
```

### Field Descriptions

| Field          | Type            | Description                                          |
| -------------- | --------------- | ---------------------------------------------------- |
| `day`          | ISO 8601 date   | Trading date (YYYY-MM-DD)                            |
| `start_equity` | float           | Account equity at market open (INR)                  |
| `end_equity`   | float           | Account equity at market close (INR) after all exits |
| `pnl`          | float           | Day's profit/loss: `end_equity - start_equity` (INR) |
| `trades`       | integer         | Number of trades closed on this day                  |
| `trade_pnls`   | array of floats | P&L for each individual trade closed (INR)           |

**Note:** Individual trade P&Ls in `trade_pnls` array are aligned with trades closed on that day in the order they appear in `trade_records`.

---

## Section 6: `all_signal_records` - Complete Opportunity Universe

Array containing **every A/A+ quality signal** generated during the backtest, regardless of whether it was executed. This is the **full opportunity universe**.

### Structure (Example Signal)

```json
{
  "all_signal_records": [
    {
      "signal_id": "SIG_20260106_0925_HINDZINC_000001",
      "timestamp": "2026-01-06T09:25:00",
      "scan_order": 4,
      "playbook": "MAIN",
      "regime": "MEAN_REVERT",
      "symbol": "HINDZINC",
      "sector": "NIFTY METAL",
      "direction": "LONG",
      "grade": "A+",
      "score": 9.0,
      "reasons": [
        "HMA Fully Aligned",
        "Strong RVOL (2.08)",
        "StochRSI Neutral",
        "Top 3 Sector (Rank 1)",
        "Superior Spread Quality"
      ],
      "price": 639.0,
      "change_pct": 1.6544702513522076,
      "hma_align": "BULLISH",
      "rvol": 2.0785959233748477,
      "stoch_k": 26.189785784494664,
      "sector_rank": 1,
      "spread_atr": 0.019368527405907447,
      "gate_passed": true,
      "gate_reason": "PASS",
      "adv_crores": 811.8840908672498,
      "atr": 19.794999999999995,
      "vix_ltp": 10.2,
      "vix_percentile": 75.0,
      "vix_multiplier": 0.75,
      "nifty_ltp": 26173.85,
      "nifty_pct": -0.2912347668407627,
      "open_positions_before": 0,
      "max_positions_limit": 6,
      "max_positions_slot_available": true,
      "blocked_by_max_positions": false,
      "risk_allowed": true,
      "risk_reason": "OK",
      "entry_decision": "EXECUTED",
      "executed_trade": true,
      "executed_trade_id": "TRD_HINDZINC_20260106_0925_1",
      "executed_within_max_positions": true
    }
  ]
}
```

### Field Descriptions

#### Signal Identity & Timing

| Field        | Type              | Description                                                      |
| ------------ | ----------------- | ---------------------------------------------------------------- |
| `signal_id`  | string            | Unique signal ID: `SIG_YYYYMMDD_HHMM_SYMBOL_XXXXXX`              |
| `timestamp`  | ISO 8601 datetime | Exact time signal was generated                                  |
| `scan_order` | integer           | Order in which this signal was evaluated in the scan (ascending) |
| `playbook`   | string            | Market playbook state: MAIN, FORCE_EXIT, INIT, etc.              |

#### Signal Quality & Grading

| Field       | Type             | Description                                            |
| ----------- | ---------------- | ------------------------------------------------------ |
| `symbol`    | string           | Stock ticker symbol                                    |
| `sector`    | string           | Sector classification (e.g., "NIFTY METAL")            |
| `direction` | string           | "LONG" or "SHORT"                                      |
| `grade`     | string           | Signal grade: "A+", "A", "B", "C" (only A/A+ included) |
| `score`     | float            | Composite score (typically 0-10 range for A grades)    |
| `reasons`   | array of strings | Human-readable factors contributing to the signal      |

#### Market & Instrument Data

| Field         | Type    | Description                                                                    |
| ------------- | ------- | ------------------------------------------------------------------------------ |
| `price`       | float   | LTP (Last Traded Price) at signal time (INR)                                   |
| `change_pct`  | float   | Percent change from previous close (decimal, e.g., 1.65 = +1.65%)              |
| `hma_align`   | string  | HMA alignment: "BULLISH", "BEARISH", "NEUTRAL", "WEAK_BULLISH", "WEAK_BEARISH" |
| `rvol`        | float   | Realized Volatility ratio (e.g., 2.08 = 208% of typical)                       |
| `stoch_k`     | float   | Stochastic RSI K value (0-100 scale)                                           |
| `sector_rank` | integer | Sector rank (1 = #1 performing sector, 15 = weakest)                           |
| `spread_atr`  | float   | Bid-ask spread as fraction of ATR (liquidity metric)                           |
| `adv_crores`  | float   | Average Daily Volume in Indian crores (INR)                                    |
| `atr`         | float   | Average True Range (volatility measure, INR)                                   |

#### Market Regime

| Field            | Type   | Description                                                   |
| ---------------- | ------ | ------------------------------------------------------------- |
| `vix_ltp`        | float  | India VIX level at signal time                                |
| `vix_percentile` | float  | VIX percentile (0-100) from 45-day historical window          |
| `vix_multiplier` | float  | Risk multiplier derived from VIX percentile (0.5 - 1.5 range) |
| `nifty_ltp`      | float  | NIFTY 50 price at signal time (INR)                           |
| `nifty_pct`      | float  | NIFTY % change from previous close                            |
| `regime`         | string | Market regime: "MEAN_REVERT", "TREND", "LOW_VIX", "HIGH_VIX"  |

#### Gating & Filtering

| Field         | Type    | Description                                                  |
| ------------- | ------- | ------------------------------------------------------------ |
| `gate_passed` | boolean | Whether signal passed the entry gate (ADV, liquidity checks) |
| `gate_reason` | string  | Gate status: "PASS", "FAIL_LOW_ADV", "FAIL_LOW_SPREAD", etc. |

#### Position Management

| Field                          | Type    | Description                                 |
| ------------------------------ | ------- | ------------------------------------------- |
| `open_positions_before`        | integer | Number of open positions before this signal |
| `max_positions_limit`          | integer | Max concurrent positions allowed            |
| `max_positions_slot_available` | boolean | True if position slot is available          |
| `blocked_by_max_positions`     | boolean | True if rejected due to max positions limit |

#### Risk & Execution

| Field            | Type    | Description                                                                                               |
| ---------------- | ------- | --------------------------------------------------------------------------------------------------------- |
| `risk_allowed`   | boolean | Whether risk manager approved the trade                                                                   |
| `risk_reason`    | string  | Risk decision: "OK", "MAX_POSITIONS", "INSUFFICIENT_BALANCE", "MAX_SECTOR_LIMIT", "MAX_STOCK_LIMIT", etc. |
| `entry_decision` | string  | Final decision: "EXECUTED", "RISK_REJECTED:<reason>", "SAFETY_REJECTED:<reason>", etc.                    |

#### Execution Result

| Field                           | Type    | Description                                                                    |
| ------------------------------- | ------- | ------------------------------------------------------------------------------ |
| `executed_trade`                | boolean | True if this signal resulted in executed trade                                 |
| `executed_trade_id`             | string  | Trade ID if executed (e.g., "TRD_HINDZINC_20260106_0925_1"), or "" if rejected |
| `executed_within_max_positions` | boolean | True if executed while position slot was available                             |

---

## Section 7: `all_position_records` - Position Analysis (All Signals)

Array containing **position-level analysis** for every signal in the opportunity universe. Includes sizing calculations, risk metrics, and blocking reasons.

### Structure (Example Position Record)

```json
{
  "all_position_records": [
    {
      "signal_id": "SIG_20260106_0925_HINDZINC_000001",
      "timestamp": "2026-01-06T09:25:00",
      "symbol": "HINDZINC",
      "sector": "NIFTY METAL",
      "direction": "LONG",
      "grade": "A+",
      "entry_price": 639.0,
      "atr": 19.794999999999995,
      "stop_price": 599.41,
      "target_1": 698.385,
      "open_positions_before": 0,
      "max_positions_limit": 6,
      "max_positions_slot_available": true,
      "max_positions_considered": true,
      "blocked_by_max_positions": false,
      "blocked_by_sector_limit": false,
      "blocked_by_stock_limit": false,
      "risk_allowed": true,
      "risk_reason": "OK",
      "sizing_allowed": true,
      "sizing_reason": "OK (Mult: 0.75x)",
      "sizing_shares": 94,
      "risk_amount": 3750.0,
      "risk_per_share": 39.59000000000003,
      "effective_risk_pct": 0.00375,
      "entry_decision": "EXECUTED",
      "executed_trade": true,
      "executed_trade_id": "TRD_HINDZINC_20260106_0925_1",
      "executed_within_max_positions": true
    }
  ]
}
```

### Field Descriptions

#### Identity & Signal Link

| Field       | Type              | Description                                       |
| ----------- | ----------------- | ------------------------------------------------- |
| `signal_id` | string            | Links to corresponding `all_signal_records` entry |
| `timestamp` | ISO 8601 datetime | Signal timestamp (same as signal)                 |
| `symbol`    | string            | Stock ticker                                      |
| `sector`    | string            | Sector name                                       |
| `direction` | string            | "LONG" or "SHORT"                                 |
| `grade`     | string            | Signal grade ("A+", "A", etc.)                    |

#### Entry & Stop Levels

| Field         | Type  | Description                      |
| ------------- | ----- | -------------------------------- |
| `entry_price` | float | LTP at signal time (INR)         |
| `atr`         | float | ATR at signal time (INR)         |
| `stop_price`  | float | Calculated stop loss price (INR) |
| `target_1`    | float | Target 1 exit price (INR)        |

**Stop & Target Calculation:**

- For LONG: `stop = entry - (2 * ATR)`, `target = entry + (ATR / 2)`
- For SHORT: `stop = entry + (2 * ATR)`, `target = entry - (ATR / 2)`

#### Position Limit Checks

| Field                          | Type    | Description                                                       |
| ------------------------------ | ------- | ----------------------------------------------------------------- |
| `open_positions_before`        | integer | Open positions when this signal was evaluated                     |
| `max_positions_limit`          | integer | Global max concurrent positions                                   |
| `max_positions_considered`     | boolean | Always true (this field indicates position limits were evaluated) |
| `max_positions_slot_available` | boolean | True if global position limit not hit                             |
| `blocked_by_max_positions`     | boolean | True if rejected by global limit                                  |
| `blocked_by_sector_limit`      | boolean | True if sector limit exceeded                                     |
| `blocked_by_stock_limit`       | boolean | True if stock-level limit exceeded                                |

#### Risk Manager Decision

| Field          | Type    | Description                 |
| -------------- | ------- | --------------------------- |
| `risk_allowed` | boolean | Final risk manager approval |
| `risk_reason`  | string  | Risk decision reason        |

#### Position Sizing

| Field                | Type    | Description                                                        |
| -------------------- | ------- | ------------------------------------------------------------------ |
| `sizing_allowed`     | boolean | Whether sizing calculation succeeded                               |
| `sizing_reason`      | string  | Sizing status (e.g., "OK (Mult: 0.75x)" or "INSUFFICIENT_BALANCE") |
| `sizing_shares`      | integer | Number of shares to trade                                          |
| `risk_amount`        | float   | Absolute rupee amount at risk (INR)                                |
| `risk_per_share`     | float   | Risk amount divided by shares (INR per share)                      |
| `effective_risk_pct` | float   | Risk as % of account equity (decimal, e.g., 0.00375 = 0.375%)      |

#### Entry Decision & Execution Result

| Field                           | Type    | Description                                                                  |
| ------------------------------- | ------- | ---------------------------------------------------------------------------- |
| `entry_decision`                | string  | Final decision: "EXECUTED", "RISK_REJECTED:...", "SAFETY_REJECTED:...", etc. |
| `executed_trade`                | boolean | True if trade was executed                                                   |
| `executed_trade_id`             | string  | Links to trade in `trade_records`                                            |
| `executed_within_max_positions` | boolean | True if executed while position slot available                               |

---

## Section 8: `signal_records` - Executed Signals Only

Subset of `all_signal_records` containing **only signals that were actually executed**. Same structure and fields as `all_signal_records`, but filtered to executed trades only.

**Usage:** When analyzing strategy execution, this contains the actual path taken (what was traded).

---

## Section 9: `position_records` - Executed Positions Only

Subset of `all_position_records` containing **only position records for executed signals**. Same structure as `all_position_records`, but filtered to executed trades only.

**Usage:** Risk and sizing analysis for actual trades only.

---

## Section 10: `trade_records` - Executed & Closed Trades

Array of **fully executed and closed trades** with entry and exit details.

### Structure (Example Trade Record)

```json
{
  "trade_records": [
    {
      "trade_id": "TRD_HINDZINC_20260106_0925_1",
      "symbol": "HINDZINC",
      "sector": "NIFTY METAL",
      "direction": "LONG",
      "entry_time": "2026-01-06T09:25:00",
      "entry_price": 639.0,
      "initial_qty": 94,
      "exit_time": "2026-01-06T15:05:00",
      "exit_price": 642.8,
      "exit_reason": "FORCE_EXIT",
      "realized_pnl": 357.1999999999957,
      "stage": "CLOSED"
    },
    {
      "trade_id": "TRD_VEDL_20260106_0925_2",
      "symbol": "VEDL",
      "sector": "NIFTY METAL",
      "direction": "LONG",
      "entry_time": "2026-01-06T09:25:00",
      "entry_price": 622.4,
      "initial_qty": 138,
      "exit_time": "2026-01-06T15:05:00",
      "exit_price": 621.4,
      "exit_reason": "FORCE_EXIT",
      "realized_pnl": -138.0,
      "stage": "CLOSED"
    }
  ]
}
```

### Field Descriptions

#### Trade Identity

| Field       | Type   | Description                                         |
| ----------- | ------ | --------------------------------------------------- |
| `trade_id`  | string | Unique trade ID: `TRD_SYMBOL_YYYYMMDD_HHMM_COUNTER` |
| `symbol`    | string | Stock ticker symbol                                 |
| `sector`    | string | Sector classification                               |
| `direction` | string | "LONG" or "SHORT"                                   |

#### Entry Details

| Field         | Type              | Description           |
| ------------- | ----------------- | --------------------- |
| `entry_time`  | ISO 8601 datetime | Exact execution time  |
| `entry_price` | float             | Execution price (INR) |
| `initial_qty` | integer           | Shares bought/sold    |

#### Exit Details

| Field         | Type              | Description                                   |
| ------------- | ----------------- | --------------------------------------------- |
| `exit_time`   | ISO 8601 datetime | When position was closed                      |
| `exit_price`  | float             | Exit execution price (INR)                    |
| `exit_reason` | string            | Why trade was closed (see exit reasons below) |

#### P&L & Status

| Field          | Type   | Description                                        |
| -------------- | ------ | -------------------------------------------------- |
| `realized_pnl` | float  | Actual profit/loss realized (INR)                  |
| `stage`        | string | Always "CLOSED" in trade_records (lifecycle stage) |

#### Exit Reason Values

- `STOP` - Stopped out at stop loss level
- `TARGET1_FULL` - Exited at full target price
- `TARGET1_PARTIAL` - Partially exited at target, remainder stopped at chandelier
- `DAY_END_CLEANUP` - Force exited at market close
- `FORCE_EXIT` - Forced exit during FORCE_EXIT playbook
- `SAFETY_HALT` - Exited due to safety halt trigger

---

## Data Relationships & Keys

### Signal → Position → Trade Trail

1. **`all_signal_records[i]`** → **`all_position_records[j]`** → **`trade_records[k]`**
   - Linked via `signal_id` and `executed_trade_id`
   - Not all signals have corresponding trades (some are rejected)

2. **Key Matching:**

   ```
   all_signal_records[i].signal_id == all_position_records[j].signal_id
   all_signal_records[i].executed_trade_id == trade_records[k].trade_id
   ```

3. **Filtering Relationships:**
   - `signal_records` ⊆ `all_signal_records` (executed only)
   - `position_records` ⊆ `all_position_records` (executed only)
   - `trade_records` = finalized trades (all executed and closed)

---

## Key Metrics & Calculations

### Per-Trade Calculations

**P&L Calculation:**

```
For LONG:  P&L = (exit_price - entry_price) × initial_qty
For SHORT: P&L = (entry_price - exit_price) × initial_qty
```

**Win/Loss Classification:**

```
Win:  realized_pnl > 0
Loss: realized_pnl < 0
Break-even: realized_pnl == 0
```

### Portfolio-Level Calculations

**Total Return (from summary):**

```
Total Return = final_equity - initial_equity
Total Return % = (final_equity / initial_equity - 1) × 100
```

**Win Rate:**

```
Win Rate = count(realized_pnl > 0) / total_trades
```

**Execution Rate:**

```
Execution Rate = executed_positions / all_position_candidates
```

**Average Trade P&L:**

```
Avg P&L = sum(trade_pnl) / total_trades
```

---

## File Organization & Naming

### History Files Location

```
backtest_v6/
├── history/
│   ├── backtest_history_23-02-2026_01-30_pm.json
│   ├── backtest_history_23-02-2026_01-35_pm.json
│   ├── backtest_history_23-02-2026_01-56_am.json
│   └── ouput_file_structure.md (this document)
```

### Filename Format

```
backtest_history_DD-MM-YYYY_HH-MM_am|pm.json
                    ^------^  ^----------^
                    Run Date  Run Time
```

- **Date Label:** 23-02-2026 (Day-Month-Year)
- **Time Label:** 01:30 pm (12-hour format with am/pm)
- **Sequential:** If multiple runs occur at same timestamp, adds \_2, \_3 suffix

---

## Summary & Usage Guide

| Use Case                  | Section                                                 | Key Fields                                         |
| ------------------------- | ------------------------------------------------------- | -------------------------------------------------- |
| Overall performance       | `summary` + `daily_results`                             | final_equity, total_return_pct, closed_trades      |
| Full opportunity analysis | `all_signal_records` + `all_position_records`           | All signals before filtering, decision_counts      |
| Actual trading path       | `signal_records` + `position_records` + `trade_records` | Executed trades only                               |
| Individual trade analysis | `trade_records`                                         | entry_price, exit_price, realized_pnl, exit_reason |
| Risk analysis             | `all_position_records`                                  | risk_amount, effective_risk_pct, risk_reason       |
| Market conditions         | `all_signal_records`                                    | vix_ltp, nifty_ltp, regime, vix_multiplier         |
| Strategy parameters       | `inputs` + `config_snapshot`                            | All configuration used                             |
| Execution blockers        | `all_position_records` + `summary`                      | blocked*by*\* fields, decision_counts              |

---

**Last Updated:** February 23, 2026  
**Format Version:** 1.0  
**Generated by:** SectorBacktesterV6
