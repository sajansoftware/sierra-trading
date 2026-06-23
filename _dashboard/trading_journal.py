"""Trading performance journal — JSON-backed trade recording and stats."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

JOURNAL_PATH = Path(__file__).parent / "journal_data.json"


@dataclass
class Trade:
    date: str
    ticker: str
    direction: str
    entry: float
    exit: float
    quantity: int
    notes: str
    tags: str
    pnl: float = 0.0
    pnl_pct: float = 0.0
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if self.pnl == 0.0 and self.quantity > 0 and self.entry > 0:
            if self.direction == "Long":
                self.pnl = (self.exit - self.entry) * self.quantity
                self.pnl_pct = ((self.exit - self.entry) / self.entry) * 100
            else:
                self.pnl = (self.entry - self.exit) * self.quantity
                self.pnl_pct = ((self.entry - self.exit) / self.entry) * 100


def _load_raw() -> list[dict]:
    if not JOURNAL_PATH.exists():
        return []
    try:
        return json.loads(JOURNAL_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_raw(data: list[dict]) -> None:
    JOURNAL_PATH.write_text(
        json.dumps(data, indent=2, default=str),
        encoding="utf-8",
    )


def load_trades() -> list[dict]:
    return _load_raw()


def add_trade(trade: Trade) -> None:
    data = _load_raw()
    data.insert(0, asdict(trade))
    _save_raw(data)


def delete_trade(index: int) -> None:
    data = _load_raw()
    if 0 <= index < len(data):
        data.pop(index)
        _save_raw(data)


def clear_all() -> None:
    _save_raw([])


def calculate_stats(trades: list[dict]) -> dict:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "max_win": 0.0,
            "max_loss": 0.0,
        }

    wins = [t for t in trades if t.get("pnl", 0) > 0]
    pnls = [t.get("pnl", 0) for t in trades]
    total_pnl = sum(pnls)

    return {
        "total_trades": len(trades),
        "win_rate": (len(wins) / len(trades) * 100) if trades else 0,
        "total_pnl": total_pnl,
        "avg_pnl": total_pnl / len(trades) if trades else 0,
        "max_win": max((t.get("pnl", 0) for t in wins), default=0.0),
        "max_loss": min((t.get("pnl", 0) for t in trades if t.get("pnl", 0) < 0), default=0.0),
    }
