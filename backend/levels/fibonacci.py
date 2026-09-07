import pandas as pd

FIB_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]


def _find_last_major_swing(df: pd.DataFrame, lookback: int = 120):
    """Toma la ventana reciente y ubica el máximo y mínimo absolutos dentro
    de ella como el 'movimiento relevante más reciente'. Si el mínimo ocurre
    después del máximo, el movimiento dominante es bajista (retroceso hacia
    arriba); si el máximo ocurre después del mínimo, es alcista."""
    window = df.tail(lookback)
    if window.empty:
        return None
    idx_max = window["High"].idxmax()
    idx_min = window["Low"].idxmin()
    price_max = float(window.loc[idx_max, "High"])
    price_min = float(window.loc[idx_min, "Low"])
    trend_up = idx_max > idx_min  # el máximo es más reciente => tramo alcista
    return {
        "high": price_max,
        "low": price_min,
        "high_date": idx_max,
        "low_date": idx_min,
        "trend_up": trend_up,
    }


def compute_fibonacci(df: pd.DataFrame, lookback: int = 120):
    swing = _find_last_major_swing(df, lookback)
    if swing is None:
        return None

    high, low = swing["high"], swing["low"]
    diff = high - low
    levels = []
    for ratio in FIB_RATIOS:
        if swing["trend_up"]:
            # Retroceso desde el máximo hacia el mínimo
            price = high - diff * ratio
        else:
            # Retroceso desde el mínimo hacia el máximo
            price = low + diff * ratio
        levels.append({"ratio": ratio, "price": round(price, 4)})

    return {
        "swing_high": round(high, 4),
        "swing_low": round(low, 4),
        "swing_high_date": swing["high_date"].strftime("%Y-%m-%d"),
        "swing_low_date": swing["low_date"].strftime("%Y-%m-%d"),
        "direction": "alcista" if swing["trend_up"] else "bajista",
        "levels": levels,
    }


def match_fib_with_levels(fib_levels, sr_levels, tolerance_pct: float = 1.5):
    """Marca qué niveles de Fibonacci coinciden (dentro de tolerance_pct%)
    con soportes/resistencias ya detectados."""
    all_sr = (sr_levels.get("supports", []) if sr_levels else []) + \
             (sr_levels.get("resistances", []) if sr_levels else [])
    for fl in fib_levels:
        fl["matches_sr"] = None
        for sr in all_sr:
            if sr["price"] == 0:
                continue
            if abs(fl["price"] - sr["price"]) / sr["price"] * 100 <= tolerance_pct:
                fl["matches_sr"] = sr["label"]
                break
    return fib_levels
