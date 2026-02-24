# V6 Trading Schedule (Exact `get_playbook()` Mapping)

> Source of truth: `v6/main.py:get_playbook()` and `v6/config.py` constants.
> Last verified against code: June 2025 (post issue #001 resolution).

---

## 1. Effective Playbook Windows

| Time (IST)     | Playbook      | New Entries | Notes                        |
| -------------- | ------------- | ----------- | ---------------------------- |
| Before 09:15   | `PRE_MARKET`  | No          | Pre-open state               |
| 09:15-09:24:59 | `WAIT`        | No          | First two 5-min candles form |
| 09:25-14:04:59 | `MAIN`        | Yes         | Unified momentum strategy    |
| 14:05-15:04:59 | `EXIT_ONLY`   | No          | Manage open trades only      |
| 15:05-15:29:59 | `FORCE_EXIT`  | No          | Force-close mode             |
| 15:30 onward   | `AFTER_CLOSE` | No          | Housekeeping and shutdown    |

Important:

- The old ORB/OR_FORMATION/GAP phases were removed (issue #001). A single MAIN strategy now covers all entries.
- `AFTER_CLOSE` triggers final state save and auto-shutdown.

---

## 2. State Machine in Code

```text
PRE_MARKET -> WAIT -> MAIN -> EXIT_ONLY -> FORCE_EXIT -> AFTER_CLOSE
```

---

## 3. Config Constants Used by `get_playbook()`

- `MARKET_OPEN_TIME` (09:15)
- `ENTRY_START_TIME` (09:25)
- `ENTRY_CUTOFF_TIME` (14:05)
- `FORCE_EXIT_TIME` (15:05)
- `MARKET_CLOSE_TIME` (15:30)

Other timing constants still used elsewhere:

- `LUNCH_START_TIME` and `LUNCH_END_TIME` are used in position sizing logic (not playbook routing).

---

## 4. Quick Reference Timeline

```text
09:15  WAIT
09:25  MAIN
14:05  EXIT_ONLY
15:05  FORCE_EXIT
15:30  AFTER_CLOSE
```

---

## 5. Related Known Gaps

- Issue #001 (ORB removal / unified strategy): Resolved.
- Issue #018 (market close playbook): Resolved — `AFTER_CLOSE` state now exists.
