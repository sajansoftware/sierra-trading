"""yfinance-backed data layer with filter logic.

Fetches price + free-float per ticker, caches for 15 minutes, and
returns rows grouped by category folder.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace as dc_replace
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
    country: str | None = None       # country of domicile from yfinance

    @property
    def close(self) -> float | None:
        """Latest closing price; falls back to live price if close is missing."""
        return self.previous_close if self.previous_close is not None else self.price

    def passes_filter(self) -> bool:
        """Price-only screen: $1 <= close <= $20.

        Float < 20M is enforced separately in filtered_by_category()
        after the Finviz/shares-out enrichment step so we don't drop
        tickers before the fallback data has a chance to populate.
        """
        if self.error or self.close is None:
            return False
        return MIN_PRICE <= self.close <= MAX_PRICE

    def passes_full_criteria(self) -> bool:
        """Strict criterion: price $1-$20 AND a known float strictly under 20M.

        Float-source fallback chain (in filtered_by_category):
          yfinance -> Finviz -> Finviz shares_out * 0.7
        If none of those returned a number, the ticker is excluded
        (we can't honor the float<20M constraint without the data).
        """
        if not self.passes_filter():
            return False
        if self.float_shares is None or self.float_shares <= 0:
            return False
        return self.float_shares < MAX_FLOAT


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
            country=info.get("country"),
        )
    except Exception as exc:
        return Quote(ticker, None, None, None, None, None, None, error=str(exc)[:120])


# Order matters: more specific patterns first so they win the match.
CATALYST_KEYWORDS: list[tuple[str, list[str]]] = [
    # ---- Regulatory milestones ----
    ("FDA Approval",      ["fda approval", "fda approves", "fda accept", "fda clearance",
                           "approves", "approved", "510(k)", "ce mark"]),
    ("CRL",               ["complete response letter", " crl ", "(crl)", "fda rejects",
                           "rejects approval", "approval delay"]),
    ("PDUFA",             ["pdufa"]),
    ("IND Clearance",     ["ind clearance", "ind application", "investigational new drug",
                           " ind ", "ind accepted", "ind cleared"]),
    ("NDA / BLA",         ["nda submission", "bla submission", "submits nda", "submits bla",
                           "files nda", "files bla", "marketing authorisation", "ma application"]),
    ("Designation",       ["fast track", "orphan drug", "breakthrough designation",
                           "rmat designation", "priority review", "qualified infectious",
                           "rare pediatric"]),
    ("FDA Meeting",       ["type a meeting", "type b meeting", "type c meeting",
                           "type d meeting", "pre-ind meeting", "end-of-phase",
                           "end of phase", "fda meeting", "fda feedback",
                           "fda interaction", "fda agreement", "regulatory update",
                           "regulatory milestone", "regulatory pathway",
                           "constructive meeting", "meeting with fda",
                           "meeting with u.s. fda", "meeting with the fda",
                           "fda guidance", "fda response"]),
    # ---- Clinical / data ----
    ("Clinical Data",     ["positive data", "topline", "interim data", "primary endpoint",
                           "met endpoint", "trial results", "study results", "data readout",
                           "phase 1 data", "phase 2 data", "phase 3 data",
                           "phase i data", "phase ii data", "phase iii data",
                           "study demonstrates", "study shows", "demonstrates predictive",
                           "demonstrates efficacy", "shows efficacy", "shows benefit",
                           "presents data", "presents results", "publication in",
                           "published in", "peer-reviewed", "research demonstrates",
                           "research shows", "clinical evidence", "preclinical data",
                           "biomarker", "rppa", "cancer institute", "phase 1/2",
                           "phase 2/3", "tumor response", "overall survival",
                           "progression-free", "response rate", "durable response"]),
    ("Trial Enrollment",  ["enrollment", "enrolled", "first patient", "dosed first",
                           "patient dosed", "trial initiation", "begins enrolling",
                           "completes enrollment"]),
    ("Conference",        ["asco", "aacr", "esmo", "ash ", "asgct", "wcle", "ada ",
                           "presents at", "presentation at", "poster presentation",
                           "abstract accepted"]),
    # ---- Corporate / business ----
    ("Earnings",          ["earnings", "reports q", "quarterly results", "fiscal year",
                           "revenue beat", "revenue miss", "financial results",
                           "audited financial", "annual results", "full year",
                           "half year results", "interim results", "earnings call",
                           "first quarter", "second quarter", "third quarter",
                           "fourth quarter", "q1 ", "q2 ", "q3 ", "q4 ",
                           "reports first", "reports second", "reports third",
                           "reports fourth", "reports full"]),
    ("Cash Runway",       ["cash runway", "cash position", "cash balance", "burn rate",
                           "funded into", "operating runway"]),
    ("Product Launch",    ["launches", "launch of", "commercial launch", "now available",
                           "first sale", "commercialization", "introduces",
                           "unveils", "rolls out", "expands product",
                           "expands market reach", "integrates", "integration with",
                           "successfully integrates", "platform launch"]),
    ("Offering",          ["public offering", "follow-on offering", "registered direct",
                           " atm ", "atm offering", "warrant", "secondary offering",
                           "closing of initial public offering", "closing of offering",
                           "closing of public", "institutional offering",
                           "closing of $", "closes offering", "closes $",
                           "pricing of", "prices public offering",
                           "underwritten offering"]),
    ("Private Placement", ["private placement", "pipe ", "convertible note", "convertible debt"]),
    ("Buyout / Rumor",    ["buyout", "acquisition rumor", "acquisition talks",
                           "exploring strategic alternatives", "strategic review",
                           "takeover", "to be acquired", "considers sale"]),
    ("M&A",               ["merger", "acquir", "acquisition", "to acquire", "combines with"]),
    ("Partnership",       ["partnership", "collaboration", "licensing", "license agreement",
                           "joint venture", "co-development", "strategic alliance",
                           "strategic agreement", "strategic partnership",
                           "alongside", "joins forces", "teams up", "teams with",
                           "alliance with", "sponsorship", "strategic brand"]),
    ("Contract Win",      ["awarded", "contract win", "wins contract", "secures contract",
                           "government contract", "wins funding", "secures funding"]),
    ("Reverse Split",     ["reverse split", "reverse stock split", "1-for-", "1 for ",
                           "share consolidation", "consolidation of shares",
                           "regain compliance", "nasdaq compliance", "minimum bid price"]),
    ("Listing",           ["ipo", "uplisting", "nasdaq listing", "delisting", "stock split",
                           "begins trading", "lists on", "joins russell",
                           "added to index", "stock symbol"]),
    ("Guidance",          ["raises guidance", "lowers guidance", "outlook",
                           "reaffirms guidance", "guidance update"]),
    ("Patent",             ["patent granted", "patent allowance", "patent issued",
                            "patent extension", "intellectual property", "patent"]),
    ("Institutional Buy", ["institutional ownership", "13d", "13g", "schedule 13",
                           "stake in", "passive stake", "active investor"]),
    ("Insider Buy",       ["insider buy", "insider purchase", "buyback",
                           "share repurchase", "form 4 purchase"]),
    ("Analyst",           ["upgrade", "downgrade", "initiates coverage", "price target",
                           "raises target", "lowers target"]),
    ("Conference",        ["webinar", "investor presentation", "ceo presentation",
                           "fireside chat", "investor day", "r&d day",
                           "key opinion leader", "kol event", "annual meeting",
                           "investor conference", "investor webcast", "q&a webinar"]),
    ("Management Change", ["ceo resigns", "cfo resigns", "appoints", "appointment of",
                           "names ceo", "names cfo", "names chief", "new ceo",
                           "new cfo", "steps down", "named president",
                           "board of directors", "board appoints",
                           "joins board", "appointed to the board"]),
    ("Operational Update", ["operational update", "business update", "company update",
                            "corporate update", "progress update", "milestone",
                            "highlights", "year in review", "expands operations",
                            "expands manufacturing", "scaling manufacturing",
                            "facility", "manufacturing capacity"]),
    ("Legal / Regulatory", ["lawsuit", "class action", "investigation", "subpoena",
                            "securities investigation", "warning letter",
                            "doj investigation", "sec investigation",
                            "non-compliance", "non-reliance", "restatement",
                            "material weakness", "going concern", "substantial doubt"]),
]


def classify_catalyst(title: str) -> str:
    """Map a news headline to a catalyst type. Every non-empty headline
    receives a real tag — if no taxonomy entry matches we fall back to
    'Press Release' (a generic but visible tag) so no row ever shows
    'No news' when a catalyst is present.

    'No news' is only returned for a truly empty / boilerplate headline.
    """
    if not title:
        return "No news"
    t = title.lower()
    # Filter out generic wire boilerplate that the news APIs return as
    # 'catalyst' but isn't actually company-specific (e.g. AP's
    # 'BC-Most Active Stocks').
    GENERIC = ("most active stocks", "stocks moving", "biggest gainers",
               "biggest losers", "market movers")
    if any(g in t for g in GENERIC):
        return "No news"
    for label, keywords in CATALYST_KEYWORDS:
        if any(kw in t for kw in keywords):
            return label
    # Fallback: a real headline exists but no taxonomy entry matched.
    # Tag it as a generic Press Release rather than 'No news' so the
    # row always carries a visible classification.
    return "Press Release"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_top_movers_dual(
    universe_tickers: tuple[str, ...],
    min_pct: float = 10.0,
    min_price: float = 1.0,
    max_price: float = 20.0,
    max_float: int = 20_000_000,
    max_rows: int = 100,
) -> dict[str, list[dict]]:
    """One scan, two slices — returns {"main": [...], "early": [...]}.

    Pulls today's 5-minute intraday bars ONCE per ticker, then
    computes both window results in a single pass. Saves yfinance
    bandwidth and avoids the rate-limit thrash that happened when
    each tab triggered its own scan.
    """
    nd_prices = nasdaq_price_map()
    seeds: dict[str, Quote] = {}
    for t in universe_tickers:
        nd = nd_prices.get(t)
        if nd is None:
            continue
        nd_price, nd_sector, nd_industry, nd_mc, nd_country = nd
        if not (min_price <= nd_price <= max_price):
            continue
        seeds[t] = Quote(
            ticker=t, price=nd_price, previous_close=nd_price,
            float_shares=None,
            market_cap=int(nd_mc) if nd_mc else None,
            sector=nd_sector, industry=nd_industry,
            name=t, summary=None, country=nd_country,
        )
    fv_stats = _finviz_stats_batch(tuple(sorted(seeds.keys()))) if seeds else {}
    enriched: dict[str, Quote] = {}
    for t, seed in seeds.items():
        enriched[t] = _enrich_with_fallbacks(seed, nd_prices.get(t), fv_stats.get(t), None)

    def _passes(q: Quote) -> bool:
        if not q.previous_close or q.previous_close <= 0:
            return False
        if not (min_price <= q.previous_close <= max_price):
            return False
        if q.float_shares is not None and q.float_shares > max_float:
            return False
        return True

    eligible = [q for q in enriched.values() if _passes(q)]

    try:
        from zoneinfo import ZoneInfo
        today_et = datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        today_et = datetime.now().astimezone().date()

    def _scan_one(q: Quote) -> tuple[dict | None, dict | None]:
        """Return (main_row, early_row) for one ticker. One yfinance
        call; both windows evaluated from the same bars."""
        try:
            hist = yf.Ticker(q.ticker).history(
                period="1d", interval="5m", prepost=True, auto_adjust=True,
            )
            if hist is None or hist.empty:
                return None, None
            try:
                hist.index = hist.index.tz_convert("America/New_York")
            except Exception:
                pass
            day_bars = hist[hist.index.date == today_et]
            if day_bars.empty:
                return None, None
        except Exception:
            return None, None

        def _compute(window_start: str, window_end: str) -> dict | None:
            try:
                pm = day_bars.between_time(window_start, window_end)
            except Exception:
                return None
            if pm.empty:
                return None
            ref_price = float(pm.iloc[0].get("Open") or 0.0)
            if ref_price <= 0:
                return None
            trigger = ref_price * (1.0 + min_pct / 100.0)
            pm_high = float(pm["High"].max())
            if pm_high < trigger:
                return None
            try:
                pm_high_ts = pm["High"].idxmax()
            except Exception:
                return None
            move_pct = (pm_high - ref_price) / ref_price * 100.0
            try:
                ref_time = pm.index[0].strftime("%H:%M ET")
            except Exception:
                ref_time = ""
            try:
                high_time = pm_high_ts.strftime("%H:%M ET")
            except Exception:
                high_time = ""
            return {
                "ticker":     q.ticker,
                "name":       q.name or q.ticker,
                "prev_close": q.previous_close,
                "lod":        ref_price,
                "hod":        pm_high,
                "move_pct":   move_pct,
                "float":      q.float_shares,
                "ref_time":   ref_time,
                "high_time":  high_time,
                "country":    q.country or "",
            }

        return (_compute("07:00", "09:29"),
                _compute("04:00", "06:59"))

    main_rows: list[dict] = []
    early_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for main_r, early_r in pool.map(_scan_one, eligible):
            if main_r:
                main_rows.append(main_r)
            if early_r:
                early_rows.append(early_r)

    # Sort each slice and enrich both with news (one news call per
    # unique ticker across both slices).
    main_rows.sort(key=lambda r: -r["move_pct"])
    early_rows.sort(key=lambda r: -r["move_pct"])
    main_rows = main_rows[:max_rows]
    early_rows = early_rows[:max_rows]

    try:
        from news_sources import fetch_finviz_news, fetch_yahoo_rss
        seen_news: dict[str, dict] = {}
        for r in (main_rows + early_rows):
            tkr = r["ticker"]
            if tkr in seen_news:
                cached = seen_news[tkr]
                r["news_title"]  = cached["title"]
                r["news_link"]   = cached["link"]
                r["news_source"] = cached["source"]
                r["news_type"]   = cached["type"]
                continue
            items = []
            try: items.extend(fetch_finviz_news(tkr))
            except Exception: pass
            try: items.extend(fetch_yahoo_rss(tkr))
            except Exception: pass
            todays = [n for n in items if n["date"] == today_et]
            best = todays[0] if todays else (items[0] if items else None)
            if best:
                payload = {
                    "title":  best["title"],
                    "link":   best["link"],
                    "source": best["source"],
                    "type":   classify_catalyst(best["title"]),
                }
            else:
                payload = {"title": "", "link": "", "source": "—", "type": "—"}
            seen_news[tkr] = payload
            r["news_title"]  = payload["title"]
            r["news_link"]   = payload["link"]
            r["news_source"] = payload["source"]
            r["news_type"]   = payload["type"]
    except Exception:
        for r in (main_rows + early_rows):
            r.setdefault("news_title", "")
            r.setdefault("news_link", "")
            r.setdefault("news_source", "—")
            r.setdefault("news_type", "—")

    return {"main": main_rows, "early": early_rows}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_penny_movers(
    max_rows: int = 100,
    min_move_pct: float = 30.0,
    min_rvol: float = 5.0,
    max_float: int = 20_000_000,
) -> list[dict]:
    """Today's sub-$1 penny stock movers — high RVOL, big PM moves.

    Seeds from the full NASDAQ universe filtered to $0.001–$0.999,
    enriches with Finviz float data, then scans yfinance 5-min
    intraday bars for the full pre-market window (4:00–9:29 AM ET).

    Criteria:
      - Price $0.001–$0.999 (sub-$1 penny stocks)
      - Float < 20M (when known)
      - Move ≥ 30% from window-open price
      - RVOL ≥ 5.0 (today's volume / average volume)
    """
    nd_prices = nasdaq_price_map()
    seeds: dict[str, Quote] = {}
    for t, nd in nd_prices.items():
        nd_price, nd_sector, nd_industry, nd_mc, nd_country = nd
        if not (0.001 <= nd_price <= 0.999):
            continue
        seeds[t] = Quote(
            ticker=t, price=nd_price, previous_close=nd_price,
            float_shares=None,
            market_cap=int(nd_mc) if nd_mc else None,
            sector=nd_sector, industry=nd_industry,
            name=t, summary=None, country=nd_country,
        )
    if not seeds:
        return []

    fv_stats = _finviz_stats_batch(tuple(sorted(seeds.keys())))
    enriched: dict[str, Quote] = {}
    for t, seed in seeds.items():
        enriched[t] = _enrich_with_fallbacks(seed, nd_prices.get(t), fv_stats.get(t), None)

    def _passes(q: Quote) -> bool:
        if not q.previous_close or q.previous_close <= 0:
            return False
        if not (0.001 <= q.previous_close <= 0.999):
            return False
        if q.float_shares is not None and q.float_shares > max_float:
            return False
        return True

    eligible = [q for q in enriched.values() if _passes(q)]

    try:
        from zoneinfo import ZoneInfo
        today_et = datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        today_et = datetime.now().astimezone().date()

    def _scan_one(q: Quote) -> dict | None:
        try:
            t_obj = yf.Ticker(q.ticker)
            hist = t_obj.history(
                period="1d", interval="5m", prepost=True, auto_adjust=True,
            )
            if hist is None or hist.empty:
                return None
            try:
                hist.index = hist.index.tz_convert("America/New_York")
            except Exception:
                pass
            day_bars = hist[hist.index.date == today_et]
            if day_bars.empty:
                return None
            pm = day_bars.between_time("04:00", "09:29")
            if pm.empty:
                return None
            ref_price = float(pm.iloc[0].get("Open") or 0.0)
            if ref_price <= 0:
                return None
            trigger = ref_price * (1.0 + min_move_pct / 100.0)
            pm_high = float(pm["High"].max())
            if pm_high < trigger:
                return None
            move_pct = (pm_high - ref_price) / ref_price * 100.0
            # RVOL: today's volume / average volume
            try:
                avg_vol = t_obj.info.get("averageVolume") or 0
            except Exception:
                avg_vol = 0
            today_vol = float(day_bars["Volume"].sum()) if "Volume" in day_bars else 0
            rvol = (today_vol / avg_vol) if avg_vol > 0 else 0.0
            if rvol < min_rvol:
                return None
            try:
                pm_high_ts = pm["High"].idxmax()
                high_time = pm_high_ts.strftime("%H:%M ET")
            except Exception:
                high_time = ""
            try:
                ref_time = pm.index[0].strftime("%H:%M ET")
            except Exception:
                ref_time = ""
            return {
                "ticker":     q.ticker,
                "name":       q.name or q.ticker,
                "prev_close": q.previous_close,
                "lod":        ref_price,
                "hod":        pm_high,
                "move_pct":   move_pct,
                "float":      q.float_shares,
                "ref_time":   ref_time,
                "high_time":  high_time,
                "rvol":       rvol,
                "country":    q.country or "",
            }
        except Exception:
            return None

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for r in pool.map(_scan_one, eligible):
            if r:
                rows.append(r)

    # News enrichment
    try:
        from news_sources import fetch_finviz_news, fetch_yahoo_rss
        for r in rows:
            news_items = []
            try: news_items.extend(fetch_finviz_news(r["ticker"]))
            except Exception: pass
            try: news_items.extend(fetch_yahoo_rss(r["ticker"]))
            except Exception: pass
            todays = [n for n in news_items if n["date"] == today_et]
            best = todays[0] if todays else (news_items[0] if news_items else None)
            if best:
                r["news_title"]  = best["title"]
                r["news_link"]   = best["link"]
                r["news_source"] = best["source"]
                r["news_type"]   = classify_catalyst(best["title"])
            else:
                r["news_title"]  = ""
                r["news_link"]   = ""
                r["news_source"] = "—"
                r["news_type"]   = "—"
    except Exception:
        for r in rows:
            r.setdefault("news_title", "")
            r.setdefault("news_link", "")
            r.setdefault("news_source", "—")
            r.setdefault("news_type", "—")

    rows.sort(key=lambda r: -r["move_pct"])
    return rows[:max_rows]


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_penny_candidates(
    max_float: int = 20_000_000,
) -> list[Quote]:
    """All sub-$1 penny stocks with sector-style enrichment.

    Returns Quote objects suitable for the standard sector table layout
    (Ticker, Close, Float, Mkt Cap, Country, Description).  Sorted by
    float ascending.  Cached 15 minutes.
    """
    nd_prices = nasdaq_price_map()
    seeds: dict[str, Quote] = {}
    for t, nd in nd_prices.items():
        nd_price, nd_sector, nd_industry, nd_mc, nd_country = nd
        if not (0.001 <= nd_price <= 0.999):
            continue
        seeds[t] = Quote(
            ticker=t, price=nd_price, previous_close=nd_price,
            float_shares=None,
            market_cap=int(nd_mc) if nd_mc else None,
            sector=nd_sector, industry=nd_industry,
            name=t, summary=None, country=nd_country,
        )
    if not seeds:
        return []

    fv_stats = _finviz_stats_batch(tuple(sorted(seeds.keys())))

    try:
        from verifier import fetch_nasdaq_desc_cached_only, fetch_nasdaq_desc
    except Exception:
        fetch_nasdaq_desc_cached_only = lambda t: ""
        fetch_nasdaq_desc = lambda t: ""

    enriched: dict[str, Quote] = {}
    for t, seed in seeds.items():
        desc = fetch_nasdaq_desc_cached_only(t) or None
        eq = _enrich_with_fallbacks(seed, nd_prices.get(t), fv_stats.get(t), desc)
        # Keep if price in range; drop if known float exceeds max
        if not (0.001 <= (eq.close or 0) <= 0.999):
            continue
        if eq.float_shares is not None and eq.float_shares > max_float:
            continue
        enriched[t] = eq

    # Fetch NASDAQ descriptions for survivors that lack one
    missing = [t for t, q in enriched.items() if not q.summary]
    if missing:
        def _one(t):
            try:
                return t, fetch_nasdaq_desc(t)
            except Exception:
                return t, ""
        with ThreadPoolExecutor(max_workers=6) as pool:
            for t, d in pool.map(_one, missing):
                if d:
                    enriched[t] = dc_replace(enriched[t], summary=d)

    rows = list(enriched.values())
    rows.sort(key=lambda q: (q.float_shares or 1e12))
    return rows


@st.cache_data(ttl=300, show_spinner=False)
def fetch_top_movers(
    universe_tickers: tuple[str, ...],
    min_pct: float = 10.0,
    min_price: float = 1.0,
    max_price: float = 20.0,
    max_float: int = 20_000_000,
    max_rows: int = 100,
    window_start: str = "07:00",
    window_end:   str = "09:29",
) -> list[dict]:
    """Today's biggest *pre-market* movers across the universe.

    A ticker qualifies when:
      - close between `min_price` and `max_price` (default $1-$20)
      - free float < `max_float` (default 20M)
      - The window's HIGH is at least (window-open * (1 + min_pct/100)).
        i.e. the stock rallied ≥ min_pct (default 10%) from its
        opening price at `window_start`. For the main tab that's
        the 7:00 AM price; for the early tab it's the 4:00 AM price.

    A ticker that pops in BOTH windows surfaces in BOTH tabs (each
    tab computes its own reference from its own window-open).
    """
    # FAST path: build seeds from NASDAQ + Finviz, skip yfinance .info
    # (it 401s constantly). yfinance.history per eligible ticker below
    # computes the actual PM move.
    nd_prices = nasdaq_price_map()
    seeds: dict[str, Quote] = {}
    for t in universe_tickers:
        nd = nd_prices.get(t)
        if nd is None:
            continue
        nd_price, nd_sector, nd_industry, nd_mc, nd_country = nd
        # Honor the function args, not the module-level MIN/MAX_PRICE.
        if not (min_price <= nd_price <= max_price):
            continue
        seeds[t] = Quote(
            ticker=t, price=nd_price, previous_close=nd_price,
            float_shares=None,
            market_cap=int(nd_mc) if nd_mc else None,
            sector=nd_sector, industry=nd_industry,
            name=t, summary=None, country=nd_country,
        )
    fv_stats = _finviz_stats_batch(tuple(sorted(seeds.keys()))) if seeds else {}
    enriched_quotes: dict[str, Quote] = {}
    for t, seed in seeds.items():
        enriched_quotes[t] = _enrich_with_fallbacks(seed, nd_prices.get(t), fv_stats.get(t), None)

    def _passes(q: Quote) -> bool:
        if not q.previous_close or q.previous_close <= 0:
            return False
        if not (min_price <= q.previous_close <= max_price):
            return False
        # Float gate — only enforced when we actually know the float.
        # If float is unknown (Finviz miss), let it through so we
        # don't silently drop everything when scraping is degraded.
        if q.float_shares is not None and q.float_shares > max_float:
            return False
        return True

    eligible = [q for q in enriched_quotes.values() if _passes(q)]

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
            day_bars = hist[hist.index.date == today_et]
            if day_bars.empty:
                return None
            pm_bars = day_bars.between_time(window_start, window_end)
            if pm_bars.empty:
                return None
            # Reference price = OPEN of the first bar in the window.
            # For the main tab that's the 7:00 AM bar; for the early
            # tab the 4:00 AM bar. yfinance 5-min bars are indexed by
            # their start time, so iloc[0] is the bar at or just
            # after window_start.
            first_bar = pm_bars.iloc[0]
            ref_price = float(first_bar.get("Open") or 0.0)
            if ref_price <= 0:
                return None
            trigger_price = ref_price * (1.0 + min_pct / 100.0)
            pm_high = float(pm_bars["High"].max())
            if pm_high < trigger_price:
                return None
            try:
                pm_high_ts = pm_bars["High"].idxmax()
            except Exception:
                return None
            move_pct = (pm_high - ref_price) / ref_price * 100.0
            try:
                ref_time = pm_bars.index[0].strftime("%H:%M ET")
            except Exception:
                ref_time = ""
            try:
                high_time = pm_high_ts.strftime("%H:%M ET")
            except Exception:
                high_time = ""
            return {
                "ticker":     q.ticker,
                "name":       q.name or q.ticker,
                "prev_close": q.previous_close,
                "lod":        ref_price,        # reference (window-open) price
                "hod":        pm_high,          # actual peak in window
                "move_pct":   move_pct,         # gain from ref
                "float":      q.float_shares,
                "ref_time":   ref_time,         # e.g. "07:00 ET"
                "high_time":  high_time,
                "country":    q.country or "",
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
                r["news_type"] = "—"
    except Exception:
        for r in rows:
            r.setdefault("news_title", "")
            r.setdefault("news_link", "")
            r.setdefault("news_source", "—")
            # If a title made it onto the row, classify it; otherwise
            # mark as "—" (genuinely no catalyst).
            if r.get("news_title"):
                r.setdefault("news_type", classify_catalyst(r["news_title"]))
            else:
                r.setdefault("news_type", "—")

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

    try:
        from sentiment import classify_sentiment
    except Exception:
        def classify_sentiment(_title: str) -> str:
            return "Neutral"

    rows: list[dict] = []
    for d, day_bars in pm.groupby(pm.index.date):
        if day_bars.empty:
            continue
        pm_high = float(day_bars["High"].max())
        try:
            pm_high_ts = day_bars["High"].idxmax()
        except Exception:
            continue

        pc = prior_close(d)
        if pc is None or pc <= 0:
            continue
        # Initial filter (vs prior close) to qualify the day as a catalyst.
        if (pm_high - pc) / pc * 100.0 < min_upside_pct:
            continue
        # Apply $1-$20 filter using the day's regular-session close
        day_close = daily_close_by_date.get(d, pm_high)
        if not (min_price <= day_close <= max_price):
            continue

        # Collect ALL news sources that have a headline on or near this
        # catalyst day. Need to know the earliest news time so PM Low can
        # be calculated for the pre-news window. Search ±2 days.
        all_sources: list[dict] = []
        seen_titles: set[str] = set()
        for offset in (0, -1, 1, -2, 2):
            for item in news_by_date.get(d + timedelta(days=offset), []):
                ttl = (item.get("title") or "").strip()
                if not ttl or ttl in seen_titles:
                    continue
                seen_titles.add(ttl)
                all_sources.append(item)
        # SEC EDGAR can corroborate
        sec_match: dict | None = None
        for offset in range(-3, 6):
            fls = filings_idx.get(d + timedelta(days=offset), [])
            if fls:
                sec_match = fls[0]
                break

        # Choose primary headline + secondary source
        if all_sources:
            primary = all_sources[0]
            title = primary["title"]
            link = primary["link"]
            source = primary["source"]
        elif sec_match:
            title = sec_match["description"]
            link = sec_match["link"]
            source = "SEC EDGAR"
        else:
            title = link = ""
            source = "—"

        # Distinct corroborating sources (drop duplicates by source name)
        distinct_source_names: list[str] = []
        for s in all_sources:
            sn = s.get("source") or ""
            if sn and sn not in distinct_source_names:
                distinct_source_names.append(sn)
        if sec_match and "SEC EDGAR" not in distinct_source_names:
            distinct_source_names.append("SEC EDGAR")
        sources_count = len(distinct_source_names)
        secondary_source = (distinct_source_names[1]
                            if sources_count >= 2 else "")

        # PM Low: lowest Low between 4:00 AM and the bar of the news
        # catalyst. We use the earliest available news timestamp on the
        # catalyst day; fall back to the PM-High bar timestamp when news
        # time is unknown. Result is the lowest pre-news price.
        news_time = None
        for s in all_sources:
            dt = s.get("datetime")
            if isinstance(dt, datetime) and dt.date() == d:
                if news_time is None or dt < news_time:
                    news_time = dt
        try:
            if news_time is not None:
                try:
                    nt_et = news_time.astimezone(pm.index.tz)
                except Exception:
                    nt_et = news_time
                before_news = day_bars[day_bars.index < nt_et]
                if not before_news.empty:
                    pm_low_window = before_news
                else:
                    pm_low_window = day_bars[day_bars.index <= pm_high_ts]
            else:
                # No news timestamp - use everything up to (and including)
                # the PM High bar as the pre-catalyst window.
                pm_low_window = day_bars[day_bars.index <= pm_high_ts]
            pm_low = float(pm_low_window["Low"].min())
        except Exception:
            pm_low = float(day_bars["Low"].min())

        # Upside formula per spec: (PM High - PM Low) / PM Low * 100
        if pm_low and pm_low > 0:
            upside_pct = (pm_high - pm_low) / pm_low * 100.0
        else:
            upside_pct = 0.0

        # Type = catalyst type (FDA Approval, Clinical Data, etc.).
        # Sentiment = Bullish / Bearish / Neutral. Independent of type.
        if title:
            ctype = classify_catalyst(title)
        elif sec_match:
            ctype = sec_match.get("type", "News")
        else:
            ctype = "News"
        sentiment = classify_sentiment(title) if title else "Neutral"
        unverified = sources_count < 2

        rows.append({
            "date":             d,
            "pm_low":           pm_low,
            "pm_high":          pm_high,
            "pm_high_time":     pm_high_ts.strftime("%I:%M %p ET").lstrip("0"),
            "prior_close":      pc,
            "upside_pct":       upside_pct,
            "type":             ctype,
            "sentiment":        sentiment,
            "title":            title,
            "link":             link,
            "source":           source,
            "secondary_source": secondary_source,
            "sources_count":    sources_count,
            "unverified":       unverified,
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
            ctype = "No news"
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
def nasdaq_price_map() -> dict[str, tuple[float, str, str, float | None, str]]:
    """ticker -> (last_price, sector, industry, market_cap, country).

    Sourced from the cached NASDAQ screener (24h cache). Used as
    fallback data when yfinance .info 401s on the .info endpoint.
    """
    try:
        from screener import fetch_nasdaq_universe, _parse_price, _parse_marketcap
        raw = fetch_nasdaq_universe()
    except Exception:
        return {}
    out: dict[str, tuple[float, str, str, float | None, str]] = {}
    for r in raw:
        sym = (r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        p = _parse_price(r.get("lastsale"))
        if p is None:
            continue
        mc = _parse_marketcap(r.get("marketCap"))
        out[sym] = (
            p,
            (r.get("sector") or "").strip(),
            (r.get("industry") or "").strip(),
            mc,
            (r.get("country") or "").strip(),
        )
    return out


@st.cache_data(ttl=43_200, show_spinner=False)
def _finviz_stats_batch(tickers: tuple[str, ...]) -> dict[str, dict]:
    """Read Finviz stats from the DISK CACHE ONLY. Instant.

    No live HTTP for the broad sector load - Finviz rate-limits at
    scale so a 3000-ticker live scrape would hang. Tickers not yet
    in the disk cache fall through to the implied-shares estimate.
    Live Finviz scrapes still happen via per-ticker contexts (catalyst
    dialog) and on the prewarm_finviz.py script.
    """
    try:
        from news_sources import fetch_finviz_stats_cached_only
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for t in tickers:
        stats = fetch_finviz_stats_cached_only(t)
        if stats:
            out[t] = stats
    return out


@st.cache_data(ttl=86_400, show_spinner=False)
def _nasdaq_descriptions_batch(tickers: tuple[str, ...]) -> dict[str, str]:
    """Parallel NASDAQ company-profile fetch for company descriptions.
    Returns ticker -> first sentence of the company description.
    Cached 24h."""
    try:
        from verifier import _nasdaq_profile_raw, _short_sentence
    except Exception:
        return {}
    out: dict[str, str] = {}
    def _one(t: str):
        try:
            raw = _nasdaq_profile_raw(t)
            data = (raw.get("data") or {}) if isinstance(raw, dict) else {}
            for k in ("CompanyDescription", "companyDescription",
                      "Description", "description", "BusinessDescription"):
                v = data.get(k)
                if isinstance(v, dict):
                    v = v.get("value") or v.get("text") or ""
                if v:
                    return t, _short_sentence(str(v).strip(), max_chars=220)
            return t, ""
        except Exception:
            return t, ""
    with ThreadPoolExecutor(max_workers=10) as pool:
        for t, desc in pool.map(_one, tickers):
            if desc:
                out[t] = desc
    return out


def _enrich_with_fallbacks(
    q: Quote,
    nd: tuple[float, str, str, float | None] | None,
    fv: dict | None,
    nd_desc: str | None,
) -> Quote:
    """Fill missing float / market_cap / summary on a Quote.

    Float-source chain (best to worst):
      1. yfinance .floatShares (when present on the seed)
      2. Finviz Shs Float
      3. Finviz Shs Outstand * 0.70
      4. NASDAQ market_cap / price * 0.70  <- guarantees a number
         for every ticker that has both price and mcap.
    """
    float_shares = q.float_shares
    market_cap = q.market_cap
    summary = q.summary

    if (float_shares is None or float_shares <= 0) and fv:
        fs = fv.get("float_shares")
        if fs:
            float_shares = fs
        else:
            so = fv.get("shares_out")
            if so:
                float_shares = int(so * 0.70)
    if (market_cap is None or market_cap <= 0) and fv:
        mc = fv.get("market_cap")
        if mc:
            market_cap = mc
    if (market_cap is None or market_cap <= 0) and nd and nd[3]:
        market_cap = int(nd[3])
    # Final-fallback float estimate: implied shares from market cap
    if (float_shares is None or float_shares <= 0) and market_cap and q.close and q.close > 0:
        implied_shares = market_cap / q.close
        float_shares = int(implied_shares * 0.70)
    if not summary and nd_desc:
        summary = nd_desc

    if (float_shares == q.float_shares
            and market_cap == q.market_cap
            and summary == q.summary):
        return q
    return dc_replace(q,
                      float_shares=float_shares,
                      market_cap=market_cap,
                      summary=summary)


@st.cache_data(ttl=1800, show_spinner=False)
def _filtered_by_category_cached(
    universe_tuple: tuple[tuple[str, tuple[str, ...]], ...],
    ticker_tuple: tuple[str, ...],
) -> dict[str, list[Quote]]:
    """Hashable-key wrapper so Streamlit can cache the final dict.

    Inputs converted from dict/list to nested tuples before the cache
    key is computed; on a hit we return the previously-built dict and
    skip all the Finviz / NASDAQ / iteration work.
    """
    _cache_v2 = True  # bytecode bump: force re-cache after country fix
    universe_dict = {k: list(v) for k, v in universe_tuple}
    return _filtered_by_category_impl(universe_dict, list(ticker_tuple))


def filtered_by_category(
    universe_dict: dict[str, list[str]],
    ticker_list: list[str],
) -> dict[str, list[Quote]]:
    """Public entry: forwards to the cached implementation."""
    uni_tuple = tuple((k, tuple(v)) for k, v in universe_dict.items())
    return _filtered_by_category_cached(uni_tuple, tuple(ticker_list))


def _filtered_by_category_impl(
    universe_dict: dict[str, list[str]],
    ticker_list: list[str],
) -> dict[str, list[Quote]]:
    """Return surviving quotes grouped by folder.

    FAST path:
      1. Build seed Quotes from cached NASDAQ snapshot (price/sector/
         industry/mcap/name) - no per-ticker network call.
      2. Parallel Finviz enrichment (workers=10) for float / mcap /
         shares-out. Disk-cached 7d per ticker so the second visit
         per week is instant.
      3. Filter by passes_full_criteria (price $1-$20 + float<20M).
      4. NASDAQ profile descriptions for surviving tickers.

    yfinance .info is skipped here - it 401s constantly and burns
    minutes per cold load. yfinance.history is still used for the
    catalyst dialog (different endpoint, more reliable).
    """
    nd_prices = nasdaq_price_map()

    seeds: dict[str, Quote] = {}
    for t in ticker_list:
        nd = nd_prices.get(t)
        if nd is None:
            continue
        nd_price, nd_sector, nd_industry, nd_mc, nd_country = nd
        if not (MIN_PRICE <= nd_price <= MAX_PRICE):
            continue
        seeds[t] = Quote(
            ticker=t,
            price=nd_price,
            previous_close=nd_price,
            float_shares=None,
            market_cap=int(nd_mc) if nd_mc else None,
            sector=nd_sector,
            industry=nd_industry,
            name=t,
            summary=None,
            country=nd_country,
        )

    fv_stats = _finviz_stats_batch(tuple(sorted(seeds.keys()))) if seeds else {}

    # First pass: enrich with whatever's already cached on disk.
    try:
        from verifier import fetch_nasdaq_desc_cached_only, fetch_nasdaq_desc
    except Exception:
        fetch_nasdaq_desc_cached_only = lambda t: ""
        fetch_nasdaq_desc = lambda t: ""

    enriched_pass: dict[str, Quote] = {}
    for t, seed in seeds.items():
        desc = fetch_nasdaq_desc_cached_only(t) or None
        eq = _enrich_with_fallbacks(seed, nd_prices.get(t), fv_stats.get(t), desc)
        if eq.passes_full_criteria():
            enriched_pass[t] = eq

    # Second pass: for surviving tickers that don't have a description
    # yet, fetch live from NASDAQ in parallel. Each successful fetch
    # writes to the 30-day disk cache so subsequent loads are instant.
    missing = [t for t, q in enriched_pass.items() if not q.summary]
    if missing:
        def _one(t):
            try:
                return t, fetch_nasdaq_desc(t)
            except Exception:
                return t, ""
        with ThreadPoolExecutor(max_workers=6) as pool:
            for t, d in pool.map(_one, missing):
                if d:
                    enriched_pass[t] = dc_replace(enriched_pass[t], summary=d)

    result: dict[str, list[Quote]] = {}
    for folder, tickers in universe_dict.items():
        rows = [enriched_pass[t] for t in tickers if t in enriched_pass]
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
    # pandas turns None into NaN inside DataFrames; treat NaN/inf as missing
    if f != f or f in (float("inf"), float("-inf")):
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
