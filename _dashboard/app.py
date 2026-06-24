"""Sierra Trading dashboard — navy theme, native Streamlit interactions.

Architecture:
- Sidebar: category selectbox + sub-sector radio + refresh.
- Sector pages: header / description / candidate table.
- Ticker drill-in: native st.dialog (built-in close), opened from a
  selectbox above each table.
- Trading Journal: stats + add-trade form + native st.dataframe with
  row selection -> delete button.
"""

from __future__ import annotations

import base64
import math
import struct
import threading as _threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

import pandas as pd
import streamlit as st

from data import (
    MAX_FLOAT,
    MAX_PRICE,
    MIN_PRICE,
    Quote,
    fetch_penny_candidates,
    fetch_premarket_catalysts,
    fetch_top_movers,
    fetch_top_movers_dual,
    filtered_by_category,
    short_blurb,
    tv_num,
)
from changelog import record_snapshot, recent_events
import universe as bio_universe
import tech_universe
import energy_universe
import industrials_universe
import materials_universe
import consumer_disc_universe
import financials_universe
import comm_services_universe
import consumer_staples_universe
import real_estate_universe
import healthcare_svc_universe
import healthcare_universe
import utilities_universe
import trading_journal
from ipo_calendar import fetch_ipo_calendar, IPO
import stan as stan_module

ROOT = Path(__file__).parent

# ---------- Navy theme palette ----------
NAVY        = "#0a1929"   # background
NAVY_CARD   = "#102841"   # cards / sidebar / table header
NAVY_HOVER  = "#1a3a5c"   # row hover
BORDER      = "#1e3a5f"
WHITE       = "#ffffff"
WHITE_DIM   = "#e2e8f0"
WHITE_MUTE  = "#94a3b8"
ACCENT      = "#64b5f6"   # bright sky
GOOD        = "#22c55e"
WARN        = "#facc15"
DANGER      = "#ef4444"

# Sectors are ordered to match the GICS top-level classification:
#   Technology, Communication Services, Consumer Discretionary,
#   Consumer Staples, Health Care, Financials, Industrials, Energy,
#   Materials, Utilities, Real Estate.
SECTORS: dict[str, dict[str, tuple[str, str, Path]]] = {
    "Technology": {
        "Semiconductors":      ("Semiconductors",        ACCENT, ROOT / "Technology" / "Semiconductors"),
        "Software_SaaS":       ("Software / SaaS",       ACCENT, ROOT / "Technology" / "Software_SaaS"),
        "Cloud_Infrastructure":("Cloud & Infrastructure",ACCENT, ROOT / "Technology" / "Cloud_Infrastructure"),
        "AI_Machine_Learning": ("AI & Machine Learning", ACCENT, ROOT / "Technology" / "AI_Machine_Learning"),
        "Cybersecurity":       ("Cybersecurity",         ACCENT, ROOT / "Technology" / "Cybersecurity"),
        "Consumer_Electronics":("Consumer Electronics",  ACCENT, ROOT / "Technology" / "Consumer_Electronics"),
        "Fintech":             ("Fintech",               ACCENT, ROOT / "Technology" / "Fintech"),
        "Telecom":             ("Telecom",               ACCENT, ROOT / "Technology" / "Telecom"),
        "IT_Services":         ("IT Services",           ACCENT, ROOT / "Technology" / "IT_Services"),
        "Other":               ("Other",                 ACCENT, ROOT / "Technology" / "Other"),
    },
    "Communication Services": {
        "Wireless_Wireline_Telecom": ("Wireless & Wireline Telecom", ACCENT, ROOT / "Communication_Services" / "Wireless_Wireline_Telecom"),
        "Satellite_Towers":          ("Satellite & Towers",          ACCENT, ROOT / "Communication_Services" / "Satellite_Towers"),
        "Media_Entertainment":       ("Media & Entertainment",       ACCENT, ROOT / "Communication_Services" / "Media_Entertainment"),
        "Advertising_MarTech":       ("Advertising & MarTech",       ACCENT, ROOT / "Communication_Services" / "Advertising_MarTech"),
        "Social_Gaming_Platforms":   ("Social & Gaming Platforms",   ACCENT, ROOT / "Communication_Services" / "Social_Gaming_Platforms"),
        "Publishing_News":           ("Publishing & News",           ACCENT, ROOT / "Communication_Services" / "Publishing_News"),
        "Streaming":                 ("Streaming",                   ACCENT, ROOT / "Communication_Services" / "Streaming"),
        "Other":                     ("Other",                       ACCENT, ROOT / "Communication_Services" / "Other"),
    },
    "Consumer Discretionary": {
        "Retail_Specialty":         ("Retail & Specialty Stores",  ACCENT, ROOT / "Consumer_Discretionary" / "Retail_Specialty"),
        "Apparel_Footwear":         ("Apparel & Footwear",         ACCENT, ROOT / "Consumer_Discretionary" / "Apparel_Footwear"),
        "Automotive_EVs":           ("Automotive & EVs",           ACCENT, ROOT / "Consumer_Discretionary" / "Automotive_EVs"),
        "Restaurants_Hospitality":  ("Restaurants & Hospitality",  ACCENT, ROOT / "Consumer_Discretionary" / "Restaurants_Hospitality"),
        "Travel_Leisure":           ("Travel & Leisure",           ACCENT, ROOT / "Consumer_Discretionary" / "Travel_Leisure"),
        "Gaming_Entertainment":     ("Gaming & Entertainment",     ACCENT, ROOT / "Consumer_Discretionary" / "Gaming_Entertainment"),
        "Home_Garden":              ("Home & Garden",              ACCENT, ROOT / "Consumer_Discretionary" / "Home_Garden"),
        "E_commerce":               ("E-commerce",                 ACCENT, ROOT / "Consumer_Discretionary" / "E_commerce"),
        "Other":                    ("Other",                      ACCENT, ROOT / "Consumer_Discretionary" / "Other"),
    },
    "Consumer Staples": {
        "Food_Beverage":         ("Food & Beverage",         ACCENT, ROOT / "Consumer_Staples" / "Food_Beverage"),
        "Alt_Protein_Food_Tech": ("Alt-Protein & Food Tech", ACCENT, ROOT / "Consumer_Staples" / "Alt_Protein_Food_Tech"),
        "Household_Products":    ("Household Products",      ACCENT, ROOT / "Consumer_Staples" / "Household_Products"),
        "Personal_Care_Beauty":  ("Personal Care & Beauty",  ACCENT, ROOT / "Consumer_Staples" / "Personal_Care_Beauty"),
        "Tobacco_Vape":          ("Tobacco & Vape",          ACCENT, ROOT / "Consumer_Staples" / "Tobacco_Vape"),
        "Grocery_Distribution":  ("Grocery & Distribution",  ACCENT, ROOT / "Consumer_Staples" / "Grocery_Distribution"),
        "Other":                 ("Other",                   ACCENT, ROOT / "Consumer_Staples" / "Other"),
    },
    "Health Care": {
        # Biotech sub-sectors (7-color framework)
        "Red_Medical_Pharmaceutical": ("Medical / Pharmaceutical", ACCENT, ROOT / "Biotechnology" / "Red_Medical_Pharmaceutical"),
        "Green_Agricultural":         ("Agricultural",             ACCENT, ROOT / "Biotechnology" / "Green_Agricultural"),
        "White_Industrial":           ("Industrial",               ACCENT, ROOT / "Biotechnology" / "White_Industrial"),
        "Blue_Marine":                ("Marine",                   ACCENT, ROOT / "Biotechnology" / "Blue_Marine"),
        "Grey_Environmental":         ("Environmental",            ACCENT, ROOT / "Biotechnology" / "Grey_Environmental"),
        "Yellow_Food_Nutrition":      ("Food / Nutrition",         ACCENT, ROOT / "Biotechnology" / "Yellow_Food_Nutrition"),
        "Gold_Bioinformatics":        ("Bioinformatics",           ACCENT, ROOT / "Biotechnology" / "Gold_Bioinformatics"),
        # Healthcare services
        "Hospitals_Health_Systems":   ("Hospitals & Health Systems", ACCENT, ROOT / "Healthcare_Services" / "Hospitals_Health_Systems"),
        "Health_Insurance":           ("Health Insurance",           ACCENT, ROOT / "Healthcare_Services" / "Health_Insurance"),
        "Healthcare_IT_Telehealth":   ("Healthcare IT & Telehealth", ACCENT, ROOT / "Healthcare_Services" / "Healthcare_IT_Telehealth"),
        "Pharmacy_Distributors":      ("Pharmacy & Distributors",    ACCENT, ROOT / "Healthcare_Services" / "Pharmacy_Distributors"),
        "Medical_Devices":            ("Medical Devices",            ACCENT, ROOT / "Healthcare_Services" / "Medical_Devices"),
        "Dental_Vision_Hearing":      ("Dental, Vision & Hearing",   ACCENT, ROOT / "Healthcare_Services" / "Dental_Vision_Hearing"),
        "Other":                      ("Other",                      ACCENT, ROOT / "Healthcare_Services" / "Other"),
    },
    "Financials": {
        "Regional_Banks":           ("Regional Banks",             ACCENT, ROOT / "Financials" / "Regional_Banks"),
        "Investment_Banks_Brokers": ("Investment Banks & Brokers", ACCENT, ROOT / "Financials" / "Investment_Banks_Brokers"),
        "Asset_Management":         ("Asset Management",           ACCENT, ROOT / "Financials" / "Asset_Management"),
        "Insurance":                ("Insurance",                  ACCENT, ROOT / "Financials" / "Insurance"),
        "Fintech_Payments":         ("Fintech & Payments",         ACCENT, ROOT / "Financials" / "Fintech_Payments"),
        "BDCs":                     ("BDCs",                       ACCENT, ROOT / "Financials" / "BDCs"),
        "Specialty_Finance":        ("Specialty Finance",          ACCENT, ROOT / "Financials" / "Specialty_Finance"),
        "Crypto_Adjacent":          ("Crypto-Adjacent",            ACCENT, ROOT / "Financials" / "Crypto_Adjacent"),
        "Other":                    ("Other",                      ACCENT, ROOT / "Financials" / "Other"),
    },
    "Industrials": {
        "Aerospace_Defense":        ("Aerospace & Defense",        ACCENT, ROOT / "Industrials" / "Aerospace_Defense"),
        "Machinery":                ("Machinery",                  ACCENT, ROOT / "Industrials" / "Machinery"),
        "Transportation_Logistics": ("Transportation & Logistics", ACCENT, ROOT / "Industrials" / "Transportation_Logistics"),
        "Construction_Engineering": ("Construction & Engineering", ACCENT, ROOT / "Industrials" / "Construction_Engineering"),
        "Electrical_Equipment":     ("Electrical Equipment",       ACCENT, ROOT / "Industrials" / "Electrical_Equipment"),
        "Industrial_Services":      ("Industrial Services",        ACCENT, ROOT / "Industrials" / "Industrial_Services"),
        "Other":                    ("Other",                      ACCENT, ROOT / "Industrials" / "Other"),
    },
    "Energy": {
        "Exploration_Production":      ("Exploration & Production",      ACCENT, ROOT / "Energy" / "Exploration_Production"),
        "Oilfield_Services_Equipment": ("Oilfield Services & Equipment", ACCENT, ROOT / "Energy" / "Oilfield_Services_Equipment"),
        "Midstream":                   ("Midstream",                     ACCENT, ROOT / "Energy" / "Midstream"),
        "Renewable_Energy":            ("Renewable Energy",              ACCENT, ROOT / "Energy" / "Renewable_Energy"),
        "Coal_Uranium":                ("Coal & Uranium",                ACCENT, ROOT / "Energy" / "Coal_Uranium"),
        "Other":                       ("Other",                         ACCENT, ROOT / "Energy" / "Other"),
    },
    "Materials": {
        "Precious_Metals":          ("Precious Metals",            ACCENT, ROOT / "Materials" / "Precious_Metals"),
        "Battery_Critical_Metals":  ("Battery & Critical Metals",  ACCENT, ROOT / "Materials" / "Battery_Critical_Metals"),
        "Rare_Earth_Strategic":     ("Rare Earth & Strategic",     ACCENT, ROOT / "Materials" / "Rare_Earth_Strategic"),
        "Uranium":                  ("Uranium",                    ACCENT, ROOT / "Materials" / "Uranium"),
        "Base_Metals":              ("Base Metals",                ACCENT, ROOT / "Materials" / "Base_Metals"),
        "Steel_Iron":               ("Steel & Iron",               ACCENT, ROOT / "Materials" / "Steel_Iron"),
        "Specialty_Chemicals":      ("Specialty Chemicals",        ACCENT, ROOT / "Materials" / "Specialty_Chemicals"),
        "Construction_Materials":   ("Construction Materials",     ACCENT, ROOT / "Materials" / "Construction_Materials"),
        "Other":                    ("Other",                      ACCENT, ROOT / "Materials" / "Other"),
    },
    "Utilities": {
        "Electric_Utilities": ("Electric Utilities", ACCENT, ROOT / "Utilities" / "Electric_Utilities"),
        "Gas_Utilities":      ("Gas Utilities",      ACCENT, ROOT / "Utilities" / "Gas_Utilities"),
        "Water_Utilities":    ("Water Utilities",    ACCENT, ROOT / "Utilities" / "Water_Utilities"),
        "Multi_Utilities":    ("Multi-Utilities",    ACCENT, ROOT / "Utilities" / "Multi_Utilities"),
        "Renewable_IPPs":     ("Renewable IPPs",     ACCENT, ROOT / "Utilities" / "Renewable_IPPs"),
        "Other":              ("Other",              ACCENT, ROOT / "Utilities" / "Other"),
    },
    "Real Estate": {
        "Diversified_REITs":          ("Diversified REITs",           ACCENT, ROOT / "Real_Estate" / "Diversified_REITs"),
        "Residential_REITs":          ("Residential REITs",           ACCENT, ROOT / "Real_Estate" / "Residential_REITs"),
        "Commercial_Office_REITs":    ("Commercial / Office REITs",   ACCENT, ROOT / "Real_Estate" / "Commercial_Office_REITs"),
        "Industrial_Logistics_REITs": ("Industrial / Logistics REITs",ACCENT, ROOT / "Real_Estate" / "Industrial_Logistics_REITs"),
        "Data_Center_REITs":          ("Data Center REITs",           ACCENT, ROOT / "Real_Estate" / "Data_Center_REITs"),
        "Specialty_REITs":            ("Specialty REITs",             ACCENT, ROOT / "Real_Estate" / "Specialty_REITs"),
        "Mortgage_REITs":             ("Mortgage REITs",              ACCENT, ROOT / "Real_Estate" / "Mortgage_REITs"),
        "Proptech":                   ("Proptech",                    ACCENT, ROOT / "Real_Estate" / "Proptech"),
        "Other":                      ("Other",                       ACCENT, ROOT / "Real_Estate" / "Other"),
    },
}


# =============================================================================
# Theme
# =============================================================================
def inject_theme() -> None:
    st.markdown(
        f"""<style>
        /* Hide the deploy menu + footer but KEEP the header so the
           sidebar toggle chevron stays visible. */
        #MainMenu, footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{
            background-color: {NAVY} !important;
            height: 2.5rem;
        }}
        header[data-testid="stHeader"] button {{
            color: {WHITE} !important;
        }}
        .stApp {{
            background-color: {NAVY};
            color: {WHITE};
        }}
        .main .block-container {{
            padding-top: 1.8rem; padding-bottom: 2rem; max-width: 1280px;
        }}
        /* Force all Streamlit wrappers to be transparent — prevents
           default white backgrounds on markdown containers, element
           wrappers, and vertical blocks. */
        .main .block-container .element-container,
        .main .block-container .stMarkdown,
        .main .block-container [data-testid="stMarkdownContainer"],
        .main .block-container [data-testid="stVerticalBlock"] > div {{
            background: transparent !important;
        }}
        /* Default text: white on navy */
        h1, h2, h3, h4, h5, h6, p, span, label, li, code, .stMarkdown {{
            color: {WHITE} !important;
        }}
        /* Sidebar shell */
        section[data-testid="stSidebar"] > div:first-child {{
            background-color: {NAVY_CARD};
            border-right: 1px solid {BORDER};
        }}
        section[data-testid="stSidebar"] hr {{
            border-color: {BORDER}; margin: 14px 0;
        }}
        /* Streamlit bordered wrappers (forms, containers with border=True):
           override default white/light backgrounds with navy theme. */
        [data-testid="stForm"],
        [data-testid="stForm"] > div,
        [data-testid="stVerticalBlockBorderWrapper"],
        [data-testid="stVerticalBlockBorderWrapper"] > div,
        .stForm {{
            background-color: transparent !important;
            background: transparent !important;
            border-color: {BORDER} !important;
        }}
        /* Buttons */
        .stButton > button, .stForm button {{
            background-color: {NAVY_CARD};
            color: {WHITE};
            border: 1px solid {BORDER};
            border-radius: 6px;
            font-weight: 500;
        }}
        .stButton > button:hover, .stForm button:hover {{
            background-color: {NAVY_HOVER};
            border-color: {ACCENT};
            color: {WHITE};
        }}
        .stButton > button[kind="primary"] {{
            background-color: {ACCENT};
            color: #06121e;
            border-color: {ACCENT};
        }}
        /* ============ INPUTS ============
         * Streamlit's default light theme renders inputs with a white-ish
         * background. Forcing white text made it invisible. Switch to:
         *   widget container -> white background
         *   widget value text -> BLACK (per user request)
         *   widget OUTSIDE label -> WHITE (left on navy)
         */
        .stTextInput > div > div > input,
        .stNumberInput > div > div > input,
        .stDateInput > div > div > input,
        .stTextArea > div > div > textarea,
        .stSelectbox > div > div,
        .stSelectbox > div > div * {{
            background-color: #ffffff !important;
            color: #000000 !important;
            border-color: {BORDER} !important;
        }}
        /* Dropdown popover (rendered to body via portal) */
        div[data-baseweb="popover"], div[data-baseweb="popover"] * {{
            color: #000000 !important;
        }}
        div[data-baseweb="popover"] {{
            background-color: #ffffff !important;
        }}
        li[role="option"] {{
            background-color: #ffffff !important;
            color: #000000 !important;
        }}
        li[role="option"]:hover, li[role="option"][aria-selected="true"] {{
            background-color: #e2e8f0 !important;
        }}
        /* Date picker calendar */
        div[data-baseweb="calendar"], div[data-baseweb="calendar"] * {{
            background-color: #ffffff !important;
            color: #000000 !important;
        }}
        /* Radio: keep labels white, dot accent */
        .stRadio label, .stRadio label * {{ color: {WHITE} !important; }}
        /* Alerts / info / spinner */
        .stAlert {{
            background-color: {NAVY_CARD} !important;
            color: {WHITE_DIM} !important;
            border: 1px solid {BORDER} !important;
        }}
        .stAlert * {{ color: {WHITE_DIM} !important; }}
        .stSpinner, .stSpinner > div {{
            border-top-color: {ACCENT} !important;
            background: transparent !important;
        }}
        /* Streamlit status/running widget */
        [data-testid="stStatusWidget"],
        [data-testid="stStatusWidget"] * {{
            background-color: {NAVY_CARD} !important;
            color: {WHITE_DIM} !important;
            border-color: {BORDER} !important;
        }}
        hr {{ border-color: {BORDER} !important; }}
        a {{ color: {ACCENT}; }}
        /* Native dataframe (trade history) */
        [data-testid="stDataFrame"] {{
            background-color: {NAVY_CARD};
            border: 1px solid {BORDER};
            border-radius: 6px;
        }}
        /* Native dialog (catalyst modal) */
        div[role="dialog"] {{
            background-color: {NAVY_CARD} !important;
            color: {WHITE} !important;
            border: 1px solid {BORDER} !important;
        }}
        div[role="dialog"] * {{ color: {WHITE} !important; }}
        div[role="dialog"] a {{ color: {ACCENT} !important; }}
        /* IPO and other HTML tables we render via st.markdown */
        table.sierra-table {{
            background-color: {NAVY} !important;
            color: {WHITE};
            border-collapse: collapse;
            width: 100%;
            border: 1px solid {BORDER};
            border-radius: 6px;
            overflow: hidden;
        }}
        table.sierra-table th, table.sierra-table td {{
            background-color: {NAVY} !important;
            color: {WHITE};
        }}
        table.sierra-table tbody tr:nth-child(even) td {{
            background-color: rgba(255,255,255,0.025) !important;
        }}
        table.sierra-table tbody tr:hover td {{
            background-color: {NAVY_HOVER} !important;
        }}
        table.sierra-table tbody tr.sierra-clickable {{
            cursor: pointer;
        }}
        table.sierra-table tbody tr.sierra-clickable:hover td {{
            background-color: {NAVY_HOVER} !important;
            box-shadow: inset 3px 0 0 {ACCENT};
        }}
        table.sierra-table tbody tr.sierra-clickable a {{
            text-decoration: none !important;
            display: block;
        }}

        /* ====== REUSABLE CLASS SYSTEM ====== */

        /* Table header cell */
        .sierra-th {{
            padding: 10px 12px;
            border-bottom: 1px solid {BORDER};
            background: {NAVY_CARD} !important;
            color: {WHITE} !important;
            font-weight: 600;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            text-align: left;
        }}
        .sierra-th.text-right {{ text-align: right; }}
        .sierra-th.text-center {{ text-align: center; }}
        .sierra-th.wide-pad {{ padding: 10px 14px; }}

        /* Table body cell */
        .sierra-td {{
            padding: 9px 12px;
            border-bottom: 1px solid {BORDER};
            color: {WHITE_DIM} !important;
            font-size: 0.9rem;
            vertical-align: top;
        }}
        .sierra-td.text-right {{ text-align: right; }}
        .sierra-td.text-center {{ text-align: center; }}
        .sierra-td.narrow {{ font-size: 0.85rem; max-width: 340px; }}
        .sierra-td.nowrap {{ white-space: nowrap; }}
        .sierra-td.wide-pad {{ padding: 9px 14px; }}

        /* Badge */
        .sierra-badge {{
            display: inline-block;
            font-weight: 700;
            font-size: 0.7rem;
            padding: 2px 8px;
            border-radius: 4px;
            white-space: nowrap;
            color: #06121e !important;
            line-height: 1.4;
        }}
        .sierra-badge.sm {{
            font-size: 0.65rem;
            padding: 1px 6px;
            border-radius: 3px;
            text-transform: uppercase;
        }}
        .sierra-badge.lg {{
            font-size: 0.78rem;
            padding: 3px 10px;
        }}

        /* Ticker link */
        .sierra-link {{
            color: {WHITE} !important;
            font-weight: 700;
            text-decoration: none !important;
            border-bottom: 1px dotted {ACCENT};
        }}
        .sierra-link:hover {{
            color: {ACCENT} !important;
            border-bottom-style: solid;
        }}
        .sierra-link-ext {{
            color: {ACCENT} !important;
            text-decoration: none;
            font-size: 0.78rem;
            white-space: nowrap;
        }}
        .sierra-link-ext:hover {{
            text-decoration: underline !important;
        }}

        /* Cards */
        .sierra-card {{
            background: {NAVY_CARD};
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 14px 16px;
        }}
        .sierra-card.stat {{ text-align: center; }}
        .sierra-card .card-label {{
            font-size: 0.72rem;
            color: {WHITE_MUTE} !important;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }}
        .sierra-card .card-value {{
            font-size: 1.35rem;
            font-weight: 700;
        }}
        .sierra-card.event {{
            display: flex;
            gap: 14px;
            align-items: stretch;
            padding: 12px 14px;
            margin-bottom: 10px;
        }}
        .sierra-card.theme {{
            padding: 14px 18px;
            margin-bottom: 12px;
        }}

        /* Page header */
        .sierra-page-header {{
            margin-bottom: 8px;
        }}
        .sierra-page-header .section-label {{
            font-size: 0.75rem;
            color: {WHITE_MUTE} !important;
            text-transform: uppercase;
            letter-spacing: 1px;
            display: block;
            margin-bottom: 4px;
        }}
        .sierra-page-header .page-title {{
            font-size: 2rem;
            font-weight: 700;
            color: {WHITE} !important;
            letter-spacing: -0.5px;
            margin-bottom: 4px;
            line-height: 1.2;
        }}
        .sierra-page-header .page-subtitle {{
            font-size: 0.78rem;
            color: {WHITE_DIM} !important;
            margin-bottom: 14px;
            line-height: 1.55;
            max-width: 780px;
        }}

        /* Sidebar branding */
        .sierra-brand {{
            padding: 6px 0 14px;
            font-size: 1.15rem;
            font-weight: 700;
            color: {WHITE} !important;
            letter-spacing: -0.3px;
            border-bottom: 2px solid {ACCENT};
            margin-bottom: 8px;
        }}
        .sierra-nav-section {{
            font-size: 0.7rem;
            color: {WHITE_MUTE} !important;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin: 18px 0 8px;
            padding-top: 14px;
            border-top: 1px solid {BORDER};
        }}

        /* Sidebar active button */
        section[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
            box-shadow: inset 3px 0 0 {WHITE};
        }}
        /* Sidebar icon nav */
        .sierra-icon-nav {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}
        section[data-testid="stSidebar"] .sierra-icon-nav .stButton > button {{
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            text-align: left !important;
            justify-content: flex-start !important;
            padding: 6px 10px !important;
            border-radius: 6px !important;
            font-size: 0.85rem !important;
            font-weight: 400 !important;
            color: {WHITE_MUTE} !important;
            transition: background 0.15s, color 0.15s;
        }}
        section[data-testid="stSidebar"] .sierra-icon-nav .stButton > button:hover {{
            background: {NAVY_HOVER} !important;
            color: {WHITE} !important;
        }}
        section[data-testid="stSidebar"] .sierra-icon-nav .stButton > button[kind="primary"] {{
            background: {NAVY_HOVER} !important;
            color: {WHITE} !important;
            box-shadow: inset 3px 0 0 {ACCENT} !important;
        }}
        /* Flex helpers */
        .sierra-flex-row {{
            display: flex;
            gap: 14px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .sierra-flex-row.spread {{
            justify-content: space-between;
        }}
        .sierra-flex-row.baseline {{
            align-items: baseline;
        }}

        /* Spacers */
        .sierra-spacer {{ height: 18px; }}
        .sierra-spacer.sm {{ height: 10px; }}
        .sierra-spacer.lg {{ height: 24px; }}

        /* Text utilities */
        .text-mute {{ color: {WHITE_MUTE} !important; }}
        .text-dim {{ color: {WHITE_DIM} !important; }}
        .text-white {{ color: {WHITE} !important; }}
        .text-accent {{ color: {ACCENT} !important; }}
        .text-good {{ color: {GOOD} !important; }}
        .text-danger {{ color: {DANGER} !important; }}
        .text-warn {{ color: {WARN} !important; }}
        .text-xs {{ font-size: 0.68rem; }}
        .text-sm {{ font-size: 0.78rem; }}
        .text-md {{ font-size: 0.85rem; }}
        .text-lg {{ font-size: 1.05rem; }}
        .text-bold {{ font-weight: 700; }}
        .text-medium {{ font-weight: 500; }}
        .text-upper {{ text-transform: uppercase; letter-spacing: 0.5px; }}

        /* Responsive */
        @media (max-width: 768px) {{
            .main .block-container {{
                padding-left: 0.5rem !important;
                padding-right: 0.5rem !important;
            }}
            .sierra-td, .sierra-th {{
                padding: 6px 8px;
                font-size: 0.78rem;
            }}
            .sierra-page-header .page-title {{
                font-size: 1.5rem;
            }}
            .sierra-card.event {{
                flex-direction: column;
                gap: 8px;
            }}
            table.sierra-table {{
                display: block;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
            }}
        }}
        @media (max-width: 480px) {{
            .sierra-td.narrow {{ max-width: 200px; }}
            .sierra-page-header .page-subtitle {{ font-size: 0.72rem; }}
        }}
        </style>""",
        unsafe_allow_html=True,
    )


# =============================================================================
# UI Helpers
# =============================================================================

def _page_header(section: str, title: str, subtitle: str = "") -> None:
    """Render a consistent page header: section label + title + optional subtitle."""
    sub_html = (
        f"<div class='page-subtitle'>{subtitle}</div>" if subtitle else ""
    )
    st.markdown(
        f"""<div class='sierra-page-header'>
          <span class='section-label'>{section}</span>
          <div class='page-title'>{title}</div>
          {sub_html}
        </div>""",
        unsafe_allow_html=True,
    )


def _badge(label: str, color: str, size: str = "") -> str:
    """Return HTML for a colored badge. size: '' (default), 'sm', 'lg'."""
    cls = f"sierra-badge {size}".strip()
    return f"<span class='{cls}' style='background:{color};'>{label}</span>"


def _ticker_link(ticker: str) -> str:
    """Return HTML for a clickable ticker that opens the catalyst dialog."""
    return (
        f"<a href='?ticker={ticker}' target='_self' "
        f"class='sierra-link'>{ticker}</a>"
    )


def _table_head(columns: list[tuple[str, str]], wide: bool = False) -> str:
    """Build <thead><tr>…</tr></thead> from [(header_text, alignment), …].

    *alignment*: 'left', 'right', 'center'.
    *wide*: use wider IPO-style padding.
    """
    pad_cls = " wide-pad" if wide else ""
    cells = "".join(
        f"<th class='sierra-th{pad_cls} text-{align}'>{h}</th>"
        for h, align in columns
    )
    return f"<thead><tr>{cells}</tr></thead>"


# =============================================================================
# Helpers
# =============================================================================
def _human_sub_label(sec: str, sub_key: str) -> str:
    """Map a sector + sub-key pair to a human-readable label."""
    try:
        return SECTORS[sec][sub_key][0]
    except Exception:
        return (sub_key or "").replace("_", " ")


def load_description(dir_path: Path) -> str:
    """Legacy plain-text loader (kept for backwards compat)."""
    p = dir_path / "description.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def load_description_parts(dir_path: Path) -> tuple[str, list[str]]:
    """Parse description.md into (paragraph_text, [representative_areas]).

    Strips markdown # / ## headers (no inline taxonomy labels).
    Lines starting with '-' or '*' become area entries.
    Remaining non-empty lines fold into the paragraph.
    """
    p = dir_path / "description.md"
    if not p.exists():
        return "", []
    raw = p.read_text(encoding="utf-8")
    para: list[str] = []
    areas: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("- ", "* ", "• ")):
            areas.append(line[2:].strip())
        else:
            para.append(line)
    return " ".join(para), areas


def quotes_to_df(rows: list[Quote], info: dict) -> pd.DataFrame:
    out = []
    for q in rows:
        meta = info.get(q.ticker)
        if meta is not None:
            # Curated INFO: real company name + curated blurb
            company = f"{meta.name} — {meta.blurb}"
        elif q.summary:
            # Real NASDAQ description (cached or fresh)
            company = short_blurb(q.summary) or q.summary
        else:
            # No real company-specific description available; blank.
            company = ""
        # Same-window link: only this cell is clickable, so clicking
        # anywhere else in the row does nothing.
        ticker_link = _ticker_link(q.ticker)
        out.append({
            "Ticker":      ticker_link,
            "Close":       q.close,
            "Float":       q.float_shares,
            "Mkt Cap":     q.market_cap,
            "Country":     q.country or "",
            "Description": company,
        })
    return pd.DataFrame(out)


def _price_color(v: float) -> str:
    if pd.isna(v):
        return ""
    if v < 5:
        return f"color:{GOOD}; font-weight:600;"
    if v < 10:
        return f"color:{WARN}; font-weight:600;"
    return "color:#fb923c; font-weight:600;"


def _float_bg(v: float) -> str:
    if pd.isna(v):
        return ""
    norm = max(0.0, min(1.0, float(v) / MAX_FLOAT))
    alpha = 0.75 - norm * 0.55
    return (
        f"background-color: rgba(34, 197, 94, {alpha:.2f}); "
        f"color:#06121e; font-weight:600;"
    )


def style_table(df: pd.DataFrame) -> pd.io.formats.style.Styler | pd.DataFrame:
    if df.empty:
        return df
    s = df.style.format({
        "Ticker":  lambda v: v,                      # already HTML anchor
        "Close":   lambda v: f"${v:.2f}" if pd.notna(v) else "—",
        "Float":   tv_num,
        "Mkt Cap": tv_num,
        "Country": lambda v: v if v else "—",
    }, escape=None)
    s = s.map(_float_bg, subset=["Float"])
    s = s.map(_price_color, subset=["Close"])
    s = s.set_properties(subset=["Ticker"], **{
        "font-weight": "700", "color": WHITE, "text-align": "left",
    })
    s = s.set_properties(**{"text-align": "right", "color": WHITE_DIM})
    s = s.set_properties(subset=["Ticker"], **{"text-align": "left"})
    s = s.set_properties(subset=["Country"], **{
        "text-align": "left", "color": WHITE_DIM,
        "font-size": "0.85rem",
    })
    s = s.set_properties(subset=["Description"], **{
        "text-align": "left", "color": WHITE_MUTE,
        "font-size": "0.85rem", "max-width": "440px",
        "white-space": "normal", "line-height": "1.4",
    })
    s = s.set_table_styles([
        {"selector": "th",
         "props": f"background-color:{NAVY_CARD}; color:{WHITE}; "
                  "font-weight:600; text-align:right; padding:10px 14px; "
                  f"border-bottom:1px solid {BORDER}; font-size:0.78rem; "
                  "text-transform:uppercase; letter-spacing:0.5px;"},
        {"selector": "th.col_heading.level0:nth-child(1), "
                     "th.col_heading.level0:nth-child(5), "
                     "th.col_heading.level0:nth-child(6)",
         "props": "text-align:left;"},
        {"selector": "td",
         "props": f"padding:9px 14px; font-size:0.9rem; "
                  f"vertical-align:top; border-bottom:1px solid {BORDER};"},
        {"selector": "tbody tr:nth-child(even)",
         "props": f"background-color:rgba(255,255,255,0.02);"},
        {"selector": "tbody tr:hover",
         "props": f"background-color:{NAVY_HOVER};"},
        {"selector": "",
         "props": "border-collapse:collapse; width:100%; "
                  f"border:1px solid {BORDER}; border-radius:6px; overflow:hidden;"},
    ])
    s = s.hide(axis="index")
    return s


# =============================================================================
# Catalyst modal (native dialog — has built-in close X)
# =============================================================================
CATALYST_TYPE_COLOR = {
    # Bullish (green family)
    "FDA Approval":     "#22c55e",
    "PDUFA":            "#22c55e",
    "IND Clearance":    "#22c55e",
    "NDA / BLA":        "#10b981",
    "Designation":      "#10b981",
    "FDA Meeting":      "#06b6d4",
    "Product Launch":   "#10b981",
    "Contract Win":     "#34d399",
    "Buyout / Rumor":   "#facc15",
    "M&A":              "#facc15",
    "Insider Buy":      "#22c55e",
    "Institutional Buy":"#34d399",
    # Mixed / depends on result (cyan / blue family)
    "Clinical Data":    "#06b6d4",
    "Trial Enrollment": "#06b6d4",
    "Conference":       "#06b6d4",
    "Partnership":      "#64b5f6",
    "Listing":          "#64b5f6",
    # Neutral / structural (violet / muted)
    "Earnings":         "#a78bfa",
    "Cash Runway":      "#a78bfa",
    "Guidance":         "#a78bfa",
    "Patent":           "#94a3b8",
    "Analyst":          "#94a3b8",
    "Management Change":"#94a3b8",
    "Operational Update":"#94a3b8",
    "Press Release":    "#64748b",
    # Bearish-leaning (orange / red)
    "Offering":         "#f97316",
    "Private Placement":"#f97316",
    "Reverse Split":    "#f97316",
    "CRL":              "#ef4444",
    "Bankruptcy":       "#ef4444",
    "Restructuring":    "#f97316",
    "Auditor":          "#94a3b8",
    "Legal / Regulatory":"#ef4444",
}


def _close_dialog() -> None:
    """Called by the in-dialog Close button. Streamlit reruns afterwards;
    selected_ticker has already been consumed in main(), so the dialog
    won't re-open."""
    pass




@st.dialog("Catalysts", width="large")
def catalyst_dialog(ticker: str) -> None:
    # No price filter on the catalyst dialog — show every PM catalyst
    # day regardless of where the stock traded that day. (The default
    # $1-$20 cap on fetch_premarket_catalysts is for the LIVE screen,
    # not historical research.) Threshold dropped to 20% so smaller
    # but still notable moves surface.
    with st.spinner("Loading pre-market catalysts…"):
        rows = fetch_premarket_catalysts(
            ticker,
            min_price=0.01,
            max_price=1_000_000.0,
            min_upside_pct=20.0,
            lookback_days=60,
        )

    st.markdown(
        f"<div style='font-size:1.4rem;font-weight:700;color:{WHITE};"
        f"margin-bottom:4px;'>{ticker} — Pre-Market Catalysts</div>"
        f"<div style='font-size:0.78rem;color:{WHITE_MUTE};"
        f"margin-bottom:14px;'>Click any row to open {ticker} on "
        f"TradingView (5-min) at the PM-low timestamp.</div>",
        unsafe_allow_html=True,
    )

    if not rows:
        st.info(
            f"No pre-market catalyst days found for {ticker} in the "
            f"last 60 days (PM upside ≥ 20%). Either the ticker had "
            f"no notable pre-market moves, or yfinance returned no "
            f"intraday data for it."
        )
        if st.button("Close", key="close_empty"):
            _close_dialog()
            st.rerun()
        return

    thead = _table_head([
        ("Date", "left"), ("PM Low", "right"), ("PM High", "right"),
        ("Upside", "right"), ("Type", "left"),
        ("Catalyst", "left"), ("Source", "center"),
    ])

    SENT_COLOR = {
        "Bullish": "#22c55e",
        "Bearish": "#ef4444",
        "Neutral": "#64748b",
    }

    body_rows = []
    for r in rows:
        date_str = r["date"].strftime("%b %d, %Y")
        type_label = r.get("type") or "News"
        type_col = CATALYST_TYPE_COLOR.get(type_label, WHITE_MUTE)
        type_badge = _badge(type_label, type_col)
        sent_label = r.get("sentiment") or "Neutral"
        sent_col = SENT_COLOR.get(sent_label, "#64748b")
        sent_badge = _badge(sent_label, sent_col)
        catalyst_text = (
            r["title"] if r["title"]
            else "<span class='text-mute'>—</span>"
        )
        # Source cell: primary source link + secondary source corroboration
        # OR an explicit Unverified badge when only one source is available.
        primary_source = r.get("source") or "—"
        secondary = r.get("secondary_source") or ""
        unverified = r.get("unverified", False)
        if r["link"] and primary_source != "—":
            primary_html = (
                f"<a href='{r['link']}' target='_blank' "
                f"class='sierra-link-ext'>{primary_source} ↗</a>"
            )
        else:
            primary_html = (
                f"<span class='text-mute text-sm'>"
                f"{primary_source}</span>"
            )
        if unverified:
            verify_html = (
                f"<div style='margin-top:2px;'>"
                f"{_badge('Unverified', '#f97316', 'sm')}</div>"
            )
        elif secondary:
            verify_html = (
                f"<div style='margin-top:2px;' class='text-mute text-xs'>"
                f"+ {secondary}</div>"
            )
        else:
            verify_html = ""
        source_html = primary_html + verify_html

        up = r["upside_pct"]
        up_color = GOOD if up >= 50 else (WARN if up >= 30 else ACCENT)
        pm_low = r.get("pm_low")
        pm_low_time = r.get("pm_low_time") or ""
        pm_low_cell = (
            f"<div class='text-dim text-medium'>${pm_low:.2f}</div>"
            + (f"<div class='text-mute text-xs'>{pm_low_time}</div>"
               if pm_low_time else "")
            if pm_low is not None
            else "<div class='text-mute'>—</div>"
        )
        pm_high_cell = (
            f"<div class='text-white text-bold'>${r['pm_high']:.2f}</div>"
            f"<div class='text-mute text-xs'>{r['pm_high_time']}</div>"
        )
        # TradingView deep-link: 5m chart at the symbol. URL hash carries
        # the PM-low date + time so the user knows where to scroll on
        # arrival (TradingView doesn't accept intraday time as a query
        # param, so this is the best deep-link possible today).
        date_iso = r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"])
        tv_url = (
            f"https://www.tradingview.com/chart/?symbol=NASDAQ%3A{ticker}"
            f"&interval=5#pm_low={date_iso}_{pm_low_time.replace(' ', '_')}"
        )
        tv_tip = (f"Open {ticker} on TradingView 5m — scroll to "
                  f"{date_str} {pm_low_time} (PM low)") if pm_low_time else \
                 (f"Open {ticker} on TradingView 5m — {date_str}")
        row_link_open = (
            f"<a href='{tv_url}' target='_blank' "
            f"title='{tv_tip}'>"
        )
        row_link_close = "</a>"
        body_rows.append(
            f"<tr class='sierra-clickable'>"
            f"<td class='sierra-td nowrap text-white text-medium'>"
            f"{row_link_open}📈 {date_str}{row_link_close}</td>"
            f"<td class='sierra-td text-right'>{row_link_open}{pm_low_cell}{row_link_close}</td>"
            f"<td class='sierra-td text-right'>{row_link_open}{pm_high_cell}{row_link_close}</td>"
            f"<td class='sierra-td text-right text-bold' style='color:{up_color};'>"
            f"{row_link_open}<span style='color:{up_color};'>+{up:.1f}%</span>{row_link_close}</td>"
            f"<td class='sierra-td'>{type_badge}</td>"
            f"<td class='sierra-td narrow'>"
            f"{row_link_open}{catalyst_text}{row_link_close}</td>"
            f"<td class='sierra-td text-center'>{source_html}</td>"
            f"</tr>"
        )

    st.markdown(
        f"""<table class='sierra-table'>
          {thead}
          <tbody>{''.join(body_rows)}</tbody>
        </table>""",
        unsafe_allow_html=True,
    )

    if st.button("Close", key="close_dlg"):
        _close_dialog()
        st.rerun()


# =============================================================================
# Sector view
# =============================================================================
def render_sector(sector: str, folder: str, rows: list[Quote], info: dict) -> None:
    label, _, dir_path = SECTORS[sector][folder]

    para, areas = load_description_parts(dir_path)
    if para:
        st.markdown(
            f"<div class='text-dim' style='font-size:0.9rem;"
            f"line-height:1.6;margin-bottom:14px;'>{para}</div>",
            unsafe_allow_html=True,
        )
    if areas:
        items = "".join(
            f"<li class='text-white' style='margin-bottom:4px;'>{a}</li>"
            for a in areas
        )
        st.markdown(
            f"<ul style='font-size:0.9rem;line-height:1.5;"
            f"padding-left:22px;margin:0 0 20px 0;'>{items}</ul>",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""<div style="margin-bottom:10px;">
          <span class='text-lg text-bold text-white'>
            Candidates ({len(rows)})
          </span>
        </div>""",
        unsafe_allow_html=True,
    )

    if not rows:
        st.info("No tickers in this category currently pass the filter.")
        return

    df = quotes_to_df(rows, info)
    st.markdown(style_table(df).to_html(), unsafe_allow_html=True)


# =============================================================================
# Trading Journal
# =============================================================================
def _stat_card(label: str, value: str, color: str) -> None:
    st.markdown(
        f"""<div class='sierra-card stat'>
          <div class='card-label'>{label}</div>
          <div class='card-value' style='color:{color};'>{value}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_journal() -> None:
    _page_header("Trading Journal", "Performance Dashboard")

    trades = trading_journal.load_trades()
    stats = trading_journal.calculate_stats(trades)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _stat_card("Total Trades", str(stats["total_trades"]), WHITE)
    with c2:
        col = GOOD if stats["win_rate"] >= 50 else DANGER
        _stat_card("Win Rate", f"{stats['win_rate']:.1f}%", col)
    with c3:
        col = GOOD if stats["total_pnl"] >= 0 else DANGER
        sign = "+" if stats["total_pnl"] >= 0 else ""
        _stat_card("Total P&L", f"{sign}${stats['total_pnl']:,.2f}", col)
    with c4:
        col = GOOD if stats["avg_pnl"] >= 0 else DANGER
        sign = "+" if stats["avg_pnl"] >= 0 else ""
        _stat_card("Avg P&L", f"{sign}${stats['avg_pnl']:,.2f}", col)

    st.markdown("<div class='sierra-spacer'></div>", unsafe_allow_html=True)

    with st.expander("Add new trade", expanded=not trades):
        with st.form("trade_form", clear_on_submit=True):
            r1 = st.columns(4)
            with r1[0]: trade_date = st.date_input("Date")
            with r1[1]: ticker = st.text_input("Ticker").upper().strip()
            with r1[2]: direction = st.selectbox("Direction", ["Long", "Short"])
            with r1[3]: quantity = st.number_input("Quantity", min_value=1, value=100, step=100)
            r2 = st.columns(3)
            with r2[0]: entry = st.number_input("Entry", min_value=0.01, value=10.0, step=0.01, format="%.2f")
            with r2[1]: exit_ = st.number_input("Exit", min_value=0.01, value=10.0, step=0.01, format="%.2f")
            with r2[2]: tags = st.text_input("Tags (comma-separated)")
            notes = st.text_area("Notes", height=70)
            submitted = st.form_submit_button("Save trade", use_container_width=True)
            if submitted:
                if not ticker:
                    st.error("Ticker is required.")
                else:
                    trading_journal.add_trade(trading_journal.Trade(
                        date=trade_date.isoformat(), ticker=ticker,
                        direction=direction, entry=entry, exit=exit_,
                        quantity=quantity, notes=notes, tags=tags,
                    ))
                    st.success(f"Trade saved: {ticker}")
                    st.rerun()

    if not trades:
        st.markdown(
            f"<div style='color:{WHITE_MUTE};text-align:center;padding:32px 0;'>"
            "No trades recorded yet. Add your first trade above.</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"<div style='font-size:1.05rem;font-weight:700;color:{WHITE};"
        f"margin:22px 0 10px;'>Trade history ({len(trades)})</div>",
        unsafe_allow_html=True,
    )

    df = pd.DataFrame([
        {
            "Date":     t.get("date", ""),
            "Ticker":   t.get("ticker", ""),
            "Dir":      t.get("direction", ""),
            "Entry":    t.get("entry"),
            "Exit":     t.get("exit"),
            "Qty":      t.get("quantity"),
            "P&L":      t.get("pnl"),
            "P&L %":    t.get("pnl_pct"),
            "Tags":     t.get("tags", ""),
        }
        for t in trades
    ])
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "Entry":  st.column_config.NumberColumn(format="$%.2f"),
            "Exit":   st.column_config.NumberColumn(format="$%.2f"),
            "P&L":    st.column_config.NumberColumn(format="$%.2f"),
            "P&L %":  st.column_config.NumberColumn(format="%.2f%%"),
        },
    )

    selected = event.selection.rows if event and event.selection else []

    bcol1, bcol2, _ = st.columns([1, 1, 4])
    with bcol1:
        if st.button(
            f"Delete selected ({len(selected)})",
            disabled=not selected,
            use_container_width=True,
        ):
            # delete from highest index down to keep indices stable
            for idx in sorted(selected, reverse=True):
                trading_journal.delete_trade(idx)
            st.success(f"Deleted {len(selected)} trade(s).")
            st.rerun()
    with bcol2:
        if st.button("Clear all trades", use_container_width=True):
            trading_journal.clear_all()
            st.success("Journal cleared.")
            st.rerun()


# =============================================================================
# Changelog dialog
# =============================================================================
@st.dialog("Universe Changelog", width="large")
def changelog_dialog() -> None:
    """Modal showing the 10 most recent ticker adds / drops with reason."""
    events = recent_events(limit=10)

    st.markdown(
        f"""<div class='text-sm text-dim' style='margin-bottom:10px;line-height:1.5;'>
          Tracks tickers entering or exiting the screen
          (<b>${MIN_PRICE:.0f}\u2013${MAX_PRICE:.0f}</b> &middot;
          <b>float &lt; 20M</b>). Updated each time a sector loads.
        </div>""",
        unsafe_allow_html=True,
    )

    if not events:
        st.info(
            "No changes recorded yet. Browse sector pages — the first "
            "visit seeds the snapshot, and every subsequent qualifying "
            "change is logged here."
        )
        return

    cards: list[str] = []
    for e in events:
        sym = e.get("sym", "")
        sector = e.get("sector", "")
        ts = e.get("ts", "")
        action = e.get("action", "")
        reason = e.get("reason", "")
        price = e.get("price")
        fl = e.get("float_shares")

        is_add = action == "added"
        accent_col = GOOD if is_add else DANGER
        accent_bg = "rgba(34,197,94,0.10)" if is_add else "rgba(239,68,68,0.10)"
        glyph = "▲ ADDED" if is_add else "▼ REMOVED"

        meta_bits: list[str] = []
        if price is not None:
            try:
                meta_bits.append(f"${float(price):.2f}")
            except Exception:
                pass
        if fl:
            try:
                meta_bits.append(f"float {float(fl)/1e6:.1f}M")
            except Exception:
                pass
        meta_str = " &middot; ".join(meta_bits) if meta_bits else "&nbsp;"

        cards.append(
            f"""<div class='sierra-card event' style='border-left:4px solid {accent_col};'>
              <div style="flex:0 0 84px;">
                <div class='sierra-badge sm' style='background:{accent_bg};
                  color:{accent_col} !important;text-align:center;
                  margin-bottom:6px;display:block;'>{glyph}</div>
                <div class='text-lg text-bold text-white'
                  style='letter-spacing:-0.3px;'>{sym}</div>
              </div>
              <div style="flex:1;min-width:0;">
                <div class='text-xs text-mute text-upper'
                  style='margin-bottom:4px;'>{sector} &middot; {ts}</div>
                <div class='text-md text-dim'
                  style='line-height:1.45;margin-bottom:4px;'>{reason}</div>
                <div class='text-xs text-mute'>{meta_str}</div>
              </div>
            </div>"""
        )

    st.markdown("".join(cards), unsafe_allow_html=True)


# =============================================================================
# Today's top moves
# =============================================================================
def _top_movers_pool() -> tuple[str, ...]:
    pool: set[str] = set()
    for mod in (bio_universe, tech_universe, energy_universe,
                industrials_universe, materials_universe,
                consumer_disc_universe, financials_universe,
                comm_services_universe, consumer_staples_universe,
                real_estate_universe, healthcare_svc_universe):
        try:
            pool.update(mod.all_tickers())
        except Exception:
            try:
                pool.update(mod.INFO.keys())
            except Exception:
                continue
    return tuple(sorted(pool))


def _build_movers_sector_lookup() -> dict[str, tuple[str, str]]:
    sector_lookup: dict[str, tuple[str, str]] = {}
    try:
        from screener import fetch_nasdaq_universe, classify_ticker_sector
        for nrow in fetch_nasdaq_universe():
            sym = (nrow.get("symbol") or "").strip().upper()
            if not sym:
                continue
            cls = classify_ticker_sector(nrow)
            if cls is None:
                continue
            sector_lookup[sym] = cls
    except Exception:
        pass
    return sector_lookup


def _render_movers_table(movers: list[dict],
                         sector_lookup: dict[str, tuple[str, str]],
                         empty_msg: str) -> None:
    if not movers:
        st.info(empty_msg)
        return

    thead = _table_head([
        ("Ticker", "left"), ("Sector", "left"), ("Country", "left"),
        ("Ref Price", "right"),     # price at window-open (7:00 or 4:00)
        ("PM High", "right"),       # peak hit in window
        ("Move", "right"),          # gain from ref
        ("Type", "left"),
        ("Catalyst", "left"), ("Source", "center"),
    ])

    body_rows = []
    for r in movers:
        ticker_html = _ticker_link(r["ticker"])
        type_label = r["news_type"]
        type_col = CATALYST_TYPE_COLOR.get(type_label, WHITE_MUTE)
        type_badge = _badge(type_label, type_col)
        catalyst_text = (
            r["news_title"] if r["news_title"]
            else "<span class='text-mute'>\u2014</span>"
        )
        source_label = r.get("news_source") or "\u2014"
        if r["news_link"] and source_label != "\u2014":
            source_html = (
                f"<a href='{r['news_link']}' target='_blank' "
                f"class='sierra-link-ext'>{source_label} \u2197</a>"
            )
        else:
            source_html = (
                f"<span class='text-mute text-sm'>"
                f"{source_label}</span>"
            )
        move = r["move_pct"]
        # Re-tiered for the 10% floor — most rows will be small moves.
        # Bright green ≥100, green ≥50, yellow ≥25, accent base.
        if move >= 100:
            move_color = "#22c55e"
        elif move >= 50:
            move_color = GOOD
        elif move >= 25:
            move_color = WARN
        else:
            move_color = ACCENT

        cls = sector_lookup.get(r["ticker"])
        if cls:
            sec, sub = cls
            sub_label = _human_sub_label(sec, sub)
            sector_html = (
                f"<div class='text-white text-bold' "
                f"style='font-size:0.82rem;line-height:1.25;'>{sec}</div>"
                f"<div class='text-mute text-xs' "
                f"style='line-height:1.25;'>{sub_label}</div>"
            )
        else:
            sector_html = "<span class='text-mute'>\u2014</span>"

        country_val = r.get("country") or "\u2014"
        country_html = (
            f"<span class='text-dim' style='font-size:0.82rem;'>"
            f"{country_val}</span>"
        )

        ref_time = r.get("ref_time") or ""
        high_time = r.get("high_time") or ""
        ref_cell = (
            f"<div class='text-dim text-medium'>${r['lod']:.2f}</div>"
            + (f"<div class='text-mute text-xs'>{ref_time}</div>"
               if ref_time else "")
        )
        high_cell = (
            f"<div class='text-white text-bold'>${r['hod']:.2f}</div>"
            + (f"<div class='text-mute text-xs'>{high_time}</div>"
               if high_time else "")
        )

        body_rows.append(
            f"<tr>"
            f"<td class='sierra-td'>{ticker_html}</td>"
            f"<td class='sierra-td'>{sector_html}</td>"
            f"<td class='sierra-td'>{country_html}</td>"
            f"<td class='sierra-td text-right'>{ref_cell}</td>"
            f"<td class='sierra-td text-right'>{high_cell}</td>"
            f"<td class='sierra-td text-right text-bold' "
            f"style='color:{move_color};'>+{move:.1f}%</td>"
            f"<td class='sierra-td'>{type_badge}</td>"
            f"<td class='sierra-td narrow'>{catalyst_text}</td>"
            f"<td class='sierra-td text-center'>{source_html}</td>"
            f"</tr>"
        )

    st.markdown(
        f"""<table class='sierra-table'>
          {thead}
          <tbody>{''.join(body_rows)}</tbody>
        </table>""",
        unsafe_allow_html=True,
    )


@st.cache_resource
def _ping_sound_b64() -> str:
    """Generate a short alert ping as a base64-encoded WAV string."""
    sr, dur, freq = 22050, 0.12, 880
    n = int(sr * dur)
    samples = []
    for i in range(n):
        t = i / sr
        env = math.exp(-t * 25)
        val = env * math.sin(2 * math.pi * freq * t)
        samples.append(int(val * 32767 * 0.4))
    data_sz = n * 2
    hdr = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_sz, b"WAVE",
        b"fmt ", 16, 1, 1, sr, sr * 2, 2, 16,
        b"data", data_sz,
    )
    raw = hdr + struct.pack(f"<{n}h", *samples)
    return base64.b64encode(raw).decode()


@st.fragment(run_every="30s")
def _top_movers_fragment(
    pool: tuple[str, ...],
    sector_lookup: dict[str, tuple[str, str]],
    which: str,                       # "main" or "early"
    window_label: str,
) -> None:
    """Self-refreshing fragment — re-runs every 30s without re-running
    the entire page. Calls fetch_top_movers_dual() so both tabs share
    a single underlying scan (cached at 5min). Tab switching is
    instant because the data already exists for both windows."""
    _refresh_key = f"_pending_refresh_{which}"
    _data_key = f"_movers_data_{which}"
    _err_key = f"_movers_err_{which}"

    # Apply pending cache clear from a previous button click BEFORE
    # the data fetch so the fresh scan runs in the same execution.
    if st.session_state.pop(_refresh_key, False):
        fetch_top_movers_dual.clear()

    try:
        from zoneinfo import ZoneInfo
        now_et = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        now_et = datetime.utcnow()
    now_str = now_et.strftime("%H:%M:%S %Z") or now_et.strftime("%H:%M:%S")

    try:
        dual = fetch_top_movers_dual(pool)
        movers = dual.get(which) or []
        scan_err = None
        # Persist last successful result so the table never goes blank.
        st.session_state[_data_key] = movers
        st.session_state.pop(_err_key, None)
    except Exception as e:
        scan_err = f"{type(e).__name__}: {e}"
        st.session_state[_err_key] = scan_err
        # Fall back to last known good data.
        movers = st.session_state.get(_data_key, [])

    # -- Detect newly-appeared movers and play an alert ping --
    _cur_syms = {m["ticker"] for m in movers}
    _seen_key = f"seen_movers_{which}"
    _prev = st.session_state.get(_seen_key)
    if _prev is not None and st.session_state.get("enable_mover_sound", True):
        if _cur_syms - _prev:
            import streamlit.components.v1 as _comp
            _comp.html(
                '<audio autoplay src="data:audio/wav;base64,'
                + _ping_sound_b64()
                + '"></audio>',
                height=0,
            )
    st.session_state[_seen_key] = _cur_syms

    is_weekend = now_et.weekday() >= 5
    window_start = "07:00" if which == "main" else "04:00"
    window_end = "09:29" if which == "main" else "06:59"
    in_main_pm = (7, 0) <= (now_et.hour, now_et.minute) < (9, 30)
    in_early_pm = (4, 0) <= (now_et.hour, now_et.minute) < (7, 0)

    diag_bits = [f"{window_label}", f"as of {now_str}"]
    if is_weekend:
        diag_bits.append("weekend — no fresh PM data today")
    elif (which == "main" and now_et.hour < 7):
        diag_bits.append("market hasn't opened the main PM window yet")
    elif (which == "early" and now_et.hour < 4):
        diag_bits.append("early PM hasn't started yet")

    info_col, btn_col = st.columns([10, 1])
    with info_col:
        st.markdown(
            f"<div style='font-size:0.72rem;color:{WHITE_MUTE};"
            f"margin-bottom:6px;'>{' &middot; '.join(diag_bits)}</div>"
            f"<div style='font-size:0.7rem;color:{WHITE_MUTE};"
            f"margin-bottom:10px;'>Universe pool: {len(pool):,} tickers "
            f"&middot; movers found: {len(movers):,} &middot; "
            f"auto-refresh every 30s (data cache 5min, one scan covers both tabs)</div>",
            unsafe_allow_html=True,
        )
    with btn_col:
        if st.button(
            "↻", key=f"force_refresh_{which}",
            help="Force-refresh: clear cache and re-scan yfinance now",
            use_container_width=True,
        ):
            st.session_state[_refresh_key] = True

    if scan_err:
        st.error(f"Scan failed: {scan_err}")
        if not movers:
            return

    if not movers:
        why = ""
        if is_weekend:
            why = (" Pre-market data is only published during trading "
                   "days (Mon–Fri).")
        elif window_start == "07:00" and not in_main_pm and now_et.hour < 7:
            why = (" The 7:00–9:30 AM window is still in the future — "
                   "check back after 7:00 AM ET.")
        elif window_start == "04:00" and not in_early_pm and now_et.hour < 4:
            why = (" The 4:00–7:00 AM window is still in the future.")
        st.info(
            f"No tickers met the criteria (≥10% from window-open · "
            f"$1–$20 · float <20M) between {window_start} and "
            f"{window_end} ET today.{why}"
        )
        return

    _render_movers_table(movers, sector_lookup, empty_msg="")


def render_top_movers() -> None:
    _title_col, _sound_col = st.columns([20, 1])
    with _title_col:
        _page_header(
            "Top Moves",
            "Today's Top Moves",
            "Criteria: price $1\u201320 &middot; float &lt; 20M. Logged anytime "
            "within the window the stock is up \u226510% from its window-open "
            "price (7:00 AM for main, 4:00 AM for early).",
        )
    with _sound_col:
        st.toggle(
            "\U0001f514", value=True, key="enable_mover_sound",
            help="Toggle new-mover alert sound",
        )

    # Build the pool + sector lookup ONCE at page render — both are
    # cheap and don't need to re-run on the per-fragment tick.
    with st.spinner("Loading universe…"):
        pool = _top_movers_pool()
        sector_lookup = _build_movers_sector_lookup()
    if not pool:
        st.warning(
            "Universe pool is empty. Check that the sector universe "
            "modules import correctly."
        )
        return

    tab_main, tab_early = st.tabs(
        ["Main pre-market (7:00 – 9:30 AM)",
         "Early pre-market (4:00 – 7:00 AM)"]
    )
    with tab_main:
        _top_movers_fragment(
            pool=pool,
            sector_lookup=sector_lookup,
            which="main",
            window_label="Window 7:00 – 9:29 AM ET",
        )
    with tab_early:
        _top_movers_fragment(
            pool=pool,
            sector_lookup=sector_lookup,
            which="early",
            window_label="Window 4:00 – 6:59 AM ET",
        )


# =============================================================================
# Penny Watchlist — standalone view (sub-$1 universe)
# =============================================================================

def render_penny_watchlist() -> None:
    with st.spinner("Loading penny candidates…"):
        rows = fetch_penny_candidates()

    _page_header(
        "Penny Watchlist",
        "Penny Watchlist",
        f"Sub-$1 universe &middot; float &lt; 20M &middot; candidates: {len(rows):,}",
    )

    if not rows:
        st.info("No sub-$1 tickers currently pass the filter (price $0.001–$0.999, float < 20M).")
        return

    df = quotes_to_df(rows, info={})
    st.markdown(style_table(df).to_html(), unsafe_allow_html=True)


# =============================================================================
# Stan — Research AI Employee (market theme scanner)
# =============================================================================
_THEME_COLORS = ["#64b5f6", "#22c55e", "#facc15", "#f97316", "#a78bfa"]


def render_stan_research() -> None:
    _page_header(
        "Stan / Research",
        "Market Themes",
        "Stan scans the universe for emerging themes by clustering today\u2019s "
        "catalysts and sector momentum. Each theme card shows the catalyst "
        "type, supporting tickers, and top headlines.",
    )

    with st.spinner("Stan is scanning for market themes…"):
        pool = _top_movers_pool()
        sector_lookup = _build_movers_sector_lookup()
        research = stan_module.compile_research(pool, sector_lookup)

    themes = research.get("themes") or []
    sector_perf = research.get("sector_perf") or []
    gen_at = research.get("generated_at")
    scanned = research.get("tickers_scanned", 0)

    ts_str = gen_at.strftime("%H:%M:%S") if gen_at else "—"
    st.markdown(
        f"<div style='font-size:0.72rem;color:{WHITE_MUTE};"
        f"margin-bottom:14px;'>Generated at {ts_str} &middot; "
        f"{scanned:,} tickers in universe</div>",
        unsafe_allow_html=True,
    )

    # Sector performance bar
    if sector_perf:
        perf_items = []
        for sp in sorted(sector_perf, key=lambda x: -x.get("change_pct", 0)):
            chg = sp.get("change_pct", 0)
            color = GOOD if chg > 0 else (DANGER if chg < 0 else WHITE_MUTE)
            sign = "+" if chg > 0 else ""
            perf_items.append(
                f"<span style='margin-right:16px;white-space:nowrap;'>"
                f"<span class='text-sm text-dim'>"
                f"{sp.get('sector', '')}</span> "
                f"<span class='text-sm text-bold' style='color:{color};'>"
                f"{sign}{chg:.1f}%</span></span>"
            )
        st.markdown(
            f"<div class='sierra-card' style='overflow-x:auto;"
            f"white-space:nowrap;margin-bottom:18px;'>"
            f"<div class='text-xs text-mute text-upper'"
            f" style='margin-bottom:6px;'>Sector Performance</div>"
            f"{''.join(perf_items)}</div>",
            unsafe_allow_html=True,
        )

    if not themes:
        st.info(
            "No strong themes detected right now. Stan needs active "
            "market hours with catalysts firing across multiple tickers "
            "in the same sector to cluster a theme. Check back during "
            "pre-market or the trading session."
        )
        return

    # Theme cards
    for i, theme in enumerate(themes):
        color = _THEME_COLORS[i % len(_THEME_COLORS)]
        ticker_links = " ".join(
            f"<a href='?ticker={t}' target='_self' "
            f"class='sierra-link' style='margin-right:8px;"
            f"font-size:0.82rem;'>{t}</a>"
            for t in theme.tickers
        )
        headlines_html = ""
        if theme.headlines:
            items = "".join(
                f"<li class='text-sm text-dim'"
                f" style='margin-bottom:3px;'>{h}</li>"
                for h in theme.headlines[:4]
            )
            headlines_html = (
                f"<ul style='margin:8px 0 0;padding-left:18px;'>"
                f"{items}</ul>"
            )

        catalyst_badge = _badge(
            theme.catalyst_type,
            CATALYST_TYPE_COLOR.get(theme.catalyst_type, WHITE_MUTE),
        )

        st.markdown(
            f"""<div class='sierra-card theme'
              style='border-left:4px solid {color};'>
              <div class='sierra-flex-row spread'
                style='margin-bottom:6px;'>
                <span class='text-lg text-bold text-white'>
                  #{theme.rank} {theme.name}</span>
                <span style='margin-left:10px;'>{catalyst_badge}</span>
              </div>
              <div class='text-md text-dim'
                style='margin-bottom:8px;'>{theme.description}</div>
              <div style='margin-bottom:4px;'>
                <span class='text-xs text-mute text-upper'>
                  Tickers:</span> {ticker_links}
              </div>
              {headlines_html}
            </div>""",
            unsafe_allow_html=True,
        )


# =============================================================================
# IPO calendar
# =============================================================================
SECTOR_BADGE_COLOR = {
    "Biotechnology": "#ef4444",
    "Technology":    "#64b5f6",
    "Energy":        "#f97316",
    "Other":         "#94a3b8",
}
STATUS_COLOR = {
    "Upcoming": "#facc15",
    "Priced":   "#22c55e",
    "Filed":    "#94a3b8",
}


def _format_ipo_date(raw: str | None) -> str:
    if not raw:
        return "TBD"
    try:
        from datetime import datetime as _dt
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                return _dt.strptime(raw, fmt).strftime("%b %d, %Y")
            except ValueError:
                continue
    except Exception:
        pass
    return raw


def _ipo_row(ipo: IPO) -> str:
    status_col = STATUS_COLOR.get(ipo.status, WHITE_MUTE)
    deal = f"${ipo.deal_size/1e6:.1f}M" if ipo.deal_size else "—"
    shares = tv_num(ipo.shares) if ipo.shares else "—"
    date_str = _format_ipo_date(ipo.expected_date)
    exch = ipo.exchange or "—"
    return (
        f"<tr>"
        f"<td class='sierra-td wide-pad text-bold'>{ipo.ticker}</td>"
        f"<td class='sierra-td wide-pad text-dim'>{ipo.company}</td>"
        f"<td class='sierra-td wide-pad text-right' style='font-weight:600;'>{ipo.price_display}</td>"
        f"<td class='sierra-td wide-pad' style='font-weight:500;'>{date_str}</td>"
        f"<td class='sierra-td wide-pad text-dim text-right'>{shares}</td>"
        f"<td class='sierra-td wide-pad text-dim text-right'>{deal}</td>"
        f"<td class='sierra-td wide-pad text-mute'>{exch}</td>"
        f"<td class='sierra-td wide-pad'>{_badge(ipo.status, status_col, 'lg')}</td>"
        f"</tr>"
    )


def _ipo_section(sector: str, rows: list[IPO]) -> None:
    badge = SECTOR_BADGE_COLOR.get(sector, ACCENT)
    st.markdown(
        f"""<div style="display:flex;align-items:baseline;gap:10px;
            margin:22px 0 10px;">
          {_badge(sector, badge, "lg")}
          <span class="text-mute text-sm">{len(rows)} IPO(s)</span>
        </div>""",
        unsafe_allow_html=True,
    )
    if not rows:
        st.markdown(
            f"<div style='color:{WHITE_MUTE};font-size:0.85rem;"
            f"padding:8px 0;'>No upcoming IPOs in this sector currently "
            "have a proposed price between $1 and $20.</div>",
            unsafe_allow_html=True,
        )
        return

    thead = _table_head([
        ("Ticker", "left"), ("Company", "left"), ("Price", "right"),
        ("Expected Date", "left"), ("Shares", "right"), ("Deal Size", "right"),
        ("Exch", "left"), ("Status", "left"),
    ], wide=True)
    body = "".join(_ipo_row(r) for r in rows)
    st.markdown(
        f"""<table class="sierra-table">
          {thead}
          <tbody>{body}</tbody>
        </table>""",
        unsafe_allow_html=True,
    )


# =============================================================================
# Backtesting — 6-month archive of ≥50% pre-market moves
# =============================================================================
def render_backtesting() -> None:
    from backtest_archive import (
        list_moves, stats as bt_stats, MIN_MOVE_PCT, LOOKBACK_DAYS,
    )

    _page_header(
        "Backtesting",
        "\u2265100% Pre-Market Moves",
        "Every ticker-day in the past six months \u2014 across the full "
        "US-listed universe \u2014 where the pre-market window "
        "(4:00\u20139:29 AM ET) doubled or better from PM low to PM high. "
        "Sorted most-recent first. Click any ticker to open the "
        "catalysts dialog.",
    )

    s = bt_stats()
    moves = list_moves(min_pct=MIN_MOVE_PCT, lookback_days=LOOKBACK_DAYS)

    # Build a per-ticker sector lookup so the table can carry GICS info.
    sector_lookup: dict[str, tuple[str, str]] = {}
    try:
        from screener import fetch_nasdaq_universe, classify_ticker_sector
        for nrow in fetch_nasdaq_universe():
            sym = (nrow.get("symbol") or "").strip().upper()
            if not sym:
                continue
            cls = classify_ticker_sector(nrow)
            if cls is None:
                continue
            sector_lookup[sym] = cls
    except Exception:
        pass

    universe = s.get("universe_size", 0)
    to_scan = s.get("to_scan", 0) or universe
    done = s.get("processed", 0)
    pct = (done / to_scan * 100) if to_scan else 0
    in_prog = s.get("in_progress")
    status_color = ACCENT if in_prog else GOOD
    status_label = "RUNNING" if in_prog else "IDLE"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _stat_card("Status", status_label, status_color)
    with c2:
        _stat_card("Moves Logged", f"{len(moves):,}", WHITE)
    with c3:
        _stat_card("Tickers w/ 100%+", f"{s.get('tickers_with_moves', 0):,}", ACCENT)
    with c4:
        _stat_card("Reviewed", f"{s.get('reviewed_moves', 0):,}", WHITE_DIM)
    st.markdown(
        f"""<div class='sierra-flex-row' style='margin:10px 0 18px;font-size:0.78rem;'>
          <span class='text-mute'>Coverage: {s.get('earliest_date') or '\u2014'} \u2192 {s.get('latest_date') or '\u2014'}</span>
          <span class='text-mute'>Scanned: {done:,} / {to_scan:,} ({pct:.0f}%)</span>
          <span class='text-mute'>Last run: {s.get('last_run_ts') or '\u2014'}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    if not moves:
        if in_prog:
            st.info(
                f"Backtest archive is being built right now — "
                f"{done:,} of {to_scan:,} tickers checked so far. "
                "Refresh in a few minutes; rows appear as the worker "
                "finds them."
            )
        else:
            st.info(
                "Backtest archive is empty. The background worker fires on "
                "every app startup — restart the Streamlit process if you "
                "don't see RUNNING above. Watch the terminal for "
                "`[backtest-bg]` log lines."
            )
        return

    thead = _table_head([
        ("Date",      "left"),
        ("Ticker",    "left"),
        ("Sector",    "left"),
        ("PM Low",    "right"),
        ("PM High",   "right"),
        ("PM Move",   "right"),
        ("Type",      "left"),
        ("Catalyst",  "left"),
        ("Source",    "center"),
    ])

    body_rows = []
    for r in moves:
        sym = r.get("ticker", "")
        date_str = r.get("date", "")
        pm_low = r.get("pm_low")
        pm_high = r.get("pm_high")
        pm_low_time = r.get("pm_low_time") or ""
        pm_high_time = r.get("pm_high_time") or ""
        upside = float(r.get("upside_pct") or 0)
        reviewed = bool(r.get("reviewed", False))
        # Re-tiered for the 100%+ floor: bright green ≥300, green ≥200,
        # yellow ≥150, accent at the 100-149 base tier.
        if upside >= 300:
            move_color = "#22c55e"
        elif upside >= 200:
            move_color = GOOD
        elif upside >= 150:
            move_color = WARN
        else:
            move_color = ACCENT

        ticker_html = _ticker_link(sym)

        sec_cls = sector_lookup.get(sym)
        if sec_cls:
            sec, sub = sec_cls
            sub_label = _human_sub_label(sec, sub)
            sector_html = (
                f"<div class='text-bold' style='font-size:0.8rem;"
                f"line-height:1.25;color:{WHITE};'>{sec}</div>"
                f"<div class='text-mute text-xs' "
                f"style='line-height:1.25;'>{sub_label}</div>"
            )
        else:
            sector_html = "<span class='text-mute'>\u2014</span>"

        pm_low_cell = (
            f"<div class='text-dim' style='font-weight:500;'>"
            f"${pm_low:.2f}</div>"
            + (f"<div class='text-mute text-xs'>{pm_low_time}</div>"
               if pm_low_time else "")
        ) if pm_low else "<span class='text-mute'>\u2014</span>"

        pm_high_cell = (
            f"<div class='text-bold' style='color:{WHITE};'>${pm_high:.2f}</div>"
            + (f"<div class='text-mute text-xs'>{pm_high_time}</div>"
               if pm_high_time else "")
        ) if pm_high else "<span class='text-mute'>\u2014</span>"

        type_label = r.get("type") or "\u2014"
        type_col = CATALYST_TYPE_COLOR.get(type_label, WHITE_MUTE)
        type_badge = _badge(type_label, type_col)

        title = r.get("title") or ""
        catalyst_text = title if title else "<span class='text-mute'>\u2014</span>"

        src = r.get("source") or "\u2014"
        link = r.get("link") or ""
        if link and src != "\u2014":
            source_link_html = (
                f"<a href='{link}' target='_blank' "
                f"class='sierra-link-ext'>{src} \u2197</a>"
            )
        else:
            source_link_html = (
                f"<span class='text-mute text-sm'>{src}</span>"
            )

        # Clickable reviewed-toggle next to the source. Filled green
        # check when reviewed, empty box otherwise. Navigates to
        # ?toggle_reviewed=TICKER:DATE which the main() handler
        # consumes and persists.
        toggle_url = f"?toggle_reviewed={sym}:{date_str}"
        if reviewed:
            check_html = (
                f"<a href='{toggle_url}' target='_self' "
                f"title='Reviewed — click to unmark' "
                f"style='display:inline-block;margin-right:6px;"
                f"font-size:0.95rem;color:{GOOD};text-decoration:none;"
                f"font-weight:700;'>✓</a>"
            )
        else:
            check_html = (
                f"<a href='{toggle_url}' target='_self' "
                f"title='Click after reviewing' "
                f"style='display:inline-block;margin-right:6px;"
                f"font-size:0.95rem;color:{WHITE_MUTE};text-decoration:none;'>☐</a>"
            )
        source_html = check_html + source_link_html

        row_opacity = "style='opacity:0.55;'" if reviewed else ""
        body_rows.append(
            f"<tr {row_opacity}>"
            f"<td class='sierra-td nowrap' style='color:{WHITE};"
            f"font-weight:500;'>{date_str}</td>"
            f"<td class='sierra-td'>{ticker_html}</td>"
            f"<td class='sierra-td'>{sector_html}</td>"
            f"<td class='sierra-td text-right'>{pm_low_cell}</td>"
            f"<td class='sierra-td text-right'>{pm_high_cell}</td>"
            f"<td class='sierra-td text-right text-bold' style='color:{move_color};'>"
            f"+{upside:.1f}%</td>"
            f"<td class='sierra-td'>{type_badge}</td>"
            f"<td class='sierra-td narrow'>{catalyst_text}</td>"
            f"<td class='sierra-td text-center nowrap'>{source_html}</td>"
            f"</tr>"
        )

    st.markdown(
        f"<table class='sierra-table'>"
        f"{thead}"
        f"<tbody>{''.join(body_rows)}</tbody></table>",
        unsafe_allow_html=True,
    )


def render_ipo_calendar() -> None:
    if "ipo_tab" not in st.session_state:
        st.session_state.ipo_tab = "upcoming"

    _page_header("IPO Calendar", "IPO Calendar")

    # Tab buttons
    tabs = [("upcoming", "Upcoming"), ("priced", "Recently Priced")]
    cols = st.columns([1, 1, 4])
    for (key, label), col in zip(tabs, cols[:2]):
        with col:
            is_active = st.session_state.ipo_tab == key
            if st.button(
                label,
                key=f"ipo_tab_{key}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.ipo_tab = key
                st.rerun()

    st.markdown("<div class='sierra-spacer sm'></div>", unsafe_allow_html=True)

    with st.spinner("Loading IPO calendar…"):
        by_sector = fetch_ipo_calendar(min_price=MIN_PRICE, max_price=MAX_PRICE)

    target_status = "Upcoming" if st.session_state.ipo_tab == "upcoming" else "Priced"
    filtered: dict[str, list[IPO]] = {
        sec: [r for r in rows if r.status == target_status]
        for sec, rows in by_sector.items()
    }
    total = sum(len(rows) for rows in filtered.values())

    if total == 0:
        if target_status == "Upcoming":
            st.info(
                "No IPOs with a scheduled price date are currently in the "
                f"${MIN_PRICE:.0f}–${MAX_PRICE:.0f} range. Check the "
                "Recently Priced tab for IPOs that completed this month."
            )
        else:
            st.info(
                f"No IPOs were priced this month in the "
                f"${MIN_PRICE:.0f}–${MAX_PRICE:.0f} range."
            )
        return

    for sec in ("Biotechnology", "Technology", "Energy", "Other"):
        _ipo_section(sec, filtered.get(sec, []))


# =============================================================================
# Backtest archive background worker
# =============================================================================
# Scans every valid US-listed ticker for ≥100% pre-market moves
# (PM High vs PM Low, 4:00–9:29 AM ET) and persists each to
# .pm_backtest_cache.json. No live-screen price filter — historical
# coverage includes tickers above $20 today. yfinance caps 5-minute
# intraday history at ~60 days, so the archive accumulates over
# time until it covers a true rolling six-month window.
# =============================================================================
_BACKTEST_BG_LOCK = _threading.Lock()
_BACKTEST_BG_STARTED = False


def _kickoff_backtest_archive_worker() -> None:
    global _BACKTEST_BG_STARTED
    with _BACKTEST_BG_LOCK:
        if _BACKTEST_BG_STARTED:
            return
        _BACKTEST_BG_STARTED = True

    def _worker() -> None:
        """Scan every valid US-listed ticker for ≥100% PM moves.

        Previously this had a 'Pass 1' daily-bar pre-filter that
        rejected tickers whose daily High/Low never crossed 2× in
        6 months. That was WRONG — yfinance daily bars exclude
        pre-market data, so any ticker whose 100% move happened
        *only* in the 4-9:29 AM window got incorrectly rejected.

        Fix: run the precise 5-minute PM-window scan
        (fetch_premarket_catalysts) on every candidate, parallelized
        across 16 worker threads. Slower than the broken pre-filter
        but catches the real cases.

        Every scanned ticker gets a scanned_ts on disk even when no
        moves match, so subsequent restarts skip via is_stale gating.
        """
        try:
            import sys
            import time as _time
            from concurrent.futures import ThreadPoolExecutor
            from data import fetch_premarket_catalysts
            from screener import fetch_nasdaq_universe
            from backtest_archive import (
                record_moves, is_stale, update_meta, MIN_MOVE_PCT,
            )

            SCAN_WORKERS = 16
            STALE_HOURS  = 24

            def _log(msg: str) -> None:
                print(f"[backtest-bg] {msg}", file=sys.stderr, flush=True)

            # ----- Collect candidate symbols (every valid US ticker) -
            raw = fetch_nasdaq_universe()
            all_valid: list[str] = []
            candidates: list[str] = []
            for r in raw:
                sym = (r.get("symbol") or "").strip().upper()
                if not sym or any(c in sym for c in ".^$/"):
                    continue
                all_valid.append(sym)
                if not is_stale(sym, max_age_hours=STALE_HOURS):
                    continue
                candidates.append(sym)
            _log(f"universe size: {len(all_valid)} valid tickers; "
                 f"{len(candidates)} to scan this run "
                 f"({len(all_valid) - len(candidates)} already fresh)")
            if not candidates:
                update_meta(
                    universe_size=len(all_valid),
                    processed=len(all_valid),
                    in_progress=False,
                )
                return
            update_meta(
                universe_size=len(all_valid),
                to_scan=len(candidates),
                processed=0,
                in_progress=True,
                last_run_ts=_time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", _time.gmtime()
                ),
            )

            # ----- Single pass: precise PM-window scan in parallel ---
            def _scan_one(sym: str) -> tuple[str, int]:
                try:
                    moves = fetch_premarket_catalysts(
                        sym,
                        min_price=0.01,
                        max_price=1_000_000.0,
                        min_upside_pct=MIN_MOVE_PCT,
                        lookback_days=60,
                    )
                except Exception:
                    moves = []
                # Always touch the archive (even for empty results)
                # so is_stale skips this ticker on next run.
                try:
                    n = record_moves(sym, moves or [])
                except Exception:
                    n = 0
                return sym, n

            done = 0
            with_moves = 0
            _log(f"scan starting on {len(candidates)} tickers "
                 f"with {SCAN_WORKERS} workers")
            with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as pool:
                for sym, n in pool.map(_scan_one, candidates):
                    done += 1
                    if n > 0:
                        with_moves += 1
                    if done % 50 == 0 or done == len(candidates):
                        _log(f"progress: {done}/{len(candidates)} "
                             f"({with_moves} tickers w/ ≥100% moves)")
                        update_meta(processed=done, with_moves=with_moves)
            update_meta(processed=done, with_moves=with_moves,
                        in_progress=False)
            _log(f"finished: {done}/{len(candidates)} scanned, "
                 f"{with_moves} tickers contributed moves")
        except Exception as e:
            import sys
            print(f"[backtest-bg] failed: {e}", file=sys.stderr, flush=True)
            try:
                from backtest_archive import update_meta as _um
                _um(in_progress=False)
            except Exception:
                pass

    t = _threading.Thread(target=_worker, daemon=True, name="backtest-bg")
    t.start()


# =============================================================================
# Main
# =============================================================================
def main() -> None:
    st.set_page_config(
        page_title="Sierra Trading",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()

    # Backtest archive worker — scans tickers for ≥50% PM moves and
    # writes them to .pm_backtest_cache.json. Capped at 200 tickers per
    # process run; resumes via is_stale gating on next start.
    _kickoff_backtest_archive_worker()

    if "selected_ticker" not in st.session_state:
        st.session_state.selected_ticker = None
    if "view" not in st.session_state:
        st.session_state.view = "sector"

    # Daily auto-refresh: clear all TTL caches on the first script run of
    # each ET trading day so a left-open browser tab pulls fresh data
    # automatically (no manual refresh needed).
    try:
        et = ZoneInfo("America/New_York") if ZoneInfo else timezone(timedelta(hours=-5))
        today_et = datetime.now(et).date()
    except Exception:
        today_et = datetime.utcnow().date()
    if st.session_state.get("last_data_date") != today_et:
        st.cache_data.clear()
        st.session_state.last_data_date = today_et

    # Ticker click -> ?ticker=XXX. Capture, set session state, then clear
    # the URL so refreshing or closing the dialog doesn't re-open it.
    qp_ticker = st.query_params.get("ticker")
    if qp_ticker:
        st.session_state.selected_ticker = qp_ticker.strip().upper()
        st.query_params.clear()

    # Backtesting reviewed-toggle: ?toggle_reviewed=TICKER:YYYY-MM-DD
    qp_toggle = st.query_params.get("toggle_reviewed")
    if qp_toggle:
        try:
            from backtest_archive import _load, mark_reviewed
            parts = qp_toggle.split(":", 1)
            if len(parts) == 2:
                tkr, dt = parts[0].strip().upper(), parts[1].strip()
                cache = _load()
                key = f"{tkr}:{dt}"
                currently = bool((cache.get("reviewed") or {}).get(key))
                mark_reviewed(tkr, dt, not currently)
        except Exception:
            pass
        st.query_params.clear()
        st.session_state.view = "backtesting"
        st.rerun()

    # Open the catalyst dialog FIRST (before any sector loading) so the
    # popup appears immediately on ticker click. Single-shot consume:
    # subsequent reruns see None and let Streamlit dismiss the dialog.
    pending_dialog = st.session_state.selected_ticker
    if pending_dialog:
        st.session_state.selected_ticker = None
        catalyst_dialog(pending_dialog)

    # Changelog dialog (single-shot consume to mirror catalyst pattern)
    if st.session_state.get("show_changelog"):
        st.session_state.show_changelog = False
        changelog_dialog()

    # Top-of-dashboard ticker-lookup search bar.
    sc1, sc2 = st.columns([6, 1])
    with sc1:
        search_q = st.text_input(
            "Ticker lookup",
            key="ticker_search",
            label_visibility="collapsed",
            placeholder="🔎 Search any ticker — e.g. ODYS, AAPL, NVDA",
        )
    with sc2:
        do_search = st.button("Look up", use_container_width=True)
    if do_search and search_q.strip():
        tkr = search_q.strip().upper()
        import re as _re
        if _re.fullmatch(r"[A-Z0-9.\-]{1,8}", tkr):
            st.session_state.selected_ticker = tkr
            st.rerun()

    def _reset_view() -> None:
        st.session_state.view = "sector"

    category_keys = sorted(SECTORS.keys()) + ["Trading Journal"]

    with st.sidebar:
        st.markdown(
            "<div class='sierra-brand'>Sierra Trading</div>",
            unsafe_allow_html=True,
        )

        main_cat = st.selectbox(
            label="Category",
            options=category_keys,
            label_visibility="collapsed",
            key="main_cat",
            on_change=_reset_view,
        )

        is_journal = main_cat == "Trading Journal"
        selected_folder = selected_label = None

        if not is_journal:
            branches = SECTORS[main_cat]
            branch_labels = [v[0] for v in branches.values()]
            selected_label = st.radio(
                "Sub-sector",
                options=branch_labels,
                label_visibility="collapsed",
                key=f"sub_{main_cat}",
                on_change=_reset_view,
            )
            selected_folder = next(
                k for k, (l, _, _) in branches.items() if l == selected_label
            )

            st.markdown("<div class='sierra-nav-section'>Tools</div>", unsafe_allow_html=True)
            st.markdown("<div class='sierra-icon-nav'>", unsafe_allow_html=True)
            if st.button(
                "Top Moves",
                use_container_width=True,
                key="top_movers_btn",
                icon=":material/trending_up:",
                type="primary" if st.session_state.view == "movers" else "secondary",
            ):
                st.session_state.view = "movers"
                st.rerun()

            if st.button(
                "Penny Watchlist",
                use_container_width=True,
                key="penny_btn",
                icon=":material/savings:",
                type="primary" if st.session_state.view == "penny" else "secondary",
            ):
                st.session_state.view = "penny"
                st.rerun()

            if st.button(
                "IPO Calendar",
                use_container_width=True,
                key="ipo_calendar_btn",
                icon=":material/calendar_month:",
                type="primary" if st.session_state.view == "ipo" else "secondary",
            ):
                st.session_state.view = "ipo"
                st.rerun()

            if st.button(
                "Backtesting",
                use_container_width=True,
                key="backtesting_btn",
                icon=":material/history:",
                type="primary" if st.session_state.view == "backtesting" else "secondary",
                help="Full US universe — historical 100%+ pre-market moves, past 6 months",
            ):
                st.session_state.view = "backtesting"
                st.rerun()

            if st.button(
                "Changelog",
                use_container_width=True,
                key="changelog_btn",
                icon=":material/description:",
            ):
                st.session_state.show_changelog = True
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<div class='sierra-nav-section'>Extensions</div>", unsafe_allow_html=True)
            st.markdown("<div class='sierra-icon-nav'>", unsafe_allow_html=True)
            if st.button(
                "Stan (Research)",
                use_container_width=True,
                key="stan_btn",
                icon=":material/smart_toy:",
                type="primary" if st.session_state.view == "stan" else "secondary",
            ):
                st.session_state.view = "stan"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    if is_journal:
        render_journal()
        return

    if st.session_state.view == "movers":
        render_top_movers()
        return

    if st.session_state.view == "penny":
        render_penny_watchlist()
        return

    if st.session_state.view == "stan":
        render_stan_research()
        return

    if st.session_state.view == "ipo":
        render_ipo_calendar()
        return

    if st.session_state.view in ("backtesting", "replay"):
        render_backtesting()
        return

    uni_mod = {
        "Technology":             tech_universe,
        "Communication Services": comm_services_universe,
        "Consumer Discretionary": consumer_disc_universe,
        "Consumer Staples":       consumer_staples_universe,
        "Health Care":            healthcare_universe,
        "Financials":             financials_universe,
        "Industrials":            industrials_universe,
        "Energy":                 energy_universe,
        "Materials":              materials_universe,
        "Utilities":              utilities_universe,
        "Real Estate":            real_estate_universe,
    }[main_cat]

    _page_header(f"{main_cat} / {selected_label}", "Sierra Trading")

    by_cat = filtered_by_category(uni_mod.UNIVERSE(), uni_mod.all_tickers())

    # Snapshot the qualifying tickers for this sector so the sidebar
    # changelog can report adds/drops between loads.
    try:
        all_quotes: list[Quote] = []
        seen: set[str] = set()
        for syms in by_cat.values():
            for q in syms:
                if q.ticker in seen:
                    continue
                seen.add(q.ticker)
                all_quotes.append(q)
        record_snapshot(main_cat, all_quotes)
    except Exception:
        pass

    render_sector(main_cat, selected_folder, by_cat.get(selected_folder, []), uni_mod.INFO)


if __name__ == "__main__":
    main()
