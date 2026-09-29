"""
Analisis de correlacion entre las posiciones de una cartera.

Complementa (no reemplaza) el analisis de concentracion por sector: dos
acciones del MISMO sector pueden moverse de forma bastante independiente,
mientras que dos de sectores DISTINTOS a veces se mueven casi identicas
(por ejemplo, si ambas dependen mucho del mismo factor macro). Mirar solo
el sector puede dar una falsa sensacion de diversificacion.

Se calcula sobre los retornos diarios de cada ticker en el periodo
disponible (reutiliza los datos que el analisis normal ya trae, sin
consultas adicionales a la API).
"""

import pandas as pd
import numpy as np


def compute_correlation_matrix(closes_by_ticker: dict) -> dict:
    """closes_by_ticker: { "AAPL": [{"time": "2026-01-01", "close": 150.0}, ...], ... }
    Devuelve la matriz de correlacion de retornos diarios y una lista de
    pares con correlacion alta (>= 0.7) o muy alta (>= 0.85)."""
    series = {}
    for ticker, candles in closes_by_ticker.items():
        if not candles:
            continue
        s = pd.Series(
            {c["time"]: c["close"] for c in candles if c.get("close") is not None}
        )
        s.index = pd.to_datetime(s.index)
        series[ticker] = s.sort_index()

    if len(series) < 2:
        return {"matrix": {}, "high_correlation_pairs": [], "note": "Se necesitan al menos 2 posiciones con datos para calcular correlacion."}

    df = pd.DataFrame(series)
    df = df.dropna(how="any")  # solo fechas donde TODOS los tickers tienen dato
    if len(df) < 10:
        return {"matrix": {}, "high_correlation_pairs": [], "note": "No hay suficientes fechas en comun entre las posiciones para calcular correlacion de forma confiable."}

    returns = df.pct_change().dropna()
    corr = returns.corr()

    matrix = {t1: {t2: round(float(corr.loc[t1, t2]), 2) for t2 in corr.columns} for t1 in corr.index}

    high_pairs = []
    tickers = list(corr.columns)
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            t1, t2 = tickers[i], tickers[j]
            value = corr.loc[t1, t2]
            if pd.isna(value):
                continue
            if value >= 0.85:
                level = "muy_alta"
            elif value >= 0.7:
                level = "alta"
            else:
                continue
            high_pairs.append({"ticker_a": t1, "ticker_b": t2, "correlation": round(float(value), 2), "level": level})

    high_pairs.sort(key=lambda p: -p["correlation"])

    return {"matrix": matrix, "high_correlation_pairs": high_pairs, "note": None, "sample_days": len(returns)}
