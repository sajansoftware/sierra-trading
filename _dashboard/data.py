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
        if self.error or self.close is None or self.float_shares is None:
            return False
        return (
            MIN_PRICE <= self.close <= MAX_PRICE
            and self.float_shares < MAX_FLOAT
        )


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


def filtered_by_category(
    universe_dict: dict[str, list[str]],
    ticker_list: list[str],
) -> dict[str, list[Quote]]:
    """Return surviving quotes grouped by folder from the given universe."""
    quotes = fetch_quotes(tuple(sorted(ticker_list)))
    result: dict[str, list[Quote]] = {}
    for folder, tickers in universe_dict.items():
        rows = [quotes[t] for t in tickers if t in quotes and quotes[t].passes_filter()]
        rows.sort(key=lambda q: (q.float_shares or 0))
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
