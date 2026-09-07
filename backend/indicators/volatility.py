import pandas as pd
import numpy as np


def true_range(df: pd.DataFrame) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    tr = true_range(df)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def adx(df: pd.DataFrame, length: int = 14):
    high, low = df["High"], df["Low"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = true_range(df)
    atr_ = tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()

    plus_dm_s = pd.Series(plus_dm, index=df.index).ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    minus_dm_s = pd.Series(minus_dm, index=df.index).ewm(alpha=1 / length, min_periods=length, adjust=False).mean()

    plus_di = 100 * (plus_dm_s / atr_.replace(0, np.nan))
    minus_di = 100 * (minus_dm_s / atr_.replace(0, np.nan))

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx_line = dx.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    return adx_line, plus_di, minus_di


def interpret_adx(value: float) -> str:
    if value is None:
        return "N/D"
    if value < 20:
        return "mercado_lateral"
    if value < 25:
        return "tendencia_debil"
    if value < 40:
        return "tendencia_fuerte"
    return "tendencia_muy_fuerte"


def bollinger_bands(close: pd.Series, length: int = 20, num_std: float = 2.0):
    mid = close.rolling(length, min_periods=length).mean()
    std = close.rolling(length, min_periods=length).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower
