"""Sierra Voice — knowledge-base agent.

Server-side helpers that assemble a context payload for the browser-side
voice widget. The widget itself (HTML/JS in app.py) does intent
matching and lookup against this payload, so responses are instant
and entirely offline — no API calls.

Contents of the payload:
  - kb_terms     : trading-concept definitions (RVOL, VWAP, gap-and-go,
                   etc.) — the actual "knowledge base"
  - faq          : common short questions about the dashboard itself
  - sectors      : list of sector names available in the screen
  - tickers      : flat list of every curated ticker the dashboard knows
                   about, mapped to its sector + sub-sector folder so
                   "tell me about XYZ" can return real info
  - criteria     : the screen rules as plain English
"""

from __future__ import annotations

from typing import Iterable


# ---------------------------------------------------------------------------
# Trading concept definitions
# ---------------------------------------------------------------------------
TRADING_KB: dict[str, str] = {
    "rvol": (
        "Relative Volume — today's volume divided by the average volume "
        "over a lookback period. RVOL above 2 means the stock is trading "
        "twice its usual flow; above 5 is a momentum-trader's signal that "
        "something has changed."
    ),
    "vwap": (
        "Volume Weighted Average Price — the running average of price "
        "weighted by share volume since the open. Traders use VWAP as a "
        "fair-value benchmark; reclaims above VWAP after a flush are a "
        "common long setup."
    ),
    "float": (
        "Float — the number of freely tradable shares, excluding "
        "insider-held and restricted stock. Micro-floats under 20 million "
        "shares move violently on volume because supply is thin."
    ),
    "short interest": (
        "Short Interest — the number of shares sold short and not yet "
        "covered. High short interest plus a positive catalyst is the "
        "setup for a short squeeze."
    ),
    "days to cover": (
        "Days to Cover — short interest divided by average daily volume. "
        "A high reading means shorts can't exit quickly, raising squeeze "
        "risk."
    ),
    "borrow rate": (
        "Borrow Rate — the annualized fee a short seller pays to borrow "
        "shares. Triple-digit borrow rates flag a hard-to-borrow stock "
        "primed for a squeeze."
    ),
    "gap and go": (
        "Gap and Go — a momentum setup where a stock gaps up on news, "
        "holds above the open, and continues higher. Entries trigger on "
        "the first one-minute high break with volume."
    ),
    "vwap reclaim": (
        "VWAP Reclaim — entering long after a stock that broke below "
        "VWAP intraday pushes back above it. Confirmation is volume and "
        "a clean retest from above."
    ),
    "parabolic short": (
        "Parabolic Short — fading a stock that has extended too far, too "
        "fast above a moving average or VWAP. High risk; size small and "
        "use mechanical stops."
    ),
    "halt resumption": (
        "Halt Resumption — playing the first move after a Limit-Up-Limit-"
        "Down or news halt lifts. Direction usually continues for the "
        "first one to five minutes."
    ),
    "orb": (
        "Opening Range Breakout — buying the break of the first five or "
        "fifteen-minute range. Works best on names with a pre-market "
        "catalyst and clean opening range."
    ),
    "news fade": (
        "News Fade — shorting a parabolic move after a stale or weak "
        "catalyst. Requires the move to top out before sizing in."
    ),
    "pdt": (
        "Pattern Day Trader rule — four or more day trades in five "
        "business days on a margin account under twenty-five thousand "
        "dollars flags PDT and locks day trading for ninety days."
    ),
    "pdufa": (
        "Prescription Drug User Fee Act date — the FDA's target action "
        "date for approving or rejecting a drug application. Major "
        "biotech catalyst."
    ),
    "crl": (
        "Complete Response Letter — the FDA's rejection of a drug "
        "application. Highly bearish, usually triggers a gap-down."
    ),
    "510k": (
        "510(k) Clearance — the FDA pathway for medical devices "
        "demonstrating substantial equivalence to an existing product. "
        "Less heavy than a full approval but still a real catalyst."
    ),
    "atm offering": (
        "At-The-Market Offering — a continuous secondary stock sale at "
        "current market prices. Dilutive, usually triggers a gap-down."
    ),
    "reverse split": (
        "Reverse Split — consolidating shares to lift the price, usually "
        "to regain Nasdaq one-dollar minimum bid compliance. Bearish "
        "signal; the underlying business hasn't changed."
    ),
    "uplisting": (
        "Uplisting — moving from OTC to Nasdaq or NYSE. Often triggers a "
        "rally on improved liquidity and institutional eligibility."
    ),
    "8-k": (
        "8-K — the SEC form a public company files to disclose material "
        "events: M&A, leadership change, bankruptcy, results. Real-time "
        "catalyst source on EDGAR."
    ),
    "13d": (
        "Schedule 13D — filed when an investor crosses a 5 percent "
        "ownership threshold with intent to influence. Activist signal."
    ),
    "form 4": (
        "Form 4 — insider trade disclosure within two business days. "
        "Cluster buys by insiders are a bullish tell."
    ),
    "ind": (
        "Investigational New Drug application — the FDA filing that lets "
        "a company start human trials. IND clearance is a clinical "
        "milestone."
    ),
    "nda": (
        "New Drug Application — the FDA submission seeking marketing "
        "approval for a finished drug. Acceptance starts the PDUFA clock."
    ),
    "bla": (
        "Biologics License Application — the FDA submission for biologic "
        "products. Same role as an NDA but for biologics."
    ),
    "topline data": (
        "Topline Data — the headline primary-endpoint result from a "
        "clinical trial, released before full publication. Most "
        "tradeable biotech catalyst."
    ),
    "primary endpoint": (
        "Primary Endpoint — the main outcome a trial is designed to "
        "measure. Hitting it usually means the program advances."
    ),
    "burn rate": (
        "Burn Rate — quarterly cash consumption. Combined with cash on "
        "hand it tells you runway. Short runway plus dilution risk is a "
        "bearish bias."
    ),
    "runway": (
        "Runway — months of cash remaining at current burn. Below twelve "
        "months almost guarantees a near-term offering."
    ),
    "rs": (
        "Relative Strength — performance versus a benchmark like the "
        "Russell 2000. Top-decile RS names lead in trending markets."
    ),
    "kill switch": (
        "Kill Switch — a hard daily loss limit that halts trading once "
        "hit. Stops bad days from becoming bad weeks."
    ),
}


# ---------------------------------------------------------------------------
# Frequently-asked dashboard questions
# ---------------------------------------------------------------------------
FAQ: list[dict] = [
    {
        "q": ["what is the screen", "what's the criteria", "what's the screen",
              "screen rules", "what filter"],
        "a": ("The screen is: price between one and twenty dollars, free "
              "float under twenty million shares, listed on NASDAQ, NYSE, "
              "or AMEX."),
    },
    {
        "q": ["what can you do", "help", "what do you know",
              "what can i ask"],
        "a": ("I cover trading terminology — RVOL, VWAP, float, "
              "short interest, gap-and-go, VWAP reclaim, parabolic short, "
              "halt resumption, and roughly thirty more concepts. I also "
              "know the dashboard's sector list, the current screen "
              "criteria, and every curated ticker in the universe. Ask "
              "me to define a term, list sectors, or tell me about a "
              "specific ticker."),
    },
    {
        "q": ["who are you", "what are you", "your name"],
        "a": ("I'm Sierra Voice — the dashboard's knowledge-base agent. "
              "Trading terminology, screen rules, and ticker lookup, all "
              "by voice."),
    },
    {
        "q": ["what sectors", "list sectors", "what sectors do you cover"],
        "a": "I cover all eleven GICS sectors. Ask me for the list.",
    },
]


def build_payload(sectors_dict: dict, universe_modules: Iterable) -> dict:
    """Assemble the JSON-serializable payload the browser widget consumes."""
    sectors = list(sectors_dict.keys())

    # Flatten curated tickers across all sector universes. Cheap — just
    # dict-keys reads.
    tickers: dict[str, dict] = {}
    for mod in universe_modules:
        info = getattr(mod, "INFO", None) or {}
        for sym, meta in info.items():
            tickers.setdefault(sym, {
                "name": getattr(meta, "name", sym),
                "blurb": getattr(meta, "blurb", ""),
            })

    return {
        "kb_terms": TRADING_KB,
        "faq": FAQ,
        "sectors": sectors,
        "tickers": tickers,
        "criteria": ("Price between one and twenty dollars. Free float "
                     "under twenty million shares. Listed on NASDAQ, "
                     "NYSE, or AMEX."),
    }
