"""
Fetch last 5000 daily candles for a list of Binance USDT symbols from TradingView,
in parallel (each symbol gets its own websocket, run concurrently in threads).

Usage:
    python fetch_5000_daily.py            # smoke test: random 5 symbols
    python fetch_5000_daily.py --all      # fetch the full list (53 symbols)
"""

import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from TradingviewData import TradingViewData, Interval

SYMBOLS = [
    "AAVEUSDT", "ADAUSDT", "APTUSDT", "ARBUSDT", "ASTERUSDT", "AVAXUSDT",
    "BCHUSDT", "BNBUSDT", "BTCUSDT", "CRCLBUSDT", "DASHUSDT", "DOGEUSDT",
    "DOTUSDT", "ENAUSDT", "ETHFIUSDT", "ETHUSDT", "EURUSDT", "FDUSDUSDT",
    "FETUSDT", "HOLOUSDT", "LINKUSDT", "LTCUSDT", "MARSCOINUSDT", "METUSDT",
    "NEARUSDT", "NIULAIUSDT", "ONDOUSDT", "PAXGUSDT", "PEPEUSDT", "POLUSDT",
    "PUMPUSDT", "RAYUSDT", "RLUSDUSDT", "SAHARAUSDT", "SNDKBUSDT", "SOLUSDT",
    "SPCXBUSDT", "SUIUSDT", "TAOUSDT", "THEUSDT", "TRUMPUSDT", "TRXUSDT",
    "UNIUSDT", "USD1USDT", "USDCUSDT", "UUSDT", "VTHOUSDT", "WLDUSDT",
    "WLFIUSDT", "XAUTUSDT", "XLMUSDT", "XRPUSDT", "ZECUSDT",
]

EXCHANGE = "BINANCE"
N_BARS = 5000
MAX_WORKERS = 8  # parallel websocket connections


def fetch_one(symbol: str):
    """Fetch 5000 daily candles for one symbol. Returns (symbol, df or error)."""
    tv = TradingViewData()  # one instance/WS per call
    try:
        df = tv.get_hist(
            symbol=symbol,
            exchange=EXCHANGE,
            interval=Interval.daily,
            n_bars=N_BARS,
        )
        if df is None or df.empty:
            return symbol, None, "no data returned"
        return symbol, df, None
    except Exception as e:
        return symbol, None, f"{type(e).__name__}: {e}"


def run(symbols):
    print(f"Fetching {len(symbols)} symbols x {N_BARS} daily candles "
          f"with {MAX_WORKERS} workers...\n")
    start = time.time()
    ok, failed = [], []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_one, s): s for s in symbols}
        for fut in as_completed(futures):
            symbol, df, err = fut.result()
            if err:
                failed.append((symbol, err))
                print(f"  FAIL  {symbol:<14} {err}")
            else:
                ok.append(symbol)
                print(f"  OK    {symbol:<14} {len(df)} bars  "
                      f"({df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d})")

    print(f"\nDone in {time.time() - start:.1f}s — "
          f"{len(ok)} ok, {len(failed)} failed")
    if failed:
        print("Failed symbols:", ", ".join(s for s, _ in failed))
    return ok, failed


if __name__ == "__main__":
    if "--all" in sys.argv:
        run(SYMBOLS)
    else:
        # Test: pick random 5 and check we get a response
        sample = random.sample(SYMBOLS, 5)
        print("Random 5 for smoke test:", ", ".join(sample), "\n")
        run(sample)
