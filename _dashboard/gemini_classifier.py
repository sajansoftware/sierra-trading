"""Google Gemini classifier for sector / sub-sector assignment.

Replaces the keyword-rule classifier with an LLM call that understands
company business descriptions. Results are persisted to disk so the
expensive API call only fires once per ticker — every subsequent
dashboard load reads from cache.

Environment:
  GEMINI_API_KEY — your Google AI Studio key. If unset, classify_*
  functions return None and callers fall back to the keyword rules.

Cache file: .gemini_classify_cache.json next to this module. Schema:
  {
    "tickers": {
      "ABC": {
        "sector": "Health Care",
        "sub_sector": "Red_Medical_Pharmaceutical",
        "rationale": "biotech pharma focused on oncology",
        "ts": "2026-05-22T10:32:00Z"
      },
      ...
    },
    "taxonomy_hash": "..."   # invalidates cache when SECTORS dict changes
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


# ----------------------------------------------------------------------------
# Cache I/O
# ----------------------------------------------------------------------------
def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {"tickers": {}, "taxonomy_hash": ""}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tickers": {}, "taxonomy_hash": ""}


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
) -> str:
    tax_lines = []
    for sec, subs in taxonomy.items():
        tax_lines.append(f"- {sec}: {', '.join(subs)}")
    tax_block = "\n".join(tax_lines)

    co_lines = []
    for i, c in enumerate(companies, 1):
        co_lines.append(
            f"{i}. TICKER {c.get('ticker','?')}"
            f" | NAME: {c.get('name','')[:80]}"
            f" | NASDAQ_SECTOR: {c.get('sector','')[:40]}"
            f" | NASDAQ_INDUSTRY: {c.get('industry','')[:80]}"
        )
    co_block = "\n".join(co_lines)

    return f"""You are a securities classification analyst. Classify each
company into exactly one of these GICS top-level sectors AND exactly
one of that sector's sub-sectors. Use your knowledge of each company's
actual business from their public filings and website. Output ONLY
valid JSON — no commentary, no markdown fences.

TAXONOMY (sector → sub-sectors):
{tax_block}

RULES:
- sector MUST be one of the sector names above, character-for-character.
- sub_sector MUST be one of that sector's listed sub-sectors,
  character-for-character (including underscores).
- Rely on what the company actually does, not just the NASDAQ industry
  label which is often coarse or wrong.
- If you are uncertain, choose the sector's "Other" sub-sector.
- "rationale" is one short clause (≤ 12 words) explaining the pick.

COMPANIES:
{co_block}

OUTPUT FORMAT (JSON array, one object per company, same order):
[
  {{"ticker": "...", "sector": "...", "sub_sector": "...", "rationale": "..."}},
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
    progress_cb=None,
) -> dict[str, dict]:
    """Classify a batch of companies via Gemini.

    `companies` items: {ticker, name, sector, industry}
    Returns {ticker: {sector, sub_sector, rationale}} for picks Gemini
    produced. Skips tickers that already have a cached entry for the
    current taxonomy. Persists to cache as it goes.
    """
    if not is_configured():
        return {}

    data = _load_cache()
    tax_h = _taxonomy_hash(taxonomy)
    if data.get("taxonomy_hash") != tax_h:
        data = {"tickers": {}, "taxonomy_hash": tax_h}

    cache = data.setdefault("tickers", {})
    to_run = [c for c in companies if c.get("ticker", "").upper() not in cache]
    out: dict[str, dict] = {}
    total = len(to_run)
    done = 0

    for i in range(0, total, BATCH_SIZE):
        chunk = to_run[i:i + BATCH_SIZE]
        try:
            prompt = _build_prompt(chunk, taxonomy)
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
            cache[tkr] = {
                **{k: v for k, v in valid.items() if k != "ticker"},
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            out[tkr] = cache[tkr]

        done += len(chunk)
        data["taxonomy_hash"] = tax_h
        _save_cache(data)
        if progress_cb:
            progress_cb(done, total, "ok")
        time.sleep(0.4)

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
