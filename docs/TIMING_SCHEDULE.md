# V6 Trading Schedule (Exact `get_playbook()` Mapping)

> Source of truth: `v6/main.py:get_playbook()` and `v6/config.py` constants.
> Last verified against code: February 19, 2026.

---

## 1. Effective Playbook Windows

| Time (IST) | Playbook | New Entries | Notes |
| --- | --- | --- | --- |
| Before 09:15 | `PRE_MARKET` | No | Pre-open state |
| 09:15-09:19:59 | `WAIT` | No | Stabilization window |
| 09:20-09:33:59 | `OR_FORMATION` | No | OR formation label only |
| 09:34-10:04:59 | `ORB` | Yes | Strict gate profile |
| 10:05-10:09:59 | `GAP` | No | Transition window |
| 10:10-14:04:59 | `MAIN` | Yes | Normal gate profile |
| 14:05-15:04:59 | `EXIT_ONLY` | No | Manage open trades only |
| 15:05 onward | `FORCE_EXIT` | No | Force-close mode remains active |

Important:

- There is no separate `MARKET_CLOSE` playbook state in `get_playbook()`.
- After 15:05, the function keeps returning `FORCE_EXIT`.

---

## 2. State Machine in Code

```text
PRE_MARKET -> WAIT -> OR_FORMATION -> ORB -> GAP -> MAIN -> EXIT_ONLY -> FORCE_EXIT
```

Terminal behavior in current implementation:

- `FORCE_EXIT` is terminal for the day unless process is stopped/restarted.

---

## 3. Config Constants vs Playbook Usage

### Directly used by `get_playbook()`

- `MARKET_OPEN_TIME`
- `OR_START_TIME`
- `OR_END_TIME`
- `GAP_START_TIME`
- `GAP_END_TIME`
- `ENTRY_CUTOFF_TIME`
- `FORCE_EXIT_TIME`

### Defined but not used by `get_playbook()`

- `ORB_START_TIME`
- `ORB_END_TIME`
- `MAIN_START_TIME`
- `MAIN_END_TIME`
- `MARKET_CLOSE_TIME`

Other timing constants still used elsewhere:

- `LUNCH_START_TIME` and `LUNCH_END_TIME` are used in position sizing logic (not playbook routing).

---

## 4. ORB Timing Caveat

Current behavior starts ORB at 09:34 boundary because `get_playbook()` transitions to ORB immediately after `OR_END_TIME`.

- `OR_END_TIME = 09:34`
- `ORB_START_TIME = 09:35` (currently unused by routing)

Tracked issue: `issues/001_missing_or_logic.md` (also covers missing opening-range breakout enforcement).

---

## 5. Quick Reference Timeline

```text
09:15  WAIT
09:20  OR_FORMATION
09:34  ORB
10:05  GAP
10:10  MAIN
14:05  EXIT_ONLY
15:05  FORCE_EXIT (persists)
```

---

## 6. Related Known Gaps

- No distinct post-close playbook state (`issues/018_market_close_playbook_absent.md`).
- OR timing constants are partially disconnected from actual state routing (`issues/001_missing_or_logic.md`).
