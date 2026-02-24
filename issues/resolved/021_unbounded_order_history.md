# Issue: Unbounded Growth of Paper Order History

## Status: Completed (2026-02-20)

## Severity: Medium

## Location: `v6/execution.py` (`OrderManager`)

---

## Description

`OrderManager.paper_orders` stores every order generated since session start (or restored from state). There is no mechanism to archive or prune closed/cancelled orders.

## Current Behavior

- Every entry, stop, and exit order is added to dictionary.
- State save writes full dictionary to JSON.
- Restore loads full dictionary.

## Impact

- Memory usage grows linearly with trade count.
- `state_v6.json` grows indefinitely, slowing down save/load.
- Performance degradation over long runs (weeks/months).

## Proposed Fix

1. Prune `paper_orders` in memory:
   - Keep only `OPEN` or `TRIGGER PENDING` orders.
   - Keep `COMPLETE`/`CANCELLED` orders only for active trade lifecycle.
   - Or implement a "Day History" vs "Archive" separation.

2. On State Save:
   - Only save active orders and perhaps last N historical orders (e.g., last 50).

## Acceptance Criteria

- `paper_orders` size remains bounded (e.g., < 1000 items) regardless of uptime.
- State file size does not explode over time.

---

## Resolution Summary

- Added bounded retention in `OrderManager` (`v6/execution.py`):
  - `MAX_PAPER_ORDER_HISTORY` cap with pruning of oldest closed orders,
  - always keeps pending/open orders.
- Added bounded persistence via `get_orders_for_persistence()`:
  - persists all active orders + only the most recent closed history slice.
- Updated `StateManager.save_state(...)` to persist bounded order set.
- Updated restore path to prune loaded order history after deserialization.
