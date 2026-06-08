"""NASDAQ universe screener.

Pulls the full NASDAQ-listed symbol table from NASDAQ's public screener
API, narrows it to biotech-relevant sectors/industries, and pre-filters
by NASDAQ's last-sale price so we don't waste yfinance calls on names
that obviously won't pass the live $1-$20 filter.

Output: list[dict] with keys
    symbol, name, sector, industry, last_price, market_cap
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

import requests
import streamlit as st

_log = logging.getLogger("screener.classify")

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
    "Paper":                                   (SECTOR_MATERIALS, "Construction_Materials"),
    "Paints/Coatings":                         (SECTOR_MATERIALS, "Specialty_Chemicals"),
    "Miscellaneous Chemical Manufacturing":    (SECTOR_MATERIALS, "Specialty_Chemicals"),
    "Agricultural Chemicals":                  (SECTOR_MATERIALS, "Specialty_Chemicals"),
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
    "Diversified Retail":                      (SECTOR_CONSUMER_D, "Retail_Specialty"),
    "General Merchandise Stores":              (SECTOR_CONSUMER_D, "Retail_Specialty"),
    "Shoe Manufacturing":                      (SECTOR_CONSUMER_D, "Apparel_Footwear"),
    "Textiles":                                (SECTOR_CONSUMER_D, "Apparel_Footwear"),
    "Consumer Electronics/Appliances":         (SECTOR_CONSUMER_D, "Home_Garden"),
    "Consumer Electronics/Video Chains":       (SECTOR_CONSUMER_D, "Home_Garden"),
    "Home Electronics & Appliances":           (SECTOR_CONSUMER_D, "Home_Garden"),
    "Recreational Products/Toys":              (SECTOR_CONSUMER_D, "Gaming_Entertainment"),
    "Movies/Entertainment":                    (SECTOR_CONSUMER_D, "Gaming_Entertainment"),
    "Services-Misc. Amusement & Recreation":   (SECTOR_CONSUMER_D, "Gaming_Entertainment"),
    "Sports & Recreation":                     (SECTOR_CONSUMER_D, "Gaming_Entertainment"),
    "Other Consumer Services":                 (SECTOR_CONSUMER_D, "Travel_Leisure"),
    "Rental/Leasing Companies":                (SECTOR_CONSUMER_D, "Other"),
    "Educational Services":                    (SECTOR_CONSUMER_D, "Other"),
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
    "Blank Checks":                            (SECTOR_FINANCIALS, "Specialty_Finance"),
    "Trusts Except Educational Religious and Charitable": (SECTOR_FINANCIALS, "Specialty_Finance"),
    "Financial Conglomerates":                 (SECTOR_FINANCIALS, "Specialty_Finance"),
    "Accident & Health Insurance":             (SECTOR_FINANCIALS, "Insurance"),
    "Surety Organization":                     (SECTOR_FINANCIALS, "Insurance"),
    "Business Services":                       (SECTOR_TECH, "IT_Services"),
    # ---------- Communication Services ----------
    "Telecommunications Equipment":            (SECTOR_COMMUNICATION, "Wireless_Wireline_Telecom"),
    "Radio And Television Broadcasting And Communications Equipment": (SECTOR_COMMUNICATION, "Media_Entertainment"),
    "Television Services":                     (SECTOR_COMMUNICATION, "Media_Entertainment"),
    "Cable & Other Pay Television Services":   (SECTOR_COMMUNICATION, "Streaming"),
    "Newspapers/Magazines":                    (SECTOR_COMMUNICATION, "Publishing_News"),
    "Books":                                   (SECTOR_COMMUNICATION, "Publishing_News"),
    "Advertising":                             (SECTOR_COMMUNICATION, "Advertising_MarTech"),
    "Broadcasting":                            (SECTOR_COMMUNICATION, "Media_Entertainment"),
    "Publishing":                              (SECTOR_COMMUNICATION, "Publishing_News"),
    "Diversified/Integrated Telecommunication": (SECTOR_COMMUNICATION, "Wireless_Wireline_Telecom"),
    "Wireless Communications":                 (SECTOR_COMMUNICATION, "Wireless_Wireline_Telecom"),
    "Multi-Sector Companies":                  (SECTOR_COMMUNICATION, "Media_Entertainment"),
    # ---------- Consumer Staples ----------
    "Packaged Foods":                          (SECTOR_STAPLES, "Food_Beverage"),
    "Beverages (Production/Distribution)":     (SECTOR_STAPLES, "Food_Beverage"),
    "Specialty Foods":                         (SECTOR_STAPLES, "Food_Beverage"),
    "Meat/Poultry/Fish":                       (SECTOR_STAPLES, "Food_Beverage"),
    "Food Distributors":                       (SECTOR_STAPLES, "Grocery_Distribution"),
    "Food Chains":                             (SECTOR_STAPLES, "Grocery_Distribution"),
    "Farming/Seeds/Milling":                   (SECTOR_STAPLES, "Food_Beverage"),
    "Consumer Non-Durables":                   (SECTOR_STAPLES, "Household_Products"),
    "Package Goods/Cosmetics":                 (SECTOR_STAPLES, "Personal_Care_Beauty"),
    "Tobacco":                                 (SECTOR_STAPLES, "Tobacco_Vape"),
    # ---------- Real Estate ----------
    "Real Estate Investment Trusts":           (SECTOR_REALESTATE, "Diversified_REITs"),
    "Real Estate":                             (SECTOR_REALESTATE, "Proptech"),
    "Building operators":                      (SECTOR_REALESTATE, "Diversified_REITs"),
    "Land Subdividers & Developers":           (SECTOR_REALESTATE, "Proptech"),
    "Developers":                              (SECTOR_REALESTATE, "Proptech"),
    # ---------- Healthcare Services (non-biotech) ----------
    "Managed Health Care":                     (SECTOR_HCSVC, "Health_Insurance"),
    "Hospital/Nursing Management":             (SECTOR_HCSVC, "Hospitals_Health_Systems"),
    "Medical/Nursing Services":                (SECTOR_HCSVC, "Hospitals_Health_Systems"),
    "Health Care Distributors":                (SECTOR_HCSVC, "Pharmacy_Distributors"),
    "Misc Health and Biotechnology Services":  (SECTOR_HCSVC, "Healthcare_IT_Telehealth"),
    # Biotech / pharma industries (also in HEALTHCARE_INDUSTRIES for biotech filter)
    "Biotechnology: Biological Products (No Diagnostic Substances)":       (SECTOR_HCSVC, "Other"),
    "Biotechnology: Commercial Physical & Biological Resarch":             (SECTOR_HCSVC, "Other"),
    "Biotechnology: Electromedical & Electrotherapeutic Apparatus":        (SECTOR_HCSVC, "Medical_Devices"),
    "Biotechnology: In Vitro & In Vivo Diagnostic Substances":             (SECTOR_HCSVC, "Other"),
    "Biotechnology: Pharmaceutical Preparations":                          (SECTOR_HCSVC, "Other"),
    "Biotechnology: Laboratory Analytical Instruments":                    (SECTOR_HCSVC, "Medical_Devices"),
    "Medical Specialities":                    (SECTOR_HCSVC, "Medical_Devices"),
    "Medical/Dental Instruments":              (SECTOR_HCSVC, "Medical_Devices"),
    "Medical Electronics":                     (SECTOR_HCSVC, "Medical_Devices"),
    "Ophthalmic Goods":                        (SECTOR_HCSVC, "Dental_Vision_Hearing"),
    "Other Pharmaceuticals":                   (SECTOR_HCSVC, "Pharmacy_Distributors"),
    "Pharmaceuticals and Biotechnology":       (SECTOR_HCSVC, "Other"),
    "Medicinal Chemicals and Botanical Products": (SECTOR_HCSVC, "Other"),
    "Precision Instruments":                   (SECTOR_HCSVC, "Medical_Devices"),
    # ---------- Technology ----------
    "EDP Services":                            (SECTOR_TECH, "IT_Services"),
    "Computer Software: Prepackaged Software": (SECTOR_TECH, "Software_SaaS"),
    "Computer Software: Programming, Data Processing": (SECTOR_TECH, "Software_SaaS"),
    "Diversified Commercial Services":         (SECTOR_TECH, "IT_Services"),
    "Computer Manufacturing":                  (SECTOR_TECH, "Consumer_Electronics"),
    "Computer Communications Equipment":       (SECTOR_TECH, "Cloud_Infrastructure"),
    "Computer peripheral equipment":           (SECTOR_TECH, "Consumer_Electronics"),
    "Internet Software/Services":              (SECTOR_TECH, "Software_SaaS"),
    "Computer Integrated Systems Design":      (SECTOR_TECH, "IT_Services"),
    "Information Technology Services":         (SECTOR_TECH, "IT_Services"),
    "Data Processing Services":                (SECTOR_TECH, "IT_Services"),
    "Retail: Computer Software & Peripheral Equipment": (SECTOR_TECH, "Consumer_Electronics"),
    "Electronic/Photographic Dealers":         (SECTOR_TECH, "Consumer_Electronics"),
    "Photographic Equipment & Supplies":       (SECTOR_TECH, "Consumer_Electronics"),
    "Semiconductors":                          (SECTOR_TECH, "Semiconductors"),
    "Electronic Components":                   (SECTOR_TECH, "Semiconductors"),
    "Industrial Measurement Instruments":      (SECTOR_TECH, "Semiconductors"),
    "Printed Circuit Boards":                  (SECTOR_TECH, "Semiconductors"),
    "Electronic Coils/Transformers":           (SECTOR_TECH, "Semiconductors"),
    # ---------- Energy ----------
    "Oil & Gas Production":                    (SECTOR_ENERGY, "Exploration_Production"),
    "Integrated oil Companies":                (SECTOR_ENERGY, "Exploration_Production"),
    "Oilfield Services/Equipment":             (SECTOR_ENERGY, "Oilfield_Services_Equipment"),
    "Oil Refining/Marketing":                  (SECTOR_ENERGY, "Midstream"),
    "Oil/Gas Transmission":                    (SECTOR_ENERGY, "Midstream"),
    "Natural Gas Pipeline":                    (SECTOR_ENERGY, "Midstream"),
    "Crude Petroleum & Natural Gas":           (SECTOR_ENERGY, "Exploration_Production"),
    "Drilling Oil & Gas Wells":                (SECTOR_ENERGY, "Oilfield_Services_Equipment"),
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
    "General Industrial Machinery & Equipment": (SECTOR_INDUSTRIAL, "Machinery"),
    "Special Industry Machinery":              (SECTOR_INDUSTRIAL, "Machinery"),
    "Environmental Services":                  (SECTOR_INDUSTRIAL, "Industrial_Services"),
    "Professional Services":                   (SECTOR_INDUSTRIAL, "Industrial_Services"),
    "Security & Protection Services":          (SECTOR_INDUSTRIAL, "Industrial_Services"),
    "Wholesale Distributors":                  (SECTOR_INDUSTRIAL, "Industrial_Services"),
    "Office/Plant Supplies/Maintenance":       (SECTOR_INDUSTRIAL, "Industrial_Services"),
    "Miscellaneous Manufacturing Industries":  (SECTOR_INDUSTRIAL, "Other"),
    "Ordnance And Accessories":                (SECTOR_INDUSTRIAL, "Aerospace_Defense"),
    "Package/Freight Delivery":                (SECTOR_INDUSTRIAL, "Transportation_Logistics"),
    "Homebuilding":                            (SECTOR_INDUSTRIAL, "Construction_Engineering"),
    "General Building Contractors":            (SECTOR_INDUSTRIAL, "Construction_Engineering"),
    "Heavy Construction":                      (SECTOR_INDUSTRIAL, "Construction_Engineering"),
    # ---------- Utilities ----------
    "Water Supply":                            (SECTOR_UTILITIES, "Water_Utilities"),
    "Power Generation":                        (SECTOR_UTILITIES, "Electric_Utilities"),
    "Electric Utilities: Central":             (SECTOR_UTILITIES, "Electric_Utilities"),
    "Electric Utilities":                      (SECTOR_UTILITIES, "Electric_Utilities"),
    "Cogeneration":                            (SECTOR_UTILITIES, "Electric_Utilities"),
    "Sewage & Water Treatment":                (SECTOR_UTILITIES, "Water_Utilities"),
    # --- Casing variants and NASDAQ typos (discovered via live audit) ---
    "Accident &Health Insurance":              (SECTOR_FINANCIALS, "Insurance"),
    "Auto & Home Supply Stores":               (SECTOR_CONSUMER_D, "Retail_Specialty"),
    "Building Products":                       (SECTOR_MATERIALS, "Construction_Materials"),
    "Computer Software: Programming Data Processing": (SECTOR_TECH, "Software_SaaS"),
    "Diversified Electronic Products":         (SECTOR_TECH, "Consumer_Electronics"),
    "Durable Goods":                           (SECTOR_CONSUMER_D, "Home_Garden"),
    "Electronics Distribution":                (SECTOR_TECH, "Consumer_Electronics"),
    "Fluid Controls":                          (SECTOR_INDUSTRIAL, "Machinery"),
    "Garments and Clothing":                   (SECTOR_CONSUMER_D, "Apparel_Footwear"),
    "General Bldg Contractors - Nonresidential Bldgs": (SECTOR_INDUSTRIAL, "Construction_Engineering"),
    "Integrated Freight & Logistics":          (SECTOR_INDUSTRIAL, "Transportation_Logistics"),
    "Misc Corporate Leasing Services":         (SECTOR_FINANCIALS, "Specialty_Finance"),
    "Miscellaneous":                           (SECTOR_INDUSTRIAL, "Other"),
    "Miscellaneous manufacturing industries":  (SECTOR_INDUSTRIAL, "Other"),
    "Office Equipment/Supplies/Services":      (SECTOR_INDUSTRIAL, "Industrial_Services"),
    "Oil and Gas Field Machinery":             (SECTOR_ENERGY, "Oilfield_Services_Equipment"),
    "Other Metals and Minerals":               (SECTOR_MATERIALS, "Base_Metals"),
    "Other Transportation":                    (SECTOR_INDUSTRIAL, "Transportation_Logistics"),
    "Plastic Products":                        (SECTOR_MATERIALS, "Specialty_Chemicals"),
    "Professional and commerical equipment":   (SECTOR_INDUSTRIAL, "Machinery"),
    "Recreational Games/Products/Toys":        (SECTOR_CONSUMER_D, "Gaming_Entertainment"),
    "Retail-Auto Dealers and Gas Stations":    (SECTOR_CONSUMER_D, "Retail_Specialty"),
    "Retail-Drug Stores and Proprietary Stores": (SECTOR_HCSVC, "Pharmacy_Distributors"),
    "Tools/Hardware":                          (SECTOR_INDUSTRIAL, "Machinery"),
    "Transportation Services":                 (SECTOR_INDUSTRIAL, "Transportation_Logistics"),
    "Water Sewer Pipeline Comm & Power Line Construction": (SECTOR_INDUSTRIAL, "Construction_Engineering"),
}

# ---------------------------------------------------------------------------
# Cross-sector keyword patterns
# ---------------------------------------------------------------------------
# These run after the initial industry-based classification and can override
# the sector/sub-sector when the company name reveals a better fit.

_CRYPTO_KEYWORDS = re.compile(
    r"\b(bitcoin|crypto|blockchain|digital asset|web3|mining (?:rig|hardware))\b",
    re.IGNORECASE,
)

_FINTECH_KEYWORDS = re.compile(
    r"\b(fintech|payment[s]?|neobank|digital bank|mobile bank"
    r"|lending platform|peer.to.peer|p2p lend|buy.now.pay.later|bnpl"
    r"|remittance|money transfer|digital wallet|e.wallet"
    r"|payment processing|merchant services"
    r"|insurtech|regtech|wealthtech|robo.advisor)\b",
    re.IGNORECASE,
)

_EV_KEYWORDS = re.compile(
    r"\b(electric vehicle|ev chargi|ev battery|lithium.ion"
    r"|solid.state battery|charging station|charging network"
    r"|ev infrastructure|battery technology)\b",
    re.IGNORECASE,
)

_CANNABIS_KEYWORDS = re.compile(
    r"\b(cannabis|marijuana|hemp|cbd|thc|dispensar"
    r"|cultivation facility|grow facility)\b",
    re.IGNORECASE,
)

_SPACE_KEYWORDS = re.compile(
    r"\b(satellite|orbital|launch vehicle|spacecraft"
    r"|rocket|lunar|space tourism"
    r"|low.earth orbit|leo constellation)\b",
    re.IGNORECASE,
)

_QUANTUM_KEYWORDS = re.compile(
    r"\b(quantum comput|quantum encrypt|quantum key"
    r"|quantum network|qubit|quantum sensor)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Diagnostic tracking for unmapped industries
# ---------------------------------------------------------------------------
_UNMAPPED_SEEN: set[str] = set()


def _unmapped_industries() -> set[str]:
    """Return NASDAQ industry strings seen at runtime with no
    INDUSTRY_TO_SECTOR_SUB entry. Useful for iterative improvement."""
    return set(_UNMAPPED_SEEN)


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


# Manual ticker-level overrides — wins ahead of EVERYTHING else
# (Gemini cache, keyword rules, NASDAQ-sector fallback). For cases
# where NASDAQ's industry string is just wrong (e.g. SOBR Safe is
# tagged "Newspapers/Magazines") and we want the fix to ship
# immediately without waiting for the AI classifier to run.
#
# Format: {TICKER: (sector_key, sub_sector_folder)}
# Sub-sector folders must match keys in app.py SECTORS dict.
MANUAL_OVERRIDES: dict[str, tuple[str, str]] = {
    # SOBR Safe -- alcohol-detection wearables, not a newspaper.
    "SOBR": (SECTOR_HCSVC, "Medical_Devices"),
    # AXIL Brands -- hearing enhancement / protection products,
    # not personal-care / beauty.
    "AXIL": (SECTOR_HCSVC, "Dental_Vision_Hearing"),
    # Bonk Inc -- digital-infrastructure / crypto company,
    # not personal-care / beauty.
    "BNKK": (SECTOR_FINANCIALS, "Crypto_Adjacent"),
}


def _apply_keyword_overrides(
    sector: str, sub: str, name: str,
) -> tuple[str, str]:
    """Post-classification keyword overrides for cross-sector ambiguities.

    Applied after INDUSTRY_TO_SECTOR_SUB or ND_SECTOR_TO_DASHBOARD has
    produced a (sector, sub) pair. Keyword rules can reclassify the
    sub-sector (or even the sector) based on the company name.
    Rules are ordered by priority -- first match wins.
    """
    # Crypto: any sector -> Financials/Crypto_Adjacent
    if _CRYPTO_KEYWORDS.search(name):
        return SECTOR_FINANCIALS, "Crypto_Adjacent"

    # Fintech: Tech or Industrial companies that are actually fintech
    if sector in (SECTOR_TECH, SECTOR_INDUSTRIAL) and _FINTECH_KEYWORDS.search(name):
        return SECTOR_FINANCIALS, "Fintech_Payments"

    # EV: tech or industrial companies doing EV infrastructure
    if sector in (SECTOR_TECH, SECTOR_INDUSTRIAL) and _EV_KEYWORDS.search(name):
        return SECTOR_CONSUMER_D, "Automotive_EVs"

    # Cannabis: can appear under various NASDAQ sectors
    if _CANNABIS_KEYWORDS.search(name):
        return SECTOR_HCSVC, "Other"

    # Space/satellite: often tagged as tech or industrial
    if sector in (SECTOR_TECH, SECTOR_INDUSTRIAL, SECTOR_COMMUNICATION):
        if _SPACE_KEYWORDS.search(name):
            return SECTOR_COMMUNICATION, "Satellite_Towers"

    # Quantum computing
    if _QUANTUM_KEYWORDS.search(name):
        return SECTOR_TECH, "AI_Machine_Learning"

    return sector, sub


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
        return _apply_keyword_overrides(sector, sub, name)
    # Track unmapped industries for diagnostic purposes
    if industry:
        _UNMAPPED_SEEN.add(industry)
        _log.debug("Unmapped NASDAQ industry: %r (sector=%r)", industry, sector_str)
    fallback_sector = ND_SECTOR_TO_DASHBOARD.get(sector_str) or SECTOR_INDUSTRIAL
    return _apply_keyword_overrides(fallback_sector, "Other", name)


def classify_ticker_sector(row: dict) -> tuple[str, str] | None:
    """Return (sector_key, sub_sector_folder) for a NASDAQ screener row.

    Four-pass classification, first hit wins:
      0a. Manual override (MANUAL_OVERRIDES) — for known-bad NASDAQ
          data that we want to fix immediately, ahead of any other
          source. Persists across deploys (in source).
      0b. Gemini cache hit — LLM-driven semantic pick from disk cache.
      1.  Industry-specific keyword mapping (INDUSTRY_TO_SECTOR_SUB).
      2.  NASDAQ sector fallback (ND_SECTOR_TO_DASHBOARD).

    Returns None only if we have neither industry nor a recognisable
    sector to map to.
    """
    industry = (row.get("industry") or "").strip()
    sector_str = (row.get("sector") or "").strip()
    name = row.get("name") or ""
    sym = (row.get("symbol") or "").upper().strip()

    # Pass 0a: hand-written override
    if sym and sym in MANUAL_OVERRIDES:
        return MANUAL_OVERRIDES[sym]

    # Pass 0b: Gemini cache (no API call — disk lookup)
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
