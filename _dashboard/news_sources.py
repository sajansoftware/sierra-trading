"""Free news sources for historical headline enrichment.

Three sources stack to give the catalyst dialog real headline coverage
across the 5-year window:

1. Finviz news table (~1-2y per ticker; small-cap coverage is strong;
   carries the publisher name e.g. PR Newswire, GlobeNewswire).
2. Yahoo Finance RSS (last ~30-60d; structured XML; high reliability).
3. SEC EDGAR 8-K filings (full 5y; from edgar.py).

yfinance.news is layered in for free since we already have the Ticker
object — it adds ~20 of the most recent Yahoo articles. Stock Titan was
considered but returns 403 to automated requests.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

import requests
import streamlit as st
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml"}


# ============================================================
# Finviz news table scraper
# ============================================================
_FINVIZ_FULL_DATE_RE = re.compile(r"([A-Z][a-z]{2}-\d{2}-\d{2})\s+\d")


@st.cache_data(ttl=86_400, show_spinner=False)
def fetch_finviz_news(ticker: str) -> list[dict]:
    """Scrape the Finviz news table. Returns [{date, title, link, source}].

    Finviz keeps roughly 1-2 years of headlines for actively-covered
    tickers. Date column alternates between full dates ('May-12-26 09:00AM')
    and time-only rows ('09:35AM') that inherit the previous date.
    """
    try:
        r = requests.get(
            f"https://finviz.com/quote.ashx?t={ticker.upper()}",
            headers=HEADERS, timeout=15,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        table = soup.find("table", id="news-table")
        if not table:
            return []
    except Exception:
        return []

    out: list[dict] = []
    last_date: date | None = None
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) != 2:
            continue
        date_text = tds[0].get_text(strip=True)
        parsed_date: date | None = None
        m = _FINVIZ_FULL_DATE_RE.match(date_text)
        if m:
            try:
                parsed_date = datetime.strptime(m.group(1), "%b-%d-%y").date()
                last_date = parsed_date
            except ValueError:
                parsed_date = None
        else:
            parsed_date = last_date
        if parsed_date is None:
            continue
        link_tag = tds[1].find("a")
        if not link_tag:
            continue
        title = link_tag.get_text(strip=True)
        href = link_tag.get("href", "")
        if not title or not href:
            continue
        publisher_tag = tds[1].find("span")
        publisher_raw = publisher_tag.get_text(strip=True) if publisher_tag else ""
        # Finviz wraps the publisher in parens, e.g. "(GlobeNewswire)"
        publisher = publisher_raw.strip("() ")
        out.append({
            "date":   parsed_date,
            "title":  title,
            "link":   href,
            "source": publisher if publisher else "Finviz",
        })
    return out


# ============================================================
# Yahoo Finance RSS
# ============================================================
@st.cache_data(ttl=86_400, show_spinner=False)
def fetch_yahoo_rss(ticker: str) -> list[dict]:
    """Yahoo Finance RSS feed. Recent items only (~30-60 days)."""
    try:
        r = requests.get(
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?"
            f"s={ticker.upper()}&region=US&lang=en-US",
            headers=HEADERS, timeout=15,
        )
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except Exception:
        return []

    out: list[dict] = []
    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        date_el = item.find("pubDate")
        if title_el is None or link_el is None or date_el is None:
            continue
        title = (title_el.text or "").strip()
        link = (link_el.text or "").strip()
        raw_date = (date_el.text or "").strip()
        if not title or not link or not raw_date:
            continue
        try:
            dt = datetime.strptime(raw_date, "%a, %d %b %Y %H:%M:%S %z")
            d = dt.date()
        except ValueError:
            continue
        out.append({
            "date":   d,
            "title":  title,
            "link":   link,
            "source": "Yahoo",
        })
    return out


# ============================================================
# Finviz snapshot stats (Market Cap, Shs Float, Shs Outstand, ...)
# ============================================================
_FINVIZ_NUM_RE = re.compile(r"([\d.,]+)\s*([KMBT])?", re.I)


def _parse_finviz_num(s: str | None) -> int | None:
    if not s:
        return None
    s = s.strip()
    if s in ("-", "—", ""):
        return None
    m = _FINVIZ_NUM_RE.match(s)
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(
        (m.group(2) or "").upper(), 1
    )
    return int(n * mult)


import json
import time as _time
from pathlib import Path as _Path

_FINVIZ_DISK_CACHE = _Path(__file__).parent / ".finviz_stats_cache.json"
_FINVIZ_DISK_TTL = 7 * 86_400          # 7 days per entry
_finviz_disk_mem: dict | None = None   # in-process load cache


def _load_finviz_disk() -> dict:
    global _finviz_disk_mem
    if _finviz_disk_mem is not None:
        return _finviz_disk_mem
    if _FINVIZ_DISK_CACHE.exists():
        try:
            _finviz_disk_mem = json.loads(_FINVIZ_DISK_CACHE.read_text(encoding="utf-8"))
        except Exception:
            _finviz_disk_mem = {}
    else:
        _finviz_disk_mem = {}
    return _finviz_disk_mem


def _save_finviz_disk(data: dict) -> None:
    try:
        _FINVIZ_DISK_CACHE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def fetch_finviz_stats_cached_only(ticker: str) -> dict:
    """Read from disk cache only. No HTTP. Returns {} if not cached.

    Used by the broad sector-load path where live-scraping 3000+
    tickers would hang on Finviz rate-limits. Live scrapes still
    happen via fetch_finviz_stats() from per-ticker contexts (the
    catalyst dialog).
    """
    disk = _load_finviz_disk()
    entry = disk.get(ticker.upper())
    if entry and (_time.time() - entry.get("_t", 0)) < _FINVIZ_DISK_TTL:
        return {k: v for k, v in entry.items() if not k.startswith("_")}
    return {}


@st.cache_data(ttl=86_400, show_spinner=False)
def fetch_finviz_stats(ticker: str) -> dict:
    """Scrape the Finviz snapshot-table-2 for fundamental stats.

    Two-tier cache:
      - Disk: 7 days per ticker, survives Streamlit restarts and
        accumulates as the dashboard runs. Eliminates cold-start
        Finviz rate-limit pain.
      - Streamlit @cache_data: 24h in-process layer on top.

    Returns {market_cap, float_shares, shares_out} with integer values
    where present, None when the cell was missing or unparseable.
    """
    disk = _load_finviz_disk()
    entry = disk.get(ticker.upper())
    if entry and (_time.time() - entry.get("_t", 0)) < _FINVIZ_DISK_TTL:
        return {k: v for k, v in entry.items() if not k.startswith("_")}

    try:
        r = requests.get(
            f"https://finviz.com/quote.ashx?t={ticker.upper()}",
            headers=HEADERS, timeout=15,
        )
        if r.status_code != 200:
            return {}
        soup = BeautifulSoup(r.text, "lxml")
    except Exception:
        return {}

    # Finviz has rotated this class a few times: snapshot-table2 /
    # snapshot-table-2. Try both, then any table that contains
    # 'Market Cap' as a label.
    table = (soup.find("table", class_="snapshot-table2")
             or soup.find("table", class_="snapshot-table-2"))
    if table is None:
        for t in soup.find_all("table"):
            if t.find(string=lambda s: s and s.strip() == "Market Cap"):
                table = t
                break
    if table is None:
        return {}

    pairs: dict[str, str] = {}
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        for i in range(0, len(cells) - 1, 2):
            label = cells[i].get_text(strip=True)
            value = cells[i + 1].get_text(strip=True)
            if label:
                pairs[label] = value
    result = {
        "market_cap":   _parse_finviz_num(pairs.get("Market Cap")),
        "float_shares": _parse_finviz_num(pairs.get("Shs Float")),
        "shares_out":   _parse_finviz_num(pairs.get("Shs Outstand")),
    }
    # Write back to disk cache if we got at least one useful value
    if any(v is not None for v in result.values()):
        disk[ticker.upper()] = {**result, "_t": _time.time()}
        _save_finviz_disk(disk)
    return result


# ============================================================
# Combined index
# ============================================================
def combined_news_by_date(ticker: str) -> dict[date, list[dict]]:
    """Index headlines from all free sources by trading date.

    Items within a date are ordered by source priority (Finviz first
    because it usually carries the press-release wire headline,
    Yahoo RSS second)."""
    by_date: dict[date, list[dict]] = {}
    for fn in (fetch_finviz_news, fetch_yahoo_rss):
        try:
            for item in fn(ticker):
                by_date.setdefault(item["date"], []).append(item)
        except Exception:
            continue
    return by_date
