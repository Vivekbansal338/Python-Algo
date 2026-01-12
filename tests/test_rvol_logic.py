import logging
import numpy as np
import sys
import os

# Add parent directory to path to allow importing core modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta
from core_v4.data_v4 import data_manager

# Setup simple logger
logging.basicConfig(level=logging.INFO)

def test_rvol():
    print("🚀 Starting RVOL Logic Test...")
    
    # 1. Connect
    if not data_manager.connect():
        print("❌ Connect Failed")
        return
        
    data_manager.load_instruments()
    
    symbol = "RELIANCE"
    token = data_manager.get_token(f"NSE:{symbol}")
    
    if not token:
        print("❌ Token not found")
        return

    # 2. Fetch 5 Days of 5-Min Data
    to_date = datetime.now()
    from_date = to_date - timedelta(days=5)
    
    print(f"📥 Fetching data for {symbol} ({from_date.date()} to {to_date.date()})...")
    data = data_manager.get_historical(token, from_date, to_date, "5minute")
    
    if not data:
        print("❌ No data received")
        return
        
    print(f"✅ Received {len(data)} candles.")
    
    # 3. Extract Volume
    volumes = np.array([d['volume'] for d in data])
    
    # 4. Calculate Stats
    avg_vol = np.mean(volumes)
    last_vol = volumes[-1]
    last_time = data[-1]['date']
    
    rvol = last_vol / avg_vol
    
    print("\n📊 RVOL Analysis:")
    print(f"   Last Candle Time: {last_time}")
    print(f"   Last Candle Volume: {last_vol:,.0f}")
    print(f"   5-Day Avg 5-Min Volume: {avg_vol:,.0f}")
    print(f"   RVOL Ratio: {rvol:.2f}x")
    
    # 5. Sanity Check
    if avg_vol == 0:
        print("❌ ERROR: Average Volume is 0")
    elif rvol > 50:
        print("⚠️ WARNING: RVOL seems improbably high (Data spike?)")
    elif rvol < 0.01:
        print("⚠️ WARNING: RVOL seems improbably low")
    else:
        print("✅ Logic seems mathematically sound.")

if __name__ == "__main__":
    test_rvol()
