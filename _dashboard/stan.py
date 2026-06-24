"""Stan — Research AI Employee for Momentus.

Scans the universe for emerging market themes by clustering catalysts
and sector performance data. Pure-function module following the mia.py
pattern: takes data in, returns analysis dicts. UI lives in
app.render_stan_research().
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, date

import requests
import streamlit as st
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Theme:
    rank: int
    name: str
    description: str
    tickers: list[str]
    headlines: list[str]
    catalyst_type: str
    count: int
    sector: str


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


@st.cache_data(ttl=900, show_spinner=False)  # 15 min
def fetch_market_themes() -> dict:
    """Scrape Finviz homepage for sector performance and trending tickers.

    Returns dict with keys:
      - sector_perf: list of {sector, change_pct}
      - trending: list of ticker strings from the homepage ticker bar
    """
    sector_perf: list[dict] = []
    trending: list[str] = []
    try:
        resp = requests.get(
            "https://finviz.com/groups.ashx?g=sector&v=110&o=name",
            headers={"User-Agent": UA},
            timeout=12,
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            for row in soup.select("table.table-light tr"):
                cells = row.find_all("td")
                if len(cells) >= 3:
                    name = cells[1].get_text(strip=True)
                    chg = cells[2].get_text(strip=True).replace("%", "")
                    try:
                        sector_perf.append({
                            "sector": name,
                            "change_pct": float(chg),
                        })
                    except ValueError:
                        continue
    except Exception:
        pass

    try:
        resp2 = requests.get(
            "https://finviz.com",
            headers={"User-Agent": UA},
            timeout=10,
        )
        if resp2.status_code == 200:
            soup2 = BeautifulSoup(resp2.text, "lxml")
            for a in soup2.select("a.tab-link"):
                txt = a.get_text(strip=True).upper()
                if txt and len(txt) <= 6 and txt.isalpha():
                    trending.append(txt)
    except Exception:
        pass

    return {
        "sector_perf": sector_perf,
        "trending": trending[:30],
    }


def identify_themes(
    catalyst_data: list[dict],
    market_themes: dict,
) -> list[Theme]:
    """Group catalysts by type + sector, cluster themes with >= 3 tickers.

    Args:
        catalyst_data: list of dicts with keys: ticker, catalyst_type,
                       headline, sector
        market_themes: output of fetch_market_themes()

    Returns top 3 Theme objects ranked by frequency.
    """
    # Group by (catalyst_type, sector)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in catalyst_data:
        key = (c.get("catalyst_type") or "News", c.get("sector") or "Other")
        groups[key].append(c)

    themes: list[Theme] = []
    for (ctype, sector), items in groups.items():
        tickers = list({c["ticker"] for c in items})
        if len(tickers) < 3:
            continue
        headlines = [c.get("headline") or "" for c in items if c.get("headline")][:5]
        themes.append(Theme(
            rank=0,
            name=f"{ctype} in {sector}",
            description=(
                f"{len(tickers)} tickers in {sector} with {ctype} catalysts "
                f"today."
            ),
            tickers=tickers[:10],
            headlines=headlines,
            catalyst_type=ctype,
            count=len(tickers),
            sector=sector,
        ))

    # Also check for sector-level momentum from Finviz
    for sp in (market_themes.get("sector_perf") or []):
        chg = sp.get("change_pct", 0)
        sec_name = sp.get("sector", "")
        if abs(chg) >= 2.0:
            direction = "rally" if chg > 0 else "selloff"
            trending_in_sector = [
                t for t in (market_themes.get("trending") or [])
            ][:5]
            themes.append(Theme(
                rank=0,
                name=f"{sec_name} sector {direction}",
                description=(
                    f"{sec_name} is {'up' if chg > 0 else 'down'} "
                    f"{abs(chg):.1f}% today — a notable sector-wide move."
                ),
                tickers=trending_in_sector,
                headlines=[],
                catalyst_type="Sector Move",
                count=1,
                sector=sec_name,
            ))

    # Rank by count (more tickers = stronger theme)
    themes.sort(key=lambda t: -t.count)
    ranked = []
    for i, t in enumerate(themes[:3]):
        ranked.append(Theme(
            rank=i + 1,
            name=t.name,
            description=t.description,
            tickers=t.tickers,
            headlines=t.headlines,
            catalyst_type=t.catalyst_type,
            count=t.count,
            sector=t.sector,
        ))
    return ranked


def compile_research(
    universe_pool: list[str] | tuple[str, ...],
    sector_lookup: dict[str, tuple[str, str]],
) -> dict:
    """Orchestrator — fetches today's catalysts for universe tickers.

    Returns {"themes": [...], "generated_at": datetime,
             "tickers_scanned": int, "sector_perf": [...]}
    """
    market_themes = fetch_market_themes()

    # Build catalyst data from today's news for universe tickers
    catalyst_data: list[dict] = []
    try:
        from data import classify_catalyst
        from news_sources import fetch_finviz_news
        today = date.today()

        # Sample a subset to avoid rate limits
        sample = list(universe_pool)[:200]
        for tkr in sample:
            try:
                items = fetch_finviz_news(tkr)
                todays = [n for n in items if n.get("date") == today]
                if todays:
                    best = todays[0]
                    sec_sub = sector_lookup.get(tkr)
                    sector_name = sec_sub[0] if sec_sub else "Other"
                    catalyst_data.append({
                        "ticker": tkr,
                        "catalyst_type": classify_catalyst(best.get("title", "")),
                        "headline": best.get("title", ""),
                        "sector": sector_name,
                    })
            except Exception:
                continue
    except Exception:
        pass

    themes = identify_themes(catalyst_data, market_themes)

    return {
        "themes": themes,
        "generated_at": datetime.now(),
        "tickers_scanned": len(universe_pool),
        "sector_perf": market_themes.get("sector_perf", []),
    }
