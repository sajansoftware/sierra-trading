"""Aidan — QA agent for the catalyst classifier.

Walks every ticker's catalyst headlines, runs each through the
classify_catalyst() pipeline, and flags rows that returned 'No news'
but contain biotech / corporate signal keywords. For each flagged
row Aidan proposes:
  - the catalyst type the row should probably be
  - the specific phrase from the headline that triggered the proposal
    (i.e. the keyword to add to CATALYST_KEYWORDS)

Use this to grow the classifier coverage with real-world examples,
not guesses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Per-type heuristic signal words. Distinct from the strict
# CATALYST_KEYWORDS list - these are *broader* terms that hint at
# the category. When a 'No news' row contains one of these, Aidan
# suggests the corresponding type as a likely classification and
# recommends the matched phrase as a new keyword.
SIGNAL_WORDS: dict[str, list[str]] = {
    "Clinical Data":  [
        "clinical benefit", "patient data", "patient response",
        "aml", "nhl", "her2", "kras", "egfr", "br-cancer",
        "delivers", "response rate", "objective response",
        "complete response", "partial response", "duration of response",
        "patient outcomes", "efficacy", "safety profile",
        "patients treated", "evaluable patients",
        "clinical update", "trial update", "pivotal", "registrational",
        "open-label", "double-blind", "randomized", "single-arm",
        "cohort", "first-in-human",
    ],
    "FDA Meeting":    [
        "regulatory milestone", "regulatory pathway",
        "fda communication", "fda discussion", "agency feedback",
        "agency meeting", "with the agency", "agency interaction",
        "scientific advice", "ema meeting", "european medicines agency",
    ],
    "FDA Approval":   [
        "approval granted", "approval received", "regulatory approval",
        "marketing approval", "european commission approves",
    ],
    "Designation":    [
        "designation", "rmat", "qidp", "prv", "pediatric voucher",
        "regenerative medicine", "expanded access",
    ],
    "Partnership":    [
        "strategic agreement", "research collaboration",
        "supply agreement", "manufacturing agreement",
        "exclusive license", "non-exclusive license",
        "co-promotion", "co-development",
    ],
    "Buyout / Rumor": [
        "exploring options", "strategic review", "tender offer",
        "definitive agreement to acquire", "private equity",
        "going private",
    ],
    "Offering":       [
        "underwritten offering", "share sale", "secondary",
        "raising capital", "capital raise",
    ],
    "Earnings":       [
        "annual results", "fy results", "interim results",
        "h1 results", "h2 results", "1h results", "2h results",
    ],
    "Insider Buy":    [
        "10b5-1", "form 4", "purchases shares", "bought shares",
    ],
    "Reverse Split":  [
        "split ratio", "consolidation of shares",
        "share consolidation",
    ],
    "Conference":     [
        "investor day", "r&d day", "key opinion leader",
        "kol event", "scientific conference", "annual meeting",
    ],
    "Patent":         [
        "patent application", "patent allowance", "patent issuance",
        "patent extension", "ip portfolio",
    ],
    "Listing":        [
        "lists on", "begins trading", "trading symbol",
    ],
}

# Drug-name pattern: capitalized word ending in -mab, -tinib, -nib,
# -mig, -mig, -ide, -ix etc. - a strong signal of biotech clinical news.
DRUG_SUFFIX_RE = re.compile(
    r"\b[A-Z][a-zA-Z]*"
    r"(mab|tinib|nib|mig|cept|umab|olimus|tide|tolimod|imab|cycline"
    r"|stat|fenib|gliflozin|prazole|sartan|olol|vir|trel|relbant|profen)\b"
)


@dataclass(frozen=True)
class QASuggestion:
    ticker: str
    date: str          # YYYY-MM-DD or readable date
    headline: str
    current_type: str
    suggested_type: str
    matched_phrase: str   # the substring that triggered the suggestion
    source: str


def suggest_type(headline: str) -> tuple[str, str]:
    """Return (suggested_type, matched_phrase) for an unclassified
    headline, or ('', '') if no signal found.

    Strategy:
      1. Walk SIGNAL_WORDS in dict order; first match wins. Distinct
         signal phrases are biased toward biotech-specific terms so
         we don't false-positive on generic words like 'study'.
      2. If no signal phrase matches, check for a drug-name suffix
         (-mab, -tinib, ...) and suggest Clinical Data.
    """
    t = (headline or "").lower()
    if not t:
        return "", ""
    for sector, words in SIGNAL_WORDS.items():
        for w in words:
            if w in t:
                return sector, w
    m = DRUG_SUFFIX_RE.search(headline or "")
    if m:
        return "Clinical Data", m.group(0)
    return "", ""


def audit_rows(rows: list[dict], ticker: str) -> list[QASuggestion]:
    """Apply the QA pass to a list of catalyst rows for one ticker."""
    out: list[QASuggestion] = []
    for r in rows:
        current = r.get("type", "")
        if current not in ("No news", "Press Release"):
            continue
        title = r.get("title", "") or r.get("catalyst", "") or ""
        if not title:
            continue
        suggested, phrase = suggest_type(title)
        if not suggested:
            continue
        date_v = r.get("date", "")
        date_s = date_v.isoformat() if hasattr(date_v, "isoformat") else str(date_v)
        out.append(QASuggestion(
            ticker=ticker,
            date=date_s,
            headline=title,
            current_type=current,
            suggested_type=suggested,
            matched_phrase=phrase,
            source=r.get("source") or "",
        ))
    return out
