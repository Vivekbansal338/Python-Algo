# Issue: Redundant 15-Minute Sector Logic

## 1. Description
The codebase contains a configuration constant `SECTOR_RECALC_INTERVAL_SEC` set to 900 seconds (15 minutes) and a corresponding orchestrator method `run_strategy_cycle` intended to perform periodic sector re-ranking. 

## 2. Findings
Our analysis of the execution loop in `main_v4.py` reveals that this 15-minute periodic update is redundant and biologically "dead" within the system architecture for the following reasons:

### A. The Real-Time Overwrite
The main trading loop calls `_recalculate_live_metrics()` every **5 seconds** (controlled by `UI_REFRESH_INTERVAL`). Inside this 5-second function, the bot performs the following:
*   Updates Sector prices and returns using live WebSocket ticks.
*   Calculates real-time Sector Breadth (LTP vs VWAP).
*   Calls `self.sector_scorer.score_all()`, which re-calculates the Composite Score and **re-ranks** every sector.
*   Calls `self.sector_scorer.select_top_n()`, which updates the selected trading universe.

### B. Logic Displacement
Because the re-ranking and scoring logic is already executing every 5 seconds, the 15-minute timer never triggers a "new" state. By the time 15 minutes pass, the sectors have already been re-ranked 180 times by the high-speed loop.

### C. Initialization Only
Currently, the `run_strategy_cycle` logic serves only as a "Primer" at startup to populate the UI with REST data before the WebSocket stream is fully active. After this initial call, it provides no additional value.

## 3. Recommendation
The system should be refactored to:
1.  Explicitly define the architecture as **WebSocket-Driven**.
2.  Remove the `SECTOR_RECALC_INTERVAL_SEC` constant and associated timer variables.
3.  Formalize the startup "Primer" logic as an initialization step rather than a periodic strategy cycle.
4.  Remove the redundant `run_strategy_cycle` method to improve code maintainability and clarity.
