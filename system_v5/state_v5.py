"""
================================================================================
V5 STATE PERSISTENCE
================================================================================
Manages saving and loading of system state to survive restarts.
Handles:
- Active Trades
- Daily Stats (PnL, High Watermark)
- Orders (Paper)

File Format: JSON
Location: data/state.json

Author: Sector Analysis System
Version: 5.0.0
================================================================================
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from core_v5 import config_v5 as config
from execution_v5.lifecycle_v5 import Trade

logger = logging.getLogger("StateV5")

STATE_FILE = config.DATA_DIR / "state_v5.json"


class StateManager:
    def __init__(self):
        self.file_path = STATE_FILE
        self.state: Dict[str, Any] = {
            "last_updated": None,
            "daily_start_equity": 0.0,
            "daily_high_equity": 0.0,
            "trades": {},
            "paper_orders": {},
            "paper_positions": {}
        }

    def load_state(self) -> bool:
        """Load state from disk."""
        if not self.file_path.exists():
            logger.info("No state file found. Starting fresh.")
            return False

        try:
            with open(self.file_path, 'r') as f:
                raw_data = json.load(f)
                
            # Validate date (reset if new day)
            saved_date = raw_data.get("last_updated", "")[:10]
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            if saved_date != current_date:
                logger.info(f"State file is from {saved_date}. Resetting for new day {current_date}.")
                self._archive_old_state(raw_data)
                return False
                
            self.state = raw_data
            logger.info("State loaded successfully.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return False

    def save_state(self, 
                   risk_manager, 
                   lifecycle_manager, 
                   order_manager):
        """Save current system components to disk."""
        try:
            # Serialize Trades
            serialized_trades = {}
            for tid, trade in lifecycle_manager.trades.items():
                t_dict = asdict(trade)
                # Convert datetime to string
                t_dict['entry_time'] = t_dict['entry_time'].isoformat()
                # Handle Chandelier timestamp
                if isinstance(t_dict.get('last_anchor_update'), datetime):
                    t_dict['last_anchor_update'] = t_dict['last_anchor_update'].isoformat()
                serialized_trades[tid] = t_dict

            # Serialize Orders/Positions (Paper)
            serialized_orders = {}
            for oid, order in order_manager.paper_orders.items():
                o_copy = order.copy()
                if isinstance(o_copy.get('timestamp'), datetime):
                    o_copy['timestamp'] = o_copy['timestamp'].isoformat()
                serialized_orders[oid] = o_copy

            current_equity = risk_manager.state.equity

            self.state = {
                "last_updated": datetime.now().isoformat(),
                "daily_start_equity": risk_manager.state.daily_start_equity,
                "daily_high_equity": max(self.state.get("daily_high_equity", 0), current_equity),
                "trades": serialized_trades,
                "paper_orders": serialized_orders,
                "paper_positions": order_manager.paper_positions
            }

            with open(self.file_path, 'w') as f:
                json.dump(self.state, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def restore_system(self, 
                       risk_manager, 
                       lifecycle_manager, 
                       order_manager):
        """Restore system components from loaded state."""
        if not self.state.get("trades"):
            return

        # Restore Risk State
        risk_manager.state.daily_start_equity = self.state.get("daily_start_equity", 0.0)
        
        # Restore Orders/Positions
        order_manager.paper_positions = self.state.get("paper_positions", {})
        # Restore datetimes in orders
        restored_orders = self.state.get("paper_orders", {})
        for oid, order in restored_orders.items():
            if 'timestamp' in order:
                order['timestamp'] = datetime.fromisoformat(order['timestamp'])
        order_manager.paper_orders = restored_orders

        # Restore Trades
        raw_trades = self.state.get("trades", {})
        for tid, t_data in raw_trades.items():
            # Convert string back to datetime
            t_data['entry_time'] = datetime.fromisoformat(t_data['entry_time'])
            
            # Handle Chandelier timestamp
            if 'last_anchor_update' in t_data and isinstance(t_data['last_anchor_update'], str):
                t_data['last_anchor_update'] = datetime.fromisoformat(t_data['last_anchor_update'])
            
            # Reconstruct Trade object
            trade = Trade(**t_data)
            lifecycle_manager.trades[tid] = trade
            
        logger.info(f"Restored {len(lifecycle_manager.trades)} trades and {len(order_manager.paper_positions)} positions.")

    def _archive_old_state(self, old_state):
        """Archive old state file."""
        date_str = old_state.get("last_updated", "unknown")[:10]
        archive_path = config.DATA_DIR / f"state_v5_{date_str}.json"
        try:
            with open(archive_path, 'w') as f:
                json.dump(old_state, f, indent=2)
        except Exception:
            pass
