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
EXCHANGES = ("nasdaq", "nyse", "amex")
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
    """Hit the NASDAQ screener API across NASDAQ + NYSE + AMEX and merge.

    NASDAQ.com hosts the screener for all three US exchanges via the
    same endpoint with an `exchange` parameter. Tickers are deduped by
    symbol with the NASDAQ row winning on collision.
    """
    out: dict[str, dict] = {}
    for exch in EXCHANGES:
        try:
            r = requests.get(
                NASDAQ_URL,
                params={"tableonly": "true", "exchange": exch, "download": "true"},
                headers=NASDAQ_HEADERS,
                timeout=30,
            )
            r.raise_for_status()
            rows = r.json()["data"]["rows"] or []
        except Exception:
            continue
        for row in rows:
            sym = (row.get("symbol") or "").strip().upper()
            if not sym:
                continue
            # Tag which exchange this came from (useful for UI/debug)
            row["_exchange"] = exch.upper()
            # Keep first (NASDAQ wins since it iterates first)
            out.setdefault(sym, row)
    return list(out.values())


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
SECTOR_UTILITIES     = "Utilities"

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
    # ---------- Technology ----------
    "EDP Services":                            (SECTOR_TECH, "IT_Services"),
    "Computer Software: Prepackaged Software": (SECTOR_TECH, "Software_SaaS"),
    "Computer Software: Programming, Data Processing": (SECTOR_TECH, "Software_SaaS"),
    "Diversified Commercial Services":         (SECTOR_TECH, "IT_Services"),
    "Computer Manufacturing":                  (SECTOR_TECH, "Consumer_Electronics"),
    "Computer Communications Equipment":       (SECTOR_TECH, "Cloud_Infrastructure"),
    "Computer peripheral equipment":           (SECTOR_TECH, "Consumer_Electronics"),
    "Semiconductors":                          (SECTOR_TECH, "Semiconductors"),
    "Electronic Components":                   (SECTOR_TECH, "Semiconductors"),
    # ---------- Energy ----------
    "Oil & Gas Production":                    (SECTOR_ENERGY, "Exploration_Production"),
    "Integrated oil Companies":                (SECTOR_ENERGY, "Exploration_Production"),
    "Oilfield Services/Equipment":             (SECTOR_ENERGY, "Oilfield_Services_Equipment"),
    "Oil Refining/Marketing":                  (SECTOR_ENERGY, "Midstream"),
    "Natural Gas Distribution":                (SECTOR_UTILITIES, "Gas_Utilities"),
    "Coal Mining":                             (SECTOR_ENERGY, "Coal_Uranium"),
    "Industrial Machinery/Components":         (SECTOR_INDUSTRIAL, "Machinery"),
    # ---------- Industrials ----------
    "Aerospace":                               (SECTOR_INDUSTRIAL, "Aerospace_Defense"),
    "Military/Government/Technical":           (SECTOR_INDUSTRIAL, "Aerospace_Defense"),
    "Engineering & Construction":              (SECTOR_INDUSTRIAL, "Construction_Engineering"),
    "Construction/Ag Equipment/Trucks":        (SECTOR_INDUSTRIAL, "Machinery"),
    "Marine Transportation":                   (SECTOR_INDUSTRIAL, "Transportation_Logistics"),
    "Trucking Freight/Courier Services":       (SECTOR_INDUSTRIAL, "Transportation_Logistics"),
    "Air Freight/Delivery Services":           (SECTOR_INDUSTRIAL, "Transportation_Logistics"),
    "Railroads":                               (SECTOR_INDUSTRIAL, "Transportation_Logistics"),
    "Pollution Control Equipment":             (SECTOR_INDUSTRIAL, "Industrial_Services"),
    "Electrical Products":                     (SECTOR_INDUSTRIAL, "Electrical_Equipment"),
    "Metal Fabrications":                      (SECTOR_INDUSTRIAL, "Machinery"),
    "Environmental Services":                  (SECTOR_INDUSTRIAL, "Industrial_Services"),
    # ---------- Utilities ----------
    "Water Supply":                            (SECTOR_UTILITIES, "Water_Utilities"),
    "Power Generation":                        (SECTOR_UTILITIES, "Electric_Utilities"),
    "Electric Utilities: Central":             (SECTOR_UTILITIES, "Electric_Utilities"),
    "Electric Utilities":                      (SECTOR_UTILITIES, "Electric_Utilities"),
}

# Keywords that nudge a ticker into Crypto-Adjacent sub-sector of Financials
_CRYPTO_KEYWORDS = re.compile(
    r"\b(bitcoin|crypto|blockchain|digital asset|web3|mining (?:rig|hardware))\b",
    re.IGNORECASE,
)


ND_SECTOR_TO_DASHBOARD: dict[str, str] = {
    "Health Care":            SECTOR_HCSVC,        # non-biotech HC default
    "Technology":             SECTOR_TECH,
    "Energy":                 SECTOR_ENERGY,
    "Industrials":            SECTOR_INDUSTRIAL,
    "Finance":                SECTOR_FINANCIALS,
    "Consumer Discretionary": SECTOR_CONSUMER_D,
    "Consumer Staples":       SECTOR_STAPLES,
    "Telecommunications":     SECTOR_COMMUNICATION,
    "Real Estate":            SECTOR_REALESTATE,
    "Basic Materials":        SECTOR_MATERIALS,
    "Miscellaneous":          SECTOR_INDUSTRIAL,   # most "misc" small-caps are industrial-ish
    "Communication Services": SECTOR_COMMUNICATION,
    "Communications":         SECTOR_COMMUNICATION,
    "Public Utilities":       SECTOR_UTILITIES,
    "Utilities":              SECTOR_UTILITIES,
    "Transportation":         SECTOR_INDUSTRIAL,
}


def keyword_classify(row: dict) -> tuple[str, str] | None:
    """Run only the deterministic keyword + NASDAQ-sector passes.

    Exposed separately so the background Gemini worker can compute
    each ticker's *current* rule-based assignment and ask Gemini to
    validate it. Excludes the Gemini cache pass.
    """
    industry = (row.get("industry") or "").strip()
    sector_str = (row.get("sector") or "").strip()
    name = row.get("name") or ""
    mapped = INDUSTRY_TO_SECTOR_SUB.get(industry)
    if mapped is not None:
        sector, sub = mapped
        if sector == SECTOR_FINANCIALS and _CRYPTO_KEYWORDS.search(name):
            sub = "Crypto_Adjacent"
        return sector, sub
    fallback_sector = ND_SECTOR_TO_DASHBOARD.get(sector_str) or SECTOR_INDUSTRIAL
    if fallback_sector == SECTOR_FINANCIALS and _CRYPTO_KEYWORDS.search(name):
        return SECTOR_FINANCIALS, "Crypto_Adjacent"
    return fallback_sector, "Other"


def classify_ticker_sector(row: dict) -> tuple[str, str] | None:
    """Return (sector_key, sub_sector_folder) for a NASDAQ screener row.

    Three-pass classification:
      0. Gemini cache hit — if google-classified disk cache has this
         ticker, use that (LLM-driven, semantic). No API call here.
      1. Industry-specific keyword mapping (INDUSTRY_TO_SECTOR_SUB) —
         precise sub-sector when we recognise the industry.
      2. NASDAQ sector fallback (ND_SECTOR_TO_DASHBOARD) — any ticker
         whose industry we don't recognise falls into 'Other' within
         its NASDAQ-declared sector.

    Returns None only if we have neither industry nor a recognisable
    sector to map to.
    """
    industry = (row.get("industry") or "").strip()
    sector_str = (row.get("sector") or "").strip()
    name = row.get("name") or ""
    sym = (row.get("symbol") or "").upper().strip()

    # Pass 0: Gemini cache (no API call — disk lookup)
    if sym:
        try:
            from gemini_classifier import cached_classification
            gem = cached_classification(sym)
            if gem is not None:
                return gem
        except Exception:
            pass

    # Passes 1 + 2: keyword / NASDAQ-sector fallback
    return keyword_classify(row)


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
