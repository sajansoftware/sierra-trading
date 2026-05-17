"""Auto-classifier: ticker metadata -> biotech color categories.

Uses NASDAQ industry as a strong signal and yfinance business summary as
a refinement for cross-category placement (e.g. AI-bio also lands in Gold).
"""

from __future__ import annotations

import re

from universe import BLUE, GOLD, GREEN, GREY, RED, WHITE, YELLOW

# Industry -> primary category. Anything in Health Care defaults to RED.
INDUSTRY_PRIMARY: dict[str, str] = {
    "Agricultural Chemicals": GREEN,
    "Farming/Seeds/Milling": GREEN,
    "Major Chemicals": WHITE,
    "Specialty Chemicals": WHITE,
    "Marine Transportation": BLUE,
    "Environmental Services": GREY,
    "Water Supply": GREY,
    "Packaged Foods": YELLOW,
    "Beverages (Production/Distribution)": YELLOW,
    "Specialty Foods": YELLOW,
    "Food Distributors": YELLOW,
    "Meat/Poultry/Fish": YELLOW,
}

# Patterns that add secondary categories (a ticker can carry several)
SECONDARY_PATTERNS: list[tuple[str, re.Pattern]] = [
    (GOLD,   re.compile(r"\b(artificial intelligence|machine learning|deep learning|ai[- ]?driven|ai[- ]?powered|bioinformat|computational biology|in silico|generative (?:ai|model)|protein design)\b", re.I)),
    (GREEN,  re.compile(r"\b(crop|agricultur|seed|veterinar|animal health|companion animal|livestock|dairy cattle|equine|pet (?:health|medicine|pharmaceutical))\b", re.I)),
    (BLUE,   re.compile(r"\b(marine biotech|aquaculture|salmon|fish farming|algae|seaweed|kelp|ocean-derived)\b", re.I)),
    (GREY,   re.compile(r"\b(bioremediation|water purification|water treatment|wastewater|recycling|pollution control|hazardous waste|environmental remediation)\b", re.I)),
    (YELLOW, re.compile(r"\b(probiotic|nutraceutical|fermentation|plant[- ]based|alternative protein|kefir|yogurt|functional food|food fortification|biofortification|nutrition supplement)\b", re.I)),
    (WHITE,  re.compile(r"\b(industrial enzyme|biofuel|biodiesel|bioethanol|sustainable aviation fuel|bioplastic|biopolymer|bio[- ]based (?:chemical|material|polymer)|synthetic biology platform)\b", re.I)),
    (RED,    re.compile(r"\b(therapeutic|pharmaceutic|biotech|drug discovery|gene therapy|vaccine|clinical[- ]stage|antibody|oncolog|medical device|diagnostic)\b", re.I)),
]


def classify(
    sector: str,
    industry: str,
    name: str = "",
    summary: str = "",
) -> tuple[str, ...]:
    cats: list[str] = []

    # Primary: industry mapping
    if sector == "Health Care":
        cats.append(RED)
    elif industry in INDUSTRY_PRIMARY:
        cats.append(INDUSTRY_PRIMARY[industry])

    # Secondary: keyword refinements on name + summary
    text = f"{name} {summary}"
    for cat, pattern in SECONDARY_PATTERNS:
        if pattern.search(text) and cat not in cats:
            cats.append(cat)

    # Fallback: if nothing matched but the row passed screener filters,
    # default to RED so the ticker still surfaces.
    if not cats:
        cats.append(RED)

    return tuple(cats)
