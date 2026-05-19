"""Utilities — electric, gas, water, multi-utility, renewable IPPs."""

from __future__ import annotations

from dataclasses import dataclass


ELECTRIC_UTILITIES = "Electric_Utilities"
GAS_UTILITIES      = "Gas_Utilities"
WATER_UTILITIES    = "Water_Utilities"
MULTI_UTILITIES    = "Multi_Utilities"
RENEWABLE_IPPS     = "Renewable_IPPs"
OTHER              = "Other"

FOLDERS = (
    ELECTRIC_UTILITIES, GAS_UTILITIES, WATER_UTILITIES,
    MULTI_UTILITIES, RENEWABLE_IPPS, OTHER,
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
        from screener import discover_by_sector, SECTOR_UTILITIES
        for sub, syms in discover_by_sector(SECTOR_UTILITIES).items():
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
