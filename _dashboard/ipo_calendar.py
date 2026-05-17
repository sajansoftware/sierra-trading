"""NASDAQ IPO calendar — upcoming + filed pipeline, filtered to $1-$20.

Pulls the public NASDAQ IPO calendar for the current and next two
months, normalises the row shape, parses share-price ranges, and
classifies each IPO into one of the dashboard's macro-sectors
(Biotechnology / Technology / Energy / Other) using company-name
keywords. Cached for 6 hours.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import requests
import streamlit as st

NASDAQ_IPO_URL = "https://api.nasdaq.com/api/ipo/calendar"
NASDAQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}


@dataclass(frozen=True)
class IPO:
    ticker: str
    company: str
    price_low: float | None
    price_high: float | None
    shares: int | None
    deal_size: float | None
    expected_date: str | None
    exchange: str
    status: str
    sector: str

    @property
    def price_display(self) -> str:
        if self.price_low is None:
            return "TBD"
        if self.price_high and self.price_high != self.price_low:
            return f"${self.price_low:.2f}–${self.price_high:.2f}"
        return f"${self.price_low:.2f}"


# Sector classification keywords (longest-match wins where overlap exists)
SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Biotechnology": [
        "therapeutic", "pharma", "biotech", "bio ", "biosciences",
        "medical", "medicine", "medtech", "medi-", "gene", "oncolog",
        "vaccine", "clinic", "diagnostic", "health", "neuro",
        "cardio", "derma", "cell ther", "immun", " bio", "biopharm",
        "lifesci", "life sci", "genomic", "rx ", " rx", "biosc",
    ],
    "Technology": [
        "tech", "software", "cloud", "cyber", " ai ", "ai-", "ai ",
        "saas", "platform", "data", "analytics", "digital", "robot",
        "quantum", "metaverse", "blockchain", "crypto", "fintech",
        "payments", "internet", "online", "app ", "studios",
        "interactive", "semiconductor", "chip ", "computing",
    ],
    "Energy": [
        "energy", "oil ", "gas ", "petroleum", "solar", "wind",
        "renewable", "hydro", "nuclear", "uranium", "mining",
        "battery", "power ", "lithium", "carbon", "rare earth",
        "minerals", "metals",
    ],
}


def _classify_sector(company: str) -> str:
    name = (company or "").lower()
    best = ("Other", 0)
    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if kw in name and len(kw) > best[1]:
                best = (sector, len(kw))
    return best[0]


def _parse_price(raw: str | None) -> tuple[float | None, float | None]:
    """Parse '$5.00' or '$5.00 - $7.00' or '5.00' into (low, high)."""
    if not raw:
        return None, None
    nums = re.findall(r"\d+\.?\d*", str(raw).replace(",", ""))
    if not nums:
        return None, None
    vals = [float(n) for n in nums if n]
    if not vals:
        return None, None
    low = min(vals)
    high = max(vals)
    return low, high


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(re.sub(r"[^\d]", "", str(raw)))
    except ValueError:
        return None


def _parse_dollar(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(re.sub(r"[^\d.]", "", str(raw)))
    except ValueError:
        return None


def _fetch_month(ym: str) -> dict:
    r = requests.get(
        NASDAQ_IPO_URL, params={"date": ym},
        headers=NASDAQ_HEADERS, timeout=20,
    )
    r.raise_for_status()
    return r.json().get("data", {}) or {}


def _normalise(row: dict, status: str) -> IPO | None:
    ticker = (row.get("proposedTickerSymbol") or "").strip().upper()
    company = (row.get("companyName") or "").strip()
    if not company:
        return None
    low, high = _parse_price(row.get("proposedSharePrice"))
    return IPO(
        ticker=ticker or "—",
        company=company,
        price_low=low,
        price_high=high,
        shares=_parse_int(row.get("sharesOffered")),
        deal_size=_parse_dollar(row.get("dollarValueOfSharesOffered")),
        expected_date=row.get("expectedPriceDate") or row.get("filedDate"),
        exchange=(row.get("proposedExchange") or "").strip(),
        status=status,
        sector=_classify_sector(company),
    )


@st.cache_data(ttl=21_600, show_spinner=False)   # 6 hours
def fetch_ipo_calendar(
    months_ahead: int = 3,
    min_price: float = 1.0,
    max_price: float = 20.0,
) -> dict[str, list[IPO]]:
    """Return {sector -> [IPO, ...]} for the next `months_ahead` months,
    filtered to upcoming + filed deals with proposed price in [min, max].
    Filed deals without a price (TBD) are excluded so the $1-$20
    constraint stays meaningful."""
    today = date.today().replace(day=1)
    months = []
    for i in range(months_ahead):
        d = today + timedelta(days=32 * i)
        months.append(d.strftime("%Y-%m"))

    rows: list[IPO] = []
    for ym in months:
        try:
            data = _fetch_month(ym)
        except Exception:
            continue
        for status_key, status_label in [
            ("upcoming", "Upcoming"),
            ("priced",   "Priced"),
        ]:
            section = data.get(status_key) or {}
            for r in (section.get("rows") or []):
                ipo = _normalise(r, status_label)
                if ipo is None:
                    continue
                if ipo.price_low is None:
                    continue
                if not (min_price <= ipo.price_low <= max_price):
                    continue
                rows.append(ipo)

    # De-dupe by ticker+company (a deal can show up in multiple months)
    seen: set[tuple] = set()
    unique: list[IPO] = []
    for r in rows:
        key = (r.ticker, r.company)
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    # Sort: Upcoming first, then Priced; within each, by date asc
    status_order = {"Upcoming": 0, "Priced": 1}

    def _sort_key(r: IPO):
        try:
            d = datetime.fromisoformat(r.expected_date) if r.expected_date else None
        except (TypeError, ValueError):
            d = None
        return (status_order.get(r.status, 9), d is None, d or datetime.max, r.ticker)

    unique.sort(key=_sort_key)

    by_sector: dict[str, list[IPO]] = {
        "Biotechnology": [], "Technology": [], "Energy": [], "Other": [],
    }
    for r in unique:
        by_sector[r.sector].append(r)
    return by_sector
