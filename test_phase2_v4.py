import time
import logging
from datetime import datetime, time as dt_time
from execution_v4.risk_v4 import RiskManager
from execution_v4.orders_v4 import OrderManager
from execution_v4.lifecycle_v4 import LifecycleManager

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestPhase2")

def main():
    print("🚀 Starting V4 Phase 2 Integration Test (Execution)...")
    
    # 1. Initialize Modules
    risk = RiskManager()
    orders = OrderManager()
    lifecycle = LifecycleManager(orders)
    
    # 2. Setup Account (10 Lakh)
    risk.update_account(
        equity=1000000.0, 
        pnl=0.0, 
        positions=[]
    )
    print("💰 Account Initialized: ₹10,00,000")

    # 3. Test Risk Calculation
    # Scenario: A+ Grade, Normal VIX, Lunch Time
    entry = 1000.0
    stop = 990.0  # Risk = 10
    
    # Lunch time (12:30) -> Should apply 0.7x multiplier
    sizing = risk.calculate_position_size(
        entry, stop, "A+", 1.0, dt_time(12, 30)
    )
    
    print("\n----------------------------------------------------------------")
    print(f"📉 Risk Check (Lunch Time):")
    print(f"   Allowed: {sizing.is_allowed}")
    print(f"   Shares: {sizing.shares}")
    print(f"   Risk Amt: ₹{sizing.risk_amount:.2f}")
    print(f"   Reason: {sizing.reason}")
    
    if not sizing.is_allowed:
        print("❌ Risk Logic Failed")
        return

    # 4. Test Order & Lifecycle (Simulation)
    print("\n----------------------------------------------------------------")
    print("🔄 Starting Lifecycle Simulation (Long RELIANCE)...")
    
    symbol = "RELIANCE"
    trade_id = lifecycle.initiate_trade(
        symbol, "LONG", sizing.shares, entry, stop, atr=5.0
    )
    
    if trade_id:
        print(f"✅ Trade Initiated: {trade_id}")
        t = lifecycle.trades[trade_id]
        print(f"   Target 1: {t.target_1:.2f}")
    else:
        print("❌ Trade Init Failed")
        return

    # 5. Simulate Price Action
    # Scenario: Price goes up, hits T1, then trails
    
    # Tick 1: Small move up
    print("\n--- Tick 1: Price 1010 ---")
    lifecycle.update_trades({"NSE:RELIANCE": {"last_price": 1010.0}})
    
    # Tick 2: Hits Target 1 (1.5R = 1000 + 15 = 1015)
    print("\n--- Tick 2: Price 1016 (Target Hit) ---")
    lifecycle.update_trades({"NSE:RELIANCE": {"last_price": 1016.0}})
    
    # Verify Partial Exit
    t = lifecycle.trades[trade_id]
    print(f"   Stage: {t.stage}")
    print(f"   Remaining Qty: {t.qty}")
    print(f"   Current Stop: {t.current_stop} (Should be 1000.0)")

    # Tick 3: Price pumps to 1040 (New High)
    print("\n--- Tick 3: Price 1040 (New High) ---")
    lifecycle.update_trades({"NSE:RELIANCE": {"last_price": 1040.0}})
    # Chandelier should trail: 1040 - (3 * 5) = 1025
    print(f"   New Stop: {t.current_stop} (Should be 1025.0)")

    # Tick 4: Price crashes to 1020 (Stop Hit)
    print("\n--- Tick 4: Price 1020 (Stop Hit) ---")
    lifecycle.update_trades({"NSE:RELIANCE": {"last_price": 1020.0}})
    
    if t.stage == "CLOSED":
        print("✅ Trade Closed Successfully")
    else:
        print("❌ Trade Failed to Close")

    # 6. Verify Paper Positions Cleared
    final_pos = orders.get_positions()
    print(f"\nFinal Open Positions: {len(final_pos)}")
    
    print("\n✅ V4 PHASE 2 TEST COMPLETE!")

if __name__ == "__main__":
    main()