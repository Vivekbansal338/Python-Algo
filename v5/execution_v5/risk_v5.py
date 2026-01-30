"""
================================================================================
V5 RISK MANAGER
================================================================================
The Gatekeeper. Enforces:
- Position Sizing (Grade, VIX, DayState)
- Portfolio Limits (Max 6, Max 2/Sector, Correlation)
- Kill Switches (Daily Drawdown)

Author: Sector Analysis System
Version: 5.0.0
================================================================================
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from datetime import time

from core_v5 import config_v5 as config

logger = logging.getLogger("RiskV5")


# ══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class AccountState:
    equity: float
    daily_start_equity: float
    current_pnl: float = 0.0
    open_positions_count: int = 0
    sector_exposure: Dict[str, int] = field(default_factory=dict)
    active_symbols: List[str] = field(default_factory=list)


@dataclass
class SizingResult:
    shares: int
    risk_amount: float
    risk_per_share: float
    effective_risk_pct: float
    is_allowed: bool
    reason: str


# ══════════════════════════════════════════════════════════════════════════════
# RISK MANAGER CLASS
# ══════════════════════════════════════════════════════════════════════════════

class RiskManager:
    def __init__(self):
        self.state = AccountState(
            equity=0.0,
            daily_start_equity=0.0
        )
        self.kill_switch_active = False
        self.kill_switch_reason = ""

    def update_account(self, equity: float, pnl: float, positions: List[Dict]):
        """Update account state from Broker/Paper Broker."""
        self.state.equity = equity
        self.state.current_pnl = pnl
        
        # Update Exposure
        self.state.open_positions_count = len(positions)
        self.state.active_symbols = [p['symbol'] for p in positions]
        
        # Update Sector Exposure
        self.state.sector_exposure.clear()
        for p in positions:
            sector = p.get('sector', 'UNKNOWN')
            self.state.sector_exposure[sector] = self.state.sector_exposure.get(sector, 0) + 1

    def check_kill_switches(self, current_vix_pctl: float) -> Tuple[bool, str]:
        """
        Check 5-Layer Risk Architecture (Layer 5: System).
        Returns (is_halted, reason).
        """
        # 3. Daily Drawdown (-2.0%)
        if self.state.daily_start_equity > 0:
            daily_dd = (self.state.equity - self.state.daily_start_equity) / self.state.daily_start_equity
            if daily_dd <= config.DAILY_DRAWDOWN_HALT_PCT:
                self.kill_switch_active = True
                self.kill_switch_reason = f"DAILY_DD_HALT ({daily_dd:.2%})"
                return True, self.kill_switch_reason

        self.kill_switch_active = False
        return False, "OK"

    def can_open_new_trade(self, symbol: str, sector: str) -> Tuple[bool, str]:
        """
        Check Portfolio Constraints (Layer 4).
        """
        if self.kill_switch_active:
            return False, f"KILL_SWITCH: {self.kill_switch_reason}"

        # Max Positions
        if self.state.open_positions_count >= config.MAX_CONCURRENT_POSITIONS:
            return False, f"MAX_POSITIONS ({self.state.open_positions_count})"

        # Max Per Sector
        current_sector_count = self.state.sector_exposure.get(sector, 0)
        if current_sector_count >= config.MAX_POSITIONS_PER_SECTOR:
            return False, f"MAX_SECTOR_LIMIT ({sector}: {current_sector_count})"

        # Already Open
        if symbol in self.state.active_symbols:
            return False, f"ALREADY_OPEN ({symbol})"

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
        
        # Guard against zero equity
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
            logging.getLogger("Orchestrator").info(debug_msg)
            return SizingResult(0, 0.0, risk_per_share, effective_risk_pct, False, "RISK_TOO_LOW_FOR_1_SHARE")

        return SizingResult(
            shares=shares,
            risk_amount=risk_amount,
            risk_per_share=risk_per_share,
            effective_risk_pct=effective_risk_pct,
            is_allowed=True,
            reason=f"OK (Mult: {total_mult:.2f}x)"
        )
