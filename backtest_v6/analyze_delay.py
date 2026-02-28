import json
from pathlib import Path
from collections import defaultdict
import numpy as np

def analyze_crossover_delay(filepath):
    print(f"\n{'='*80}\nAnalyzing Entry Delay Correlation in: {filepath.name}\n{'='*80}")
    
    with open(filepath, 'r') as f:
        data = json.load(f)
        
    trades = data.get('trade_records', [])
    signals = data.get('signal_records', [])
    if not trades:
        print("No trades found.")
        return
        
    # Map trade_id back to its signal to get cross_bars_ago
    trade_delay_map = {}
    for s in signals:
        t_id = s.get('executed_trade_id')
        if t_id:
            delay = s.get('hma_quality', {}).get('cross_bars_ago', -1)
            trade_delay_map[t_id] = delay
            
    # Group trades by cross_bars_ago
    # Delay buckets: 1-3 bars (5-15m), 4-6 bars (20-30m), 7-10 bars (35-50m), 11-15 bars (55-75m)
    buckets = {
        "1-3 (Fast)": [],
        "4-6 (Medium)": [],
        "7-10 (Slow)": [],
        "11-15 (Very Late)": [],
        "Unknown": []
    }
    
    for t in trades:
        t_id = t.get('trade_id')
        bars_ago = trade_delay_map.get(t_id, -1)
        if bars_ago <= 0:
            buckets["Unknown"].append(t)
        elif bars_ago <= 3:
            buckets["1-3 (Fast)"].append(t)
        elif bars_ago <= 6:
            buckets["4-6 (Medium)"].append(t)
        elif bars_ago <= 10:
            buckets["7-10 (Slow)"].append(t)
        else:
            buckets["11-15 (Very Late)"].append(t)
            
    print(f"{'Delay Bucket':<20} | {'Trades':>8} | {'Win Rate':>10} | {'Net PnL':>12} | {'Avg PnL':>10}")
    print("-" * 70)
    
    for bucket_name, bucket_trades in buckets.items():
        if not bucket_trades:
            continue
            
        count = len(bucket_trades)
        wins = sum(1 for t in bucket_trades if t['realized_pnl'] > 0)
        win_rate = (wins / count) * 100 if count > 0 else 0
        net_pnl = sum(t['realized_pnl'] for t in bucket_trades)
        avg_pnl = net_pnl / count if count > 0 else 0
        
        print(f"{bucket_name:<20} | {count:>8} | {win_rate:>9.1f}% | {net_pnl:>12,.0f} | {avg_pnl:>10,.0f}")
        
analyze_crossover_delay(Path(r"C:\Users\VIVEK BANSAL\Desktop\Python_Algo\TradingBot\backtest_v6\history_v6.9\backtest_history_28-02-2026_12-15_pm.json"))
