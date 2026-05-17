"""NASDAQ universe screener.

Pulls the full NASDAQ-listed symbol table from NASDAQ's public screener
API, narrows it to biotech-relevant sectors/industries, and pre-filters
by NASDAQ's last-sale price so we don't waste yfinance calls on names
that obviously won't pass the live $1-$20 filter.

Output: list[dict] with keys
    symbol, name, sector, industry, last_price, market_cap
"""

from __future__ import annotations

import re
from typing import Iterable

import requests
import streamlit as st

NASDAQ_URL = "https://api.nasdaq.com/api/screener/stocks"
NASDAQ_PARAMS = {"tableonly": "true", "exchange": "nasdaq", "download": "true"}
NASDAQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}

# Healthcare industries that all funnel into Red by default
HEALTHCARE_INDUSTRIES: set[str] = {
    "Biotechnology: Biological Products (No Diagnostic Substances)",
    "Biotechnology: Commercial Physical & Biological Resarch",
    "Biotechnology: Electromedical & Electrotherapeutic Apparatus",
    "Biotechnology: In Vitro & In Vivo Diagnostic Substances",
    "Biotechnology: Pharmaceutical Preparations",
    "Biotechnology: Laboratory Analytical Instruments",
    "Medical Specialities",
    "Medical/Dental Instruments",
    "Medical Electronics",
    "Medical/Nursing Services",
    "Industrial Specialties",
    "Ophthalmic Goods",
    "Other Pharmaceuticals",
    "Pharmaceuticals and Biotechnology",
    "Misc Health and Biotechnology Services",
    "Medicinal Chemicals and Botanical Products",
    "Precision Instruments",
    "Hospital/Nursing Management",
}

# Industries where every member is biotech-relevant (no keyword filter).
# These cleanly map to one of the biotech color categories.
NON_HC_INCLUDE_ALL: set[str] = {
    "Agricultural Chemicals",
    "Farming/Seeds/Milling",
    "Environmental Services",
    "Water Supply",
}

# Catch-all industries where keyword match in the company name is required
# (most members are unrelated petrochemicals, shipping, packaged food, etc.).
NON_HC_KEYWORD_REQUIRED: set[str] = {
    "Major Chemicals",
    "Specialty Chemicals",
    "Marine Transportation",
    "Packaged Foods",
    "Beverages (Production/Distribution)",
    "Specialty Foods",
    "Food Distributors",
    "Meat/Poultry/Fish",
}

# Backwards-compat union (referenced elsewhere historically)
NON_HEALTHCARE_CANDIDATES: set[str] = NON_HC_INCLUDE_ALL | NON_HC_KEYWORD_REQUIRED

# Keywords used to admit a non-healthcare ticker into the biotech universe
BIOTECH_KEYWORDS = re.compile(
    r"\b("
    r"bio|biotech|biological|enzyme|biofuel|biodiesel|bioethanol|"
    r"bioplastic|biopolymer|bio-based|synthetic biology|fermentation|"
    r"probiotic|nutraceutical|plant-based|alternative protein|"
    r"seed|crop|ag-?biotech|agritech|veterinary|animal health|"
    r"aquaculture|salmon|algae|seaweed|"
    r"bioremediation|water purification|water treatment|wastewater|recycl|"
    r"genom|proteom|bioinformat|computational biology"
    r")\b",
    re.IGNORECASE,
)


def _parse_price(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(re.sub(r"[^\d.]", "", s))
    except ValueError:
        return None


def _parse_marketcap(s: str | None) -> float | None:
    if not s:
        return None
    try:
        v = float(re.sub(r"[^\d.]", "", s))
        return v if v > 0 else None
    except ValueError:
        return None


@st.cache_data(ttl=86_400, show_spinner=False)  # 24 hours
def fetch_nasdaq_universe() -> list[dict]:
    """Hit NASDAQ's screener API and return the raw rows."""
    r = requests.get(
        NASDAQ_URL, params=NASDAQ_PARAMS, headers=NASDAQ_HEADERS, timeout=30
    )
    r.raise_for_status()
    return r.json()["data"]["rows"]


def is_biotech_relevant(row: dict) -> bool:
    sector = (row.get("sector") or "").strip()
    industry = (row.get("industry") or "").strip()
    name = row.get("name") or ""
    if sector == "Health Care" and industry in HEALTHCARE_INDUSTRIES:
        return True
    if industry in NON_HC_INCLUDE_ALL:
        return True
    if industry in NON_HC_KEYWORD_REQUIRED and BIOTECH_KEYWORDS.search(name):
        return True
    return False


def biotech_candidates(
    min_price: float = 1.0,
    max_price: float = 20.0,
) -> list[dict]:
    """Filtered, normalised list of NASDAQ biotech candidates."""
    raw = fetch_nasdaq_universe()
    out: list[dict] = []
    for row in raw:
        if not is_biotech_relevant(row):
            continue
        # filter out obvious symbol oddities (warrants, units, preferreds)
        sym = (row.get("symbol") or "").strip()
        if not sym or any(c in sym for c in ".^$/") or sym.endswith(("W", "U", "R")):
            # Allow common biotech tickers ending in W/U/R (avoid over-filtering)
            # Only skip if symbol has typical warrant/unit suffix patterns
            if "." in sym or "^" in sym or "/" in sym:
                continue
        price = _parse_price(row.get("lastsale"))
        if price is None or not (min_price <= price <= max_price):
            continue
        out.append(
            {
                "symbol":     sym,
                "name":       (row.get("name") or "").strip(),
                "sector":     (row.get("sector") or "").strip(),
                "industry":   (row.get("industry") or "").strip(),
                "last_price": price,
                "market_cap": _parse_marketcap(row.get("marketCap")),
            }
        )
    return out


def candidate_symbols(rows: Iterable[dict]) -> list[str]:
    return [r["symbol"] for r in rows]
