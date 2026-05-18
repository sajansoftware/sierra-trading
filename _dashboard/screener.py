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

# Healthcare industries that funnel into biotech Red by default.
# Non-biotech health (hospitals, insurance, healthcare IT, distributors)
# are routed to the Healthcare Services sector by classify_ticker_sector.
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
    "Industrial Specialties",
    "Ophthalmic Goods",
    "Other Pharmaceuticals",
    "Pharmaceuticals and Biotechnology",
    "Medicinal Chemicals and Botanical Products",
    "Precision Instruments",
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


# =============================================================================
# Cross-sector classifier: NASDAQ industry -> (sector, sub_sector)
# =============================================================================
# Sector keys match the SECTORS dict in app.py
SECTOR_BIOTECH       = "Biotechnology"
SECTOR_TECH          = "Technology"
SECTOR_ENERGY        = "Energy"
SECTOR_INDUSTRIAL    = "Industrials"
SECTOR_MATERIALS     = "Materials"
SECTOR_CONSUMER_D    = "Consumer_Discretionary"
SECTOR_FINANCIALS    = "Financials"
SECTOR_COMMUNICATION = "Communication_Services"
SECTOR_STAPLES       = "Consumer_Staples"
SECTOR_REALESTATE    = "Real_Estate"
SECTOR_HCSVC         = "Healthcare_Services"

# Map: NASDAQ industry string -> (sector_key, sub_sector_folder)
# Comprehensive mapping built from observed NASDAQ industry vocabulary.
INDUSTRY_TO_SECTOR_SUB: dict[str, tuple[str, str]] = {
    # ---------- Materials ----------
    "Precious Metals":                         (SECTOR_MATERIALS, "Precious_Metals"),
    "Metal Mining":                            (SECTOR_MATERIALS, "Base_Metals"),
    "Mining & Quarrying of Nonmetallic Minerals (No Fuels)": (SECTOR_MATERIALS, "Base_Metals"),
    "Major Chemicals":                         (SECTOR_MATERIALS, "Specialty_Chemicals"),
    "Specialty Chemicals":                     (SECTOR_MATERIALS, "Specialty_Chemicals"),
    "Industrial Specialties":                  (SECTOR_MATERIALS, "Specialty_Chemicals"),
    "Steel/Iron Ore":                          (SECTOR_MATERIALS, "Steel_Iron"),
    "Aluminum":                                (SECTOR_MATERIALS, "Base_Metals"),
    "Containers/Packaging":                    (SECTOR_MATERIALS, "Construction_Materials"),
    "Building Materials":                      (SECTOR_MATERIALS, "Construction_Materials"),
    "Forest Products":                         (SECTOR_MATERIALS, "Construction_Materials"),
    # ---------- Consumer Discretionary ----------
    "Apparel":                                 (SECTOR_CONSUMER_D, "Apparel_Footwear"),
    "Clothing/Shoe/Accessory Stores":          (SECTOR_CONSUMER_D, "Apparel_Footwear"),
    "Auto Manufacturing":                      (SECTOR_CONSUMER_D, "Automotive_EVs"),
    "Auto Parts:O.E.M.":                       (SECTOR_CONSUMER_D, "Automotive_EVs"),
    "Automotive Aftermarket":                  (SECTOR_CONSUMER_D, "Automotive_EVs"),
    "Motor Vehicles":                          (SECTOR_CONSUMER_D, "Automotive_EVs"),
    "Restaurants":                             (SECTOR_CONSUMER_D, "Restaurants_Hospitality"),
    "Hotels/Resorts":                          (SECTOR_CONSUMER_D, "Restaurants_Hospitality"),
    "Other Specialty Stores":                  (SECTOR_CONSUMER_D, "Retail_Specialty"),
    "Department/Specialty Retail Stores":      (SECTOR_CONSUMER_D, "Retail_Specialty"),
    "Catalog/Specialty Distribution":          (SECTOR_CONSUMER_D, "E_commerce"),
    "RETAIL: Building Materials":              (SECTOR_CONSUMER_D, "Home_Garden"),
    "Home Furnishings":                        (SECTOR_CONSUMER_D, "Home_Garden"),
    "Consumer Specialties":                    (SECTOR_CONSUMER_D, "Retail_Specialty"),
    "Recreational Products/Toys":              (SECTOR_CONSUMER_D, "Gaming_Entertainment"),
    "Movies/Entertainment":                    (SECTOR_CONSUMER_D, "Gaming_Entertainment"),
    "Services-Misc. Amusement & Recreation":   (SECTOR_CONSUMER_D, "Gaming_Entertainment"),
    "Other Consumer Services":                 (SECTOR_CONSUMER_D, "Travel_Leisure"),
    "Air Freight/Delivery Services":           (SECTOR_CONSUMER_D, "Travel_Leisure"),
    # ---------- Financials ----------
    "Major Banks":                             (SECTOR_FINANCIALS, "Regional_Banks"),
    "Banks":                                   (SECTOR_FINANCIALS, "Regional_Banks"),
    "Savings Institutions":                    (SECTOR_FINANCIALS, "Regional_Banks"),
    "Commercial Banks":                        (SECTOR_FINANCIALS, "Regional_Banks"),
    "Investment Bankers/Brokers/Service":      (SECTOR_FINANCIALS, "Investment_Banks_Brokers"),
    "Investment Managers":                     (SECTOR_FINANCIALS, "Asset_Management"),
    "Finance/Investors Services":              (SECTOR_FINANCIALS, "Asset_Management"),
    "Life Insurance":                          (SECTOR_FINANCIALS, "Insurance"),
    "Property-Casualty Insurers":              (SECTOR_FINANCIALS, "Insurance"),
    "Specialty Insurers":                      (SECTOR_FINANCIALS, "Insurance"),
    "Diversified Financial Services":          (SECTOR_FINANCIALS, "Specialty_Finance"),
    "Finance: Consumer Services":              (SECTOR_FINANCIALS, "Specialty_Finance"),
    "Finance Companies":                       (SECTOR_FINANCIALS, "Specialty_Finance"),
    "Business Services":                       (SECTOR_FINANCIALS, "Fintech_Payments"),
    # ---------- Communication Services ----------
    "Telecommunications Equipment":            (SECTOR_COMMUNICATION, "Wireless_Wireline_Telecom"),
    "Radio And Television Broadcasting And Communications Equipment": (SECTOR_COMMUNICATION, "Media_Entertainment"),
    "Television Services":                     (SECTOR_COMMUNICATION, "Media_Entertainment"),
    "Cable & Other Pay Television Services":   (SECTOR_COMMUNICATION, "Streaming"),
    "Newspapers/Magazines":                    (SECTOR_COMMUNICATION, "Publishing_News"),
    "Books":                                   (SECTOR_COMMUNICATION, "Publishing_News"),
    "Advertising":                             (SECTOR_COMMUNICATION, "Advertising_MarTech"),
    "Multi-Sector Companies":                  (SECTOR_COMMUNICATION, "Media_Entertainment"),
    # ---------- Consumer Staples ----------
    "Packaged Foods":                          (SECTOR_STAPLES, "Food_Beverage"),
    "Beverages (Production/Distribution)":     (SECTOR_STAPLES, "Food_Beverage"),
    "Specialty Foods":                         (SECTOR_STAPLES, "Food_Beverage"),
    "Meat/Poultry/Fish":                       (SECTOR_STAPLES, "Food_Beverage"),
    "Food Distributors":                       (SECTOR_STAPLES, "Grocery_Distribution"),
    "Food Chains":                             (SECTOR_STAPLES, "Grocery_Distribution"),
    "Consumer Non-Durables":                   (SECTOR_STAPLES, "Household_Products"),
    "Package Goods/Cosmetics":                 (SECTOR_STAPLES, "Personal_Care_Beauty"),
    "Tobacco":                                 (SECTOR_STAPLES, "Tobacco_Vape"),
    # ---------- Real Estate ----------
    "Real Estate Investment Trusts":           (SECTOR_REALESTATE, "Diversified_REITs"),
    "Real Estate":                             (SECTOR_REALESTATE, "Proptech"),
    "Building operators":                      (SECTOR_REALESTATE, "Diversified_REITs"),
    # ---------- Healthcare Services (non-biotech) ----------
    "Managed Health Care":                     (SECTOR_HCSVC, "Health_Insurance"),
    "Hospital/Nursing Management":             (SECTOR_HCSVC, "Hospitals_Health_Systems"),
    "Medical/Nursing Services":                (SECTOR_HCSVC, "Hospitals_Health_Systems"),
    "Health Care Distributors":                (SECTOR_HCSVC, "Pharmacy_Distributors"),
    "Misc Health and Biotechnology Services":  (SECTOR_HCSVC, "Healthcare_IT_Telehealth"),
}

# Keywords that nudge a ticker into Crypto-Adjacent sub-sector of Financials
_CRYPTO_KEYWORDS = re.compile(
    r"\b(bitcoin|crypto|blockchain|digital asset|web3|mining (?:rig|hardware))\b",
    re.IGNORECASE,
)


def classify_ticker_sector(row: dict) -> tuple[str, str] | None:
    """Return (sector_key, sub_sector_folder) for a NASDAQ screener row.
    None means the ticker doesn't fit any extended-screener sector
    (e.g. Healthcare/Tech/Energy/Industrials are handled by their own
    sector modules, not by this cross-sector classifier).
    """
    industry = (row.get("industry") or "").strip()
    name = row.get("name") or ""

    mapped = INDUSTRY_TO_SECTOR_SUB.get(industry)
    if mapped is None:
        return None

    sector, sub = mapped
    # Crypto-adjacent override in Financials
    if sector == SECTOR_FINANCIALS and _CRYPTO_KEYWORDS.search(name):
        sub = "Crypto_Adjacent"
    return sector, sub


@st.cache_data(ttl=86_400, show_spinner=False)
def discover_by_sector(
    target_sector: str,
    min_price: float = 1.0,
    max_price: float = 20.0,
) -> dict[str, list[str]]:
    """Pull all NASDAQ tickers $1-$20 that classify to target_sector.
    Returns {sub_sector_folder: [tickers]}."""
    raw = fetch_nasdaq_universe()
    out: dict[str, list[str]] = {}
    for r in raw:
        sym = (r.get("symbol") or "").strip()
        if not sym or any(c in sym for c in ".^$/"):
            continue
        price = _parse_price(r.get("lastsale"))
        if price is None or not (min_price <= price <= max_price):
            continue
        cls = classify_ticker_sector(r)
        if cls is None or cls[0] != target_sector:
            continue
        _, sub = cls
        out.setdefault(sub, []).append(sym)
    return out
