import pandas as pd
import numpy as np


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On Balance Volume: acumula el volumen sumando en dias de suba y
    restando en dias de baja. Su pendiente (no el valor absoluto) es lo
    que importa: OBV subiendo confirma la tendencia de precio; OBV
    divergiendo del precio es una señal de alerta."""
    direction = np.sign(close.diff().fillna(0))
    return (direction * volume).cumsum()


def obv_trend(obv_series: pd.Series, lookback: int = 10) -> str:
    s = obv_series.dropna()
    if len(s) < lookback + 1:
        return "N/D"
    change = s.iloc[-1] - s.iloc[-lookback]
    if change > 0:
        return "confirma_alcista"
    if change < 0:
        return "confirma_bajista"
    return "plano"


def roc(close: pd.Series, length: int = 10) -> pd.Series:
    """Rate of Change: variacion porcentual respecto a `length` periodos atras."""
    return (close / close.shift(length) - 1) * 100


def momentum(close: pd.Series, length: int = 10) -> pd.Series:
    """Momentum simple: diferencia absoluta respecto a `length` periodos atras."""
    return close - close.shift(length)


def relative_volume(volume: pd.Series, length: int = 20) -> float:
    """Volumen del ultimo dia dividido por el promedio de los ultimos
    `length` dias (sin contar el ultimo). >1.5 suele considerarse volumen
    inusualmente alto; <0.5 inusualmente bajo."""
    if len(volume) < length + 1:
        return None
    avg = volume.iloc[-(length + 1):-1].mean()
    if not avg:
        return None
    return float(volume.iloc[-1] / avg)


def classic_pivot_points(prev_high: float, prev_low: float, prev_close: float) -> dict:
    """Pivot points clasicos (metodo estandar de floor trader), calculados
    sobre el maximo/minimo/cierre del PERIODO ANTERIOR (la sesion o semana
    previa, segun el timeframe elegido). Son niveles de referencia muy
    usados para intradia y swing trading."""
    pp = (prev_high + prev_low + prev_close) / 3
    r1 = 2 * pp - prev_low
    s1 = 2 * pp - prev_high
    r2 = pp + (prev_high - prev_low)
    s2 = pp - (prev_high - prev_low)
    r3 = prev_high + 2 * (pp - prev_low)
    s3 = prev_low - 2 * (prev_high - pp)
    return {
        "pp": round(pp, 4),
        "r1": round(r1, 4), "r2": round(r2, 4), "r3": round(r3, 4),
        "s1": round(s1, 4), "s2": round(s2, 4), "s3": round(s3, 4),
    }
