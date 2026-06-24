"""SEC EDGAR 8-K filings lookup for historical catalyst enrichment.

yfinance's news feed only carries ~30 days of items. For a true 5-year
catalyst archive we read 8-K material-event filings from SEC EDGAR
(free, no API key, 5y+ history). Each 8-K has an Item code that maps
cleanly to a catalyst type (Item 2.02 = Earnings, Item 8.01 = Other
Events / FDA & clinical news, etc.) and a primaryDocument URL we can
link to as the source.

EDGAR fair-access policy requires a contactable User-Agent string;
make sure SEC_USER_AGENT below identifies you.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import requests
import streamlit as st

_GENERIC_DESC = re.compile(
    r"^(current report|form\s*8-?k|8-?k\s*(sec\s*)?filing|sec\s*filing).*",
    re.IGNORECASE,
)

# Per https://www.sec.gov/os/accessing-edgar-data — identify yourself.
SEC_USER_AGENT = "Momentus Dashboard contact@momentus.app"

SEC_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept": "application/json"}

# 8-K Item -> (catalyst type, friendly description). Item numbers per
# https://www.sec.gov/files/form8-k.pdf
ITEM_MAP: dict[str, tuple[str, str]] = {
    "1.01": ("Partnership",   "Entry into a Material Definitive Agreement"),
    "1.02": ("Partnership",   "Termination of a Material Definitive Agreement"),
    "1.03": ("Bankruptcy",    "Bankruptcy or Receivership"),
    "2.01": ("M&A",           "Completion of Acquisition or Disposition of Assets"),
    "2.02": ("Earnings",      "Results of Operations and Financial Condition"),
    "2.03": ("Offering",      "Creation of a Material Direct Financial Obligation"),
    "2.04": ("Offering",      "Triggering Events that Accelerate a Direct Financial Obligation"),
    "2.05": ("Restructuring", "Costs Associated with Exit or Disposal Activities"),
    "2.06": ("Restructuring", "Material Impairments"),
    "3.01": ("Listing",       "Notice of Delisting / Listing Standards"),
    "3.02": ("Offering",      "Unregistered Sales of Equity Securities"),
    "3.03": ("Listing",       "Material Modification to Rights of Security Holders"),
    "4.01": ("Auditor",       "Changes in Registrant's Certifying Accountant"),
    "4.02": ("Auditor",       "Non-Reliance on Previously Issued Financial Statements"),
    "5.01": ("M&A",           "Changes in Control of Registrant"),
    "5.02": ("Insider",       "Departure / Election of Directors or Officers"),
    "5.03": ("Insider",       "Amendments to Articles of Incorporation or Bylaws"),
    "5.07": ("Insider",       "Submission of Matters to a Vote of Security Holders"),
    "7.01": ("No news",       "Regulation FD Disclosure"),
    "8.01": ("No news",       "Other Events"),
    "9.01": ("No news",       "Financial Statements and Exhibits"),
}


def _user_agent() -> dict:
    return SEC_HEADERS


@st.cache_data(ttl=86_400, show_spinner=False)  # 24h
def fetch_ticker_cik_map() -> dict[str, str]:
    """Map ticker -> zero-padded 10-digit CIK."""
    try:
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=_user_agent(), timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return {}
    out: dict[str, str] = {}
    for row in data.values():
        try:
            ticker = (row.get("ticker") or "").upper()
            cik = int(row.get("cik_str") or 0)
            if ticker and cik:
                out[ticker] = f"{cik:010d}"
        except (TypeError, ValueError):
            continue
    return out


@st.cache_data(ttl=21_600, show_spinner=False)  # 6h
def fetch_8k_filings(ticker: str, years_back: int = 5) -> list[dict]:
    """Return 8-K filings for the ticker filed within the last `years_back`.

    Each row: {date, items, type, description, link}
        items: comma-separated 8-K item codes (e.g. "2.02,9.01")
        type:  best-effort catalyst type from the first recognised item
        description: friendly description from ITEM_MAP for the first item
        link: URL to the primary document (the 8-K filing itself)
    """
    cik_map = fetch_ticker_cik_map()
    cik = cik_map.get(ticker.upper())
    if not cik:
        return []
    try:
        r = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=_user_agent(), timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    recent = (data.get("filings") or {}).get("recent") or {}
    forms          = recent.get("form", []) or []
    dates          = recent.get("filingDate", []) or []
    items          = recent.get("items", []) or []
    accessions     = recent.get("accessionNumber", []) or []
    primary_docs   = recent.get("primaryDocument", []) or []
    primary_descs  = recent.get("primaryDocDescription", []) or []

    cutoff = date.today() - timedelta(days=years_back * 365)
    cik_int = int(cik)
    out: list[dict] = []
    for i, form in enumerate(forms):
        if form not in ("8-K", "8-K/A"):
            continue
        try:
            fd = datetime.strptime(dates[i], "%Y-%m-%d").date()
        except (ValueError, IndexError):
            continue
        if fd < cutoff:
            continue
        item_str = (items[i] if i < len(items) else "") or ""
        item_codes = [c.strip() for c in item_str.split(",") if c.strip()]
        # Best catalyst type: first item whose code we recognise
        ctype = "No news"
        desc = "Material event filing (8-K)"
        for code in item_codes:
            if code in ITEM_MAP:
                ctype, desc = ITEM_MAP[code]
                break
        accession = (accessions[i] if i < len(accessions) else "") or ""
        primary_doc = (primary_docs[i] if i < len(primary_docs) else "") or ""
        link = ""
        if accession and primary_doc:
            acc_clean = accession.replace("-", "")
            link = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{primary_doc}"
        # The SEC's primaryDocDescription is generic boilerplate for nearly
        # all small-cap filers ("CURRENT REPORT", "FORM 8-K SEC FILING").
        # The item-derived description is consistently more informative.
        out.append({
            "date":        fd,
            "items":       item_str,
            "type":        ctype,
            "description": desc,
            "link":        link,
        })
    return out


def filings_by_date(filings: list[dict]) -> dict[date, list[dict]]:
    out: dict[date, list[dict]] = {}
    for f in filings:
        out.setdefault(f["date"], []).append(f)
    return out
