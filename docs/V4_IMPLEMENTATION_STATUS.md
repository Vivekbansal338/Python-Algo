# V4 Implementation Status Analysis

**Purpose**: Comprehensive analysis of V4 code implementation against 04.concepts documentation  
**Date**: 2025-01-07  
**Coverage**: ~75% Complete

---

## Executive Summary

The V4 codebase demonstrates strong architectural foundation with excellent implementation of core trading logic. Key strengths include market regime detection, sector scoring with dynamic N selection, position sizing formula, and portfolio limits.

**Critical Gaps**: ORB breakout detection, VIX spike detection, and centralized kill switch unification.

---

## Implementation Status by Concept File

### 1. Market Structure & Trading Universe (01_MARKET_AND_INDICES.md)

| Feature                           | Status      | Notes                                                               |
| --------------------------------- | ----------- | ------------------------------------------------------------------- |
| Trading Hours (09:15-15:30)       | ✅ **100%** | All timing windows defined in config_v4.py                          |
| Non-overlapping Playbooks         | ✅ **100%** | OR: 09:20-09:34, ORB: 09:35-10:05, Main: 10:10-14:05                |
| Opening Range Definition (14 min) | ✅ **100%** | Correctly implemented as 09:20-09:34                                |
| Token Validation                  | ✅ **100%** | Filters empty tokens in main_v4.py:111                              |
| ADV Filter (₹75 Cr min)           | ⚠️ **50%**  | Function exists (strategy_v4.py:388) but NOT used in stock scanning |
| Volume Pattern Awareness          | ✅ **100%** | Lunch lull sizing (0.7x) implemented                                |
| Pre-market Checklist              | ✅ **100%** | Initialization sequence follows checklist                           |

**Code Locations:**

- `config_v4.py:39-70` - All timing constants
- `main_v4.py:111` - Token filtering
- `strategy_v4.py:388-396` - ADV calculation function
- `risk_v4.py:169-178` - Lunch lull multipliers

---

### 2. Sector Analysis Engine (02_SECTOR_ANALYSIS.md)

| Feature                            | Status      | Notes                                            |
| ---------------------------------- | ----------- | ------------------------------------------------ |
| 5-Component Scoring System         | ✅ **100%** | All components implemented with correct weights  |
| Rank-Based Normalization           | ✅ **100%** | 1-16 ranking system implemented                  |
| Market Regime (VIX Percentile)     | ✅ **100%** | TRENDING/NEUTRAL/MEAN_REVERT/HALT classification |
| Regime-Adaptive Weights            | ✅ **100%** | Weight shifting based on market condition        |
| Dynamic N Selection (3-5 sectors)  | ✅ **100%** | Score spread logic: ≥15 = 3, <15 = 5             |
| Breadth Calculation (% above VWAP) | ✅ **100%** | Real-time breadth using live ticks               |
| Sector Selection Timeline          | ✅ **100%** | 15-minute recalculation in main loop             |

**Code Locations:**

- `strategy_v4.py:68-109` - MarketRegimeDetector class
- `strategy_v4.py:116-212` - SectorScorer class
- `main_v4.py:389-418` - Sector ranking logic
- `main_v4.py:598-609` - Real-time breadth calculation

**Implementation Detail:**

```python
# Regime classification (strategy_v4.py:86-95)
def get_regime(vix_pctl: float) -> str:
    if vix_pctl >= 90: return "HALT"
    elif vix_pctl >= 75: return "MEAN_REVERT"
    elif vix_pctl <= 25: return "TRENDING"
    else: return "NEUTRAL"

# Dynamic N selection (strategy_v4.py:191-212)
spread = ranked_sectors[0].composite_score - ranked_sectors[4].composite_score
n = 3 if spread >= 15.0 else 5
```

---

### 3. Stock Analysis & Trade Setups (03_STOCKS_AND_SETUPS.md)

| Feature                             | Status      | Notes                                                           |
| ----------------------------------- | ----------- | --------------------------------------------------------------- |
| Microstructure Gate (STRICT/NORMAL) | ✅ **100%** | Two modes with correct thresholds                               |
| HMA 3-Layer Alignment               | ⚠️ **75%**  | All periods present (40/16 daily, 20 5m), slope detection basic |
| Entry Type Detection                | ❌ **30%**  | ORB breakout missing, consolidation breakout missing            |
| VIX-Adaptive RVOL Thresholds        | ✅ **100%** | All percentile breakpoints implemented                          |
| Signal Grading (A+/A/B/C)           | ✅ **95%**  | All disqualifiers and scoring logic present                     |
| StochRSI Momentum Confirmation      | ✅ **100%** | Full (14,3,3) implementation                                    |
| ADV Calculation                     | ⚠️ **50%**  | Function exists but not used                                    |

**Code Locations:**

- `strategy_v4.py:347-397` - ExecutionFilters and ADV calculation
- `indicators_v4.py:29-76` - HMA calculation
- `indicators_v4.py:147-196` - StochRSI calculation
- `strategy_v4.py:219-341` - StockGrader class
- `main_v4.py:176-211` - HMA alignment check

**Implementation Details:**

**Microstructure Gate:**

```python
# strategy_v4.py:351-385
def check_gate(playbook, bid, ask, price, atr, u_circuit, l_circuit):
    # STRICT mode (ORB): spread/ATR < 0.15, circuit buffer > 3%
    # NORMAL mode (Main): spread/ATR < 0.25, circuit buffer > 2%
```

**HMA Alignment:**

```python
# main_v4.py:176-211
def _get_hma_alignment(self, sym: str, current_price: float) -> str:
    # HMA40, HMA16 from daily data
    # HMA20 from 5-minute data
    # Checks both position AND slope
```

**Missing:**

- ORB range high/low tracking (09:20-09:34)
- ORB breakout detection (price > OR_high after 09:35)
- Consolidation range detection (tight range < 1.5x ATR for 30 min)
- Consolidation breakout trigger

---

### 4. Entry, Position Sizing & Exit Management (04_ENTRY_POSITION_EXIT.md)

| Feature                      | Status      | Notes                                                      |
| ---------------------------- | ----------- | ---------------------------------------------------------- |
| Position Sizing Formula      | ✅ **95%**  | (Equity × 0.35% × Grade × VIX × DayState) / (Entry - Stop) |
| Base Risk (0.35%)            | ✅ **100%** | Single base value with multipliers                         |
| Grade Multipliers            | ✅ **100%** | A+: 1.00x, A: 0.85x, B: 0.60x, C: 0.00x                    |
| VIX Multipliers (Percentile) | ✅ **100%** | 0-20th: 1.2x, 20-50th: 1.0x, 50-75th: 0.8x, 75-90th: 0.6x  |
| Day State Multipliers        | ✅ **100%** | Lunch (0.7x), Late session (0.85x), DD warning (0.5x)      |
| ATR-Based Stops              | ✅ **85%**  | ORB: 2.4x, Pullback: 2.0x (Consolidation 1.8x missing)     |
| Two-Stage Exit (50% @ 1.5R)  | ✅ **90%**  | Partial exit + breakeven logic correct                     |
| Chandelier Exit              | ✅ **100%** | 10-bar rolling lookback (5m) implemented with 60s cache    |
| Force Exit (15:05)           | ✅ **100%** | Hard requirement implemented                               |

**Code Locations:**

- `risk_v4.py:143-198` - Position sizing calculation
- `main_v4.py:516-538` - Stop price calculation
- `lifecycle_v4.py:140-190` - Two-stage exit logic
- `lifecycle_v4.py:192-199` - Chandelier calculation

**Implementation Details:**

**Position Sizing:**

```python
# risk_v4.py:143-198
def calculate_position_size(self, entry_price, stop_price, grade, vix_multiplier, current_time):
    base_risk_amount = self.state.equity * 0.0035  # 0.35%
    grade_mult = config.GRADE_MULTIPLIERS.get(grade, 0.0)

    # Day state
    if config.LUNCH_START_TIME <= current_time <= config.LUNCH_END_TIME:
        day_mult = 0.70
    elif self.state.daily_dd <= -0.01:
        day_mult = 0.50

    total_mult = grade_mult * vix_multiplier * day_mult
    risk_amount = base_risk_amount * total_mult
    shares = int(risk_amount / (entry_price - stop_price))
```

**Two-Stage Exit:**

```python
# lifecycle_v4.py:156-190
def _check_exits(self, trade: Trade, ltp: float) -> bool:
    # Stage 1: Target 1.5R hit
    if trade.stage == "ACTIVE":
        target_hit = (direction == "LONG" and ltp >= trade.target_1)
        if target_hit:
            partial_qty = max(1, int(trade.qty * 0.5))
            self.orders.close_position(trade.symbol, partial_qty, f"{trade.id}_T1")
            trade.qty -= partial_qty
            trade.current_stop = trade.entry_price  # Move to breakeven
            trade.stage = "PARTIAL"

    # Stage 2: Chandelier trailing
    if trade.stage == "PARTIAL":
        new_stop = self._calculate_chandelier(trade)
        # Only move stop in favor of trade
        if new_stop > trade.current_stop:
            trade.current_stop = new_stop
```

**Chandelier Implementation:**

```python
# lifecycle_v4.py:192-219
def _calculate_chandelier(self, trade: Trade) -> float:
    # 1. Update Lookback Extreme (Rolling 10-bar window)
    if (now - trade.last_anchor_update).total_seconds() > 60:
        hist = data_manager.get_historical(..., "5minute")
        trade.cached_lookback_extreme = max/min(last_10_bars)

    # 2. Final Anchor (Best of Lookback vs Life-of-Trade)
    anchor = trade.cached_lookback_extreme
    if trade.direction == "LONG":
        final_anchor = max(anchor, trade.highest_price)
        return final_anchor - (trade.atr_at_entry * 3.0)
```

**Missing:**

- Consolidation breakout entry type
- Dynamic ATR update for Chandelier (currently uses entry ATR)

---

### 5. Risk Management & Kill Switches (05_RISK_AND_KILLS.md)

| Feature                                | Status      | Notes                                                            |
| -------------------------------------- | ----------- | ---------------------------------------------------------------- |
| 5-Layer Risk Architecture              | ✅ **70%**  | All layers defined, some gaps in implementation                  |
| Portfolio Limits (Max 6, Max 2/Sector) | ✅ **90%**  | Core limits correct, correlation blocking missing                |
| Correlation Blocking (0.70)            | ❌ **0%**   | Config exists but not used in risk checks                        |
| Daily Drawdown Warning (-1.0%)         | ✅ **100%** | Reduces size to 50%                                              |
| Daily Drawdown Halt (-2.0%)            | ✅ **100%** | Blocks new entries, keeps positions                              |
| VIX Halt (> 90th percentile)           | ✅ **100%** | Percentile-based halt implemented                                |
| VIX Spike Detection (>15% in 5 min)    | ❌ **0%**   | Missing completely                                               |
| Flash Crash Detection                  | ✅ **80%**  | Logic exists (Nifty drop, breadth collapse), integration unclear |
| Master Kill Switch                     | ❌ **0%**   | Individual checks exist but not unified                          |
| State Persistence (Daily)              | ✅ **100%** | Daily reset works                                                |

**Code Locations:**

- `risk_v4.py:57-199` - Portfolio limits and drawdowns
- `safety_v4.py:24-69` - Flash crash and VIX spike detection
- `state_v4.py:34-62` - State persistence and reset logic

**Implementation Details:**

**Portfolio Limits:**

```python
# config_v4.py:79-82
MAX_CONCURRENT_POSITIONS = 6
MAX_POSITIONS_PER_SECTOR = 2
MAX_POSITIONS_PER_STOCK = 1
CORRELATION_THRESHOLD = 0.70  # Configured but NOT USED

# risk_v4.py:121-141
def can_open_new_trade(self, symbol: str, sector: str) -> bool:
    if self.state.open_positions_count >= 6:
        return False, "MAX_POSITIONS (6)"

    if sector in self.state.sector_exposure:
        if self.state.sector_exposure[sector] >= 2:
            return False, "MAX_SECTOR_LIMIT"

    if symbol in self.state.active_symbols:
        return False, "ALREADY_OPEN"

    # Correlation check NOT implemented
```

**Drawdown Response:**

```python
# risk_v4.py:83-119
def check_kill_switches(self, current_vix_pctl: float) -> bool:
    # Daily (-2.0%)
    if daily_dd <= -0.02:
        return True, "DAILY_DD_HALT"

    # VIX Halt (>90th percentile)
    if current_vix_pctl >= 90:
        return True, "VIX_HALT (Pctl: 90%)"
```

**Flash Crash Detection:**

```python
# safety_v4.py:33-59
def update(self, nifty_ltp: float, vix_ltp: float, red_stock_pct: float):
    # Nifty flash crash: >3% drop in 5 minutes
    if len(self.nifty_history) > 10:
        start_val = self.nifty_history[0][1]
        drop = (nifty_ltp - start_val) / start_val
        if drop <= -0.03:
            self._trigger_halt(f"FLASH_CRASH (Nifty drop {drop:.2%})")

    # VIX spike: >15% in 5 minutes
    if len(self.vix_history) > 10:
        start_vix = self.vix_history[0][1]
        spike = (vix_ltp - start_vix) / start_vix
        if spike >= 0.15:
            self._trigger_halt(f"VIX_SPIKE (VIX up {spike:.2%})")

    # Breadth collapse: >70% red
    if red_stock_pct >= 0.70:
        self._trigger_halt(f"BREADTH_COLLAPSE ({red_stock_pct:.0%}%)")
```

**Missing:**

- Centralized master kill switch (combines all triggers)
- Correlation matrix calculation
- Integration of safety_v4 with main loop (mocked red_stock_pct)

---

## Critical Gaps - Priority Order

### HIGH PRIORITY (Blocking Core Functionality)

1. **ORB Breakout Detection** (`03_STOCKS_AND_SETUPS.md`)

   - **Status**: ❌ Missing
   - **Required**: Track OR high/low (09:20-09:34), detect breakout after 09:35
   - **Impact**: ORB playbook cannot function as designed
   - **File**: `main_v4.py` (new class needed)
   - **Estimated Effort**: 2-3 hours

2. **VIX Spike Detection Integration** (`05_RISK_AND_KILLS.md`)
   - **Status**: ❌ Missing
   - **Required**: Connect safety_v4 VIX spike check to main loop, implement recovery
   - **Impact**: No protection against sudden volatility spikes
   - **File**: `safety_v4.py` + `main_v4.py`
   - **Estimated Effort**: 1-2 hours

### MEDIUM PRIORITY (Important Features)

4. **ADV Filter Integration** (`01_MARKET_AND_INDICES.md`)

   - **Status**: ⚠️ Partial
   - **Required**: Calculate ADV, exclude stocks < ₹75 Cr in stock scanning
   - **Impact**: May trade illiquid stocks
   - **File**: `main_v4.py` line 419+
   - **Estimated Effort**: 30 minutes

5. **Chandelier 10-Bar Lookback** (`04_ENTRY_POSITION_EXIT.md`)

   - **Status**: ✅ **Complete**
   - **Implemented**: Rolling 10-bar 5m lookback with 60s caching and singleton API access.
   - **Impact**: Dynamic trailing stop that respects recent price action.

6. **Consolidation Breakout Entry** (`03_STOCKS_AND_SETUPS.md`)
   - **Status**: ❌ Missing
   - **Required**: Detect tight range < 1.5x ATR for 30 min, breakout trigger
   - **Impact**: Missing one of three entry types
   - **File**: `main_v4.py`
   - **Estimated Effort**: 2-3 hours

### LOW PRIORITY (Enhancement)

7. **Correlation Blocking** (`05_RISK_AND_KILLS.md`)

   - **Status**: ❌ Missing
   - **Required**: Calculate correlation matrix, block > 0.70
   - **Impact**: May open highly correlated positions
   - **File**: `risk_v4.py` + data layer for correlation
   - **Estimated Effort**: 4-6 hours (needs correlation calculation)

8. **Master Kill Switch Unification** (`05_RISK_AND_KILLS.md`)
   - **Status**: ❌ Missing
   - **Required**: Single class combining all triggers with priority order
   - **Impact**: Duplicate code, harder to maintain
   - **File**: New class or refactor existing
   - **Estimated Effort**: 2-3 hours

---

## Overall Assessment

### Strengths

1. **Architecture**: Excellent modular design with clear separation of concerns
2. **Core Logic**: Sector scoring, regime detection, position sizing are production-grade
3. **Code Quality**: Clean, well-documented, follows concepts closely
4. **Timing**: Perfect implementation of non-overlapping playbooks
5. **Safety**: Multiple layers of protection (drawdown, VIX, portfolio limits)

### Weaknesses

1. **Entry Types**: Only generic entry implemented, ORB and consolidation missing
2. **VIX Protection**: Spike detection exists but not integrated
3. **Integration**: Safety monitor mocked (red_stock_pct parameter not real)

### Coverage Summary

```
┌─────────────────────────────────────────────────────────────┐
│              V4 IMPLEMENTATION COVERAGE                  │
├─────────────────────────────────────────────────────────────┤
│                                                         │
│  Concept Files          ████████████████████░░░░░░ 75% │
│                                                         │
│  Market Structure        ████████████████████████████  90% │
│  Sector Analysis          ████████████████████████████  95% │
│  Stock Analysis          ████████████████████░░░░░░  70% │
│  Entry/Exit             ████████████████████░░░░░░  75% │
│  Risk & Kills           ████████████████░░░░░░░░░  65% │
│                                                         │
│  Core Trading Logic      ████████████████████████████████  90% │
│  Safety Systems         ████████████████░░░░░░░░░░  60% │
│  State Management       ████████████████░░░░░░░░░░  70% │
│                                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Recommendations

### Immediate Actions (Next Development Cycle)

1. **Implement ORB Breakout Detection**

   - Add OpeningRange class to track OR high/low
   - Integrate ORB breakout check in `_scan_tradeable_stocks()`
   - Only allow ORB entries during ORB playbook window

2. **Integrate VIX Spike Detection**
   - Connect safety_v4 VIX 5-minute history tracking to main loop
   - Implement 30-minute cooldown after spike
   - Add recovery logic (VIX must be below 90th percentile)

### Secondary Actions (Following Week)

4. **Integrate ADV Filter**

   - **Status**: ✅ **Complete**
   - **Implemented**: Numpy-based calculation in strategy_v4.py, threshold in config_v4.py (75Cr), integrated in main loop.

5. **Add Consolidation Breakout Entry**
   - Detect tight range condition (< 1.5x ATR for 30 min)
   - Trigger on breakout above range high
   - Use tighter stop (1.8x ATR)

### Long-term Actions

7. **Implement Correlation Matrix**

   - Calculate historical correlations between stocks
   - Update correlation matrix periodically
   - Add correlation check in `can_open_new_trade()`

8. **Create Master Kill Switch**

   - Unify all kill switch triggers
   - Implement priority order (Flash crash > VIX spike > VIX halt > Daily DD)
   - Single interface for all halt/recovery logic

9. **Complete State Persistence**
   - Ensure all drawdown checks work with persistent state

---

## File Structure Mapping

| Concept File              | V4 Implementation Files                      | Completeness |
| ------------------------- | -------------------------------------------- | ------------ |
| 00_INDEX.md               | All modules                                  | 100%         |
| 01_MARKET_AND_INDICES.md  | config_v4.py, main_v4.py                     | 90%          |
| 02_SECTOR_ANALYSIS.md     | strategy_v4.py                               | 95%          |
| 03_STOCKS_AND_SETUPS.md   | strategy_v4.py, indicators_v4.py, main_v4.py | 70%          |
| 04_ENTRY_POSITION_EXIT.md | risk_v4.py, lifecycle_v4.py, orders_v4.py    | 75%          |
| 05_RISK_AND_KILLS.md      | risk_v4.py, safety_v4.py, state_v4.py        | 65%          |

---

## Testing Recommendations

### Unit Tests Needed

1. `test_orb_detection.py` - ORB range tracking and breakout logic
2. `test_vix_spike.py` - Spike detection and recovery
3. `test_chandelier.py` - 10-bar lookback Chandelier logic
4. `test_adv_filter.py` - ADV calculation and exclusion

### Integration Tests Needed

1. `test_full_day_cycle.py` - Simulate complete trading day
2. `test_kill_switch_triggers.py` - All halt scenarios
3. `test_state_persistence.py` - Daily reset
4. `test_playbook_transitions.py` - All playbook timing windows

---

## Conclusion

The V4 codebase represents a strong foundation with ~75% implementation of concept specifications. Core trading logic, risk management, and architecture are well-implemented. The remaining gaps focus on edge case handling (ORB breakout, VIX spike), advanced features (correlation, consolidation entries), and operational completeness (master kill switch).

**Estimated completion time**: 15-20 hours for all gaps

**Recommendation**: Prioritize HIGH PRIORITY items (ORB breakout, VIX spike) before moving to paper trading, as these affect core trading functionality.

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-07  
**Next Review**: After ORB breakout implementation
