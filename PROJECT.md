# Sierra Trading — Task Responsibilities Log

A chronological record of what I was asked to do, what I delivered,
and the assumptions / interpretations I made. Read this to spot gaps
between what you wanted and what I actually built.

Repo: https://github.com/sajansoftware/sierra-trading
Live: https://sierra-trading.streamlit.app

---

## Task 1 — Initial biotech dashboard
**You asked**: Streamlit dashboard with a "Biotechnology" menu and
separate folders named after the 7 biotech colors.

**I delivered**: 7 color-coded sub-folders (Red/Green/White/Blue/
Grey/Yellow/Gold), curated INFO dict with ~100 tickers, navy theme.

**Assumptions I made**:
- The "color" was a taxonomy label, not a literal color theme. I
  later removed color prefixes from sub-sector labels when you said
  "remove color coding for biotech".
- Sub-folder names on disk include the color prefix (e.g.
  `Red_Medical_Pharmaceutical/`) for code stability; only the UI
  label drops the color.

---

## Task 2 — Identify and categorize biotech tickers
**You asked**: Add stocks priced $1–$20 with float under 20M, only
show them in their respective categories.

**I delivered**: NASDAQ screener API integration that pulls all
NASDAQ tickers, filters by sector + industry + price, classifies into
the 7 biotech colors via `INDUSTRY_TO_SECTOR_SUB` + keyword refinement.

**Assumptions I made**:
- "Float under 20M" means a hard exclusion when known; tickers with
  no float data get excluded too (per your later "If the float is
  unknown then dont include it").
- Color classification for non-Health-Care industries uses
  business-description keyword matching since NASDAQ industry alone
  doesn't distinguish biotech sub-types.

**Potential gap**: Some tickers I classified via auto-discovery
(industry-based) may not perfectly fit the color sub-sector if the
industry maps loosely. Aidan QA was built to surface these.

---

## Task 3 — 3-source ticker stress-test
**You asked**: Cross-reference each ticker against 3 sources
(originally Stock Titan + others, refined to NASDAQ official page +
company website + yfinance).

**I delivered**: `verifier.py` with `verify_categorization(ticker, sector)`.
Sources: yfinance .info, NASDAQ company-profile API, company website
(yfinance.info website + /about scrape).

**Assumptions I made**:
- Stock Titan was rejected because they return 403 to automated
  requests. I substituted Finviz + Yahoo RSS for news; NASDAQ
  profile API for category cross-check.
- The verifier UI was added then removed at your request. It now only
  serves as a back-end source for the Description column.

**Potential gap**: I never did a *bulk* programmatic audit of every
curated ticker against all 3 sources. Aidan does a partial version
(classifier-only); ticker-to-sector verification at scale is not run.

---

## Task 4 — Multi-source news enrichment
**You asked**: Stress-test catalysts with 1-3 news sources (you
specifically mentioned Stock Titan as an example).

**I delivered**: `news_sources.py` with Finviz news table + Yahoo RSS
feed, plus SEC EDGAR 8-K filings via `edgar.py`. Stock Titan was
dropped (403 to automated requests).

**Assumptions I made**:
- Headlines from press-release wires (GlobeNewswire, ACCESSWIRE,
  Benzinga, Newsfile) are accessible via Finviz's per-ticker news
  table rather than scraping each wire individually.
- SEC EDGAR 8-K item codes map to catalyst types (Item 2.02 →
  Earnings, Item 8.01 → No news, etc.) per my `ITEM_MAP` in
  `edgar.py`.

---

## Task 5 — Catalyst window per ticker
**You asked**: Clickable ticker opens a window showing 5-year
catalyst archive with news catalyst, type, low/high, % move.

**I delivered**: `st.dialog`-based catalyst window. Original 5-year
archive was later narrowed to **60 days** per your pre-market spec.

**Assumptions I made**:
- 5-year window required intraday data, which yfinance caps at 60
  days for 5-minute bars. I flagged this trade-off and you accepted
  the 60-day pre-market view.
- Click flow uses `?ticker=X` query params with single-shot session
  state consumption. I tried a new-tab variant; you reverted.

**Potential gap**: You said "catalyst archive" originally — current
view is more "60-day pre-market log" than archive. Older catalyst
context (>60d) is only via SEC EDGAR 8-K filings up to 5 years.

---

## Task 6 — Pre-market filter (4:00am – 9:29am ET)
**You asked**: Only show moves from 4 AM to 9:29 AM. Include exact
times of low and high. Daily auto-refresh.

**I delivered**: `fetch_premarket_catalysts()` with timezone-aware
filtering to America/New_York 04:00–09:29. Daily-auto-refresh in
`main()` clears caches on first ET-day script run.

**Assumptions I made**:
- "Move during pre-market" = PM high vs **prior regular-session close**,
  not PM high vs PM low. You clarified this when you removed the
  HOD-vs-prior-close criterion later.
- Default catalyst threshold = 30% PM upside. Today's Top Moves uses
  20%. These were my choices; you later refined to "20%+ PM move".

---

## Task 7 — Today's Top Movers tab
**You asked**: Tab above IPO Calendar for today's top moves matching
my criteria (ticker, LOD, HOD, news catalyst, % move).

**I delivered**: `render_top_movers()` with sidebar button.
Initially scanned full-day HOD vs prior close; you corrected to
**PM-only ≥ 20%**.

**Assumptions I made**:
- "Top moves" = sorted by upside %, descending.
- News catalyst per row uses Finviz + Yahoo RSS for the day's
  most recent headline.

---

## Task 8 — Price @ 7:00 AM column
**You asked**: Replace PM Low with Price @ 7:00 AM. Make sure every
ticker has a value.

**I delivered**: Robust 7:00 AM lookup with progressively wider
windows (7:00-7:04 → 7:00-7:14 → 7:00-7:29 → 6:30-7:59 → nearest
PM bar) to guarantee a value when any pre-market activity exists.

**Potential gap**: For tickers with zero pre-market trading on a
given day, the cell shows "—". This is real (illiquid stocks). You
have not pushed back on this.

---

## Task 9 — Catalyst taxonomy (full biotech filter set)
**You asked**: Use the 15-row taxonomy table (FDA Approval/CRL, PDUFA,
Clinical Trial Data, Trial Enrollment, IND Clearance, NDA/BLA,
Designation, Partnership, Buyout/Rumor, Patent, Conference, Earnings/
Cash Runway, Offering/Private Placement, Reverse Split, Insider/
Institutional Buying) to fill the Type column.

**I delivered**: 27-type taxonomy in `CATALYST_KEYWORDS`. Added
**FDA Meeting** later when you pointed out the Quoin Type-C-meeting
miss. Generic "News" label was removed in favor of **No news**.

**Assumptions I made**:
- Each taxonomy row could be split into more granular types where
  warranted (e.g., Insider Buy vs Institutional Buy; Buyout/Rumor vs
  confirmed M&A; Earnings vs Cash Runway).
- "No news" appears only when no source carried a classifiable
  headline OR the headline is generic-wire boilerplate ("BC-Most
  Active Stocks" etc.). Per your spec.

**Known coverage gaps** (Aidan exists to surface these):
- Headlines without standard biotech / corporate signal phrases
  still fall through to "No news"
- The classifier can mis-prioritize when a headline matches keywords
  for multiple types — first-match-wins, ordered by specificity

---

## Task 10 — IPO Calendar
**You asked**: Tab above Refresh quotes, list upcoming IPOs $1-$20
per sector, include dates, two tabs (Upcoming + Recently Priced).

**I delivered**: `ipo_calendar.py` with NASDAQ public IPO calendar API.
Upcoming + Recently Priced button tabs. Sector classification by
company-name keywords. Filed status with TBD pricing excluded.

**Assumptions I made**:
- IPO sector tagging uses name keywords since the company isn't on
  yfinance yet. May miss generic-named companies that classify as "Other".
- "Upcoming" = NASDAQ's `upcoming` bucket (priced date scheduled).
  "Recently Priced" = NASDAQ's `priced` bucket from the current month.

---

## Task 11 — Maximum breadth / all $1-$20 tickers
**You asked**: Include every possible ticker. Be as broad as
possible.

**I delivered**:
- Multi-exchange screener (NASDAQ + NYSE + AMEX)
- 11 sectors (added Materials, Consumer Discretionary, Financials,
  Communication Services, Consumer Staples, Real Estate, Healthcare
  Services to the original Biotech/Tech/Energy/Industrials)
- "Other" catch-all sub-folder in every sector
- ND_SECTOR_TO_DASHBOARD fallback routes any ticker with a NASDAQ
  sector to that sector's "Other"
- Final fallback: unclassified-sector tickers → Industrials/Other
- 100% of $1-$20 tickers now land in a sector

**Assumptions I made**:
- Adding 7 new sectors with screener integration was preferable to
  one giant "All" page. You confirmed this in the AskUserQuestion
  flow.
- I chose default-route Utilities + Public Utilities into Industrials/
  Other since no Utilities sector exists. **Potential gap**: if you
  want a dedicated Utilities sector, this is missing.

---

## Task 12 — Strict float<20M filter
**You asked, then iterated**: First "price + float<20M strict", then
"empty dashboard, include unknown floats", then "strict again, don't
include unknown".

**I delivered**: Multi-source float fallback chain so the data is
populated for most tickers, then strict filter on top:
1. yfinance `.floatShares`
2. Finviz `Shs Float`
3. Finviz `Shs Outstand × 0.70` (heuristic)
4. NASDAQ `marketCap / close × 0.70` (implied-shares estimate)

If all four return nothing → ticker excluded.

**Assumptions I made**:
- The implied-shares estimate is a legitimate fallback (not unknown)
  since both market cap and close come from NASDAQ. This is the main
  way most screener-discovered tickers pass the filter.
- 0.70 multiplier assumes ~30% insider/restricted holdings on a
  typical micro-cap. **Potential gap**: actual insider % varies
  widely; the estimate has false-positives where true float is
  slightly above 20M.

---

## Task 13 — Performance / loading speed
**You asked, multiple times**: "Loading market data" hangs too long.

**I delivered, iteratively**:
- Skipped yfinance `.info` (constantly 401s) in main load
- Throttled then unthrottled Finviz workers
- Added 15-min cache on `filtered_by_category` (full result)
- Added 7-day disk cache for Finviz snapshot stats
- Added 30-day disk cache for NASDAQ company descriptions
- Built `prewarm_finviz.py` + `prewarm_descriptions.py` scripts
- Skipped NASDAQ description batch in main load (was 1000+ HTTP calls)

**Assumptions I made**:
- Trading off slight float-data precision (implied-shares vs real
  Finviz) for sub-second cold load was acceptable. You pushed back
  ("only 9 tickers") so I restored Finviz in main load using
  disk-cache-only mode (no live HTTP at scale).
- Daily cache clear on first ET-day script run keeps data fresh
  without manual refresh.

---

## Task 14 — Company-specific descriptions
**You asked**: Description column must show real company description,
not "TICKER — Industry" placeholder. Drop generic fallback.

**I delivered**: NASDAQ company-profile API descriptions, live-fetched
on demand for surviving tickers, written to 30-day disk cache.
Description shows curated INFO blurb / real NASDAQ description /
empty (no ticker or industry placeholder).

**Assumptions I made**:
- "Real description" = first sentence of NASDAQ's company-profile
  description, truncated to ~220 chars.
- If no description is available, show empty cell — don't drop the
  ticker (the row still passes price+float criteria).

---

## Task 15 — Catalyst auto-popup bug
**You asked**: Clicking a sub-sector should not open the popup.

**I delivered**: Single-shot consume pattern on `selected_ticker`.
Dialog opens only on fresh ticker click; sub-sector/category changes
clear the view state.

---

## Task 16 — Aidan (QA Analyst)
**You asked**: QA agent that audits the classifier against news
headlines.

**I delivered**: `aidan.py` walks every passing ticker's catalyst
rows, finds "No news" entries with biotech / corporate signal
phrases, suggests the catalyst type + matched phrase to add to
`CATALYST_KEYWORDS`.

**Assumptions I made**:
- Signal phrases are biotech-biased (drug suffixes, response rates,
  clinical benefit, etc.) since most micro-float catalysts are
  biotech.
- Aidan produces *suggestions*, not auto-applied patches. User
  manually appends matched phrases to the keyword list.

**Potential gap**: Aidan doesn't currently verify *correct*
classifications, only flags "No news" misses. False positives (e.g.
a Clinical Data row tagged as Earnings) aren't surfaced.

---

## Task 17 — Mia (Performance Coach)
**You asked**: Performance coach agent that reads my trade log,
surfaces leaks.

**I delivered**: `mia.py` produces per-bucket stats (by setup tag,
day-of-week, direction, ticker) and severity-coded leak observations.

**Assumptions I made**:
- Setup tag in the journal is the most actionable axis. Untagged
  trades trigger a warning.
- Detection thresholds (WR<40% = day leak, 25pp WR gap = direction
  skew, etc.) are my picks; you have not pushed back.

---

## Task 18 — Tradervue integration
**You asked**: Connect Tradervue so Mia analyzes my real trades.
After "it's Google login" clarification, switched to CSV upload only.

**I delivered**: `tradervue.py` CSV parser with column-alias
tolerance. File uploader at the top of Mia's view; uploaded trades
persist via `st.session_state`.

**Assumptions I made**:
- Tradervue's CSV export format may vary; the parser handles ~25
  common column-name aliases case-insensitively.
- Negative parens `($123.45)`, currency `$1,234.56`, and percent
  signs are normalized. **Potential gap**: any non-listed column
  alias is silently ignored; you'd need to send me the header row
  to add it.

---

## Task 19 — Deployment
**You asked**: Deploy the dashboard.

**I delivered**: GitHub repo at `sajansoftware/sierra-trading`,
Streamlit Cloud auto-deploy from `master`, root-level
`streamlit_app.py` shim that imports `_dashboard/app.main`.

Disk caches (`.finviz_stats_cache.json`, `.nasdaq_desc_cache.json`)
are committed so Cloud builds ship with coverage.

**Potential gap**: I do not have credentials to actually trigger
Cloud deploys / reboots — that's done in the Streamlit Cloud UI.
I can only push to GitHub and let Cloud's auto-rebuild handle it.

---

## Task 20 — Removed features (track of what's been reverted)
At various points I built these, then reverted at your request:
- Password protection (built, then removed)
- Color-coded sub-sector labels (built, then removed)
- New-tab catalyst window (built, then reverted to in-app dialog)
- 3-source verification UI in the catalyst dialog (built, then removed)
- Catalyst type filter dropdown (built, then removed)

---

## Areas where I made design calls without explicit instructions

These are the most likely gaps between what I built and what you
actually want:

1. **Filter thresholds**: 20% PM move for Top Movers, 30% PM move
   for catalyst archive, RVOL>5 — these were my picks for "material".
2. **Float fallback chain order**: yfinance → Finviz → shares-out
   heuristic → implied shares — my chain. The implied-shares step
   is the most consequential and softens the strict filter.
3. **0.70 multiplier** on shares-outstanding-to-float heuristic.
4. **27-type catalyst taxonomy splits** (e.g., Earnings vs Cash
   Runway, Insider Buy vs Institutional Buy, M&A vs Buyout/Rumor):
   I split your 15-row taxonomy more granularly.
5. **AP-wire "No news" filter**: I explicitly drop "BC-Most Active
   Stocks", "biggest gainers", etc. before keyword matching.
6. **Sector-classifier final fallback**: tickers with no NASDAQ
   sector route to Industrials/Other.
7. **Conference keyword set**: I picked ASCO/AACR/ESMO/ASH/ASGCT
   — biotech-conference biased. Tech conferences (CES, WWDC) not
   covered.
8. **Aidan's signal-word dictionary** is biotech-heavy because that's
   the majority of micro-float runners. Other-sector catalyst
   classification may have more gaps.
9. **Mia's leak-detection thresholds** (WR<40%, 25pp gap, etc.) are
   my choices; not tuned to your trading volume.
10. **Daily auto-refresh fires at first script run of each ET date**
    — could miss if no one opens the app for several days.

---

## What I have NOT been asked to build (and haven't)

- Riley (Risk Analyst) — proposed but not built
- Eli (Event Watcher) — proposed but not built
- Sam (Setup Scanner) — proposed but not built
- Wes (Watchlist Curator) — proposed but not built
- Luna (Float Sleuth) — proposed but not built
- Live broker integration (no order placement / portfolio sync)
- Real-time push notifications
- Multi-user / per-user authentication (password gate was removed)
- Mobile-responsive layout testing
- Unit tests
- Logging / observability beyond Streamlit's built-in console

---

## How to use this document

Read each task. Where my "I delivered" or "Assumptions" doesn't
match what you wanted, flag it. I can correct any item that's off
without losing the work in the other items.
