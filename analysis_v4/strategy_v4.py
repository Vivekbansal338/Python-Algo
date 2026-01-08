"""
================================================================================
V4 STRATEGY MODULE (THE BRAIN)
================================================================================
Implements the core decision-making logic:
- Market Regime Detection (VIX Percentile)
- Rank-Based Sector Scoring & Dynamic N Selection
- Stock Grading (A+/A/B/C)
- Microstructure Gate
- ADV Filtering

Author: Sector Analysis System
Version: 4.0.0
================================================================================
"""

import numpy as np
from datetime import time, datetime
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field

from core_v4 import config_v4 as config
from analysis_v4 import indicators_v4 as ind


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SectorScore:
    symbol: str
    price: float = 0.0
    change_pct: float = 0.0
    structural_rs: float = 0.0
    shortterm_rs: float = 0.0
    intraday_rs: float = 0.0
    breadth: float = 0.0 # Net Breadth (-1.0 to 1.0)
    composite_score: float = 0.0
    rank: int = 0
    bias: str = "NEUTRAL" # LONG, SHORT, NEUTRAL
    is_selected: bool = False


@dataclass
class StockSignal:
    symbol: str
    sector: str
    price: float = 0.0
    change_pct: float = 0.0
    hma_align: str = ""
    rvol: float = 0.0
    stoch_k: float = 0.0
    sector_rank: int = 0
    spread_atr: float = 0.0
    grade: str = "" # A+, A, B, C
    multiplier: float = 0.0
    direction: str = "" # LONG, SHORT, NONE
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    gate_passed: bool = False
    gate_reason: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# MARKET REGIME
# ══════════════════════════════════════════════════════════════════════════════

class MarketRegimeDetector:
    """Detects market regime based on VIX 20-day percentile."""
    
    @staticmethod
    def calculate_percentile(current_vix: float, vix_history: List[float]) -> float:
        """Calculate current VIX percentile vs 20-day history."""
        if not vix_history:
            return 50.0
        
        # Use last 20 elements
        window = vix_history[-20:]
        if not window:
            return 50.0
            
        count_below = sum(1 for v in window if v < current_vix)
        return (count_below / len(window)) * 100

    @staticmethod
    def get_regime(vix_pctl: float) -> str:
        """Classify regime: TRENDING, NEUTRAL, MEAN_REVERT, EXTREME."""
        if vix_pctl >= config.VIX_PCTL_HALT_THRESHOLD:
            # NOTE: Renamed from HALT to EXTREME.
            # Even in this zone, we now allow trading (at 0.75x size) 
            # but label it EXTREME to warn of panic-level volatility.
            return "EXTREME"
        elif vix_pctl >= config.VIX_PCTL_HIGH_THRESHOLD:
            return "MEAN_REVERT"
        elif vix_pctl <= config.VIX_PCTL_LOW_THRESHOLD:
            return "TRENDING"
        else:
            return "NEUTRAL"

    @staticmethod
    def get_vix_multiplier(vix_pctl: float) -> float:
        """Get position size multiplier based on VIX."""
        if vix_pctl >= config.VIX_PCTL_HALT_THRESHOLD:
            return config.VIX_MULT_HIGH # Return 0.75x instead of 0.00x
        elif vix_pctl >= config.VIX_PCTL_HIGH_THRESHOLD:
            return config.VIX_MULT_HIGH
        elif vix_pctl > 50:
            return config.VIX_MULT_ELEVATED
        elif vix_pctl > config.VIX_PCTL_LOW_THRESHOLD:
            return config.VIX_MULT_NORMAL
        else:
            return config.VIX_MULT_LOW


# ══════════════════════════════════════════════════════════════════════════════
# SECTOR SCORING (ABSOLUTE MOMENTUM)
# ══════════════════════════════════════════════════════════════════════════════

class SectorScorer:
    """
    Ranks sectors by Absolute Momentum (Trend Intensity).
    Sorts by Magnitude of Score, allowing Strong Bears to rank alongside Strong Bulls.
    """
    
    def __init__(self):
        # Weights for Composite Score
        # Balanced to ensure Intraday Flow (Breadth) can override Historical Legacy (Structural RS)
        self.weights = {
            "structural": 3.0,
            "shortterm": 10.0,
            "intraday": 20.0,
            "breadth": 40.0
        }

    def score_all(self, sectors: List[SectorScore], regime: str) -> List[SectorScore]:
        """
        Input: List of SectorScore with raw metrics (RS values and Net Breadth).
        Output: Same list with composite_score, rank, and bias populated.
        """
        if not sectors: return []
        
        # Calculate Composite Score for each sector
        # Formula: Weighted Sum of RS Metrics and Net Breadth
        # RS metrics are naturally signed (+/-).
        # Net Breadth is -1.0 to +1.0.
        
        for s in sectors:
            raw_score = 0.0
            raw_score += s.structural_rs * self.weights["structural"]
            raw_score += s.shortterm_rs * self.weights["shortterm"]
            raw_score += s.intraday_rs * self.weights["intraday"]
            raw_score += s.breadth * self.weights["breadth"] # Breadth is -1 to 1
            
            s.composite_score = raw_score
            
            # Determine Bias based on Score Thresholds
            # These thresholds might need tuning, but +/- 10 is a good starting point for strong trend
            if s.composite_score >= 10.0:
                s.bias = "LONG"
            elif s.composite_score <= -10.0:
                s.bias = "SHORT"
            else:
                s.bias = "NEUTRAL"

        # Sort by MAGNITUDE of Score (Absolute Value)
        # This puts the "loudest" sectors (Bull or Bear) at the top
        ranked = sorted(sectors, key=lambda x: abs(x.composite_score), reverse=True)
        
        for i, s in enumerate(ranked, 1):
            s.rank = i
            
        return ranked

    def select_top_n(self, ranked_sectors: List[SectorScore]) -> List[str]:
        """Select Top N sectors regardless of direction."""
        # Reset selections
        for s in ranked_sectors:
            s.is_selected = False

        if not ranked_sectors: return []
        
        # Dynamic N logic based on Score Magnitude Spread
        # Compare magnitude of Top 1 vs Top 5
        if len(ranked_sectors) >= 5:
            spread = abs(ranked_sectors[0].composite_score) - abs(ranked_sectors[4].composite_score)
            n = 3 if spread >= 15.0 else 5
        else:
            n = len(ranked_sectors)
        
        selected = []
        for i in range(min(n, len(ranked_sectors))):
            # Only select if it has a directional bias (ignore top-ranked Neutral/Choppy)
            if ranked_sectors[i].bias != "NEUTRAL":
                ranked_sectors[i].is_selected = True
                selected.append(ranked_sectors[i].symbol)
            
        return selected


# ══════════════════════════════════════════════════════════════════════════════
# STOCK ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

class StockGrader:
    """Grades stocks A+ to C based on technical alignment and microstructure."""
    
    @staticmethod
    def get_direction(hma_align: str) -> str:
        """Maps HMA alignment to trade direction."""
        if hma_align == "BULLISH": return "LONG"
        if hma_align == "BEARISH": return "SHORT"
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
        
        # HMA Conflict
        if direction == "NONE":
            # If mixed, we might still trade B grade, but if it conflicts, it's C
            pass 

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
            score += 3
            reasons.append("HMA Fully Aligned")
        else:
            score += 1
            reasons.append("HMA Mixed")
            
        # Volume (2 pts)
        if rvol >= rvol_threshold + 0.3:
            score += 2
            reasons.append(f"Strong RVOL ({rvol:.2f})")
        else:
            score += 1
            reasons.append("Adequate RVOL")
            
        # StochRSI Confirmation (2 pts)
        if (direction == "LONG" and stoch_k < 20) or (direction == "SHORT" and stoch_k > 80):
            score += 2
            reasons.append("StochRSI Extreme Confirmation")
        elif 20 <= stoch_k <= 80:
            score += 1
            reasons.append("StochRSI Neutral")
            
        # Sector (2 pts)
        if sector_rank <= 3:
            score += 2
            reasons.append(f"Top 3 Sector (Rank {sector_rank})")
        elif sector_rank <= 5:
            score += 1
            reasons.append(f"Top 5 Sector (Rank {sector_rank})")
            
        # Spread Quality (1 pt)
        gate_limit = config.STRICT_SPREAD_ATR_LIMIT if playbook == "ORB" else config.NORMAL_SPREAD_ATR_LIMIT
        if spread_atr < gate_limit * 0.5:
            score += 1
            reasons.append("Superior Spread Quality")

        # 3. Final Grade Assignment
        if score >= 9: grade = "A+"
        elif score >= 7: grade = "A"
        elif score >= 4: grade = "B"
        else: grade = "C"
        
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
        
        # Use last 20 elements
        c_win = closes[-20:]
        v_win = volumes[-20:]
        
        # Vectorized calculation: (Price * Volume)
        daily_values = c_win * v_win
        avg_val = np.mean(daily_values)
        
        return float(avg_val / 10_000_000) # 1 Crore = 10^7
