"""
================================================================================
V5 CONFIGURATION MODULE
================================================================================
Central repository for all constants, thresholds, and settings.
V5 Fixes:
- Removed redundant SECTOR_RECALC_INTERVAL_SEC (now WebSocket-driven)
- Added INTRADAY_REFRESH_INTERVAL_SEC for periodic 5m candle re-fetch
- Cleaner architecture with explicit data refresh strategy

Author: Sector Analysis System
Version: 5.0.0 (Paper Trading)
================================================================================
"""

import os
from datetime import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PATHS
# ══════════════════════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = Path(__file__).parent.parent / "config"
UNIVERSE_PATH = CONFIG_DIR / "universe.json"
DATA_DIR = Path(__file__).parent.parent / "data"
LOG_FILE = Path(__file__).parent.parent / "v5_bot.log"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# TRADING TIMINGS (IST)
# ══════════════════════════════════════════════════════════════════════════════

# 09:15 - Market Open (Wait period starts)
MARKET_OPEN_TIME = time(9, 15)

# 09:20 - Opening Range Formation Starts
OR_START_TIME = time(9, 20)

# 09:34 - Opening Range Ends
OR_END_TIME = time(9, 34)

# 09:35 - ORB Playbook Starts (Strict Entry)
ORB_START_TIME = time(9, 35)
ORB_END_TIME = time(10, 5)

# 10:05 - Gap Period (No New Entries)
GAP_START_TIME = time(10, 5)
GAP_END_TIME = time(10, 10)

# 10:10 - Main Playbook Starts (Normal Entry)
MAIN_START_TIME = time(10, 10)
MAIN_END_TIME = time(14, 5)

# 12:00 - Lunch Lull (Reduced Sizing)
LUNCH_START_TIME = time(12, 0)
LUNCH_END_TIME = time(13, 15)

# 14:05 - Entry Cutoff (Exit Only Mode)
ENTRY_CUTOFF_TIME = time(14, 5)

# 15:05 - Force Exit (Hard Square-off)
FORCE_EXIT_TIME = time(15, 5)

# 15:30 - Market Close
MARKET_CLOSE_TIME = time(15, 30)

# ══════════════════════════════════════════════════════════════════════════════
# RISK MANAGEMENT CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

# Capital Allocation
BASE_RISK_PER_TRADE_PCT = 0.005  # 0.5% of account equity

# Portfolio Limits
MAX_CONCURRENT_POSITIONS = 6
MAX_POSITIONS_PER_SECTOR = 2
MAX_POSITIONS_PER_STOCK = 1
CORRELATION_THRESHOLD = 0.70

# Drawdown Limits (Kill Switches)
DAILY_DRAWDOWN_WARNING_PCT = -0.01  # -1.0% (Reduce size)
DAILY_DRAWDOWN_HALT_PCT = -0.02     # -2.0% (Stop new entries)

# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL & GRADING CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

# Grade Multipliers
GRADE_MULTIPLIERS = {
    "A+": 1.00,
    "A":  0.85,
    "B":  0.60,
    "C":  0.00
}

# VIX Percentile Thresholds (20-day)
VIX_PCTL_LOW_THRESHOLD = 20.0
VIX_PCTL_HIGH_THRESHOLD = 75.0
VIX_PCTL_EXTREME_THRESHOLD = 90.0

# VIX Sizing Multipliers
VIX_MULT_LOW = 1.20      # 0-20th percentile
VIX_MULT_NORMAL = 1.00   # 20-50th percentile
VIX_MULT_ELEVATED = 0.80 # 50-75th percentile
VIX_MULT_HIGH = 0.75     # 75th percentile and above

# RVOL Thresholds (ORB / MAIN)
# Format: (VIX_PCTL_MAX, THRESHOLD)
RVOL_THRESHOLDS_ORB = [
    (25, 1.8),
    (50, 1.5),
    (75, 1.3),
    (100, 1.2)
]

RVOL_THRESHOLDS_MAIN = [
    (25, 1.5),
    (50, 1.3),
    (75, 1.1),
    (100, 1.0)
]

# ══════════════════════════════════════════════════════════════════════════════
# STRATEGY WEIGHTS & SCORING
# ══════════════════════════════════════════════════════════════════════════════

# Sector Scoring Weights
SECTOR_WEIGHTS = {
    "structural": 3.0,
    "shortterm": 10.0,
    "intraday": 20.0,
    "breadth": 40.0,
    "nifty": 30.0
}

# Sector Selection Thresholds
SECTOR_TOP_N_SPREAD = 15.0  # Spread between #1 and #5 to pick Top 3 vs Top 5

# Stock Grading Points (Total 10)
POINTS_HMA = 3
POINTS_RVOL = 2
POINTS_STOCH = 2
POINTS_SECTOR_RANK = 2
POINTS_SPREAD = 1

# Grade Cutoffs
THRESHOLD_A_PLUS = 9
THRESHOLD_A = 7
THRESHOLD_B = 4

# Microstructure Gate Constants
# ══════════════════════════════════════════════════════════════════════════════

# Liquidity Filter
MIN_ADV_CRORES = 75.0

# Strict Mode (ORB)
STRICT_SPREAD_ATR_LIMIT = 0.15
STRICT_CIRCUIT_BUFFER = 0.03

# Normal Mode (Main)
NORMAL_SPREAD_ATR_LIMIT = 0.25
NORMAL_CIRCUIT_BUFFER = 0.02

# ══════════════════════════════════════════════════════════════════════════════
# API SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

KITE_API_KEY = os.getenv("KITE_API_KEY")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")

# Rate Limits (Requests per second)
RATE_LIMIT_QUOTE = 1.0
RATE_LIMIT_ORDERS = 5.0  # Conservative

# Caching
CACHE_INSTRUMENTS_SEC = 3600 * 12  # 12 hours
CACHE_HISTORICAL_SEC = 60 * 15     # 15 minutes

# ══════════════════════════════════════════════════════════════════════════════
# MODE SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

# Execution Mode
# V5 is STRICTLY PAPER_TRADING.
# This flag protects against accidental live orders in V5 logic.
IS_PAPER_TRADING = True

# ══════════════════════════════════════════════════════════════════════════════
# DATA & REFRESH SETTINGS (V5 REFINED)
# ══════════════════════════════════════════════════════════════════════════════

# V5 FIX: Removed SECTOR_RECALC_INTERVAL_SEC (redundant - now WebSocket-driven)

# V5 NEW: Periodic re-fetch interval for 5-minute candles (RVOL/HMA fix)
# This addresses the "Memory Loss" / "Stale Data" issue
# ~50 stocks at 3 req/sec = ~20 seconds fetch time
INTRADAY_REFRESH_INTERVAL_SEC = 300  # 5 minutes

# Historical lookback periods
LOOKBACK_DAYS_DAILY = 60
LOOKBACK_DAYS_INTRA = 5
LOOKBACK_DAYS_VIX = 45

# UI refresh interval (WebSocket-driven metrics)
UI_REFRESH_INTERVAL = 5  # Seconds between UI updates

# ══════════════════════════════════════════════════════════════════════════════
# RISK & SIZING ADVANCED
# ══════════════════════════════════════════════════════════════════════════════
DEFAULT_PAPER_EQUITY = 1000000.0
RISK_MULT_LUNCH = 0.70
RISK_MULT_WARNING = 0.50

# ══════════════════════════════════════════════════════════════════════════════
# LIFECYCLE & STOPS
# ══════════════════════════════════════════════════════════════════════════════
STOP_ATR_MULT_ORB = 2.4
STOP_ATR_MULT_MAIN = 2.0

TARGET_1_MULT = 1.5
TARGET_1_EXIT_PCT = 0.50

CHANDELIER_ATR_MULT = 3.0
CHANDELIER_LOOKBACK = 10
