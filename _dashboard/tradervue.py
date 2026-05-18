"""Tradervue API client for pulling real trades into Mia's analysis.

Uses HTTP Basic authentication with the user's Tradervue username +
password (Tradervue's documented auth mechanism for the v1 API).

Set credentials in:
  - Streamlit Cloud: app settings → Secrets:
        tradervue_username = "you@example.com"
        tradervue_password = "your_password"
  - Local dev: _dashboard/.streamlit/secrets.toml with the same keys.

Tradervue API docs: https://github.com/tradervue/api-docs
"""

from __future__ import annotations

import requests
import streamlit as st


API_BASE = "https://www.tradervue.com/api/v1"
TIMEOUT = 20


def _get_credentials() -> tuple[str | None, str | None]:
    try:
        user = st.secrets.get("tradervue_username")
        pw = st.secrets.get("tradervue_password")
        return user, pw
    except Exception:
        return None, None


def is_configured() -> bool:
    user, pw = _get_credentials()
    return bool(user and pw)


def _normalize_trade(t: dict) -> dict:
    """Convert a Tradervue trade row into the same dict shape that
    trading_journal.load_trades() returns, so Mia can ingest both
    sources interchangeably."""
    raw_tags = t.get("tags") or []
    if isinstance(raw_tags, list):
        tags = ", ".join(str(x).strip() for x in raw_tags if x)
    else:
        tags = str(raw_tags)

    side = (t.get("side") or t.get("type") or "long").strip().lower()
    direction = "Long" if side.startswith("l") else "Short"

    def _f(key: str) -> float:
        v = t.get(key)
        try:
            return float(v) if v not in (None, "") else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _i(key: str) -> int:
        v = t.get(key)
        try:
            return int(float(v)) if v not in (None, "") else 0
        except (TypeError, ValueError):
            return 0

    pnl = _f("gain_loss") or _f("pnl") or _f("net_pnl")
    pnl_pct = _f("gain_loss_pct") or _f("pnl_pct")
    entry = _f("entry_price") or _f("avg_entry")
    exitp = _f("exit_price") or _f("avg_exit")
    qty = _i("quantity") or _i("shares")

    # Best-effort date selection: trade open date preferred
    date = (t.get("date") or t.get("entry_date") or t.get("open_date")
            or t.get("close_date") or "")
    # Trim datetimes to YYYY-MM-DD
    if isinstance(date, str) and len(date) >= 10:
        date = date[:10]

    return {
        "date":      date,
        "ticker":    (t.get("symbol") or "").upper(),
        "direction": direction,
        "entry":     entry,
        "exit":      exitp,
        "quantity":  qty,
        "pnl":       pnl,
        "pnl_pct":   pnl_pct,
        "tags":      tags,
        "notes":     t.get("notes") or "",
    }


@st.cache_data(ttl=900, show_spinner=False)   # 15 min
def fetch_tradervue_trades(limit: int = 500) -> tuple[list[dict], str]:
    """Fetch the user's trades from Tradervue.

    Returns (trades, error_msg). On success error_msg is ''. On
    failure trades is [] and error_msg explains why (missing creds,
    auth failed, network issue, etc.).
    """
    user, pw = _get_credentials()
    if not user or not pw:
        return [], "Tradervue credentials not configured"

    out: list[dict] = []
    page = 1
    err = ""
    while len(out) < limit:
        try:
            r = requests.get(
                f"{API_BASE}/trades.json",
                auth=(user, pw),
                params={"page": page, "per_page": 100},
                timeout=TIMEOUT,
            )
        except Exception as exc:
            err = f"Network error: {exc}"
            break
        if r.status_code == 401:
            return [], "Tradervue authentication failed (check username / password)"
        if r.status_code != 200:
            err = f"Tradervue API returned HTTP {r.status_code}"
            break
        try:
            data = r.json()
        except Exception:
            err = "Tradervue returned a non-JSON response"
            break
        # Tradervue may return {'trades': [...]} or a bare list
        rows = data.get("trades") if isinstance(data, dict) else data
        if not rows:
            break
        for t in rows:
            out.append(_normalize_trade(t))
        if len(rows) < 100:
            break
        page += 1
        if page > 20:  # hard safety cap
            break
    return out[:limit], err
