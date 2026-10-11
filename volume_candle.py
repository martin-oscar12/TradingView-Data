"""
Volume Candle indicator (Pine v3 study) ported to Python.

Original logic:
    up = close > open
    down = open > close
    pesado = volume > (ema(volume, 20) * 1.25)
    barcolor: heavy+up -> lime, heavy+down -> red, up -> silver, else gray

Pine's ema() is recursive: ema_t = alpha*vol_t + (1-alpha)*ema_{t-1},
alpha = 2/(period+1), seeded with an SMA of the first `periodo` values.

Runs on 5 symbols and verifies manually:
  1. Compares our recursive EMA against pandas' ewm(span=20, adjust=False).
  2. Spot-checks one "heavy" bar: prints raw OHLCV so the volume-vs-threshold
     comparison can be verified by eye.
"""

import pandas as pd

from fetch_5000_daily import fetch_one

PERIODO = 20
FATOR = 1.25


def pine_ema(series: pd.Series, length: int) -> pd.Series:
    """Pine-script style EMA: SMA seed, then recursive update."""
    alpha = 2.0 / (length + 1)
    out = series.copy().astype(float)
    values = out.values
    import math
    ema = [math.nan] * len(values)
    for i in range(len(values)):
        if i == length - 1:                      # seed = SMA of first `length` bars
            ema[i] = sum(values[:length]) / length
        elif i >= length:
            ema[i] = alpha * values[i] + (1 - alpha) * ema[i - 1]
    out[:] = ema
    return out


def volume_candle(df: pd.DataFrame) -> pd.DataFrame:
    """Add candle color classification columns matching the Pine study."""
    d = df.copy()
    d["up"] = d["close"] > d["open"]
    d["down"] = d["open"] > d["close"]
    d["vol_ema"] = pine_ema(d["volume"], PERIODO)
    d["vol_threshold"] = d["vol_ema"] * FATOR
    d["pesado"] = d["volume"] > d["vol_threshold"]

    def color(row):
        if row["pesado"] and row["up"]:
            return "lime"
        if row["pesado"] and row["down"]:
            return "red"
        if row["up"]:
            return "silver"
        return "gray"

    d["bar_color"] = d.apply(color, axis=1)
    return d


def verify(d: pd.DataFrame, symbol: str):
    # 1. Cross-check EMA against pandas ewm (equivalent recursion)
    pd_ema = d["volume"].ewm(span=PERIODO, adjust=False).mean()
    diff = (d["vol_ema"].dropna() - pd_ema[d["vol_ema"].notna()]).abs().max()
    print(f"  EMA check ({symbol}): max |pine_ema - pandas_ewm| = {diff:.6f}")

    # 2. Color-rule sanity: no impossible combos
    bad = d[(d["pesado"] & d["up"] & (d["bar_color"] != "lime"))
            | (d["pesado"] & d["down"] & (d["bar_color"] != "red"))
            | (~d["pesado"] & d["up"] & (d["bar_color"] != "silver"))
            | (~d["pesado"] & ~d["up"] & (d["bar_color"] != "gray"))]
    print(f"  Rule check: {'PASS (0 inconsistencies)' if bad.empty else f'FAIL {len(bad)} rows'}")

    # 3. Spot-check the most recent heavy bar manually
    heavy = d[d["pesado"]]
    if heavy.empty:
        print("  No heavy bars in sample")
        return
    hb = heavy.iloc[-1]
    print(f"  Manual spot-check (last lime/red bar):")
    print(f"    date={hb.name:%Y-%m-%d}  vol={hb['volume']:.0f}  "
          f"ema20*1.25={hb['vol_threshold']:.0f}  "
          f"vol>thr -> {hb['volume'] > hb['vol_threshold']}  "
          f"candle: open={hb['open']} close={hb['close']} "
          f"(up={hb['close'] > hb['open']})  -> color={hb['bar_color']}")


if __name__ == "__main__":
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    for s in symbols:
        sym, df, err = fetch_one(s)
        print(f"\n=== {sym} ===")
        if df is None:
            print(f"  fetch failed: {err}  (retrying once...)")
            sym, df, err = fetch_one(s)
        if df is None:
            print(f"  FAILED: {err}")
            continue
        d = volume_candle(df)
        counts = d["bar_color"].value_counts()
        print("  Color distribution:", dict(counts))
        verify(d, sym)
