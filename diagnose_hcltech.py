#!/usr/bin/env python3
"""
Diagnostic script to check HCLTECH StochK issue
"""

import json
import sys
from pathlib import Path
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from v6 import config
from v6.data_engine import data_manager, calculate_stoch_rsi, calculate_rsi

def check_hcltech():
    print("=" * 60)
    print("HCLTECH DIAGNOSTIC REPORT")
    print("=" * 60)
    
    # 1. Check universe.json
    print("\n1. CHECKING UNIVERSE.JSON...")
    try:
        with open(config.UNIVERSE_PATH, 'r') as f:
            universe = json.load(f)
        
        hcltech_in_stocks = [s for s in universe.get('stocks', []) if 'HCLTECH' in s.get('symbol', '')]
        hcltech_in_indices = [i for i in universe.get('indices', []) if 'HCLTECH' in i.get('symbol', '')]
        
        if hcltech_in_stocks:
            print(f"[OK] HCLTECH found in stocks: {hcltech_in_stocks[0]}")
        else:
            print("[ERROR] HCLTECH NOT found in stocks list")
            
        if hcltech_in_indices:
            print(f"[OK] HCLTECH found in indices: {hcltech_in_indices[0]}")
        else:
            print("[INFO] HCLTECH not in indices (expected)")
    except Exception as e:
        print(f"[ERROR] Error reading universe: {e}")
    
    # 2. Check logs
    print("\n2. CHECKING V6_BOT.LOG...")
    try:
        log_path = Path(config.LOG_FILE)
        if log_path.exists():
            with open(log_path, 'r') as f:
                logs = f.read()
            
            hcltech_mentions = [line for line in logs.split('\n') if 'HCLTECH' in line.upper()]
            if hcltech_mentions:
                print(f"[OK] Found {len(hcltech_mentions)} mentions of HCLTECH in logs")
                print("   Last 3 mentions:")
                for line in hcltech_mentions[-3:]:
                    print(f"   - {line}")
            else:
                print("[WARN] No HCLTECH mentions in logs (stock never processed)")
        else:
            print(f"[WARN] Log file not found: {log_path}")
    except Exception as e:
        print(f"[ERROR] Error reading logs: {e}")
    
    # 3. Check state file
    print("\n3. CHECKING STATE FILE...")
    try:
        if config.STATE_FILE.exists():
            with open(config.STATE_FILE, 'r') as f:
                state = json.load(f)
            
            positions = state.get('paper_positions', {})
            if 'HCLTECH' in positions:
                print(f"[OK] HCLTECH in positions: {positions['HCLTECH']}")
            else:
                print("[INFO] HCLTECH not in current positions")
            
            trades = state.get('trades', {})
            hcltech_trades = [t for t in trades.values() if t.get('symbol') == 'HCLTECH']
            if hcltech_trades:
                print(f"[OK] Found {len(hcltech_trades)} trade(s) for HCLTECH")
            else:
                print("[INFO] No trades found for HCLTECH")
        else:
            print("[WARN] State file not found")
    except Exception as e:
        print(f"[ERROR] Error reading state: {e}")
    
    # 4. Test data fetching (if credentials available)
    print("\n4. TESTING DATA FETCH...")
    if not config.KITE_API_KEY or not config.KITE_ACCESS_TOKEN:
        print("⚠️  No API credentials found - skipping live data test")
    else:
        try:
            if data_manager.connect():
                print("✅ Connected to Kite API")
                data_manager.load_instruments()
                
                token = data_manager.get_token("NSE:HCLTECH")
                if token:
                    print(f"✅ HCLTECH token: {token}")
                    
                    # Fetch historical data
                    from datetime import datetime, timedelta
                    to_date = datetime.now()
                    from_date = to_date - timedelta(days=config.LOOKBACK_DAYS_DAILY)
                    
                    hist = data_manager.get_historical(token, from_date, to_date, "day")
                    if hist:
                        print(f"✅ Fetched {len(hist)} days of history")
                        
                        closes = np.array([d['close'] for d in hist])
                        print(f"   Close prices shape: {closes.shape}")
                        print(f"   First close: {closes[0]:.2f}")
                        print(f"   Last close: {closes[-1]:.2f}")
                        
                        # Test StochRSI calculation
                        stoch_k, stoch_d = calculate_stoch_rsi(closes)
                        print(f"\n   StochRSI Calculation:")
                        print(f"   - StochK: {stoch_k:.2f}")
                        print(f"   - StochD: {stoch_d:.2f}")
                        
                        if stoch_k == 50.0:
                            print("   ⚠️  StochK=50 indicates insufficient data for calculation")
                        elif stoch_k == 0:
                            print("   ✅ StochK=0 is valid (extreme oversold)")
                        else:
                            print(f"   ✅ StochK={stoch_k:.2f} is a valid calculation")
                    else:
                        print("❌ Failed to fetch historical data")
                else:
                    print("❌ HCLTECH token not found in instruments")
            else:
                print("❌ Failed to connect to Kite API")
        except Exception as e:
            print(f"❌ Error during data fetch: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    check_hcltech()
