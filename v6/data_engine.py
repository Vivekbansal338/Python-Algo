"""
================================================================================
V6 DATA ENGINE
================================================================================
The Foundation Layer - Handles all external data interactions and pure math.

Merged from V5:
- core_v5/data_v5.py (DataManager)
- analysis_v5/indicators_v5.py (All indicator functions)

Features:
- Zero dependencies on other V6 modules (except config)
- Optimized Caching (Pickle/JSON)
- Robust Error Handling
- High-performance indicator calculations

Author: Sector Analysis System
Version: 6.0.0
================================================================================
"""

import time
import logging
import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union

import numpy as np

try:
    import pandas as pd
    from kiteconnect import KiteConnect, KiteTicker
except ImportError:
    print("CRITICAL: kiteconnect or pandas not installed.")
    raise

from v6 import config

# Logging setup
logger = logging.getLogger("DataEngine")


# ══════════════════════════════════════════════════════════════════════════════
# TECHNICAL INDICATORS (Pure Math Functions)
# ══════════════════════════════════════════════════════════════════════════════

def calculate_wma(data: np.ndarray, period: int) -> float:
    """
    Calculate Weighted Moving Average for the last 'period' elements.
    WMA = sum(price_i * weight_i) / sum(weights)
    """
    if len(data) < period:
        return 0.0
    
    weights = np.arange(1, period + 1)
    weight_sum = weights.sum()
    if weight_sum == 0:
        return 0.0
    return float(np.dot(data[-period:], weights) / weight_sum)


def calculate_hma(prices: Union[List[float], np.ndarray], period: int) -> float:
    """
    Calculate Hull Moving Average.
    HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))
    """
    prices = np.array(prices)
    if len(prices) < period:
        return 0.0

    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))

    # Calculate series of the raw (2*WMA(n/2) - WMA(n))
    # for the last 'sqrt_period' to then WMA it.
    raw_hma_series = []
    
    for i in range(sqrt_period):
        end_idx = len(prices) - i
        if end_idx < period:
            break
        
        subset = prices[:end_idx]
        wma_half = calculate_wma(subset, half_period)
        wma_full = calculate_wma(subset, period)
        
        raw_hma_series.insert(0, 2 * wma_half - wma_full)

    if len(raw_hma_series) < sqrt_period:
        return raw_hma_series[-1] if raw_hma_series else 0.0

    return calculate_wma(np.array(raw_hma_series), sqrt_period)


def calculate_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 10) -> float:
    """
    Calculate Average True Range (SMA of True Range).
    TR = max(H-L, abs(H-PC), abs(L-PC))
    """
    if len(closes) < period + 1:
        return 0.0

    # Calculate True Ranges
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)
    
    # ATR is SMA of TR
    return float(np.mean(tr_list[-period:]))


def calculate_rsi(closes: np.ndarray, period: int = 14) -> float:
    """Standard RSI calculation."""
    if len(closes) < period + 1:
        return 50.0
    
    deltas = np.diff(closes)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    
    if down == 0:
        rs = 100.0
    else:
        rs = up / down
    
    rsi = np.zeros_like(closes)
    rsi[:period] = 100. - 100. / (1. + rs)

    for i in range(period, len(closes)):
        delta = deltas[i-1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta

        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period

        if down == 0:
            rs = 100.0
        else:
            rs = up / down
        rsi[i] = 100. - 100. / (1. + rs)

    return float(rsi[-1])


def calculate_stoch_rsi(closes: Union[List[float], np.ndarray], 
                        rsi_period: int = 14, 
                        stoch_period: int = 14, 
                        k_smooth: int = 3, 
                        d_smooth: int = 3) -> Tuple[float, float]:
    """
    Calculate Stochastic RSI (K, D).
    Values in range 0-100.
    """
    closes = np.array(closes)
    # Need a series of RSI values with extra history for smoothing
    total_needed = stoch_period + k_smooth + d_smooth + 5
    rsi_series = []
    
    for i in range(total_needed):
        end_idx = len(closes) - i
        if end_idx < rsi_period + 1:
            break
        rsi_series.insert(0, calculate_rsi(closes[:end_idx], rsi_period))
    
    if len(rsi_series) < stoch_period:
        return 50.0, 50.0

    # Calculate Raw StochRSI
    stoch_raw = []
    for i in range(len(rsi_series) - stoch_period + 1):
        window = rsi_series[i : i + stoch_period]
        low = min(window)
        high = max(window)
        curr = window[-1]
        
        if high == low:
            stoch_raw.append(50.0)
        else:
            stoch_raw.append(((curr - low) / (high - low)) * 100)
            
    # Calculate Smooth %K (SMA of raw)
    k_series = []
    for i in range(len(stoch_raw) - k_smooth + 1):
        k_series.append(np.mean(stoch_raw[i : i + k_smooth]))
        
    if not k_series:
        return 50.0, 50.0
        
    # Calculate Smooth %D (SMA of K)
    d = np.mean(k_series[-d_smooth:])
    k = k_series[-1]
    
    return float(k), float(d)


def calculate_rvol(current_vol: int, avg_vol: float) -> float:
    """Calculate Relative Volume."""
    if avg_vol <= 0:
        return 0.0
    return float(current_vol / avg_vol)


def calculate_rs_subtraction(subject_return: float, benchmark_return: float) -> float:
    """
    Relative Strength using subtraction method.
    RS = Subject % - Benchmark %
    """
    return subject_return - benchmark_return


def calculate_return_pct(current: float, previous: float) -> float:
    """Simple percentage return calculation."""
    if previous <= 0:
        return 0.0
    return ((current - previous) / previous) * 100


def calculate_slope(current: float, previous: float, threshold: float = 0.0001) -> str:
    """Determine slope direction: UP, DOWN, or FLAT."""
    if not current or not previous:
        return "FLAT"
    
    diff = current - previous
    if diff > threshold:
        return "UP"
    elif diff < -threshold:
        return "DOWN"
    else:
        return "FLAT"


# ══════════════════════════════════════════════════════════════════════════════
# DATA MANAGER CLASS
# ══════════════════════════════════════════════════════════════════════════════

class DataManager:
    """
    Unified Data Handler for V6.
    Manages Zerodha connection, instruments, historical data, and WebSocket.
    """
    
    def __init__(self):
        self.api_key = config.KITE_API_KEY
        self.access_token = config.KITE_ACCESS_TOKEN
        self.kite: Optional[KiteConnect] = None
        self.ticker: Optional[KiteTicker] = None
        
        # Data Stores
        self.instruments_df: Optional[pd.DataFrame] = None
        self.token_map: Dict[str, int] = {}  # Symbol -> Token
        self.symbol_map: Dict[int, str] = {}  # Token -> Symbol
        self.live_ticks: Dict[int, Dict] = {}  # Token -> Latest Tick
        
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

        # Create dicts directly: "RELIANCE" -> 738561
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
            # Note: Kite allows max 500 symbols per call
            return self.kite.quote(prefixed_symbols)
        except Exception as e:
            logger.error(f"Quote fetch failed: {e}")
            return {}

    def get_historical(self, token: int, from_date: datetime, to_date: datetime, interval: str) -> List[Dict]:
        """
        Fetch historical candles.
        
        Args:
            token: Instrument token
            from_date: Start date
            to_date: End date
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
            on_connect: Optional callback on connection.
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


# ══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

data_manager = DataManager()
