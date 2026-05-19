"""Ticker changelog — tracks which tickers entered / exited the
qualifying universe ($1-$20 + float<20M), per ticker, with a reason
for each transition.

Snapshots live in ticker_changelog.json:
    {
      "snapshots": {sector: {sym: {price, float, mcap}, ...}},
      "events":    [{ts, sector, sym, action, reason, price, float_shares}, ...]
    }
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")
STORE = Path(__file__).resolve().parent / "ticker_changelog.json"
MAX_EVENTS = 200

MIN_PRICE = 1.0
MAX_PRICE = 20.0
MAX_FLOAT = 20_000_000


def _now_iso() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")


def _load() -> dict:
    if not STORE.exists():
        return {"snapshots": {}, "events": []}
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {"snapshots": {}, "events": []}
    # Migrate from old shape (snapshots had {tickers, ts} + "changes" key)
    snaps = data.get("snapshots") or {}
    migrated_snaps: dict = {}
    for sec, snap in snaps.items():
        if isinstance(snap, dict) and "tickers" in snap and isinstance(snap.get("tickers"), list):
            migrated_snaps[sec] = {t: {} for t in snap["tickers"]}
        elif isinstance(snap, dict):
            migrated_snaps[sec] = snap
    data["snapshots"] = migrated_snaps
    data.setdefault("events", [])
    data.pop("changes", None)
    return data


def _save(data: dict) -> None:
    try:
        STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _reason_for_drop(
    sym: str,
    prev_meta: dict,
    nd_row: tuple[float, str, str, float | None] | None,
) -> str:
    """Best-guess reason a previously-qualifying ticker no longer passes."""
    if nd_row is None:
        return "Delisted or removed from NASDAQ universe"
    price, _sector, _industry, _mc = nd_row
    if price is None:
        return "No price available"
    if price < MIN_PRICE:
        return f"Price ${price:.2f} dropped below ${MIN_PRICE:.0f}"
    if price > MAX_PRICE:
        return f"Price ${price:.2f} rose above ${MAX_PRICE:.0f}"
    # Price still in band → likely float grew past 20M
    prev_float = prev_meta.get("float")
    if prev_float and prev_float >= MAX_FLOAT * 0.8:
        return "Free float grew above 20M (dilution / offering)"
    return "Free float now exceeds 20M"


def _reason_for_add(
    sym: str,
    new_meta: dict,
    prev_in_snapshot: bool,
) -> str:
    """Best-guess reason a ticker newly qualifies."""
    price = new_meta.get("price")
    fl = new_meta.get("float")
    if not prev_in_snapshot:
        # Could be a brand-new IPO or simply first time this sector
        # was loaded.
        if price is not None and MIN_PRICE <= price <= MAX_PRICE:
            return f"Newly qualifying at ${price:.2f}" + (
                f", float {fl/1e6:.1f}M" if fl else ""
            )
        return "Newly qualifying"
    # Was previously known but dropped before; came back
    return "Re-entered screen (price / float now within criteria)"


def record_snapshot(
    sector: str,
    quotes: Iterable[Any],
) -> tuple[list[dict], list[dict]]:
    """Diff this sector's current qualifying quotes vs the last snapshot.

    `quotes` is an iterable of Quote objects (data.Quote) — anything with
    `.ticker`, `.price`, `.float_shares`, `.market_cap` attributes.

    Appends per-ticker events to the rolling log with a human reason.
    Returns (added_events, removed_events) for this call.
    """
    # Lazy import so changelog.py has no hard dep on data.py at module load.
    try:
        from data import nasdaq_price_map
        nd_map = nasdaq_price_map()
    except Exception:
        nd_map = {}

    data = _load()
    snapshots = data.setdefault("snapshots", {})
    events = data.setdefault("events", [])

    cur_meta: dict[str, dict] = {}
    for q in quotes:
        sym = getattr(q, "ticker", None)
        if not sym:
            continue
        cur_meta[sym] = {
            "price": getattr(q, "price", None) or getattr(q, "previous_close", None),
            "float": getattr(q, "float_shares", None),
            "mcap":  getattr(q, "market_cap", None),
        }

    prev_meta_map: dict[str, dict] = snapshots.get(sector) or {}
    prev_syms = set(prev_meta_map.keys())
    cur_syms = set(cur_meta.keys())

    added = sorted(cur_syms - prev_syms)
    removed = sorted(prev_syms - cur_syms)

    ts = _now_iso()
    new_events: list[dict] = []

    # Was this sector ever recorded before? If not, treat as initial
    # seed — don't flood the log with hundreds of "newly qualifying"
    # entries on first visit.
    first_seed = not prev_meta_map

    if not first_seed:
        for sym in added:
            meta = cur_meta[sym]
            new_events.append({
                "ts": ts,
                "sector": sector,
                "sym": sym,
                "action": "added",
                "reason": _reason_for_add(sym, meta, sym in prev_meta_map),
                "price": meta.get("price"),
                "float_shares": meta.get("float"),
            })
        for sym in removed:
            reason = _reason_for_drop(sym, prev_meta_map.get(sym) or {}, nd_map.get(sym))
            nd_row = nd_map.get(sym)
            cur_price = nd_row[0] if nd_row else None
            new_events.append({
                "ts": ts,
                "sector": sector,
                "sym": sym,
                "action": "removed",
                "reason": reason,
                "price": cur_price,
                "float_shares": (prev_meta_map.get(sym) or {}).get("float"),
            })

    snapshots[sector] = cur_meta
    if new_events:
        events.extend(new_events)
        events = events[-MAX_EVENTS:]
        data["events"] = events
    _save(data)

    added_evts = [e for e in new_events if e["action"] == "added"]
    removed_evts = [e for e in new_events if e["action"] == "removed"]
    return added_evts, removed_evts


def recent_events(limit: int = 10) -> list[dict]:
    """Most recent per-ticker events, newest first."""
    data = _load()
    events = data.get("events") or []
    return list(reversed(events[-limit:]))
