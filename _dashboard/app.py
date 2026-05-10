"""Biotechnology & Technology dashboard — multi-sector micro-float screener."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from data import (
    MAX_FLOAT,
    MAX_PRICE,
    MIN_PRICE,
    Quote,
    fetch_catalysts,
    filtered_by_category,
    tv_num,
)
import universe as bio_universe
import tech_universe

ROOT = Path(__file__).parent

DARK_BG = "#0d1117"
CARD_BG = "#161b22"
BORDER = "#21262d"
TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_MUTED = "#484f58"
ACCENT = "#58a6ff"

SECTORS: dict[str, dict[str, tuple[str, str, Path]]] = {
    "Biotechnology": {
        "Red_Medical_Pharmaceutical": (
            "Red — Medical / Pharmaceutical", "#D7263D",
            ROOT / "Biotechnology" / "Red_Medical_Pharmaceutical",
        ),
        "Green_Agricultural": (
            "Green — Agricultural", "#2E933C",
            ROOT / "Biotechnology" / "Green_Agricultural",
        ),
        "White_Industrial": (
            "White — Industrial", "#8b949e",
            ROOT / "Biotechnology" / "White_Industrial",
        ),
        "Blue_Marine": (
            "Blue — Marine", "#1E6FBA",
            ROOT / "Biotechnology" / "Blue_Marine",
        ),
        "Grey_Environmental": (
            "Grey — Environmental", "#6C757D",
            ROOT / "Biotechnology" / "Grey_Environmental",
        ),
        "Yellow_Food_Nutrition": (
            "Yellow — Food / Nutrition", "#F4C430",
            ROOT / "Biotechnology" / "Yellow_Food_Nutrition",
        ),
        "Gold_Bioinformatics": (
            "Gold — Bioinformatics", "#C9A227",
            ROOT / "Biotechnology" / "Gold_Bioinformatics",
        ),
    },
    "Technology": {
        "Semiconductors": (
            "Semiconductors", "#58a6ff",
            ROOT / "Technology" / "Semiconductors",
        ),
        "Software_SaaS": (
            "Software / SaaS", "#7ee787",
            ROOT / "Technology" / "Software_SaaS",
        ),
        "Cloud_Infrastructure": (
            "Cloud & Infrastructure", "#79c0ff",
            ROOT / "Technology" / "Cloud_Infrastructure",
        ),
        "AI_Machine_Learning": (
            "AI & Machine Learning", "#d2a8ff",
            ROOT / "Technology" / "AI_Machine_Learning",
        ),
        "Cybersecurity": (
            "Cybersecurity", "#ff7b72",
            ROOT / "Technology" / "Cybersecurity",
        ),
        "Consumer_Electronics": (
            "Consumer Electronics", "#ffa657",
            ROOT / "Technology" / "Consumer_Electronics",
        ),
        "Fintech": (
            "Fintech", "#3fb950",
            ROOT / "Technology" / "Fintech",
        ),
        "Telecom": (
            "Telecom", "#79c0ff",
            ROOT / "Technology" / "Telecom",
        ),
        "IT_Services": (
            "IT Services", "#8b949e",
            ROOT / "Technology" / "IT_Services",
        ),
    },
}


def load_description(dir_path: Path) -> str:
    path = dir_path / "description.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def quotes_to_df(rows: list[Quote], info: dict) -> pd.DataFrame:
    out = []
    for q in rows:
        meta = info.get(q.ticker)
        if meta is not None:
            company = f"{meta.name} — {meta.blurb}"
        else:
            company = q.industry or ""
        ticker_html = (
            f'<a href="?ticker={q.ticker}" '
            f'style="color:{TEXT_PRIMARY};text-decoration:none;font-weight:700;">'
            f"{q.ticker}</a>"
        )
        out.append(
            {
                "Ticker":      ticker_html,
                "Close":       q.close,
                "Float":       q.float_shares,
                "Mkt Cap":     q.market_cap,
                "Description": company,
            }
        )
    return pd.DataFrame(out)


def _price_color(v: float) -> str:
    if pd.isna(v):
        return ""
    if v < 5:
        return "color:#22c55e; font-weight:600;"
    if v < 10:
        return "color:#eab308; font-weight:600;"
    return "color:#f97316; font-weight:600;"


def _float_bg(v: float) -> str:
    if pd.isna(v):
        return ""
    norm = max(0.0, min(1.0, float(v) / MAX_FLOAT))
    alpha = 0.85 - norm * 0.65
    return (
        f"background-color: rgba(74, 222, 128, {alpha:.2f}); "
        f"color:#0b1220; font-weight:600;"
    )


def style_table(df: pd.DataFrame):
    if df.empty:
        return df
    s = df.style.format(
        {
            "Ticker":  lambda v: v,
            "Close":   lambda v: f"${v:.2f}" if pd.notna(v) else "—",
            "Float":   tv_num,
            "Mkt Cap": tv_num,
        },
        escape=None,
    )
    s = s.map(_float_bg, subset=["Float"])
    s = s.map(_price_color, subset=["Close"])
    s = s.set_properties(subset=["Ticker"], **{"font-weight": "700"})
    s = s.set_properties(**{"text-align": "right"})
    s = s.set_properties(subset=["Ticker"], **{"text-align": "left"})
    s = s.set_properties(
        subset=["Description"],
        **{
            "text-align": "left",
            "color": TEXT_SECONDARY,
            "font-size": "0.85rem",
            "max-width": "420px",
            "white-space": "normal",
            "line-height": "1.4",
        },
    )
    s = s.set_table_styles(
        [
            {"selector": "th",
             "props": f"background-color:{CARD_BG}; color:{TEXT_PRIMARY}; "
                      "font-weight:600; text-align:right; padding:10px 14px; "
                      f"border-bottom:1px solid {BORDER}; font-size:0.8rem; "
                      "text-transform:uppercase; letter-spacing:0.5px;"},
            {"selector": "th.col_heading.level0:nth-child(1), "
                         "th.col_heading.level0:nth-child(5)",
             "props": "text-align:left;"},
            {"selector": "td",
             "props": f"padding:8px 14px; font-size:0.9rem; vertical-align:top; "
                      f"border-bottom:1px solid {BORDER};"},
            {"selector": "tbody tr:nth-child(even)",
             "props": f"background-color:rgba(255,255,255,0.02);"},
            {"selector": "tbody tr:hover",
             "props": "background-color:rgba(88,166,255,0.08);"},
            {"selector": "",
             "props": f"border-collapse:collapse; width:100%;"},
        ]
    )
    s = s.hide(axis="index")
    return s


def render_sector(sector: str, folder: str, rows: list[Quote], info: dict) -> None:
    label, color, dir_path = SECTORS[sector][folder]

    st.markdown(
        f"""<div style="
            border-left:4px solid {color};
            background:{CARD_BG};
            padding:16px 20px;
            border-radius:6px;
            margin:0 0 20px 0;">
            <span style="font-size:1.3rem;font-weight:600;color:{TEXT_PRIMARY};">{label}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    desc = load_description(dir_path)
    if desc:
        st.markdown(
            f"""<div style="color:{TEXT_SECONDARY};font-size:0.9rem;
                line-height:1.6;margin-bottom:20px;">{desc}</div>""",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""<div style="display:flex;justify-content:space-between;align-items:baseline;
            margin-bottom:12px;">
            <span style="font-size:1.1rem;font-weight:600;color:{TEXT_PRIMARY};">
                Candidates ({len(rows)})
            </span>
            <span style="font-size:0.78rem;color:{TEXT_SECONDARY};">
                ${MIN_PRICE:.0f}–${MAX_PRICE:.0f} &nbsp;·&nbsp; Float &lt; {MAX_FLOAT/1_000_000:.0f}M
                &nbsp;·&nbsp; yfinance / 15m cache
            </span>
        </div>""",
        unsafe_allow_html=True,
    )

    if not rows:
        st.info("No tickers in this category currently pass the filter.")
        return

    df = quotes_to_df(rows, info)
    st.markdown(style_table(df).to_html(), unsafe_allow_html=True)


def inject_theme() -> None:
    st.markdown(
        f"""<style>
        #MainMenu, header, footer {{visibility:hidden;}}
        .stApp {{
            background-color: {DARK_BG};
        }}
        .main .block-container {{
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1280px;
        }}
        h1, h2, h3 {{
            color: {TEXT_PRIMARY} !important;
        }}
        p, li, .stMarkdown {{
            color: {TEXT_SECONDARY};
        }}
        section[data-testid="stSidebar"] > div:first-child {{
            background-color: {CARD_BG};
        }}
        section[data-testid="stSidebar"] .stSelectbox label,
        section[data-testid="stSidebar"] .stRadio label {{
            color: {TEXT_SECONDARY} !important;
            font-size: 0.85rem;
            padding: 4px 0;
        }}
        section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] {{
            gap: 2px;
        }}
        section[data-testid="stSidebar"] .stRadio label:hover {{
            color: {TEXT_PRIMARY} !important;
        }}
        section[data-testid="stSidebar"] .stSelectbox > div > div {{
            background-color: {DARK_BG};
            border-color: {BORDER};
            border-radius: 4px;
        }}
        section[data-testid="stSidebar"] hr {{
            border-color: {BORDER};
            margin: 16px 0;
        }}
        section[data-testid="stSidebar"] .stButton button {{
            background: transparent;
            border: 1px solid {BORDER};
            color: {TEXT_SECONDARY};
            font-size: 0.8rem;
            border-radius: 4px;
            width: 100%;
        }}
        section[data-testid="stSidebar"] .stButton button:hover {{
            border-color: {ACCENT};
            color: {TEXT_PRIMARY};
        }}
        section[data-testid="stSidebar"] .stCaption {{
            color: {TEXT_MUTED};
            font-size: 0.75rem;
        }}
        .stAlert {{
            background-color: {CARD_BG} !important;
            color: {TEXT_SECONDARY} !important;
            border: 1px solid {BORDER} !important;
        }}
        hr {{
            border-color: {BORDER} !important;
        }}
        .stSpinner > div {{
            border-color: {ACCENT} !important;
        }}
        .sidebar-quote {{
            margin-top: 24px;
            padding: 12px 0;
            border-top: 1px solid {BORDER};
        }}
        .sidebar-quote q {{
            color: {TEXT_SECONDARY};
            font-size: 0.78rem;
            font-style: italic;
            line-height: 1.5;
        }}
        .sidebar-quote cite {{
            color: {TEXT_MUTED};
            font-size: 0.72rem;
            display: block;
            margin-top: 6px;
        }}
        </style>""",
        unsafe_allow_html=True,
    )


def render_catalyst_modal(ticker: str) -> None:
    data = fetch_catalysts(ticker)

    if not data:
        st.markdown(
            f"""<div style="
                position:fixed;top:0;left:0;width:100%;height:100%;
                background:rgba(0,0,0,0.75);z-index:9999;
                display:flex;align-items:center;justify-content:center;
                backdrop-filter:blur(2px);
            ">
            <div style="
                background:{CARD_BG};border:1px solid {BORDER};
                border-radius:8px;max-width:600px;width:92%;
                padding:32px;text-align:center;
            ">
                <div style="font-size:1.1rem;font-weight:700;color:{TEXT_PRIMARY};margin-bottom:12px;">
                    {ticker}
                </div>
                <div style="color:{TEXT_SECONDARY};font-size:0.9rem;margin-bottom:20px;">
                    No recent news found for this ticker.
                </div>
                <a href="?" style="
                    display:inline-block;
                    background:transparent;border:1px solid {BORDER};
                    color:{TEXT_SECONDARY};padding:6px 20px;border-radius:4px;
                    text-decoration:none;font-size:0.85rem;
                ">Close</a>
            </div>
            </div>""",
            unsafe_allow_html=True,
        )
        return

    items_html = ""
    for item in data:
        chg = item.get("change_pct")
        if chg is not None:
            chg_str = f"{'+' if chg >= 0 else ''}{chg:.2f}%"
            badge = (
                f"<span style='color:#22c55e;font-weight:700;font-size:0.9rem;'>{chg_str}</span>"
                if chg >= 0
                else f"<span style='color:#ef4444;font-weight:700;font-size:0.9rem;'>{chg_str}</span>"
            )
        else:
            badge = f"<span style='color:{TEXT_MUTED};font-size:0.9rem;'>--</span>"

        dt = item.get("datetime")
        dt_str = dt.strftime("%b %d, %Y %I:%M %p") if dt else ""
        pub = item.get("publisher") or ""

        o = f"${item['open']:.2f}" if item.get("open") is not None else "—"
        h = f"${item['high']:.2f}" if item.get("high") is not None else "—"
        lo = f"${item['low']:.2f}" if item.get("low") is not None else "—"
        c = f"${item['close']:.2f}" if item.get("close") is not None else "—"
        v = tv_num(item["volume"]) if item.get("volume") is not None else "—"

        items_html += f"""
        <div style="padding:12px 0;border-bottom:1px solid {BORDER};">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;flex-wrap:wrap;">
                {badge}
                <span style="color:{TEXT_MUTED};font-size:0.78rem;">{dt_str}</span>
                {f'<span style="color:{TEXT_MUTED};font-size:0.78rem;">| {pub}</span>' if pub else ''}
            </div>
            <a href="{item.get("link","#")}" target="_blank" style="
                color:{ACCENT};text-decoration:none;font-size:0.95rem;
                font-weight:500;display:block;margin-bottom:6px;
            ">{item.get("title","")}</a>
            <div style="color:{TEXT_SECONDARY};font-size:0.8rem;">
                O: {o} &nbsp; H: {h} &nbsp; L: {lo} &nbsp; C: {c} &nbsp; Vol: {v}
            </div>
        </div>"""

    st.markdown(
        f"""<div style="
            position:fixed;top:0;left:0;width:100%;height:100%;
            background:rgba(0,0,0,0.75);z-index:9999;
            display:flex;align-items:center;justify-content:center;
            backdrop-filter:blur(2px);
        ">
        <div style="
            background:{CARD_BG};border:1px solid {BORDER};
            border-radius:8px;max-width:780px;width:92%;
            max-height:85vh;overflow-y:auto;padding:0;
        ">
            <div style="
                display:flex;justify-content:space-between;align-items:center;
                padding:14px 20px;border-bottom:1px solid {BORDER};
                position:sticky;top:0;background:{CARD_BG};z-index:1;
            ">
                <div style="font-size:1.15rem;font-weight:700;color:{TEXT_PRIMARY};">
                    {ticker} &mdash; Recent Catalysts
                </div>
                <a href="?" style="
                    color:{TEXT_MUTED};font-size:1.5rem;text-decoration:none;
                    line-height:1;padding:0 6px;
                " title="Close">&times;</a>
            </div>
            <div style="padding:8px 20px 16px 20px;">
                {items_html}
            </div>
        </div>
        </div>""",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Sierra Trading",
        page_icon="",
        layout="wide",
    )

    inject_theme()

    category_keys = list(SECTORS.keys())

    with st.sidebar:
        st.markdown(
            f"""<div style="padding:4px 0 16px 0;">
                <div style="font-size:1.1rem;font-weight:700;color:{TEXT_PRIMARY};
                    letter-spacing:-0.3px;">Sierra Trading</div>
                <div style="font-size:0.75rem;color:{TEXT_MUTED};
                    margin-top:2px;">Curated universe &middot; yfinance</div>
            </div>""",
            unsafe_allow_html=True,
        )

        main_cat = st.sidebar.selectbox(
            label="Category",
            options=category_keys,
            label_visibility="collapsed",
        )

        branches = SECTORS[main_cat]
        branch_labels = [v[0] for v in branches.values()]
        selected_label = st.sidebar.radio(
            label="Sub-sector",
            options=branch_labels,
            label_visibility="collapsed",
        )
        selected_folder = next(k for k, (l, _, _) in branches.items() if l == selected_label)

        st.sidebar.divider()
        if st.sidebar.button("Refresh Quotes"):
            st.cache_data.clear()
            st.rerun()
        st.sidebar.caption(f"Last load: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        st.sidebar.markdown(
            f"""<div class="sidebar-quote">
                <q>Be fearful when others are greedy, and greedy when others are fearful.</q>
                <cite>&mdash; Warren Buffett</cite>
            </div>""",
            unsafe_allow_html=True,
        )

    if main_cat == "Biotechnology":
        uni_mod = bio_universe
    else:
        uni_mod = tech_universe

    ticker_count = f"{len(uni_mod.INFO)} tickers"

    st.markdown(
        f"""<div style="margin-bottom:8px;">
            <span style="font-size:0.75rem;color:{TEXT_MUTED};
                text-transform:uppercase;letter-spacing:1px;">
                {main_cat} &nbsp;/&nbsp; {selected_label}
            </span>
        </div>
        <div style="font-size:2rem;font-weight:700;color:{TEXT_PRIMARY};
            letter-spacing:-0.5px;margin-bottom:4px;">
            Sierra Trading
        </div>
        <div style="font-size:0.9rem;color:{TEXT_SECONDARY};margin-bottom:24px;">
            Price ${MIN_PRICE:.0f}–${MAX_PRICE:.0f} &nbsp;·&nbsp;
            Free float &lt; {MAX_FLOAT/1_000_000:.0f}M shares &nbsp;·&nbsp;
            {ticker_count}
        </div>""",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading market data&hellip;"):
        by_cat = filtered_by_category(uni_mod.UNIVERSE(), uni_mod.all_tickers())

    render_sector(main_cat, selected_folder, by_cat.get(selected_folder, []), uni_mod.INFO)

    ticker_param = st.query_params.get("ticker")
    if ticker_param and ticker_param.strip():
        render_catalyst_modal(ticker_param.strip())


if __name__ == "__main__":
    main()
