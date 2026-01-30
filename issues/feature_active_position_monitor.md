# Feature Proposal: Active Position Monitor (APM)

## 1. The Concept: "Flight Cockpit" vs. "Accounting Ledger"

The current Portfolio table acts as an **Accounting Ledger** (tracking entry, quantity, and P&L). While necessary for record-keeping, it is insufficient for **active trade management**.

The **Active Position Monitor (APM)** is designed as a **Flight Cockpit**. It focuses on the "Technical Health" of an open trade in real-time. Instead of asking "How much am I up?", it asks "Is the trend still strong enough to stay?"

## 2. The Monitoring Metrics (Proposed Columns)

| Column           | Header   | Formula / Logic             | Why It Matters                                                                                                           |
| :--------------- | :------- | :-------------------------- | :----------------------------------------------------------------------------------------------------------------------- |
| **Trend Dist**   | `Dist%`  | `(LTP - Stop) / LTP`        | **Safety Buffer.** Measures how close the price is to your exit. If this shrinks fast, the trend is reversing.           |
| **Sector Pulse** | `SecS`   | Real-time `SectorScore`     | **The Wind.** If you are Long Auto, but the Auto Sector Score drops from +20 to +5, your "Macro" support is evaporating. |
| **Momentum**     | `Stoch`  | Current StochRSI K          | **The Gas.** Is the stock pegged at 80+ (Strong) or crossing below 80 (Exhaustion)?                                      |
| **Volume Power** | `RVOL-L` | `Live 5m Vol / Avg 5m Vol`  | **The Fuel.** Is volume still backing the move, or is it drying up on the way up?                                        |
| **Rel Strength** | `RS-5m`  | `Stock% (5m) - Nifty% (5m)` | **The Race.** Is your stock outperforming the market _right now_?                                                        |
| **Trade Health** | `Health` | Composite Grade (A/B/C)     | **The Decision.** A simplified status for quick decision making.                                                         |

---

## 3. The "Health" Algorithm (Trade Scoring)

Every active position will be assigned a **Health Score (0-100)** refreshed every 5 seconds.

| Metric       | Condition (for Long) | Points |
| :----------- | :------------------- | :----- |
| **VWAP**     | Price > VWAP         | 20 pts |
| **Sector**   | Sector Score > 10    | 20 pts |
| **Momentum** | StochRSI K > 60      | 20 pts |
| **Volume**   | RVOL-Live > 1.0      | 20 pts |
| **HMA**      | Price > HMA(20) [5m] | 20 pts |

**Visual Status:**

- **80 - 100:** 🟢 **STRONG** (Hold and relax)
- **50 - 79:** 🟡 **WEAK** (Tighten stops / Prepare to exit)
- **< 50:** 🔴 **CRITICAL** (Exit manually or at first sign of reversal)

---

## 4. Implementation Strategy

### Phase 1: Data Granularity (`v6/data_engine.py`)

To calculate `RVOL-L` (Live RVOL), we need to track the volume of the _current_ incomplete 5-minute candle.

- **Task:** Store a `volume_snapshot` at the start of every 5-minute bar.
- **Calculation:** `Current Bar Vol` = `WebSocket Total Vol` - `Snapshot Vol`.

### Phase 2: Scoring Engine (`v6/brain.py`)

Create a `TradeHealthMonitor` class.

- **Task:** This class will take a `StockSignal` object and the current `AccountState` to generate the 0-100 Health Score.

### Phase 3: Orchestration (`v6/main.py`)

Modify the main loop to handle active metrics separately from the scanner.

- **Current:** Bot scans potential trades -> Grades them.
- **New:** Bot scans active trades -> Updates Health -> Decides on "Early Exit" if Health is CRITICAL.

### Phase 4: UI Development (`v6/main.py - DashboardUI`)

Create a dedicated panel for APM.

- **Task:** If `open_positions > 0`, the UI should prioritize the APM table over the standard scanner or merge them into a "Unified Cockpit."

---

## 5. Mockup UI View

```text
+-----------------------------------------------------------------------------+
| 🛰️  ACTIVE POSITION COCKPIT (REAL-TIME)                                    |
+-------+------+-------+-------+-------+-------+-------+--------+-------------+
| Sym   | Side | P&L%  | Dist% | SecS  | Stoch | RVOL  | RS-5m  | Health      |
+-------+------+-------+-------+-------+-------+-------+--------+-------------+
| RELI  | LONG | +1.2% | 0.8%  | +18.5 | 92    | 2.2x  | +0.15  | 🟢 STRONG   |
| TATA  | LONG | -0.1% | 0.1%  | +05.2 | 45    | 0.7x  | -0.08  | 🔴 CRITICAL |
| SBIN  | LONG | +0.4% | 0.5%  | +12.1 | 72    | 1.1x  | +0.02  | 🟡 WEAK     |
+-------+------+-------+-------+-------+-------+-------+--------+-------------+
```

## 6. Next Steps

1.  **Refactor Metric Calculation:** Extract "Point Scoring" logic into a reusable function that can be applied to both Scanned Stocks and Active Stocks.
2.  **Volume Snapshoting:** Implement the 5-minute volume snapshot in `data_manager`.
3.  **UI Prototype:** Add the `generate_active_monitor` method to `DashboardUI`.
