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
    short_blurb,
    tv_num,
)
import universe as bio_universe
import tech_universe
import energy_universe
import trading_journal

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
            "Red — Medical / Pharmaceutical", "#8b949e",
            ROOT / "Biotechnology" / "Red_Medical_Pharmaceutical",
        ),
        "Green_Agricultural": (
            "Green — Agricultural", "#8b949e",
            ROOT / "Biotechnology" / "Green_Agricultural",
        ),
        "White_Industrial": (
            "White — Industrial", "#8b949e",
            ROOT / "Biotechnology" / "White_Industrial",
        ),
        "Blue_Marine": (
            "Blue — Marine", "#8b949e",
            ROOT / "Biotechnology" / "Blue_Marine",
        ),
        "Grey_Environmental": (
            "Grey — Environmental", "#8b949e",
            ROOT / "Biotechnology" / "Grey_Environmental",
        ),
        "Yellow_Food_Nutrition": (
            "Yellow — Food / Nutrition", "#8b949e",
            ROOT / "Biotechnology" / "Yellow_Food_Nutrition",
        ),
        "Gold_Bioinformatics": (
            "Gold — Bioinformatics", "#8b949e",
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
    "Energy": {
        "Exploration_Production": (
            "Exploration & Production", "#f97316",
            ROOT / "Energy" / "Exploration_Production",
        ),
        "Oilfield_Services_Equipment": (
            "Oilfield Services & Equipment", "#d97706",
            ROOT / "Energy" / "Oilfield_Services_Equipment",
        ),
        "Midstream": (
            "Midstream", "#ea580c",
            ROOT / "Energy" / "Midstream",
        ),
        "Renewable_Energy": (
            "Renewable Energy", "#22c55e",
            ROOT / "Energy" / "Renewable_Energy",
        ),
        "Coal_Uranium": (
            "Coal & Uranium", "#6b7280",
            ROOT / "Energy" / "Coal_Uranium",
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
            # Screener-discovered ticker: fall back to yfinance metadata
            name = (q.name or q.ticker).strip()
            blurb = short_blurb(q.summary) or (q.industry or "")
            company = f"{name} — {blurb}" if blurb else name
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
    collapsed = st.session_state.get("sidebar_collapsed", False)
    collapsed_css = (
        "section[data-testid='stSidebar'] { display: none !important; }"
        ".main .block-container { max-width: 100% !important; padding-left: 1.5rem !important; padding-right: 1.5rem !important; }"
        if collapsed else ""
    )
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
        .sb-toggle {{
            background: transparent !important;
            border: 1px solid {BORDER} !important;
            color: {TEXT_PRIMARY} !important;
            font-size: 1.1rem !important;
            padding: 2px 8px !important;
            border-radius: 4px !important;
            cursor: pointer !important;
            line-height: 1.4 !important;
        }}
        .sb-toggle:hover {{
            border-color: {ACCENT} !important;
            color: {TEXT_PRIMARY} !important;
        }}
        {collapsed_css}
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


def _stat_card(label: str, value: str, color: str) -> None:
    st.markdown(
        f"""<div style="
            background:{CARD_BG};border:1px solid {BORDER};
            border-radius:6px;padding:14px 16px;text-align:center;
        ">
            <div style="font-size:0.72rem;color:{TEXT_MUTED};
                text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">
                {label}
            </div>
            <div style="font-size:1.35rem;font-weight:700;color:{color};">
                {value}
            </div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_trading_journal() -> None:
    st.markdown(
        f"""<div style="margin-bottom:8px;">
            <span style="font-size:0.75rem;color:{TEXT_MUTED};
                text-transform:uppercase;letter-spacing:1px;">
                Trading Journal
            </span>
        </div>
        <div style="font-size:2rem;font-weight:700;color:{TEXT_PRIMARY};
            letter-spacing:-0.5px;margin-bottom:24px;">
            Performance Dashboard
        </div>""",
        unsafe_allow_html=True,
    )

    trades = trading_journal.load_trades()
    stats = trading_journal.calculate_stats(trades)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _stat_card("Total Trades", str(stats["total_trades"]), TEXT_PRIMARY)
    with col2:
        c = "#22c55e" if stats["win_rate"] >= 50 else "#ef4444"
        _stat_card("Win Rate", f"{stats['win_rate']:.1f}%", c)
    with col3:
        c = "#22c55e" if stats["total_pnl"] >= 0 else "#ef4444"
        p = "+" if stats["total_pnl"] >= 0 else ""
        _stat_card("Total P&L", f"{p}${stats['total_pnl']:,.2f}", c)
    with col4:
        c = "#22c55e" if stats["avg_pnl"] >= 0 else "#ef4444"
        p = "+" if stats["avg_pnl"] >= 0 else ""
        _stat_card("Avg P&L", f"{p}${stats['avg_pnl']:,.2f}", c)

    with st.expander("Add New Trade", expanded=True):
        with st.form("trade_form", clear_on_submit=True):
            cols = st.columns(4)
            with cols[0]:
                trade_date = st.date_input("Date")
            with cols[1]:
                ticker = st.text_input("Ticker").upper().strip()
            with cols[2]:
                direction = st.selectbox("Direction", ["Long", "Short"])
            with cols[3]:
                quantity = st.number_input("Quantity", min_value=1, value=100, step=100)
            cols2 = st.columns(3)
            with cols2[0]:
                entry = st.number_input("Entry Price", min_value=0.01, value=10.0, step=0.01, format="%.2f")
            with cols2[1]:
                exit_ = st.number_input("Exit Price", min_value=0.01, value=10.0, step=0.01, format="%.2f")
            with cols2[2]:
                tags = st.text_input("Tags (comma-separated)")
            notes = st.text_area("Notes", height=80)
            submitted = st.form_submit_button("Save Trade", use_container_width=True)
            if submitted:
                if not ticker:
                    st.error("Ticker is required.")
                else:
                    trade = trading_journal.Trade(
                        date=trade_date.isoformat(),
                        ticker=ticker,
                        direction=direction,
                        entry=entry,
                        exit=exit_,
                        quantity=quantity,
                        notes=notes,
                        tags=tags,
                    )
                    trading_journal.add_trade(trade)
                    st.success(f"Trade saved: {ticker}")
                    st.rerun()

    if not trades:
        st.markdown(
            f"""<div style="color:{TEXT_SECONDARY};font-size:0.9rem;
                margin-top:24px;text-align:center;padding:40px 0;">
                No trades recorded yet. Add your first trade above.
            </div>""",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""<div style="font-size:1.1rem;font-weight:700;color:{TEXT_PRIMARY};
            margin:24px 0 12px 0;">Trade History ({len(trades)})</div>""",
        unsafe_allow_html=True,
    )

    rows_html = ""
    for i, t in enumerate(trades):
        pnl = t.get("pnl", 0)
        pnl_pct = t.get("pnl_pct", 0)
        pnl_color = "#22c55e" if pnl >= 0 else "#ef4444"
        pnl_sign = "+" if pnl >= 0 else ""
        dir_color = "#22c55e" if t.get("direction") == "Long" else "#ef4444"
        dir_badge = (
            f"<span style='color:{dir_color};font-weight:600;font-size:0.8rem;'>"
            f"{t.get('direction','')}</span>"
        )
        rows_html += f"""<tr>
            <td style="padding:7px 10px;border-bottom:1px solid {BORDER};font-size:0.85rem;color:{TEXT_PRIMARY};">{t.get("date","")}</td>
            <td style="padding:7px 10px;border-bottom:1px solid {BORDER};font-size:0.85rem;font-weight:700;color:{TEXT_PRIMARY};">{t.get("ticker","")}</td>
            <td style="padding:7px 10px;border-bottom:1px solid {BORDER};">{dir_badge}</td>
            <td style="padding:7px 10px;border-bottom:1px solid {BORDER};font-size:0.85rem;color:{TEXT_SECONDARY};">${t.get("entry",0):.2f} → ${t.get("exit",0):.2f}</td>
            <td style="padding:7px 10px;border-bottom:1px solid {BORDER};font-size:0.85rem;color:{TEXT_SECONDARY};">{t.get("quantity",0)}</td>
            <td style="padding:7px 10px;border-bottom:1px solid {BORDER};font-size:0.85rem;font-weight:600;color:{pnl_color};">{pnl_sign}${pnl:,.2f}</td>
            <td style="padding:7px 10px;border-bottom:1px solid {BORDER};font-size:0.85rem;color:{pnl_color};">{pnl_sign}{pnl_pct:.2f}%</td>
            <td style="padding:7px 10px;border-bottom:1px solid {BORDER};font-size:0.8rem;color:{TEXT_MUTED};">{t.get("tags","")}</td>
            <td style="padding:7px 10px;border-bottom:1px solid {BORDER};text-align:center;">
                <a href="?delete_trade={i}" style="color:#ef4444;text-decoration:none;font-size:1.1rem;font-weight:700;" title="Delete trade">&times;</a>
            </td>
        </tr>"""

    st.markdown(
        f"""<div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;">
        <thead>
            <tr style="background:{CARD_BG};">
                <th style="padding:8px 10px;border-bottom:1px solid {BORDER};color:{TEXT_SECONDARY};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;text-align:left;">Date</th>
                <th style="padding:8px 10px;border-bottom:1px solid {BORDER};color:{TEXT_SECONDARY};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;text-align:left;">Ticker</th>
                <th style="padding:8px 10px;border-bottom:1px solid {BORDER};color:{TEXT_SECONDARY};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;text-align:left;">Dir</th>
                <th style="padding:8px 10px;border-bottom:1px solid {BORDER};color:{TEXT_SECONDARY};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;text-align:left;">Entry → Exit</th>
                <th style="padding:8px 10px;border-bottom:1px solid {BORDER};color:{TEXT_SECONDARY};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;text-align:left;">Qty</th>
                <th style="padding:8px 10px;border-bottom:1px solid {BORDER};color:{TEXT_SECONDARY};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;text-align:left;">P&L</th>
                <th style="padding:8px 10px;border-bottom:1px solid {BORDER};color:{TEXT_SECONDARY};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;text-align:left;">P&L %</th>
                <th style="padding:8px 10px;border-bottom:1px solid {BORDER};color:{TEXT_SECONDARY};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;text-align:left;">Tags</th>
                <th style="padding:8px 10px;border-bottom:1px solid {BORDER};color:{TEXT_SECONDARY};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px;text-align:center;width:32px;"></th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
        </table>
        </div>""",
        unsafe_allow_html=True,
    )

    if st.button("Clear All Trades", type="secondary", use_container_width=False):
        trading_journal.clear_all()
        st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Sierra Trading",
        page_icon="",
        layout="wide",
    )

    if "sidebar_collapsed" not in st.session_state:
        st.session_state.sidebar_collapsed = False

    inject_theme()

    top = st.columns([0.04, 0.96])
    with top[0]:
        icon = "☰" if st.session_state.sidebar_collapsed else "◀"
        if st.button(icon, key="sb_toggle", help="Toggle sidebar"):
            st.session_state.sidebar_collapsed = not st.session_state.sidebar_collapsed
            st.rerun()

    category_keys = list(SECTORS.keys()) + ["Trading Journal"]

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

        is_journal = main_cat == "Trading Journal"

        if not is_journal:
            branches = SECTORS[main_cat]
            branch_labels = [v[0] for v in branches.values()]
            selected_label = st.sidebar.radio(
                label="Sub-sector",
                options=branch_labels,
                label_visibility="collapsed",
            )
            selected_folder = next(
                k for k, (l, _, _) in branches.items() if l == selected_label
            )

            st.sidebar.divider()
            if st.sidebar.button("Refresh Quotes"):
                st.cache_data.clear()
                st.rerun()
            st.sidebar.caption(
                f"Last load: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

        st.sidebar.markdown(
            f"""<div class="sidebar-quote">
                <q>Be fearful when others are greedy, and greedy when others are fearful.</q>
                <cite>&mdash; Warren Buffett</cite>
            </div>""",
            unsafe_allow_html=True,
        )

    delete_idx = st.query_params.get("delete_trade")
    if delete_idx and delete_idx.isdigit():
        trading_journal.delete_trade(int(delete_idx))
        st.query_params.clear()
        st.rerun()

    if is_journal:
        render_trading_journal()
        return

    if main_cat == "Biotechnology":
        uni_mod = bio_universe
    elif main_cat == "Energy":
        uni_mod = energy_universe
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
