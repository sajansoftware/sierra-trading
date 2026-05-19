"""Sentiment classifier for catalyst headlines.

Rule-based NLP classifier that maps a headline to one of:
  - Bullish
  - Bearish
  - Neutral

Bullish keywords vote +1, bearish vote -1. Net score >0 = Bullish,
<0 = Bearish, 0 = Neutral. Keyword lists below cover the small-cap
catalyst patterns we see in the dashboard's news sources.
"""

from __future__ import annotations


BULLISH_KEYWORDS: list[str] = [
    "fda approval", "fda approves", "approves", "approved",
    "510(k)", "ce mark", "marketing authorization", "breakthrough",
    "fast track", "orphan drug", "priority review", "designation",
    "met endpoint", "met primary", "primary endpoint", "topline",
    "positive data", "positive results", "positive interim",
    "demonstrates efficacy", "shows efficacy", "exceeds expectations",
    "clinical benefit", "compelling data", "delivers compelling",
    "promising results", "encouraging results",
    "beats estimates", "beats consensus", "raises guidance",
    "reaffirms guidance", "record revenue", "record results",
    "milestone achievement", "milestone payment",
    "strategic partnership", "exclusive license", "collaboration",
    "definitive agreement", "to acquire", "completed acquisition",
    "buyout offer", "merger agreement", "tender offer",
    "contract win", "contract award", "secures contract",
    "wins contract", "wins funding", "secures funding",
    "uplisting", "lists on nasdaq", "lists on nyse",
    "patent granted", "patent allowance", "patent issued",
    "insider buy", "buyback", "share repurchase",
    "initiates coverage", "upgrade", "raises price target",
    "product launch", "commercial launch", "now available",
    "expands into", "expands product line", "expands operations",
    "regulatory approval", "ind clearance", "ind cleared",
    "nda submission", "bla submission", "files nda", "files bla",
    "strong demand", "increased adoption", "first sale",
]

BEARISH_KEYWORDS: list[str] = [
    "complete response letter", " crl ", "(crl)",
    "fda rejects", "rejects approval", "approval delay",
    "halts trial", "halted trial", "trial halt", "study terminated",
    "missed endpoint", "missed primary", "failed primary",
    "negative data", "disappointing data", "discontinues",
    "discontinuation", "withdrawal", "withdraws", "recall",
    "voluntary recall", "fda warning", "warning letter",
    "delisting", "delisting notice", "notice of delisting",
    "non-compliance", "minimum bid price",
    "going concern", "substantial doubt", "auditor",
    "non-reliance", "restatement", "material weakness",
    "lawsuit", "class action", "securities investigation",
    "subpoena", "doj investigation", "sec investigation",
    "downgrade", "lowers guidance", "lowers price target",
    "misses estimates", "misses consensus", "revenue miss",
    "earnings miss", "loss widens",
    "registered direct", " atm offering", "atm offering",
    "public offering", "follow-on offering", "secondary offering",
    "underwritten offering",
    "warrant exercise", "dilution", "private placement",
    "convertible debt", "convertible notes", "reverse split",
    "reverse stock split", "stock consolidation",
    "bankruptcy", "chapter 11", "chapter 7", "receivership",
    "going private", "ceo resigns", "cfo resigns",
    "layoffs", "restructuring", "impairment",
]


def classify_sentiment(headline: str) -> str:
    """Return 'Bullish', 'Bearish', or 'Neutral' for the given headline."""
    if not headline:
        return "Neutral"
    t = headline.lower()
    bull_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in t)
    bear_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in t)
    if bull_hits > bear_hits:
        return "Bullish"
    if bear_hits > bull_hits:
        return "Bearish"
    return "Neutral"
