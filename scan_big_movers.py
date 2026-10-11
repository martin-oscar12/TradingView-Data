"""
Big movers scanner — flags symbols whose LATEST daily candle moved
more than +/- 10% vs the previous daily close.

Run:  python scan_big_movers.py           (default threshold 10%)
      python scan_big_movers.py 5         (custom threshold, e.g. 5%)
      python scan_big_movers.py --save    (also write result to big_movers.csv)
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from fetch_5000_daily import SYMBOLS, fetch_one

DEFAULT_THRESHOLD = 10.0  # percent
MAX_WORKERS = 3        # lower concurrency: TradingView throttles at 429
RETRY_DELAYS = (5, 15)  # seconds to wait on a 429 before retrying


def fetch_with_retries(symbol: str):
    """fetch_one with backoff retries for TradingView 429 rate limiting."""
    for attempt, delay in enumerate((0,) + RETRY_DELAYS, 1):
        if delay:
            time.sleep(delay)
        _, df, err = fetch_one(symbol)
        if df is not None:
            return df, None
        if "429" not in str(err):
            return None, err
        print(f"    retry {attempt}/{len(RETRY_DELAYS)} {symbol} (rate limited)")
    return None, err


def scan_symbol(symbol: str, threshold: float):
    """Return (symbol, row dict or None, error)."""
    df, err = fetch_with_retries(symbol)
    if df is None:
        return symbol, None, err
    if len(df) < 2:
        return symbol, None, "not enough bars"

    today, prev = df.iloc[-1], df.iloc[-2]
    pct = (today["close"] - prev["close"]) / prev["close"] * 100.0
    if abs(pct) <= threshold:
        return symbol, None, None

    return symbol, {
        "symbol": symbol,
        "date": f"{df.index[-1]:%Y-%m-%d}",
        "prev_close": round(float(prev["close"]), 8),
        "close": round(float(today["close"]), 8),
        "change_pct": round(pct, 2),
    }, None


def run(threshold: float, save: bool):
    print(f"Scanning {len(SYMBOLS)} symbols: |daily change| > {threshold}%\n")
    rows, failed = [], []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scan_symbol, s, threshold): s for s in SYMBOLS}
        for fut in as_completed(futures):
            symbol, row, err = fut.result()
            if err:
                failed.append((symbol, err))
                print(f"  FAIL {symbol}: {err}")
            elif row:
                rows.append(row)
                direction = "UP  " if row["change_pct"] > 0 else "DOWN"
                print(f"  {direction} {symbol:<14} {row['change_pct']:+.2f}%  "
                      f"({row['prev_close']} -> {row['close']})  {row['date']}")

    rows.sort(key=lambda r: r["change_pct"])
    print(f"\n=== {len(rows)} movers beyond +-{threshold}% "
          f"({len(failed)} fetch failures) ===")
    for r in rows:
        print(f"  {r['symbol']:<14} {r['change_pct']:+8.2f}%  "
              f"close={r['close']}  ({r['date']})")

    if not rows:
        print("  (none today)")
    elif save:
        out = pd.DataFrame(rows)
        out.to_csv("big_movers.csv", index=False)
        print(f"\nSaved to big_movers.csv")

    if failed:
        print("Failed symbols:", ", ".join(s for s, _ in failed))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    threshold = float(args[0]) if args else DEFAULT_THRESHOLD
    run(threshold, save="--save" in sys.argv)
