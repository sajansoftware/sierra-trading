"""Aidan — Sector / Sub-Sector Classifier (powered by Gemini).

Aidan owns the sector / sub-sector categorization workflow in
Operations. His job runs in four steps on every dashboard load:

  1. Scan through each ticker in the $1-$20 NASDAQ universe.
  2. For each one, ask Gemini:
        "Is [company name] stock a [sub-sector] company that falls
         under [sector]? If not, which sector and sub-sector does
         this company fall under?"
     This anchors the LLM to the current keyword-rule pick instead
     of free-form picking from scratch.
  3. Update the ticker's classification on disk (Gemini's pick wins
     over the keyword rules from this point forward).
  4. If Gemini overturned the pick, the change is recorded in the
     Categorization log under Aidan (Operations) with timestamp,
     ticker, previous sector / sub-sector, new sector / sub-sector,
     and a one-clause rationale.

Results are persisted to disk so the API call only fires once per
ticker — every subsequent dashboard load reads from cache.

Environment:
  GEMINI_API_KEY — your Google AI Studio key. If unset, Aidan
  stays idle and the dashboard uses the keyword rule fallback.

Cache file: .gemini_classify_cache.json next to this module. Schema:
  {
    "tickers": {
      "ABC": {
        "sector":          "Health Care",
        "sub_sector":      "Red_Medical_Pharmaceutical",
        "prev_sector":     "Communication Services",
        "prev_sub_sector": "Publishing_News",
        "is_correct":      false,
        "rationale":       "alcohol-detection wearable medical device",
        "ts":              "2026-05-22T10:32:00Z"
      },
      ...
    },
    "taxonomy_hash": "...",
    "prompt_version": "..."
  }
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


CACHE_PATH = Path(__file__).resolve().parent / ".gemini_classify_cache.json"
MODEL_NAME = "gemini-2.5-flash"
BATCH_SIZE = 25
# Bump when the prompt format changes — any cache built under a
# different version is wiped on load so every ticker re-runs through
# the current prompt.
PROMPT_VERSION = "v4-aidan-template"


# ----------------------------------------------------------------------------
# Cache I/O
# ----------------------------------------------------------------------------
def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {"tickers": {}, "taxonomy_hash": "", "prompt_version": PROMPT_VERSION}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tickers": {}, "taxonomy_hash": "", "prompt_version": PROMPT_VERSION}
    # Invalidate stale-prompt-version caches so every ticker re-runs
    # through the current prompt format.
    if data.get("prompt_version") != PROMPT_VERSION:
        return {"tickers": {}, "taxonomy_hash": data.get("taxonomy_hash", ""),
                "prompt_version": PROMPT_VERSION}
    return data


def _save_cache(data: dict) -> None:
    try:
        CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _taxonomy_hash(taxonomy: dict[str, list[str]]) -> str:
    """Stable hash of the sector → sub-sectors mapping. Cache invalidated
    when this changes."""
    blob = json.dumps(
        {k: sorted(v) for k, v in taxonomy.items()},
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:12]


# ----------------------------------------------------------------------------
# Public lookup helpers (no API call)
# ----------------------------------------------------------------------------
def cached_classification(ticker: str) -> tuple[str, str] | None:
    """Return (sector, sub_sector) for a ticker if present in cache.

    No API call. Safe to invoke per-render."""
    data = _load_cache()
    rec = (data.get("tickers") or {}).get(ticker.upper())
    if not rec:
        return None
    sec = rec.get("sector")
    sub = rec.get("sub_sector")
    if not sec or not sub:
        return None
    return sec, sub


def is_configured() -> bool:
    return bool(_api_key())


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return (
            st.secrets.get("GEMINI_API_KEY")
            or st.secrets.get("GOOGLE_API_KEY")
            or ""
        )
    except Exception:
        return ""


# ----------------------------------------------------------------------------
# Gemini call
# ----------------------------------------------------------------------------
def _build_prompt(
    companies: list[dict],
    taxonomy: dict[str, list[str]],
    taxonomy_labels: dict[str, dict[str, str]] | None = None,
) -> str:
    """Validation-style prompt: for each company, ask whether the
    current sub-sector assignment is correct and, if not, what the
    correct (sector, sub_sector) should be from the taxonomy.

    `taxonomy_labels[sector][sub_key]` → human-readable label like
    "Publishing & News". Defaults to underscore-stripped key when
    labels are missing.
    """
    def label_of(sec: str, sub_key: str) -> str:
        if taxonomy_labels and sec in taxonomy_labels:
            lbl = taxonomy_labels[sec].get(sub_key)
            if lbl:
                return lbl
        return sub_key.replace("_", " ")

    tax_lines = []
    for sec, subs in taxonomy.items():
        bits = []
        for sub in subs:
            bits.append(f"{sub} ({label_of(sec, sub)})")
        tax_lines.append(f"- {sec}: " + ", ".join(bits))
    tax_block = "\n".join(tax_lines)

    co_lines = []
    for i, c in enumerate(companies, 1):
        cur_sec = c.get("current_sector") or "—"
        cur_sub_key = c.get("current_sub_sector") or "—"
        cur_label = (label_of(cur_sec, cur_sub_key)
                     if cur_sec != "—" else "—")
        name = c.get("name", "this company")
        co_lines.append(
            f"{i}. TICKER {c.get('ticker','?')}"
            f" | NAME: {name[:80]}"
            f" | NASDAQ_INDUSTRY: {c.get('industry','')[:80]}\n"
            f"   CURRENT_ASSIGNMENT: {cur_sec} / {cur_label}"
            f"  [sub_sector key: {cur_sub_key}]\n"
            f"   QUESTION: Is {name} stock a {cur_label} company that"
            f" falls under {cur_sec}? If not, which sector and"
            f" sub-sector does this company fall under?"
        )
    co_block = "\n".join(co_lines)

    return f"""You are Aidan, the Operations classification analyst
for a small-cap intraday trading dashboard. Your job is to scan each
ticker, ask the validation question, and either confirm the current
sector / sub-sector or pick the correct one from the firm's taxonomy.
Rely on what the company actually does (public filings + website),
not the coarse NASDAQ industry label. Output ONLY valid JSON — no
commentary, no markdown fences.

TAXONOMY (sector_key (human label), …):
{tax_block}

RULES:
- "sector" MUST be a sector key from the taxonomy, character-for-character.
- "sub_sector" MUST be a sub-sector KEY (underscored form) listed
  under that sector — never the human label.
- "is_correct" is true when the current assignment is right;
  false when you are overriding it.
- When is_correct is true, sector / sub_sector MUST equal the
  CURRENT_ASSIGNMENT.
- If genuinely uncertain, route to the sector's "Other" sub-sector.
- "rationale" is one short clause (≤ 14 words) — what the company
  actually does and why this sub-sector fits.

COMPANIES:
{co_block}

OUTPUT FORMAT (JSON array, one object per company, same order):
[
  {{
    "ticker": "...",
    "is_correct": true,
    "sector": "...",
    "sub_sector": "...",
    "rationale": "..."
  }},
  ...
]
""".strip()


def _call_gemini(prompt: str) -> str:
    """Single API call. Raises on failure."""
    import google.generativeai as genai
    genai.configure(api_key=_api_key())
    model = genai.GenerativeModel(MODEL_NAME)
    resp = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    )
    return resp.text or "[]"


def _parse_response(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        out = json.loads(raw)
        if isinstance(out, dict) and "results" in out:
            return out["results"]
        if isinstance(out, list):
            return out
    except Exception:
        pass
    return []


def _validate_pick(
    rec: dict,
    taxonomy: dict[str, list[str]],
) -> dict | None:
    sec = (rec.get("sector") or "").strip()
    sub = (rec.get("sub_sector") or "").strip()
    if sec not in taxonomy:
        return None
    if sub not in taxonomy[sec]:
        sub = "Other" if "Other" in taxonomy[sec] else taxonomy[sec][0]
    return {
        "ticker": (rec.get("ticker") or "").upper().strip(),
        "sector": sec,
        "sub_sector": sub,
        "rationale": (rec.get("rationale") or "")[:160],
    }


# ----------------------------------------------------------------------------
# Public batch API
# ----------------------------------------------------------------------------
def classify_batch(
    companies: list[dict],
    taxonomy: dict[str, list[str]],
    taxonomy_labels: dict[str, dict[str, str]] | None = None,
    progress_cb=None,
) -> dict[str, dict]:
    """Classify a batch of companies via Gemini.

    `companies` items: {ticker, name, sector, industry,
                        current_sector?, current_sub_sector?}
    Returns {ticker: {sector, sub_sector, rationale, is_correct}}
    for picks Gemini produced. Skips tickers already cached under the
    current taxonomy. Persists to cache as it goes.
    """
    if not is_configured():
        return {}

    data = _load_cache()
    tax_h = _taxonomy_hash(taxonomy)
    if data.get("taxonomy_hash") != tax_h:
        data = {"tickers": {}, "taxonomy_hash": tax_h,
                "prompt_version": PROMPT_VERSION}

    cache = data.setdefault("tickers", {})
    to_run = [c for c in companies if c.get("ticker", "").upper() not in cache]
    out: dict[str, dict] = {}
    total = len(to_run)
    done = 0

    for i in range(0, total, BATCH_SIZE):
        chunk = to_run[i:i + BATCH_SIZE]
        # Index by ticker so we can carry the prior rule-based pick
        # onto the cache record as prev_sector / prev_sub_sector.
        by_tkr = {c.get("ticker", "").upper(): c for c in chunk}
        try:
            prompt = _build_prompt(chunk, taxonomy, taxonomy_labels)
            raw = _call_gemini(prompt)
            picks = _parse_response(raw)
        except Exception as e:
            if progress_cb:
                progress_cb(done, total, f"error: {e}")
            time.sleep(2)
            continue

        for rec in picks:
            valid = _validate_pick(rec, taxonomy)
            if not valid:
                continue
            tkr = valid["ticker"]
            cur = by_tkr.get(tkr) or {}
            is_correct = bool(rec.get("is_correct"))
            cache[tkr] = {
                **{k: v for k, v in valid.items() if k != "ticker"},
                "is_correct":      is_correct,
                "prev_sector":     cur.get("current_sector"),
                "prev_sub_sector": cur.get("current_sub_sector"),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            out[tkr] = cache[tkr]

        done += len(chunk)
        data["taxonomy_hash"] = tax_h
        data["prompt_version"] = PROMPT_VERSION
        _save_cache(data)
        if progress_cb:
            progress_cb(done, total, "ok")
        time.sleep(0.4)

    return out


def list_overturns(limit: int | None = None) -> list[dict]:
    """Return cache entries where Gemini overturned the rule-based pick.

    Each item: {ticker, prev_sector, prev_sub_sector, sector,
    sub_sector, rationale, ts}. Sorted newest first.
    """
    data = _load_cache()
    tickers = data.get("tickers") or {}
    out: list[dict] = []
    for sym, rec in tickers.items():
        if rec.get("is_correct"):
            continue
        prev_sec = rec.get("prev_sector")
        prev_sub = rec.get("prev_sub_sector")
        if not prev_sec or not prev_sub:
            continue
        new_sec = rec.get("sector")
        new_sub = rec.get("sub_sector")
        # Don't show identity flips (defensive — shouldn't happen)
        if prev_sec == new_sec and prev_sub == new_sub:
            continue
        out.append({
            "ticker":          sym,
            "prev_sector":     prev_sec,
            "prev_sub_sector": prev_sub,
            "sector":          new_sec,
            "sub_sector":      new_sub,
            "rationale":       rec.get("rationale", ""),
            "ts":              rec.get("ts", ""),
        })
    out.sort(key=lambda r: r["ts"], reverse=True)
    if limit is not None:
        out = out[:limit]
    return out


def stats() -> dict:
    """Cache stats for the settings panel."""
    data = _load_cache()
    tickers = data.get("tickers") or {}
    by_sector: dict[str, int] = {}
    for rec in tickers.values():
        sec = rec.get("sector", "?")
        by_sector[sec] = by_sector.get(sec, 0) + 1
    return {
        "total_classified": len(tickers),
        "by_sector": by_sector,
        "configured": is_configured(),
        "taxonomy_hash": data.get("taxonomy_hash", ""),
    }
