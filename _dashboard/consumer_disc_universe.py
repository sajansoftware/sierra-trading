"""Consumer Discretionary — retail, apparel, autos, restaurants, gaming, leisure."""

from __future__ import annotations

from dataclasses import dataclass


RETAIL_SPECIALTY        = "Retail_Specialty"
APPAREL_FOOTWEAR        = "Apparel_Footwear"
AUTOMOTIVE_EVS          = "Automotive_EVs"
RESTAURANTS_HOSPITALITY = "Restaurants_Hospitality"
TRAVEL_LEISURE          = "Travel_Leisure"
GAMING_ENTERTAINMENT    = "Gaming_Entertainment"
HOME_GARDEN             = "Home_Garden"
E_COMMERCE              = "E_commerce"

FOLDERS = (
    RETAIL_SPECIALTY, APPAREL_FOOTWEAR, AUTOMOTIVE_EVS,
    RESTAURANTS_HOSPITALITY, TRAVEL_LEISURE, GAMING_ENTERTAINMENT,
    HOME_GARDEN, E_COMMERCE,
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
        from screener import discover_by_sector, SECTOR_CONSUMER_D
        for sub, syms in discover_by_sector(SECTOR_CONSUMER_D).items():
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
