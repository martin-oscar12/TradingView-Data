"""
Volume Candle scanner — HEAVY VOLUME at 200% of average (fator=2.0).

For every Binance USDT symbol, fetch daily candles, compute Pine-style
EMA(volume, 20), and flag "heavy" bars: volume > ema * 2.0.
Saves the most recent heavy candle per symbol to result.csv with:
    currency_name, date, open, high, low, close, volume, volume_pct
(volume_pct = volume / ema20 * 100, i.e. % of average volume)

Run:  python scan_heavy_volume.py            (scanner, default mode)
      python scan_heavy_volume.py --all-events   (log EVERY heavy bar, big file)
"""

import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from fetch_5000_daily import SYMBOLS, EXCHANGE, N_BARS, MAX_WORKERS, fetch_one

PERIODO = 20
FATOR = 2.0  # 200% of average volume


def pine_ema(series: pd.Series, length: int) -> pd.Series:
    """Pine-script style EMA: SMA seed, then recursive update."""
    alpha = 2.0 / (length + 1)
    values = series.astype(float).values
    ema = [math.nan] * len(values)
    for i in range(len(values)):
        if i == length - 1:
            ema[i] = sum(values[:length]) / length
        elif i >= length:
            ema[i] = alpha * values[i] + (1 - alpha) * ema[i - 1]
    return pd.Series(ema, index=series.index)


def scan_symbol(symbol: str, all_events: bool = False):
    """Return (symbol, DataFrame of heavy bars, error)."""
    for attempt in (1, 2):  # one retry for flaky 5s websocket timeout
        _, df, err = fetch_one(symbol)
        if df is not None:
            break
    if df is None:
        return symbol, None, err

    ema = pine_ema(df["volume"], PERIODO)
    threshold = ema * FATOR
    heavy = df[df["volume"] > threshold].copy()
    heavy["volume_pct"] = (df["volume"] / ema * 100).reindex(heavy.index)

    if not all_events and not heavy.empty:
        heavy = heavy.iloc[[-1]]  # most recent heavy candle only

    return symbol, heavy, None


def run(all_events: bool):
    rows = []
    failed = []
    start = time.time()
    print(f"Scanning {len(SYMBOLS)} symbols: volume > EMA20(volume) x {FATOR} (200%)")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scan_symbol, s, all_events): s for s in SYMBOLS}
        done = 0
        for fut in as_completed(futures):
            symbol, heavy, err = fut.result()
            done += 1
            if err:
                failed.append(symbol)
                print(f"  [{done}/{len(SYMBOLS)}] FAIL {symbol}: {err}")
            else:
                count = 0 if heavy is None else len(heavy)
                if heavy is not None and not heavy.empty:
                    rows.append(heavy.assign(currency_name=symbol))
                    last = heavy.iloc[-1]
                    print(f"  [{done}/{len(SYMBOLS)}] {symbol:<14} "
                          f"{count:>4} heavy bars | last: {last.name:%Y-%m-%d} "
                          f"vol={last['volume_pct']:.0f}% of avg")
                else:
                    print(f"  [{done}/{len(SYMBOLS)}] {symbol:<14} no heavy bars")

    if rows:
        result = pd.concat(rows)[["currency_name", "open", "high", "low", "close",
                                  "volume", "volume_pct"]]
        result = result.rename(columns={"open": "open", "high": "high",
                                        "low": "low", "close": "close"})
        result.insert(1, "date", result.index.strftime("%Y-%m-%d"))
        result = result.reset_index(drop=True)
        result.to_csv("result.csv", index=False)
        print(f"\nSaved {len(result)} rows to result.csv "
              f"({result['currency_name'].nunique()} symbols, "
              f"{time.time()-start:.1f}s total)")
        print("\nMost extreme recent events (top 10 by volume %):")
        top = result.sort_values("volume_pct", ascending=False).head(10)
        for _, r in top.iterrows():
            print(f"  {r['currency_name']:<14} {r['date']}  "
                  f"O={r['open']:<10} H={r['high']:<10} L={r['low']:<10} "
                  f"C={r['close']:<10} vol={r['volume_pct']:.0f}% of avg")
    else:
        print("\nNo heavy bars found — result.csv not written")

    if failed:
        print("Failed symbols:", ", ".join(failed))


if __name__ == "__main__":
    run(all_events="--all-events" in sys.argv)
