"""Three-source category verification for a ticker.

For a given ticker + assigned-sector pair, we pull descriptions from
three independent sources and check whether each one mentions
keywords associated with that sector:

1. yfinance (sector / industry / longBusinessSummary)
2. NASDAQ official company-profile API (sector / industry / description)
3. The company's own website (homepage / about page text)

A source 'matches' when its description text contains one or more
sector-relevance keywords. Confidence is 'high' when >=2 of 3 match,
'low' when only 1 matches, 'none' when 0 match. UI can flag the
low-confidence rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
import streamlit as st
import yfinance as yf
from bs4 import BeautifulSoup


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/json,application/xml"}


@dataclass(frozen=True)
class SourceCheck:
    source: str
    sector_label: str          # e.g. "Healthcare / Biotechnology"
    snippet: str               # first sentence or so of the description
    matches: bool              # does the snippet/labels match expected sector?
    link: str                  # URL the user can click to verify


# Keywords (lowercased) that indicate a source supports the assigned sector.
SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Biotechnology": [
        "biotech", "biotechnology", "pharma", "pharmaceutical", "therapeutic",
        "drug", "vaccine", "clinical-stage", "medical", "medicines",
        "oncology", "antibody", "gene", "rna", "biopharmaceutical",
    ],
    "Technology": [
        "software", "saas", "cloud", "ai", "artificial intelligence",
        "platform", "data", "cybersecurity", "semiconductor", "computer",
        "internet", "digital", "fintech", "technology",
    ],
    "Energy": [
        "oil", "gas", "petroleum", "drilling", "midstream", "refining",
        "solar", "wind", "renewable", "energy", "uranium", "coal",
    ],
    "Industrials": [
        "aerospace", "defense", "construction", "engineering", "machinery",
        "industrial", "shipping", "logistics", "trucking", "manufacturing",
        "electrical equipment", "ev charging", "fuel cell",
    ],
    "Materials": [
        "mining", "metals", "lithium", "uranium", "rare earth", "copper",
        "gold", "silver", "steel", "iron", "chemicals", "cement",
        "aggregates", "specialty chemicals",
    ],
    "Consumer_Discretionary": [
        "retail", "apparel", "footwear", "automotive", "ev", "restaurant",
        "hotel", "leisure", "gaming", "ecommerce", "consumer",
        "specialty stores",
    ],
    "Financials": [
        "bank", "banking", "insurance", "investment", "asset management",
        "fintech", "payments", "broker", "lending", "financial",
        "crypto", "blockchain",
    ],
    "Communication_Services": [
        "telecom", "wireless", "media", "broadcasting", "publishing",
        "advertising", "streaming", "internet platform", "satellite",
    ],
    "Consumer_Staples": [
        "food", "beverage", "grocery", "household", "personal care",
        "cosmetics", "tobacco", "vape", "packaged foods",
    ],
    "Real_Estate": [
        "reit", "real estate", "property", "trust", "office", "residential",
        "commercial", "data center", "mortgage",
    ],
    "Healthcare_Services": [
        "hospital", "nursing", "managed care", "health insurance",
        "telehealth", "pharmacy", "distributor", "medical device",
        "dental", "vision",
    ],
}


def _text_matches_sector(text: str, sector: str) -> bool:
    if not text:
        return False
    t = text.lower()
    keywords = SECTOR_KEYWORDS.get(sector, [])
    return any(kw in t for kw in keywords)


def _short_sentence(text: str, max_chars: int = 200) -> str:
    if not text:
        return ""
    t = text.strip()
    cut = t.find(". ")
    if 30 < cut < max_chars:
        return t[:cut + 1]
    return (t[:max_chars] + "…") if len(t) > max_chars else t


# ===========================================================
# Source 1: yfinance
# ===========================================================
def _check_yfinance(ticker: str, sector: str) -> SourceCheck:
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    yf_sector = info.get("sector") or ""
    yf_industry = info.get("industry") or ""
    summary = info.get("longBusinessSummary") or ""
    label = f"{yf_sector} / {yf_industry}".strip(" /") or "(no data)"
    combined = f"{yf_sector} {yf_industry} {summary}"
    return SourceCheck(
        source="yfinance",
        sector_label=label,
        snippet=_short_sentence(summary),
        matches=_text_matches_sector(combined, sector),
        link=f"https://finance.yahoo.com/quote/{ticker}/profile",
    )


# ===========================================================
# Source 2: NASDAQ official company-profile API
# ===========================================================
@st.cache_data(ttl=86_400, show_spinner=False)
def _nasdaq_profile_raw(ticker: str) -> dict:
    url = f"https://api.nasdaq.com/api/company/{ticker.upper()}/company-profile"
    try:
        r = requests.get(
            url,
            headers={
                **HEADERS,
                "Origin": "https://www.nasdaq.com",
                "Referer": "https://www.nasdaq.com/",
            },
            timeout=15,
        )
        if r.status_code != 200:
            return {}
        return r.json() or {}
    except Exception:
        return {}


def _check_nasdaq(ticker: str, sector: str) -> SourceCheck:
    raw = _nasdaq_profile_raw(ticker)
    data = (raw.get("data") or {}) if isinstance(raw, dict) else {}
    # Nasdaq profile JSON structure: { data: { CompanyName, Sector,
    #   Industry, CompanyDescription, ... } } but field names vary.
    def get(*keys):
        for k in keys:
            v = data.get(k)
            if isinstance(v, dict):
                v = v.get("value") or v.get("text") or ""
            if v:
                return v
        return ""

    nd_sector = get("Sector", "sector")
    nd_industry = get("Industry", "industry")
    description = get("CompanyDescription", "companyDescription", "Description", "description", "BusinessDescription")
    label = f"{nd_sector} / {nd_industry}".strip(" /") or "(no data)"
    combined = f"{nd_sector} {nd_industry} {description}"
    return SourceCheck(
        source="NASDAQ",
        sector_label=label,
        snippet=_short_sentence(description),
        matches=_text_matches_sector(combined, sector),
        link=f"https://www.nasdaq.com/market-activity/stocks/{ticker.lower()}",
    )


# ===========================================================
# Source 3: Company website (homepage / about page)
# ===========================================================
ABOUT_PATHS = ("/about", "/about-us", "/company", "/about/company", "")


@st.cache_data(ttl=86_400, show_spinner=False)
def _fetch_website_text(website: str) -> tuple[str, str]:
    """Return (best_text_blob, used_url). Tries the homepage and common
    /about paths, picks whichever returns the most meaningful body text."""
    if not website:
        return "", ""
    base = website.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base
    best_text = ""
    best_url = ""
    for path in ABOUT_PATHS:
        url = base + path
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200 or not r.text:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            # Strip script/style noise
            for tag in soup(["script", "style", "noscript", "header", "nav", "footer"]):
                tag.decompose()
            text = " ".join(soup.get_text(" ", strip=True).split())
            # Prefer pages with more meaningful content (proxy: length)
            if len(text) > len(best_text):
                best_text = text[:4000]   # cap to avoid blowing memory
                best_url = url
        except Exception:
            continue
    return best_text, best_url


def _check_website(ticker: str, sector: str) -> SourceCheck:
    """Find the company website via yfinance first, NASDAQ profile as
    fallback (yfinance frequently 401s lately)."""
    website = ""
    try:
        info = yf.Ticker(ticker).info or {}
        website = info.get("website") or ""
    except Exception:
        pass
    if not website:
        nd = _nasdaq_profile_raw(ticker)
        data = (nd.get("data") or {}) if isinstance(nd, dict) else {}
        for key in ("URL", "Website", "url", "website"):
            v = data.get(key)
            if isinstance(v, dict):
                v = v.get("value") or v.get("text") or ""
            if v:
                website = str(v)
                break
    text, used_url = _fetch_website_text(website)
    return SourceCheck(
        source="Website",
        sector_label=urlparse(website).netloc if website else "(no website)",
        snippet=_short_sentence(text, max_chars=240),
        matches=_text_matches_sector(text, sector),
        link=used_url or website,
    )


# ===========================================================
# Public API
# ===========================================================
_UNAVAILABLE_LABELS = ("(no data)", "(no website)")


@st.cache_data(ttl=43_200, show_spinner=False)  # 12 hours
def verify_categorization(ticker: str, sector: str) -> tuple[list[SourceCheck], str]:
    """Return (per-source checks, confidence_label).

    Confidence is computed against sources that actually returned data.
    yfinance is intermittently 401-blocked; we don't punish a ticker
    when a source is unreachable, only when it actively disagrees.
    """
    checks = [
        _check_yfinance(ticker, sector),
        _check_nasdaq(ticker, sector),
        _check_website(ticker, sector),
    ]
    available = [c for c in checks if c.sector_label not in _UNAVAILABLE_LABELS]
    n_total = len(available)
    n_match = sum(1 for c in available if c.matches)
    if n_total == 0:
        confidence = "none"
    elif n_match == n_total:
        confidence = "high"
    elif n_match / n_total >= 0.5:
        confidence = "high"
    elif n_match >= 1:
        confidence = "low"
    else:
        confidence = "none"
    return checks, confidence


# =============================================================================
# Disk-backed NASDAQ description cache (for the Description column)
# =============================================================================
import json as _json
import time as _time
from pathlib import Path as _Path

_NASDAQ_DESC_CACHE = _Path(__file__).parent / ".nasdaq_desc_cache.json"
_NASDAQ_DESC_TTL = 30 * 86_400        # 30 days per entry
_nasdaq_desc_mem: dict | None = None


def _load_nasdaq_desc_disk() -> dict:
    global _nasdaq_desc_mem
    if _nasdaq_desc_mem is not None:
        return _nasdaq_desc_mem
    if _NASDAQ_DESC_CACHE.exists():
        try:
            _nasdaq_desc_mem = _json.loads(_NASDAQ_DESC_CACHE.read_text(encoding="utf-8"))
        except Exception:
            _nasdaq_desc_mem = {}
    else:
        _nasdaq_desc_mem = {}
    return _nasdaq_desc_mem


def _save_nasdaq_desc_disk(data: dict) -> None:
    try:
        _NASDAQ_DESC_CACHE.write_text(_json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def fetch_nasdaq_desc_cached_only(ticker: str) -> str:
    """Return the cached NASDAQ description (or '' if not cached / expired)."""
    disk = _load_nasdaq_desc_disk()
    entry = disk.get(ticker.upper())
    if entry and (_time.time() - entry.get("_t", 0)) < _NASDAQ_DESC_TTL:
        return entry.get("d", "")
    return ""


def fetch_nasdaq_desc(ticker: str) -> str:
    """Disk-cached single NASDAQ description fetch. 30d TTL."""
    cached = fetch_nasdaq_desc_cached_only(ticker)
    if cached:
        return cached
    raw = _nasdaq_profile_raw(ticker)
    data = (raw.get("data") or {}) if isinstance(raw, dict) else {}
    desc = ""
    for k in ("CompanyDescription", "companyDescription",
              "Description", "description", "BusinessDescription"):
        v = data.get(k)
        if isinstance(v, dict):
            v = v.get("value") or v.get("text") or ""
        if v:
            desc = _short_sentence(str(v).strip(), max_chars=220)
            break
    if desc:
        disk = _load_nasdaq_desc_disk()
        disk[ticker.upper()] = {"d": desc, "_t": _time.time()}
        _save_nasdaq_desc_disk(disk)
    return desc
