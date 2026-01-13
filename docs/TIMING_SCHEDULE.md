# V4 Trading Bot - Time Schedule Reference

## Overview

This document provides a complete breakdown of all trading timings used in the V4 Trading Bot system. All times are in **Indian Standard Time (IST)**.

---

## Time Schedule Table

| Time          | Phase        | New Entries         | Existing Trades | Notes                              |
| ------------- | ------------ | ------------------- | --------------- | ---------------------------------- |
| 09:15 - 09:20 | Pre-Market   | ❌ No               | ✅ Active       | Market just opened, wait period    |
| 09:20 - 09:34 | OR Formation | ❌ No               | ✅ Active       | Building opening range             |
| 09:35 - 10:05 | **ORB**      | ✅ **YES** (Strict) | ✅ Active       | Aggressive entries, strict filters |
| 10:05 - 10:10 | Gap Period   | ❌ No               | ✅ Active       | No new entries                     |
| 10:10 - 12:00 | Main Session | ✅ YES (Normal)     | ✅ Active       | Normal trading resumes             |
| 12:00 - 13:15 | Lunch Lull   | ✅ YES              | ✅ Active       | 70% sizing, no halts               |
| 13:15 - 14:05 | Main Session | ✅ YES              | ✅ Active       | Normal trading                     |
| 14:05 - 15:05 | Exit Only    | ❌ No               | ✅ Active       | Close only, no new                 |
| 15:05 - 15:30 | Force Exit   | ❌ No               | ⚠️ Closing      | Hard square-off triggered          |
| 15:30+        | Market Close | ❌ No               | ❌ Closed       | All positions closed               |

---

## Summary Statistics

| Category                 | Time Window   | Duration |
| ------------------------ | ------------- | -------- |
| **Total Trading Day**    | 09:15 - 15:30 | 6h 15m   |
| **Active Entry Windows** | 09:35 - 14:05 | 4h 55m   |
| **ORB (Strict)**         | 09:35 - 10:05 | 30 min   |
| **Main (Normal)**        | 10:10 - 14:05 | 3h 55m   |
| **No Entry Periods**     | Multiple      | 1h 20m   |
| **Forced Exit Begins**   | 15:05         | -        |

---

## Phase Details

### 1. Pre-Market (09:15 - 09:20)

- Market has just opened
- Bot enters "wait period"
- No new trade entries
- System initializes data feeds

### 2. OR Formation (09:20 - 09:34)

- Opening Range is being established
- System calculates OR high and OR low
- No new entries allowed
- Preparing for ORB playbook

### 3. ORB - Opening Range Breakout (09:35 - 10:05)

- **Primary entry window**
- Strict microstructure filters applied:
  - Spread/ATR limit: 15%
  - Higher RVOL threshold (1.8x at low VIX)
  - Wider stop loss (2.4 ATR)
  - Circuit buffer: 3%
- Most aggressive trading phase

### 4. Gap Period (10:05 - 10:10)

- Transition period between ORB and Main
- No new entries allowed
- Existing trades continue to be monitored

### 5. Main Session (10:10 - 12:00)

- Normal trading resumes
- Standard filters applied:
  - Spread/ATR limit: 25%
  - Normal RVOL threshold (1.5x at low VIX)
  - Standard stop loss (2.0 ATR)
  - Circuit buffer: 2%

### 6. Lunch Lull (12:00 - 13:15)

- Reduced trading activity period
- Position sizing reduced to 70%
- No trading halt - entries still allowed
- Risk management is more conservative

### 7. Main Session (13:15 - 14:05)

- Afternoon normal trading
- Standard filters continue
- Last window for new entries before Exit Only phase

### 8. Exit Only (14:05 - 15:05)

- No new entries allowed
- Focus on managing existing positions
- Target exits, trailing stops active

### 9. Force Exit (15:05 - 15:30)

- **Hard square-off triggered at 15:05**
- All remaining positions closed at market price
- No exceptions - guaranteed exit
- Trading day ends

### 10. Market Close (15:30+)

- NSE market closed
- All positions should be flat
- State saved for next trading day

---

## Entry/Exit Windows Visualization

```
09:15 ───┬─── Pre-Market (wait)
         │
09:20 ───┼─── OR Formation (build range)
         │
09:35 ───┼─────────────────────┐ ORB (30 min - strict)
         │                     │
10:05 ───┼─── Gap (no entries)─┘
         │
10:10 ───┼─────────────────────────────────────────┐ Main (normal)
         │                                         │
12:00 ───┼─── Lunch (70% size)─────────────────────┤
         │                                         │
13:15 ───┼─────────────────────────────────────────┤
         │                                         │
14:05 ───┼─────────────────────────────────────────┤ Exit Only
         │                                         │
15:05 ───┼─────────────────────────────────────────┼ FORCE EXIT
         │                                         │
15:30 ───┴─────────────────────────────────────────┘ Close
```

---

## Configuration Reference

All timing constants are defined in `core_v4/config_v4.py`:

```python
MARKET_OPEN_TIME = time(9, 15)
OR_START_TIME = time(9, 20)
OR_END_TIME = time(9, 34)
ORB_START_TIME = time(9, 35)
ORB_END_TIME = time(10, 5)
GAP_START_TIME = time(10, 5)
GAP_END_TIME = time(10, 10)
MAIN_START_TIME = time(10, 10)
MAIN_END_TIME = time(14, 5)
LUNCH_START_TIME = time(12, 0)
LUNCH_END_TIME = time(13, 15)
ENTRY_CUTOFF_TIME = time(14, 5)
FORCE_EXIT_TIME = time(15, 5)
MARKET_CLOSE_TIME = time(15, 30)
```

---

## Key Observations

1. **ORB window is short (30 min)** - Fast decision making required
2. **Gap period at 10:05** - Strategy switches, no entries allowed
3. **Lunch doesn't halt trading** - Just reduces position size to 70%
4. **Force exit is absolute** - All trades closed at 15:05
5. **Total entry window is ~5 hours** - Significant time for opportunities

---

## Current Implementation Gaps (Critical)

### ⚠️ Missing Opening Range (OR) Logic
While the **ORB Playbook** window (09:35 - 10:05) is defined in the schedule, the logic to support it is currently **incomplete**:

1.  **State Tracking**: The bot does **not** currently record the High and Low prices during the `09:20-09:34` "OR FORMATION" phase.
2.  **Breakout Signal**: Consequently, the `StockGrader` does not validate if the price has actually **broken out** of this range.
3.  **Result**: During the ORB window, the bot effectively trades a generic momentum strategy (based on HMA/RVOL) rather than a true Opening Range Breakout strategy. It will enter trades even if the price is still stuck inside the opening range.

---

## Notes

- All times are in Indian Standard Time (IST)
- The bot operates strictly in PAPER TRADING mode by default
- State persistence ensures survival across restarts
- Safety monitors run continuously regardless of phase

---

_Last Updated: January 2026_
_Version: 4.0.0_
