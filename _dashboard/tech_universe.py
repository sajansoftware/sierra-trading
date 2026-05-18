"""Curated technology universe with metadata — 9 sub-sectors.

Tickers that yfinance can no longer resolve are silently dropped
by the live filter (price $1–$20, free float < 20M).
"""

from __future__ import annotations

from dataclasses import dataclass

SEMI     = "Semiconductors"
SW_SAAS  = "Software_SaaS"
CLOUD    = "Cloud_Infrastructure"
AI_ML    = "AI_Machine_Learning"
CYBER    = "Cybersecurity"
CONS_ELC = "Consumer_Electronics"
FINTECH  = "Fintech"
TELECOM  = "Telecom"
IT_SVC   = "IT_Services"

OTHER = "Other"

FOLDERS = (SEMI, SW_SAAS, CLOUD, AI_ML, CYBER, CONS_ELC, FINTECH, TELECOM, IT_SVC, OTHER)


@dataclass(frozen=True)
class CompanyInfo:
    name: str
    blurb: str
    categories: tuple[str, ...]


INFO: dict[str, CompanyInfo] = {
    # ---------- Semiconductors ----------
    "AEHR": CompanyInfo("Aehr Test Systems",       "Semiconductor burn-in and test equipment for EV and AI chips.",           (SEMI,)),
    "AAOI": CompanyInfo("Applied Optoelectronics",  "Fiber optic transceiver and laser components for data centers.",          (SEMI,)),
    "CEVA": CompanyInfo("CEVA",                     "Licensor of DSP IP cores for AI edge processing.",                        (SEMI,)),
    "PXLW": CompanyInfo("Pixelworks",               "Visual processing semiconductors for mobile and projection.",            (SEMI,)),
    "MXL":  CompanyInfo("MaxLinear",                "Fabless RF, analog and mixed-signal semiconductor ICs.",                  (SEMI,)),
    "AOSL": CompanyInfo("Alpha & Omega Semi",       "Power semiconductor MOSFETs and ICs.",                                    (SEMI,)),
    "GCTS": CompanyInfo("GCT Semiconductor",        "4G/5G semiconductor solutions for mobile devices.",                       (SEMI,)),
    "POET": CompanyInfo("POET Technologies",        "Photonic integrated circuit platforms for AI data centers.",              (SEMI,)),

    # ---------- Software / SaaS ----------
    "SMWB": CompanyInfo("Similarweb",               "AI-driven digital analytics and website traffic intelligence platform.",   (SW_SAAS,)),
    "VTEX": CompanyInfo("VTEX",                     "Enterprise SaaS digital commerce platform for retailers.",                (SW_SAAS,)),
    "DOMO": CompanyInfo("Domo Technologies",        "Cloud business intelligence and real-time data visualization platform.",  (SW_SAAS,)),
    "APPN": CompanyInfo("Appian",                   "Low-code workflow automation and application development platform.",      (SW_SAAS,)),
    "YEXT": CompanyInfo("Yext",                     "AI digital knowledge management and search platform.",                    (SW_SAAS,)),
    "BAND": CompanyInfo("Bandwidth",                "Cloud-based enterprise communications API platform.",                     (SW_SAAS,)),

    # ---------- Cloud & Infrastructure ----------
    "RKLB": CompanyInfo("Rocket Lab USA",           "Launch services and spacecraft systems for satellite deployment.",        (CLOUD,)),
    "ASTS": CompanyInfo("AST SpaceMobile",          "Satellite direct-to-cell broadband network infrastructure.",             (CLOUD,)),
    "VNET": CompanyInfo("VNET Group",               "Carrier-neutral data center and cloud infrastructure in China.",         (CLOUD,)),
    "CRNT": CompanyInfo("Ceragon Networks",         "Wireless backhaul and fronthaul solutions for 5G networks.",             (TELECOM,)),
    "INFN": CompanyInfo("Infinera",                 "Optical transport networking equipment for telecom and cloud.",          (CLOUD,)),
    "ORBC": CompanyInfo("ORBCOMM",                  "IoT and M2M satellite connectivity and tracking solutions.",             (CLOUD,)),

    # ---------- AI & Machine Learning ----------
    "BBAI": CompanyInfo("BigBear.ai",               "AI-powered analytics for defense, supply chain and logistics.",          (AI_ML,)),
    "RCAT": CompanyInfo("Red Cat Holdings",         "AI-powered drone systems for defense and security applications.",        (AI_ML,)),
    "SERV": CompanyInfo("Serve Robotics",           "Autonomous sidewalk delivery robots for last-mile logistics.",           (AI_ML,)),
    "ONDS": CompanyInfo("Ondas Holdings",           "AI-driven autonomous drone and counter-drone defense systems.",          (AI_ML,)),
    "ARQQ": CompanyInfo("Arqit Quantum",            "Quantum-safe encryption key generation as a service.",                  (CYBER,)),
    "RZLV": CompanyInfo("Rezolve AI",               "AI-powered mobile commerce and engagement platform.",                    (AI_ML,)),

    # ---------- Cybersecurity ----------
    "RDWR": CompanyInfo("Radware",                  "Cloud application security, DDoS protection and bot management.",        (CYBER,)),
    "RPD":  CompanyInfo("Rapid7",                   "Security analytics, vulnerability management and SIEM solutions.",       (CYBER,)),
    "MIME": CompanyInfo("Mimecast",                 "Cloud email security, archiving and data protection platform.",          (CYBER,)),
    "SAIL": CompanyInfo("SailPoint Technologies",    "AI-powered enterprise identity security and governance platform.",      (CYBER,)),

    # ---------- Consumer Electronics ----------
    "KN":   CompanyInfo("Knowles",                  "Acoustic microphones, speakers and audio components for devices.",       (CONS_ELC,)),
    "VUZI": CompanyInfo("Vuzix",                    "Augmented reality smart glasses and optical waveguide technology.",      (CONS_ELC,)),
    "KOPN": CompanyInfo("Kopin",                    "Wearable displays and optics for defense, industrial and consumer.",     (CONS_ELC,)),
    "CREX": CompanyInfo("Creative Realities",       "Digital signage and immersive in-store experience technology.",          (CONS_ELC,)),

    # ---------- Fintech ----------
    "LC":   CompanyInfo("LendingClub",              "Online lending marketplace connecting borrowers with investors.",         (FINTECH,)),
    "GDOT": CompanyInfo("Green Dot",                "Prepaid debit cards, digital banking and payment processing.",           (FINTECH,)),
    "LMND": CompanyInfo("Lemonade",                 "AI-powered renters, homeowners and pet insurance platform.",             (FINTECH,)),
    "NRDS": CompanyInfo("NerdWallet",               "Personal finance comparison, advice and credit monitoring platform.",    (FINTECH,)),

    # ---------- Telecom ----------
    "GSAT": CompanyInfo("Globalstar",               "Satellite voice, data and IoT connectivity services.",                  (TELECOM,)),
    "CALX": CompanyInfo("Calix",                    "Broadband access platforms and cloud software for telecom operators.",   (TELECOM,)),
    "RBBN": CompanyInfo("Ribbon Communications",    "Session border controllers and telecom network security solutions.",     (TELECOM,)),
    "HLIT": CompanyInfo("Harmonic",                 "Video delivery and cable broadband infrastructure for telecom.",         (TELECOM,)),
    "CMTL": CompanyInfo("Comtech Telecommunications","Emergency response and satellite ground station communication tech.",   (TELECOM,)),

    # ---------- IT Services ----------
    "IBEX": CompanyInfo("IBEX",                     "BPO and digital customer engagement services for global brands.",        (IT_SVC,)),
    "PRGS": CompanyInfo("Progress Software",        "Application development, data connectivity and infrastructure tools.",  (IT_SVC,)),
    "CTLP": CompanyInfo("Cantaloupe",               "IoT and payment solutions for unattended retail and vending.",          (IT_SVC,)),
    "CSGS": CompanyInfo("CSG Systems",              "Customer care and revenue management software for telecom operators.",   (IT_SVC,)),
}


def UNIVERSE() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {f: [] for f in FOLDERS}
    for ticker, info in INFO.items():
        for cat in info.categories:
            out[cat].append(ticker)
    try:
        from screener import discover_by_sector, SECTOR_TECH
        for sub, syms in discover_by_sector(SECTOR_TECH).items():
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
