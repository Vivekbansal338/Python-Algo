# Issue: Log File Unbounded Growth (No Rotation)

## Status: Completed (2026-02-20)

## Severity: Low

## Location: `v6/main.py`

---

## Description

The logging configuration uses `logging.basicConfig` with a single file target and no rotation policy.

## Current Behavior

- All logs are appended to `v6_bot.log`.
- File size will grow indefinitely over time.

## Impact

- Disk space exhaustion eventually.
- Hard to open/parse massive log files.

## Proposed Fix

1. Use `logging.handlers.RotatingFileHandler`.
2. Configure max size (e.g., 10MB) and backup count (e.g., 5).

## Acceptance Criteria

- Logs rotate when size threshold is reached.
- Old logs are kept up to backup count.

---

## Resolution Summary

- Replaced `logging.basicConfig(...)` file logging in `v6/main.py` with `RotatingFileHandler`.
- Added config controls in `v6/config.py`:
  - `LOG_MAX_BYTES`
  - `LOG_BACKUP_COUNT`
- Log file now rotates automatically with bounded backup retention.
