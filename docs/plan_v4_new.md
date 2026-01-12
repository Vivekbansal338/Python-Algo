# 🚀 PROJECT V4: THE AUTONOMOUS TRADING ENGINE (REWRITE)

**Status:** Draft / Master Blueprint
**Methodology:** Clean Slate Rewrite (No imports from V3)
**Goal:** Production-grade, fully automated execution system with a high-performance terminal UI.

---

## 1. Core Philosophy

V4 is **not** an extension of V3. It is a ground-up rewrite designed for **Execution reliability** and **State safety**.
While V3 was an _Analysis Tool_, V4 is a _Trading Bot_.
It must integrate the **Analysis Logic** (from V3) directly into its own efficient pipeline, feeding a robust **Execution Engine** (from Concepts).

**⚠️ SCOPE LIMITATION:** V4 is **strictly for PAPER TRADING (Simulation)**. All execution logic will be built to mimic real trading, but actual Kite API order placement (Live Mode) is deferred to **Project V5**.

**Guiding Principles:**

1.  **Safety First:** Risk checks happen _before_ every single order. Kill switches are hard-coded.
2.  **State Persistence:** The bot must survive a crash/restart without losing track of open positions.
3.  **Visual Clarity:** The "Rich" UI must provide a "Command Center" view—combining Market Scan (Left) with Portfolio State (Right).
4.  **Strict Timing:** Millisecond-precision awareness of Playbooks (ORB vs Main) and specific minute-based triggers (15:05 Force Exit).

---

## 2. Architecture & File Structure (All New in `07.python_practice`)

**Context Sources:**

- **Analysis Engine (V3 Code):** `07.python_practice/v3/` (Contains `DataManager_v3.py`, `sector_dashboard_v3.py`, `stock_analyzers_v3.py` - Source of signals).
- **Rules of Engagement (Concepts):** `04.concepts/` (Strict logic for Risk, Exits, and Timing).
- **API Reference:** `03.zerodha_docs_python/` (Official KiteConnect documentation).
- **API Experiments:** `07.python_practice/zerodha_tests/` (Real-world API output samples).
  - _Note: If specific API response structures are missing in `zerodha_tests`, consult `03.zerodha_docs_python`._
- **Universe Definition:** `config/universe.json` (Single source of truth for indices/stocks).

We will use a flattened, modular structure with `_v4` suffix.

### A. Configuration & Data (`core_v4`)

- `config_v4.py`: Central repository for ALL constants (Time windows, Risk % (0.35), Thresholds, Universe paths).
- `data_v4.py`: Unified Data Handler.
  - Manages Zerodha connection.
  - Fetches Instruments/Quotes/History.
  - **Improvement over V3:** Optimized caching for execution speed, lighter objects.

### B. Analysis Engine (`analysis_v4`)

- `indicators_v4.py`: Pure math functions (ATR, HMA, StochRSI, RVOL).
  - _Rewrite of `stock_analyzers_v3.py` but cleaner/stateless._
- `strategy_v4.py`: The Logic Core.
  - Sector Ranking Algorithm (5-factor score).
  - Stock Grading (A+/A/B/C) & Signaling.
  - ORB & Microstructure Gate logic.
  - _Rewrite of logic from `sector_dashboard_v3.py`._

### C. Execution Engine (`execution_v4`)

- `risk_v4.py`: The Gatekeeper.
  - Calculates Position Size based on Grade/VIX/DayState.
  - Enforces Portfolio Limits (Max 6, Max 2/Sector).
  - Tracks Drawdowns & Kill Switches.
- `orders_v4.py`: The Interface to Exchange.
  - Abstracts Zerodha API.
  - **Paper Trading Only:** Simulates order fills, slippage, and rejections. (No real capital risk).
  - Simulates LIMIT entries and SL-M stops.
- `lifecycle_v4.py`: The Manager.
  - State Machine for Trades: `PENDING` → `ACTIVE` → `PARTIAL` → `CLOSED`.
  - Handles Two-Stage Exit (1.5R target).
  - Updates Trailing Stops (Chandelier).
  - Manages 15:05 Force Exit.

### D. System & UI (`system_v4`)

- `state_v4.py`: Persistence Layer.
  - Saves/Loads `trades.json` and `daily_stats.json`.
  - Reconstructs bot state on startup.
- `ui_v4.py`: The Interface.
  - **Header:** Session Timer, Global P&L, VIX Status, Nifty.
  - **Left Panel (Scanner):** Top Sectors, Tradeable Stocks (Grade A+/A).
  - **Right Panel (Portfolio):** Active Positions (P&L, R-multiple), Pending Orders.
  - **Bottom Panel:** Scrolling Log (Signals, Rejections, Fills).
- `main_v4.py`: The Orchestrator.
  - Main Event Loop.
  - Coordinates: `Data -> Strategy -> Signal -> Risk -> Execution -> UI`.

---

## 3. Reference Material (Strict Adherence)

1.  **Concepts (The Rules):** `04.concepts/`
    - _Timing:_ 09:20-09:34 (OR), 09:35-10:05 (ORB), 10:10-14:05 (Main).
    - _Risk:_ 0.35% Base Risk.
    - _Grading:_ HMA 3-layer + StochRSI + RVOL.
2.  **Instrument Source:** `config/universe.json` (Indices & Stocks).
3.  **API Knowledge:** `07.python_practice/zerodha_tests/` (Output formats).

---

## 4. Development Stages (Prompt Sequence)

### Phase 1: The Skeleton & Core Logic

- Create `config_v4.py` and `data_v4.py`.
- Implement `indicators_v4.py` and `strategy_v4.py`.
- _Goal:_ We can connect, fetch data, and generate valid signals/grades (A+/A) independently of V3.

### Phase 2: The Execution Layer

- Implement `risk_v4.py` (Calculations & Limits).
- Implement `orders_v4.py` (Paper Trading Logic).
- Implement `lifecycle_v4.py` (The State Machine).
- _Goal:_ We can take a signal, size it, "place" a paper order, and manage its lifecycle stops/targets.

### Phase 3: The System & UI

- Implement `state_v4.py` (Save/Load).
- Implement `ui_v4.py` (Rich Layout).
- Implement `main_v4.py` (Integration).
- _Goal:_ A running bot that scans market, places paper trades, updates UI, and saves state.

### Phase 4: System Hardening (Simulated Production)

- Flash Crash & VIX Spike Monitors (Triggering system-wide Paper stop-outs).
- Error Handling (Network/API simulation).
- _Note: Live/Real API Mode switch is reserved for V5._

---

## 5. Next Action

The user will now prompt for **Phase 1**.
We will begin by creating the folder structure and the foundational `config` and `data` modules.
