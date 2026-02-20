# V6 Issue Tracking - Priority List

> Last Updated: 2026-02-20  
> Total Issues: 21

---

## CRITICAL (Fix Immediately - Risk/Safety)

| Priority | Issue # | Issue Title                          | Severity | Location                        | Status |
| -------- | ------- | ------------------------------------ | -------- | ------------------------------- | ------ |
| 1        | #008    | Tick Staleness Detection             | Critical | data_engine.py, main.py         | Open   |
| 2        | #007    | WebSocket Disconnect Fallback        | Critical | data_engine.py, main.py         | Completed   |
| 3        | #015    | Drawdown Killswitch Not Invoked      | High     | main.py, brain.py               | Open   |
| 4        | #010    | Equity Tracking (Paper PnL)          | High     | main.py, execution.py, brain.py | Open   |
| 5        | #016    | Daily Start Equity Never Initialized | High     | main.py, brain.py, execution.py | Open   |
| 6        | #004    | Daily High-Water Mark Unused         | High     | execution.py, brain.py          | Open   |

---

## HIGH (Risk Controls & Testing)

| Priority | Issue # | Issue Title                        | Severity | Location                     | Status |
| -------- | ------- | ---------------------------------- | -------- | ---------------------------- | ------ |
| 7        | #011    | Zero Test Coverage                 | High     | Entire v6/                   | Open   |
| 8        | #003    | Correlation Threshold Not Enforced | Medium   | config.py, brain.py, main.py | Completed   |
| 9        | #006    | Safety Breadth Collapse Unwired    | Medium   | main.py, brain.py            | Open   |

---

## MEDIUM (Core Functionality)

| Priority | Issue # | Issue Title                      | Severity | Location                | Status |
| -------- | ------- | -------------------------------- | -------- | ----------------------- | ------ |
| 10       | #001    | Missing Opening Range (OR) Logic | Medium   | main.py                 | Open   |
| 11       | #002    | RVOL 5-Minute Candle Lag         | Medium   | main.py                 | Open   |
| 12       | #014    | Thread Safety (live_ticks)       | Medium   | data_engine.py, main.py | Completed   |
| 13       | #012    | Holiday/Weekend Detection        | Medium   | main.py                 | Open   |
| 14       | #017    | Safety Window Cadence Mismatch   | Medium   | brain.py, main.py       | Open   |
| 15       | #018    | Market Close Playbook Absent     | Medium   | main.py, config.py      | Open   |

---

## LOW (Polish/Config)

| Priority | Issue # | Issue Title                       | Severity | Location            | Status   |
| -------- | ------- | --------------------------------- | -------- | ------------------- | -------- |
| 16       | #019    | MAX_POSITIONS_PER_STOCK Unused    | Low      | config.py, brain.py | Completed     |
| 17       | #005    | VIX Multiplier Flat (75th=90th)   | Low      | brain.py            | Completed     |
| 18       | #020    | Log File Rotation Missing         | Low      | main.py             | Completed     |
| 19       | #009    | State Save Race Condition         | Low      | main.py             | Completed     |
| 20       | #013    | Active Position Monitor (Feature) | Feature  | -                   | Proposed |
| 21       | #021    | Unbounded Order History           | Medium   | execution.py        | Completed     |
