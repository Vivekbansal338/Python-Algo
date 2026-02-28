import json
from pathlib import Path
from collections import Counter
import numpy as np

def analyze_v69_history(filepath):
    print(f"\n{'='*80}\nAnalyzing: {filepath.name}\n{'='*80}")
    
    with open(filepath, 'r') as f:
        data = json.load(f)
        
    trades = data.get('trade_records', [])
    summary = data.get('summary', {})
    
    if not trades:
        print("No trades found.")
        return
        
    print(f"Total Trades: {len(trades)}")
    print(f"Net PnL: {summary.get('total_return', 0):,.0f}")
    
    # Win / Loss
    wins = [t for t in trades if t['realized_pnl'] > 0]
    losses = [t for t in trades if t['realized_pnl'] <= 0]
    print(f"Win Rate: {len(wins)} / {len(trades)} ({len(wins)/len(trades)*100:.1f}%)")
    
    # Exits
    exits = Counter(t['exit_reason'] for t in trades)
    print("\nExit Reasons:")
    for reason, count in exits.most_common():
        print(f"  {reason:<20}: {count:>5} ({count/len(trades)*100:.1f}%)")
        
    # HMA Trail efficiency
    hma_active = sum(1 for t in trades if t.get('hma_trail_active', False))
    print(f"\nHMA Trail Engaged: {hma_active} trades ({hma_active/len(trades)*100:.1f}%)")
    
    # Stop Hard stats
    hard_stops = [t for t in trades if t['exit_reason'] == 'STOP_HARD']
    if hard_stops:
        avg_hard_loss = np.mean([t['realized_pnl'] for t in hard_stops])
        print(f"Avg STOP_HARD Loss: {avg_hard_loss:,.0f}")
    
    # HMA Trail stats
    trail_stops = [t for t in trades if t['exit_reason'] == 'STOP_HMA_TRAIL']
    if trail_stops:
        avg_trail_pnl = np.mean([t['realized_pnl'] for t in trail_stops])
        print(f"Avg STOP_HMA_TRAIL PnL: {avg_trail_pnl:,.0f}")

analyze_v69_history(Path(r"C:\Users\VIVEK BANSAL\Desktop\Python_Algo\TradingBot\backtest_v6\history_v6.9\backtest_history_28-02-2026_12-15_pm.json"))
