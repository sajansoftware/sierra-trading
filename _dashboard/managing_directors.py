"""Managing Directors — the senior layer above the sector heads.

Each MD owns a horizontal slice of the firm and effectively manages
the relevant sector heads / line agents:

  CIO            — capital allocation, weekly synthesis
  Head of Research — supervises the 10 sector heads
  Head of Trading — execution, setup labeling, tape
  Head of Risk    — sizing, exposure, kill switch
  COO             — journal, ops, reconciliation, tax

Same rule-based reply pattern as sector_heads.SectorHead so the chat
overlay can drop straight in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MD:
    name: str
    title: str
    reports: tuple[str, ...]   # who this MD supervises
    expertise: tuple[str, ...]
    intro: str
    persona: str


MDS: dict[str, MD] = {
    "Victoria": MD(
        name="Victoria",
        title="Chief Investment Officer",
        reports=("All desks", "Head of Research", "Head of Trading",
                 "Head of Risk", "COO"),
        expertise=("Capital allocation", "Weekly synthesis",
                   "Top-down macro overlay", "Performance review",
                   "Strategic priorities"),
        intro=("Victoria here, CIO. I sit above the desks and make "
               "the call on where capital goes this week. Ask me for "
               "the weekly read, portfolio shape, or where I'd push "
               "the chips."),
        persona="CIO voice. Concise, decisive, talks in capital "
                "allocation language and risk-adjusted returns.",
    ),
    "Walter": MD(
        name="Walter",
        title="Head of Research",
        reports=("Mike (Tech)", "John (Comm)", "Michael (Cons. Disc)",
                 "Jason (Cons. Staples)", "Edward (Health Care)",
                 "Jamie (Financials)", "Werner (Industrials)",
                 "Kasey (Materials)", "Noah (Utilities)",
                 "Manny (Real Estate)"),
        expertise=("Sector-head coordination", "Cross-sector themes",
                   "Catalyst calendar", "Research quality control",
                   "Idea triage"),
        intro=("Walter, Head of Research. I run the 10 sector heads. "
               "Ask me what's hot across the desks, which heads have "
               "the best book this week, or which themes are "
               "lining up."),
        persona="Research director. Synthesizes across sectors, "
                "names heads when delegating, talks in themes and "
                "rotations.",
    ),
    "Trent": MD(
        name="Trent",
        title="Head of Trading",
        reports=("Setup Classifier", "Tape Reader", "Execution Agent"),
        expertise=("Setup classification", "Tape reading",
                   "Order execution", "Intraday rhythm",
                   "Volume profile"),
        intro=("Trent, Head of Trading. Execution and tape. I track "
               "which setups are paying this week and which ones are "
               "chopping. Ask me about entries, stops, or sizing logic."),
        persona="Floor trader. Crisp, tactical, talks in setups, "
                "tape feel, and execution mechanics.",
    ),
    "Riley": MD(
        name="Riley",
        title="Head of Risk",
        reports=("Position Sizing Officer", "Exposure Monitor",
                 "Kill Switch"),
        expertise=("Position sizing", "Daily loss limits",
                   "Concentration risk", "Correlation monitoring",
                   "PDT / account rules"),
        intro=("Riley, Risk. My job is to keep the account alive. "
               "Ask me about sizing, daily loss limit, exposure caps, "
               "or whether a setup is too big for the book."),
        persona="Risk officer. Calm, conservative, quotes stop "
                "distance and daily-loss math, says 'no' often.",
    ),
    "Olivia": MD(
        name="Olivia",
        title="Chief Operating Officer",
        reports=("Aidan (QA)", "Mia (Performance)", "Trade Blotter",
                 "Tradervue import", "Tax/Wash-sale Tracker"),
        expertise=("Trade journaling", "Tradervue import",
                   "Reconciliation", "Wash-sale tracking",
                   "Aidan & Mia oversight", "Tooling roadmap"),
        intro=("Olivia, COO. I keep the books straight and the AI "
               "employees aligned. Ask me about the journal, "
               "reconciliations, wash sales, or what Aidan and Mia "
               "are flagging."),
        persona="Operator. Process-minded, talks in workflows, "
                "audit trails, and reconciliation deltas.",
    ),
}


# ----------------------------------------------------------------------------
# Reply engine — mirrors sector_heads.reply()
# ----------------------------------------------------------------------------
def _intent(prompt: str) -> str:
    p = prompt.lower()
    if any(w in p for w in ("hello", "hi ", "hey", "yo ", "good morning")):
        return "greet"
    if any(w in p for w in ("help", "what can you", "what do you")):
        return "help"
    if any(w in p for w in ("who reports", "team", "your people",
                            "who do you manage", "direct reports",
                            "who works for")):
        return "reports"
    if any(w in p for w in ("week", "summary", "synthesis", "weekly")):
        return "weekly"
    if any(w in p for w in ("change", "added", "removed", "new tickers",
                            "what's new")):
        return "changes"
    if any(w in p for w in ("size", "sizing", "stop", "loss limit",
                            "kill switch", "exposure")):
        return "risk"
    if any(w in p for w in ("setup", "tape", "execution", "entry",
                            "vwap", "orb")):
        return "trading"
    if any(w in p for w in ("journal", "trade log", "wash sale",
                            "reconcil", "tradervue", "tax")):
        return "ops"
    if any(w in p for w in ("focus", "priority", "where to look",
                            "allocate", "capital")):
        return "focus"
    return "default"


def reply(md: MD, prompt: str, context: dict) -> str:
    if not prompt or not prompt.strip():
        return "Go ahead."

    intent = _intent(prompt)
    changelog: list[dict] = context.get("changelog") or []
    sectors_covered: int = context.get("sectors_covered", 0)
    total_tickers: int = context.get("total_tickers", 0)

    if intent == "greet":
        return md.intro

    if intent == "help":
        return ("I can talk through: " + ", ".join(md.expertise)
                + ". Ask 'who reports to you' for my team, "
                "'weekly read' for the synthesis, or anything in my lane.")

    if intent == "reports":
        return ("Direct reports / desks I manage:\n\n• "
                + "\n• ".join(md.reports))

    if intent == "weekly":
        if md.name == "Victoria":
            adds = sum(1 for e in changelog if e.get("action") == "added")
            drops = sum(1 for e in changelog if e.get("action") == "removed")
            return (f"Weekly read: {total_tickers} names across "
                    f"{sectors_covered} sectors currently pass the screen. "
                    f"Universe churn this window: {adds} adds, {drops} drops. "
                    f"I'd lean into desks with fresh adds — that's where "
                    f"the fresh setups are. Ask Walter for the cross-sector "
                    f"theme picture.")
        if md.name == "Walter":
            sec_counts: dict[str, int] = {}
            for e in changelog:
                sec_counts[e.get("sector", "?")] = sec_counts.get(e.get("sector", "?"), 0) + 1
            if sec_counts:
                top = sorted(sec_counts.items(), key=lambda x: -x[1])[:3]
                top_str = ", ".join(f"{s} ({n})" for s, n in top)
                return ("Most active desks by changelog volume this window: "
                        f"{top_str}. I'd schedule a sit-down with those "
                        "sector heads first.")
            return ("Light week on the changelog. No desk is screaming "
                    "for attention. Use the quiet window for catalyst "
                    "calendar prep.")
        return "I'd defer the weekly read to Victoria — that's her brief."

    if intent == "changes":
        if not changelog:
            return ("Nothing in the changelog window yet. Load a few "
                    "sector pages to seed the snapshot.")
        recent = changelog[:6]
        bits = []
        for e in recent:
            arrow = "▲" if e.get("action") == "added" else "▼"
            bits.append(f"{arrow} {e.get('sym')} ({e.get('sector')}) — "
                        f"{e.get('reason')}")
        return ("Latest universe activity across the firm:\n\n"
                + "\n\n".join(bits))

    if intent == "risk":
        if md.name == "Riley":
            return ("Risk discipline: fixed-fractional sizing off the "
                    "stop, daily loss limit hard-capped, and no doubling "
                    "into a losing day. Ask me to compute size for a "
                    "specific stop distance and account.")
        return f"Risk questions belong with Riley. I'll loop her in."

    if intent == "trading":
        if md.name == "Trent":
            return ("Setup framework: gap-and-go, VWAP reclaim, ORB, "
                    "parabolic short, halt resumption, news fade. Each "
                    "trade should carry one of these labels at entry — "
                    "no label, no trade.")
        return f"Execution questions go to Trent."

    if intent == "ops":
        if md.name == "Olivia":
            return ("Ops checklist: end-of-day Tradervue import, "
                    "reconcile broker P&L against the journal, flag "
                    "open wash-sale exposure. Aidan and Mia both report "
                    "into me — Aidan QA's the classifier, Mia surfaces "
                    "performance leaks.")
        return f"Ops questions go to Olivia."

    if intent == "focus":
        if md.name == "Victoria":
            return ("Where I'd push the chips this week: the desks "
                    "with the highest changelog turnover (fresh adds = "
                    "fresh setups). Walter can give you the names; "
                    "Riley signs off on size.")
        return "Focus question — Victoria sets the allocation."

    return (f"I'm {md.title}. Try asking about my team, the weekly "
            f"read, or anything in: {', '.join(md.expertise)}.")
