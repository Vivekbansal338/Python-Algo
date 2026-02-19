# Issue: No Holiday or Weekend Detection

## Status: Open

## Severity: Medium

## Location: `v6/main.py`

---

## Description

The runtime does not validate whether today is a trading day before starting full loop execution.

## Current Behavior

- Bot can start on weekends/holidays.
- It may run with stale or non-updating market feeds.
- Resources are consumed even when market is closed.

## Impact

- Operational noise and misleading runtime behavior on non-trading days.
- Increased chance of stale-state assumptions.

## Proposed Fix (Detailed)

1. Add trading-calendar utility module (example: `v6/calendar_utils.py`).
2. Implement `is_trading_day(date)`:

- weekend check (`weekday() < 5`),
- holiday check from maintained NSE holiday list (`config/nse_holidays_YYYY.json`).

3. In `initialize()`, before websocket start:

- if not trading day: log reason and exit gracefully.

4. Add optional intraday session guard:

- if current time is outside market session and `auto_exit_after_close` enabled, save state and stop process.

5. Add yearly holiday file refresh process (manual script or docs instruction).

## Acceptance Criteria

- Weekend start exits with explicit log message.
- Listed holiday start exits with explicit log message.
- Normal weekday trading day proceeds unchanged.
