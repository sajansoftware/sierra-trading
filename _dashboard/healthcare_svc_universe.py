"""Healthcare Services — hospitals, insurance, healthcare IT, distributors."""

from __future__ import annotations

from dataclasses import dataclass


HOSPITALS_HEALTH_SYSTEMS = "Hospitals_Health_Systems"
HEALTH_INSURANCE         = "Health_Insurance"
HEALTHCARE_IT_TELEHEALTH = "Healthcare_IT_Telehealth"
PHARMACY_DISTRIBUTORS    = "Pharmacy_Distributors"
MEDICAL_DEVICES          = "Medical_Devices"
DENTAL_VISION_HEARING    = "Dental_Vision_Hearing"

OTHER = "Other"

FOLDERS = (
    HOSPITALS_HEALTH_SYSTEMS, HEALTH_INSURANCE,
    HEALTHCARE_IT_TELEHEALTH, PHARMACY_DISTRIBUTORS,
    MEDICAL_DEVICES, DENTAL_VISION_HEARING, OTHER)


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
        from screener import discover_by_sector, SECTOR_HCSVC
        for sub, syms in discover_by_sector(SECTOR_HCSVC).items():
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
