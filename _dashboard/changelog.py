"""Ticker changelog — tracks which tickers entered / exited the
qualifying universe (price $1-$20 + float<20M) sector-by-sector.

Each time a sector view loads, the current set of surviving tickers is
diffed against the previous on-disk snapshot. Non-empty diffs are
appended to a rolling change log. The sidebar renders the most recent
entries under the Refresh button.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")
STORE = Path(__file__).resolve().parent / "ticker_changelog.json"
MAX_ENTRIES = 50


def _now_iso() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")


def _load() -> dict:
    if not STORE.exists():
        return {"snapshots": {}, "changes": []}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return {"snapshots": {}, "changes": []}


def _save(data: dict) -> None:
    try:
        STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def record_snapshot(sector: str, tickers: list[str]) -> tuple[list[str], list[str]]:
    """Diff current sector tickers vs last snapshot. Persist new snapshot
    and append a change entry if added/removed is non-empty.

    Returns (added, removed) for this call.
    """
    data = _load()
    snapshots = data.setdefault("snapshots", {})
    changes = data.setdefault("changes", [])

    cur = sorted(set(tickers))
    prev_snap = snapshots.get(sector) or {}
    prev = set(prev_snap.get("tickers") or [])

    added = sorted(set(cur) - prev)
    removed = sorted(prev - set(cur))

    # Always update snapshot so the next diff is against the most recent
    # observation, even if no change today.
    snapshots[sector] = {"tickers": cur, "ts": _now_iso()}

    if added or removed:
        # Drop any prior entry for the same sector on the same date
        # to keep the log readable (today's mutations collapse to one).
        today = _now_iso().split(" ")[0]
        changes = [
            c for c in changes
            if not (c.get("sector") == sector and c.get("ts", "").startswith(today))
        ]
        changes.append({
            "ts": _now_iso(),
            "sector": sector,
            "added": added,
            "removed": removed,
        })
        # Keep the rolling window
        changes = changes[-MAX_ENTRIES:]
        data["changes"] = changes

    _save(data)
    return added, removed


def recent_changes(limit: int = 10) -> list[dict]:
    """Return the most recent change entries, newest first."""
    data = _load()
    changes = data.get("changes") or []
    return list(reversed(changes[-limit:]))
