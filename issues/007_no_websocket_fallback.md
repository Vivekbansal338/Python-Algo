# Issue: No WebSocket Disconnect Fallback

## Status: Open

## Severity: Critical

## Location: `v6/data_engine.py`, `v6/main.py`

---

## Description

WebSocket connectivity state is tracked but not acted on. If websocket disconnects, runtime keeps consuming stale tick cache with no recovery mode.

## Current Behavior

- `is_ws_connected` flips false in `_on_close`.
- Main loop does not branch on websocket health.
- No reconnection loop, no degraded polling mode.

## Impact

- Stop/target management may run on stale data.
- New entries can be made on stale quotes.
- Silent reliability failure.

## Proposed Fix (Detailed)

1. Add websocket watchdog state in `DataManager`:

- `last_tick_received_at` (monotonic timestamp),
- `reconnect_attempts`, `next_reconnect_ts`.

2. Update `_on_ticks` to refresh `last_tick_received_at`.

3. In main loop, detect degraded state when either:

- `is_ws_connected` is false, or
- `now - last_tick_received_at > STALE_FEED_SEC` (e.g., 10-15s).

4. Degraded mode behavior:

- disable new entries,
- continue exit management using REST quote polling for active positions and major indices,
- surface status in UI header (`WS_DEGRADED`).

5. Automatic reconnect:

- attempt reconnect with exponential backoff (1s, 2s, 5s, 10s, 30s, max 60s),
- on stable ticks for `RECOVERY_STABLE_SEC` (e.g., 20s), clear degraded mode.

## Acceptance Criteria

- Disconnect event triggers degraded mode and visible UI status.
- Active trade exits continue via REST fallback path.
- Reconnect succeeds automatically and system returns to normal mode without restart.
