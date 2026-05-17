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
        "Red_Medical_Pharmaceutical": ("Red — Medical / Pharmaceutical", ACCENT, ROOT / "Biotechnology" / "Red_Medical_Pharmaceutical"),
        "Green_Agricultural":         ("Green — Agricultural",           ACCENT, ROOT / "Biotechnology" / "Green_Agricultural"),
        "White_Industrial":           ("White — Industrial",             ACCENT, ROOT / "Biotechnology" / "White_Industrial"),
        "Blue_Marine":                ("Blue — Marine",                  ACCENT, ROOT / "Biotechnology" / "Blue_Marine"),
        "Grey_Environmental":         ("Grey — Environmental",           ACCENT, ROOT / "Biotechnology" / "Grey_Environmental"),
        "Yellow_Food_Nutrition":      ("Yellow — Food / Nutrition",      ACCENT, ROOT / "Biotechnology" / "Yellow_Food_Nutrition"),
        "Gold_Bioinformatics":        ("Gold — Bioinformatics",          ACCENT, ROOT / "Biotechnology" / "Gold_Bioinformatics"),
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
        /* All text */
        h1, h2, h3, h4, h5, h6, p, span, label, li, code, .stMarkdown {{
            color: {WHITE} !important;
        }}
        /* Sidebar */
        section[data-testid="stSidebar"] > div:first-child {{
            background-color: {NAVY_CARD};
            border-right: 1px solid {BORDER};
        }}
        section[data-testid="stSidebar"] .stSelectbox > div > div,
        section[data-testid="stSidebar"] .stTextInput > div > div > input,
        section[data-testid="stSidebar"] .stNumberInput > div > div > input,
        section[data-testid="stSidebar"] .stDateInput > div > div > input {{
            background-color: {NAVY} !important;
            color: {WHITE} !important;
            border-color: {BORDER} !important;
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
        /* Inputs in main area */
        .stTextInput input, .stNumberInput input, .stDateInput input,
        .stSelectbox div[data-baseweb="select"] > div, .stTextArea textarea {{
            background-color: {NAVY_CARD} !important;
            color: {WHITE} !important;
            border-color: {BORDER} !important;
        }}
        /* Alert / info boxes */
        .stAlert {{
            background-color: {NAVY_CARD} !important;
            color: {WHITE_DIM} !important;
            border: 1px solid {BORDER} !important;
        }}
        /* Native dataframe */
        [data-testid="stDataFrame"] {{
            background-color: {NAVY_CARD};
            border: 1px solid {BORDER};
            border-radius: 6px;
        }}
        /* Native dialog */
        div[role="dialog"] {{
            background-color: {NAVY_CARD} !important;
            color: {WHITE} !important;
            border: 1px solid {BORDER} !important;
        }}
        div[role="dialog"] * {{ color: {WHITE} !important; }}
        /* Spinner */
        .stSpinner > div {{ border-top-color: {ACCENT} !important; }}
        hr {{ border-color: {BORDER} !important; }}
        a {{ color: {ACCENT}; }}
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
        out.append({
            "Ticker":      q.ticker,
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
        "Close":   lambda v: f"${v:.2f}" if pd.notna(v) else "—",
        "Float":   tv_num,
        "Mkt Cap": tv_num,
    })
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
@st.dialog("Catalysts", width="large")
def catalyst_dialog(ticker: str) -> None:
    st.markdown(
        f"<div style='font-size:1.3rem;font-weight:700;color:{WHITE};'>"
        f"{ticker} — Recent Catalysts</div>",
        unsafe_allow_html=True,
    )
    with st.spinner("Loading news…"):
        data = fetch_catalysts(ticker)
    if not data:
        st.info("No recent news found for this ticker.")
        if st.button("Close", key="close_empty"):
            st.session_state.selected_ticker = None
            st.rerun()
        return

    for item in data:
        chg = item.get("change_pct")
        if chg is not None:
            color = GOOD if chg >= 0 else DANGER
            sign = "+" if chg >= 0 else ""
            badge = f"<span style='color:{color};font-weight:700;'>{sign}{chg:.2f}%</span>"
        else:
            badge = f"<span style='color:{WHITE_MUTE};'>--</span>"
        dt = item.get("datetime")
        dt_str = dt.strftime("%b %d, %Y %I:%M %p") if dt else ""
        pub = item.get("publisher") or ""
        ohlcv = " &nbsp; ".join(
            f"{k}: ${item[v]:.2f}" if item.get(v) is not None else f"{k}: —"
            for k, v in [("O","open"),("H","high"),("L","low"),("C","close")]
        )
        vol = f"Vol: {tv_num(item['volume'])}" if item.get("volume") is not None else "Vol: —"
        st.markdown(
            f"""<div style="padding:12px 0;border-bottom:1px solid {BORDER};">
              <div style="display:flex;gap:12px;align-items:center;margin-bottom:4px;">
                {badge}
                <span style="color:{WHITE_MUTE};font-size:0.78rem;">{dt_str}</span>
                {f'<span style="color:{WHITE_MUTE};font-size:0.78rem;">| {pub}</span>' if pub else ''}
              </div>
              <a href="{item.get('link','#')}" target="_blank" style="
                  color:{ACCENT};font-weight:500;text-decoration:none;
                  display:block;margin-bottom:6px;">{item.get('title','')}</a>
              <div style="color:{WHITE_MUTE};font-size:0.8rem;">{ohlcv} &nbsp; {vol}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    if st.button("Close", key="close_dlg"):
        st.session_state.selected_ticker = None
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

    # Ticker picker for catalyst drill-in
    tickers = [q.ticker for q in rows]
    picker_col, btn_col = st.columns([4, 1])
    with picker_col:
        sel = st.selectbox(
            "View catalysts for ticker",
            options=["—"] + tickers,
            key=f"picker_{folder}",
            label_visibility="collapsed",
        )
    with btn_col:
        if st.button("View catalysts", key=f"view_{folder}", use_container_width=True):
            if sel and sel != "—":
                st.session_state.selected_ticker = sel
                st.rerun()
            else:
                st.toast("Pick a ticker first.")

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
            )
            selected_folder = next(
                k for k, (l, _, _) in branches.items() if l == selected_label
            )

            st.divider()
            if st.button("Refresh quotes", use_container_width=True):
                st.cache_data.clear()
                st.toast("Quotes cache cleared.")
                st.rerun()
            st.caption(
                f"Last load: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

        st.markdown(
            f"""<div style="margin-top:24px;padding-top:14px;
              border-top:1px solid {BORDER};">
              <q style="color:{WHITE_MUTE};font-size:0.78rem;
                font-style:italic;line-height:1.5;">
                Be fearful when others are greedy, and greedy when others
                are fearful.</q>
              <cite style="color:{WHITE_MUTE};font-size:0.72rem;
                display:block;margin-top:6px;">— Warren Buffett</cite>
            </div>""",
            unsafe_allow_html=True,
        )

    if is_journal:
        render_journal()
        return

    uni_mod = {
        "Biotechnology": bio_universe,
        "Technology":    tech_universe,
        "Energy":        energy_universe,
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
          Float &lt; {MAX_FLOAT/1_000_000:.0f}M &nbsp;·&nbsp;
          {ticker_count}</div>""",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading market data…"):
        by_cat = filtered_by_category(uni_mod.UNIVERSE(), uni_mod.all_tickers())

    render_sector(main_cat, selected_folder, by_cat.get(selected_folder, []), uni_mod.INFO)

    # Open catalyst dialog if a ticker is selected
    if st.session_state.selected_ticker:
        catalyst_dialog(st.session_state.selected_ticker)


if __name__ == "__main__":
    main()
