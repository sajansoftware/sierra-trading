"""Curated energy universe with metadata — 5 sub-sectors."""

from __future__ import annotations

from dataclasses import dataclass

EP   = "Exploration_Production"
OFS  = "Oilfield_Services_Equipment"
MID  = "Midstream"
REN  = "Renewable_Energy"
COAL = "Coal_Uranium"

FOLDERS = (EP, OFS, MID, REN, COAL)


@dataclass(frozen=True)
class CompanyInfo:
    name: str
    blurb: str
    categories: tuple[str, ...]


INFO: dict[str, CompanyInfo] = {
    # ---------- Exploration & Production ----------
    "BRY":  CompanyInfo("Berry Corp",              "California-focused oil producer; conventional and thermal recovery.",           (EP,)),
    "REI":  CompanyInfo("Ring Energy",             "Permian Basin oil & gas producer; horizontal drilling in the Delaware.",        (EP,)),
    "NINE": CompanyInfo("Nine Energy Service",     "Well completion and wireline services for onshore oil & gas wells.",             (EP,)),
    "WTI":  CompanyInfo("W&T Offshore",            "Gulf of Mexico shelf and deepwater conventional oil & gas producer.",            (EP,)),
    "HUSA": CompanyInfo("Houston American Energy",  "International E&P with assets in Colombia, Permian and Gulf Coast.",            (EP,)),
    "TUSK": CompanyInfo("Mammoth Energy Services", "Oilfield services and E&P; integrated well-site services.",                     (EP,)),
    "SD":   CompanyInfo("SandRidge Energy",        "Mid-continent oil & gas producer; Mississippian Lime and STACK play.",           (EP,)),
    "PBT":  CompanyInfo("Permian Basin Royalty Trust","Royalty trust holding overriding royalty interests in Texas oil properties.",  (EP,)),

    # ---------- Oilfield Services & Equipment ----------
    "KLXE": CompanyInfo("KLX Energy Services",    "Completion, drilling and production services across major US basins.",           (OFS,)),
    "PFIE": CompanyInfo("Profire Energy",          "Burner-management and safety systems for oilfield separators and heaters.",      (OFS,)),
    "OIS":  CompanyInfo("Oil States International","Offshore and onshore oilfield equipment; accommodation units and well services.",(OFS,)),
    "NCSM": CompanyInfo("NCS Multistage",          "Multi-stage fracturing systems and downhole completion tools.",                  (OFS,)),
    "FET":  CompanyInfo("Forum Energy Technologies","Manufactured oilfield consumables, capital equipment and drilling products.",    (OFS,)),
    "BOOM": CompanyInfo("DMC Global",              "Composite frac plugs and energy-transition fasteners for oilfield and industrial.", (OFS,)),
    "PUMP": CompanyInfo("ProPetro Holding",        "Permian-focused hydraulic fracturing and wireline services.",                    (OFS,)),

    # ---------- Midstream ----------
    "NGL":  CompanyInfo("NGL Energy Partners",     "Crude oil, water and liquids transportation, storage and processing.",            (MID,)),
    "BPT":  CompanyInfo("BP Prudhoe Bay Royalty Trust","Royalty trust entitled to a share of Prudhoe Bay production revenue.",       (MID,)),
    "SBR":  CompanyInfo("Sabine Royalty Trust",    "Trust holding royalty and mineral interests in oil and gas properties.",          (MID,)),
    "GEL":  CompanyInfo("Genesis Energy",          "Pipeline and refinery services; soda ash mining and transportation.",            (MID,)),
    "DHT":  CompanyInfo("DHT Holdings",            "Crude oil tanker shipping; very large crude carrier (VLCC) fleet.",              (MID,)),
    "TK":   CompanyInfo("Teekay Corp",             "Marine energy transportation; crude, gas and product tanker services.",          (MID,)),
    "CAPL": CompanyInfo("CrossAmerica Partners",   "Wholesale motor fuels distribution and retail site leasing across the US.",      (MID,)),

    # ---------- Renewable Energy ----------
    "OPTT": CompanyInfo("Ocean Power Technologies","Wave-energy conversion systems and autonomous offshore power buoys.",            (REN,)),
    "EOSE": CompanyInfo("Eos Energy Enterprises",  "Zinc-based long-duration battery storage systems for grid-scale applications.",  (REN,)),
    "ADN":  CompanyInfo("Advent Technologies",     "High-temperature hydrogen fuel cell and electrolyzer systems.",                   (REN,)),
    "GWH":  CompanyInfo("ESS Tech",                "Iron-flow battery energy storage systems for utility and commercial use.",        (REN,)),
    "FCEL": CompanyInfo("FuelCell Energy",         "Carbonate and solid-oxide fuel cell platforms for distributed generation.",       (REN,)),
    "TURB": CompanyInfo("Turbo Energy",            "AI-optimized solar photovoltaic energy storage solutions for residential.",       (REN,)),
    "AMPX": CompanyInfo("Amprius Technologies",    "High-energy-density silicon-anode lithium-ion batteries for aviation and EV.",   (REN,)),

    # ---------- Coal & Uranium ----------
    "UEC":  CompanyInfo("Uranium Energy Corp",     "In-situ recovery uranium mining and development in the US and Canada.",           (COAL,)),
    "DNN":  CompanyInfo("Denison Mines",           "Uranium development in the Athabasca Basin; ISR and conventional projects.",       (COAL,)),
    "URG":  CompanyInfo("Ur-Energy",               "US-based uranium mining; Lost Creek ISR facility in Wyoming.",                    (COAL,)),
    "ARCH": CompanyInfo("Arch Resources",          "Metallurgical and thermal coal producer supplying global steel and power.",       (COAL,)),
    "CEIX": CompanyInfo("CONSOL Energy",           "Pennsylvania thermal coal mining; PA Mining Complex and export terminal.",        (COAL,)),
    "BTU":  CompanyInfo("Peabody Energy",           "Largest US coal producer; met and thermal operations across US and Australia.",   (COAL,)),
}


def UNIVERSE() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {f: [] for f in FOLDERS}
    for ticker, info in INFO.items():
        for cat in info.categories:
            out[cat].append(ticker)
    try:
        from screener import discover_by_sector, SECTOR_ENERGY
        for sub, syms in discover_by_sector(SECTOR_ENERGY).items():
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
