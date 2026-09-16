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


def _simplified_short_score_series(df: pd.DataFrame):
    """Version espejo (bajista) del score simplificado, para backtestear
    el lado SHORT: premia EMAs en orden bajista, MACD bajista, RSI debil
    y volumen alto en dias de baja."""
    close = df["Close"]
    mas = compute_all_mas(close)
    rsi_s = rsi(close, 14)
    macd_line, signal_line, hist = macd(close)
    atr_s = atr(df, 14)
    vol_avg = df["Volume"].rolling(20).mean()

    ema9, ema20, ema50 = mas["ema9"], mas["ema20"], mas["ema50"]

    trend_score = (
        (ema9 < ema20).astype(float) * 10 +
        (ema20 < ema50).astype(float) * 10 +
        (close < ema20).astype(float) * 10
    )
    momentum_score = ((macd_line < signal_line).astype(float) * 15 +
                       (hist < 0).astype(float) * 10)
    rsi_score = pd.Series(np.select(
        [rsi_s > 70, rsi_s > 55, rsi_s >= 45, rsi_s >= 30, rsi_s < 30],
        [15, 10, 12, 20, 10],
        default=10,
    ), index=rsi_s.index).astype(float)
    price_down = close.diff() < 0
    volume_score = ((df["Volume"] > 1.5 * vol_avg) & price_down).astype(float) * 15

    total = trend_score + momentum_score + rsi_score + volume_score
    return total.clip(0, 100), atr_s


def run_backtest(df: pd.DataFrame, entry_threshold: float = 65, stop_atr_mult: float = 1.5,
                  target_atr_mult: float = 3.0, max_holding_days: int = 20,
                  commission_pct: float = 0.0, side: str = "long") -> dict:
    if df.empty or len(df) < 30:
        return {"error": "No hay suficientes datos historicos para backtestear (se necesitan al menos 30 velas)."}
    if side not in ("long", "short"):
        side = "long"

    close = df["Close"].reset_index(drop=True)
    dates = df.index
    if side == "long":
        score_series, atr_series = _simplified_score_series(df)
    else:
        score_series, atr_series = _simplified_short_score_series(df)
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
                if side == "long":
                    stop_price = entry_price - stop_atr_mult * atr_series.iloc[i]
                    target_price = entry_price + target_atr_mult * atr_series.iloc[i]
                else:
                    stop_price = entry_price + stop_atr_mult * atr_series.iloc[i]
                    target_price = entry_price - target_atr_mult * atr_series.iloc[i]
        else:
            price_now = close.iloc[i]
            days_held = i - entry_idx
            if side == "long":
                hit_stop = price_now <= stop_price
                hit_target = price_now >= target_price
            else:
                hit_stop = price_now >= stop_price
                hit_target = price_now <= target_price
            timed_out = days_held >= max_holding_days

            if hit_stop or hit_target or timed_out or i == len(close) - 1:
                exit_price = price_now
                if side == "long":
                    gross_return_pct = (exit_price - entry_price) / entry_price * 100
                else:
                    gross_return_pct = (entry_price - exit_price) / entry_price * 100
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

    # ---------- Metricas avanzadas ----------
    # Sharpe y Sortino simplificados: se calculan sobre el retorno POR
    # OPERACION (no por dia), porque las operaciones duran distinto tiempo
    # cada una. Esto NO es el Sharpe ratio anualizado estandar que usan
    # los profesionales (que se calcula sobre retornos diarios de una
    # cartera) -- es una version simplificada, valida solo para comparar
    # configuraciones entre si, no para comparar contra otros activos.
    returns_arr = np.array(returns)
    std_returns = float(np.std(returns_arr, ddof=1)) if len(returns_arr) > 1 else 0.0
    sharpe_simplified = round(avg_return / std_returns, 2) if std_returns > 0 else None

    downside = returns_arr[returns_arr < 0]
    downside_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else (abs(float(downside[0])) if len(downside) == 1 else 0.0)
    sortino_simplified = round(avg_return / downside_std, 2) if downside_std > 0 else None

    expectancy = round((win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss), 2)

    best_trade = max(trades, key=lambda t: t["return_pct"])
    worst_trade = min(trades, key=lambda t: t["return_pct"])
    avg_days_held = round(float(np.mean([t["days_held"] for t in trades])), 1)

    max_consecutive_wins = max_consecutive_losses = 0
    current_streak = 0
    current_type = None
    for r in returns:
        is_win = r > 0
        if current_type == is_win:
            current_streak += 1
        else:
            current_type = is_win
            current_streak = 1
        if is_win:
            max_consecutive_wins = max(max_consecutive_wins, current_streak)
        else:
            max_consecutive_losses = max(max_consecutive_losses, current_streak)

    return {
        "trades": trades,
        "num_trades": len(trades),
        "win_rate_pct": round(win_rate, 1),
        "avg_return_pct": round(avg_return, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "max_drawdown_pct": round(max_drawdown, 2),
        "sharpe_simplified": sharpe_simplified,
        "sortino_simplified": sortino_simplified,
        "expectancy_pct": expectancy,
        "best_trade_pct": best_trade["return_pct"],
        "worst_trade_pct": worst_trade["return_pct"],
        "avg_days_held": avg_days_held,
        "max_consecutive_wins": max_consecutive_wins,
        "max_consecutive_losses": max_consecutive_losses,
        "total_return_pct": round(float(sum(returns)), 2),
        "params": {
            "side": side,
            "entry_threshold": entry_threshold,
            "stop_atr_mult": stop_atr_mult,
            "target_atr_mult": target_atr_mult,
            "max_holding_days": max_holding_days,
            "commission_pct": commission_pct,
        },
        "sample_size_days": len(df),
        "note": "Muestra chica (limitada por el plan gratuito de datos): resultado orientativo, no concluyente estadisticamente." if len(df) < 250 else None,
    }
