"""
================================================================================
V6 BRAIN MODULE
================================================================================
Decision Engine: Strategy, Risk, and Safety combined.

MERGED FROM V5:
- analysis_v5/strategy_v5.py → MarketRegimeDetector, SectorScorer, StockGrader, ExecutionFilters
- execution_v5/risk_v5.py → RiskManager
- system_v5/safety_v5.py → SafetyMonitor

Author: Sector Analysis System
Version: 6.0.0
================================================================================
"""

import logging
import numpy as np
from collections import deque
from datetime import datetime, time
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

from v6 import config

logger = logging.getLogger("BrainV6")


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SectorScore:
    """Sector ranking and bias information."""
    symbol: str
    price: float = 0.0
    change_pct: float = 0.0  # Daily Change (vs Prev Close)
    structural_rs: float = 0.0
    shortterm_rs: float = 0.0
    intraday_rs: float = 0.0  # Daily RS (vs Prev Close)
    breadth: float = 0.0  # Net Breadth (-1.0 to 1.0)
    composite_score: float = 0.0
    rank: int = 0
    bias: str = "NEUTRAL"  # LONG, SHORT, NEUTRAL
    is_selected: bool = False


@dataclass
class StockSignal:
    """Stock signal with grade and trade direction."""
    symbol: str
    sector: str
    price: float = 0.0
    change_pct: float = 0.0  # Daily Change (vs Prev Close)
    hma_align: str = ""
    rvol: float = 0.0
    stoch_k: float = 0.0
    sector_rank: int = 0
    spread_atr: float = 0.0
    grade: str = ""  # A+, A, B, C
    multiplier: float = 0.0
    direction: str = ""  # LONG, SHORT, NONE
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    gate_passed: bool = False
    gate_reason: str = ""


@dataclass
class AccountState:
    """Current account state for risk management."""
    equity: float
    daily_start_equity: float
    current_pnl: float = 0.0
    open_positions_count: int = 0
    sector_exposure: Dict[str, int] = field(default_factory=dict)
    symbol_exposure: Dict[str, int] = field(default_factory=dict)
    active_symbols: List[str] = field(default_factory=list)


@dataclass
class SizingResult:
    """Position sizing calculation result."""
    shares: int
    risk_amount: float
    risk_per_share: float
    effective_risk_pct: float
    is_allowed: bool
    reason: str


# ══════════════════════════════════════════════════════════════════════════════
# SAFETY MONITOR (Kill Switch)
# ══════════════════════════════════════════════════════════════════════════════

class SafetyMonitor:
    """
    Monitors for extreme market events and triggers halts.
    - Flash Crash: Nifty drop > 3% in 5m
    - VIX Spike: > 15% in 5m
    - Breadth Collapse: > 70% Sector stocks red
    """
    
    def __init__(self):
        # Time-series buffers for spike detection (5-min windows @ 1 sec resolution)
        self.nifty_history = deque(maxlen=300)
        self.vix_history = deque(maxlen=300)
        
        self.is_halted = False
        self.halt_reason = ""

    def update(self, nifty_ltp: float, vix_ltp: float, red_stock_pct: float):
        """Feed current values into safety buffers and check triggers."""
        now = datetime.now()
        self.nifty_history.append((now, nifty_ltp))
        self.vix_history.append((now, vix_ltp))
        
        # 1. Flash Crash Detection (Nifty)
        if len(self.nifty_history) > 10:
            start_val = self.nifty_history[0][1]
            if start_val > 0:
                drop = (nifty_ltp - start_val) / start_val
                if drop <= -0.03:  # -3%
                    self._trigger_halt(f"FLASH_CRASH (Nifty drop {drop:.2%})")

        # 2. VIX Spike Detection
        if len(self.vix_history) > 10:
            start_vix = self.vix_history[0][1]
            if start_vix > 0:
                spike = (vix_ltp - start_vix) / start_vix
                if spike >= 0.15:  # +15%
                    self._trigger_halt(f"VIX_SPIKE (VIX up {spike:.2%})")

        # 3. Breadth Collapse
        if red_stock_pct >= 0.70:  # 70% red
            self._trigger_halt(f"BREADTH_COLLAPSE ({red_stock_pct:.0%})")

    def _trigger_halt(self, reason: str):
        """Trigger system halt."""
        if not self.is_halted:
            self.is_halted = True
            self.halt_reason = reason
            logger.critical(f"🛑 SYSTEM HALT TRIGGERED: {reason}")

    def check_force_exit(self, current_time: time) -> bool:
        """Binary check for 15:05 cutoff."""
        return current_time >= config.FORCE_EXIT_TIME


# ══════════════════════════════════════════════════════════════════════════════
# MARKET REGIME DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

class MarketRegimeDetector:
    """Detects market regime based on VIX 20-day percentile."""
    
    @staticmethod
    def calculate_percentile(current_vix: float, vix_history: List[float]) -> float:
        """Calculate current VIX percentile vs 20-day history."""
        if not vix_history:
            return 50.0
        
        window = vix_history[-20:]
        if not window:
            return 50.0
            
        count_below = sum(1 for v in window if v < current_vix)
        return (count_below / len(window)) * 100

    @staticmethod
    def get_regime(vix_pctl: float) -> str:
        """Classify regime: TRENDING, NEUTRAL, MEAN_REVERT, EXTREME."""
        if vix_pctl >= config.VIX_PCTL_EXTREME_THRESHOLD:
            return "EXTREME"
        elif vix_pctl >= config.VIX_PCTL_HIGH_THRESHOLD:
            return "MEAN_REVERT"
        elif vix_pctl <= config.VIX_PCTL_LOW_THRESHOLD:
            return "TRENDING"
        else:
            return "NEUTRAL"

    @staticmethod
    def get_vix_multiplier(vix_pctl: float) -> float:
        """Get position size multiplier based on VIX percentile."""
        if vix_pctl >= config.VIX_PCTL_EXTREME_THRESHOLD:
            return config.VIX_MULT_EXTREME
        elif vix_pctl >= config.VIX_PCTL_HIGH_THRESHOLD:
            return config.VIX_MULT_HIGH
        elif vix_pctl > 50:
            return config.VIX_MULT_ELEVATED
        elif vix_pctl > config.VIX_PCTL_LOW_THRESHOLD:
            return config.VIX_MULT_NORMAL
        else:
            return config.VIX_MULT_LOW


# ══════════════════════════════════════════════════════════════════════════════
# SECTOR SCORER
# ══════════════════════════════════════════════════════════════════════════════

class SectorScorer:
    """
    Ranks sectors by Absolute Momentum (Trend Intensity).
    Sorts by Magnitude of Score, allowing Strong Bears to rank alongside Strong Bulls.
    """
    
    def __init__(self):
        self.weights = config.SECTOR_WEIGHTS

    def score_all(self, sectors: List[SectorScore], regime: str, nifty_pct: float = 0.0) -> List[SectorScore]:
        """
        Calculate composite scores, ranks, and bias for all sectors.
        Input: List of SectorScore with raw metrics (RS values and Net Breadth).
        Output: Same list with composite_score, rank, and bias populated.
        """
        if not sectors:
            return []
        
        # Calculate Composite Score
        for s in sectors:
            raw_score = 0.0
            raw_score += s.structural_rs * self.weights["structural"]
            raw_score += s.shortterm_rs * self.weights["shortterm"]
            raw_score += s.intraday_rs * self.weights["intraday"]
            raw_score += s.breadth * self.weights["breadth"]
            raw_score += nifty_pct * self.weights["nifty"]  # Market Gravity
            
            s.composite_score = raw_score
            
            # Determine Bias based on Score Thresholds
            if s.composite_score >= 10.0:
                s.bias = "LONG"
            elif s.composite_score <= -10.0:
                s.bias = "SHORT"
            else:
                s.bias = "NEUTRAL"

        # Sort by MAGNITUDE of Score (Absolute Value)
        ranked = sorted(sectors, key=lambda x: abs(x.composite_score), reverse=True)
        
        for i, s in enumerate(ranked, 1):
            s.rank = i
            
        return ranked

    def select_top_n(self, ranked_sectors: List[SectorScore]) -> List[str]:
        """Select Top N sectors regardless of direction."""
        for s in ranked_sectors:
            s.is_selected = False

        if not ranked_sectors:
            return []
        
        # Dynamic N logic based on Score Magnitude Spread
        if len(ranked_sectors) >= 5:
            spread = abs(ranked_sectors[0].composite_score) - abs(ranked_sectors[4].composite_score)
            n = 3 if spread >= config.SECTOR_TOP_N_SPREAD else 5
        else:
            n = len(ranked_sectors)
        
        selected = []
        for i in range(min(n, len(ranked_sectors))):
            if ranked_sectors[i].bias != "NEUTRAL":
                ranked_sectors[i].is_selected = True
                selected.append(ranked_sectors[i].symbol)
            
        return selected


# ══════════════════════════════════════════════════════════════════════════════
# STOCK GRADER
# ══════════════════════════════════════════════════════════════════════════════

class StockGrader:
    """Grades stocks A+ to C based on technical alignment and microstructure."""
    
    @staticmethod
    def get_direction(hma_align: str) -> str:
        """Maps HMA alignment to trade direction."""
        if hma_align == "BULLISH":
            return "LONG"
        if hma_align == "BEARISH":
            return "SHORT"
        return "NONE"

    def calculate_grade(self, 
                        hma_align: str, 
                        rvol: float, 
                        stoch_k: float, 
                        sector_rank: int, 
                        spread_atr: float,
                        playbook: str,
                        vix_pctl: float) -> StockSignal:
        """Comprehensive signal grading."""
        reasons = []
        direction = self.get_direction(hma_align)
        
        # 1. Immediate Disqualifiers (Grade C)
        # RVOL Check
        rvol_threshold = self._get_rvol_threshold(playbook, vix_pctl)
        if rvol < rvol_threshold:
            return StockSignal(
                symbol="", sector="", grade="C", direction=direction, 
                reasons=[f"RVOL {rvol:.2f} < {rvol_threshold}"],
                hma_align=hma_align, rvol=rvol, stoch_k=stoch_k,
                sector_rank=sector_rank, spread_atr=spread_atr
            )
        
        # StochRSI Divergence
        if direction == "LONG" and stoch_k > 80:
            return StockSignal(
                symbol="", sector="", grade="C", direction=direction,
                reasons=["StochRSI Overbought vs Long"],
                hma_align=hma_align, rvol=rvol, stoch_k=stoch_k,
                sector_rank=sector_rank, spread_atr=spread_atr
            )
        if direction == "SHORT" and stoch_k < 20:
            return StockSignal(
                symbol="", sector="", grade="C", direction=direction,
                reasons=["StochRSI Oversold vs Short"],
                hma_align=hma_align, rvol=rvol, stoch_k=stoch_k,
                sector_rank=sector_rank, spread_atr=spread_atr
            )

        # 2. Scoring (0-10)
        score = 0.0
        
        # HMA (3 pts)
        if hma_align in ["BULLISH", "BEARISH"]:
            score += config.POINTS_HMA
            reasons.append("HMA Fully Aligned")
        else:
            score += 1
            reasons.append("HMA Mixed")
            
        # Volume (2 pts)
        if rvol >= rvol_threshold + 0.3:
            score += config.POINTS_RVOL
            reasons.append(f"Strong RVOL ({rvol:.2f})")
        else:
            score += 1
            reasons.append("Adequate RVOL")
            
        # StochRSI Confirmation (2 pts)
        if (direction == "LONG" and stoch_k < 20) or (direction == "SHORT" and stoch_k > 80):
            score += config.POINTS_STOCH
            reasons.append("StochRSI Extreme Confirmation")
        elif 20 <= stoch_k <= 80:
            score += 1
            reasons.append("StochRSI Neutral")
            
        # Sector (2 pts)
        if sector_rank <= 3:
            score += config.POINTS_SECTOR_RANK
            reasons.append(f"Top 3 Sector (Rank {sector_rank})")
        elif sector_rank <= 5:
            score += 1
            reasons.append(f"Top 5 Sector (Rank {sector_rank})")
            
        # Spread Quality (1 pt)
        gate_limit = config.STRICT_SPREAD_ATR_LIMIT if playbook == "ORB" else config.NORMAL_SPREAD_ATR_LIMIT
        if spread_atr < gate_limit * 0.5:
            score += config.POINTS_SPREAD
            reasons.append("Superior Spread Quality")

        # 3. Final Grade Assignment
        if score >= config.THRESHOLD_A_PLUS:
            grade = "A+"
        elif score >= config.THRESHOLD_A:
            grade = "A"
        elif score >= config.THRESHOLD_B:
            grade = "B"
        else:
            grade = "C"
        
        return StockSignal(
            symbol="", 
            sector="", 
            grade=grade, 
            multiplier=config.GRADE_MULTIPLIERS[grade], 
            direction=direction, 
            score=score, 
            reasons=reasons,
            hma_align=hma_align,
            rvol=rvol,
            stoch_k=stoch_k,
            sector_rank=sector_rank,
            spread_atr=spread_atr
        )

    def _get_rvol_threshold(self, playbook: str, vix_pctl: float) -> float:
        """Get RVOL threshold based on playbook and VIX percentile."""
        thresholds = config.RVOL_THRESHOLDS_ORB if playbook == "ORB" else config.RVOL_THRESHOLDS_MAIN
        for max_pctl, val in thresholds:
            if vix_pctl <= max_pctl:
                return val
        return 1.5


# ══════════════════════════════════════════════════════════════════════════════
# EXECUTION FILTERS
# ══════════════════════════════════════════════════════════════════════════════

class ExecutionFilters:
    """Microstructure gate and liquidity checks."""
    
    @staticmethod
    def check_gate(playbook: str, 
                   bid: float, 
                   ask: float, 
                   price: float, 
                   atr: float, 
                   u_circuit: float, 
                   l_circuit: float) -> Tuple[bool, str]:
        """Binary pass/fail microstructure check."""
        if price <= 0:
            return False, "INVALID_PRICE"
        if atr <= 0:
            return False, "INVALID_ATR"
        if bid <= 0 or ask <= 0:
            return False, "NO_DEPTH"

        # 1. Spread/ATR Ratio
        spread = ask - bid
        ratio = spread / atr
        limit = config.STRICT_SPREAD_ATR_LIMIT if playbook == "ORB" else config.NORMAL_SPREAD_ATR_LIMIT
        
        if ratio > limit:
            return False, f"SPREAD_ATR_{ratio:.2%}_>_{limit:.0%}"
            
        # 2. Circuit Buffer
        if u_circuit > 0 and l_circuit > 0:
            dist_u = (u_circuit - price) / price
            dist_l = (price - l_circuit) / price
            buffer = min(dist_u, dist_l)
            min_buffer = config.STRICT_CIRCUIT_BUFFER if playbook == "ORB" else config.NORMAL_CIRCUIT_BUFFER
            
            if buffer < min_buffer:
                return False, f"CIRCUIT_BUFFER_{buffer:.2%}_<_{min_buffer:.0%}"
                
        return True, "PASS"

    @staticmethod
    def calculate_adv_crores(closes: np.ndarray, volumes: np.ndarray) -> float:
        """
        Calculate 20-day Average Daily Value in Crores.
        Uses Numpy arrays for performance.
        """
        if len(closes) < 20 or len(volumes) < 20:
            return 0.0
        
        c_win = closes[-20:]
        v_win = volumes[-20:]
        daily_values = c_win * v_win
        avg_val = np.mean(daily_values)
        
        return float(avg_val / 10_000_000)  # 1 Crore = 10^7


# ══════════════════════════════════════════════════════════════════════════════
# RISK MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class RiskManager:
    """
    The Gatekeeper. Enforces:
    - Position Sizing (Grade, VIX, DayState)
    - Portfolio Limits (Max 6, Max 2/Sector, Max/Symbol)
    - Kill Switches (Daily Drawdown)
    """
    
    def __init__(self):
        self.state = AccountState(equity=0.0, daily_start_equity=0.0)
        self.kill_switch_active = False
        self.kill_switch_reason = ""

    def update_account(self,
                       equity: float,
                       pnl: float,
                       positions: List[Dict],
                       symbol_exposure: Optional[Dict[str, int]] = None,
                       sector_exposure: Optional[Dict[str, int]] = None):
        """Update account state from Broker/Paper Broker."""
        self.state.equity = equity
        self.state.current_pnl = pnl

        self.state.symbol_exposure.clear()
        if symbol_exposure is not None:
            for sym, count in symbol_exposure.items():
                if count > 0:
                    self.state.symbol_exposure[sym] = int(count)
        else:
            for p in positions:
                sym = p.get('symbol')
                if not sym:
                    continue
                self.state.symbol_exposure[sym] = self.state.symbol_exposure.get(sym, 0) + 1

        if symbol_exposure is not None:
            self.state.open_positions_count = sum(self.state.symbol_exposure.values())
        else:
            self.state.open_positions_count = len(positions)

        self.state.active_symbols = list(self.state.symbol_exposure.keys())

        self.state.sector_exposure.clear()
        if sector_exposure is not None:
            for sec, count in sector_exposure.items():
                if count > 0:
                    self.state.sector_exposure[sec] = int(count)
        else:
            for p in positions:
                sector = p.get('sector', 'UNKNOWN')
                self.state.sector_exposure[sector] = self.state.sector_exposure.get(sector, 0) + 1

    def check_kill_switches(self, current_vix_pctl: float) -> Tuple[bool, str]:
        """
        Check 5-Layer Risk Architecture (Layer 5: System).
        Returns (is_halted, reason).
        """
        # Daily Drawdown (-2.0%)
        if self.state.daily_start_equity > 0:
            daily_dd = (self.state.equity - self.state.daily_start_equity) / self.state.daily_start_equity
            if daily_dd <= config.DAILY_DRAWDOWN_HALT_PCT:
                self.kill_switch_active = True
                self.kill_switch_reason = f"DAILY_DD_HALT ({daily_dd:.2%})"
                return True, self.kill_switch_reason

        self.kill_switch_active = False
        return False, "OK"

    def can_open_new_trade(self, symbol: str, sector: str) -> Tuple[bool, str]:
        """Check Portfolio Constraints (Layer 4)."""
        if self.kill_switch_active:
            return False, f"KILL_SWITCH: {self.kill_switch_reason}"

        # Max Positions
        if self.state.open_positions_count >= config.MAX_CONCURRENT_POSITIONS:
            return False, f"MAX_POSITIONS ({self.state.open_positions_count})"

        # Max Per Sector
        current_sector_count = self.state.sector_exposure.get(sector, 0)
        if current_sector_count >= config.MAX_POSITIONS_PER_SECTOR:
            return False, f"MAX_SECTOR_LIMIT ({sector}: {current_sector_count})"

        # Max Per Symbol (configurable)
        current_symbol_count = self.state.symbol_exposure.get(symbol, 0)
        if current_symbol_count >= config.MAX_POSITIONS_PER_STOCK:
            return False, f"MAX_STOCK_LIMIT ({symbol}: {current_symbol_count})"

        return True, "OK"

    def calculate_position_size(self, 
                                entry_price: float, 
                                stop_price: float, 
                                grade: str, 
                                vix_multiplier: float,
                                current_time: time) -> SizingResult:
        """
        Calculate Share Count based on Risk Factors (Layer 1).
        Formula: Size = (Equity * 0.35% * Multipliers) / (Entry - Stop)
        """
        risk_per_share = abs(entry_price - stop_price)
        if risk_per_share == 0:
            return SizingResult(0, 0.0, 0.0, 0.0, False, "ZERO_STOP_WIDTH")
        
        if self.state.equity <= 0:
            return SizingResult(0, 0.0, risk_per_share, 0.0, False, "ZERO_EQUITY")

        # 1. Base Risk
        base_risk_amount = self.state.equity * config.BASE_RISK_PER_TRADE_PCT

        # 2. Grade Multiplier
        grade_mult = config.GRADE_MULTIPLIERS.get(grade, 0.0)
        if grade_mult == 0.0:
            return SizingResult(0, 0.0, 0.0, 0.0, False, f"GRADE_{grade}_NO_TRADE")

        # 3. Day State Multiplier
        day_mult = 1.0
        # Lunch Lull (12:00 - 13:15) -> 70%
        if config.LUNCH_START_TIME <= current_time <= config.LUNCH_END_TIME:
            day_mult = config.RISK_MULT_LUNCH
        # Daily DD Warning (-1%) -> 50%
        if self.state.daily_start_equity > 0:
            daily_dd = (self.state.equity - self.state.daily_start_equity) / self.state.daily_start_equity
            if daily_dd <= config.DAILY_DRAWDOWN_WARNING_PCT:
                day_mult = config.RISK_MULT_WARNING

        # 4. Total Multiplier
        total_mult = grade_mult * vix_multiplier * day_mult
        
        # 5. Final Calculation
        risk_amount = base_risk_amount * total_mult
        shares = int(risk_amount / risk_per_share)
        effective_risk_pct = risk_amount / self.state.equity if self.state.equity > 0 else 0.0

        if shares < 1:
            debug_msg = (
                f"REJECT: Eq={self.state.equity:.0f}, Base={base_risk_amount:.0f}, "
                f"Mult={total_mult:.2f}, RiskAmt={risk_amount:.2f}, "
                f"StopDist={risk_per_share:.2f}"
            )
            logger.info(debug_msg)
            return SizingResult(0, 0.0, risk_per_share, effective_risk_pct, False, "RISK_TOO_LOW_FOR_1_SHARE")

        return SizingResult(
            shares=shares,
            risk_amount=risk_amount,
            risk_per_share=risk_per_share,
            effective_risk_pct=effective_risk_pct,
            is_allowed=True,
            reason=f"OK (Mult: {total_mult:.2f}x)"
        )
