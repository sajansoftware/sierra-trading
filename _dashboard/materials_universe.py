"""Materials sector — mining, chemicals, steel, construction materials.

Same shape as other sector universes. Curated INFO is the override
layer (you fill in over time); the NASDAQ screener auto-populates the
rest of the $1-$20 universe by industry classification.
"""

from __future__ import annotations

from dataclasses import dataclass


PRECIOUS_METALS        = "Precious_Metals"
BATTERY_CRITICAL_METALS = "Battery_Critical_Metals"
RARE_EARTH_STRATEGIC   = "Rare_Earth_Strategic"
URANIUM                = "Uranium"
BASE_METALS            = "Base_Metals"
STEEL_IRON             = "Steel_Iron"
SPECIALTY_CHEMICALS    = "Specialty_Chemicals"
CONSTRUCTION_MATERIALS = "Construction_Materials"

OTHER = "Other"

FOLDERS = (
    PRECIOUS_METALS, BATTERY_CRITICAL_METALS, RARE_EARTH_STRATEGIC,
    URANIUM, BASE_METALS, STEEL_IRON, SPECIALTY_CHEMICALS,
    CONSTRUCTION_MATERIALS, OTHER)


@dataclass(frozen=True)
class CompanyInfo:
    name: str
    blurb: str
    categories: tuple[str, ...]


# Curated overrides (extend over time)
INFO: dict[str, CompanyInfo] = {}


def UNIVERSE() -> dict[str, list[str]]:
    """Curated INFO merged with screener-discovered tickers from NASDAQ."""
    out: dict[str, list[str]] = {f: [] for f in FOLDERS}
    for ticker, info in INFO.items():
        for cat in info.categories:
            out[cat].append(ticker)
    try:
        from screener import discover_by_sector, SECTOR_MATERIALS
        discovered = discover_by_sector(SECTOR_MATERIALS)
        for sub, syms in discovered.items():
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
