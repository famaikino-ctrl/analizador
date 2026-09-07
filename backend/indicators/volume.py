import pandas as pd


def average_volume(volume: pd.Series, length: int = 20) -> pd.Series:
    return volume.rolling(length, min_periods=length).mean()


def is_abnormal_volume(volume: pd.Series, length: int = 20, multiple: float = 2.0) -> bool:
    avg = average_volume(volume, length)
    if avg.dropna().empty:
        return False
    last_vol = volume.iloc[-1]
    last_avg = avg.iloc[-1]
    if pd.isna(last_avg) or last_avg == 0:
        return False
    return bool(last_vol >= multiple * last_avg)


def vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP acumulado del período cargado. Sólo tiene sentido pleno en
    datos intradía; para timeframes diarios se calcula igualmente mostrando
    el VWAP acumulado de la serie como referencia de precio promedio ponderado."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
    cum_vol = df["Volume"].cumsum()
    cum_vol_price = (typical_price * df["Volume"]).cumsum()
    return cum_vol_price / cum_vol.replace(0, pd.NA)
