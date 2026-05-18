"""Real Estate — REITs and proptech."""

from __future__ import annotations

from dataclasses import dataclass


DIVERSIFIED_REITS         = "Diversified_REITs"
RESIDENTIAL_REITS         = "Residential_REITs"
COMMERCIAL_OFFICE_REITS   = "Commercial_Office_REITs"
INDUSTRIAL_LOGISTICS_REITS = "Industrial_Logistics_REITs"
DATA_CENTER_REITS         = "Data_Center_REITs"
SPECIALTY_REITS           = "Specialty_REITs"
MORTGAGE_REITS            = "Mortgage_REITs"
PROPTECH                  = "Proptech"

FOLDERS = (
    DIVERSIFIED_REITS, RESIDENTIAL_REITS, COMMERCIAL_OFFICE_REITS,
    INDUSTRIAL_LOGISTICS_REITS, DATA_CENTER_REITS, SPECIALTY_REITS,
    MORTGAGE_REITS, PROPTECH,
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
        from screener import discover_by_sector, SECTOR_REALESTATE
        for sub, syms in discover_by_sector(SECTOR_REALESTATE).items():
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
