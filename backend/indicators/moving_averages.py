import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length, min_periods=length).mean()


def compute_all_mas(close: pd.Series) -> dict:
    return {
        "ema9": ema(close, 9),
        "ema20": ema(close, 20),
        "ema50": ema(close, 50),
        "ema100": ema(close, 100),
        "ema200": ema(close, 200),
        "sma20": sma(close, 20),
        "sma50": sma(close, 50),
        "sma200": sma(close, 200),
    }


def last_valid(series: pd.Series):
    s = series.dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def detect_cross(fast: pd.Series, slow: pd.Series, lookback: int = 5) -> str:
    """Devuelve: 'golden_recent', 'death_recent', 'bullish', 'bearish', 'none'"""
    f = fast.dropna()
    s = slow.dropna()
    n = min(len(f), len(s))
    if n < 2:
        return "none"
    f = f.iloc[-n:]
    s = s.iloc[-n:]
    diff = f.values - s.values
    if diff[-1] > 0 and diff[-2] <= 0:
        return "golden_recent"
    if diff[-1] < 0 and diff[-2] >= 0:
        return "death_recent"
    window = min(lookback, len(diff))
    crossed_up = any(diff[-window] <= 0 for _ in [0]) if window else False
    # revisar si hubo cruce alcista/bajista dentro del lookback
    for i in range(-window, -1):
        if diff[i] <= 0 and diff[i + 1] > 0:
            return "bullish"
        if diff[i] >= 0 and diff[i + 1] < 0:
            return "bearish"
    return "bullish" if diff[-1] > 0 else "bearish"
