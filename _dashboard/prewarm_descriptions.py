"""Pre-populate the NASDAQ description disk cache.

Run once (or periodically):
    python _dashboard/prewarm_descriptions.py

Walks every $1-$20 ticker, fetches NASDAQ company-profile description,
writes to .nasdaq_desc_cache.json. Subsequent dashboard loads serve
descriptions instantly from disk.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import warnings; warnings.filterwarnings("ignore")
from screener import fetch_nasdaq_universe, _parse_price
from verifier import fetch_nasdaq_desc

raw = fetch_nasdaq_universe()
in_range = []
for r in raw:
    sym = (r.get("symbol") or "").strip().upper()
    if not sym or any(c in sym for c in ".^$/"):
        continue
    p = _parse_price(r.get("lastsale"))
    if p is not None and 1.0 <= p <= 20.0:
        in_range.append(sym)

print(f"Pre-warming NASDAQ descriptions for {len(in_range)} tickers...")
start = time.time()
got = 0
for i, t in enumerate(in_range, 1):
    d = fetch_nasdaq_desc(t)
    if d:
        got += 1
    if i % 100 == 0:
        elapsed = time.time() - start
        rate = i / elapsed
        eta = (len(in_range) - i) / rate
        print(f"  {i}/{len(in_range)} processed | {got} cached | {elapsed:.0f}s elapsed | ~{eta:.0f}s remaining")
    time.sleep(0.10)

print(f"\nDone: {got}/{len(in_range)} descriptions cached in {time.time()-start:.0f}s")
