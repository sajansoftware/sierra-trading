"""Financials — regional banks, investment banks, asset mgmt, insurance,
   fintech, BDCs, specialty finance, crypto-adjacent."""

from __future__ import annotations

from dataclasses import dataclass


REGIONAL_BANKS          = "Regional_Banks"
INVESTMENT_BANKS_BROKERS = "Investment_Banks_Brokers"
ASSET_MANAGEMENT        = "Asset_Management"
INSURANCE               = "Insurance"
FINTECH_PAYMENTS        = "Fintech_Payments"
BDCS                    = "BDCs"
SPECIALTY_FINANCE       = "Specialty_Finance"
CRYPTO_ADJACENT         = "Crypto_Adjacent"

FOLDERS = (
    REGIONAL_BANKS, INVESTMENT_BANKS_BROKERS, ASSET_MANAGEMENT,
    INSURANCE, FINTECH_PAYMENTS, BDCS, SPECIALTY_FINANCE,
    CRYPTO_ADJACENT,
)


@dataclass(frozen=True)
class CompanyInfo:
    name: str
    blurb: str
    categories: tuple[str, ...]


INFO: dict[str, CompanyInfo] = {}


def UNIVERSE() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {f: [] for f in FOLDERS}
    for ticker, info in INFO.items():
        for cat in info.categories:
            out[cat].append(ticker)
    try:
        from screener import discover_by_sector, SECTOR_FINANCIALS
        for sub, syms in discover_by_sector(SECTOR_FINANCIALS).items():
            if sub not in out:
                continue
            for s in syms:
                if s not in out[sub]:
                    out[sub].append(s)
    except Exception:
        pass
    return out


def all_tickers() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for syms in UNIVERSE().values():
        for s in syms:
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out
