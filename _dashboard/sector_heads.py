"""Sector Heads — AI employees, one per GICS top-level sector.

Each head is a specialist agent with their own persona, expertise list,
and intro. The reply() function is a rule-based contextual responder
that leans on the dashboard's live data (qualifying tickers, INFO
blurbs, recent changelog events) to answer questions about that
sector. The intent is a small, fast, deterministic chat overlay that
can later be swapped for an LLM-backed implementation without changing
the call site.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SectorHead:
    name: str
    sector: str
    title: str
    expertise: tuple[str, ...]
    intro: str
    persona: str   # one-line style guide for future LLM use


HEADS: dict[str, SectorHead] = {
    "Technology": SectorHead(
        name="Mike",
        sector="Technology",
        title="Head of Technology",
        expertise=("Semiconductors", "Software/SaaS", "Cloud", "AI/ML",
                   "Cybersecurity", "Consumer Electronics", "Fintech",
                   "Telecom", "IT Services"),
        intro=("Mike here. I run the Tech desk — semis, SaaS, AI, "
               "cyber, cloud. Ask me about any small-cap tech name "
               "in the screen, recent changes, or what's catalyst-rich."),
        persona="Direct, technical, allergic to hype. Quotes revenue "
                "multiples and burn instead of narratives.",
    ),
    "Communication Services": SectorHead(
        name="John",
        sector="Communication Services",
        title="Head of Communication Services",
        expertise=("Telecom", "Media & Entertainment", "Streaming",
                   "Advertising", "Social platforms", "Publishing"),
        intro=("John, Comm Services. Telcos, media, ad-tech, "
               "streaming, social. What do you want to dig into?"),
        persona="Old-school media operator. Talks ARPU, churn, ad CPMs.",
    ),
    "Consumer Discretionary": SectorHead(
        name="Michael",
        sector="Consumer Discretionary",
        title="Head of Consumer Discretionary",
        expertise=("Retail", "Apparel", "Automotive/EVs",
                   "Restaurants", "Travel", "Gaming", "E-commerce"),
        intro=("Michael, Consumer Discretionary. Retail, apparel, "
               "autos, restaurants, travel, gaming. What's the trade?"),
        persona="Consumer-spend tracker. Watches credit card data, "
                "foot traffic, and inventory days.",
    ),
    "Consumer Staples": SectorHead(
        name="Jason",
        sector="Consumer Staples",
        title="Head of Consumer Staples",
        expertise=("Food & Beverage", "Alt-protein", "Household",
                   "Personal Care", "Tobacco/Vape", "Grocery"),
        intro=("Jason, Staples. Food, beverage, household, beauty, "
               "tobacco. Mostly defensive but the small-caps move."),
        persona="Margin-focused. Talks input costs, shelf space, "
                "private-label encroachment.",
    ),
    "Health Care": SectorHead(
        name="Edward",
        sector="Health Care",
        title="Head of Health Care",
        expertise=("Biotech (Red/Green/White/Blue/Grey/Yellow/Gold)",
                   "Pharma", "Medical Devices", "Hospitals",
                   "Health Insurance", "Healthcare IT", "Telehealth",
                   "Pharmacy & Distributors"),
        intro=("Edward — Health Care desk. Biotech across the seven-color "
               "framework plus the services side. FDA cycles are my "
               "calendar. What name are you looking at?"),
        persona="Catalyst-driven. Quotes PDUFA dates, primary endpoints, "
                "p-values, and cash runway.",
    ),
    "Financials": SectorHead(
        name="Jamie",
        sector="Financials",
        title="Head of Financials",
        expertise=("Regional Banks", "Investment Banks", "Asset Mgmt",
                   "Insurance", "Fintech/Payments", "BDCs",
                   "Specialty Finance", "Crypto-adjacent"),
        intro=("Jamie, Financials. Banks, brokers, insurers, fintech, "
               "BDCs, crypto-adjacent. NIM and credit are the levers."),
        persona="Balance-sheet eye. Talks NIM, efficiency ratio, "
                "tangible book, and credit cost.",
    ),
    "Industrials": SectorHead(
        name="Werner",
        sector="Industrials",
        title="Head of Industrials",
        expertise=("Aerospace & Defense", "Machinery", "Transportation",
                   "Construction & Engineering", "Electrical Equipment",
                   "Industrial Services"),
        intro=("Werner, Industrials. Aerospace, machinery, trucking, "
               "rail, electrical, construction. Capex cycles are my "
               "weather report."),
        persona="Cycle-aware. Quotes book-to-bill, backlog, PMI, "
                "and ISM new orders.",
    ),
    "Materials": SectorHead(
        name="Kasey",
        sector="Materials",
        title="Head of Materials",
        expertise=("Precious Metals", "Battery/Critical Metals",
                   "Rare Earth", "Uranium", "Base Metals", "Steel",
                   "Specialty Chemicals", "Construction Materials"),
        intro=("Kasey, Materials. Miners, metals, chemicals — gold, "
               "silver, copper, lithium, uranium, rare earths. "
               "Drill results and offtakes are the catalysts."),
        persona="Commodity-pegged. Talks LME prices, AISC, grades, "
                "and offtake agreements.",
    ),
    "Utilities": SectorHead(
        name="Noah",
        sector="Utilities",
        title="Head of Utilities",
        expertise=("Electric", "Gas", "Water", "Multi-Utilities",
                   "Renewable IPPs"),
        intro=("Noah, Utilities. Regulated electric, gas, water, "
               "multi-utilities, renewable IPPs. Rate cases and PPAs "
               "drive the story."),
        persona="Rate-base mindset. Quotes allowed ROE, rate-base "
                "growth, and PPA tenor.",
    ),
    "Real Estate": SectorHead(
        name="Manny",
        sector="Real Estate",
        title="Head of Real Estate",
        expertise=("Diversified/Residential/Office/Industrial/Data "
                   "Center/Specialty/Mortgage REITs", "Proptech"),
        intro=("Manny, Real Estate. REITs across diversified, "
               "residential, office, industrial, data center, "
               "specialty, mortgage — plus proptech. FFO and "
               "occupancy are the lifeblood."),
        persona="REIT-fluent. Talks FFO/AFFO, cap rates, occupancy, "
                "and same-store NOI.",
    ),
}


# ----------------------------------------------------------------------------
# Reply engine
# ----------------------------------------------------------------------------
TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")


def _intent(prompt: str) -> str:
    p = prompt.lower()
    if any(w in p for w in ("hello", "hi ", "hey", "yo ", "sup", "good morning")):
        return "greet"
    if any(w in p for w in ("help", "what can you")):
        return "help"
    if any(w in p for w in ("sentiment", "tone", "mood", "tape", "skew",
                            "bullish", "bearish", "feeling")):
        return "sentiment"
    if any(w in p for w in ("pattern", "theme", "cluster", "shift",
                            "rotation", "trend")):
        return "patterns"
    if any(w in p for w in ("brief", "read", "what's happening",
                            "what's going on", "update me")):
        return "brief"
    if any(w in p for w in ("list", "names", "universe", "tickers", "what's in",
                            "show me the", "watchlist", "watch list")):
        return "list"
    if any(w in p for w in ("change", "added", "removed", "drop",
                            "new tickers", "what's new")):
        return "changes"
    if any(w in p for w in ("mover", "biggest", "top move", "leaders", "gainer",
                            "loser", "premarket move")):
        return "movers"
    if any(w in p for w in ("catalyst", "news", "why is")):
        return "catalyst"
    if any(w in p for w in ("count", "how many")):
        return "count"
    if any(w in p for w in ("focus", "watch", "pick", "interesting", "best")):
        return "focus"
    return "ticker_or_default"


def _find_ticker(prompt: str, universe: set[str]) -> str | None:
    for tok in TICKER_RE.findall(prompt or ""):
        if tok in universe and tok not in {"AI", "FDA", "CEO", "CFO",
                                            "USA", "US", "PM", "EV", "OK"}:
            return tok
    # Case-insensitive fallback
    for tok in re.findall(r"\b[a-zA-Z]{1,5}\b", prompt or ""):
        if tok.upper() in universe:
            return tok.upper()
    return None


def reply(head: SectorHead, prompt: str, context: dict) -> str:
    """Generate a contextual response from the sector head."""
    if not prompt or not prompt.strip():
        return "I'm listening."

    tickers: list[str] = context.get("tickers") or []
    info_map: dict = context.get("info") or {}
    changelog: list[dict] = context.get("changelog") or []
    sub_folders: list[str] = context.get("sub_folders") or []

    uni_set = set(tickers)
    intent = _intent(prompt)

    # Always check for a specific ticker first; that beats generic intent.
    sym = _find_ticker(prompt, uni_set)
    if sym:
        meta = info_map.get(sym)
        if meta is not None:
            name = getattr(meta, "name", None) or sym
            blurb = getattr(meta, "blurb", None) or ""
            return (f"**{sym} — {name}**. {blurb} "
                    f"Sitting in the {head.sector} screen now. "
                    f"Want me to pull the catalyst stack or recent "
                    f"changelog activity?")
        return (f"**{sym}** is in the {head.sector} universe but I "
                f"don't have a description on file. Click the ticker "
                f"in the table for the catalyst dialog.")

    if intent == "greet":
        return head.intro

    if intent == "help":
        return ("Try: 'what's the sentiment', 'any patterns', 'brief me', "
                "'list tickers', 'top movers', 'what changed', "
                "'tell me about [TICKER]', 'what's the focus today'. "
                "I cover: " + ", ".join(head.expertise) + ".")

    snap = context.get("sentiment")

    if intent in ("brief", "sentiment", "patterns"):
        if snap is None or snap.total < 5:
            return ("Thin headline flow in my desk's window — nothing "
                    "actionable on sentiment yet. Hit Refresh to repull.")
        from sentiment_intel import detect_patterns as _dp
        bullets = _dp(snap)
        head_line = (f"{head.sector} read — {snap.skew} skew "
                     f"({snap.bull} bull / {snap.bear} bear / "
                     f"{snap.neutral} neut over {snap.window_days}d, "
                     f"{snap.n_tickers_with_news}/"
                     f"{snap.n_tickers_scanned} names with news).")
        body = "\n\n• " + "\n\n• ".join(bullets) if bullets else ""
        # Sample headlines
        samples = []
        if intent in ("brief", "sentiment"):
            for t, h in (snap.sample_bull_headlines[:2] +
                         snap.sample_bear_headlines[:2]):
                samples.append(f"_{t}_: {h}")
        sample_block = ("\n\n" + "\n\n".join(samples)) if samples else ""
        return head_line + body + sample_block

    if intent == "count":
        return (f"{len(tickers)} {head.sector} names currently pass the "
                f"$1–$20 + float<20M screen across "
                f"{len(sub_folders)} sub-sectors.")

    if intent == "list":
        if not tickers:
            return "Screen is empty right now — nothing qualifies."
        head_str = ", ".join(tickers[:20])
        more = "" if len(tickers) <= 20 else f" …and {len(tickers)-20} more."
        return (f"{len(tickers)} names in {head.sector}. First 20: "
                f"{head_str}.{more}")

    if intent == "changes":
        sec_events = [e for e in changelog if e.get("sector") == head.sector]
        if not sec_events:
            return ("Nothing on the changelog for my sector yet — "
                    "reload the page to refresh the snapshot.")
        latest = sec_events[:5]
        bits = []
        for e in latest:
            arrow = "▲" if e.get("action") == "added" else "▼"
            bits.append(f"{arrow} {e.get('sym')} — {e.get('reason')}")
        return "Recent moves through the screen:\n\n" + "\n\n".join(bits)

    if intent == "movers":
        movers = context.get("movers") or []
        if not movers:
            return ("No premarket movers cached yet for the sector. "
                    "Hit Today's Top Moves from the sidebar.")
        bits = [f"{m['sym']} {m['move_pct']:+.1f}%" for m in movers[:5]]
        return "Today's leaders in my sector: " + ", ".join(bits) + "."

    if intent == "focus":
        if not tickers:
            return "Nothing in the screen right now to focus on."
        # Pick names with recent additions or active catalysts as proxy
        recent_adds = [
            e.get("sym") for e in changelog
            if e.get("sector") == head.sector and e.get("action") == "added"
        ][:5]
        if recent_adds:
            return ("Names that just entered the screen — fresh setups "
                    "worth a look: " + ", ".join(recent_adds) + ".")
        return ("No fresh adds today. From the current list I'd start "
                f"with the higher-volume tape names: "
                + ", ".join(tickers[:5]) + ".")

    if intent == "catalyst":
        return ("Click any ticker in the sector table to open the "
                "catalyst dialog — it pulls Finviz, Yahoo RSS, and "
                "SEC 8-Ks with sentiment classification.")

    # Default fallback
    return (f"I cover {head.sector}. Try asking about a specific "
            f"ticker, recent changes, top movers, or just say 'list'.")
