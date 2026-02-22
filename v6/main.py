"""
================================================================================
V6 ORCHESTRATOR + UI (MAIN)
================================================================================
The Master Controller with integrated Rich TUI Dashboard.

MERGED FROM V5:
- main_v5.py → TradingBot orchestrator
- system_v5/ui_v5.py → DashboardUI

Author: Sector Analysis System
Version: 6.0.0
================================================================================
"""

import time
import logging
import signal
import sys
import json
import traceback
from logging.handlers import RotatingFileHandler
import numpy as np
from datetime import datetime, timedelta, time as dt_time
from typing import List, Dict, Any, Tuple

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.align import Align
from rich.style import Style
from rich import box

from v6 import config
from v6.data_engine import data_manager, calculate_hma, calculate_atr, calculate_stoch_rsi, calculate_rvol, calculate_slope
from v6.brain import (
    MarketRegimeDetector, SectorScorer, SectorScore, 
    StockGrader, StockSignal, ExecutionFilters,
    RiskManager, SafetyMonitor
)
from v6.execution import OrderManager, LifecycleManager, StateManager

# Logging to file ONLY
root_logger = logging.getLogger()
if root_logger.handlers:
    root_logger.handlers = []

root_logger.setLevel(logging.INFO)
log_handler = RotatingFileHandler(
    filename=config.LOG_FILE,
    maxBytes=config.LOG_MAX_BYTES,
    backupCount=config.LOG_BACKUP_COUNT,
    encoding="utf-8"
)
log_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
root_logger.addHandler(log_handler)
logger = logging.getLogger("Orchestrator")


# ══════════════════════════════════════════════════════════════════════════════
# UI STYLES & CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

STYLES = {
    "title": Style(color="bright_cyan", bold=True),
    "subtitle": Style(color="cyan"),
    "regime_trending": Style(color="bright_green", bold=True),
    "regime_neutral": Style(color="bright_yellow", bold=True),
    "regime_meanrevert": Style(color="bright_magenta", bold=True),
    "regime_halt": Style(color="bright_red", bold=True, blink=True),
    "session_premarket": Style(color="grey50"),
    "session_wait": Style(color="bright_yellow"),
    "session_main": Style(color="bright_cyan"),
    "session_closing": Style(color="bright_magenta"),
    "session_after": Style(color="grey50"),
    "positive": Style(color="bright_green"),
    "negative": Style(color="bright_red"),
    "neutral": Style(color="white"),
    "grade_a_plus": Style(color="bright_green", bold=True),
    "grade_a": Style(color="green"),
    "grade_b": Style(color="yellow"),
    "grade_c": Style(color="grey50"),
    "gate_pass": Style(color="bright_green"),
    "gate_fail": Style(color="bright_red"),
    "selected": Style(color="bright_cyan", bold=True),
    "unselected": Style(color="white"),
    "bullish": Style(color="bright_green", bold=True),
    "bearish": Style(color="bright_red", bold=True),
    "mixed": Style(color="yellow"),
}

SYMBOLS = {
    "up": "▲", "down": "▼", "flat": "━",
    "check": "✓", "cross": "✗", "star": "★",
    "circle": "●", "diamond": "◆",
    "trending": "📈", "neutral": "📊", "meanrevert": "🔄", "halt": "🛑",
    "bull": "🐂", "bear": "🐻", "rocket": "🚀", "fire": "🔥",
}


# ══════════════════════════════════════════════════════════════════════════════
# UI HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_grade_display(grade: str) -> Text:
    displays = {
        "A+": (STYLES["grade_a_plus"], "A+ ★"),
        "A": (STYLES["grade_a"], "A"),
        "B": (STYLES["grade_b"], "B"),
        "C": (STYLES["grade_c"], "C"),
    }
    style, text = displays.get(grade, (STYLES["grade_c"], grade or "-"))
    return Text(text, style=style)


def get_alignment_display(alignment: str) -> Text:
    if alignment == "BULLISH":
        return Text("BULL", style=STYLES["bullish"])
    elif alignment == "BEARISH":
        return Text("BEAR", style=STYLES["bearish"])
    return Text("MIXED", style=STYLES["mixed"])


def get_gate_display(passed: bool, reason: str = None) -> Text:
    if passed:
        return Text(f"{SYMBOLS['check']} PASS", style=STYLES["gate_pass"])
    return Text(f"{SYMBOLS['cross']} {reason or 'FAIL'}", style=STYLES["gate_fail"])


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD UI CLASS
# ══════════════════════════════════════════════════════════════════════════════

class DashboardUI:
    """Rich TUI Dashboard for the trading bot."""
    
    def __init__(self):
        self.console = Console()
        self.layout = Layout()
        self._init_layout()
        
    def _init_layout(self):
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1)
        )
        self.layout["main"].split_row(
            Layout(name="scanner", ratio=6),
            Layout(name="portfolio", ratio=4)
        )
        self.layout["portfolio"].split_column(
            Layout(name="positions", ratio=1),
            Layout(name="logs", ratio=1)
        )

    def get_regime_style(self, regime: str) -> tuple:
        styles = {
            "TRENDING": (STYLES["regime_trending"], SYMBOLS["trending"], "TRENDING"),
            "NEUTRAL": (STYLES["regime_neutral"], SYMBOLS["neutral"], "NEUTRAL"),
            "MEAN_REVERT": (STYLES["regime_meanrevert"], SYMBOLS["meanrevert"], "MEAN REVERT"),
            "EXTREME": (STYLES["regime_halt"], SYMBOLS["halt"], "EXTREME"),
        }
        return styles.get(regime, (STYLES["neutral"], "?", "UNKNOWN"))

    def get_session_style(self, session: str) -> tuple:
        styles = {
            "PRE_MARKET": (STYLES["session_premarket"], "PRE-MARKET"),
            "WAIT": (STYLES["session_wait"], "WAIT"),
            "MAIN": (STYLES["session_main"], "MAIN SESSION"),
            "EXIT_ONLY": (STYLES["session_closing"], "EXIT ONLY"),
            "FORCE_EXIT": (STYLES["session_closing"], "FORCE EXIT"),
            "AFTER_CLOSE": (STYLES["session_after"], "AFTER CLOSE"),
        }
        return styles.get(session, (STYLES["neutral"], session))

    def format_price_change(self, price: float, change: float) -> Text:
        text = Text()
        text.append(f"{price:,.2f} ", style="white")
        sign = "+" if change > 0 else ""
        color = "positive" if change > 0 else "negative" if change < 0 else "neutral"
        symbol = SYMBOLS["up"] if change > 0 else SYMBOLS["down"] if change < 0 else SYMBOLS["flat"]
        text.append(f"{symbol} {sign}{change:.2f}%", style=STYLES[color])
        return text

    def generate_header(self, session_name: str, regime: str, vix: float,
                        nifty_val: float, nifty_pct: float, mode_str: str,
                        feed_status: str = "WS_LIVE",
                        risk_status: str = "RISK_OK") -> Panel:
        time_str = datetime.now().strftime("%H:%M:%S")
        regime_style, regime_emoji, regime_text = self.get_regime_style(regime)
        session_style, session_text = self.get_session_style(session_name)
        
        header = Text()
        header.append(f"⏰ {time_str} ", style="white")
        header.append("│ ", style="grey50")
        header.append(session_text, style=session_style)
        header.append(" │ ", style="grey50")
        header.append(f"NIFTY ", style="bright_white bold")
        header.append_text(self.format_price_change(nifty_val, nifty_pct))
        header.append(" │ ", style="grey50")
        header.append(f"{regime_emoji} {regime_text}", style=regime_style)
        header.append(" │ ", style="grey50")
        vix_color = "bright_green" if vix < 13 else "yellow" if vix < 18 else "bright_red"
        header.append(f"VIX {vix:.2f} ", style=vix_color)
        header.append(" │ ", style="grey50")
        header.append(mode_str, style="bold cyan")
        header.append(" │ ", style="grey50")
        feed_style = "bright_red" if "DEGRADED" in feed_status else "bright_green"
        header.append(feed_status, style=feed_style)
        header.append(" │ ", style="grey50")
        risk_style = "bright_red" if risk_status != "RISK_OK" else "bright_green"
        header.append(risk_status, style=risk_style)
        
        return Panel(
            Align.center(header),
            title="[bold cyan]📊 V6 AUTONOMOUS BOT[/]",
            border_style="cyan",
            box=box.DOUBLE,
            padding=(0, 1)
        )

    def generate_scanner(self, sectors: list, stocks: list, nifty_pct: float = 0.0) -> Panel:
        # Sector Table
        sec_table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
        sec_table.add_column("#", justify="center", width=2, style="dim")
        sec_table.add_column("Sector", ratio=1)
        sec_table.add_column("Bias", justify="center", width=5)
        sec_table.add_column("Price", justify="right", width=8)
        sec_table.add_column("Day%", justify="right", width=6)
        sec_table.add_column("RS-S", justify="right", width=5, style="cyan")
        sec_table.add_column("RS-3", justify="right", width=5, style="bright_cyan")
        sec_table.add_column("RS-D", justify="right", width=5, style="bright_blue")
        sec_table.add_column("Brdth", justify="right", width=5)
        sec_table.add_column("Mkt", justify="right", width=5, style="dim")
        sec_table.add_column("Score", justify="right", width=5, style="bright_yellow")
        
        nifty_impact = nifty_pct * 30.0
        mkt_style = "bright_green" if nifty_impact > 0 else "bright_red" if nifty_impact < 0 else "dim white"
        
        for s in sectors[:12]:
            rank_text = f"{SYMBOLS['star']}{s.rank}" if s.is_selected else str(s.rank)
            rank_style = "bold bright_cyan" if s.is_selected else "dim"
            name_short = s.symbol.replace("NIFTY ", "").replace("MS ", "")[:10]
            name_style = STYLES["selected"] if s.is_selected else STYLES["unselected"]
            
            chg = s.change_pct
            chg_style = "bright_green" if chg > 0.5 else "bright_red" if chg < -0.5 else "white"
            chg_sym = SYMBOLS["up"] if chg > 0 else SYMBOLS["down"] if chg < 0 else ""
            
            br = s.breadth * 100
            br_style = "bright_green" if br > 20 else "bright_red" if br < -20 else "yellow"
            br_text = f"{br:+.0f}%" if br > 20 else f"{br:.0f}%"
            
            bias = s.bias
            if bias == "LONG":
                sc_style, bias_style, bias_text = "bright_green bold", "bright_green", "LONG"
            elif bias == "SHORT":
                sc_style, bias_style, bias_text = "bright_red bold", "bright_red", "SHRT"
            else:
                sc_style, bias_style, bias_text = "yellow", "dim white", "NEUT"
            
            sec_table.add_row(
                Text(rank_text, style=rank_style),
                Text(name_short, style=name_style),
                Text(bias_text, style=bias_style),
                f"{s.price:,.0f}",
                Text(f"{chg_sym}{chg:+.1f}%", style=chg_style),
                f"{s.structural_rs:+.1f}",
                f"{s.shortterm_rs:+.1f}",
                f"{s.intraday_rs:+.1f}",
                Text(br_text, style=br_style),
                Text(f"{nifty_impact:+.1f}", style=mkt_style),
                Text(f"{s.composite_score:+.1f}", style=sc_style),
            )

        # Stock Table
        stk_table = Table(
            box=box.SIMPLE_HEAD, expand=True,
            title=f"[bold cyan]{SYMBOLS['rocket']} SIGNALS[/]",
            padding=(0, 1)
        )
        stk_table.add_column("#", justify="right", width=2, style="dim")
        stk_table.add_column("Symbol", ratio=1)
        stk_table.add_column("SecBias", justify="center", width=5)
        stk_table.add_column("SecRnk", justify="center", width=6)
        stk_table.add_column("Price", justify="right", width=8)
        stk_table.add_column("Day%", justify="right", width=6)
        stk_table.add_column("StochK", justify="center", width=6)
        stk_table.add_column("Sprd%", justify="center", width=6)
        stk_table.add_column("HMA", justify="center", width=5)
        stk_table.add_column("RVOL", justify="right", width=5)
        stk_table.add_column("Gate", justify="center", width=6)
        stk_table.add_column("Score", justify="center", width=5, style="bright_yellow")
        stk_table.add_column("Grade", justify="center", width=5)
        
        sorted_stocks = sorted(stocks, key=lambda s: s.score, reverse=True)
        
        for rank, s in enumerate(sorted_stocks[:15], 1):
            sym_style = "bold bright_green" if s.multiplier > 0 else "white"
            chg = s.change_pct
            chg_style = "bright_green" if chg > 0 else "bright_red" if chg < 0 else "white"
            chg_sym = SYMBOLS["up"] if chg > 0 else SYMBOLS["down"] if chg < 0 else ""
            hma_disp = get_alignment_display(s.hma_align)
            rvol_style = "bright_green" if s.rvol >= 1.3 else "grey50"
            gate_disp = get_gate_display(s.gate_passed, s.gate_reason[:4] if s.gate_reason else None)
            stoch_style = "bright_red" if s.stoch_k > 80 else "bright_green" if s.stoch_k < 20 else "white"
            sprd_pct = s.spread_atr * 100
            sprd_style = "bright_green" if sprd_pct < 10 else "yellow" if sprd_pct < 20 else "bright_red"

            bias_disp, bias_style = "NEUT", "dim"
            if s.grade in ["A+", "A", "B"]:
                bias_disp = s.direction[:4]
                bias_style = "bright_green" if s.direction == "LONG" else "bright_red"
            elif any("Sector Bias" in r for r in s.reasons):
                bias_disp, bias_style = "OPP", "bright_red"
            else:
                bias_disp = "-"

            stk_table.add_row(
                str(rank),
                Text(s.symbol, style=sym_style),
                Text(bias_disp, style=bias_style),
                str(s.sector_rank),
                f"{s.price:,.1f}",
                Text(f"{chg_sym}{chg:+.1f}%", style=chg_style),
                Text(f"{s.stoch_k:.0f}", style=stoch_style),
                Text(f"{sprd_pct:.0f}%", style=sprd_style),
                hma_disp,
                Text(f"{s.rvol:.1f}x", style=rvol_style),
                gate_disp,
                Text(f"{s.score:.0f}", style="bright_yellow"),
                get_grade_display(s.grade)
            )

        return Panel(Group(sec_table, Text(" "), stk_table), title="📡 Market Scan", border_style="blue")

    def generate_portfolio(self, positions: list, equity: float, pnl: float) -> Panel:
        table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
        table.add_column("Sym", ratio=1)
        table.add_column("Side", justify="center", width=5)
        table.add_column("Qty", justify="right", width=4)
        table.add_column("Entry", justify="right", width=8)
        table.add_column("LTP", justify="right", width=8)
        table.add_column("P&L", justify="right", width=8)
        table.add_column("Stop", justify="right", width=8, style="bright_red")
        table.add_column("Target", justify="right", width=8, style="bright_green")
        table.add_column("Stage", justify="center", width=8)
        
        for p in positions:
            side = "LONG" if p['qty'] > 0 else "SHORT"
            side_style = "bright_green" if side == "LONG" else "bright_red"
            upnl = p.get('unrealized_pnl', 0.0)
            entry_value = abs(p['entry_price'] * p['qty'])
            upnl_pct = (upnl / entry_value * 100) if entry_value > 0 else 0.0
            pnl_style = STYLES["positive"] if upnl >= 0 else STYLES["negative"]
            pnl_text = f"{upnl:+.0f} ({upnl_pct:+.1f}%)"
            stage = p.get('stage', 'N/A')
            stage_style = "bright_cyan" if stage == "PARTIAL" else "white"
            target_val = p.get('target', '-')
            target_disp = f"{target_val:,.1f}" if isinstance(target_val, (int, float)) else str(target_val)
            
            table.add_row(
                p['symbol'],
                Text(side, style=side_style),
                str(abs(int(p['qty']))),
                f"{p['entry_price']:,.1f}",
                f"{p['ltp']:,.1f}",
                Text(pnl_text, style=pnl_style),
                f"{p['current_stop']:,.1f}",
                target_disp,
                Text(stage, style=stage_style)
            )
            
        pnl_style = STYLES["positive"] if pnl >= 0 else STYLES["negative"]
        summary = Text.assemble(
            "💰 Eq: ", (f"₹{equity:,.0f}", "white"),
            " | Day PnL: ", (f"₹{pnl:+.1f}", pnl_style)
        )
        return Panel(table, title=summary, border_style="green")

    def generate_logs(self, logs: list) -> Panel:
        text = Text()
        for log in logs[-10:]:
            if "ENTER" in log:
                style = "bright_cyan"
            elif "EXIT" in log:
                style = "bright_yellow"
            elif "STOP" in log:
                style = "bright_red"
            elif "TARGET" in log:
                style = "bright_green"
            else:
                style = "grey70"
            text.append(log + "\n", style=style)
        return Panel(text, title="📝 Live Logs", border_style="white")

    def update(self, state_data: dict):
        mode = "PAPER 📝" if config.IS_PAPER_TRADING else "LIVE 🔴"
        mode_str = f"{mode} | V6.0.0"
        
        header = self.generate_header(
            state_data['session'], 
            state_data['regime'], 
            state_data['vix'], 
            state_data['nifty'], 
            state_data['nifty_pct'],
            mode_str,
            state_data.get('feed_status', 'WS_LIVE'),
            state_data.get('risk_status', 'RISK_OK')
        )
        self.layout["header"].update(header)
        
        scanner = self.generate_scanner(
            state_data['sectors'], 
            state_data['signals'], 
            state_data.get('nifty_pct', 0.0)
        )
        self.layout["scanner"].update(scanner)
        
        portfolio = self.generate_portfolio(state_data['positions'], state_data['equity'], state_data['pnl'])
        self.layout["positions"].update(portfolio)
        
        logs = self.generate_logs(state_data['logs'])
        self.layout["logs"].update(logs)

    def render(self) -> Layout:
        return self.layout


# ══════════════════════════════════════════════════════════════════════════════
# MAIN TRADING BOT
# ══════════════════════════════════════════════════════════════════════════════

class TradingBotV6:
    """V6 Autonomous Trading Bot."""
    
    def __init__(self):
        self.running = True
        
        # Core Modules
        self.state_mgr = StateManager()
        self.risk = RiskManager()
        self.orders = OrderManager()
        self.lifecycle = LifecycleManager(self.orders)
        self.ui = DashboardUI()
        self.safety = SafetyMonitor()
        
        # Strategy Components
        self.regime_detector = MarketRegimeDetector()
        self.sector_scorer = SectorScorer()
        self.stock_grader = StockGrader()
        
        # Universe Data
        self.indices: List[Dict] = []
        self.stocks: List[Dict] = []
        self.sector_map: Dict[str, List[str]] = {}
        
        # Runtime Metrics
        self.logs = []
        self.current_playbook = "INIT"
        self.vix_percentile = 50.0
        self.vix_multiplier = 1.0
        self.vix_history: List[float] = []
        self.last_ui_update = 0
        self.last_intraday_refresh = 0
        self.last_state_save_ts = time.monotonic()
        self.ws_degraded = False
        self.ws_degraded_reason = ""
        self.last_ws_status_log_ts = 0.0
        self.ws_recovery_candidate_since = 0.0
        self.last_tick_health_log_ts = 0.0
        self.last_tick_health_stats = {"stale_ticks": 0, "missing_ticks": 0}
        self.last_killswitch_reason = ""
        self.after_close_processed = False
        
        # Historical Data Cache
        self.sector_history: Dict[str, List[float]] = {}
        self.nifty_history: List[float] = []
        self.baselines: Dict[str, Dict[str, float]] = {}
        self.stock_history_daily: Dict[str, Dict[str, np.ndarray]] = {}
        self.stock_history_5m: Dict[str, Dict[str, np.ndarray]] = {}
        self.history_loaded = False

        # Current Market State
        self.nifty_ltp = 0.0
        self.vix_ltp = 0.0
        self.nifty_pct = 0.0
        self.nifty_prev_close = 0.0
        self.sector_scores: List[SectorScore] = []
        self.active_signals: List[StockSignal] = []
        self.last_quotes: Dict[str, Any] = {}
        
        # Cooldown for rejected symbols
        self.rejected_symbols: Dict[str, float] = {}
        
        # Signal Handlers
        signal.signal(signal.SIGINT, self.shutdown)

    def log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        self.logs.append(entry)
        logger.info(msg)

    def _log_ws_status(self, message: str, force: bool = False):
        """Throttle repetitive websocket health logs."""
        now = time.monotonic()
        if force or (now - self.last_ws_status_log_ts) >= 15:
            self.log(message)
            self.last_ws_status_log_ts = now

    def _build_trade_exposure_maps(self) -> Tuple[Dict[str, int], Dict[str, int]]:
        """Build symbol and sector exposure maps from active lifecycle trades."""
        symbol_exposure: Dict[str, int] = {}
        sector_exposure: Dict[str, int] = {}

        for trade in self.lifecycle.trades.values():
            if trade.stage == "CLOSED":
                continue
            symbol_exposure[trade.symbol] = symbol_exposure.get(trade.symbol, 0) + 1

            pos = self.orders.paper_positions.get(trade.symbol, {})
            sector = pos.get("sector", "UNKNOWN")
            sector_exposure[sector] = sector_exposure.get(sector, 0) + 1

        return symbol_exposure, sector_exposure

    def _ensure_daily_baselines(self, source: str):
        """Ensure daily baseline fields are initialized and coherent."""
        reference_equity = self.risk.state.equity
        if reference_equity <= 0:
            reference_equity = self.risk.state.starting_equity
        if reference_equity <= 0:
            reference_equity = config.DEFAULT_PAPER_EQUITY

        if self.risk.state.starting_equity <= 0:
            self.risk.state.starting_equity = reference_equity

        if self.risk.state.daily_start_equity <= 0:
            self.risk.state.daily_start_equity = reference_equity

        if self.risk.state.daily_high_equity <= 0:
            self.risk.state.daily_high_equity = reference_equity
        else:
            self.risk.state.daily_high_equity = max(self.risk.state.daily_high_equity, reference_equity)

        self.log(
            f"⚓ Daily baseline ({source}): start=₹{self.risk.state.daily_start_equity:,.0f}, "
            f"high=₹{self.risk.state.daily_high_equity:,.0f}, "
            f"starting=₹{self.risk.state.starting_equity:,.0f}"
        )

    def _maybe_log_tick_health(self, now_monotonic: float):
        """Periodic observability for stale/missing tick filtering."""
        if (now_monotonic - self.last_tick_health_log_ts) < 60:
            return

        stats = data_manager.get_tick_health_stats()
        stale_now = stats.get("stale_ticks", 0)
        missing_now = stats.get("missing_ticks", 0)
        stale_prev = self.last_tick_health_stats.get("stale_ticks", 0)
        missing_prev = self.last_tick_health_stats.get("missing_ticks", 0)

        if stale_now != stale_prev or missing_now != missing_prev:
            self.log(
                f"📡 Tick Health | fresh={stats.get('fresh_ticks', 0)} "
                f"stale={stale_now} missing={missing_now}"
            )

        self.last_tick_health_stats = {
            "stale_ticks": stale_now,
            "missing_ticks": missing_now
        }
        self.last_tick_health_log_ts = now_monotonic

    def load_universe(self):
        self.log("📂 Loading Universe...")
        if not config.UNIVERSE_PATH.exists():
            self.log("❌ universe.json not found!")
            sys.exit(1)
            
        with open(config.UNIVERSE_PATH, 'r') as f:
            data = json.load(f)
            self.indices = data.get('indices', [])
            self.stocks = [s for s in data.get('stocks', []) if s.get('token')]
            
        for s in self.stocks:
            for sector in s.get('indices', []):
                if sector not in self.sector_map:
                    self.sector_map[sector] = []
                self.sector_map[sector].append(s['symbol'])
        
        self.log(f"✅ Loaded {len(self.stocks)} stocks in {len(self.sector_map)} sectors.")

    def _filter_incomplete_candle(self, candles: List[Dict], interval_minutes: int = 5) -> List[Dict]:
        if not candles:
            return []
        last_candle = candles[-1]
        last_time = last_candle.get('date')
        now = datetime.now()
        if isinstance(last_time, datetime):
            if last_time.tzinfo is not None:
                last_time = last_time.replace(tzinfo=None)
            time_diff = now - last_time
            if time_diff.total_seconds() < interval_minutes * 60:
                return candles[:-1]
        return candles

    def fetch_history(self):
        self.log("📉 Fetching Historical Data (Nifty + Sectors)...")
        to_date = datetime.now()
        from_date = to_date - timedelta(days=45)
        
        nifty_token = 256265
        nifty_data = data_manager.get_historical(nifty_token, from_date, to_date, "day")
        if nifty_data:
            self.nifty_history = [d['close'] for d in nifty_data]
            
        for idx in self.indices:
            name = idx['name']
            if name in ["NIFTY 50", "INDIA VIX"]:
                continue
            token = data_manager.get_token(f"NSE:{idx['symbol']}")
            if token:
                data = data_manager.get_historical(token, from_date, to_date, "day")
                if data:
                    self.sector_history[idx['symbol']] = [d['close'] for d in data]
        
        self.history_loaded = True
        self.log(f"✅ History loaded for {len(self.sector_history)} sectors.")

    def fetch_stock_history(self, symbols: List[str]):
        if not symbols:
            return
        
        self.log(f"📥 Fetching history for {len(symbols)} stocks...")
        to_date = datetime.now()
        from_date_daily = to_date - timedelta(days=config.LOOKBACK_DAYS_DAILY)
        from_date_5m = to_date - timedelta(days=config.LOOKBACK_DAYS_INTRA)
        
        for sym in symbols:
            token = data_manager.get_token(f"NSE:{sym}")
            if not token:
                continue
            
            d_data = data_manager.get_historical(token, from_date_daily, to_date, "day")
            if d_data:
                self.stock_history_daily[sym] = {
                    'high': np.array([d['high'] for d in d_data]),
                    'low': np.array([d['low'] for d in d_data]),
                    'close': np.array([d['close'] for d in d_data]),
                    'volume': np.array([d['volume'] for d in d_data])
                }
            
            raw_m_data = data_manager.get_historical(token, from_date_5m, to_date, "5minute")
            m_data = self._filter_incomplete_candle(raw_m_data)
            if m_data:
                self.stock_history_5m[sym] = {
                    'close': np.array([d['close'] for d in m_data]),
                    'volume': np.array([d['volume'] for d in m_data])
                }

    def _refresh_intraday_history(self, symbols: List[str]):
        if not symbols:
            return
        
        self.log(f"🔄 Refreshing 5m history for {len(symbols)} stocks...")
        to_date = datetime.now()
        from_date_5m = to_date - timedelta(days=config.LOOKBACK_DAYS_INTRA)
        
        refreshed_count = 0
        for sym in symbols:
            token = data_manager.get_token(f"NSE:{sym}")
            if not token:
                continue
            raw_m_data = data_manager.get_historical(token, from_date_5m, to_date, "5minute")
            m_data = self._filter_incomplete_candle(raw_m_data)
            if m_data:
                self.stock_history_5m[sym] = {
                    'close': np.array([d['close'] for d in m_data]),
                    'volume': np.array([d['volume'] for d in m_data])
                }
                refreshed_count += 1
        
        self.log(f"✅ Refreshed 5m history for {refreshed_count} stocks.")

    def _get_hma_alignment(self, sym: str, current_price: float) -> str:
        daily = self.stock_history_daily.get(sym)
        m5 = self.stock_history_5m.get(sym)
        
        if daily is None or m5 is None:
            return "MIXED"
        
        closes_d = np.append(daily['close'], current_price)
        closes_5m = np.append(m5['close'], current_price)
        
        hma9_curr = calculate_hma(closes_d, 9)
        hma9_prev = calculate_hma(closes_d[:-1], 9)
        hma20_curr = calculate_hma(closes_5m, 20)
        hma20_prev = calculate_hma(closes_5m[:-1], 20)
        
        h9_bull = (current_price > hma9_curr and calculate_slope(hma9_curr, hma9_prev) == "UP")
        h20_bull = (current_price > hma20_curr and calculate_slope(hma20_curr, hma20_prev) == "UP")
        h9_bear = (current_price < hma9_curr and calculate_slope(hma9_curr, hma9_prev) == "DOWN")
        h20_bear = (current_price < hma20_curr and calculate_slope(hma20_curr, hma20_prev) == "DOWN")
        
        if h9_bull and h20_bull:
            return "BULLISH"
        if h9_bear and h20_bear:
            return "BEARISH"
        return "MIXED"

    def _calculate_baselines(self):
        self.log("⚓ Calculating Baselines (Previous Close Anchor)...")
        
        if len(self.nifty_history) >= 20:
            self.baselines['NIFTY 50'] = {
                'close_20d': self.nifty_history[-20],
                'close_3d': self.nifty_history[-3],
                'prev_close': self.nifty_history[-1]
            }
            self.nifty_prev_close = self.nifty_history[-1]
            
        for sym, hist in self.sector_history.items():
            if len(hist) >= 20:
                self.baselines[sym] = {
                    'close_20d': hist[-20],
                    'close_3d': hist[-3],
                    'prev_close': hist[-1]
                }

    def _fetch_initial_quotes(self):
        self.log("🎯 Fetching Initial Quotes (Golden Anchor)...")
        
        all_symbols = ["NIFTY 50", "INDIA VIX"]
        all_symbols.extend([i['symbol'] for i in self.indices if i['name'] not in ["NIFTY 50", "INDIA VIX"]])
        
        quotes = data_manager.get_quote(all_symbols)
        
        for sym_key, quote_data in quotes.items():
            sym = sym_key.replace("NSE:", "")
            ohlc = quote_data.get('ohlc', {})
            prev_close = ohlc.get('close', 0)
            
            if prev_close > 0:
                if sym not in self.baselines:
                    self.baselines[sym] = {}
                self.baselines[sym]['prev_close'] = prev_close
                
                if sym == "NIFTY 50":
                    self.nifty_prev_close = prev_close
        
        self.log(f"✅ Fetched anchors for {len(quotes)} symbols.")

    def initialize(self):
        self.log("🚀 Initializing V6 Bot...")
        
        if not data_manager.connect():
            self.log("❌ Connection Failed.")
            sys.exit(1)
            
        data_manager.load_instruments()
        self.load_universe()

        if self.state_mgr.load_state():
            self.state_mgr.restore_system(self.risk, self.lifecycle, self.orders)
            restored_starting = self.risk.state.starting_equity if self.risk.state.starting_equity > 0 else config.DEFAULT_PAPER_EQUITY
            self.risk.state.starting_equity = restored_starting
            restored_equity = restored_starting + self.orders.realized_pnl
            self.risk.update_account(
                restored_equity,
                self.orders.realized_pnl,
                self.orders.get_positions(),
                realized_pnl=self.orders.realized_pnl,
                unrealized_pnl=0.0
            )
            self._ensure_daily_baselines("restored")
            self.log(
                f"✅ State Restored. Equity: ₹{self.risk.state.equity:,.0f} "
                f"(Realized: ₹{self.orders.realized_pnl:+,.0f})"
            )
        else:
            self.log("🆕 Starting Fresh Session.")
            self.orders.realized_pnl = 0.0
            self.risk.state.starting_equity = config.DEFAULT_PAPER_EQUITY
            self.risk.update_account(
                config.DEFAULT_PAPER_EQUITY,
                0.0,
                [],
                realized_pnl=0.0,
                unrealized_pnl=0.0
            )
            self._ensure_daily_baselines("initialized")

        self.log("📈 Fetching VIX history...")
        vix_token = 264969
        hist = data_manager.get_historical(vix_token, datetime.now() - timedelta(days=config.LOOKBACK_DAYS_VIX), datetime.now(), "day")
        self.vix_history = [d['close'] for d in hist]
        
        self.fetch_history()
        self._calculate_baselines()
        self._fetch_initial_quotes()
        
        all_tokens = [256265, 264969]
        all_tokens.extend([data_manager.get_token(f"NSE:{i['symbol']}") for i in self.indices if i['token']])
        all_tokens.extend([int(s['token']) for s in self.stocks if s.get('token')])
        
        valid_tokens = [t for t in all_tokens if t]
        data_manager.start_ticker(valid_tokens, on_ticks=None, mode="full")
        
        self.log(f"📡 WebSocket Started for {len(valid_tokens)} instruments.")
        self.log("✅ System Ready.")

    def get_playbook(self, now: dt_time) -> str:
        if now < config.MARKET_OPEN_TIME:
            return "PRE_MARKET"
        if now < config.ENTRY_START_TIME:
            return "WAIT"
        if now < config.ENTRY_CUTOFF_TIME:
            return "MAIN"
        if now < config.FORCE_EXIT_TIME:
            return "EXIT_ONLY"
        if now < config.MARKET_CLOSE_TIME:
            return "FORCE_EXIT"
        return "AFTER_CLOSE"

    def _update_sector_ranks(self, quotes: Dict, nifty_quote: Dict, regime: str):
        new_scores = []
        
        if len(self.nifty_history) < 20:
            return
        
        nifty_tick = data_manager.get_fresh_tick(256265, config.TICK_MAX_AGE_SEC) or {}
        nifty_ltp = nifty_tick.get('last_price', nifty_quote.get('last_price', 0))
        
        nifty_prev_close = self.baselines.get('NIFTY 50', {}).get('prev_close', 0)
        nifty_hist_20 = self.nifty_history[-20]
        nifty_hist_3 = self.nifty_history[-3]
        
        if nifty_hist_20 == 0 or nifty_hist_3 == 0 or nifty_prev_close == 0:
            return

        nifty_20d_ret = (nifty_ltp - nifty_hist_20) / nifty_hist_20 if nifty_hist_20 != 0 else 0.0
        nifty_3d_ret = (nifty_ltp - nifty_hist_3) / nifty_hist_3 if nifty_hist_3 != 0 else 0.0
        nifty_daily_ret = (nifty_ltp - nifty_prev_close) / nifty_prev_close if nifty_prev_close > 0 else 0.0
        
        for idx in self.indices:
            name = idx['name']
            symbol = idx['symbol']
            if name in ["NIFTY 50", "INDIA VIX"]:
                continue
            
            token = data_manager.get_token(f"NSE:{symbol}")
            tick = data_manager.get_fresh_tick(token, config.TICK_MAX_AGE_SEC) or {}
            q = quotes.get(f"NSE:{symbol}", {})
            
            curr = tick.get('last_price', q.get('last_price', 0))
            
            sec_base = self.baselines.get(symbol, {})
            sec_prev_close = sec_base.get('prev_close', 0)
            
            hist = self.sector_history.get(symbol, [])
            if len(hist) < 20:
                continue
            
            hist_20 = hist[-20]
            hist_3 = hist[-3]
            if hist_20 == 0 or hist_3 == 0 or sec_prev_close == 0:
                continue

            sec_20d_ret = (curr - hist_20) / hist_20 if hist_20 != 0 else 0.0
            sec_3d_ret = (curr - hist_3) / hist_3 if hist_3 != 0 else 0.0
            sec_daily_ret = (curr - sec_prev_close) / sec_prev_close if sec_prev_close > 0 else 0.0
            
            struct_rs = (sec_20d_ret - nifty_20d_ret) * 100
            short_rs = (sec_3d_ret - nifty_3d_ret) * 100
            daily_rs = (sec_daily_ret - nifty_daily_ret) * 100
            
            constituents = self.sector_map.get(name, [])
            valid_stocks = above_vwap = below_vwap = 0
            
            for sym in constituents:
                stk_token = data_manager.get_token(f"NSE:{sym}")
                stk_tick = data_manager.get_fresh_tick(stk_token, config.TICK_MAX_AGE_SEC)
                
                if stk_tick and stk_tick.get('average_price', 0) > 0:
                    valid_stocks += 1
                    if stk_tick['last_price'] > stk_tick['average_price']:
                        above_vwap += 1
                    elif stk_tick['last_price'] < stk_tick['average_price']:
                        below_vwap += 1
            
            net_breadth = (above_vwap / valid_stocks) - (below_vwap / valid_stocks) if valid_stocks > 0 else 0.0
            
            score = SectorScore(
                symbol=symbol,
                price=curr,
                change_pct=sec_daily_ret * 100,
                structural_rs=struct_rs,
                shortterm_rs=short_rs,
                intraday_rs=daily_rs,
                breadth=net_breadth
            )
            new_scores.append(score)
            
        self.sector_scores = self.sector_scorer.score_all(new_scores, regime, self.nifty_pct)
        self.sector_scorer.select_top_n(self.sector_scores)

    def _scan_tradeable_stocks(self, regime: str, vix_ltp: float):
        selected_sector_symbols = [s.symbol for s in self.sector_scores if s.is_selected]
        if not selected_sector_symbols:
            return
        
        sector_info = {s.symbol: s for s in self.sector_scores}
        
        all_candidate_symbols = []
        for sec_sym in selected_sector_symbols:
            sec_name = next((i['name'] for i in self.indices if i['symbol'] == sec_sym), None)
            if sec_name:
                all_candidate_symbols.extend(self.sector_map.get(sec_name, []))
        
        for active_sym in self.risk.state.active_symbols:
            if active_sym not in all_candidate_symbols:
                all_candidate_symbols.append(active_sym)
            
        missing_hist = [s for s in all_candidate_symbols if s not in self.stock_history_daily]
        if missing_hist:
            self.fetch_stock_history(missing_hist)
            
        can_enter = self.current_playbook == "MAIN"
        
        self.active_signals = []
        for symbol in all_candidate_symbols:
            token = data_manager.get_token(f"NSE:{symbol}")
            tick = data_manager.get_fresh_tick(token, config.TICK_MAX_AGE_SEC)
            hist = self.stock_history_daily.get(symbol)
            
            if not tick or not hist:
                continue
            
            adv = ExecutionFilters.calculate_adv_crores(hist['close'], hist['volume'])
            if adv < config.MIN_ADV_CRORES:
                continue

            curr_p = tick['last_price']
            atr = calculate_atr(hist['high'], hist['low'], hist['close'], 10)
            if atr <= 0:
                continue
            
            passed, reason = ExecutionFilters.check_gate(
                tick.get('depth', {}).get('buy', [{}])[0].get('price', 0),
                tick.get('depth', {}).get('sell', [{}])[0].get('price', 0),
                curr_p, atr, 
                tick.get('upper_circuit_limit', 0), tick.get('lower_circuit_limit', 0)
            )
            
            hma_align = self._get_hma_alignment(symbol, curr_p)
            stoch_k, _ = calculate_stoch_rsi(np.append(hist['close'], curr_p))
            
            hist_5m = self.stock_history_5m.get(symbol)
            if hist_5m and len(hist_5m['volume']) >= 20:
                recent_vols = hist_5m['volume'][-20:]
                avg_vol_20 = np.mean(recent_vols)
                last_closed_vol = hist_5m['volume'][-1]
                rvol = calculate_rvol(last_closed_vol, avg_vol_20) if avg_vol_20 > 0 else 0.0
            else:
                rvol = 0.0
            
            stock_sector_name = next((sec for sec, syms in self.sector_map.items() if symbol in syms), "")
            stock_sector_sym = next((i['symbol'] for i in self.indices if i['name'] == stock_sector_name), "")
            
            sec_score_obj = sector_info.get(stock_sector_sym)
            sec_rank = sec_score_obj.rank if sec_score_obj else 16
            sec_bias = sec_score_obj.bias if sec_score_obj else "NEUTRAL"
            
            bid = tick.get('depth', {}).get('buy', [{}])[0].get('price', 0)
            ask = tick.get('depth', {}).get('sell', [{}])[0].get('price', 0)
            spread_atr = (ask - bid) / atr if (ask > 0 and bid > 0 and atr > 0) else 1.0
            
            signal = self.stock_grader.calculate_grade(
                hma_align=hma_align,
                rvol=rvol,
                stoch_k=stoch_k,
                sector_rank=sec_rank,
                spread_atr=spread_atr,
                vix_pctl=self.vix_percentile
            )
            
            if sec_bias == "LONG" and signal.direction != "LONG":
                signal.grade = "C"
                signal.reasons.append(f"Sector Bias LONG vs Signal {signal.direction}")
            elif sec_bias == "SHORT" and signal.direction != "SHORT":
                signal.grade = "C"
                signal.reasons.append(f"Sector Bias SHORT vs Signal {signal.direction}")
            elif sec_bias == "NEUTRAL":
                signal.grade = "C"
                signal.reasons.append("Sector Bias NEUTRAL")

            signal.symbol = symbol
            signal.sector = stock_sector_name
            signal.price = curr_p
            
            stock_prev_close = tick.get('ohlc', {}).get('close', 0)
            signal.change_pct = ((curr_p - stock_prev_close) / stock_prev_close * 100) if stock_prev_close > 0 else 0.0
            
            signal.gate_passed = passed
            signal.gate_reason = reason
            
            self.active_signals.append(signal)
            
            if signal.grade in ["A+", "A"] and passed and can_enter:
                self._process_entry(signal, curr_p, atr)

    def _process_entry(self, signal: StockSignal, ltp: float, atr: float):
        if signal.symbol in self.rejected_symbols:
            if time.time() - self.rejected_symbols[signal.symbol] < 300:
                return
            else:
                del self.rejected_symbols[signal.symbol]

        allowed, reason = self.risk.can_open_new_trade(signal.symbol, signal.sector)
        if not allowed:
            return
            
        stop_mult = config.STOP_ATR_MULT
        stop_dist = atr * stop_mult
        stop_price = ltp - stop_dist if signal.direction == "LONG" else ltp + stop_dist
        
        sizing = self.risk.calculate_position_size(
            ltp, stop_price, signal.grade, self.vix_multiplier, datetime.now().time()
        )
        
        if sizing.is_allowed:
            self.log(
                f"🔥 ENTERING {signal.symbol} ({signal.grade}) Qty: {sizing.shares} "
                f"| VIXPCTL {self.vix_percentile:.1f} | VIX_MULT {self.vix_multiplier:.2f}"
            )
            trade_id = self.lifecycle.initiate_trade(
                signal.symbol, signal.direction, sizing.shares, ltp, stop_price, atr=atr, sector=signal.sector
            )
            
            if trade_id:
                if signal.symbol not in self.risk.state.active_symbols:
                    self.risk.state.active_symbols.append(signal.symbol)
                self.risk.state.open_positions_count += 1
                self.risk.state.symbol_exposure[signal.symbol] = self.risk.state.symbol_exposure.get(signal.symbol, 0) + 1
                self.risk.state.sector_exposure[signal.sector] = self.risk.state.sector_exposure.get(signal.sector, 0) + 1
        else:
            self.log(f"⚠️ Size Rejected {signal.symbol}: {sizing.reason}")
            self.rejected_symbols[signal.symbol] = time.time()

    def _recalculate_live_metrics(self, fallback_quotes: Dict[str, Dict[str, Any]] = None):
        fallback_quotes = fallback_quotes or {}

        nifty_tick = data_manager.get_fresh_tick(256265, config.TICK_MAX_AGE_SEC)
        vix_tick = data_manager.get_fresh_tick(264969, config.TICK_MAX_AGE_SEC)

        if nifty_tick:
            self.nifty_ltp = nifty_tick.get('last_price', self.nifty_ltp)
        else:
            n_quote = fallback_quotes.get("NSE:NIFTY 50", {})
            self.nifty_ltp = n_quote.get('last_price', self.nifty_ltp)

        if vix_tick:
            self.vix_ltp = vix_tick.get('last_price', self.vix_ltp)
        else:
            v_quote = fallback_quotes.get("NSE:INDIA VIX", {})
            self.vix_ltp = v_quote.get('last_price', self.vix_ltp)
        
        n_base = self.baselines.get('NIFTY 50', {})
        if not n_base or self.nifty_ltp == 0:
            return
        
        n_c20 = n_base.get('close_20d', 0)
        n_c3 = n_base.get('close_3d', 0)
        n_prev_close = n_base.get('prev_close', 0)
        if n_c20 == 0 or n_c3 == 0 or n_prev_close == 0:
            return

        n_ret_20d = (self.nifty_ltp - n_c20) / n_c20 if n_c20 != 0 else 0.0
        n_ret_3d = (self.nifty_ltp - n_c3) / n_c3 if n_c3 != 0 else 0.0
        n_ret_daily = (self.nifty_ltp - n_prev_close) / n_prev_close if n_prev_close > 0 else 0.0
        self.nifty_pct = n_ret_daily * 100

        for s in self.sector_scores:
            token = data_manager.get_token(f"NSE:{s.symbol}")
            tick = data_manager.get_fresh_tick(token, config.TICK_MAX_AGE_SEC)
            q = fallback_quotes.get(f"NSE:{s.symbol}", {})
            if tick:
                s.price = tick.get('last_price', s.price)
            elif q:
                s.price = q.get('last_price', s.price)
            else:
                continue
            
            base = self.baselines.get(s.symbol, {})
            if not base:
                continue
            
            s_c20 = base.get('close_20d', 0)
            s_c3 = base.get('close_3d', 0)
            s_prev_close = base.get('prev_close', 0)
            
            if s_c20 == 0 or s_c3 == 0 or s_prev_close == 0:
                continue

            s_ret_20d = (s.price - s_c20) / s_c20 if s_c20 != 0 else 0.0
            s_ret_3d = (s.price - s_c3) / s_c3 if s_c3 != 0 else 0.0
            s_ret_daily = (s.price - s_prev_close) / s_prev_close if s_prev_close > 0 else 0.0
            
            s.structural_rs = (s_ret_20d - n_ret_20d) * 100
            s.shortterm_rs = (s_ret_3d - n_ret_3d) * 100
            s.intraday_rs = (s_ret_daily - n_ret_daily) * 100
            s.change_pct = s_ret_daily * 100
            
            constituents = self.sector_map.get(next((i['name'] for i in self.indices if i['symbol'] == s.symbol), ""), [])
            valid = above = below = 0
            for sym in constituents:
                stk_token = data_manager.get_token(f"NSE:{sym}")
                stk_tick = data_manager.get_fresh_tick(stk_token, config.TICK_MAX_AGE_SEC) or {}
                if stk_tick and stk_tick.get('average_price', 0) > 0:
                    valid += 1
                    if stk_tick['last_price'] > stk_tick['average_price']:
                        above += 1
                    elif stk_tick['last_price'] < stk_tick['average_price']:
                        below += 1
            
            if valid > 0:
                s.breadth = (above / valid) - (below / valid)

        regime = self.regime_detector.get_regime(self.vix_percentile)
        self.sector_scores = self.sector_scorer.score_all(self.sector_scores, regime, self.nifty_pct)
        self.sector_scorer.select_top_n(self.sector_scores)

    def run(self):
        self.initialize()

        quote_symbols = ["NIFTY 50", "INDIA VIX"]
        quote_symbols.extend([i['symbol'] for i in self.indices if i['name'] not in ["NIFTY 50", "INDIA VIX"]])
        market_quotes = data_manager.get_quote(quote_symbols)
        self.last_quotes.update(market_quotes)

        nifty_quote = market_quotes.get("NSE:NIFTY 50", {})
        regime = self.regime_detector.get_regime(self.vix_percentile)
        self._update_sector_ranks(market_quotes, nifty_quote, regime)
        self.last_state_save_ts = time.monotonic()

        with Live(self.ui.render(), refresh_per_second=4, screen=True) as live:
            while self.running:
                try:
                    now_monotonic = time.monotonic()
                    now_dt = datetime.now()
                    self.current_playbook = self.get_playbook(now_dt.time())

                    if self.current_playbook == "AFTER_CLOSE":
                        if not self.after_close_processed:
                            self.log("📪 AFTER_CLOSE reached. Executing final housekeeping.")
                            self.lifecycle.force_exit_all()
                            self.state_mgr.save_state(self.risk, self.lifecycle, self.orders)
                            self.after_close_processed = True
                        if config.AUTO_SHUTDOWN_AFTER_CLOSE:
                            self.running = False
                            break
                        time.sleep(1)
                        continue

                    # Periodic 5m history refresh
                    if now_monotonic - self.last_intraday_refresh >= config.INTRADAY_REFRESH_INTERVAL_SEC:
                        refresh_symbols = []
                        for s in self.sector_scores:
                            if s.is_selected:
                                sec_name = next((i['name'] for i in self.indices if i['symbol'] == s.symbol), None)
                                if sec_name:
                                    refresh_symbols.extend(self.sector_map.get(sec_name, []))
                        refresh_symbols.extend(self.risk.state.active_symbols)
                        refresh_symbols = list(set(refresh_symbols))

                        if refresh_symbols:
                            self._refresh_intraday_history(refresh_symbols)
                        self.last_intraday_refresh = now_monotonic

                    # High-Speed Metrics Recalculation
                    if now_monotonic - self.last_ui_update >= config.UI_REFRESH_INTERVAL:
                        degraded_now, ws_reason, _ = data_manager.get_ws_health(config.WS_STALE_FEED_SEC)
                        if degraded_now:
                            data_manager.attempt_reconnect()
                            self.ws_recovery_candidate_since = 0.0
                            if (not self.ws_degraded) or (ws_reason != self.ws_degraded_reason):
                                self._log_ws_status(f"⚠️ WS_DEGRADED: {ws_reason}. New entries paused.", force=True)
                            else:
                                self._log_ws_status(f"⚠️ WS_DEGRADED: {ws_reason}. New entries paused.")
                            self.ws_degraded = True
                            self.ws_degraded_reason = ws_reason
                        elif self.ws_degraded:
                            if self.ws_recovery_candidate_since == 0.0:
                                self.ws_recovery_candidate_since = now_monotonic

                            stable_for = now_monotonic - self.ws_recovery_candidate_since
                            if stable_for >= config.WS_RECOVERY_STABLE_SEC:
                                self.ws_degraded = False
                                self.ws_degraded_reason = ""
                                self.ws_recovery_candidate_since = 0.0
                                data_manager.mark_recovered()
                                self._log_ws_status("✅ WS_RECOVERED: stable tick flow restored.", force=True)
                            else:
                                self._log_ws_status(
                                    f"⏳ WS_RECOVERING: stable for {stable_for:.0f}s / "
                                    f"{config.WS_RECOVERY_STABLE_SEC:.0f}s."
                                )

                        fallback_metrics_quotes = {}
                        if self.ws_degraded:
                            fallback_metrics_quotes = data_manager.get_quote(["NIFTY 50", "INDIA VIX"])

                        self._recalculate_live_metrics(fallback_metrics_quotes)

                        self.vix_percentile = self.regime_detector.calculate_percentile(self.vix_ltp, self.vix_history)
                        self.vix_multiplier = self.regime_detector.get_vix_multiplier(self.vix_percentile)

                        kill_halt, kill_reason = self.risk.check_kill_switches(self.vix_percentile)
                        if kill_halt and kill_reason != self.last_killswitch_reason:
                            self.log(f"🛑 KILL SWITCH: {kill_reason}")
                            self.last_killswitch_reason = kill_reason
                            if config.FORCE_LIQUIDATE_ON_KILLSWITCH:
                                self.lifecycle.force_exit_all()
                        elif not kill_halt:
                            self.last_killswitch_reason = ""

                        self.safety.update(self.nifty_ltp, self.vix_ltp, 0.0)
                        if self.safety.is_halted:
                            self.log(f"🛑 HALTED: {self.safety.halt_reason}")
                            self.lifecycle.force_exit_all()
                        elif kill_halt:
                            self.active_signals = []
                        elif self.ws_degraded:
                            self.active_signals = []
                        else:
                            self._scan_tradeable_stocks(
                                self.regime_detector.get_regime(self.vix_percentile),
                                self.vix_ltp
                            )

                        self._maybe_log_tick_health(now_monotonic)
                        self.last_ui_update = now_monotonic

                    # Update Lifecycle (Exits/Trailing)
                    active_trades_data = {}
                    active_trade_symbols = [
                        trade.symbol for trade in self.lifecycle.trades.values() if trade.stage != "CLOSED"
                    ]
                    fallback_trade_quotes = {}
                    if self.ws_degraded and active_trade_symbols:
                        fallback_trade_quotes = data_manager.get_quote(list(set(active_trade_symbols)))

                    for trade in self.lifecycle.trades.values():
                        if trade.stage != "CLOSED":
                            token = data_manager.get_token(f"NSE:{trade.symbol}")
                            tick = data_manager.get_fresh_tick(token, config.TICK_MAX_AGE_SEC)
                            if tick and tick.get("last_price", 0) > 0:
                                active_trades_data[f"NSE:{trade.symbol}"] = {"last_price": tick["last_price"]}
                            elif fallback_trade_quotes:
                                q = fallback_trade_quotes.get(f"NSE:{trade.symbol}", {})
                                if q.get("last_price", 0) > 0:
                                    active_trades_data[f"NSE:{trade.symbol}"] = {"last_price": q["last_price"]}

                    if active_trades_data:
                        self.lifecycle.update_trades(active_trades_data)

                    # Force Exit Check
                    if self.current_playbook == "FORCE_EXIT":
                        self.lifecycle.force_exit_all()

                    # Periodic Sync
                    if (now_monotonic - self.last_state_save_ts) >= config.STATE_SAVE_INTERVAL_SEC:
                        self.state_mgr.save_state(self.risk, self.lifecycle, self.orders)
                        self.last_state_save_ts = now_monotonic

                    # UI Render State
                    positions_for_ui = []
                    total_unrealized_pnl = 0.0
                    raw_positions = self.orders.get_positions()
                    fallback_position_quotes = {}
                    if self.ws_degraded and raw_positions:
                        pos_symbols = [p["symbol"] for p in raw_positions]
                        fallback_position_quotes = data_manager.get_quote(list(set(pos_symbols)))

                    for pos in raw_positions:
                        sym = pos['symbol']
                        token = data_manager.get_token(f"NSE:{sym}")
                        tick = data_manager.get_fresh_tick(token, config.TICK_MAX_AGE_SEC)
                        if tick and tick.get("last_price", 0) > 0:
                            ltp = tick['last_price']
                        else:
                            q = fallback_position_quotes.get(f"NSE:{sym}", {})
                            ltp = q.get('last_price', pos['entry_price'])

                        upnl = (ltp - pos['entry_price']) * pos['qty']
                        pos['unrealized_pnl'] = upnl
                        pos['ltp'] = ltp
                        total_unrealized_pnl += upnl

                        trade_data = next((t for t in self.lifecycle.trades.values()
                                         if t.symbol == sym and t.stage != "CLOSED"), None)

                        if trade_data:
                            pos['current_stop'] = trade_data.current_stop
                            pos['target'] = trade_data.target_1 if trade_data.stage == "ACTIVE" else "Run"
                            pos['stage'] = trade_data.stage
                        else:
                            pos['current_stop'] = 0.0
                            pos['target'] = 0.0
                            pos['stage'] = "MANUAL"

                        positions_for_ui.append(pos)

                    starting_equity = self.risk.state.starting_equity if self.risk.state.starting_equity > 0 else config.DEFAULT_PAPER_EQUITY
                    realized_pnl = float(self.orders.realized_pnl)
                    current_pnl = realized_pnl + total_unrealized_pnl
                    current_equity = starting_equity + current_pnl

                    symbol_exposure, sector_exposure = self._build_trade_exposure_maps()
                    self.risk.update_account(
                        current_equity,
                        current_pnl,
                        positions_for_ui,
                        symbol_exposure=symbol_exposure,
                        sector_exposure=sector_exposure,
                        realized_pnl=realized_pnl,
                        unrealized_pnl=total_unrealized_pnl
                    )
                    kill_halt_post, kill_reason_post = self.risk.check_kill_switches(self.vix_percentile)
                    if kill_halt_post and kill_reason_post != self.last_killswitch_reason:
                        self.log(f"🛑 KILL SWITCH: {kill_reason_post}")
                        self.last_killswitch_reason = kill_reason_post
                        if config.FORCE_LIQUIDATE_ON_KILLSWITCH:
                            self.lifecycle.force_exit_all()
                    elif not kill_halt_post and not self.risk.kill_switch_active:
                        self.last_killswitch_reason = ""

                    feed_status = "WS_LIVE"
                    if self.ws_degraded:
                        feed_status = f"WS_DEGRADED ({self.ws_degraded_reason})"
                    risk_status = "RISK_OK"
                    if self.risk.kill_switch_active:
                        risk_status = f"KILL_SWITCH ({self.risk.kill_switch_reason})"

                    ui_state = {
                        "session": self.current_playbook,
                        "regime": self.regime_detector.get_regime(self.vix_percentile),
                        "vix": self.vix_ltp,
                        "nifty": self.nifty_ltp,
                        "nifty_pct": self.nifty_pct,
                        "sectors": self.sector_scores,
                        "signals": self.active_signals,
                        "positions": positions_for_ui,
                        "equity": current_equity,
                        "pnl": current_pnl,
                        "feed_status": feed_status,
                        "risk_status": risk_status,
                        "logs": self.logs
                    }
                    self.ui.update(ui_state)
                    live.update(self.ui.render())

                    time.sleep(0.5)

                except Exception as e:
                    self.log(f"🔥 LOOP ERROR: {e}")
                    self.log(f"🔥 TRACEBACK: {traceback.format_exc()}")
                    time.sleep(5)

    def shutdown(self, sig, frame):
        self.log("🛑 Shutdown Signal Received.")
        self.state_mgr.save_state(self.risk, self.lifecycle, self.orders)
        self.running = False
        sys.exit(0)


if __name__ == "__main__":
    bot = TradingBotV6()
    bot.run()
