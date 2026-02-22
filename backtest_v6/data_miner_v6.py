"""
===============================================================================
V6 BACKTEST DATA MINER
===============================================================================
Fetches historical data for the V6 backtest engine and stores parquet files.

Data layout:
- backtest_v6/data/daily/*.parquet
- backtest_v6/data/5minute/*.parquet

Uses:
- v6.data_engine.data_manager (Kite API wrapper)
- v6.config.UNIVERSE_PATH (instrument universe)
===============================================================================
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from v6 import config
from v6.data_engine import data_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DataMinerV6")


class DataMinerV6:
    """Incremental data fetcher for V6 backtests."""

    def __init__(self, data_root: Path = None):
        self.data_root = Path(data_root) if data_root else (Path(__file__).parent / "data")
        self.daily_dir = self.data_root / "daily"
        self.intra_dir = self.data_root / "5minute"
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self.intra_dir.mkdir(parents=True, exist_ok=True)
        self.universe = self._load_universe()

    @staticmethod
    def _safe_symbol(symbol: str) -> str:
        return str(symbol).strip()

    def _load_universe(self) -> Dict:
        if not config.UNIVERSE_PATH.exists():
            raise FileNotFoundError(f"Universe file missing: {config.UNIVERSE_PATH}")
        with open(config.UNIVERSE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_targets(self) -> List[Dict[str, int]]:
        targets: List[Dict[str, int]] = [
            {"symbol": "NIFTY 50", "token": 256265},
            {"symbol": "INDIA VIX", "token": 264969},
        ]

        for idx in self.universe.get("indices", []):
            name = idx.get("name", "")
            if name in ("NIFTY 50", "INDIA VIX"):
                continue
            sym = self._safe_symbol(idx.get("symbol", ""))
            token = idx.get("token")
            if sym and token:
                targets.append({"symbol": sym, "token": int(token)})

        for stk in self.universe.get("stocks", []):
            sym = self._safe_symbol(stk.get("symbol", ""))
            token = stk.get("token")
            if sym and token:
                targets.append({"symbol": sym, "token": int(token)})

        # De-duplicate by symbol while preserving first occurrence.
        dedup = {}
        for item in targets:
            if item["symbol"] not in dedup:
                dedup[item["symbol"]] = item
        return list(dedup.values())

    def fetch_all(self, days_back: int = 90, force: bool = False):
        if not data_manager.connect():
            logger.error("Failed to connect to Kite API.")
            return

        targets = self._build_targets()
        logger.info("Target instruments: %d", len(targets))

        to_date = datetime.now()
        from_date = to_date - timedelta(days=int(days_back))

        ok = 0
        failed = 0
        for i, item in enumerate(targets, start=1):
            sym = item["symbol"]
            token = item["token"]
            logger.info("[%d/%d] %s", i, len(targets), sym)
            try:
                self._fetch_interval(token, sym, from_date, to_date, "day", self.daily_dir, force=force)
                self._fetch_interval(token, sym, from_date, to_date, "5minute", self.intra_dir, force=force)
                ok += 1
            except Exception as exc:
                logger.error("Failed %s: %s", sym, exc)
                failed += 1
            time.sleep(0.35)

        logger.info("Completed: ok=%d failed=%d", ok, failed)

    def _fetch_interval(
        self,
        token: int,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        out_dir: Path,
        force: bool = False,
    ) -> bool:
        file_path = out_dir / f"{symbol}.parquet"
        existing = pd.DataFrame()

        if file_path.exists() and not force:
            try:
                existing = pd.read_parquet(file_path)
                if not existing.empty:
                    existing["date"] = pd.to_datetime(existing["date"], errors="coerce")
                    existing = existing.dropna(subset=["date"])
            except Exception as exc:
                logger.warning("Corrupt existing parquet for %s (%s). Rebuilding.", symbol, exc)
                existing = pd.DataFrame()

        fetch_ranges: List[Tuple[datetime, datetime]] = []
        if existing.empty:
            fetch_ranges.append((from_date, to_date))
        else:
            old_min = existing["date"].min().to_pydatetime()
            old_max = existing["date"].max().to_pydatetime()

            if from_date < old_min:
                fetch_ranges.append((from_date, old_min))
                logger.info("  backfill: %s -> %s", from_date.date(), old_min.date())

            if to_date > old_max:
                if interval == "5minute":
                    start_ext = old_max + timedelta(minutes=1)
                else:
                    start_ext = old_max + timedelta(days=1)
                if start_ext < to_date:
                    fetch_ranges.append((start_ext, to_date))
                    logger.info("  extend: %s -> %s", start_ext.date(), to_date.date())

        if not fetch_ranges and not force:
            logger.info("  up-to-date (%s)", interval)
            return False

        chunks: List[Dict] = []
        for start, end in fetch_ranges:
            if interval == "5minute" and (end - start).days > 60:
                curr = start
                while curr < end:
                    chunk_end = min(curr + timedelta(days=60), end)
                    data = data_manager.get_historical(token, curr, chunk_end, interval)
                    if data:
                        chunks.extend(data)
                    curr = chunk_end + timedelta(days=1)
                    time.sleep(0.35)
            else:
                data = data_manager.get_historical(token, start, end, interval)
                if data:
                    chunks.extend(data)
                time.sleep(0.1)

        if not chunks and existing.empty:
            logger.warning("  no server data")
            return False

        if chunks:
            new_df = pd.DataFrame(chunks)
            new_df["date"] = pd.to_datetime(new_df["date"], errors="coerce").dt.tz_localize(None)
            merged = pd.concat([existing, new_df], ignore_index=True)
        else:
            merged = existing

        merged = merged.dropna(subset=["date"])
        merged = merged.drop_duplicates(subset=["date"], keep="last")
        merged = merged.sort_values("date")
        merged.to_parquet(file_path, index=False)

        logger.info(
            "  saved %s rows=%d range=%s -> %s",
            interval,
            len(merged),
            merged["date"].min().date(),
            merged["date"].max().date(),
        )
        return True

    def fetch_extended(self, days_back: int = 365):
        logger.info("Fetching extended history: %d days", days_back)
        self.fetch_all(days_back=days_back, force=False)

    def verify_data_integrity(self) -> bool:
        issues = []

        def exists(path: Path, label: str):
            if not path.exists():
                issues.append(f"missing {label}: {path.name}")

        exists(self.daily_dir / "NIFTY 50.parquet", "NIFTY daily")
        exists(self.intra_dir / "NIFTY 50.parquet", "NIFTY 5minute")
        exists(self.daily_dir / "INDIA VIX.parquet", "VIX daily")

        for idx in self.universe.get("indices", []):
            name = idx.get("name", "")
            symbol = idx.get("symbol", "")
            if name in ("NIFTY 50", "INDIA VIX") or not symbol:
                continue
            exists(self.daily_dir / f"{symbol}.parquet", f"{symbol} daily")
            exists(self.intra_dir / f"{symbol}.parquet", f"{symbol} 5minute")

        if issues:
            logger.warning("Integrity issues found:")
            for issue in issues:
                logger.warning("  %s", issue)
            return False

        logger.info("Integrity check passed.")
        return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V6 data miner for backtest parquet files")
    parser.add_argument("--days", type=int, default=90, help="Days of history to fetch")
    parser.add_argument("--force", action="store_true", help="Force full re-download")
    parser.add_argument("--verify", action="store_true", help="Only verify existing data")
    parser.add_argument("--extended", action="store_true", help="Fetch extended 365-day history")
    parser.add_argument("--data-root", type=str, default=None, help="Output data root (contains daily/ and 5minute/)")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    root = Path(args.data_root) if args.data_root else None
    miner = DataMinerV6(data_root=root)

    if args.verify:
        miner.verify_data_integrity()
    elif args.extended:
        miner.fetch_extended(days_back=365)
    else:
        miner.fetch_all(days_back=args.days, force=args.force)

