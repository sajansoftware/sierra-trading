"""Tradervue CSV import for Mia.

Tradervue exports your trades as a CSV (Account → Export). Upload it
via the Mia view and we parse it into the same trade-dict shape that
trading_journal.load_trades() returns, so Mia ingests both sources
interchangeably.

The parser is column-name driven (case-insensitive) so it tolerates
the small differences between Tradervue's various export presets.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime


# Lower-case column header -> normalized field name.
# Add aliases here when Tradervue rotates a column label.
COLUMN_ALIASES: dict[str, str] = {
    "symbol":         "ticker",
    "ticker":         "ticker",
    "side":           "direction",
    "type":           "direction",
    "long/short":     "direction",
    "open date":      "date",
    "entry date":     "date",
    "date":           "date",
    "close date":     "exit_date",
    "exit date":      "exit_date",
    "avg entry price":"entry",
    "entry price":    "entry",
    "entry":          "entry",
    "avg exit price": "exit",
    "exit price":     "exit",
    "exit":           "exit",
    "quantity":       "quantity",
    "shares":         "quantity",
    "size":           "quantity",
    "gross p&l":      "pnl",
    "net p&l":        "pnl",
    "p&l":            "pnl",
    "pnl":            "pnl",
    "gain/loss":      "pnl",
    "profit":         "pnl",
    "p&l %":          "pnl_pct",
    "pnl %":          "pnl_pct",
    "gain %":         "pnl_pct",
    "tags":           "tags",
    "tag":            "tags",
    "notes":          "notes",
    "comments":       "notes",
}


def _clean_num(s: str) -> float:
    if s is None:
        return 0.0
    s = str(s).strip().replace("$", "").replace(",", "")
    # Tradervue sometimes shows negatives as "($123.45)"
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace("%", "")
    try:
        v = float(s)
        return -v if neg else v
    except (TypeError, ValueError):
        return 0.0


def _parse_date(s: str) -> str:
    """Return ISO YYYY-MM-DD or '' if unparseable."""
    if not s:
        return ""
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y",
                "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S",
                "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:19], fmt).date().isoformat()
        except ValueError:
            continue
    # Last-resort: take leading YYYY-MM-DD
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return ""


def _normalize_direction(v: str) -> str:
    s = str(v or "").strip().lower()
    if not s:
        return "Long"
    if s.startswith("s") or "short" in s:
        return "Short"
    return "Long"


def parse_tradervue_csv(file_bytes: bytes) -> list[dict]:
    """Parse a Tradervue CSV export into a list of trade dicts in the
    shape that mia.analyze() expects."""
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1", errors="ignore")

    reader = csv.DictReader(io.StringIO(text))
    out: list[dict] = []
    for raw_row in reader:
        # Normalize column keys via the alias table
        norm: dict[str, str] = {}
        for k, v in raw_row.items():
            if k is None:
                continue
            field = COLUMN_ALIASES.get(k.strip().lower())
            if field and (field not in norm or not norm[field]):
                norm[field] = (v or "").strip()
        if not norm.get("ticker"):
            continue
        date = _parse_date(norm.get("date", ""))
        if not date:
            # Skip rows without a parseable date - they break by-DoW
            continue
        out.append({
            "date":      date,
            "ticker":    norm["ticker"].upper(),
            "direction": _normalize_direction(norm.get("direction")),
            "entry":     _clean_num(norm.get("entry")),
            "exit":      _clean_num(norm.get("exit")),
            "quantity":  int(_clean_num(norm.get("quantity"))),
            "pnl":       _clean_num(norm.get("pnl")),
            "pnl_pct":   _clean_num(norm.get("pnl_pct")),
            "tags":      norm.get("tags", ""),
            "notes":     norm.get("notes", ""),
        })
    return out
