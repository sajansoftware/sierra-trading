"""Industrials universe — curated small-cap candidates per sub-sector.

Same shape as bio / tech / energy universes:
    FOLDERS:      tuple of sub-sector folder names (under Industrials/)
    INFO:         dict ticker -> CompanyInfo(name, blurb, categories)
    UNIVERSE():   dict folder -> list of tickers
    all_tickers(): unique list of tickers

The live filter ($1-$20, free float < 20M, yfinance quotes) decides
what surfaces on any given day. Add or remove tickers freely.
"""

from __future__ import annotations

from dataclasses import dataclass


AEROSPACE_DEFENSE       = "Aerospace_Defense"
MACHINERY               = "Machinery"
TRANSPORTATION_LOGISTICS = "Transportation_Logistics"
CONSTRUCTION_ENGINEERING = "Construction_Engineering"
ELECTRICAL_EQUIPMENT    = "Electrical_Equipment"
INDUSTRIAL_SERVICES     = "Industrial_Services"

FOLDERS = (
    AEROSPACE_DEFENSE,
    MACHINERY,
    TRANSPORTATION_LOGISTICS,
    CONSTRUCTION_ENGINEERING,
    ELECTRICAL_EQUIPMENT,
    INDUSTRIAL_SERVICES,
)


@dataclass(frozen=True)
class CompanyInfo:
    name: str
    blurb: str
    categories: tuple[str, ...]


INFO: dict[str, CompanyInfo] = {
    # -------- Aerospace & Defense (incl. drones, satellites, defense tech) --------
    "KULR": CompanyInfo("KULR Technology Group",   "Thermal-management and battery-safety tech for EVs, aerospace and defense.",     (AEROSPACE_DEFENSE, ELECTRICAL_EQUIPMENT)),
    "KOPN": CompanyInfo("Kopin Corporation",       "Micro-displays for military helmet-mounted systems and AR/VR.",                  (AEROSPACE_DEFENSE,)),
    "BKSY": CompanyInfo("BlackSky Technology",     "High-revisit satellite imagery and geospatial intelligence.",                    (AEROSPACE_DEFENSE,)),
    "RDW":  CompanyInfo("Redwire Corporation",     "Space infrastructure components and on-orbit additive manufacturing.",           (AEROSPACE_DEFENSE,)),
    "LUNR": CompanyInfo("Intuitive Machines",      "Lunar landers, cislunar data services and orbital infrastructure.",              (AEROSPACE_DEFENSE,)),
    "ARQQ": CompanyInfo("Arqit Quantum",           "Quantum-safe symmetric-key encryption for defense and enterprise networks.",     (AEROSPACE_DEFENSE,)),
    "WRAP": CompanyInfo("Wrap Technologies",       "BolaWrap remote-restraint device and body-worn cameras for law enforcement.",    (AEROSPACE_DEFENSE,)),
    "BBAI": CompanyInfo("BigBear.ai Holdings",     "AI-driven decision intelligence for defense, intel and supply-chain customers.", (AEROSPACE_DEFENSE,)),
    "GSAT": CompanyInfo("Globalstar",              "Satellite mobile services; partner behind Apple iPhone emergency SOS.",          (AEROSPACE_DEFENSE,)),
    "EH":   CompanyInfo("EHang Holdings",          "Autonomous eVTOL passenger and cargo aircraft.",                                  (AEROSPACE_DEFENSE,)),
    "DPRO": CompanyInfo("Draganfly",               "Drones and remote-sensing platforms for public-safety, defense, and ag.",         (AEROSPACE_DEFENSE,)),
    "ONDS": CompanyInfo("Ondas Holdings",          "Private wireless and autonomous drone systems for rail, oil, and defense.",       (AEROSPACE_DEFENSE,)),
    "POWW": CompanyInfo("Outdoor Holding Company", "Operates GunBroker.com online auction marketplace for firearms and ammunition (post-AMMO ammunition spinoff).", (AEROSPACE_DEFENSE,)),

    # -------- Machinery (industrial machinery, 3D printing, automation) --------
    "AEHR": CompanyInfo("Aehr Test Systems",       "Wafer-level burn-in and reliability test systems for semiconductors.",           (MACHINERY,)),
    "DDD":  CompanyInfo("3D Systems",              "Industrial 3D printers and additive-manufacturing materials.",                    (MACHINERY,)),
    "XMTR": CompanyInfo("Xometry",                 "AI-driven on-demand manufacturing marketplace for CNC, 3D and sheet metal.",      (MACHINERY,)),
    "LIDR": CompanyInfo("AEye",                    "Adaptive solid-state LiDAR for ADAS, autonomous mobility, and industrial.",       (MACHINERY,)),
    "RR":   CompanyInfo("Richtech Robotics",       "Service robots for hospitality, healthcare and food-service automation.",         (MACHINERY,)),

    # -------- Transportation & Logistics (mostly shipping; some trucking) --------
    "SHIP": CompanyInfo("Seanergy Maritime",       "Capesize dry-bulk shipping fleet.",                                                (TRANSPORTATION_LOGISTICS,)),
    "GLBS": CompanyInfo("Globus Maritime",         "Dry-bulk shipping (Supramax and Kamsarmax).",                                      (TRANSPORTATION_LOGISTICS,)),
    "CTRM": CompanyInfo("Castor Maritime",         "Diversified dry-bulk and tanker shipping fleet.",                                  (TRANSPORTATION_LOGISTICS,)),
    "TOPS": CompanyInfo("TOP Ships",               "Tanker and dry-bulk shipping (Aframax/Suezmax/MR).",                               (TRANSPORTATION_LOGISTICS,)),
    "GASS": CompanyInfo("StealthGas",              "Small-scale LPG carriers serving petrochemical and refining customers.",           (TRANSPORTATION_LOGISTICS,)),
    "HSHP": CompanyInfo("Himalaya Shipping",       "Modern Newcastlemax dual-fuel dry-bulk carriers.",                                 (TRANSPORTATION_LOGISTICS,)),
    "DLNG": CompanyInfo("Dynagas LNG Partners",    "LNG carrier MLP with long-term charters.",                                         (TRANSPORTATION_LOGISTICS,)),
    "IMPP": CompanyInfo("Imperial Petroleum",      "Tanker and dry-bulk shipping subsidiary of StealthGas.",                           (TRANSPORTATION_LOGISTICS,)),
    "PSHG": CompanyInfo("Performance Shipping",    "Aframax crude tanker operator.",                                                   (TRANSPORTATION_LOGISTICS,)),
    "ULH":  CompanyInfo("Universal Logistics",     "Trucking, intermodal and value-added logistics services.",                         (TRANSPORTATION_LOGISTICS,)),

    # -------- Construction & Engineering --------
    "WLDN": CompanyInfo("Willdan Group",           "Engineering and consulting for utilities, energy efficiency and government.",     (CONSTRUCTION_ENGINEERING,)),
    "LMB":  CompanyInfo("Limbach Holdings",        "Mechanical, electrical and plumbing services for commercial buildings.",          (CONSTRUCTION_ENGINEERING,)),
    "NWPX": CompanyInfo("Northwest Pipe",          "Engineered steel water pipe and precast concrete products.",                       (CONSTRUCTION_ENGINEERING,)),
    "TPC":  CompanyInfo("Tutor Perini",            "Civil, building and specialty construction (transit, healthcare, gaming).",        (CONSTRUCTION_ENGINEERING,)),
    "STRL": CompanyInfo("Sterling Infrastructure", "Heavy civil, transportation, and e-infrastructure construction.",                  (CONSTRUCTION_ENGINEERING,)),

    # -------- Electrical Equipment (EV charging, fuel cells, power) --------
    "BLNK": CompanyInfo("Blink Charging",          "Owner-operator of EV charging stations and charging hardware.",                    (ELECTRICAL_EQUIPMENT,)),
    "EVGO": CompanyInfo("EVgo",                    "Public DC fast-charging network for electric vehicles.",                           (ELECTRICAL_EQUIPMENT,)),
    "POLA": CompanyInfo("Polar Power",             "DC power systems for telecom, marine and military backup applications.",           (ELECTRICAL_EQUIPMENT,)),
    "BLDP": CompanyInfo("Ballard Power Systems",   "PEM fuel cells for heavy-duty mobility and stationary power.",                     (ELECTRICAL_EQUIPMENT,)),
    "SLDP": CompanyInfo("Solid Power",             "Solid-state lithium-metal battery R&D for the EV market.",                         (ELECTRICAL_EQUIPMENT,)),

    # -------- Industrial Services (waste, recycling, environmental, pipeline svc) --------
    "SKYQ": CompanyInfo("Sky Quarry",              "Oil-sands tailings recycling and asphalt feedstock recovery.",                     (INDUSTRIAL_SERVICES,)),
    "ESOA": CompanyInfo("Energy Services of America","Pipeline construction and industrial service for energy and utility customers.",(INDUSTRIAL_SERVICES, CONSTRUCTION_ENGINEERING)),
    "LOOP": CompanyInfo("Loop Industries",         "Depolymerization technology that recycles low-value PET into virgin-grade resin.", (INDUSTRIAL_SERVICES,)),
}


def UNIVERSE() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {f: [] for f in FOLDERS}
    for ticker, info in INFO.items():
        for cat in info.categories:
            out[cat].append(ticker)
    try:
        from screener import discover_by_sector, SECTOR_INDUSTRIAL
        for sub, syms in discover_by_sector(SECTOR_INDUSTRIAL).items():
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
