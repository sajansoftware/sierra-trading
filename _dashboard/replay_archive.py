"""Replay archive — persistent log of historical pre-market spikes.

Each row in the archive is one ticker-day where the pre-market move
(PM High vs PM Low, 4:00 AM – 9:29 AM ET) was ≥ MIN_MOVE_PCT.

Why persist instead of pull live every time:
  - yfinance caps 5-minute intraday history to ~60 days. A persistent
    cache that's updated over time naturally accumulates to a true
    rolling 6-month archive.
  - Each scan is rate-limited and slow; the cache lets us avoid
    re-fetching what we already have.

Cache file: .pm_replay_cache.json next to this module. Schema:
  {
    "tickers": {
      "ABC": {
        "moves": [
          {date, pm_low, pm_low_time, pm_high, pm_high_time,
           upside_pct, prior_close, type, title, link, source,
           sentiment, secondary_source?},
          ...
        ],
        "scanned_ts": "2026-05-25T13:30:00Z"
      },
      ...
    }
  }
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


CACHE_PATH = Path(__file__).resolve().parent / ".pm_replay_cache.json"
MIN_MOVE_PCT = 50.0
LOOKBACK_DAYS = 180   # 6 months


# ----------------------------------------------------------------------------
# Disk I/O
# ----------------------------------------------------------------------------
def _load() -> dict:
    if not CACHE_PATH.exists():
        return {"tickers": {}}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tickers": {}}


def _save(data: dict) -> None:
    try:
        CACHE_PATH.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
    except Exception:
        pass


def _serialize_move(m: dict) -> dict:
    out: dict[str, Any] = {}
    for k, v in m.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------
def record_moves(ticker: str, moves: list[dict]) -> int:
    """Merge a fresh scan into the archive. Deduped by date.

    Returns the number of new rows added for this ticker.
    """
    sym = ticker.upper().strip()
    if not sym:
        return 0
    data = _load()
    tickers = data.setdefault("tickers", {})
    existing = tickers.get(sym) or {"moves": [], "scanned_ts": ""}
    by_date: dict[str, dict] = {
        (m.get("date") or ""): m for m in (existing.get("moves") or [])
    }
    n_new = 0
    for m in moves:
        s = _serialize_move(m)
        d = s.get("date") or ""
        if not d:
            continue
        if (s.get("upside_pct") or 0) < MIN_MOVE_PCT:
            continue
        if d not in by_date:
            n_new += 1
        by_date[d] = s
    tickers[sym] = {
        "moves":      list(by_date.values()),
        "scanned_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _save(data)
    return n_new


def list_moves(
    min_pct: float = MIN_MOVE_PCT,
    lookback_days: int = LOOKBACK_DAYS,
    limit: int | None = None,
) -> list[dict]:
    """Return archived ≥min_pct moves within the lookback window,
    newest first. Each row carries the ticker symbol."""
    data = _load()
    tickers = data.get("tickers") or {}
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    out: list[dict] = []
    for sym, rec in tickers.items():
        for m in rec.get("moves") or []:
            try:
                up = float(m.get("upside_pct") or 0)
            except (TypeError, ValueError):
                up = 0.0
            if up < min_pct:
                continue
            d = m.get("date") or ""
            if d < cutoff:
                continue
            out.append({**m, "ticker": sym})
    out.sort(key=lambda r: (r.get("date") or "",
                            -float(r.get("upside_pct") or 0)), reverse=True)
    if limit is not None:
        out = out[:limit]
    return out


def stats() -> dict:
    data = _load()
    tickers = data.get("tickers") or {}
    total_moves = 0
    earliest = ""
    latest = ""
    for rec in tickers.values():
        for m in rec.get("moves") or []:
            total_moves += 1
            d = m.get("date") or ""
            if not earliest or (d and d < earliest):
                earliest = d
            if not latest or (d and d > latest):
                latest = d
    return {
        "tickers_scanned":  len(tickers),
        "total_moves":      total_moves,
        "earliest_date":    earliest,
        "latest_date":      latest,
    }


def is_stale(ticker: str, max_age_hours: int = 24) -> bool:
    """Whether this ticker should be re-scanned (no record or stale)."""
    data = _load()
    rec = (data.get("tickers") or {}).get(ticker.upper().strip())
    if not rec:
        return True
    ts = rec.get("scanned_ts") or ""
    try:
        scanned = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        age = (datetime.now(scanned.tzinfo) - scanned).total_seconds()
        return age > max_age_hours * 3600
    except Exception:
        return True
