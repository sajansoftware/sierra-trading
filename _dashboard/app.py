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
import trading_journal
from ipo_calendar import fetch_ipo_calendar, IPO
from verifier import verify_categorization, SourceCheck

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

SECTORS: dict[str, dict[str, tuple[str, str, Path]]] = {
    "Biotechnology": {
        "Red_Medical_Pharmaceutical": ("Medical / Pharmaceutical", ACCENT, ROOT / "Biotechnology" / "Red_Medical_Pharmaceutical"),
        "Green_Agricultural":         ("Agricultural",             ACCENT, ROOT / "Biotechnology" / "Green_Agricultural"),
        "White_Industrial":           ("Industrial",               ACCENT, ROOT / "Biotechnology" / "White_Industrial"),
        "Blue_Marine":                ("Marine",                   ACCENT, ROOT / "Biotechnology" / "Blue_Marine"),
        "Grey_Environmental":         ("Environmental",            ACCENT, ROOT / "Biotechnology" / "Grey_Environmental"),
        "Yellow_Food_Nutrition":      ("Food / Nutrition",         ACCENT, ROOT / "Biotechnology" / "Yellow_Food_Nutrition"),
        "Gold_Bioinformatics":        ("Bioinformatics",           ACCENT, ROOT / "Biotechnology" / "Gold_Bioinformatics"),
    },
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
    },
    "Energy": {
        "Exploration_Production":      ("Exploration & Production",      ACCENT, ROOT / "Energy" / "Exploration_Production"),
        "Oilfield_Services_Equipment": ("Oilfield Services & Equipment", ACCENT, ROOT / "Energy" / "Oilfield_Services_Equipment"),
        "Midstream":                   ("Midstream",                     ACCENT, ROOT / "Energy" / "Midstream"),
        "Renewable_Energy":            ("Renewable Energy",              ACCENT, ROOT / "Energy" / "Renewable_Energy"),
        "Coal_Uranium":                ("Coal & Uranium",                ACCENT, ROOT / "Energy" / "Coal_Uranium"),
    },
    "Industrials": {
        "Aerospace_Defense":        ("Aerospace & Defense",        ACCENT, ROOT / "Industrials" / "Aerospace_Defense"),
        "Machinery":                ("Machinery",                  ACCENT, ROOT / "Industrials" / "Machinery"),
        "Transportation_Logistics": ("Transportation & Logistics", ACCENT, ROOT / "Industrials" / "Transportation_Logistics"),
        "Construction_Engineering": ("Construction & Engineering", ACCENT, ROOT / "Industrials" / "Construction_Engineering"),
        "Electrical_Equipment":     ("Electrical Equipment",       ACCENT, ROOT / "Industrials" / "Electrical_Equipment"),
        "Industrial_Services":      ("Industrial Services",        ACCENT, ROOT / "Industrials" / "Industrial_Services"),
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
    },
    "Communication Services": {
        "Wireless_Wireline_Telecom": ("Wireless & Wireline Telecom", ACCENT, ROOT / "Communication_Services" / "Wireless_Wireline_Telecom"),
        "Satellite_Towers":          ("Satellite & Towers",          ACCENT, ROOT / "Communication_Services" / "Satellite_Towers"),
        "Media_Entertainment":       ("Media & Entertainment",       ACCENT, ROOT / "Communication_Services" / "Media_Entertainment"),
        "Advertising_MarTech":       ("Advertising & MarTech",       ACCENT, ROOT / "Communication_Services" / "Advertising_MarTech"),
        "Social_Gaming_Platforms":   ("Social & Gaming Platforms",   ACCENT, ROOT / "Communication_Services" / "Social_Gaming_Platforms"),
        "Publishing_News":           ("Publishing & News",           ACCENT, ROOT / "Communication_Services" / "Publishing_News"),
        "Streaming":                 ("Streaming",                   ACCENT, ROOT / "Communication_Services" / "Streaming"),
    },
    "Consumer Staples": {
        "Food_Beverage":         ("Food & Beverage",         ACCENT, ROOT / "Consumer_Staples" / "Food_Beverage"),
        "Alt_Protein_Food_Tech": ("Alt-Protein & Food Tech", ACCENT, ROOT / "Consumer_Staples" / "Alt_Protein_Food_Tech"),
        "Household_Products":    ("Household Products",      ACCENT, ROOT / "Consumer_Staples" / "Household_Products"),
        "Personal_Care_Beauty":  ("Personal Care & Beauty",  ACCENT, ROOT / "Consumer_Staples" / "Personal_Care_Beauty"),
        "Tobacco_Vape":          ("Tobacco & Vape",          ACCENT, ROOT / "Consumer_Staples" / "Tobacco_Vape"),
        "Grocery_Distribution":  ("Grocery & Distribution",  ACCENT, ROOT / "Consumer_Staples" / "Grocery_Distribution"),
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
    },
    "Healthcare Services": {
        "Hospitals_Health_Systems": ("Hospitals & Health Systems", ACCENT, ROOT / "Healthcare_Services" / "Hospitals_Health_Systems"),
        "Health_Insurance":         ("Health Insurance",           ACCENT, ROOT / "Healthcare_Services" / "Health_Insurance"),
        "Healthcare_IT_Telehealth": ("Healthcare IT & Telehealth", ACCENT, ROOT / "Healthcare_Services" / "Healthcare_IT_Telehealth"),
        "Pharmacy_Distributors":    ("Pharmacy & Distributors",    ACCENT, ROOT / "Healthcare_Services" / "Pharmacy_Distributors"),
        "Medical_Devices":          ("Medical Devices",            ACCENT, ROOT / "Healthcare_Services" / "Medical_Devices"),
        "Dental_Vision_Hearing":    ("Dental, Vision & Hearing",   ACCENT, ROOT / "Healthcare_Services" / "Dental_Vision_Hearing"),
    },
}


# =============================================================================
# Theme
# =============================================================================
def inject_theme() -> None:
    st.markdown(
        f"""<style>
        #MainMenu, header, footer {{ visibility: hidden; }}
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
        </style>""",
        unsafe_allow_html=True,
    )


# =============================================================================
# Helpers
# =============================================================================
def load_description(dir_path: Path) -> str:
    p = dir_path / "description.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def quotes_to_df(rows: list[Quote], info: dict) -> pd.DataFrame:
    out = []
    for q in rows:
        meta = info.get(q.ticker)
        if meta is not None:
            company = f"{meta.name} — {meta.blurb}"
        else:
            name = (q.name or q.ticker).strip()
            blurb = short_blurb(q.summary) or (q.industry or "")
            company = f"{name} — {blurb}" if blurb else name
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
    "FDA Approval":   "#22c55e",
    "PDUFA":          "#22c55e",
    "Clinical Data":  "#06b6d4",
    "Trial Update":   "#06b6d4",
    "Product Launch": "#10b981",
    "Earnings":       "#a78bfa",
    "Offering":       "#f97316",
    "M&A":            "#facc15",
    "Partnership":    "#64b5f6",
    "Contract Win":   "#34d399",
    "Listing":        "#64b5f6",
    "Guidance":       "#a78bfa",
    "Patent":         "#94a3b8",
    "Insider":        "#94a3b8",
    "Analyst":        "#94a3b8",
    "Restructuring":  "#f97316",
    "Bankruptcy":     "#ef4444",
    "Auditor":        "#94a3b8",
    "News":           "#94a3b8",
}


def _close_dialog() -> None:
    """Called by the in-dialog Close button. Streamlit reruns afterwards;
    selected_ticker has already been consumed in main(), so the dialog
    won't re-open."""
    pass


_SECTOR_LOOKUP_MODS = [
    ("Biotechnology",          bio_universe),
    ("Technology",             tech_universe),
    ("Energy",                  energy_universe),
    ("Industrials",            industrials_universe),
    ("Materials",              materials_universe),
    ("Consumer_Discretionary", consumer_disc_universe),
    ("Financials",             financials_universe),
    ("Communication_Services", comm_services_universe),
    ("Consumer_Staples",       consumer_staples_universe),
    ("Real_Estate",            real_estate_universe),
    ("Healthcare_Services",    healthcare_svc_universe),
]


def _find_ticker_sector(ticker: str) -> str | None:
    """Return the dashboard sector key the ticker is assigned to."""
    for sector_key, mod in _SECTOR_LOOKUP_MODS:
        try:
            if ticker in mod.all_tickers():
                return sector_key
        except Exception:
            continue
    return None


_CONFIDENCE_COLOR = {
    "high": GOOD,
    "low":  WARN,
    "none": DANGER,
}


def _render_verification_section(ticker: str) -> None:
    """3-source category verification block inside the catalyst dialog."""
    sector = _find_ticker_sector(ticker)
    if not sector:
        return
    sector_display = sector.replace("_", " ")
    with st.spinner("Cross-checking category against 3 sources…"):
        try:
            checks, confidence = verify_categorization(ticker, sector)
        except Exception:
            return
    col = _CONFIDENCE_COLOR.get(confidence, WHITE_MUTE)
    UNAVAILABLE = ("(no data)", "(no website)")
    n_avail = sum(1 for c in checks if c.sector_label not in UNAVAILABLE)
    n_match = sum(1 for c in checks if c.matches)
    st.markdown(
        f"""<div style='margin-top:18px;padding:14px 16px;
            background:rgba(255,255,255,0.03);
            border:1px solid {BORDER};border-radius:6px;'>
          <div style='display:flex;justify-content:space-between;
            align-items:center;margin-bottom:10px;'>
            <span style='font-size:0.95rem;font-weight:600;color:{WHITE};'>
              Category Verification — assigned to {sector_display}
            </span>
            <span style='background:{col};color:#06121e;font-weight:700;
              font-size:0.72rem;padding:3px 10px;border-radius:4px;'>
              {n_match}/{n_avail} available sources agree &nbsp;·&nbsp; {confidence.upper()}
            </span>
          </div>""",
        unsafe_allow_html=True,
    )
    for c in checks:
        mark = "✓" if c.matches else "✗"
        mark_col = GOOD if c.matches else DANGER
        snippet = c.snippet or "(no description available)"
        link_html = (
            f"<a href='{c.link}' target='_blank' style='color:{ACCENT};"
            f"text-decoration:none;font-size:0.78rem;'>view ↗</a>"
            if c.link else ""
        )
        st.markdown(
            f"""<div style='padding:9px 0;border-top:1px solid {BORDER};
                display:flex;gap:14px;align-items:flex-start;'>
              <span style='color:{mark_col};font-weight:700;
                font-size:1rem;width:14px;'>{mark}</span>
              <div style='flex:1;'>
                <div style='display:flex;justify-content:space-between;
                  align-items:baseline;margin-bottom:3px;'>
                  <span style='color:{WHITE};font-weight:600;
                    font-size:0.85rem;'>{c.source}</span>
                  <span style='color:{WHITE_MUTE};font-size:0.78rem;'>
                    {c.sector_label} &nbsp;·&nbsp; {link_html}
                  </span>
                </div>
                <div style='color:{WHITE_DIM};font-size:0.82rem;
                  line-height:1.4;'>{snippet}</div>
              </div>
            </div>""",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


@st.dialog("Catalysts", width="large")
def catalyst_dialog(ticker: str) -> None:
    with st.spinner("Loading pre-market catalysts…"):
        rows = fetch_premarket_catalysts(ticker)

    st.markdown(
        f"<div style='font-size:1.4rem;font-weight:700;color:{WHITE};'>"
        f"{ticker} — Pre-Market Catalysts</div>"
        f"<div style='color:{WHITE_MUTE};font-size:0.78rem;margin-bottom:14px;'>"
        f"Pre-market window 4:00 AM – 9:29 AM ET &nbsp;·&nbsp; "
        f"last 60 days (yfinance intraday limit)</div>",
        unsafe_allow_html=True,
    )

    if not rows:
        st.info(
            "No qualifying pre-market catalyst days in the last 60 days "
            "(close $1–$20, PM upside ≥ 30%)."
        )
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

    body_rows = []
    for r in rows:
        date_str = r["date"].strftime("%b %d, %Y")
        type_label = r["type"]
        type_col = CATALYST_TYPE_COLOR.get(type_label, WHITE_MUTE)
        type_badge = (
            f"<span style='background:{type_col};color:#06121e;"
            f"font-weight:700;font-size:0.7rem;padding:2px 8px;"
            f"border-radius:4px;white-space:nowrap;'>{type_label}</span>"
        )
        catalyst_text = (
            r["title"] if r["title"]
            else f"<span style='color:#64748b;'>—</span>"
        )
        source_label = r.get("source") or "—"
        if r["link"] and source_label != "—":
            source_html = (
                f"<a href='{r['link']}' target='_blank' "
                f"style='color:{ACCENT};text-decoration:none;font-size:0.78rem;"
                f"white-space:nowrap;'>{source_label} ↗</a>"
            )
        else:
            source_html = (
                f"<span style='color:#64748b;font-size:0.78rem;'>"
                f"{source_label}</span>"
            )
        up = r["upside_pct"]
        up_color = GOOD if up >= 50 else (WARN if up >= 30 else ACCENT)
        pm_low_cell = (
            f"<div style='color:{WHITE_DIM};font-weight:500;'>${r['pm_low']:.2f}</div>"
            f"<div style='color:{WHITE_MUTE};font-size:0.72rem;'>{r['pm_low_time']}</div>"
        )
        pm_high_cell = (
            f"<div style='color:{WHITE};font-weight:600;'>${r['pm_high']:.2f}</div>"
            f"<div style='color:{WHITE_MUTE};font-size:0.72rem;'>{r['pm_high_time']}</div>"
        )
        body_rows.append(
            f"<tr>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"color:{WHITE};font-weight:500;white-space:nowrap;vertical-align:top;'>{date_str}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"text-align:right;vertical-align:top;'>{pm_low_cell}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"text-align:right;vertical-align:top;'>{pm_high_cell}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"color:{up_color};text-align:right;font-weight:700;vertical-align:top;'>+{up:.1f}%</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};vertical-align:top;'>{type_badge}</td>"
            f"<td style='padding:9px 12px;border-bottom:1px solid {BORDER};"
            f"color:{WHITE_DIM};font-size:0.85rem;max-width:340px;vertical-align:top;'>{catalyst_text}</td>"
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

    # 3-source category verification - LAZY. Shows only when the user
    # opts in, so the dialog itself opens instantly.
    if st.toggle("Show 3-source category verification", key="show_verify"):
        _render_verification_section(ticker)

    if st.button("Close", key="close_dlg"):
        _close_dialog()
        st.rerun()


# =============================================================================
# Sector view
# =============================================================================
def render_sector(sector: str, folder: str, rows: list[Quote], info: dict) -> None:
    label, _, dir_path = SECTORS[sector][folder]

    st.markdown(
        f"""<div style="
            border-left:4px solid {ACCENT};background:{NAVY_CARD};
            padding:14px 18px;border-radius:6px;margin-bottom:18px;">
            <span style="font-size:1.2rem;font-weight:600;color:{WHITE};">{label}</span>
        </div>""",
        unsafe_allow_html=True,
    )
    desc = load_description(dir_path)
    if desc:
        st.markdown(
            f"<div style='color:{WHITE_DIM};font-size:0.9rem;"
            f"line-height:1.6;margin-bottom:18px;'>{desc}</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""<div style="display:flex;justify-content:space-between;
            align-items:baseline;margin-bottom:10px;">
          <span style="font-size:1.05rem;font-weight:600;color:{WHITE};">
            Candidates ({len(rows)})
          </span>
          <span style="font-size:0.78rem;color:{WHITE_MUTE};">
            ${MIN_PRICE:.0f}–${MAX_PRICE:.0f} &nbsp;·&nbsp;
            Float &lt; {MAX_FLOAT/1_000_000:.0f}M &nbsp;·&nbsp;
            yfinance / 15m cache
          </span>
        </div>""",
        unsafe_allow_html=True,
    )

    if not rows:
        st.info("No tickers in this category currently pass the filter.")
        return

    st.caption("Click any ticker symbol to open its 5-year catalyst archive.")
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
# Today's top moves
# =============================================================================
def render_top_movers() -> None:
    st.markdown(
        f"""<div style="margin-bottom:8px;">
          <span style="font-size:0.75rem;color:{WHITE_MUTE};
            text-transform:uppercase;letter-spacing:1px;">Top Moves</span>
        </div>
        <div style="font-size:2rem;font-weight:700;color:{WHITE};
          letter-spacing:-0.5px;margin-bottom:6px;">Today's Top Moves</div>
        <div style="font-size:0.85rem;color:{WHITE_DIM};margin-bottom:18px;">
          Pre-market window 4:00 AM – 9:29 AM ET
          &nbsp;·&nbsp; ${MIN_PRICE:.0f}–${MAX_PRICE:.0f}
          &nbsp;·&nbsp; Float &lt; {MAX_FLOAT/1_000_000:.0f}M
          &nbsp;·&nbsp; PM move vs prior close ≥ 20%
          &nbsp;·&nbsp; 5-min cache</div>""",
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
          letter-spacing:-0.5px;margin-bottom:6px;">IPO Calendar</div>
        <div style="font-size:0.9rem;color:{WHITE_DIM};margin-bottom:18px;">
          Proposed price ${MIN_PRICE:.0f}–${MAX_PRICE:.0f}
          &nbsp;·&nbsp; NASDAQ &nbsp;·&nbsp; 6h cache</div>""",
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

    def _reset_view():
        st.session_state.view = "sector"

    category_keys = list(SECTORS.keys()) + ["Trading Journal"]

    with st.sidebar:
        st.markdown(
            f"""<div style="padding:6px 0 14px;">
              <div style="font-size:1.15rem;font-weight:700;color:{WHITE};
                letter-spacing:-0.3px;">Sierra Trading</div>
              <div style="font-size:0.75rem;color:{WHITE_MUTE};margin-top:2px;">
                Micro-float screener · yfinance</div>
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

            if st.button("Refresh quotes", use_container_width=True, key="refresh_btn"):
                st.cache_data.clear()
                st.toast("Quotes cache cleared.")
                st.rerun()
            st.caption(
                f"Last load: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

    if is_journal:
        render_journal()
        return

    if st.session_state.view == "movers":
        render_top_movers()
        return

    if st.session_state.view == "ipo":
        render_ipo_calendar()
        return

    uni_mod = {
        "Biotechnology":          bio_universe,
        "Technology":             tech_universe,
        "Energy":                  energy_universe,
        "Industrials":            industrials_universe,
        "Materials":              materials_universe,
        "Consumer Discretionary": consumer_disc_universe,
        "Financials":             financials_universe,
        "Communication Services": comm_services_universe,
        "Consumer Staples":       consumer_staples_universe,
        "Real Estate":            real_estate_universe,
        "Healthcare Services":    healthcare_svc_universe,
    }[main_cat]

    ticker_count = f"{len(uni_mod.INFO)} curated"
    st.markdown(
        f"""<div style="margin-bottom:6px;">
          <span style="font-size:0.75rem;color:{WHITE_MUTE};
            text-transform:uppercase;letter-spacing:1px;">
            {main_cat} &nbsp;/&nbsp; {selected_label}</span>
        </div>
        <div style="font-size:2rem;font-weight:700;color:{WHITE};
          letter-spacing:-0.5px;margin-bottom:4px;">Sierra Trading</div>
        <div style="font-size:0.9rem;color:{WHITE_DIM};margin-bottom:20px;">
          ${MIN_PRICE:.0f}–${MAX_PRICE:.0f} &nbsp;·&nbsp;
          Free float &lt; {MAX_FLOAT/1_000_000:.0f}M shares &nbsp;·&nbsp;
          {ticker_count}</div>""",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading market data…"):
        by_cat = filtered_by_category(uni_mod.UNIVERSE(), uni_mod.all_tickers())

    render_sector(main_cat, selected_folder, by_cat.get(selected_folder, []), uni_mod.INFO)


if __name__ == "__main__":
    main()
