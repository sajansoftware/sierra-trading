"""Consumer Staples — food & beverage, household, personal care, tobacco, grocery."""

from __future__ import annotations

from dataclasses import dataclass


FOOD_BEVERAGE         = "Food_Beverage"
ALT_PROTEIN_FOOD_TECH = "Alt_Protein_Food_Tech"
HOUSEHOLD_PRODUCTS    = "Household_Products"
PERSONAL_CARE_BEAUTY  = "Personal_Care_Beauty"
TOBACCO_VAPE          = "Tobacco_Vape"
GROCERY_DISTRIBUTION  = "Grocery_Distribution"

OTHER = "Other"

FOLDERS = (
    FOOD_BEVERAGE, ALT_PROTEIN_FOOD_TECH, HOUSEHOLD_PRODUCTS,
    PERSONAL_CARE_BEAUTY, TOBACCO_VAPE, GROCERY_DISTRIBUTION, OTHER)


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
        from screener import discover_by_sector, SECTOR_STAPLES
        for sub, syms in discover_by_sector(SECTOR_STAPLES).items():
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
