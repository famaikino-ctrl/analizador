"""
Backtesting simple y honesto.

IMPORTANTE - limitaciones que hay que dejar claras siempre que se muestren
resultados:

1. Solo usa criterios TECNICOS (EMAs, RSI, MACD, volumen). No incluye
   fundamentales ni valuacion, porque no tenemos series historicas de
   esos datos (solo el valor actual) -- incluirlos seria mirar el futuro
   (look-ahead bias). Por eso el backtest evalua una version simplificada
   del sistema, no el score completo que se muestra en el analisis.
2. El plan gratuito de Alpha Vantage solo entrega ~100 dias habiles de
   historial diario. Un backtest sobre 100 dias es una MUESTRA CHICA:
   sirve como demostracion metodologica, no como evidencia estadistica
   solida. Con pocas operaciones, el resultado puede deberse al azar.
3. No se descuentan comisiones ni slippage por defecto (se puede
   configurar una comision aproximada).
4. La entrada se simula en el CIERRE del mismo dia en que se cumple la
   condicion (simplificacion: en la practica real la entrada seria al dia
   siguiente, lo que introduce un pequeño optimismo en el resultado).
5. No es garantia de resultados futuros. Rendimiento pasado no implica
   rendimiento futuro.
"""

import pandas as pd
import numpy as np

from indicators.moving_averages import compute_all_mas
from indicators.oscillators import rsi, macd
from indicators.volatility import atr


def _simplified_score_series(df: pd.DataFrame) -> pd.Series:
    """Score tecnico simplificado (0-100) calculado para CADA dia de la
    serie historica, usando solo indicadores que se pueden calcular sin
    mirar al futuro. No es el mismo score que se muestra en el analisis
    individual (ese incluye fundamentales/valuacion, que no tenemos en
    serie historica)."""
    close = df["Close"]
    mas = compute_all_mas(close)
    rsi_s = rsi(close, 14)
    macd_line, signal_line, hist = macd(close)
    atr_s = atr(df, 14)
    vol_avg = df["Volume"].rolling(20).mean()

    ema9, ema20, ema50 = mas["ema9"], mas["ema20"], mas["ema50"]

    trend_score = (
        (ema9 > ema20).astype(float) * 10 +
        (ema20 > ema50).astype(float) * 10 +
        (close > ema20).astype(float) * 10
    )
    momentum_score = ((macd_line > signal_line).astype(float) * 15 +
                       (hist > 0).astype(float) * 10)
    rsi_score = pd.Series(np.select(
        [rsi_s < 30, rsi_s < 45, rsi_s <= 55, rsi_s <= 70, rsi_s > 70],
        [15, 10, 12, 20, 10],
        default=10,
    ), index=rsi_s.index).astype(float)
    volume_score = (df["Volume"] > 1.5 * vol_avg).astype(float) * 15

    total = trend_score + momentum_score + rsi_score + volume_score
    return total.clip(0, 100), atr_s


def run_backtest(df: pd.DataFrame, entry_threshold: float = 65, stop_atr_mult: float = 1.5,
                  target_atr_mult: float = 3.0, max_holding_days: int = 20,
                  commission_pct: float = 0.0) -> dict:
    if df.empty or len(df) < 30:
        return {"error": "No hay suficientes datos historicos para backtestear (se necesitan al menos 30 velas)."}

    close = df["Close"].reset_index(drop=True)
    dates = df.index
    score_series, atr_series = _simplified_score_series(df)
    score_series = score_series.reset_index(drop=True)
    atr_series = atr_series.reset_index(drop=True)

    trades = []
    in_position = False
    entry_idx = entry_price = stop_price = target_price = None

    for i in range(len(close)):
        if not in_position:
            if pd.notna(score_series.iloc[i]) and score_series.iloc[i] >= entry_threshold and pd.notna(atr_series.iloc[i]):
                in_position = True
                entry_idx = i
                entry_price = close.iloc[i]
                stop_price = entry_price - stop_atr_mult * atr_series.iloc[i]
                target_price = entry_price + target_atr_mult * atr_series.iloc[i]
        else:
            price_now = close.iloc[i]
            days_held = i - entry_idx
            hit_stop = price_now <= stop_price
            hit_target = price_now >= target_price
            timed_out = days_held >= max_holding_days

            if hit_stop or hit_target or timed_out or i == len(close) - 1:
                exit_price = price_now
                gross_return_pct = (exit_price - entry_price) / entry_price * 100
                net_return_pct = gross_return_pct - (commission_pct * 2)
                outcome = "objetivo" if hit_target else ("stop" if hit_stop else "tiempo_agotado")
                trades.append({
                    "entry_date": dates[entry_idx].strftime("%Y-%m-%d"),
                    "exit_date": dates[i].strftime("%Y-%m-%d"),
                    "entry_price": round(float(entry_price), 2),
                    "exit_price": round(float(exit_price), 2),
                    "return_pct": round(float(net_return_pct), 2),
                    "days_held": int(days_held),
                    "outcome": outcome,
                })
                in_position = False

    if not trades:
        return {
            "trades": [],
            "num_trades": 0,
            "note": f"No se generaron operaciones con el umbral de score >= {entry_threshold} en el periodo disponible.",
        }

    returns = [t["return_pct"] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    win_rate = len(wins) / len(trades) * 100
    avg_return = float(np.mean(returns))
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else None
    cumulative = np.cumsum(returns)
    running_max = np.maximum.accumulate(cumulative) if len(cumulative) else np.array([0])
    max_drawdown = float(np.min(cumulative - running_max)) if len(cumulative) else 0.0

    return {
        "trades": trades,
        "num_trades": len(trades),
        "win_rate_pct": round(win_rate, 1),
        "avg_return_pct": round(avg_return, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "max_drawdown_pct": round(max_drawdown, 2),
        "total_return_pct": round(float(sum(returns)), 2),
        "params": {
            "entry_threshold": entry_threshold,
            "stop_atr_mult": stop_atr_mult,
            "target_atr_mult": target_atr_mult,
            "max_holding_days": max_holding_days,
            "commission_pct": commission_pct,
        },
        "sample_size_days": len(df),
        "note": "Muestra chica (limitada por el plan gratuito de datos): resultado orientativo, no concluyente estadisticamente." if len(df) < 250 else None,
    }
