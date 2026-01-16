"""
================================================================================
V5 DATA MINER
================================================================================
Fetches historical data for V5 Backtest Engine.
Scope: Benchmarks, Indices, and ALL Stocks.
Timeframes: Daily (for RS, ATR, StochRSI) and 5-minute (for Breadth/VWAP/RVOL).

V5 Changes:
- Uses V5 modules (core_v5, config_v5)
- Stores Previous Close data for proper percentage calculations
- Same robust incremental fetching (backfill + extension)

Author: Sector Analysis System
Version: 5.0.0
================================================================================
"""

import os
import sys
import time
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core_v5.data_v5 import data_manager
from core_v5 import config_v5 as config

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DataMinerV5")

# Paths
DATA_DIR = Path(__file__).parent / "data"
DAILY_DIR = DATA_DIR / "daily"
INTRA_DIR = DATA_DIR / "5minute"

DAILY_DIR.mkdir(parents=True, exist_ok=True)
INTRA_DIR.mkdir(parents=True, exist_ok=True)


class DataMinerV5:
    """
    V5 Data Miner for backtesting.
    Fetches historical data from Zerodha Kite API and stores as parquet files.
    Supports incremental updates (backfill + extension).
    """
    
    def __init__(self):
        self.universe = self._load_universe()
        
    def _load_universe(self):
        """Load universe.json with all indices and stocks."""
        if not config.UNIVERSE_PATH.exists():
            logger.error("❌ Universe file missing at %s", config.UNIVERSE_PATH)
            sys.exit(1)
        with open(config.UNIVERSE_PATH, 'r') as f:
            return json.load(f)

    def fetch_all(self, days_back: int = 60, force: bool = False):
        """
        Fetch all required historical data.
        
        Args:
            days_back: Number of days of history to fetch
            force: If True, re-download all data even if exists
        """
        if not data_manager.connect():
            logger.error("❌ Failed to connect to Kite API")
            return

        targets = []
        
        # 1. Benchmarks (Nifty 50 and India VIX)
        targets.append({"symbol": "NIFTY 50", "token": 256265})
        targets.append({"symbol": "INDIA VIX", "token": 264969})
        
        # 2. Sector Indices (Use tokens from universe.json)
        for idx in self.universe.get('indices', []):
            if idx['name'] not in ["NIFTY 50", "INDIA VIX"]:
                token = int(idx['token']) if idx.get('token') else None
                if token:
                    targets.append({"symbol": idx['symbol'], "token": token})
        
        # 3. Stocks (Essential for breadth and stock scanning)
        for stk in self.universe.get('stocks', []):
            if stk.get('token'):
                targets.append({"symbol": stk['symbol'], "token": int(stk['token'])})
                
        logger.info(f"🎯 Target List: {len(targets)} instruments.")
        
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days_back)
        
        success_count = 0
        error_count = 0
        
        for i, target in enumerate(targets):
            sym = target['symbol']
            token = target['token']
            
            logger.info(f"[{i+1}/{len(targets)}] Checking {sym}...")
            
            try:
                # Fetch Daily Data
                daily_ok = self._fetch(token, sym, from_date, to_date, "day", DAILY_DIR, force)
                
                # Fetch 5-minute Data
                intra_ok = self._fetch(token, sym, from_date, to_date, "5minute", INTRA_DIR, force)
                
                if daily_ok or intra_ok:
                    success_count += 1
                    
            except Exception as e:
                logger.error(f"   ❌ Error processing {sym}: {e}")
                error_count += 1
            
            # Rate limit: Kite allows ~3 requests/second for historical
            time.sleep(0.35)
        
        logger.info(f"\n✅ Completed: {success_count} successful, {error_count} errors")

    def _fetch(self, token: int, symbol: str, from_date: datetime, 
               to_date: datetime, interval: str, save_dir: Path, force: bool = False) -> bool:
        """
        Fetch historical data for a single symbol.
        Supports incremental updates (backfill old + extend new).
        
        Returns:
            True if data was fetched/updated, False otherwise
        """
        file_path = save_dir / f"{symbol}.parquet"
        
        # 1. Load Existing Data
        existing_df = pd.DataFrame()
        if file_path.exists() and not force:
            try:
                existing_df = pd.read_parquet(file_path)
                if not existing_df.empty:
                    existing_df['date'] = pd.to_datetime(existing_df['date'])
            except Exception as e:
                logger.warning(f"   ⚠️ Corrupt file {symbol}, starting fresh. Error: {e}")

        # 2. Identify Missing Ranges
        fetch_ranges = []
        
        if existing_df.empty:
            fetch_ranges.append((from_date, to_date))
        else:
            old_min = existing_df['date'].min().replace(tzinfo=None)
            old_max = existing_df['date'].max().replace(tzinfo=None)
            
            # Backfill check (Is requested start older than what we have?)
            if from_date < old_min:
                fetch_ranges.append((from_date, old_min))
                logger.info(f"   ↩️  [BACKFILL] {symbol}: Need {from_date.date()} to {old_min.date()}")
            
            # Extension check (Is requested end newer than what we have?)
            if to_date > old_max:
                start_ext = old_max + timedelta(minutes=1) if interval == "5minute" else old_max + timedelta(days=1)
                if start_ext < to_date:
                    fetch_ranges.append((start_ext, to_date))
                    logger.info(f"   ↪️  [EXTENSION] {symbol}: Need {start_ext.date()} to {to_date.date()}")

        if not fetch_ranges and not force:
            logger.info(f"   ⏩ {symbol} ({interval}) is already up to date.")
            return False

        # 3. Fetch Needed Ranges
        new_data = []
        try:
            for start, end in fetch_ranges:
                # Handle chunking for 5-minute data (Kite limits to 60 days per request)
                if interval == "5minute" and (end - start).days > 60:
                    curr = start
                    while curr < end:
                        chunk_end = min(curr + timedelta(days=60), end)
                        chunk = data_manager.get_historical(token, curr, chunk_end, interval)
                        if chunk:
                            new_data.extend(chunk)
                        curr = chunk_end + timedelta(days=1)
                        time.sleep(0.35)  # Rate limit
                else:
                    chunk = data_manager.get_historical(token, start, end, interval)
                    if chunk:
                        new_data.extend(chunk)
                    time.sleep(0.1)

            if not new_data and existing_df.empty:
                logger.warning(f"   ⚠️ No data found for {symbol} on server.")
                return False

            # 4. Merge & Save
            if new_data:
                new_df = pd.DataFrame(new_data)
                new_df['date'] = pd.to_datetime(new_df['date']).dt.tz_localize(None)
                final_df = pd.concat([existing_df, new_df])
            else:
                final_df = existing_df

            # Remove duplicates and sort
            final_df = final_df.drop_duplicates(subset=['date'], keep='last')
            final_df = final_df.sort_values('date')
            
            # Save to parquet
            final_df.to_parquet(file_path, index=False)
            
            # Summary log
            min_d = final_df['date'].min().date()
            max_d = final_df['date'].max().date()
            
            if not existing_df.empty and new_data:
                logger.info(f"   ✅ [MERGED] {symbol}: Total {len(final_df)} rows ({min_d} to {max_d})")
            elif not new_data:
                logger.info(f"   ✅ [NO CHANGE] {symbol}: Coverage {min_d} to {max_d}")
            else:
                logger.info(f"   ✅ [SAVED] {symbol}: New file with {len(final_df)} rows")
            
            return True
            
        except Exception as e:
            logger.error(f"   ❌ Error fetching {symbol}: {e}")
            return False

    def fetch_extended(self, days_back: int = 365):
        """
        Fetch extended history for comprehensive backtesting.
        Uses longer lookback for proper indicator initialization.
        """
        logger.info(f"📊 Fetching extended history ({days_back} days)...")
        self.fetch_all(days_back=days_back, force=False)

    def verify_data_integrity(self):
        """
        Verify that all required data files exist and have sufficient history.
        """
        logger.info("🔍 Verifying data integrity...")
        
        issues = []
        
        # Check NIFTY 50
        nifty_daily = DAILY_DIR / "NIFTY 50.parquet"
        nifty_intra = INTRA_DIR / "NIFTY 50.parquet"
        
        if not nifty_daily.exists():
            issues.append("❌ NIFTY 50 daily data missing")
        if not nifty_intra.exists():
            issues.append("❌ NIFTY 50 5-minute data missing")
            
        # Check VIX
        vix_daily = DAILY_DIR / "INDIA VIX.parquet"
        if not vix_daily.exists():
            issues.append("❌ INDIA VIX daily data missing")
        
        # Check sector indices
        for idx in self.universe.get('indices', []):
            if idx['name'] not in ["NIFTY 50", "INDIA VIX"]:
                daily_file = DAILY_DIR / f"{idx['symbol']}.parquet"
                intra_file = INTRA_DIR / f"{idx['symbol']}.parquet"
                
                if not daily_file.exists():
                    issues.append(f"⚠️ {idx['symbol']} daily data missing")
                if not intra_file.exists():
                    issues.append(f"⚠️ {idx['symbol']} 5-minute data missing")
        
        # Summary
        if issues:
            logger.warning("Data integrity issues found:")
            for issue in issues:
                logger.warning(f"  {issue}")
            return False
        else:
            logger.info("✅ Data integrity check passed.")
            return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="V5 Data Miner for Backtesting")
    parser.add_argument("--days", type=int, default=60, help="Days of history to fetch")
    parser.add_argument("--force", action="store_true", help="Force re-download all data")
    parser.add_argument("--verify", action="store_true", help="Only verify data integrity")
    parser.add_argument("--extended", action="store_true", help="Fetch extended 365-day history")
    
    args = parser.parse_args()
    
    miner = DataMinerV5()
    
    if args.verify:
        miner.verify_data_integrity()
    elif args.extended:
        miner.fetch_extended(days_back=365)
    else:
        miner.fetch_all(days_back=args.days, force=args.force)
