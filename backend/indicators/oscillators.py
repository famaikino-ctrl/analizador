import pandas as pd
import numpy as np


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    out[avg_loss == 0] = 100
    return out


def interpret_rsi(value: float) -> str:
    if value is None:
        return "N/D"
    if value < 30:
        return "sobreventa"
    if value < 45:
        return "debil"
    if value <= 55:
        return "neutral"
    if value <= 70:
        return "fortaleza"
    return "sobrecompra"


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def macd_state(macd_line: pd.Series, signal_line: pd.Series, hist: pd.Series) -> dict:
    m = macd_line.dropna()
    s = signal_line.dropna()
    h = hist.dropna()
    if len(m) < 2 or len(s) < 2:
        return {"cross": "N/D", "histogram": "N/D"}
    cross = "ninguno"
    if m.iloc[-1] > s.iloc[-1] and m.iloc[-2] <= s.iloc[-2]:
        cross = "cruce_alcista"
    elif m.iloc[-1] < s.iloc[-1] and m.iloc[-2] >= s.iloc[-2]:
        cross = "cruce_bajista"
    elif m.iloc[-1] > s.iloc[-1]:
        cross = "alcista"
    else:
        cross = "bajista"
    histogram = "positivo" if (not h.empty and h.iloc[-1] > 0) else "negativo"
    return {"cross": cross, "histogram": histogram}


def _local_extrema(series, kind="min", window=2):
    idxs = []
    for i in range(window, len(series) - window):
        seg = series.iloc[i - window:i + window + 1]
        if kind == "min" and series.iloc[i] == seg.min():
            idxs.append(i)
        if kind == "max" and series.iloc[i] == seg.max():
            idxs.append(i)
    return idxs


def _detect_divergence(close: pd.Series, indicator: pd.Series, lookback: int = 30, window: int = 2) -> str:
    """Heuristica generica de divergencia precio vs. indicador (sirve para
    MACD o RSI): compara los dos ultimos minimos/maximos locales del precio
    contra los del indicador en la ventana `lookback`. Es una aproximacion
    estadistica, no un detector de patrones certero -- puede dar falsos
    positivos/negativos, especialmente con series cortas."""
    c = close.tail(lookback).reset_index(drop=True)
    ind = indicator.tail(lookback).reset_index(drop=True)
    if len(c) < 10 or ind.isna().all():
        return "sin_datos_suficientes"

    lows = _local_extrema(c, "min", window)
    highs = _local_extrema(c, "max", window)

    if len(lows) >= 2:
        i1, i2 = lows[-2], lows[-1]
        if c.iloc[i2] < c.iloc[i1] and ind.iloc[i2] > ind.iloc[i1]:
            return "divergencia_alcista"
    if len(highs) >= 2:
        i1, i2 = highs[-2], highs[-1]
        if c.iloc[i2] > c.iloc[i1] and ind.iloc[i2] < ind.iloc[i1]:
            return "divergencia_bajista"
    return "sin_divergencia_clara"


def detect_macd_divergence(close: pd.Series, macd_line: pd.Series, lookback: int = 30) -> str:
    return _detect_divergence(close, macd_line, lookback)


def detect_rsi_divergence(close: pd.Series, rsi_series: pd.Series, lookback: int = 30) -> str:
    return _detect_divergence(close, rsi_series, lookback)


def stochastic_rsi(close: pd.Series, rsi_length: int = 14, stoch_length: int = 14,
                    k_smooth: int = 3, d_smooth: int = 3):
    r = rsi(close, rsi_length)
    min_r = r.rolling(stoch_length).min()
    max_r = r.rolling(stoch_length).max()
    stoch = (r - min_r) / (max_r - min_r).replace(0, np.nan) * 100
    k = stoch.rolling(k_smooth).mean()
    d = k.rolling(d_smooth).mean()
    return k, d
