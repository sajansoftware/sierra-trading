"""Sentiment Intel — aggregates news sentiment across a sector's
qualifying tickers and surfaces patterns the sector heads / MDs can
report on.

For each sector this computes:
  - Headline counts by sentiment (bull / bear / neutral) over a window
  - Sentiment skew (% bullish vs bearish)
  - Day-over-day shift vs prior baseline
  - Top tickers by bullish-headline count
  - Top tickers by bearish-headline count
  - Notable headline clusters (catalyst types that dominate)
  - Plain-English pattern insights ready for chat or briefing card

Designed to run cheaply: leans on the existing 24h-cached Finviz +
Yahoo RSS pulls in news_sources. No per-render network thrash.
"""

from __future__ import annotations

import streamlit as st
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable


@dataclass
class SectorSentimentSnapshot:
    sector: str
    window_days: int
    n_tickers_scanned: int
    n_tickers_with_news: int
    bull: int = 0
    bear: int = 0
    neutral: int = 0
    today_bull: int = 0
    today_bear: int = 0
    prior_bull: int = 0
    prior_bear: int = 0
    top_bullish: list[tuple[str, int]] = field(default_factory=list)
    top_bearish: list[tuple[str, int]] = field(default_factory=list)
    catalyst_types: list[tuple[str, int]] = field(default_factory=list)
    sample_bull_headlines: list[tuple[str, str]] = field(default_factory=list)
    sample_bear_headlines: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.bull + self.bear + self.neutral

    @property
    def bull_pct(self) -> float:
        return (self.bull / self.total * 100.0) if self.total else 0.0

    @property
    def bear_pct(self) -> float:
        return (self.bear / self.total * 100.0) if self.total else 0.0

    @property
    def skew(self) -> str:
        if self.total < 5:
            return "Thin"
        if self.bull_pct - self.bear_pct >= 20:
            return "Bullish"
        if self.bear_pct - self.bull_pct >= 20:
            return "Bearish"
        return "Mixed"


def _classify_type(title: str) -> str:
    """Lightweight catalyst-type bucket so we can cluster headlines."""
    t = (title or "").lower()
    if any(w in t for w in ("fda approv", "approves", "approved", "510(k)",
                            "ce mark", "marketing authorization")):
        return "Approval"
    if any(w in t for w in ("crl", "complete response letter", "rejects",
                            "approval delay")):
        return "Rejection"
    if any(w in t for w in ("topline", "primary endpoint", "met endpoint",
                            "phase 1", "phase 2", "phase 3", "interim")):
        return "Clinical Data"
    if any(w in t for w in ("offering", "registered direct", "atm offering",
                            "private placement", "warrant exercise",
                            "convertible")):
        return "Offering / Dilution"
    if any(w in t for w in ("acquire", "merger", "tender offer",
                            "definitive agreement", "going private")):
        return "M&A"
    if any(w in t for w in ("partnership", "collaboration",
                            "exclusive license", "licensing")):
        return "Partnership"
    if any(w in t for w in ("earnings", "beats estimates", "misses estimates",
                            "raises guidance", "lowers guidance",
                            "record revenue", "revenue miss")):
        return "Earnings"
    if any(w in t for w in ("contract", "wins contract", "secures contract",
                            "awarded")):
        return "Contract Win"
    if any(w in t for w in ("uplisting", "lists on", "begins trading",
                            "delisting", "non-compliance")):
        return "Listing Status"
    if any(w in t for w in ("ceo", "cfo", "appoint", "resign", "names")):
        return "Management Change"
    if any(w in t for w in ("buyback", "share repurchase", "insider buy",
                            "form 4")):
        return "Insider / Buyback"
    if any(w in t for w in ("lawsuit", "investigation", "subpoena",
                            "class action", "warning letter")):
        return "Legal / Regulatory"
    return "Other"


@st.cache_data(ttl=1800, show_spinner=False, max_entries=64)
def sector_sentiment_snapshot(
    sector: str,
    tickers: tuple[str, ...],
    window_days: int = 7,
    max_tickers: int = 60,
) -> SectorSentimentSnapshot:
    """Walk recent headlines for up to `max_tickers` tickers and build
    an aggregate sentiment view for the sector. Cached 30 minutes."""
    from sentiment import classify_sentiment
    try:
        from news_sources import combined_news_by_date
    except Exception:
        combined_news_by_date = lambda _t: {}

    today = date.today()
    cutoff = today - timedelta(days=window_days)
    prior_cutoff = today - timedelta(days=1)

    snap = SectorSentimentSnapshot(
        sector=sector,
        window_days=window_days,
        n_tickers_scanned=0,
        n_tickers_with_news=0,
    )

    bullish_by_ticker: Counter = Counter()
    bearish_by_ticker: Counter = Counter()
    catalyst_counter: Counter = Counter()
    bull_samples: list[tuple[str, str]] = []
    bear_samples: list[tuple[str, str]] = []

    pool = tickers[:max_tickers]
    snap.n_tickers_scanned = len(pool)

    for tkr in pool:
        try:
            by_date = combined_news_by_date(tkr) or {}
        except Exception:
            continue
        had_news = False
        for d, items in by_date.items():
            if d is None or d < cutoff:
                continue
            for it in items:
                title = (it.get("title") or "").strip()
                if not title:
                    continue
                had_news = True
                sent = classify_sentiment(title)
                if sent == "Bullish":
                    snap.bull += 1
                    bullish_by_ticker[tkr] += 1
                    if len(bull_samples) < 6:
                        bull_samples.append((tkr, title))
                    if d >= prior_cutoff:
                        snap.today_bull += 1
                    else:
                        snap.prior_bull += 1
                elif sent == "Bearish":
                    snap.bear += 1
                    bearish_by_ticker[tkr] += 1
                    if len(bear_samples) < 6:
                        bear_samples.append((tkr, title))
                    if d >= prior_cutoff:
                        snap.today_bear += 1
                    else:
                        snap.prior_bear += 1
                else:
                    snap.neutral += 1
                catalyst_counter[_classify_type(title)] += 1
        if had_news:
            snap.n_tickers_with_news += 1

    snap.top_bullish = bullish_by_ticker.most_common(5)
    snap.top_bearish = bearish_by_ticker.most_common(5)
    snap.catalyst_types = catalyst_counter.most_common(6)
    snap.sample_bull_headlines = bull_samples
    snap.sample_bear_headlines = bear_samples
    return snap


def detect_patterns(snap: SectorSentimentSnapshot) -> list[str]:
    """Return human-readable insights from the snapshot."""
    out: list[str] = []
    if snap.total < 5:
        out.append("Thin headline flow — fewer than 5 classified items "
                   "in the window. Hold off on sentiment-driven calls.")
        return out

    # Headline skew
    skew = snap.skew
    if skew == "Bullish":
        out.append(f"Bullish skew ({snap.bull_pct:.0f}% bull vs "
                   f"{snap.bear_pct:.0f}% bear across {snap.total} items).")
    elif skew == "Bearish":
        out.append(f"Bearish skew ({snap.bear_pct:.0f}% bear vs "
                   f"{snap.bull_pct:.0f}% bull across {snap.total} items).")
    else:
        out.append(f"Mixed tape ({snap.bull_pct:.0f}% bull / "
                   f"{snap.bear_pct:.0f}% bear across {snap.total} items).")

    # Day-over-day shift
    if snap.prior_bull + snap.prior_bear > 0:
        prior_total = snap.prior_bull + snap.prior_bear
        prior_bull_pct = snap.prior_bull / prior_total * 100.0
        today_total = snap.today_bull + snap.today_bear
        if today_total > 0:
            today_bull_pct = snap.today_bull / today_total * 100.0
            delta = today_bull_pct - prior_bull_pct
            if abs(delta) >= 15:
                direction = "improving" if delta > 0 else "deteriorating"
                out.append(f"Sentiment {direction} today vs prior baseline "
                           f"({today_bull_pct:.0f}% bull today vs "
                           f"{prior_bull_pct:.0f}% prior).")

    # Catalyst clustering
    if snap.catalyst_types:
        top_type, top_n = snap.catalyst_types[0]
        if top_n >= 3 and top_type != "Other":
            out.append(f"'{top_type}' cluster — {top_n} headlines in the "
                       "window. Theme is driving the tape.")

    # Concentration in top names
    if snap.top_bullish:
        top_t, n = snap.top_bullish[0]
        if n >= 3:
            out.append(f"{top_t} carrying bullish flow ({n} positive "
                       "headlines).")
    if snap.top_bearish:
        top_t, n = snap.top_bearish[0]
        if n >= 3:
            out.append(f"{top_t} taking heat ({n} negative headlines) — "
                       "watch the borrow.")

    return out


def briefing_lines(snap: SectorSentimentSnapshot) -> list[str]:
    """Short bullet list for the briefing card on the sector page."""
    lines = detect_patterns(snap)
    if snap.catalyst_types:
        types_str = ", ".join(f"{t}({n})" for t, n in snap.catalyst_types[:4])
        lines.append(f"Catalyst mix: {types_str}.")
    return lines
