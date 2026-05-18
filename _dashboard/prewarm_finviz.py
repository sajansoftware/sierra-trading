"""One-shot prewarm of the Finviz disk cache.

Run this once (and any time you want to refresh):
    python _dashboard/prewarm_finviz.py

It walks every screener-discovered ticker in the $1-$20 band and
caches Finviz stats to disk so the dashboard's first daily load is
instant.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import warnings; warnings.filterwarnings("ignore")
from screener import fetch_nasdaq_universe, _parse_price
from news_sources import fetch_finviz_stats

raw = fetch_nasdaq_universe()
in_range = []
for r in raw:
    sym = (r.get("symbol") or "").strip().upper()
    if not sym or any(c in sym for c in ".^$/"):
        continue
    p = _parse_price(r.get("lastsale"))
    if p is not None and 1.0 <= p <= 20.0:
        in_range.append(sym)

print(f"Pre-warming Finviz cache for {len(in_range)} tickers in $1-$20 range...")
start = time.time()
got = 0
for i, t in enumerate(in_range, 1):
    s = fetch_finviz_stats(t)
    if s and any(v is not None for v in s.values()):
        got += 1
    if i % 50 == 0:
        elapsed = time.time() - start
        rate = i / elapsed
        eta = (len(in_range) - i) / rate
        print(f"  {i}/{len(in_range)} done | {got} cached | {elapsed:.0f}s elapsed | ~{eta:.0f}s remaining")
    time.sleep(0.15)   # gentle on Finviz

print(f"\nDone: {got}/{len(in_range)} tickers cached in {time.time()-start:.0f}s")
