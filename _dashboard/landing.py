"""Momentus — public landing page and authentication gate."""

from __future__ import annotations

import hashlib

import streamlit as st

# Palette (matches app.py navy theme)
NAVY = "#0a1929"
NAVY_CARD = "#102841"
BORDER = "#1e3a5f"
WHITE = "#ffffff"
WHITE_DIM = "#e2e8f0"
WHITE_MUTE = "#94a3b8"
ACCENT = "#64b5f6"
GOOD = "#22c55e"


def render_landing_page() -> None:
    """Full-width marketing page for unauthenticated visitors."""
    st.markdown(
        f"""<style>
        .landing-hero {{
            text-align: center;
            padding: 80px 20px 40px;
        }}
        .landing-hero h1 {{
            font-size: 3.2rem;
            font-weight: 800;
            letter-spacing: -1px;
            margin-bottom: 12px;
        }}
        .landing-hero .tagline {{
            font-size: 1.15rem;
            color: {WHITE_DIM} !important;
            max-width: 600px;
            margin: 0 auto 32px;
            line-height: 1.6;
        }}
        .feature-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            max-width: 900px;
            margin: 0 auto 48px;
            padding: 0 20px;
        }}
        @media (max-width: 768px) {{
            .feature-grid {{ grid-template-columns: 1fr; }}
            .landing-hero h1 {{ font-size: 2.2rem; }}
        }}
        .feature-card {{
            background: {NAVY_CARD};
            border: 1px solid {BORDER};
            border-radius: 10px;
            padding: 24px 20px;
            text-align: center;
        }}
        .feature-card .feat-icon {{
            font-size: 2rem;
            margin-bottom: 10px;
        }}
        .feature-card .feat-title {{
            font-size: 1rem;
            font-weight: 700;
            color: {WHITE} !important;
            margin-bottom: 6px;
        }}
        .feature-card .feat-desc {{
            font-size: 0.85rem;
            color: {WHITE_MUTE} !important;
            line-height: 1.5;
        }}
        .pricing-section {{
            text-align: center;
            padding: 40px 20px;
        }}
        .pricing-card {{
            background: {NAVY_CARD};
            border: 2px solid {ACCENT};
            border-radius: 12px;
            padding: 32px 28px;
            max-width: 380px;
            margin: 0 auto;
        }}
        .pricing-card .price {{
            font-size: 2.8rem;
            font-weight: 800;
            color: {WHITE} !important;
            margin-bottom: 4px;
        }}
        .pricing-card .price-period {{
            font-size: 0.9rem;
            color: {WHITE_MUTE} !important;
            margin-bottom: 4px;
        }}
        .pricing-card .trial-badge {{
            display: inline-block;
            background: {ACCENT};
            color: #06121e !important;
            font-weight: 700;
            font-size: 0.78rem;
            padding: 4px 12px;
            border-radius: 20px;
            margin-bottom: 18px;
        }}
        .pricing-card .check-list {{
            text-align: left;
            list-style: none;
            padding: 0;
            margin: 0 0 24px;
        }}
        .pricing-card .check-list li {{
            padding: 6px 0;
            font-size: 0.9rem;
            color: {WHITE_DIM} !important;
        }}
        .pricing-card .check-list li::before {{
            content: "\\2713";
            color: {GOOD};
            font-weight: 700;
            margin-right: 10px;
        }}
        </style>

        <div class="landing-hero">
            <h1>Momentus</h1>
            <div class="tagline">
                Your pre-market edge. Real-time sector scanning, catalyst
                tracking, and backtesting — built for small-cap traders who
                move before the open.
            </div>
        </div>

        <div class="feature-grid">
            <div class="feature-card">
                <div class="feat-icon">&#x1F4CA;</div>
                <div class="feat-title">Sector Scanner</div>
                <div class="feat-desc">
                    Live screening across 11 GICS sectors with float, price,
                    and catalyst filters. Penny watchlist included.
                </div>
            </div>
            <div class="feature-card">
                <div class="feat-icon">&#x1F916;</div>
                <div class="feat-title">AI Research</div>
                <div class="feat-desc">
                    Stan clusters today's catalysts and sector momentum into
                    actionable market themes — automatically.
                </div>
            </div>
            <div class="feature-card">
                <div class="feat-icon">&#x1F4C8;</div>
                <div class="feat-title">Backtesting</div>
                <div class="feat-desc">
                    Six-month archive of every 100%+ pre-market move across
                    the full US-listed universe, with source links.
                </div>
            </div>
        </div>

        <div class="pricing-section">
            <div style="font-size:0.78rem;color:{WHITE_MUTE};text-transform:uppercase;
                         letter-spacing:1px;margin-bottom:10px;">Pricing</div>
            <div class="pricing-card">
                <div class="price">$29</div>
                <div class="price-period">per month</div>
                <div class="trial-badge">7-day free trial</div>
                <ul class="check-list">
                    <li>Real-time pre-market scanner</li>
                    <li>11 GICS sector dashboards</li>
                    <li>AI-powered market themes</li>
                    <li>100%+ move backtesting archive</li>
                    <li>IPO calendar with deal data</li>
                    <li>Trading journal & P&L tracking</li>
                    <li>Penny watchlist (sub-$1)</li>
                    <li>Alert sounds for new movers</li>
                </ul>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # CTA button — switch to auth form
    _c1, c2, _c3 = st.columns([1, 1, 1])
    with c2:
        if st.button(
            "Get Started",
            use_container_width=True,
            type="primary",
            key="landing_cta",
        ):
            st.session_state.show_auth = True
            st.rerun()


def render_auth_form() -> bool:
    """Centered login form. Returns True if the user is authenticated."""
    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        f"""<div style="text-align:center;padding:60px 20px 20px;">
            <div style="font-size:1.8rem;font-weight:800;color:{WHITE};
                        margin-bottom:6px;">Momentus</div>
            <div style="font-size:0.9rem;color:{WHITE_MUTE};
                        margin-bottom:32px;">Sign in to access the dashboard</div>
        </div>""",
        unsafe_allow_html=True,
    )

    _l, center, _r = st.columns([1, 1.2, 1])
    with center:
        with st.form("auth_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button(
                "Sign in", use_container_width=True, type="primary",
            )

        if submitted:
            if _verify_credentials(email.strip().lower(), password):
                st.session_state.authenticated = True
                st.session_state.user_email = email.strip().lower()
                st.session_state.show_auth = False
                st.rerun()
            else:
                st.error("Invalid email or password.")

        # Back to landing
        if st.button("Back", key="back_to_landing", use_container_width=True):
            st.session_state.show_auth = False
            st.rerun()

    return False


def _verify_credentials(email: str, password: str) -> bool:
    """Check email + SHA-256(password) against st.secrets['auth']."""
    try:
        auth = st.secrets["auth"]
    except Exception:
        return False

    stored_hash = auth.get(email)
    if not stored_hash:
        return False

    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return password_hash == stored_hash
