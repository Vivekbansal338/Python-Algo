# Issue: State Save Can Fire Multiple Times Per Minute

## Status: Open

## Severity: Low

## Location: `v6/main.py` -> `TradingBotV6.run()`

---

## Description

State save uses modulo checks on wall-clock seconds, which can trigger multiple writes within the same second because the loop runs every ~0.5s.

## Current Behavior

```python
if int(time.time()) % 60 == 0:
    self.state_mgr.save_state(...)
```

## Impact

- Duplicate writes and avoidable I/O churn.
- Harder-to-read persistence logs.

## Proposed Fix (Detailed)

1. Replace modulo with elapsed-time guard using monotonic clock.
2. Add field in `TradingBotV6.__init__`:

```python
self.last_state_save_ts = time.monotonic()
```

3. Save condition:

```python
if time.monotonic() - self.last_state_save_ts >= 60:
    save_state()
    self.last_state_save_ts = time.monotonic()
```

4. Keep explicit save on shutdown unchanged.

## Acceptance Criteria

- At most one periodic save per 60-second interval.
- Shutdown still performs immediate save.
