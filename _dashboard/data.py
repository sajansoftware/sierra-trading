"""yfinance-backed data layer with filter logic.

Fetches price + free-float per ticker, caches for 15 minutes, and
returns rows grouped by category folder.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import re
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from bs4 import BeautifulSoup

MIN_PRICE = 1.0
MAX_PRICE = 20.0
MAX_FLOAT = 20_000_000
FLOAT_CALC_MARGIN = 0.25  # buffer when estimating float from outstanding shares


@dataclass(frozen=True)
class Quote:
    ticker: str
    price: float | None              # latest live / regular-market price
    previous_close: float | None     # latest completed-session closing price
    float_shares: int | None
    market_cap: int | None
    sector: str | None
    industry: str | None
    name: str | None = None          # company short/long name from yfinance
    summary: str | None = None       # longBusinessSummary from yfinance
    error: str | None = None

    @property
    def close(self) -> float | None:
        """Latest closing price; falls back to live price if close is missing."""
        return self.previous_close if self.previous_close is not None else self.price

    def passes_filter(self) -> bool:
        """Save-to-database criterion: close priced between $1 and $20.

        Float is *informational only* — the ticker is included even if
        yfinance can't return floatShares (which happens intermittently
        when Yahoo 401s on the .info endpoint). Float still displays
        in the table when available.
        """
        if self.error or self.close is None:
            return False
        return MIN_PRICE <= self.close <= MAX_PRICE


def _resolve_float_shares(info: dict) -> int | None:
    """Best-effort free-float resolution.

    1. Direct floatShares from Yahoo (primary).
    2. Fallback: outstanding shares minus insider ownership, with a
       buffer to avoid over-estimating the free float.
    """
    raw = info.get("floatShares")
    if raw is not None and raw > 0:
        return int(raw)

    outstanding = info.get("sharesOutstanding")
    if outstanding is None or outstanding <= 0:
        return None

    insider_pct = info.get("heldPercentInsiders") or 0
    estimated = outstanding * (1 - insider_pct - FLOAT_CALC_MARGIN)
    return max(0, int(estimated))


def _fetch_one(ticker: str) -> Quote:
    try:
        info = yf.Ticker(ticker).info
        if not info:
            return Quote(ticker, None, None, None, None, None, None, error="no data")
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = (
            info.get("regularMarketPreviousClose")
            or info.get("previousClose")
        )
        if price is None and prev_close is None:
            return Quote(ticker, None, None, None, None, None, None, error="no price")
        return Quote(
            ticker=ticker,
            price=float(price) if price is not None else None,
            previous_close=float(prev_close) if prev_close is not None else None,
            float_shares=_resolve_float_shares(info),
            market_cap=info.get("marketCap"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            name=info.get("shortName") or info.get("longName"),
            summary=info.get("longBusinessSummary"),
        )
    except Exception as exc:
        return Quote(ticker, None, None, None, None, None, None, error=str(exc)[:120])


CATALYST_KEYWORDS: list[tuple[str, list[str]]] = [
    ("FDA Approval",      ["fda approval", "fda accept", "fda clearance", "approves", "approved", "510(k)"]),
    ("PDUFA",             ["pdufa"]),
    ("Clinical Data",     ["positive data", "topline", "interim data", "primary endpoint", "phase 1", "phase 2", "phase 3", "phase i", "phase ii", "phase iii", "met endpoint"]),
    ("Trial Update",      ["clinical trial", "enrollment", "first patient", "dosed first", "dosing"]),
    ("Earnings",          ["earnings", "reports q", "quarterly results", "fiscal year", "revenue beat", "revenue miss"]),
    ("Product Launch",    ["launches", "launch of", "commercial launch", "now available", "first sale", "commercialization"]),
    ("Offering",          ["offering", "registered direct", " atm ", "warrant", "dilution", "secondary"]),
    ("M&A",               ["merger", "acquir", "acquisition", "buyout", "to acquire"]),
    ("Partnership",       ["partnership", "collaboration", "licensing", "license agreement", "joint venture"]),
    ("Contract Win",      ["awarded", "contract win", "wins contract", "secures contract"]),
    ("Listing",           ["ipo", "uplisting", "nasdaq listing", "delisting", "reverse split", "stock split"]),
    ("Guidance",          ["raises guidance", "lowers guidance", "outlook", "reaffirms guidance"]),
    ("Patent",            ["patent", "intellectual property"]),
    ("Insider",           ["insider", "buyback", "share repurchase"]),
    ("Analyst",           ["upgrade", "downgrade", "initiates coverage", "price target"]),
]


def classify_catalyst(title: str) -> str:
    """Map a news headline to a catalyst type. Returns 'News' if nothing
    matches; never returns 'Big move' (a non-sentiment placeholder)."""
    if not title:
        return "News"
    t = title.lower()
    for label, keywords in CATALYST_KEYWORDS:
        if any(kw in t for kw in keywords):
            return label
    return "News"


@st.cache_data(ttl=300, show_spinner=False)  # 5 min (intraday refresh)
def fetch_top_movers(
    universe_tickers: tuple[str, ...],
    min_pct: float = 20.0,
    min_price: float = 1.0,
    max_price: float = 20.0,
    max_float: int = 20_000_000,
    max_rows: int = 40,
) -> list[dict]:
    """Today's biggest *pre-market* movers across the universe.

    A ticker qualifies when:
      - close $1-$20 and free float < 20M (passes_filter)
      - pre-market move (PM high vs prior close) >= min_pct
        within the 4:00 AM - 9:29 AM ET window

    LOD / HOD reported below are pre-market low / pre-market high
    (not full-day). Returns rows sorted by PM move descending.
    """
    quotes = fetch_quotes(universe_tickers)
    eligible = [
        q for q in quotes.values()
        if q.passes_filter()                              # price $1-$20
        and q.previous_close and q.previous_close > 0     # need a baseline
        # Float is informational: include when unknown; only exclude when
        # we know it's above the cap.
        and (q.float_shares is None or q.float_shares < max_float)
    ]

    try:
        from zoneinfo import ZoneInfo
        today_et = datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        today_et = datetime.now().astimezone().date()

    def _today_pm_move(q: Quote) -> dict | None:
        try:
            hist = yf.Ticker(q.ticker).history(
                period="1d", interval="5m", prepost=True, auto_adjust=True,
            )
            if hist is None or hist.empty:
                return None
            try:
                hist.index = hist.index.tz_convert("America/New_York")
            except Exception:
                pass
            # Restrict to today's bars, then to the 4:00-9:29 ET pre-market.
            day_bars = hist[hist.index.date == today_et]
            if day_bars.empty:
                return None
            pm_bars = day_bars.between_time("04:00", "09:29")
            if pm_bars.empty:
                return None
            pm_high = float(pm_bars["High"].max())
            pm_low = float(pm_bars["Low"].min())
            move_pct = (pm_high - q.previous_close) / q.previous_close * 100.0
            if move_pct < min_pct:
                return None
            return {
                "ticker":     q.ticker,
                "name":       q.name or q.ticker,
                "prev_close": q.previous_close,
                "lod":        pm_low,
                "hod":        pm_high,
                "move_pct":   move_pct,
                "float":      q.float_shares,
            }
        except Exception:
            return None

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for r in pool.map(_today_pm_move, eligible):
            if r:
                rows.append(r)

    # Enrich with today's news headline (Finviz first, then any source)
    try:
        from news_sources import fetch_finviz_news, fetch_yahoo_rss
        for r in rows:
            news_items = []
            try:
                news_items.extend(fetch_finviz_news(r["ticker"]))
            except Exception:
                pass
            try:
                news_items.extend(fetch_yahoo_rss(r["ticker"]))
            except Exception:
                pass
            # Prefer same-day, then most recent
            todays = [n for n in news_items if n["date"] == today_et]
            best = todays[0] if todays else (news_items[0] if news_items else None)
            if best:
                r["news_title"] = best["title"]
                r["news_link"] = best["link"]
                r["news_source"] = best["source"]
                r["news_type"] = classify_catalyst(best["title"])
            else:
                r["news_title"] = ""
                r["news_link"] = ""
                r["news_source"] = "—"
                r["news_type"] = "News"
    except Exception:
        for r in rows:
            r.setdefault("news_title", "")
            r.setdefault("news_link", "")
            r.setdefault("news_source", "—")
            r.setdefault("news_type", "News")

    rows.sort(key=lambda r: r["move_pct"], reverse=True)
    return rows[:max_rows]


@st.cache_data(ttl=3_600, show_spinner=False)  # 1 hour (intraday-sensitive)
def fetch_premarket_catalysts(
    ticker: str,
    min_price: float = 1.0,
    max_price: float = 20.0,
    min_upside_pct: float = 30.0,
    lookback_days: int = 60,
    max_rows: int = 60,
) -> list[dict]:
    """Detect pre-market (4:00am-9:29am ET) catalyst days.

    yfinance limit: 5-minute bars are only available for the last 60
    days. So this is a 60-day archive, not 5 years.

    A row qualifies when:
      - close (split-adjusted) on the day was between min_price and max_price
      - pre-market upside (PM high vs prior regular-session close)
        >= min_upside_pct

    Returns rows sorted most-recent first with:
        date, pm_low, pm_low_time, pm_high, pm_high_time, prior_close,
        upside_pct, type, title, link, source
    """
    try:
        t = yf.Ticker(ticker)
        intraday = t.history(
            period=f"{lookback_days}d",
            interval="5m",
            prepost=True,
            auto_adjust=True,
        )
        daily = t.history(period=f"{lookback_days + 5}d", interval="1d", auto_adjust=True)
    except Exception:
        return []
    if intraday is None or intraday.empty or daily is None or daily.empty:
        return []

    # Convert intraday to Eastern Time so 4:00-9:29 is the right window.
    try:
        intraday.index = intraday.index.tz_convert("America/New_York")
    except Exception:
        try:
            intraday.index = intraday.index.tz_localize("UTC").tz_convert("America/New_York")
        except Exception:
            return []

    # Daily prior-close lookup: map date -> close.
    daily_close_by_date: dict[date, float] = {}
    for ts, row in daily.iterrows():
        try:
            d = ts.date()
            daily_close_by_date[d] = float(row["Close"])
        except (KeyError, ValueError):
            continue
    sorted_daily_dates = sorted(daily_close_by_date.keys())

    def prior_close(d: date) -> float | None:
        # Find last daily date strictly before d
        prev = None
        for dd in sorted_daily_dates:
            if dd < d:
                prev = dd
            else:
                break
        return daily_close_by_date.get(prev) if prev else None

    # Filter to pre-market window (4:00am-9:29am ET) and group by date.
    pm = intraday.between_time("04:00", "09:29")
    if pm.empty:
        return []

    # Recent yfinance news (~30d) for headline matching
    news_by_date: dict[date, list[dict]] = {}
    try:
        for article in (t.news or []):
            ts_ = article.get("providerPublishTime")
            if not ts_:
                continue
            d_ = datetime.fromtimestamp(ts_).date()
            news_by_date.setdefault(d_, []).append({
                "date":   d_,
                "title":  article.get("title", "") or "",
                "link":   article.get("link", "") or "",
                "source": "Yahoo (yfinance)",
            })
    except Exception:
        pass

    # Multi-source news index
    try:
        from news_sources import combined_news_by_date
        for d_, items in combined_news_by_date(ticker).items():
            news_by_date.setdefault(d_, []).extend(items)
    except Exception:
        pass

    # SEC EDGAR
    try:
        from edgar import fetch_8k_filings, filings_by_date
        filings_idx = filings_by_date(fetch_8k_filings(ticker, years_back=1))
    except Exception:
        filings_idx = {}

    rows: list[dict] = []
    for d, day_bars in pm.groupby(pm.index.date):
        if day_bars.empty:
            continue
        pm_high = float(day_bars["High"].max())
        pm_low = float(day_bars["Low"].min())
        try:
            pm_high_ts = day_bars["High"].idxmax()
            pm_low_ts = day_bars["Low"].idxmin()
        except Exception:
            continue
        pc = prior_close(d)
        if pc is None or pc <= 0:
            continue
        upside_pct = (pm_high - pc) / pc * 100.0
        if upside_pct < min_upside_pct:
            continue
        # Apply $1-$20 filter using the day's regular-session close
        day_close = daily_close_by_date.get(d, pm_high)
        if not (min_price <= day_close <= max_price):
            continue

        # Headline enrichment (same day or 1 day before, since pre-market
        # events often follow overnight news)
        title = link = source = ctype = ""
        for offset in (0, -1, 1, -2, 2):
            for item in news_by_date.get(d + timedelta(days=offset), []):
                title = item["title"]
                link = item["link"]
                source = item["source"]
                ctype = classify_catalyst(title)
                break
            if title:
                break
        if not title:
            for offset in range(-3, 6):
                fls = filings_idx.get(d + timedelta(days=offset), [])
                if fls:
                    f = fls[0]
                    title = f["description"]
                    link = f["link"]
                    source = "SEC EDGAR"
                    ctype = f["type"]
                    break
        if not ctype:
            ctype = "News"
        if not source:
            source = "—"

        rows.append({
            "date":         d,
            "pm_low":       pm_low,
            "pm_low_time":  pm_low_ts.strftime("%I:%M %p ET").lstrip("0"),
            "pm_high":      pm_high,
            "pm_high_time": pm_high_ts.strftime("%I:%M %p ET").lstrip("0"),
            "prior_close":  pc,
            "upside_pct":   upside_pct,
            "type":         ctype,
            "title":        title,
            "link":         link,
            "source":       source,
        })

    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows[:max_rows]


@st.cache_data(ttl=21_600, show_spinner=False)  # 6 hours
def fetch_5y_catalysts(
    ticker: str,
    min_price: float = 1.0,
    max_price: float = 20.0,
    min_rvol: float = 5.0,
    min_upside_pct: float = 50.0,
    max_rows: int = 60,
) -> list[dict]:
    """Detect catalyst days in the last 5 years of trading.

    A row qualifies as a catalyst when ALL of the following hold:
      - split-adjusted close was between `min_price` and `max_price`
      - intraday upside (High vs prior Close) >= `min_upside_pct`
      - relative volume (day's volume / 50d average) >= `min_rvol`

    Float-under-20M is enforced upstream (only universe-eligible
    tickers reach this code), so we don't re-check it here.

    Prices are split-adjusted (auto_adjust=True) so the $1-$20 filter
    holds across reverse splits.

    Returns list of dicts sorted most-recent first:
        date, type, title, link, low, high, close, volume, rvol, upside_pct
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5y", auto_adjust=True)
    except Exception:
        return []
    if hist is None or hist.empty or "High" not in hist or "Close" not in hist:
        return []

    prev_close = hist["Close"].shift(1)
    upside_pct = (hist["High"] - prev_close) / prev_close * 100.0
    avg_vol = hist["Volume"].rolling(50, min_periods=20).mean()
    rvol = hist["Volume"] / avg_vol

    mask = (
        (hist["Close"] >= min_price)
        & (hist["Close"] <= max_price)
        & (upside_pct >= min_upside_pct)
        & (rvol >= min_rvol)
    )

    # Multi-source news index. Finviz (~1-2y of headlines with publisher
    # names) + Yahoo RSS (last ~30-60d). yfinance.news layered in on top
    # for free since we already have the Ticker object.
    try:
        from news_sources import combined_news_by_date
        news_idx = combined_news_by_date(ticker)
    except Exception:
        news_idx = {}
    try:
        for article in (t.news or []):
            ts_ = article.get("providerPublishTime")
            if not ts_:
                continue
            d_ = datetime.fromtimestamp(ts_).date()
            news_idx.setdefault(d_, []).append({
                "date":   d_,
                "title":  article.get("title", "") or "",
                "link":   article.get("link", "") or "",
                "source": "Yahoo (yfinance)",
            })
    except Exception:
        pass

    # Historical 8-K filings from SEC EDGAR (full 5-year window)
    try:
        from edgar import fetch_8k_filings, filings_by_date
        filings_idx = filings_by_date(fetch_8k_filings(ticker, years_back=5))
    except Exception:
        filings_idx = {}

    rows: list[dict] = []
    for ts in hist.index[mask]:
        d = ts.date() if hasattr(ts, "date") else ts
        bar = hist.loc[ts]

        title = ""
        link = ""
        source = ""
        ctype = ""

        # 1) Try the multi-source news index in a tight ±2-day window.
        #    Press releases sometimes hit the wire the trading day before
        #    the price reaction, or land after-hours on the day of.
        best_news = None
        best_news_offset = 99
        for offset in (0, 1, -1, 2, -2):
            for item in news_idx.get(d + timedelta(days=offset), []):
                if abs(offset) < best_news_offset:
                    best_news = item
                    best_news_offset = abs(offset)
                    break
        if best_news:
            title = best_news["title"]
            link = best_news["link"]
            source = best_news["source"]
            ctype = classify_catalyst(title)

        # 2) Fall back to the nearest SEC 8-K within ±5 trading days.
        if not title:
            best_f = None
            best_f_offset = 99
            for offset in range(-5, 8):
                filings = filings_idx.get(d + timedelta(days=offset), [])
                if filings and abs(offset) < best_f_offset:
                    best_f = filings[0]
                    best_f_offset = abs(offset)
            if best_f:
                title = best_f["description"]
                link = best_f["link"]
                source = "SEC EDGAR"
                ctype = best_f["type"]

        if not ctype:
            ctype = "News"
        if not source:
            source = "—"

        rows.append({
            "date":       d,
            "type":       ctype,
            "title":      title,
            "link":       link,
            "source":     source,
            "low":        float(bar["Low"]),
            "high":       float(bar["High"]),
            "close":      float(bar["Close"]),
            "volume":     int(bar["Volume"]) if not pd.isna(bar.get("Volume", 0)) else None,
            "rvol":       float(rvol.loc[ts]) if not pd.isna(rvol.loc[ts]) else None,
            "upside_pct": float(upside_pct.loc[ts]),
        })

    # Most recent first
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows[:max_rows]


def short_blurb(summary: str | None) -> str:
    """First sentence of a yfinance business summary, capped at ~180 chars."""
    if not summary:
        return ""
    chunk = summary.strip()
    for sep in (". ", "\n", ";"):
        idx = chunk.find(sep)
        if 30 < idx < 220:
            chunk = chunk[:idx]
            break
    chunk = chunk.strip().rstrip(".")
    if len(chunk) > 180:
        chunk = chunk[:177].rstrip() + "..."
    return chunk + "." if chunk else ""


@st.cache_data(ttl=900, show_spinner=False)
def fetch_quotes(tickers: tuple[str, ...]) -> dict[str, Quote]:
    """Fetch quotes for the given tickers in parallel. Cached 15 min."""
    out: dict[str, Quote] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        for fut in as_completed(futures):
            q = fut.result()
            out[q.ticker] = q
    return out


@st.cache_data(ttl=86_400, show_spinner=False)
def nasdaq_price_map() -> dict[str, tuple[float, str, str]]:
    """ticker -> (last_price, sector, industry) from the cached NASDAQ
    screener. Used as a fallback when yfinance .info 401s and we have
    no live close - we still want to surface the ticker if NASDAQ
    last-saw it in the $1-$20 band."""
    try:
        from screener import fetch_nasdaq_universe, _parse_price
        raw = fetch_nasdaq_universe()
    except Exception:
        return {}
    out: dict[str, tuple[float, str, str]] = {}
    for r in raw:
        sym = (r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        p = _parse_price(r.get("lastsale"))
        if p is None:
            continue
        out[sym] = (p, (r.get("sector") or "").strip(),
                       (r.get("industry") or "").strip())
    return out


def filtered_by_category(
    universe_dict: dict[str, list[str]],
    ticker_list: list[str],
) -> dict[str, list[Quote]]:
    """Return surviving quotes grouped by folder.

    Pipeline:
      1. yfinance fetch for live close + float (preferred).
      2. If yfinance returns no data, fall back to NASDAQ's last sale
         so the ticker still appears when it was in the $1-$20 band at
         the last NASDAQ snapshot.
    """
    quotes = fetch_quotes(tuple(sorted(ticker_list)))
    nd_prices = nasdaq_price_map()
    result: dict[str, list[Quote]] = {}
    for folder, tickers in universe_dict.items():
        rows: list[Quote] = []
        for t in tickers:
            q = quotes.get(t)
            usable = q is not None and q.passes_filter()
            if not usable:
                # yfinance had no data (or returned a price outside range).
                # If NASDAQ last saw this ticker in range, synthesize a
                # NASDAQ-sourced Quote so it still surfaces.
                nd = nd_prices.get(t)
                if nd is None:
                    continue
                nd_price, nd_sector, nd_industry = nd
                if not (MIN_PRICE <= nd_price <= MAX_PRICE):
                    continue
                q = Quote(
                    ticker=t,
                    price=nd_price,
                    previous_close=nd_price,
                    float_shares=None,
                    market_cap=None,
                    sector=nd_sector,
                    industry=nd_industry,
                    name=t,
                    summary=None,
                )
            rows.append(q)
        rows.sort(key=lambda q: (q.float_shares or 1e12))
        result[folder] = rows
    return result


def tv_num(n: float | int | None) -> str:
    """TradingView-style abbreviated number: 12.5M, 1.23B, 850K."""
    if n is None:
        return "—"
    try:
        f = float(n)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if f < 0 else ""
    f = abs(f)
    if f >= 1e12:
        v, u = f / 1e12, "T"
    elif f >= 1e9:
        v, u = f / 1e9, "B"
    elif f >= 1e6:
        v, u = f / 1e6, "M"
    elif f >= 1e3:
        v, u = f / 1e3, "K"
    else:
        return f"{sign}{f:.2f}"
    if v >= 100:
        s = f"{v:.0f}"
    elif v >= 10:
        s = f"{v:.1f}"
    else:
        s = f"{v:.2f}"
    return f"{sign}{s}{u}"


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _fetch_yfinance_news(t: yf.Ticker, n: int = 12) -> list[dict]:
    """Fallback: most-recent articles from the yfinance news feed."""
    try:
        raw = t.news or []
    except Exception:
        raw = []
    out = []
    for article in raw[:n]:
        ts = article.get("providerPublishTime")
        if not ts:
            continue
        out.append({
            "title":     article.get("title", ""),
            "link":      article.get("link", ""),
            "publisher": article.get("publisher", ""),
            "datetime":  datetime.fromtimestamp(ts),
        })
    return out


def _scrape_website_news(t: yf.Ticker) -> list[dict]:
    """Try to pull press-release links from the company website."""
    try:
        info = t.info or {}
        website = (info.get("website") or "").rstrip("/")
    except Exception:
        website = ""
    if not website:
        return []

    paths = [
        "/investors/press-releases/", "/investors/news/",
        "/news/", "/press/", "/about/news/",
        "/media/press-releases/", "/press-releases/",
    ]
    seen_links: set[str] = set()
    items: list[dict] = []

    for path in paths:
        try:
            url = website + path
            resp = requests.get(url, timeout=8, headers={"User-Agent": UA})
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(strip=True)
                if not title or len(title) < 20 or href in seen_links:
                    continue
                if not any(kw in href.lower() or kw in str(a.parent).lower()
                           for kw in ["press-release", "press_release", "pressrelease",
                                      "news", "announce", "announcement", "update",
                                      "release", "article", "story"]):
                    continue
                # Resolve relative URLs
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    p = urlparse(url)
                    href = f"{p.scheme}://{p.netloc}{href}"
                elif not href.startswith("http"):
                    href = url.rstrip("/") + "/" + href.lstrip("/")

                # Try to extract a date
                parent_text = str(a.parent)
                date_match = re.search(
                    r"(20\d{2})[/-](\d{2})[/-](\d{2})"
                    r"|(\d{1,2})[/-](\d{1,2})[/-](20\d{2})"
                    r"|(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*(20\d{2})",
                    parent_text, re.I,
                )
                date_str = date_match.group(0) if date_match else ""

                seen_links.add(href)
                parsed_dt = None
                if date_str:
                    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y",
                                "%b %d %Y", "%B %d %Y"):
                        try:
                            parsed_dt = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                items.append({
                    "title": title, "link": href,
                    "date": date_str, "datetime": parsed_dt,
                })
        except Exception:
            continue
    return items


def _enrich_with_prices(
    articles: list[dict],
    t: yf.Ticker,
) -> list[dict]:
    """Add daily OHLCV + change % to each article by matching dates."""
    try:
        hist = t.history(period="1mo")
    except Exception:
        hist = None

    px: dict[date, dict] = {}
    if hist is not None and not hist.empty:
        idx = hist.index
        if hasattr(idx, "tz") and idx.tz is not None:
            idx = idx.tz_localize(None)
        for dt, row in zip(idx, hist.itertuples()):
            px[dt.date()] = {
                "open":   float(row.Open),
                "high":   float(row.High),
                "low":    float(row.Low),
                "close":  float(row.Close),
                "volume": int(row.Volume),
            }

    out = []
    for article in articles:
        pub = article.get("datetime")
        if pub is None:
            pub = datetime.now()
        pub_date = pub.date()
        day = px.get(pub_date)
        if day is None:
            d = pub_date - timedelta(days=1)
            for _ in range(5):
                if d in px:
                    day = px[d]
                    break
                d -= timedelta(days=1)
        if day:
            chg = ((day["close"] - day["open"]) / day["open"]) * 100 if day["open"] else None
        else:
            day = {"open": None, "high": None, "low": None, "close": None, "volume": None}
            chg = None
        out.append({**article, **day, "change_pct": chg})
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_catalysts(ticker: str) -> list[dict]:
    """Recent news articles + daily price action for a ticker.

    Tries the company website first; falls back to the yfinance news feed.
    """
    t = yf.Ticker(ticker)

    # 1 — try scraping the company website
    articles = _scrape_website_news(t)

    # 2 — fallback to yfinance news
    if not articles:
        articles = _fetch_yfinance_news(t)

    if not articles:
        return []

    # 3 — enrich with price data
    enriched = _enrich_with_prices(articles, t)
    return enriched[:12]
