"""Mia — Performance Coach for the Trading Journal.

Reads the user's logged trades and produces:
- per-bucket performance stats (by setup tag, day of week, direction,
  ticker)
- human-readable 'leak' observations (where the user is losing money
  consistently and what to do about it)

Pure-function module: takes a list of trade dicts, returns analysis
dicts. UI lives in app.render_mia_coach().
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from statistics import mean


@dataclass(frozen=True)
class BucketStats:
    label: str
    trades: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    expectancy: float       # avg_pnl per trade, signed (same as avg_pnl)
    best_pnl: float
    worst_pnl: float


@dataclass(frozen=True)
class Leak:
    severity: str           # 'high' | 'medium' | 'low'
    title: str
    detail: str
    recommendation: str


def _safe_pnl(t: dict) -> float:
    try:
        return float(t.get("pnl") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _bucket_stats(label: str, trades: list[dict]) -> BucketStats:
    pnls = [_safe_pnl(t) for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    n = len(trades)
    return BucketStats(
        label=label,
        trades=n,
        win_rate=(wins / n * 100) if n else 0.0,
        total_pnl=sum(pnls),
        avg_pnl=(mean(pnls) if pnls else 0.0),
        expectancy=(mean(pnls) if pnls else 0.0),
        best_pnl=max(pnls) if pnls else 0.0,
        worst_pnl=min(pnls) if pnls else 0.0,
    )


def _split_tags(t: dict) -> list[str]:
    raw = t.get("tags") or ""
    parts = [s.strip() for s in raw.split(",")]
    return [p for p in parts if p]


def analyze(trades: list[dict]) -> dict:
    """Comprehensive performance breakdown of the trade log."""
    if not trades:
        return {"empty": True}

    # ---- By setup tag ----
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        tags = _split_tags(t)
        if not tags:
            by_tag["(untagged)"].append(t)
        for tag in tags:
            by_tag[tag].append(t)

    # ---- By day-of-week ----
    by_dow: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        try:
            d = date.fromisoformat(t.get("date", ""))
            by_dow[d.strftime("%A")].append(t)
        except (TypeError, ValueError):
            continue

    # ---- By direction (Long / Short) ----
    by_dir: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_dir[t.get("direction") or "Unknown"].append(t)

    # ---- By ticker ----
    by_tk: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        sym = (t.get("ticker") or "").upper()
        if sym:
            by_tk[sym].append(t)

    return {
        "empty": False,
        "n_trades": len(trades),
        "by_tag":       sorted(
            (_bucket_stats(k, v) for k, v in by_tag.items()),
            key=lambda s: -s.total_pnl),
        "by_dow":       [
            _bucket_stats(k, by_dow[k])
            for k in ["Monday", "Tuesday", "Wednesday", "Thursday",
                      "Friday", "Saturday", "Sunday"]
            if by_dow.get(k)
        ],
        "by_direction": sorted(
            (_bucket_stats(k, v) for k, v in by_dir.items()),
            key=lambda s: -s.total_pnl),
        "by_ticker":    sorted(
            (_bucket_stats(k, v) for k, v in by_tk.items()),
            key=lambda s: -s.total_pnl),
        "best_trade":   max(trades, key=_safe_pnl) if trades else None,
        "worst_trade":  min(trades, key=_safe_pnl) if trades else None,
        "avg_win":      mean([_safe_pnl(t) for t in trades if _safe_pnl(t) > 0])
                        if any(_safe_pnl(t) > 0 for t in trades) else 0.0,
        "avg_loss":     mean([_safe_pnl(t) for t in trades if _safe_pnl(t) < 0])
                        if any(_safe_pnl(t) < 0 for t in trades) else 0.0,
    }


def find_leaks(analysis: dict) -> list[Leak]:
    """Surface concrete patterns Mia thinks the trader should address."""
    if analysis.get("empty"):
        return []
    leaks: list[Leak] = []

    # ---- Day-of-week leaks ----
    dow_significant = [s for s in analysis["by_dow"] if s.trades >= 5]
    if dow_significant:
        worst = min(dow_significant, key=lambda s: s.win_rate)
        if worst.win_rate < 40:
            leaks.append(Leak(
                severity="high",
                title=f"{worst.label}s are a leak",
                detail=(f"{worst.trades} trades, {worst.win_rate:.0f}% win rate, "
                        f"net ${worst.total_pnl:,.0f} on the day."),
                recommendation=(f"Consider sitting out {worst.label}s, or "
                                "review what's structurally different about "
                                "your tape-read on that day."),
            ))

    # ---- Setup-tag leaks ----
    tag_significant = [s for s in analysis["by_tag"]
                       if s.trades >= 4 and s.label != "(untagged)"]
    if tag_significant:
        # Worst expectancy setup (negative AND with enough trades)
        bad = [s for s in tag_significant if s.expectancy < 0]
        for s in bad:
            leaks.append(Leak(
                severity="high" if s.total_pnl < -200 else "medium",
                title=f"Setup '{s.label}' is bleeding",
                detail=(f"{s.trades} trades, {s.win_rate:.0f}% win rate, "
                        f"avg ${s.avg_pnl:+.0f}/trade, net ${s.total_pnl:,.0f}."),
                recommendation=(f"Cut this setup until you understand why it "
                                f"isn't working. Was it the entry, the stop, "
                                f"or the universe of tickers?"),
            ))
        # Best setup highlight (not really a leak, but useful coaching)
        best_tag = max(tag_significant, key=lambda s: s.total_pnl)
        if best_tag.total_pnl > 0 and best_tag.win_rate >= 55:
            leaks.append(Leak(
                severity="low",
                title=f"Setup '{best_tag.label}' is your edge",
                detail=(f"{best_tag.trades} trades, {best_tag.win_rate:.0f}% "
                        f"win rate, net +${best_tag.total_pnl:,.0f}."),
                recommendation=(f"This is where your alpha is. Look for more "
                                f"of these setups; consider sizing up when "
                                f"the pattern is clean."),
            ))

    # ---- Untagged trades ----
    untagged = next((s for s in analysis["by_tag"] if s.label == "(untagged)"), None)
    if untagged and untagged.trades >= 5:
        leaks.append(Leak(
            severity="medium",
            title=f"{untagged.trades} trades have no setup tag",
            detail="You can't analyse what you don't label.",
            recommendation=("Tag every trade with a setup name (gap-and-go, "
                            "VWAP reclaim, fade, parabolic-short, etc.) so "
                            "Mia can spot patterns."),
        ))

    # ---- Direction skew ----
    longs = next((s for s in analysis["by_direction"] if s.label == "Long"), None)
    shorts = next((s for s in analysis["by_direction"] if s.label == "Short"), None)
    if longs and shorts:
        if longs.win_rate - shorts.win_rate > 25 and shorts.trades >= 5:
            leaks.append(Leak(
                severity="medium",
                title="You're worse at shorts than longs",
                detail=(f"Longs {longs.win_rate:.0f}% WR vs Shorts "
                        f"{shorts.win_rate:.0f}% WR. Shorts net "
                        f"${shorts.total_pnl:,.0f}."),
                recommendation=("Either drop shorting until you find a "
                                "repeatable pattern, or shrink size on shorts "
                                "while you experiment."),
            ))
        elif shorts.win_rate - longs.win_rate > 25 and longs.trades >= 5:
            leaks.append(Leak(
                severity="medium",
                title="You're worse at longs than shorts",
                detail=(f"Shorts {shorts.win_rate:.0f}% WR vs Longs "
                        f"{longs.win_rate:.0f}% WR. Longs net "
                        f"${longs.total_pnl:,.0f}."),
                recommendation=("Bias your trading toward the short side, or "
                                "review your long-entry checklist for a "
                                "missing filter."),
            ))

    # ---- Repeat-loser tickers ----
    ticker_losers = [s for s in analysis["by_ticker"]
                     if s.trades >= 3 and s.total_pnl < -100]
    for s in ticker_losers:
        leaks.append(Leak(
            severity="medium",
            title=f"{s.label} keeps losing you money",
            detail=(f"{s.trades} trades, net ${s.total_pnl:,.0f}, "
                    f"{s.win_rate:.0f}% win rate."),
            recommendation=(f"You may have a mental short / long bias on "
                            f"{s.label} that's overriding tape signals. "
                            "Consider adding it to a personal 'do not trade' "
                            "list for 30 days."),
        ))

    # ---- Avg win vs avg loss ratio ----
    if analysis["avg_win"] and analysis["avg_loss"]:
        ratio = analysis["avg_win"] / abs(analysis["avg_loss"])
        if ratio < 1.0:
            leaks.append(Leak(
                severity="high",
                title=f"You take small wins and big losses ({ratio:.2f}:1)",
                detail=(f"Avg win ${analysis['avg_win']:,.0f}, "
                        f"avg loss ${abs(analysis['avg_loss']):,.0f}."),
                recommendation=("Tighten stops or let winners run further. "
                                "A R:R below 1.0 means you need >50% WR just "
                                "to break even."),
            ))

    # Sort by severity for display
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    leaks.sort(key=lambda l: sev_rank.get(l.severity, 9))
    return leaks
