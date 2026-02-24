# Issue: Terminal UI Jumping (Header Flicker / Disappearing)

## Status: Open

## Severity: Medium

## Location: `v6/main.py` (`TradingBotV6.run()`), `DashboardUI.update()` / Rich `Live(...)`

---

## Description

During runtime, the terminal dashboard flickers and jumps vertically, and the top header intermittently disappears/reappears.
This is visible in the provided recording and affects live readability.

## Video Evidence

- Source: `C:\Users\VIVEK BANSAL\Videos\Screen Recordings\Screen Recording 2026-02-21 012535.mp4`
- Observed behavior:
  - header bar is present in some moments,
  - then missing/cut in others,
  - visible vertical redraw jitter (“jumping terminal”).

## Current Behavior

- UI runs with Rich live mode using:
  - `Live(..., refresh_per_second=4, screen=True)`
- Main loop also manually calls `live.update(self.ui.render())` every loop.
- So rendering is driven by both:
  - auto-refresh thread (from `refresh_per_second`), and
  - explicit update calls from main loop.
- `Layout` regions are mutated every cycle (`header`, `scanner`, `positions`, `logs`) while live refresh may happen concurrently.

## Impact

- Critical header state (session/feed/risk) is intermittently not visible.
- Operator confidence and usability drop during monitoring.
- Visual instability makes debugging and live supervision harder.

## Plain-English Explanation

The dashboard is being redrawn in a way that causes visual tearing/flicker.
So sometimes the top line (header) disappears for a moment and the screen looks like it jumps.

## Proposed Fix (Detailed)

1. Use a single render clock (remove dual refresh paths):

- start Live with `auto_refresh=False`.
- keep explicit render updates only from main loop:
  - `live.update(self.ui.render(), refresh=True)`.

2. Add a dedicated UI redraw cadence constant (e.g. `TUI_REDRAW_INTERVAL_SEC = 0.5`) and only redraw on that schedule.

3. Keep data/state computation separate from UI paint step:

- compute full `ui_state`,
- apply `self.ui.update(ui_state)`,
- perform one atomic `live.update(...)`.

4. Add optional fallback for terminals that flicker in alt-screen mode:

- config flag to run `Live(..., screen=False)` when needed.

5. (Optional) Minimize very long log lines in panel to reduce wrapping churn.

## Acceptance Criteria

- Header remains continuously visible (no intermittent disappearance) during at least 2 minutes runtime.
- No visible vertical jump/flicker in normal update cadence.
- UI remains responsive and feed/risk statuses still update correctly.
- Behavior is stable in Windows PowerShell terminal used in this recording.
