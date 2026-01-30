"""
================================================================================
V5 RICH UI MODULE (REFINED)
================================================================================
The Command Center.
V5 Updates:
- Changed "Chg%" to "Day%" to reflect Daily Change (vs Previous Close)
- Changed "RS-D" label to "RS-D" (Daily RS) - already correct

Displays:
- Header: Session, VIX, Nifty (Styled like V3)
- Left: Sector Rankings & Stock Analysis
- Right: Portfolio & Trade Log
- Footer: Status & Messages

Author: Sector Analysis System
Version: 5.0.0
================================================================================
"""

import time
from datetime import datetime
from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.align import Align
from rich.style import Style
from rich import box

from core_v5 import config_v5 as config

# ══════════════════════════════════════════════════════════════════════════════
# STYLE CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

STYLES = {
    # Headers
    "title": Style(color="bright_cyan", bold=True),
    "subtitle": Style(color="cyan"),
    
    # Regime colors
    "regime_trending": Style(color="bright_green", bold=True),
    "regime_neutral": Style(color="bright_yellow", bold=True),
    "regime_meanrevert": Style(color="bright_magenta", bold=True),
    "regime_halt": Style(color="bright_red", bold=True, blink=True),
    
    # Session colors
    "session_premarket": Style(color="grey50"),
    "session_or": Style(color="bright_yellow"),
    "session_orb": Style(color="bright_green", bold=True),
    "session_main": Style(color="bright_cyan"),
    "session_closing": Style(color="bright_magenta"),
    "session_after": Style(color="grey50"),
    
    # Price changes
    "positive": Style(color="bright_green"),
    "negative": Style(color="bright_red"),
    "neutral": Style(color="white"),
    
    # Grade colors
    "grade_a_plus": Style(color="bright_green", bold=True),
    "grade_a": Style(color="green"),
    "grade_b": Style(color="yellow"),
    "grade_c": Style(color="grey50"),
    
    # Gate colors
    "gate_pass": Style(color="bright_green"),
    "gate_fail": Style(color="bright_red"),
    
    # Selection
    "selected": Style(color="bright_cyan", bold=True),
    "unselected": Style(color="white"),
    
    # HMA alignment
    "bullish": Style(color="bright_green", bold=True),
    "bearish": Style(color="bright_red", bold=True),
    "mixed": Style(color="yellow"),
}

# Symbols
SYMBOLS = {
    "up": "▲",
    "down": "▼",
    "flat": "━",
    "check": "✓",
    "cross": "✗",
    "star": "★",
    "circle": "●",
    "diamond": "◆",
    "trending": "📈",
    "neutral": "📊",
    "meanrevert": "🔄",
    "halt": "🛑",
    "bull": "🐂",
    "bear": "🐻",
    "rocket": "🚀",
    "fire": "🔥",
}

# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_grade_display(grade: str) -> Text:
    """Get colored grade display"""
    displays = {
        "A+": (STYLES["grade_a_plus"], "A+ ★"),
        "A": (STYLES["grade_a"], "A"),
        "B": (STYLES["grade_b"], "B"),
        "C": (STYLES["grade_c"], "C"),
    }
    style, text = displays.get(grade, (STYLES["grade_c"], grade or "-"))
    return Text(text, style=style)


def get_alignment_display(alignment: str) -> Text:
    """Get colored HMA alignment display"""
    if alignment == "BULLISH":
        return Text("BULL", style=STYLES["bullish"])
    elif alignment == "BEARISH":
        return Text("BEAR", style=STYLES["bearish"])
    else:
        return Text("MIXED", style=STYLES["mixed"])


def get_gate_display(passed: bool, reason: str = None) -> Text:
    """Get gate status display"""
    if passed:
        return Text(f"{SYMBOLS['check']} PASS", style=STYLES["gate_pass"])
    else:
        return Text(f"{SYMBOLS['cross']} {reason or 'FAIL'}", style=STYLES["gate_fail"])


class DashboardUI:
    def __init__(self):
        self.console = Console()
        self.layout = Layout()
        self._init_layout()
        
    def _init_layout(self):
        """Define the UI grid (V3 Inspired)."""
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1)
        )
        self.layout["main"].split_row(
            Layout(name="scanner", ratio=6),  # V5 Adjusted to 6
            Layout(name="portfolio", ratio=4) # V5 Adjusted to 4
        )
        self.layout["portfolio"].split_column(
            Layout(name="positions", ratio=1),
            # Layout(name="monitor", ratio=1),
            Layout(name="logs", ratio=1)
        )

    # ══════════════════════════════════════════════════════════════════════════
    # HEADER
    # ══════════════════════════════════════════════════════════════════════════

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
            "OR_FORMATION": (STYLES["session_or"], "OR FORMING"),
            "ORB": (STYLES["session_orb"], "ORB ACTIVE 🎯"),
            "MAIN": (STYLES["session_main"], "MAIN SESSION"),
            "EXIT_ONLY": (STYLES["session_closing"], "EXIT ONLY"),
            "FORCE_EXIT": (STYLES["session_closing"], "FORCE EXIT"),
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

    def generate_header(self, session_name: str, regime: str, vix: float, nifty_val: float, nifty_pct: float, mode_str: str) -> Panel:
        time_str = datetime.now().strftime("%H:%M:%S")
        regime_style, regime_emoji, regime_text = self.get_regime_style(regime)
        session_style, session_text = self.get_session_style(session_name)
        
        # Build header line
        header = Text()
        
        # Left
        header.append(f"⏰ {time_str} ", style="white")
        header.append("│ ", style="grey50")
        header.append(session_text, style=session_style)
        header.append(" │ ", style="grey50")
        
        # Center
        header.append(f"NIFTY ", style="bright_white bold")
        header.append_text(self.format_price_change(nifty_val, nifty_pct))
        header.append(" │ ", style="grey50")
        header.append(f"{regime_emoji} {regime_text}", style=regime_style)
        header.append(" │ ", style="grey50")
        
        # Right (VIX)
        vix_color = "bright_green" if vix < 13 else "yellow" if vix < 18 else "bright_red"
        header.append(f"VIX {vix:.2f} ", style=vix_color)
        header.append(" │ ", style="grey50")
        header.append(mode_str, style="bold cyan")
        
        return Panel(
            Align.center(header),
            title="[bold cyan]📊 V5 AUTONOMOUS BOT[/]",
            border_style="cyan",
            box=box.DOUBLE,
            padding=(0, 1)
        )

    # ══════════════════════════════════════════════════════════════════════════
    # SCANNER (Left Panel)
    # ══════════════════════════════════════════════════════════════════════════

    def generate_scanner(self, sectors: list, stocks: list, nifty_pct: float = 0.0, active_positions: list = None) -> Panel:
        """Combined Sector Rank & Stock Signals table."""
        if active_positions is None:
            active_positions = []
        
        # 1. Sector Table
        sec_table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
        sec_table.add_column("#", justify="center", width=2, style="dim")
        sec_table.add_column("Sector", ratio=1)
        sec_table.add_column("Bias", justify="center", width=5)
        sec_table.add_column("Price", justify="right", width=8)
        # V5: Changed "Chg%" to "Day%" to reflect Daily Change (vs Previous Close)
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
            if br > 20:
                br_style = "bright_green"
                br_text = f"+{br:.0f}%"
            elif br < -20:
                br_style = "bright_red"
                br_text = f"{br:.0f}%"
            else:
                br_style = "yellow"
                br_text = f"{br:.0f}%"
            
            sc = s.composite_score
            bias = s.bias
            if bias == "LONG":
                sc_style = "bright_green bold"
                bias_style = "bright_green"
                bias_text = "LONG"
            elif bias == "SHORT":
                sc_style = "bright_red bold"
                bias_style = "bright_red"
                bias_text = "SHRT"
            else:
                sc_style = "yellow"
                bias_style = "dim white"
                bias_text = "NEUT"
            
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

        # 2. Stock Table
        stk_table = Table(
            box=box.SIMPLE_HEAD, 
            expand=True, 
            title=f"[bold cyan]{SYMBOLS['rocket']} SIGNALS[/]",
            padding=(0, 1)
        )
        stk_table.add_column("#", justify="right", width=2, style="dim")
        stk_table.add_column("Symbol", ratio=1)
        stk_table.add_column("SecBias", justify="center", width=5)
        stk_table.add_column("SecRnk", justify="center", width=6)
        stk_table.add_column("Price", justify="right", width=8)
        # V5: Changed "Chg%" to "Day%" to reflect Daily Change (vs Previous Close)
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

            bias_disp = "NEUT"
            bias_style = "dim"
            
            if s.grade in ["A+", "A", "B"]:
                bias_disp = s.direction[:4]
                bias_style = "bright_green" if s.direction == "LONG" else "bright_red"
            else:
                if any("Sector Bias" in r for r in s.reasons):
                    bias_disp = "OPP"
                    bias_style = "bright_red"
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

    def generate_active_monitor(self, active_positions: list, stocks: list) -> Panel:
        """New Active Monitor Panel (Moved from Scanner)"""
        active_table = Table(
            box=box.SIMPLE_HEAD,
            expand=True,
            title=f"[bold yellow]🛡️ ACTIVE MONITOR[/]",
            padding=(0, 1),
            show_header=True
        )
        active_table.add_column("Symbol", ratio=1)
        active_table.add_column("Price", justify="right", width=10)
        # V5: Changed "Chg%" to "Day%"
        active_table.add_column("Day%", justify="right", width=8)
        active_table.add_column("HMA", justify="center", width=8)

        active_syms = [p['symbol'] for p in active_positions]
        active_signals = [s for s in stocks if s.symbol in active_syms]

        if not active_signals and active_syms:
            active_table.add_row("Loading...", "-", "-", "-")
        elif not active_syms:
            active_table.add_row("[dim]No Active Positions[/]", "", "", "")
        else:
            for s in active_signals:
                hma_disp = get_alignment_display(s.hma_align)
                
                active_table.add_row(
                    Text(s.symbol, style="bold cyan"),
                    f"{s.price:,.1f}",
                    Text(f"{s.change_pct:+.1f}%", style="white"),
                    hma_disp
                )
        
        return Panel(active_table, border_style="yellow")

    # ══════════════════════════════════════════════════════════════════════════
    # PORTFOLIO (Right Panel)
    # ══════════════════════════════════════════════════════════════════════════

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
            if isinstance(target_val, (int, float)):
                target_disp = f"{target_val:,.1f}"
            else:
                target_disp = str(target_val)
            
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

    # ══════════════════════════════════════════════════════════════════════════
    # UPDATE
    # ══════════════════════════════════════════════════════════════════════════

    def update(self, state_data: dict):
        # Header
        mode = "PAPER 📝" if config.IS_PAPER_TRADING else "LIVE 🔴"
        mode_str = f"{mode} | V5.0.0"
        
        header = self.generate_header(
            state_data['session'], 
            state_data['regime'], 
            state_data['vix'], 
            state_data['nifty'], 
            state_data['nifty_pct'],
            mode_str
        )
        self.layout["header"].update(header)
        
        # Left Panel
        scanner = self.generate_scanner(
            state_data['sectors'], 
            state_data['signals'], 
            state_data.get('nifty_pct', 0.0),
            state_data['positions']
        )
        self.layout["scanner"].update(scanner)
        
        # Right Panel
        portfolio = self.generate_portfolio(state_data['positions'], state_data['equity'], state_data['pnl'])
        self.layout["positions"].update(portfolio)
        
        monitor = self.generate_active_monitor(state_data['positions'], state_data['signals'])
        self.layout["monitor"].update(monitor)
        
        logs = self.generate_logs(state_data['logs'])
        self.layout["logs"].update(logs)

    def render(self) -> Layout:
        return self.layout
