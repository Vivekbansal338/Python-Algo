"""
================================================================================
V4 PHASE 1 INTEGRATION TEST
================================================================================
Verifies connectivity, data fetching, and core analysis logic for V4 rewrite.
================================================================================
"""

import time
import logging
import sys
import os

# Add parent directory to path to allow importing core modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta
from core_v4.data_v4 import data_manager
from analysis_v4.strategy_v4 import MarketRegimeDetector, SectorScorer, SectorScore, StockGrader
from analysis_v4.indicators_v4 import calculate_hma, calculate_stoch_rsi

logger = logging.getLogger("TestV4")

def main():
    print("🚀 Starting V4 Phase 1 Integration Test...")
    
    # 1. Connect
    if not data_manager.connect():
        print("❌ Connection Failed.")
        return

    # 2. Load Instruments
    if not data_manager.load_instruments():
        print("❌ Instrument Loading Failed.")
        return
    
    print("✅ Connection and Instruments OK.")

    # 3. Test Indicator Math (HMA & StochRSI)
    prices = [100 + i for i in range(100)] # Trending up
    hma = calculate_hma(prices, 16)
    k, d = calculate_stoch_rsi(prices)
    print(f"📈 Indicator Check: HMA(16)={hma:.2f}, StochRSI(K)={k:.2f}")

    # 4. Test Strategy Logic (Market Regime)
    # Mock VIX history
    vix_history = [12.0 + i*0.1 for i in range(30)]
    curr_vix = 15.0
    pctl = MarketRegimeDetector.calculate_percentile(curr_vix, vix_history)
    regime = MarketRegimeDetector.get_regime(pctl)
    mult = MarketRegimeDetector.get_vix_multiplier(pctl)
    print(f"🌡️ Regime Check: Pctl={pctl:.1f}%, Regime={regime}, Multiplier={mult}x")

    # 5. Test Sector Scorer
    scorer = SectorScorer()
    mock_sectors = [
        SectorScore("NIFTY IT", structural_rs=2.0, shortterm_rs=1.5, intraday_rs=0.5, breadth=0.7),
        SectorScore("NIFTY AUTO", structural_rs=-1.0, shortterm_rs=-0.5, intraday_rs=-0.2, breadth=0.3),
        SectorScore("NIFTY BANK", structural_rs=0.5, shortterm_rs=0.8, intraday_rs=0.1, breadth=0.5),
    ]
    # Pass Nifty PCT = -0.5 (Market Drag)
    ranked = scorer.score_all(mock_sectors, "NEUTRAL", nifty_pct=-0.5)
    selected = scorer.select_top_n(ranked)
    print(f"📊 Sector Check: Top 1={ranked[0].symbol}, Score={ranked[0].composite_score:.2f}, Selected={selected}")

    # 6. Fetch Real Data (Sample Quote)
    sample_symbol = "RELIANCE"
    quote = data_manager.get_quote([sample_symbol])
    if quote:
        key = f"NSE:{sample_symbol}"
        if key in quote:
            ltp = quote[key]['last_price']
            print(f"💎 Real Data Check: {sample_symbol} LTP = {ltp}")
        else:
            print(f"⚠️ Quote for {key} not found in response: {quote}")
    
    print("\n✅ V4 PHASE 1 TEST COMPLETE!")

if __name__ == "__main__":
    main()