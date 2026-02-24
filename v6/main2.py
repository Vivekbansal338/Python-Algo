"""
================================================================================
V6 ORCHESTRATOR + UI (MAIN2)
================================================================================
Alternative entrypoint with a stable Rich TUI:
- Single render clock (no dual refresh paths)
- Fixed layout with bounded tables
- Cleaner terminal design for long-running monitoring

Keeps v6/main.py unchanged and reuses its core trading orchestration.
================================================================================
"""

import os
import time
import logging
import traceback
from datetime import datetime
from typing import Any, Dict, List

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from v6 import config
from v6.data_engine import data_manager
from v6.main import TradingBotV6


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, min_value: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
        return value if value >= min_value else default
    except Exception:
        return default


TUI_REDRAW_INTERVAL_SEC = _env_float("V6_TUI_REDRAW_SEC", 0.50, 0.10)
TUI_LOOP_SLEEP_SEC = _env_float("V6_TUI_LOOP_SLEEP_SEC", 0.50, 0.05)
TUI_ALT_SCREEN = _env_bool("V6_TUI_ALT_SCREEN", False)
TUI_MAX_LOG_LINES = 10
TUI_MAX_LOG_CHARS = 96


class DashboardUIV2:
    """Stable and compact TUI with fixed regions and bounded content."""

    def __init__(self):
        self.console = Console()
        self.layout = Layout()
        self._init_layout()

    def _init_layout(self):
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
        )
        self.layout["body"].split_row(
            Layout(name="left", ratio=7),
            Layout(name="right", ratio=5),
        )
        self.layout["left"].split_column(
            Layout(name="sectors", size=16),
            Layout(name="signals", ratio=1),
        )
        self.layout["right"].split_column(
            Layout(name="stats", size=10),
            Layout(name="positions", ratio=1),
            Layout(name="logs", size=12),
        )

    @staticmethod
    def _trim(value: str, max_len: int) -> str:
        if len(value) <= max_len:
            return value
        if max_len <= 3:
            return value[:max_len]
        return f"{value[:max_len - 3]}..."

    @staticmethod
    def _regime_style(regime: str) -> str:
        if regime == "TRENDING":
            return "bold bright_green"
        if regime == "MEAN_REVERT":
            return "bold yellow"
        if regime == "EXTREME":
            return "bold bright_red"
        return "bold cyan"

    @staticmethod
    def _pnl_style(pnl: float) -> str:
        return "bright_green" if pnl >= 0 else "bright_red"

    @staticmethod
    def _feed_style(feed_status: str) -> str:
        return "bright_red" if "DEGRADED" in feed_status else "bright_green"

    @staticmethod
    def _risk_style(risk_status: str) -> str:
        return "bright_red" if risk_status != "RISK_OK" else "bright_green"

    def generate_header(self, state_data: Dict[str, Any]) -> Panel:
        now_text = datetime.now().strftime("%H:%M:%S")
        session = state_data.get("session", "-")
        regime = state_data.get("regime", "-")
        feed = state_data.get("feed_status", "WS_LIVE")
        risk = state_data.get("risk_status", "RISK_OK")
        nifty = float(state_data.get("nifty", 0.0))
        nifty_pct = float(state_data.get("nifty_pct", 0.0))
        vix = float(state_data.get("vix", 0.0))
        equity = float(state_data.get("equity", 0.0))
        pnl = float(state_data.get("pnl", 0.0))

        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_column(justify="center")
        grid.add_column(justify="right")

        left = Text()
        left.append("V6 MAIN2  ", style="bold cyan")
        left.append(now_text, style="white")
        left.append("  ", style="white")
        left.append(session, style="bright_white")

        center = Text()
        center.append("REGIME ", style="white")
        center.append(regime, style=self._regime_style(regime))
        center.append("  FEED ", style="white")
        center.append(feed, style=self._feed_style(feed))
        center.append("  RISK ", style="white")
        center.append(risk, style=self._risk_style(risk))

        right = Text()
        right.append(f"NIFTY {nifty:,.1f} ", style="white")
        right.append(f"{nifty_pct:+.2f}%", style="bright_green" if nifty_pct >= 0 else "bright_red")
        right.append("  ", style="white")
        right.append(f"VIX {vix:.2f}", style="yellow")
        right.append("  ", style="white")
        right.append(f"EQ {equity:,.0f}", style="white")
        right.append("  ", style="white")
        right.append(f"PNL {pnl:+,.1f}", style=self._pnl_style(pnl))

        grid.add_row(left, center, right)
        return Panel(grid, box=box.ROUNDED, border_style="cyan", padding=(0, 1))

    def generate_sectors(self, sectors: List[Any]) -> Panel:
        table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
        table.add_column("#", justify="right", width=3)
        table.add_column("Sector", ratio=1, no_wrap=True, overflow="ellipsis")
        table.add_column("Bias", justify="center", width=7)
        table.add_column("Day%", justify="right", width=8)
        table.add_column("Breadth", justify="right", width=8)
        table.add_column("Score", justify="right", width=8)

        rows = sectors[:10]
        if not rows:
            table.add_row("-", "No sector data", "-", "-", "-", "-")
        else:
            for sec in rows:
                rank_prefix = "*" if getattr(sec, "is_selected", False) else " "
                rank = f"{rank_prefix}{getattr(sec, 'rank', 0)}"
                sym = self._trim(str(getattr(sec, "symbol", "-")), 18)
                bias = str(getattr(sec, "bias", "NEUTRAL"))
                bias_style = "bright_green" if bias == "LONG" else "bright_red" if bias == "SHORT" else "white"
                day_pct = float(getattr(sec, "change_pct", 0.0))
                breadth = float(getattr(sec, "breadth", 0.0)) * 100.0
                score = float(getattr(sec, "composite_score", 0.0))

                day_style = "bright_green" if day_pct >= 0 else "bright_red"
                breadth_style = "bright_green" if breadth >= 0 else "bright_red"
                score_style = "bright_green" if score >= 0 else "bright_red"

                table.add_row(
                    rank,
                    sym,
                    Text(bias, style=bias_style),
                    Text(f"{day_pct:+.2f}%", style=day_style),
                    Text(f"{breadth:+.0f}%", style=breadth_style),
                    Text(f"{score:+.1f}", style=score_style),
                )

        return Panel(table, title="Sectors", box=box.ROUNDED, border_style="blue")

    def generate_signals(self, signals: List[Any]) -> Panel:
        table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
        table.add_column("#", justify="right", width=3)
        table.add_column("Symbol", ratio=1, no_wrap=True, overflow="ellipsis")
        table.add_column("Dir", justify="center", width=6)
        table.add_column("Grade", justify="center", width=6)
        table.add_column("RVOL", justify="right", width=6)
        table.add_column("Stoch", justify="right", width=6)
        table.add_column("Gate", justify="center", width=6)
        table.add_column("Reason", ratio=2, no_wrap=True, overflow="ellipsis")

        sorted_signals = sorted(signals, key=lambda s: float(getattr(s, "score", 0.0)), reverse=True)[:12]
        if not sorted_signals:
            table.add_row("-", "No active signals", "-", "-", "-", "-", "-", "-")
        else:
            for idx, sig in enumerate(sorted_signals, start=1):
                direction = str(getattr(sig, "direction", "-")) or "-"
                grade = str(getattr(sig, "grade", "-")) or "-"
                gate_passed = bool(getattr(sig, "gate_passed", False))
                gate = "PASS" if gate_passed else "FAIL"
                gate_style = "bright_green" if gate_passed else "bright_red"
                reason = str(getattr(sig, "gate_reason", "")) if not gate_passed else "OK"
                reason = self._trim(reason, 34)

                dir_style = "bright_green" if direction == "LONG" else "bright_red" if direction == "SHORT" else "white"
                grade_style = (
                    "bold bright_green" if grade == "A+"
                    else "green" if grade == "A"
                    else "yellow" if grade == "B"
                    else "bright_black"
                )

                table.add_row(
                    str(idx),
                    self._trim(str(getattr(sig, "symbol", "-")), 16),
                    Text(direction, style=dir_style),
                    Text(grade, style=grade_style),
                    f"{float(getattr(sig, 'rvol', 0.0)):.2f}",
                    f"{float(getattr(sig, 'stoch_k', 0.0)):.0f}",
                    Text(gate, style=gate_style),
                    reason,
                )

        return Panel(table, title="Signals", box=box.ROUNDED, border_style="magenta")

    def generate_stats(self, state_data: Dict[str, Any]) -> Panel:
        table = Table(box=box.SIMPLE, expand=True, show_header=False, padding=(0, 1))
        table.add_column("k", style="bright_cyan", width=12)
        table.add_column("v", style="white")

        positions = state_data.get("positions", []) or []
        open_count = len(positions)
        regime = state_data.get("regime", "-")
        playbook = state_data.get("session", "-")
        vix = float(state_data.get("vix", 0.0))
        nifty_pct = float(state_data.get("nifty_pct", 0.0))
        eq = float(state_data.get("equity", 0.0))
        pnl = float(state_data.get("pnl", 0.0))
        feed = state_data.get("feed_status", "WS_LIVE")
        risk = state_data.get("risk_status", "RISK_OK")

        table.add_row("Mode", "PAPER")
        table.add_row("Session", str(playbook))
        table.add_row("Regime", Text(str(regime), style=self._regime_style(str(regime))))
        table.add_row("Open Trades", str(open_count))
        table.add_row("Nifty Day", Text(f"{nifty_pct:+.2f}%", style="bright_green" if nifty_pct >= 0 else "bright_red"))
        table.add_row("VIX", f"{vix:.2f}")
        table.add_row("Equity", f"{eq:,.0f}")
        table.add_row("Day PnL", Text(f"{pnl:+,.1f}", style=self._pnl_style(pnl)))
        table.add_row("Feed", Text(str(feed), style=self._feed_style(str(feed))))
        table.add_row("Risk", Text(str(risk), style=self._risk_style(str(risk))))

        return Panel(table, title="System", box=box.ROUNDED, border_style="cyan")

    def generate_positions(self, positions: List[Dict[str, Any]]) -> Panel:
        table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
        table.add_column("Sym", ratio=1, no_wrap=True, overflow="ellipsis")
        table.add_column("Side", justify="center", width=6)
        table.add_column("Qty", justify="right", width=5)
        table.add_column("Entry", justify="right", width=9)
        table.add_column("LTP", justify="right", width=9)
        table.add_column("UPnL", justify="right", width=11)
        table.add_column("Stop", justify="right", width=9)
        table.add_column("Stage", justify="center", width=8)

        if not positions:
            table.add_row("-", "-", "-", "-", "-", "-", "-", "-")
        else:
            for pos in positions[:10]:
                qty = int(pos.get("qty", 0))
                side = "LONG" if qty > 0 else "SHORT"
                side_style = "bright_green" if side == "LONG" else "bright_red"
                upnl = float(pos.get("unrealized_pnl", 0.0))
                stage = str(pos.get("stage", "N/A"))
                stage_style = "bright_cyan" if stage == "PARTIAL" else "white"
                table.add_row(
                    self._trim(str(pos.get("symbol", "-")), 14),
                    Text(side, style=side_style),
                    str(abs(qty)),
                    f"{float(pos.get('entry_price', 0.0)):,.1f}",
                    f"{float(pos.get('ltp', 0.0)):,.1f}",
                    Text(f"{upnl:+,.1f}", style=self._pnl_style(upnl)),
                    f"{float(pos.get('current_stop', 0.0)):,.1f}",
                    Text(stage, style=stage_style),
                )

        return Panel(table, title="Positions", box=box.ROUNDED, border_style="green")

    def generate_logs(self, logs: List[str]) -> Panel:
        log_table = Table(box=box.SIMPLE, expand=True, show_header=False, padding=(0, 0))
        log_table.add_column(no_wrap=True, overflow="ellipsis")

        recent = logs[-TUI_MAX_LOG_LINES:] if logs else []
        if not recent:
            log_table.add_row(Text("No logs yet", style="bright_black"))
        else:
            for line in recent:
                short = self._trim(line, TUI_MAX_LOG_CHARS)
                style = "white"
                if "ENTER" in short:
                    style = "bright_cyan"
                elif "EXIT" in short:
                    style = "yellow"
                elif "STOP" in short or "KILL" in short or "HALT" in short:
                    style = "bright_red"
                elif "TARGET" in short or "RECOVERED" in short:
                    style = "bright_green"
                log_table.add_row(Text(short, style=style))

        return Panel(log_table, title="Logs", box=box.ROUNDED, border_style="white")

    def update(self, state_data: Dict[str, Any]):
        self.layout["header"].update(self.generate_header(state_data))
        self.layout["sectors"].update(self.generate_sectors(state_data.get("sectors", [])))
        self.layout["signals"].update(self.generate_signals(state_data.get("signals", [])))
        self.layout["stats"].update(self.generate_stats(state_data))
        self.layout["positions"].update(self.generate_positions(state_data.get("positions", [])))
        self.layout["logs"].update(self.generate_logs(state_data.get("logs", [])))

    def render(self) -> Layout:
        return self.layout


class TradingBotV6Main2(TradingBotV6):
    """
    Alternative runner with:
    - deterministic render cadence
    - separate compute cadence and paint cadence
    - stable dashboard visuals for long sessions
    """

    def __init__(self):
        super().__init__()
        self.ui = DashboardUIV2()
        self.tui_redraw_interval_sec = TUI_REDRAW_INTERVAL_SEC
        self.loop_sleep_sec = TUI_LOOP_SLEEP_SEC
        self.tui_alt_screen = TUI_ALT_SCREEN
        self.force_exit_processed = False

    def log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        self.logs.append(entry)
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        logging.getLogger("Orchestrator").info(msg)

    def run(self):
        self.initialize()

        quote_symbols = ["NIFTY 50", "INDIA VIX"]
        quote_symbols.extend([i["symbol"] for i in self.indices if i["name"] not in ["NIFTY 50", "INDIA VIX"]])
        market_quotes = data_manager.get_quote(quote_symbols)
        self.last_quotes.update(market_quotes)

        nifty_quote = market_quotes.get("NSE:NIFTY 50", {})
        regime = self.regime_detector.get_regime(self.vix_percentile)
        self._update_sector_ranks(market_quotes, nifty_quote, regime)
        self.last_state_save_ts = time.monotonic()

        with Live(
            self.ui.render(),
            auto_refresh=False,
            screen=self.tui_alt_screen,
            transient=False,
            console=self.ui.console,
        ) as live:
            next_redraw_ts = 0.0

            while self.running:
                try:
                    now_monotonic = time.monotonic()
                    now_dt = datetime.now()
                    self.current_playbook = self.get_playbook(now_dt.time())

                    if self.current_playbook == "AFTER_CLOSE":
                        if not self.after_close_processed:
                            self.log("AFTER_CLOSE reached. Executing final housekeeping.")
                            self.lifecycle.force_exit_all()
                            self.state_mgr.save_state(self.risk, self.lifecycle, self.orders)
                            self.after_close_processed = True
                        if config.AUTO_SHUTDOWN_AFTER_CLOSE:
                            self.running = False
                            break
                        time.sleep(1.0)
                        continue

                    if now_monotonic - self.last_intraday_refresh >= config.INTRADAY_REFRESH_INTERVAL_SEC:
                        refresh_symbols: List[str] = []
                        for sec in self.sector_scores:
                            if sec.is_selected:
                                sec_name = next((i["name"] for i in self.indices if i["symbol"] == sec.symbol), None)
                                if sec_name:
                                    refresh_symbols.extend(self.sector_map.get(sec_name, []))
                        refresh_symbols.extend(self.risk.state.active_symbols)
                        refresh_symbols = list(set(refresh_symbols))
                        if refresh_symbols:
                            self._refresh_intraday_history(refresh_symbols)
                        self.last_intraday_refresh = now_monotonic

                    if now_monotonic - self.last_ui_update >= config.UI_REFRESH_INTERVAL:
                        degraded_now, ws_reason, _ = data_manager.get_ws_health(config.WS_STALE_FEED_SEC)
                        if degraded_now:
                            data_manager.attempt_reconnect()
                            self.ws_recovery_candidate_since = 0.0
                            if (not self.ws_degraded) or (ws_reason != self.ws_degraded_reason):
                                self._log_ws_status(f"WS_DEGRADED: {ws_reason}. New entries paused.", force=True)
                            else:
                                self._log_ws_status(f"WS_DEGRADED: {ws_reason}. New entries paused.")
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
                                self._log_ws_status("WS_RECOVERED: stable tick flow restored.", force=True)
                            else:
                                self._log_ws_status(
                                    f"WS_RECOVERING: stable for {stable_for:.0f}s / "
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
                            self.log(f"KILL SWITCH: {kill_reason}")
                            self.last_killswitch_reason = kill_reason
                            if config.FORCE_LIQUIDATE_ON_KILLSWITCH:
                                self.lifecycle.force_exit_all()
                        elif not kill_halt:
                            self.last_killswitch_reason = ""

                        self.safety.update(self.nifty_ltp, self.vix_ltp, 0.0)
                        if self.safety.is_halted:
                            self.log(f"HALTED: {self.safety.halt_reason}")
                            self.lifecycle.force_exit_all()
                        elif kill_halt:
                            self.active_signals = []
                        elif self.ws_degraded:
                            self.active_signals = []
                        else:
                            self._scan_tradeable_stocks(
                                self.regime_detector.get_regime(self.vix_percentile),
                                self.vix_ltp,
                            )

                        self._maybe_log_tick_health(now_monotonic)
                        self.last_ui_update = now_monotonic

                    active_trades_data: Dict[str, Dict[str, float]] = {}
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

                    if self.current_playbook == "FORCE_EXIT" and not self.force_exit_processed:
                        self.lifecycle.force_exit_all()
                        self.force_exit_processed = True

                    if (now_monotonic - self.last_state_save_ts) >= config.STATE_SAVE_INTERVAL_SEC:
                        self.state_mgr.save_state(self.risk, self.lifecycle, self.orders)
                        self.last_state_save_ts = now_monotonic

                    positions_for_ui: List[Dict[str, Any]] = []
                    total_unrealized_pnl = 0.0
                    raw_positions = self.orders.get_positions()
                    fallback_position_quotes = {}
                    if self.ws_degraded and raw_positions:
                        pos_symbols = [p["symbol"] for p in raw_positions]
                        fallback_position_quotes = data_manager.get_quote(list(set(pos_symbols)))

                    for pos in raw_positions:
                        sym = pos["symbol"]
                        token = data_manager.get_token(f"NSE:{sym}")
                        tick = data_manager.get_fresh_tick(token, config.TICK_MAX_AGE_SEC)
                        if tick and tick.get("last_price", 0) > 0:
                            ltp = tick["last_price"]
                        else:
                            q = fallback_position_quotes.get(f"NSE:{sym}", {})
                            ltp = q.get("last_price", pos["entry_price"])

                        upnl = (ltp - pos["entry_price"]) * pos["qty"]
                        pos["unrealized_pnl"] = upnl
                        pos["ltp"] = ltp
                        total_unrealized_pnl += upnl

                        trade_data = next(
                            (t for t in self.lifecycle.trades.values() if t.symbol == sym and t.stage != "CLOSED"),
                            None,
                        )
                        if trade_data:
                            pos["current_stop"] = trade_data.current_stop
                            pos["target"] = trade_data.target_1 if trade_data.stage == "ACTIVE" else "Run"
                            pos["stage"] = trade_data.stage
                        else:
                            pos["current_stop"] = 0.0
                            pos["target"] = 0.0
                            pos["stage"] = "MANUAL"
                        positions_for_ui.append(pos)

                    starting_equity = (
                        self.risk.state.starting_equity
                        if self.risk.state.starting_equity > 0
                        else config.DEFAULT_PAPER_EQUITY
                    )
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
                        unrealized_pnl=total_unrealized_pnl,
                    )
                    kill_halt_post, kill_reason_post = self.risk.check_kill_switches(self.vix_percentile)
                    if kill_halt_post and kill_reason_post != self.last_killswitch_reason:
                        self.log(f"KILL SWITCH: {kill_reason_post}")
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
                        "logs": self.logs,
                    }
                    self.ui.update(ui_state)

                    render_now = time.monotonic()
                    if render_now >= next_redraw_ts:
                        live.update(self.ui.render(), refresh=True)
                        next_redraw_ts = render_now + self.tui_redraw_interval_sec

                    time.sleep(self.loop_sleep_sec)

                except Exception as e:
                    self.log(f"LOOP ERROR: {e}")
                    self.log(f"TRACEBACK: {traceback.format_exc()}")
                    time.sleep(2.0)


if __name__ == "__main__":
    bot = TradingBotV6Main2()
    bot.run()
