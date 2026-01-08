"""
================================================================================
V4 SAFETY MONITORS
================================================================================
The Kill Switch. Monitors for extreme market events:
- Flash Crash (Nifty drop > 3% in 5m)
- VIX Spike (> 15% in 5m)
- Breadth Collapse (> 70% Sector stocks red)

Author: Sector Analysis System
Version: 4.0.0
================================================================================
"""

import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from core_v4 import config_v4 as config

logger = logging.getLogger("SafetyV4")

class SafetyMonitor:
    def __init__(self):
        # Time-series buffers for spike detection (5-min windows)
        self.nifty_history = deque(maxlen=300) # 5 mins @ 1 sec resolution
        self.vix_history = deque(maxlen=300)
        
        self.is_halted = False
        self.halt_reason = ""

    def update(self, nifty_ltp: float, vix_ltp: float, red_stock_pct: float):
        """
        Feed current values into safety buffers.
        """
        now = datetime.now()
        self.nifty_history.append((now, nifty_ltp))
        self.vix_history.append((now, vix_ltp))
        
        # 1. Flash Crash Detection (Nifty)
        if len(self.nifty_history) > 10:
            start_val = self.nifty_history[0][1]
            if start_val > 0:
                drop = (nifty_ltp - start_val) / start_val
                if drop <= -0.03: # -3%
                    self._trigger_halt(f"FLASH_CRASH (Nifty drop {drop:.2%})")

        # 2. VIX Spike Detection
        if len(self.vix_history) > 10:
            start_vix = self.vix_history[0][1]
            if start_vix > 0:
                spike = (vix_ltp - start_vix) / start_vix
                if spike >= 0.15: # +15%
                    self._trigger_halt(f"VIX_SPIKE (VIX up {spike:.2%})")

        # 3. Breadth Collapse
        if red_stock_pct >= 0.70: # 70% red
            self._trigger_halt(f"BREADTH_COLLAPSE ({red_stock_pct:.0%})")

    def _trigger_halt(self, reason: str):
        if not self.is_halted:
            self.is_halted = True
            self.halt_reason = reason
            logger.critical(f"🛑 SYSTEM HALT TRIGGERED: {reason}")

    def check_force_exit(self, current_time: datetime.time) -> bool:
        """Binary check for 15:05 cutoff."""
        return current_time >= config.FORCE_EXIT_TIME
