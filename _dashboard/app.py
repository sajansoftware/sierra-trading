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
    fetch_premarket_catalysts,
    fetch_top_movers,
    filtered_by_category,
    short_blurb,
    tv_num,
)
from changelog import record_snapshot, recent_events
from sentiment_intel import sector_sentiment_snapshot, briefing_lines
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
from aidan import audit_rows, QASuggestion
import mia as mia_module
import tradervue

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
        .stSpinner > div {{ border-top-color: {ACCENT} !important; }}
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
        </style>""",
        unsafe_allow_html=True,
    )


# =============================================================================
# Helpers
# =============================================================================
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
        ticker_link = (
            f"<a href='?ticker={q.ticker}' target='_self' "
            f"style='color:{WHITE};font-weight:700;text-decoration:none;"
            f"border-bottom:1px dotted {ACCENT};'>{q.ticker}</a>"
        )
        out.append({
            "Ticker":      ticker_link,
            "Close":       q.close,
            "Float":       q.float_shares,
            "Mkt Cap":     q.market_cap,
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


def style_table(df: pd.DataFrame):
    if df.empty:
        return df
    s = df.style.format({
        "Ticker":  lambda v: v,                      # already HTML anchor
        "Close":   lambda v: f"${v:.2f}" if pd.notna(v) else "—",
        "Float":   tv_num,
        "Mkt Cap": tv_num,
    }, escape=None)
    s = s.map(_float_bg, subset=["Float"])
    s = s.map(_price_color, subset=["Close"])
    s = s.set_properties(subset=["Ticker"], **{
        "font-weight": "700", "color": WHITE, "text-align": "left",
    })
    s = s.set_properties(**{"text-align": "right", "color": WHITE_DIM})
    s = s.set_properties(subset=["Ticker"], **{"text-align": "left"})
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
                     "th.col_heading.level0:nth-child(5)",
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
    with st.spinner("Loading pre-market catalysts…"):
        rows = fetch_premarket_catalysts(ticker)

    st.markdown(
        f"<div style='font-size:1.4rem;font-weight:700;color:{WHITE};"
        f"margin-bottom:4px;'>{ticker} — Pre-Market Catalysts</div>"
        f"<div style='font-size:0.78rem;color:{WHITE_MUTE};"
        f"margin-bottom:14px;'>Click any row to open {ticker} on "
        f"TradingView (5-min) at the PM-low timestamp.</div>",
        unsafe_allow_html=True,
    )

    if not rows:
        st.info("No pre-market catalyst days found for this ticker.")
        if st.button("Close", key="close_empty"):
            _close_dialog()
            st.rerun()
        return

    head_cells = "".join(
        f"<th style='padding:10px 12px;border-bottom:1px solid {BORDER};"
        f"background:{NAVY_CARD} !important;color:{WHITE};font-weight:600;"
        f"font-size:0.7rem;text-transform:uppercase;letter-spacing:0.5px;"
        f"text-align:{align};'>{h}</th>"
        for h, align in [
            ("Date","left"), ("PM Low","right"), ("PM High","right"),
            ("Upside","right"), ("Type","left"),
            ("Catalyst","left"), ("Source","center"),
        ]
    )

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
        type_badge = (
            f"<span style='background:{type_col};color:#06121e;"
            f"font-weight:700;font-size:0.7rem;padding:2px 8px;"
            f"border-radius:4px;white-space:nowrap;'>{type_label}</span>"
        )
        sent_label = r.get("sentiment") or "Neutral"
        sent_col = SENT_COLOR.get(sent_label, "#64748b")
        sent_badge = (
            f"<span style='background:{sent_col};color:#06121e;"
            f"font-weight:700;font-size:0.7rem;padding:2px 10px;"
            f"border-radius:4px;white-space:nowrap;'>{sent_label}</span>"
        )
        catalyst_text = (
            r["title"] if r["title"]
            else f"<span style='color:#64748b;'>—</span>"
        )
        # Source cell: primary source link + secondary source corroboration
        # OR an explicit Unverified badge when only one source is available.
        primary_source = r.get("source") or "—"
        secondary = r.get("secondary_source") or ""
        unverified = r.get("unverified", False)
        if r["link"] and primary_source != "—":
            primary_html = (
                f"<a href='{r['link']}' target='_blank' "
                f"style='color:{ACCENT};text-decoration:none;font-size:0.78rem;"
                f"white-space:nowrap;'>{primary_source} ↗</a>"
            )
        else:
            primary_html = (
                f"<span style='color:#64748b;font-size:0.78rem;'>"
                f"{primary_source}</span>"
            )
        if unverified:
            verify_html = (
                f"<div style='margin-top:2px;display:inline-block;"
                f"background:#f97316;color:#06121e;font-weight:700;"
                f"font-size:0.65rem;padding:1px 6px;border-radius:3px;"
                f"text-transform:uppercase;'>Unverified</div>"
            )
        elif secondary:
            verify_html = (
                f"<div style='margin-top:2px;color:{WHITE_MUTE};"
                f"font-size:0.7rem;'>+ {secondary}</div>"
            )
        else:
            verify_html = ""
        source_html = primary_html + verify_html

        up = r["upside_pct"]
        up_color = GOOD if up >= 50 else (WARN if up >= 30 else ACCENT)
        pm_low = r.get("pm_low")
        pm_low_time = r.get("pm_low_time") or ""
        pm_low_cell = (
            f"<div style='color:{WHITE_DIM};font-weight:500;'>${pm_low:.2f}</div>"
            + (f"<div style='color:{WHITE_MUTE};font-size:0.72rem;'>{pm_low_time}</div>"
               if pm_low_time else "")
            if pm_low is not None
            else f"<div style='color:#64748b;'>—</div>"
        )
        pm_high_cell = (
            f"<div style='color:{WHITE};font-weight:600;'>${r['pm_high']:.2f}</div>"
            f"<div style='color:{WHITE_MUTE};font-size:0.72rem;'>{r['pm_high_time']}</div>"
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
            f"title='{tv_tip}' "
            f"style='display:block;color:inherit;text-decoration:none;'>"
        )
        row_link_close = "</a>"
        body_rows.append(
            f"<tr class='sierra-clickable'>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"color:{WHITE};font-weight:500;white-space:nowrap;vertical-align:top;'>"
            f"{row_link_open}📈 {date_str}{row_link_close}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"text-align:right;vertical-align:top;'>{row_link_open}{pm_low_cell}{row_link_close}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"text-align:right;vertical-align:top;'>{row_link_open}{pm_high_cell}{row_link_close}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"color:{up_color};text-align:right;font-weight:700;vertical-align:top;'>"
            f"{row_link_open}<span style='color:{up_color};'>+{up:.1f}%</span>{row_link_close}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};vertical-align:top;'>{type_badge}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"color:{WHITE_DIM};font-size:0.85rem;max-width:340px;vertical-align:top;'>"
            f"{row_link_open}<span style='color:{WHITE_DIM};'>{catalyst_text}</span>{row_link_close}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"text-align:center;vertical-align:top;'>{source_html}</td>"
            f"</tr>"
        )

    st.markdown(
        f"""<table class='sierra-table'>
          <thead><tr>{head_cells}</tr></thead>
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
            f"<div style='color:{WHITE_DIM};font-size:0.9rem;"
            f"line-height:1.6;margin-bottom:14px;'>{para}</div>",
            unsafe_allow_html=True,
        )
    if areas:
        items = "".join(
            f"<li style='color:{WHITE};margin-bottom:4px;'>{a}</li>"
            for a in areas
        )
        st.markdown(
            f"<ul style='font-size:0.9rem;line-height:1.5;"
            f"padding-left:22px;margin:0 0 20px 0;'>{items}</ul>",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""<div style="margin-bottom:10px;">
          <span style="font-size:1.05rem;font-weight:600;color:{WHITE};">
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
        f"""<div style="background:{NAVY_CARD};border:1px solid {BORDER};
            border-radius:6px;padding:14px 16px;text-align:center;">
          <div style="font-size:0.72rem;color:{WHITE_MUTE};
              text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">
              {label}</div>
          <div style="font-size:1.35rem;font-weight:700;color:{color};">{value}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_journal() -> None:
    st.markdown(
        f"""<div style="margin-bottom:8px;">
          <span style="font-size:0.75rem;color:{WHITE_MUTE};
            text-transform:uppercase;letter-spacing:1px;">Trading Journal</span>
        </div>
        <div style="font-size:2rem;font-weight:700;color:{WHITE};
          letter-spacing:-0.5px;margin-bottom:20px;">Performance Dashboard</div>""",
        unsafe_allow_html=True,
    )

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

    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

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
        f"""<div style="margin-bottom:10px;">
          <div style="font-size:0.78rem;color:{WHITE_DIM};line-height:1.5;">
            Tracks tickers entering or exiting the screen
            (<b>${MIN_PRICE:.0f}–${MAX_PRICE:.0f}</b> &middot;
            <b>float &lt; 20M</b>). Updated each time a sector loads.
          </div>
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
            f"""<div style="display:flex;gap:14px;align-items:stretch;
                 background:{NAVY_CARD};border:1px solid {BORDER};
                 border-left:4px solid {accent_col};border-radius:8px;
                 padding:12px 14px;margin-bottom:10px;">
              <div style="flex:0 0 84px;">
                <div style="font-size:0.65rem;font-weight:700;
                  letter-spacing:1px;color:{accent_col};
                  background:{accent_bg};border-radius:4px;
                  padding:3px 6px;text-align:center;
                  margin-bottom:6px;">{glyph}</div>
                <div style="font-size:1.05rem;font-weight:700;
                  color:{WHITE};letter-spacing:-0.3px;">{sym}</div>
              </div>
              <div style="flex:1;min-width:0;">
                <div style="font-size:0.7rem;color:{WHITE_MUTE};
                  text-transform:uppercase;letter-spacing:0.5px;
                  margin-bottom:4px;">{sector} &middot; {ts}</div>
                <div style="font-size:0.88rem;color:{WHITE_DIM};
                  line-height:1.45;margin-bottom:4px;">{reason}</div>
                <div style="font-size:0.72rem;color:{WHITE_MUTE};">
                  {meta_str}</div>
              </div>
            </div>"""
        )

    st.markdown("".join(cards), unsafe_allow_html=True)


# =============================================================================
# Sentiment briefing card
# =============================================================================
def render_sentiment_briefing(snap) -> None:
    """Visible card with the desk's current sentiment read + patterns."""
    skew = snap.skew
    skew_col = {
        "Bullish": GOOD,
        "Bearish": DANGER,
        "Mixed":   WARN,
        "Thin":    WHITE_MUTE,
    }.get(skew, WHITE_MUTE)
    lines = briefing_lines(snap)
    bullets = "".join(
        f"<li style='margin:4px 0;color:{WHITE_DIM};'>{ln}</li>" for ln in lines
    ) if lines else (
        f"<li style='color:{WHITE_MUTE};font-style:italic;'>"
        f"Quiet tape — no notable patterns.</li>"
    )

    st.markdown(
        f"""<div style="background:{NAVY_CARD};border:1px solid {BORDER};
              border-left:4px solid {skew_col};border-radius:10px;
              padding:14px 18px;margin-bottom:18px;">
          <div style="display:flex;justify-content:space-between;
              align-items:center;margin-bottom:8px;">
            <div style="font-size:0.7rem;color:{WHITE_MUTE};
              text-transform:uppercase;letter-spacing:1px;">
              Sentiment briefing &middot; {snap.window_days}-day window</div>
            <div style="font-size:0.72rem;font-weight:700;color:{skew_col};
              text-transform:uppercase;letter-spacing:1px;">{skew} &middot;
              {snap.bull} bull / {snap.bear} bear / {snap.neutral} neut</div>
          </div>
          <ul style="margin:0;padding-left:18px;font-size:0.85rem;
            line-height:1.55;">{bullets}</ul>
        </div>""",
        unsafe_allow_html=True,
    )


# =============================================================================
# Today's top moves
# =============================================================================
def render_top_movers() -> None:
    st.markdown(
        f"""<div style="margin-bottom:8px;">
          <span style="font-size:0.75rem;color:{WHITE_MUTE};
            text-transform:uppercase;letter-spacing:1px;">Top Moves</span>
        </div>
        <div style="font-size:2rem;font-weight:700;color:{WHITE};
          letter-spacing:-0.5px;margin-bottom:18px;">Today's Top Moves</div>""",
        unsafe_allow_html=True,
    )

    # Pool of tickers = every ticker the dashboard knows about (curated +
    # screener-discovered) across all sectors.
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

    with st.spinner("Scanning today's tape…"):
        movers = fetch_top_movers(tuple(sorted(pool)))

    if not movers:
        st.info("No tickers in the universe moved ≥ 20% during pre-market today.")
        return

    head_cells = "".join(
        f"<th style='padding:10px 12px;border-bottom:1px solid {BORDER};"
        f"background:{NAVY_CARD} !important;color:{WHITE};font-weight:600;"
        f"font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;"
        f"text-align:{align};'>{h}</th>"
        for h, align in [
            ("Ticker","left"), ("PM Low","right"), ("PM High","right"),
            ("PM Move","right"), ("Type","left"),
            ("Catalyst","left"), ("Source","center"),
        ]
    )

    body_rows = []
    for r in movers:
        ticker_html = (
            f"<a href='?ticker={r['ticker']}' target='_self' "
            f"style='color:{WHITE};font-weight:700;text-decoration:none;"
            f"border-bottom:1px dotted {ACCENT};'>{r['ticker']}</a>"
        )
        type_label = r["news_type"]
        type_col = CATALYST_TYPE_COLOR.get(type_label, WHITE_MUTE)
        type_badge = (
            f"<span style='background:{type_col};color:#06121e;"
            f"font-weight:700;font-size:0.7rem;padding:2px 8px;"
            f"border-radius:4px;white-space:nowrap;'>{type_label}</span>"
        )
        catalyst_text = (
            r["news_title"] if r["news_title"]
            else f"<span style='color:#64748b;'>—</span>"
        )
        source_label = r.get("news_source") or "—"
        if r["news_link"] and source_label != "—":
            source_html = (
                f"<a href='{r['news_link']}' target='_blank' "
                f"style='color:{ACCENT};text-decoration:none;"
                f"font-size:0.78rem;white-space:nowrap;'>{source_label} ↗</a>"
            )
        else:
            source_html = (
                f"<span style='color:#64748b;font-size:0.78rem;'>"
                f"{source_label}</span>"
            )
        move = r["move_pct"]
        move_color = GOOD if move >= 50 else (WARN if move >= 30 else ACCENT)
        body_rows.append(
            f"<tr>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};'>{ticker_html}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"color:{WHITE_DIM};text-align:right;'>${r['lod']:.2f}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"color:{WHITE};text-align:right;font-weight:600;'>${r['hod']:.2f}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"color:{move_color};text-align:right;font-weight:700;'>+{move:.1f}%</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};'>{type_badge}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"color:{WHITE_DIM};font-size:0.85rem;max-width:340px;'>{catalyst_text}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"text-align:center;'>{source_html}</td>"
            f"</tr>"
        )

    st.markdown(
        f"""<table class='sierra-table'>
          <thead><tr>{head_cells}</tr></thead>
          <tbody>{''.join(body_rows)}</tbody>
        </table>""",
        unsafe_allow_html=True,
    )


# =============================================================================
# Gemini classification page
# =============================================================================
def render_gemini_classification() -> None:
    from gemini_classifier import (
        classify_batch, stats, is_configured, cached_classification,
    )
    st.markdown(
        f"""<div style="margin-bottom:8px;">
          <span style="font-size:0.75rem;color:{WHITE_MUTE};
            text-transform:uppercase;letter-spacing:1px;">AI Classification</span>
        </div>
        <div style="font-size:2rem;font-weight:700;color:{WHITE};
          letter-spacing:-0.5px;margin-bottom:6px;">Sector / Sub-Sector via Gemini</div>
        <div style="font-size:0.88rem;color:{WHITE_DIM};margin-bottom:22px;">
          Replaces keyword industry rules with a semantic LLM call.
          Results cache to disk forever — the dashboard then looks the
          ticker up locally on every load (no per-render API cost).</div>""",
        unsafe_allow_html=True,
    )

    s = stats()
    configured = s["configured"]
    total_cached = s["total_classified"]
    if not configured:
        st.warning(
            "GEMINI_API_KEY is not set. Add it to your environment or "
            "to `.streamlit/secrets.toml` to enable LLM classification. "
            "Until then the dashboard uses the keyword rule fallback."
        )

    # Snapshot cache stats
    st.markdown(
        f"""<div style="display:flex;gap:24px;margin-bottom:18px;">
          <span style="color:{WHITE};font-weight:600;">Cached: {total_cached}</span>
          <span style="color:{WHITE_DIM};">Sectors covered: {len(s['by_sector'])}</span>
          <span style="color:{WHITE_DIM};">Taxonomy hash: {s['taxonomy_hash'] or '—'}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    # Pull screener universe for the run
    from screener import fetch_nasdaq_universe, _parse_price
    raw = fetch_nasdaq_universe()
    candidates: list[dict] = []
    for r in raw:
        sym = (r.get("symbol") or "").strip().upper()
        if not sym or any(c in sym for c in ".^$/"):
            continue
        price = _parse_price(r.get("lastsale"))
        if price is None or not (MIN_PRICE <= price <= MAX_PRICE):
            continue
        candidates.append({
            "ticker":   sym,
            "name":     (r.get("name") or "").strip(),
            "sector":   (r.get("sector") or "").strip(),
            "industry": (r.get("industry") or "").strip(),
        })

    # Build the taxonomy from SECTORS so Gemini gets the exact options
    taxonomy = {sec: list(branches.keys()) for sec, branches in SECTORS.items()}
    uncached = [c for c in candidates if cached_classification(c["ticker"]) is None]
    st.caption(f"In $1–$20 universe: {len(candidates)} tickers · "
               f"unclassified: {len(uncached)}")

    n_default = 50 if len(uncached) > 50 else len(uncached)
    if n_default == 0:
        st.success("All in-screen tickers are already classified by Gemini.")
    else:
        n = st.slider("Tickers to classify this run",
                      min_value=10, max_value=min(500, len(uncached)),
                      value=min(50, len(uncached)),
                      step=10)
        if st.button("▶ Run Gemini classification",
                     type="primary",
                     disabled=not configured,
                     key="gemini_run_btn"):
            batch = uncached[:n]
            prog = st.progress(0, text="Starting…")
            def _on_progress(done, total, msg):
                pct = int(done / total * 100) if total else 100
                prog.progress(min(100, pct),
                              text=f"{done}/{total} · {msg}")
            out = classify_batch(batch, taxonomy, progress_cb=_on_progress)
            prog.empty()
            st.success(f"Classified {len(out)} new tickers via Gemini. "
                       "Reload any sector page to see them re-bucketed.")
            # Show what changed
            if out:
                rows = []
                for tkr, rec in list(out.items())[:30]:
                    rows.append(
                        f"<tr><td style='padding:6px 10px;color:{WHITE};'>{tkr}</td>"
                        f"<td style='padding:6px 10px;color:{WHITE_DIM};'>{rec['sector']}</td>"
                        f"<td style='padding:6px 10px;color:{WHITE_DIM};'>{rec['sub_sector']}</td>"
                        f"<td style='padding:6px 10px;color:{WHITE_MUTE};font-size:0.78rem;'>{rec.get('rationale','')}</td></tr>"
                    )
                st.markdown(
                    f"<table class='sierra-table' style='margin-top:14px;'>"
                    f"<thead><tr>"
                    f"<th style='padding:8px 10px;text-align:left;color:{WHITE_MUTE};'>Ticker</th>"
                    f"<th style='padding:8px 10px;text-align:left;color:{WHITE_MUTE};'>Sector</th>"
                    f"<th style='padding:8px 10px;text-align:left;color:{WHITE_MUTE};'>Sub-Sector</th>"
                    f"<th style='padding:8px 10px;text-align:left;color:{WHITE_MUTE};'>Rationale</th>"
                    f"</tr></thead><tbody>{''.join(rows)}</tbody></table>",
                    unsafe_allow_html=True,
                )

    # Coverage breakdown
    if s["by_sector"]:
        st.markdown(
            f"<div style='font-size:0.72rem;color:{WHITE_MUTE};"
            f"text-transform:uppercase;letter-spacing:1px;"
            f"margin:20px 0 8px;'>Coverage by sector</div>",
            unsafe_allow_html=True,
        )
        chips = []
        for sec, n in sorted(s["by_sector"].items(),
                              key=lambda kv: -kv[1]):
            chips.append(
                f"<div style='display:inline-block;margin:0 8px 8px 0;"
                f"padding:6px 10px;background:{NAVY_CARD};"
                f"border:1px solid {BORDER};border-radius:6px;'>"
                f"<span style='color:{WHITE};font-weight:600;'>{sec}</span> "
                f"<span style='color:{ACCENT};font-weight:700;'>{n}</span>"
                f"</div>"
            )
        st.markdown("".join(chips), unsafe_allow_html=True)


# =============================================================================
# Operations — catalyst-classifier QA agent
# =============================================================================
def render_operations() -> None:
    st.markdown(
        f"""<div style="margin-bottom:8px;">
          <span style="font-size:0.75rem;color:{WHITE_MUTE};
            text-transform:uppercase;letter-spacing:1px;">Operations</span>
        </div>
        <div style="font-size:2rem;font-weight:700;color:{WHITE};
          letter-spacing:-0.5px;margin-bottom:6px;">Classifier QA Audit</div>
        <div style="font-size:0.85rem;color:{WHITE_DIM};margin-bottom:18px;">
          Operations scans every passing ticker's catalyst headlines, finds
          rows still labeled 'Press Release' that contain biotech /
          corporate signal words, and proposes the catalyst type plus the
          keyword to add to the classifier.</div>""",
        unsafe_allow_html=True,
    )

    # Pool of tickers = every passing ticker across all sectors
    pool: set[str] = set()
    for mod in (bio_universe, tech_universe, energy_universe,
                industrials_universe, materials_universe,
                consumer_disc_universe, financials_universe,
                comm_services_universe, consumer_staples_universe,
                real_estate_universe, healthcare_svc_universe):
        try:
            pool.update(mod.all_tickers())
        except Exception:
            continue
    pool = sorted(pool)

    max_tickers = st.slider(
        "Tickers to scan (caps the audit so it finishes in reasonable time)",
        min_value=20, max_value=300, value=80, step=20,
    )
    pool = pool[:max_tickers]

    suggestions: list[QASuggestion] = []
    n_no_news = 0
    n_rows = 0
    with st.spinner(f"Operations auditing {len(pool)} tickers…"):
        for tkr in pool:
            try:
                rows = fetch_premarket_catalysts(tkr)
            except Exception:
                continue
            n_rows += len(rows)
            n_no_news += sum(1 for r in rows if r.get("type") in ("No news", "Press Release"))
            suggestions.extend(audit_rows(rows, tkr))

    # Summary
    cov_pct = 100 * (1 - n_no_news / n_rows) if n_rows else 0
    st.markdown(
        f"""<div style="display:flex;gap:24px;margin-bottom:18px;">
          <span style="color:{WHITE};font-weight:600;">Tickers scanned: {len(pool)}</span>
          <span style="color:{WHITE_DIM};">Catalyst rows: {n_rows}</span>
          <span style="color:{WHITE_DIM};">Unclassified rows: {n_no_news}</span>
          <span style="color:{GOOD};">Classifier coverage: {cov_pct:.1f}%</span>
          <span style="color:{WARN};">Operations suggestions: {len(suggestions)}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    if not suggestions:
        st.info(
            "No misclassified rows found in the scanned tickers. Bump the "
            "ticker count slider to audit more of the universe."
        )
        return

    # Group suggestions by proposed type
    by_type: dict[str, list[QASuggestion]] = {}
    for s in suggestions:
        by_type.setdefault(s.suggested_type, []).append(s)

    for stype in sorted(by_type.keys(), key=lambda k: -len(by_type[k])):
        items = by_type[stype]
        type_col = CATALYST_TYPE_COLOR.get(stype, WHITE_MUTE)
        st.markdown(
            f"""<div style="margin:18px 0 8px;display:flex;
              align-items:center;gap:10px;">
              <span style="background:{type_col};color:#06121e;
                font-weight:700;font-size:0.78rem;padding:3px 10px;
                border-radius:4px;">{stype}</span>
              <span style="color:{WHITE_MUTE};font-size:0.8rem;">
                {len(items)} headline(s) Operations would reclassify here</span>
            </div>""",
            unsafe_allow_html=True,
        )
        head_cells = "".join(
            f"<th style='padding:8px 12px;border-bottom:1px solid {BORDER};"
            f"background:{NAVY_CARD} !important;color:{WHITE};font-weight:600;"
            f"font-size:0.7rem;text-transform:uppercase;letter-spacing:0.5px;"
            f"text-align:{align};'>{h}</th>"
            for h, align in [
                ("Ticker","left"), ("Date","left"), ("Headline","left"),
                ("Matched phrase","left"), ("Source","center"),
            ]
        )
        body_rows = []
        for s in items[:30]:    # cap per group for readability
            body_rows.append(
                f"<tr>"
                f"<td style='padding:7px 12px;border-bottom:1px solid {BORDER};"
                f"color:{WHITE};font-weight:600;'>{s.ticker}</td>"
                f"<td style='padding:7px 12px;border-bottom:1px solid {BORDER};"
                f"color:{WHITE_DIM};font-size:0.82rem;white-space:nowrap;'>{s.date}</td>"
                f"<td style='padding:7px 12px;border-bottom:1px solid {BORDER};"
                f"color:{WHITE_DIM};font-size:0.82rem;max-width:520px;'>{s.headline}</td>"
                f"<td style='padding:7px 12px;border-bottom:1px solid {BORDER};"
                f"color:{ACCENT};font-size:0.78rem;font-style:italic;'>"
                f"\"{s.matched_phrase}\"</td>"
                f"<td style='padding:7px 12px;border-bottom:1px solid {BORDER};"
                f"color:{WHITE_MUTE};font-size:0.78rem;text-align:center;'>"
                f"{s.source}</td>"
                f"</tr>"
            )
        st.markdown(
            f"""<table class='sierra-table'>
              <thead><tr>{head_cells}</tr></thead>
              <tbody>{''.join(body_rows)}</tbody>
            </table>""",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""<div style="margin-top:24px;padding:14px 18px;
          background:{NAVY_CARD};border:1px solid {BORDER};
          border-radius:6px;">
          <div style="color:{WHITE};font-weight:600;margin-bottom:6px;">
            How to apply Operations' suggestions</div>
          <div style="color:{WHITE_DIM};font-size:0.85rem;line-height:1.5;">
            Open <code style="color:{ACCENT};">_dashboard/data.py</code>,
            find the <code style="color:{ACCENT};">CATALYST_KEYWORDS</code>
            list, and append each <em>matched phrase</em> above to its
            suggested type. Restart the dashboard - the previously
            unclassified rows reclassify on the next catalyst-dialog open.
          </div>
        </div>""",
        unsafe_allow_html=True,
    )


# =============================================================================
# Mia — Performance Coach (reads Trading Journal)
# =============================================================================
_SEV_COLOR = {"high": DANGER, "medium": WARN, "low": GOOD}


def render_mia_coach() -> None:
    st.markdown(
        f"""<div style="margin-bottom:8px;">
          <span style="font-size:0.75rem;color:{WHITE_MUTE};
            text-transform:uppercase;letter-spacing:1px;">Mia / Coach</span>
        </div>
        <div style="font-size:2rem;font-weight:700;color:{WHITE};
          letter-spacing:-0.5px;margin-bottom:6px;">Performance Review</div>
        <div style="font-size:0.85rem;color:{WHITE_DIM};margin-bottom:18px;">
          Mia reads your Trading Journal entries and surfaces leaks - where
          you're consistently losing money, what's actually working, and
          what to change next week.</div>""",
        unsafe_allow_html=True,
    )

    # ---- Trade source: Tradervue CSV upload OR local Trading Journal ----
    uploaded = st.file_uploader(
        "Upload your Tradervue CSV export (Account → Export → CSV)",
        type=["csv"], key="mia_tv_upload",
    )
    if uploaded is not None:
        try:
            parsed = tradervue.parse_tradervue_csv(uploaded.getvalue())
        except Exception as exc:
            st.error(f"Could not parse CSV: {exc}")
            parsed = []
        if parsed:
            st.session_state["mia_tv_trades"] = parsed
            st.success(f"Loaded {len(parsed)} trades from Tradervue CSV.")
        else:
            st.warning("CSV parsed but no usable rows found. "
                       "Check column headers in the export.")

    tv_trades = st.session_state.get("mia_tv_trades") or []
    local_trades = trading_journal.load_trades()

    if tv_trades and local_trades:
        src = st.radio(
            "Source",
            options=[f"Tradervue CSV ({len(tv_trades)} trades)",
                     f"Local Journal ({len(local_trades)} trades)"],
            horizontal=True, key="mia_source", label_visibility="collapsed",
        )
        trades = tv_trades if src.startswith("Tradervue") else local_trades
    elif tv_trades:
        trades = tv_trades
        st.caption(f"Analyzing {len(tv_trades)} Tradervue trades from the uploaded CSV.")
    else:
        trades = local_trades

    if tv_trades and st.button("Clear uploaded CSV", key="mia_tv_clear"):
        st.session_state.pop("mia_tv_trades", None)
        st.rerun()

    analysis = mia_module.analyze(trades)

    if analysis.get("empty"):
        st.info(
            "No trades to analyze yet. Either upload a Tradervue CSV "
            "(Account → Export → CSV) using the box above, or log "
            "trades in the Trading Journal sidebar option. Mia needs "
            "at least 8-10 trades to spot meaningful patterns."
        )
        return

    # ---- Top metrics ----
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
        _stat_card("Total P&L", f"{sign}${stats['total_pnl']:,.0f}", col)
    with c4:
        ratio = (analysis["avg_win"] / abs(analysis["avg_loss"])
                 if analysis["avg_win"] and analysis["avg_loss"] else 0)
        col = GOOD if ratio >= 1.5 else (WARN if ratio >= 1.0 else DANGER)
        _stat_card("Win:Loss $$", f"{ratio:.2f}:1", col)

    # ---- Leak callouts ----
    st.markdown(f"<div style='height:18px;'></div>", unsafe_allow_html=True)
    leaks = mia_module.find_leaks(analysis)
    st.markdown(
        f"<div style='font-size:1.15rem;font-weight:700;color:{WHITE};"
        f"margin:8px 0 12px;'>Mia's Observations ({len(leaks)})</div>",
        unsafe_allow_html=True,
    )
    if not leaks:
        st.info("No glaring leaks. Mia recommends keeping a tighter trade log "
                "(setup tags, notes) so she can spot subtler patterns.")
    for l in leaks:
        col = _SEV_COLOR.get(l.severity, WHITE_MUTE)
        st.markdown(
            f"""<div style='border-left:4px solid {col};
              background:{NAVY_CARD};border-radius:6px;
              padding:12px 16px;margin-bottom:10px;'>
              <div style='display:flex;justify-content:space-between;
                align-items:center;margin-bottom:4px;'>
                <span style='font-size:0.95rem;font-weight:700;
                  color:{WHITE};'>{l.title}</span>
                <span style='background:{col};color:#06121e;
                  font-weight:700;font-size:0.7rem;padding:2px 8px;
                  border-radius:4px;text-transform:uppercase;'>
                  {l.severity}</span>
              </div>
              <div style='color:{WHITE_DIM};font-size:0.85rem;
                margin-bottom:6px;'>{l.detail}</div>
              <div style='color:{WHITE_MUTE};font-size:0.82rem;
                line-height:1.4;'>
                <strong style='color:{ACCENT};'>Recommendation:</strong>
                {l.recommendation}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    # ---- Bucket tables ----
    def _render_bucket(title: str, buckets, label_header: str = "Bucket"):
        if not buckets:
            return
        st.markdown(
            f"<div style='font-size:1.05rem;font-weight:700;color:{WHITE};"
            f"margin:18px 0 8px;'>{title}</div>",
            unsafe_allow_html=True,
        )
        head_cells = "".join(
            f"<th style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"background:{NAVY_CARD} !important;color:{WHITE};font-weight:600;"
            f"font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;"
            f"text-align:{align};'>{h}</th>"
            for h, align in [
                (label_header, "left"), ("Trades", "right"),
                ("Win Rate", "right"), ("Total P&L", "right"),
                ("Avg P&L", "right"),
            ]
        )
        body_rows = []
        for s in buckets:
            wr_col = GOOD if s.win_rate >= 50 else DANGER
            pnl_col = GOOD if s.total_pnl >= 0 else DANGER
            avg_col = GOOD if s.avg_pnl >= 0 else DANGER
            body_rows.append(
                f"<tr>"
                f"<td style='padding:8px 12px;border-bottom:1px solid {BORDER};"
                f"color:{WHITE};font-weight:500;'>{s.label}</td>"
                f"<td style='padding:8px 12px;border-bottom:1px solid {BORDER};"
                f"color:{WHITE_DIM};text-align:right;'>{s.trades}</td>"
                f"<td style='padding:8px 12px;border-bottom:1px solid {BORDER};"
                f"color:{wr_col};text-align:right;font-weight:600;'>{s.win_rate:.0f}%</td>"
                f"<td style='padding:8px 12px;border-bottom:1px solid {BORDER};"
                f"color:{pnl_col};text-align:right;font-weight:600;'>${s.total_pnl:,.0f}</td>"
                f"<td style='padding:8px 12px;border-bottom:1px solid {BORDER};"
                f"color:{avg_col};text-align:right;'>${s.avg_pnl:+,.0f}</td>"
                f"</tr>"
            )
        st.markdown(
            f"""<table class='sierra-table'>
              <thead><tr>{head_cells}</tr></thead>
              <tbody>{''.join(body_rows)}</tbody>
            </table>""",
            unsafe_allow_html=True,
        )

    _render_bucket("By Setup Tag",     analysis["by_tag"],       "Setup")
    _render_bucket("By Day of Week",   analysis["by_dow"],       "Day")
    _render_bucket("By Direction",     analysis["by_direction"], "Direction")
    _render_bucket("By Ticker (top 20)", analysis["by_ticker"][:20], "Ticker")


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
        f"<td style='padding:9px 14px;border-bottom:1px solid {BORDER};"
        f"color:{WHITE};font-weight:700;'>{ipo.ticker}</td>"
        f"<td style='padding:9px 14px;border-bottom:1px solid {BORDER};"
        f"color:{WHITE_DIM};'>{ipo.company}</td>"
        f"<td style='padding:9px 14px;border-bottom:1px solid {BORDER};"
        f"color:{WHITE};text-align:right;font-weight:600;'>{ipo.price_display}</td>"
        f"<td style='padding:9px 14px;border-bottom:1px solid {BORDER};"
        f"color:{WHITE};font-weight:500;'>{date_str}</td>"
        f"<td style='padding:9px 14px;border-bottom:1px solid {BORDER};"
        f"color:{WHITE_DIM};text-align:right;'>{shares}</td>"
        f"<td style='padding:9px 14px;border-bottom:1px solid {BORDER};"
        f"color:{WHITE_DIM};text-align:right;'>{deal}</td>"
        f"<td style='padding:9px 14px;border-bottom:1px solid {BORDER};"
        f"color:{WHITE_MUTE};'>{exch}</td>"
        f"<td style='padding:9px 14px;border-bottom:1px solid {BORDER};'>"
        f"<span style='background:{status_col};color:#06121e;font-weight:700;"
        f"font-size:0.7rem;padding:3px 8px;border-radius:4px;'>{ipo.status}</span></td>"
        f"</tr>"
    )


def _ipo_section(sector: str, rows: list[IPO]) -> None:
    badge = SECTOR_BADGE_COLOR.get(sector, ACCENT)
    st.markdown(
        f"""<div style="display:flex;align-items:baseline;gap:10px;
            margin:22px 0 10px;">
          <span style="background:{badge};color:#06121e;font-weight:700;
            padding:3px 10px;border-radius:4px;font-size:0.78rem;">{sector}</span>
          <span style="color:{WHITE_MUTE};font-size:0.8rem;">{len(rows)} IPO(s)</span>
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

    head_cells = "".join(
        f"<th style='padding:10px 14px;border-bottom:1px solid {BORDER};"
        f"background:{NAVY_CARD} !important;color:{WHITE};font-weight:600;"
        f"font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;"
        f"text-align:{align};'>{h}</th>"
        for h, align in [
            ("Ticker","left"), ("Company","left"), ("Price","right"),
            ("Expected Date","left"), ("Shares","right"), ("Deal Size","right"),
            ("Exch","left"), ("Status","left"),
        ]
    )
    body = "".join(_ipo_row(r) for r in rows)
    st.markdown(
        f"""<table class="sierra-table">
          <thead><tr>{head_cells}</tr></thead>
          <tbody>{body}</tbody>
        </table>""",
        unsafe_allow_html=True,
    )


def render_ipo_calendar() -> None:
    if "ipo_tab" not in st.session_state:
        st.session_state.ipo_tab = "upcoming"

    st.markdown(
        f"""<div style="margin-bottom:8px;">
          <span style="font-size:0.75rem;color:{WHITE_MUTE};
            text-transform:uppercase;letter-spacing:1px;">IPO Calendar</span>
        </div>
        <div style="font-size:2rem;font-weight:700;color:{WHITE};
          letter-spacing:-0.5px;margin-bottom:18px;">IPO Calendar</div>""",
        unsafe_allow_html=True,
    )

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

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

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

    # Top-of-dashboard search bar — opens the catalyst dialog for any
    # ticker the user types, regardless of which sector page is loaded.
    sc1, sc2 = st.columns([6, 1])
    with sc1:
        search_q = st.text_input(
            "Ticker lookup",
            key="ticker_search",
            label_visibility="collapsed",
            placeholder="🔎 Search any ticker — e.g. ODYS, AAPL, NVDA",
        )
    with sc2:
        do_search = st.button("Look up", use_container_width=True,
                              key="ticker_search_btn")
    if (do_search or search_q) and search_q.strip():
        tkr = search_q.strip().upper()
        # Validate vaguely — letters / digits / dots only, 1-6 chars
        import re as _re
        if _re.fullmatch(r"[A-Z0-9.\-]{1,8}", tkr):
            st.session_state.selected_ticker = tkr
            st.session_state.ticker_search = ""
            st.rerun()

    def _reset_view():
        st.session_state.view = "sector"

    category_keys = list(SECTORS.keys()) + ["Trading Journal"]

    with st.sidebar:
        st.markdown(
            f"""<div style="padding:6px 0 14px;">
              <div style="font-size:1.15rem;font-weight:700;color:{WHITE};
                letter-spacing:-0.3px;">Sierra Trading</div>
            </div>""",
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

            st.divider()
            if st.button(
                "📈 Today's Top Moves",
                use_container_width=True,
                key="top_movers_btn",
                type="primary" if st.session_state.view == "movers" else "secondary",
            ):
                st.session_state.view = "movers"
                st.rerun()

            if st.button(
                "📅 IPO Calendar",
                use_container_width=True,
                key="ipo_calendar_btn",
                type="primary" if st.session_state.view == "ipo" else "secondary",
            ):
                st.session_state.view = "ipo"
                st.rerun()

            if st.button("Refresh", use_container_width=True, key="refresh_btn"):
                st.cache_data.clear()
                st.rerun()

            if st.button(
                "📋 Changelog",
                use_container_width=True,
                key="changelog_btn",
            ):
                st.session_state.show_changelog = True

            # ---------- AI Employees ----------
            st.markdown(
                f"""<div style="margin-top:18px;padding-top:14px;
                  border-top:1px solid {BORDER};">
                  <div style="font-size:0.7rem;color:{WHITE_MUTE};
                    text-transform:uppercase;letter-spacing:1px;
                    margin-bottom:8px;">AI Employees</div>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button(
                "🛠 Operations",
                use_container_width=True,
                key="operations_btn",
                type="primary" if st.session_state.view == "operations" else "secondary",
            ):
                st.session_state.view = "operations"
                st.rerun()

            if st.button(
                "🤖 AI Classification",
                use_container_width=True,
                key="ai_classify_btn",
                type="primary" if st.session_state.view == "ai_classify" else "secondary",
                help="Use Google Gemini to classify tickers into sector / sub-sector",
            ):
                st.session_state.view = "ai_classify"
                st.rerun()

            if st.button(
                "💡 Mia (Performance Coach)",
                use_container_width=True,
                key="mia_btn",
                type="primary" if st.session_state.view == "mia" else "secondary",
            ):
                st.session_state.view = "mia"
                st.rerun()

    if is_journal:
        render_journal()
        return

    if st.session_state.view == "movers":
        render_top_movers()
        return

    if st.session_state.view in ("operations", "aidan"):
        render_operations()
        return

    if st.session_state.view == "ai_classify":
        render_gemini_classification()
        return

    if st.session_state.view == "mia":
        render_mia_coach()
        return

    if st.session_state.view == "ipo":
        render_ipo_calendar()
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

    st.markdown(
        f"""<div style="margin-bottom:6px;">
          <span style="font-size:0.75rem;color:{WHITE_MUTE};
            text-transform:uppercase;letter-spacing:1px;">
            {main_cat} &nbsp;/&nbsp; {selected_label}</span>
        </div>
        <div style="font-size:2rem;font-weight:700;color:{WHITE};
          letter-spacing:-0.5px;margin-bottom:20px;">Sierra Trading</div>""",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading market data…"):
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

    # Compute sentiment snapshot once per render for the briefing card.
    try:
        tickers_list = sorted({q.ticker for syms in by_cat.values() for q in syms})
        snap = sector_sentiment_snapshot(
            main_cat, tuple(tickers_list), window_days=7,
        )
    except Exception:
        snap = None
    if snap is not None:
        render_sentiment_briefing(snap)

    render_sector(main_cat, selected_folder, by_cat.get(selected_folder, []), uni_mod.INFO)


if __name__ == "__main__":
    main()
