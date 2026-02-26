"""
Brokerage Cost Calculator for Backtest Trade Records

Calculates complete brokerage costs including:
- Brokerage: 0.03% or Rs. 20 per order (whichever is lower)
- STT/CTT: 0.025% on sell side
- Transaction charges: NSE 0.00297%, BSE 0.00375%
- SEBI charges: ₹10 per crore
- Stamp charges: 0.003% or ₹300 per crore on buy side
- GST: 18% on (brokerage + SEBI + transaction charges)

Usage:
    python backtest_v6/analysis/brokerage.py <history_file.json>
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class BrokerageCalculator:
    """Calculate complete brokerage costs for trades."""
    
    # Brokerage parameters
    BROKERAGE_PCT = 0.03  # 0.03%
    BROKERAGE_MIN = 20.0  # Rs. 20 per order
    
    STT_SELL_PCT = 0.025  # 0.025% on sell side
    
    TRANSACTION_CHARGE_NSE = 0.00297  # 0.00297%
    TRANSACTION_CHARGE_BSE = 0.00375  # 0.00375%
    
    SEBI_CHARGE = 10.0  # ₹10 per crore
    
    STAMP_CHARGE_PCT = 0.003  # 0.003% on buy side
    STAMP_CHARGE_MIN = 300.0  # ₹300 per crore
    
    GST_PCT = 0.18  # 18% on (brokerage + SEBI + transaction charges)
    
    def __init__(self, exchange: str = "NSE"):
        """Initialize calculator with specified exchange (NSE or BSE)."""
        self.exchange = exchange.upper()
        self.transaction_charge_pct = (
            self.TRANSACTION_CHARGE_NSE if self.exchange == "NSE" 
            else self.TRANSACTION_CHARGE_BSE
        )
    
    def calculate_turnover(self, price: float, qty: int) -> float:
        """Calculate turnover amount (price * quantity)."""
        return price * qty
    
    def calculate_brokerage(self, turnover: float) -> float:
        """Calculate brokerage: min(0.03% of turnover, Rs. 20)."""
        brokerage_pct = turnover * (self.BROKERAGE_PCT / 100.0)
        return min(brokerage_pct, self.BROKERAGE_MIN)
    
    def calculate_stt(self, turnover: float, is_sell: bool) -> float:
        """Calculate STT/CTT: 0.025% on sell side only."""
        if is_sell:
            return turnover * (self.STT_SELL_PCT / 100.0)
        return 0.0
    
    def calculate_transaction_charge(self, turnover: float) -> float:
        """Calculate transaction charges based on exchange."""
        return turnover * (self.transaction_charge_pct / 100.0)
    
    def calculate_sebi_charge(self, turnover: float) -> float:
        """Calculate SEBI charges: ₹10 per crore."""
        # 1 crore = 10,000,000
        crores = turnover / 10_000_000
        return max(self.SEBI_CHARGE * crores, 0.0)
    
    def calculate_stamp_charge(self, turnover: float, is_buy: bool) -> float:
        """Calculate stamp charges: 0.003% or ₹300 per crore on buy side."""
        if is_buy:
            stamp_pct = turnover * (self.STAMP_CHARGE_PCT / 100.0)
            crores = turnover / 10_000_000
            stamp_flat = self.STAMP_CHARGE_MIN * crores
            return min(stamp_pct, stamp_flat)
        return 0.0
    
    def calculate_gst(self, brokerage: float, sebi: float, transaction: float) -> float:
        """Calculate GST: 18% on (brokerage + SEBI + transaction charges)."""
        taxable = brokerage + sebi + transaction
        return taxable * (self.GST_PCT / 100.0)
    
    def calculate_total_charges(
        self, 
        price: float, 
        qty: int, 
        is_sell: bool
    ) -> Dict[str, float]:
        """
        Calculate all charges for a single trade.
        
        Args:
            price: Execution price (INR)
            qty: Quantity (shares)
            is_sell: True if SELL, False if BUY
        
        Returns:
            Dictionary with breakdown of all charges
        """
        turnover = self.calculate_turnover(price, qty)
        is_buy = not is_sell
        
        brokerage = self.calculate_brokerage(turnover)
        stt = self.calculate_stt(turnover, is_sell)
        transaction = self.calculate_transaction_charge(turnover)
        sebi = self.calculate_sebi_charge(turnover)
        stamp = self.calculate_stamp_charge(turnover, is_buy)
        gst = self.calculate_gst(brokerage, sebi, transaction)
        
        total = brokerage + stt + transaction + sebi + stamp + gst
        
        return {
            "turnover": turnover,
            "brokerage": brokerage,
            "stt": stt,
            "transaction_charge": transaction,
            "sebi_charge": sebi,
            "stamp_charge": stamp,
            "gst": gst,
            "total": total,
        }


def load_backtest_history(filepath: str) -> Dict[str, Any]:
    """Load backtest history JSON file."""
    path = Path(filepath)
    if not path.exists():
        print(f"[ERROR] File not found: {filepath}")
        sys.exit(1)
    
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON file: {e}")
        sys.exit(1)


def analyze_trades(history: Dict[str, Any], calculator: BrokerageCalculator, summary_only: bool = False) -> None:
    """Analyze brokerage costs for all trades in backtest history."""
    
    trade_records = history.get("trade_records", [])
    
    if not trade_records:
        print("[WARNING] No trades found in history file.")
        return
    
    if not summary_only:
        print("\n" + "="*100)
        print(f"[BROKERAGE COST ANALYSIS] - {len(trade_records)} Trades")
        print(f"Exchange: {calculator.exchange}")
        print("="*100)
    
    # Track metrics
    total_turnover = 0.0
    total_costs = defaultdict(float)
    sector_costs = defaultdict(lambda: defaultdict(float))
    symbol_costs = defaultdict(lambda: defaultdict(float))
    
    trades_list = []
    
    # Process each trade
    for trade in trade_records:
        trade_id = trade.get("trade_id", "UNKNOWN")
        symbol = trade.get("symbol", "UNKNOWN")
        sector = trade.get("sector", "UNKNOWN")
        direction = trade.get("direction", "UNKNOWN")
        entry_price = float(trade.get("entry_price", 0))
        exit_price = float(trade.get("exit_price", 0))
        qty = int(trade.get("initial_qty", 0))
        
        # Calculate entry costs (BUY)
        entry_charges = calculator.calculate_total_charges(entry_price, qty, is_sell=False)
        
        # Calculate exit costs (SELL)
        exit_charges = calculator.calculate_total_charges(exit_price, qty, is_sell=True)
        
        # Total costs for trade
        trade_total_cost = entry_charges["total"] + exit_charges["total"]
        trade_total_turnover = entry_charges["turnover"] + exit_charges["turnover"]
        
        # Track totals
        total_turnover += trade_total_turnover
        for key in entry_charges:
            if key != "turnover":
                total_costs[key] += entry_charges[key]
                total_costs[key] += exit_charges[key]
        
        # Track by sector and symbol
        for key in entry_charges:
            if key != "turnover":
                sector_costs[sector][key] += entry_charges[key] + exit_charges[key]
                symbol_costs[symbol][key] += entry_charges[key] + exit_charges[key]
        
        trades_list.append({
            "trade_id": trade_id,
            "symbol": symbol,
            "sector": sector,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "qty": qty,
            "turnover": trade_total_turnover,
            "entry_charges": entry_charges,
            "exit_charges": exit_charges,
            "total_cost": trade_total_cost,
        })
    
    # Skip detailed breakdowns if summary_only
    if summary_only:
        _print_summary_only(total_turnover, total_costs)
        return
    
    # Print detailed trade-by-trade breakdown
    print("\n[TRADE-BY-TRADE BREAKDOWN]")
    print("-" * 100)
    print(f"{'Trade ID':<30} {'Symbol':<10} {'Dir':<6} {'Qty':>8} {'Turnover (Rs)':>14} {'Total Cost (Rs)':>16} {'Cost %':>8}")
    print("-" * 100)
    
    for trade in trades_list:
        cost_pct = (trade["total_cost"] / trade["turnover"] * 100) if trade["turnover"] > 0 else 0
        print(
            f"{trade['trade_id']:<30} {trade['symbol']:<10} {trade['direction']:<6} "
            f"{trade['qty']:>8} {trade['turnover']:>14,.2f} {trade['total_cost']:>16,.2f} {cost_pct:>7.3f}%"
        )
    
    # Summary by symbol
    print("\n\n[BROKERAGE COSTS BY SYMBOL]")
    print("-" * 100)
    print(f"{'Symbol':<15} {'Trades':>8} {'Total Turnover':>18} {'Total Cost (Rs)':>16} {'Cost %':>8}")
    print("-" * 100)
    
    symbol_summary = []
    for symbol in sorted(symbol_costs.keys()):
        costs = symbol_costs[symbol]
        total = costs.get("total", 0)
        # Calculate turnover from trades
        symbol_turnover = sum(
            t["turnover"] for t in trades_list if t["symbol"] == symbol
        )
        count = len([t for t in trades_list if t["symbol"] == symbol])
        cost_pct = (total / symbol_turnover * 100) if symbol_turnover > 0 else 0
        
        symbol_summary.append({
            "symbol": symbol,
            "count": count,
            "turnover": symbol_turnover,
            "cost": total,
            "pct": cost_pct,
        })
    
    for sym in sorted(symbol_summary, key=lambda x: x["cost"], reverse=True):
        print(
            f"{sym['symbol']:<15} {sym['count']:>8} {sym['turnover']:>18,.2f} "
            f"{sym['cost']:>15,.2f} {sym['pct']:>7.3f}%"
        )
    
    # Summary by sector
    print("\n\n[BROKERAGE COSTS BY SECTOR]")
    print("-" * 100)
    print(f"{'Sector':<30} {'Trades':>8} {'Total Turnover':>18} {'Total Cost (Rs)':>16} {'Cost %':>8}")
    print("-" * 100)
    
    sector_summary = []
    for sector in sorted(sector_costs.keys()):
        costs = sector_costs[sector]
        total = costs.get("total", 0)
        # Calculate turnover from trades
        sector_turnover = sum(
            t["turnover"] for t in trades_list if t["sector"] == sector
        )
        count = len([t for t in trades_list if t["sector"] == sector])
        cost_pct = (total / sector_turnover * 100) if sector_turnover > 0 else 0
        
        sector_summary.append({
            "sector": sector,
            "count": count,
            "turnover": sector_turnover,
            "cost": total,
            "pct": cost_pct,
        })
    
    for sec in sorted(sector_summary, key=lambda x: x["cost"], reverse=True):
        print(
            f"{sec['sector']:<30} {sec['count']:>8} {sec['turnover']:>18,.2f} "
            f"{sec['cost']:>15,.2f} {sec['pct']:>7.3f}%"
        )
    
    # Overall summary
    print("\n\n[OVERALL BROKERAGE SUMMARY]")
    print("=" * 100)
    if total_costs.get("total", 0) > 0:
        total_cost = total_costs["total"]
        print(f"\nTotal Turnover:              Rs. {total_turnover:>15,.2f}")
        print(f"\nBrokerage Breakdown:")
        print(f"  Entry/Exit Brokerage:      Rs. {total_costs['brokerage']:>15,.2f}")
        print(f"  STT (Sell Side):           Rs. {total_costs['stt']:>15,.2f}")
        print(f"  Transaction Charges:       Rs. {total_costs['transaction_charge']:>15,.2f}")
        print(f"  SEBI Charges:              Rs. {total_costs['sebi_charge']:>15,.2f}")
        print(f"  Stamp Charges:             Rs. {total_costs['stamp_charge']:>15,.2f}")
        print(f"  GST (18%):                 Rs. {total_costs['gst']:>15,.2f}")
        print(f"  " + "-" * 48)
        print(f"  TOTAL BROKERAGE COST:      Rs. {total_cost:>15,.2f}")
        
        cost_pct = (total_cost / total_turnover * 100) if total_turnover > 0 else 0
        print(f"\nTotal Cost as % of Turnover: {cost_pct:>15.3f}%")
    else:
        print("[WARNING] No valid cost data available")
    
    print("\n" + "="*100 + "\n")


def _print_summary_only(total_turnover: float, total_costs: dict) -> None:
    """Print only the final brokerage summary."""
    print("\n" + "="*100)
    print("[FINAL BROKERAGE SUMMARY]")
    print("="*100)
    
    if total_costs.get("total", 0) > 0:
        total_cost = total_costs["total"]
        print(f"\nTotal Turnover:              Rs. {total_turnover:>15,.2f}")
        print(f"\nBrokerage Breakdown:")
        print(f"  Entry/Exit Brokerage:      Rs. {total_costs['brokerage']:>15,.2f}")
        print(f"  STT (Sell Side):           Rs. {total_costs['stt']:>15,.2f}")
        print(f"  Transaction Charges:       Rs. {total_costs['transaction_charge']:>15,.2f}")
        print(f"  SEBI Charges:              Rs. {total_costs['sebi_charge']:>15,.2f}")
        print(f"  Stamp Charges:             Rs. {total_costs['stamp_charge']:>15,.2f}")
        print(f"  GST (18%):                 Rs. {total_costs['gst']:>15,.2f}")
        print(f"  " + "-" * 48)
        print(f"  TOTAL BROKERAGE COST:      Rs. {total_cost:>15,.2f}")
        
        cost_pct = (total_cost / total_turnover * 100) if total_turnover > 0 else 0
        print(f"\nTotal Cost as % of Turnover: {cost_pct:>15.3f}%")
    else:
        print("[WARNING] No valid cost data available")
    
    print("\n" + "="*100 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Calculate complete brokerage costs for backtest trades"
    )
    parser.add_argument(
        "history_file",
        help="Path to backtest history JSON file"
    )
    parser.add_argument(
        "--exchange",
        default="NSE",
        choices=["NSE", "BSE"],
        help="Stock exchange (default: NSE)"
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Show only final brokerage summary (no trade-by-trade or sector breakdown)"
    )
    
    args = parser.parse_args()
    
    # Load history
    history = load_backtest_history(args.history_file)
    
    # Create calculator
    calculator = BrokerageCalculator(exchange=args.exchange)
    
    # Analyze trades
    analyze_trades(history, calculator, summary_only=args.summary_only)


if __name__ == "__main__":
    main()
