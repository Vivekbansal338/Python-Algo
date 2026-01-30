"""
================================================================================
V5 DATA HANDLER
================================================================================
Unified Data Handler for V5 Execution Engine.
Manages Zerodha connection, instruments, historical data, and WebSocket.

Features:
- Optimized Caching (Pickle/JSON)
- Robust Error Handling
- Paper Trading Support (Simulates ticks if needed)

Author: Sector Analysis System
Version: 5.0.0
================================================================================
"""

import os
import time
import json
import logging
import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

try:
    import pandas as pd
    from kiteconnect import KiteConnect, KiteTicker
except ImportError:
    print("CRITICAL: kiteconnect or pandas not installed.")
    raise

from core_v5 import config_v5 as config

# Logging setup
logger = logging.getLogger("DataV5")


class DataManagerV5:
    def __init__(self):
        self.api_key = config.KITE_API_KEY
        self.access_token = config.KITE_ACCESS_TOKEN
        self.kite: Optional[KiteConnect] = None
        self.ticker: Optional[KiteTicker] = None
        
        # Data Stores
        self.instruments_df: Optional[pd.DataFrame] = None
        self.token_map: Dict[str, int] = {}  # Symbol -> Token
        self.symbol_map: Dict[int, str] = {}  # Token -> Symbol
        self.live_ticks: Dict[int, Dict] = {} # Token -> Latest Tick
        
        # Cache paths
        self.cache_dir = config.DATA_DIR / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.instruments_cache_path = self.cache_dir / "instruments.pkl"
        
        # Connection Status
        self.is_connected = False
        self.is_ws_connected = False

    # ══════════════════════════════════════════════════════════════════════════
    # CONNECTIVITY
    # ══════════════════════════════════════════════════════════════════════════

    def connect(self) -> bool:
        """Establish connection to Kite Connect API."""
        if not self.api_key or not self.access_token:
            logger.error("Missing API Credentials in environment variables.")
            return False

        try:
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            
            # Verify session by fetching profile
            profile = self.kite.profile()
            logger.info(f"Connected to Zerodha as: {profile.get('user_name')}")
            self.is_connected = True
            return True
            
        except Exception as e:
            logger.error(f"Connection Failed: {e}")
            self.is_connected = False
            return False

    # ══════════════════════════════════════════════════════════════════════════
    # INSTRUMENT MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def load_instruments(self, force_refresh: bool = False) -> bool:
        """
        Load instruments from cache or API.
        Builds efficient token lookup maps.
        """
        if not self.is_connected:
            logger.error("Cannot load instruments: Not connected.")
            return False

        # Try Cache First
        if not force_refresh and self.instruments_cache_path.exists():
            modified_time = self.instruments_cache_path.stat().st_mtime
            age = time.time() - modified_time
            if age < config.CACHE_INSTRUMENTS_SEC:
                try:
                    with open(self.instruments_cache_path, 'rb') as f:
                        self.instruments_df = pickle.load(f)
                    logger.info("Loaded instruments from cache.")
                    self._build_maps()
                    return True
                except Exception as e:
                    logger.warning(f"Cache corrupted, fetching fresh: {e}")

        # Fetch from API
        try:
            logger.info("Downloading instruments master list...")
            instruments = self.kite.instruments("NSE")
            self.instruments_df = pd.DataFrame(instruments)
            
            # Save Cache
            with open(self.instruments_cache_path, 'wb') as f:
                pickle.dump(self.instruments_df, f)
            
            self._build_maps()
            logger.info(f"Instruments loaded: {len(self.instruments_df)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to fetch instruments: {e}")
            return False

    def _build_maps(self):
        """Build optimized Symbol <-> Token maps."""
        if self.instruments_df is None or self.instruments_df.empty:
            return

        # Optimization: Create dicts directly
        # Format: "RELIANCE" -> 738561
        self.token_map = dict(zip(self.instruments_df.tradingsymbol, self.instruments_df.instrument_token))
        self.symbol_map = dict(zip(self.instruments_df.instrument_token, self.instruments_df.tradingsymbol))
        
        # Add "NSE:" prefix support
        for symbol, token in list(self.token_map.items()):
            self.token_map[f"NSE:{symbol}"] = token

    def get_token(self, symbol: str) -> Optional[int]:
        """Get instrument token for a symbol."""
        return self.token_map.get(symbol)

    def get_symbol(self, token: int) -> Optional[str]:
        """Get symbol for a token."""
        return self.symbol_map.get(token)

    # ══════════════════════════════════════════════════════════════════════════
    # MARKET DATA (REST)
    # ══════════════════════════════════════════════════════════════════════════

    def get_quote(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Fetch full market quote (Depth, OHLC, Limits).
        """
        if not self.is_connected:
            return {}
            
        # Ensure symbols are prefixed with NSE: if raw
        prefixed_symbols = [s if ":" in s else f"NSE:{s}" for s in symbols]
        
        try:
            # Note: Kite allows max 500 symbols per call.
            # We assume batching is handled by caller or list is small.
            return self.kite.quote(prefixed_symbols)
        except Exception as e:
            logger.error(f"Quote fetch failed: {e}")
            return {}

    def get_historical(self, token: int, from_date: datetime, to_date: datetime, interval: str) -> List[Dict]:
        """
        Fetch historical candles.
        
        Args:
            interval: 'minute', 'day', '5minute', etc.
        """
        if not self.is_connected:
            return []

        try:
            data = self.kite.historical_data(
                instrument_token=token,
                from_date=from_date,
                to_date=to_date,
                interval=interval
            )
            return data
        except Exception as e:
            logger.error(f"Historical data failed for {token}: {e}")
            return []

    # ══════════════════════════════════════════════════════════════════════════
    # WEBSOCKET (LIVE DATA)
    # ══════════════════════════════════════════════════════════════════════════

    def start_ticker(self, 
                     tokens: List[int], 
                     on_ticks: Any, 
                     on_connect: Any = None, 
                     mode: str = "full") -> bool:
        """
        Start WebSocket ticker.
        
        Args:
            tokens: List of instrument tokens to subscribe.
            on_ticks: Callback function(ws, ticks).
            mode: 'ltp', 'quote', or 'full'.
        """
        if not self.api_key or not self.access_token:
            return False

        try:
            self.ticker = KiteTicker(self.api_key, self.access_token)
            
            # Wrapper to handle ticks and update buffer
            def _on_ticks(ws, ticks):
                for tick in ticks:
                    self.live_ticks[tick['instrument_token']] = tick
                if on_ticks:
                    on_ticks(ws, ticks)

            # Wrapper to handle subscription on connect
            def _on_connect(ws, response):
                logger.info("WebSocket Connected.")
                self.is_ws_connected = True
                
                if tokens:
                    ws.subscribe(tokens)
                    if mode == "full":
                        ws.set_mode(ws.MODE_FULL, tokens)
                    elif mode == "quote":
                        ws.set_mode(ws.MODE_QUOTE, tokens)
                    else:
                        ws.set_mode(ws.MODE_LTP, tokens)
                    logger.info(f"Subscribed to {len(tokens)} tokens in {mode} mode.")
                
                if on_connect:
                    on_connect(ws, response)

            def _on_close(ws, code, reason):
                logger.warning(f"WebSocket Closed: {code} - {reason}")
                self.is_ws_connected = False

            def _on_error(ws, code, reason):
                logger.error(f"WebSocket Error: {code} - {reason}")

            # Assign callbacks
            self.ticker.on_ticks = _on_ticks
            self.ticker.on_connect = _on_connect
            self.ticker.on_close = _on_close
            self.ticker.on_error = _on_error
            
            # Connect (Non-blocking)
            self.ticker.connect(threaded=True)
            return True

        except Exception as e:
            logger.error(f"Failed to start Ticker: {e}")
            return False

    def stop_ticker(self):
        """Stop the WebSocket connection."""
        if self.ticker:
            self.ticker.close()
            self.ticker = None
            self.is_ws_connected = False
            logger.info("Ticker stopped.")

# Singleton Instance
data_manager = DataManagerV5()
