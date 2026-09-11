import math
import pandas as pd

from services.data_provider import DataProvider
from indicators.moving_averages import compute_all_mas, last_valid, detect_cross
from indicators.oscillators import rsi, interpret_rsi, macd, macd_state, detect_macd_divergence, stochastic_rsi
from indicators.volatility import atr, adx, interpret_adx, bollinger_bands
from indicators.volume import average_volume, is_abnormal_volume, vwap
from levels.support_resistance import detect_levels
from levels.fibonacci import compute_fibonacci, match_fib_with_levels
from valuation.price_target import compute_price_target
from scoring.score import compute_score
from scoring.short_score import compute_short_score, determine_direction
from scoring.signals import signal_from_score, multi_horizon_trend, build_alerts, build_conclusion, build_short_conclusion, classify_trade_style
from scoring.scanner import compute_breakout_score, compute_momentum_5d
from strategies.entry_strategies import build_strategies, build_short_strategies


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (int,)):
        return v
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 6)
    return v


def _nd(v, transform=None):
    """Devuelve 'N/D' si el valor es None; si no, aplica transform (opcional)."""
    if v is None:
        return "N/D"
    return transform(v) if transform else v


PERIOD_MAP = {
    "1D": ("5d", "5m"),
    "1W": ("1mo", "30m"),
    "1M": ("3mo", "1d"),
    "3M": ("6mo", "1d"),
    "6M": ("1y", "1d"),
    "1Y": ("2y", "1d"),
    "3Y": ("5y", "1wk"),
    "5Y": ("10y", "1wk"),
    "MAX": ("max", "1mo"),
}


def analyze_ticker(provider: DataProvider, ticker: str, timeframe: str = "1Y") -> dict:
    period, interval = PERIOD_MAP.get(timeframe, ("2y", "1d"))

    # Para calcular EMA200 con solidez siempre pedimos al menos 2 años de
    # velas diarias como base para los indicadores, aunque el timeframe
    # visual elegido por el usuario sea otro (se recorta luego para el chart).
    df_calc = provider.get_price_history(ticker, period="2y", interval="1d")
    if df_calc.empty:
        return {"error": f"No se encontraron datos para el ticker '{ticker}'. Verifica que sea correcto."}

    df_chart = provider.get_price_history(ticker, period=period, interval=interval)
    if df_chart.empty:
        df_chart = df_calc

    quote = provider.get_quote(ticker)
    company = provider.get_company_info(ticker)
    fundamentals = provider.get_fundamentals(ticker)
    analyst_target = provider.get_analyst_target(ticker)

    close = df_calc["Close"]
    current_price = quote.get("price") or float(close.iloc[-1])

    # ---------- Medias móviles ----------
    mas = compute_all_mas(close)
    ma_last = {k: last_valid(v) for k, v in mas.items()}

    ema_flags = {
        "ema9_gt_ema20": (ma_last["ema9"] is not None and ma_last["ema20"] is not None and ma_last["ema9"] > ma_last["ema20"]),
        "ema20_gt_ema50": (ma_last["ema20"] is not None and ma_last["ema50"] is not None and ma_last["ema20"] > ma_last["ema50"]),
        "ema50_gt_ema200": (ma_last["ema50"] is not None and ma_last["ema200"] is not None and ma_last["ema50"] > ma_last["ema200"]),
        "price_gt_ema200": (ma_last["ema200"] is not None and current_price > ma_last["ema200"]),
        "price_gt_ema50": (ma_last["ema50"] is not None and current_price > ma_last["ema50"]),
    }

    cross_9_20 = detect_cross(mas["ema9"], mas["ema20"])
    cross_20_50 = detect_cross(mas["ema20"], mas["ema50"])
    cross_50_200 = detect_cross(mas["ema50"], mas["ema200"])

    # ---------- Osciladores ----------
    rsi_series = rsi(close, 14)
    rsi_value = last_valid(rsi_series)
    rsi_interp = interpret_rsi(rsi_value)

    macd_line, signal_line, hist = macd(close)
    macd_info = macd_state(macd_line, signal_line, hist)
    macd_divergence = detect_macd_divergence(close, macd_line)

    k, d = stochastic_rsi(close)
    stoch_k, stoch_d = last_valid(k), last_valid(d)

    # ---------- Volatilidad ----------
    atr_series = atr(df_calc, 14)
    atr_value = last_valid(atr_series)

    adx_line, plus_di, minus_di = adx(df_calc, 14)
    adx_value = last_valid(adx_line)
    adx_interp = interpret_adx(adx_value)

    bb_upper, bb_mid, bb_lower = bollinger_bands(close, 20, 2.0)

    # ---------- Volumen ----------
    vol_avg_series = average_volume(df_calc["Volume"], 20)
    vol_avg = last_valid(vol_avg_series)
    vol_abnormal = is_abnormal_volume(df_calc["Volume"], 20, 2.0)
    price_up_today = quote.get("change_pct") is not None and quote["change_pct"] > 0
    vwap_series = vwap(df_calc.tail(60))
    vwap_value = last_valid(vwap_series)

    # ---------- Soportes / Resistencias ----------
    levels = detect_levels(df_calc, current_price, quote.get("week52_high"), quote.get("week52_low"))
    broke_resistance = bool(levels["resistances"] and levels["resistances"][0]["distance_pct"] < 0)
    lost_support = bool(levels["supports"] and levels["supports"][0]["distance_pct"] > 0)

    # ---------- Fibonacci ----------
    fib = compute_fibonacci(df_calc, lookback=120)
    if fib:
        fib["levels"] = match_fib_with_levels(fib["levels"], levels)

    # ---------- Valuación / Precio objetivo ----------
    price_target = compute_price_target(current_price, fundamentals, analyst_target)

    # ---------- Score y señal ----------
    score = compute_score(
        ema_flags, macd_info, rsi_value, rsi_interp,
        levels["supports"], levels["resistances"],
        vol_abnormal, price_up_today, fundamentals, price_target.get("upside_pct"),
    )
    signal = signal_from_score(score["total"])

    trends = multi_horizon_trend(mas, current_price)

    alerts = build_alerts(cross_9_20, cross_20_50, cross_50_200, rsi_interp,
                           broke_resistance, lost_support, vol_abnormal)

    fundamentals_ok = score["breakdown"]["fundamentales"] >= 9

    nearest_support = levels["supports"][0] if levels["supports"] else None
    nearest_resistance = levels["resistances"][0] if levels["resistances"] else None

    conclusion = build_conclusion(score, signal, trends, fundamentals_ok,
                                   price_target.get("upside_pct"), current_price, atr_value,
                                   nearest_support, nearest_resistance)

    strategies = build_strategies(current_price, atr_value, ma_last["ema20"], ma_last["ema50"],
                                   nearest_support, nearest_resistance, rsi_value)

    # ---------- Score, conclusion y estrategias del lado SHORT ----------
    price_down_today = quote.get("change_pct") is not None and quote["change_pct"] < 0
    short_score = compute_short_score(
        ema_flags, macd_info, rsi_value, rsi_interp,
        levels["supports"], levels["resistances"],
        vol_abnormal, price_down_today, fundamentals, price_target.get("upside_pct"),
    )
    direction = determine_direction(score["total"], short_score["total"])

    short_conclusion = build_short_conclusion(short_score, trends, current_price, atr_value,
                                               nearest_support, nearest_resistance)
    short_strategies = build_short_strategies(current_price, atr_value, ma_last["ema20"], ma_last["ema50"],
                                               nearest_support, nearest_resistance, rsi_value)

    # ---------- Estilo de trade sugerido ----------
    atr_pct = (atr_value / current_price * 100) if (atr_value and current_price) else None
    trade_style = classify_trade_style(atr_pct, adx_value, score["total"], score["breakdown"]["fundamentales"])

    # ---------- Screener de ruptura (breakout) ----------
    momentum_5d = compute_momentum_5d(close)
    breakout = compute_breakout_score(
        rsi_value, macd_info, adx_value, vol_abnormal,
        nearest_resistance["distance_pct"] if nearest_resistance else None,
        momentum_5d,
    )

    # ---------- Serie de velas para el chart ----------
    chart_df = df_chart.tail(500)
    candles = []
    for idx, row in chart_df.iterrows():
        candles.append({
            "time": idx.strftime("%Y-%m-%d") if interval not in ("5m", "30m") else idx.strftime("%Y-%m-%dT%H:%M:%S"),
            "open": _clean(float(row["Open"])),
            "high": _clean(float(row["High"])),
            "low": _clean(float(row["Low"])),
            "close": _clean(float(row["Close"])),
            "volume": _clean(float(row["Volume"])),
        })

    ema_overlays = {}
    for key in ("ema9", "ema20", "ema50", "ema200"):
        series = mas[key].reindex(chart_df.index)
        ema_overlays[key] = [
            {"time": idx.strftime("%Y-%m-%d") if interval not in ("5m", "30m") else idx.strftime("%Y-%m-%dT%H:%M:%S"),
             "value": _clean(float(v))}
            for idx, v in series.items() if not pd.isna(v)
        ]

    return {
        "ticker": ticker.upper(),
        "company": company,
        "quote": {k: _clean(v) for k, v in quote.items() if k != "as_of"} | {"as_of": quote.get("as_of")},
        "data_freshness": {
            "precio": "tiempo real / con posible retraso de 15 min (Yahoo Finance)",
            "fundamentales": "datos trimestrales/anuales mas recientes reportados",
            "actualizado": quote.get("as_of"),
        },
        "moving_averages": {k: _clean(v) for k, v in ma_last.items()},
        "ema_flags": ema_flags,
        "crosses": {"ema9_20": cross_9_20, "ema20_50": cross_20_50, "ema50_200": cross_50_200},
        "oscillators": {
            "rsi": _clean(rsi_value),
            "rsi_interpretation": rsi_interp,
            "macd_line": _clean(last_valid(macd_line)),
            "macd_signal": _clean(last_valid(signal_line)),
            "macd_histogram": _clean(last_valid(hist)),
            "macd_state": macd_info,
            "macd_divergence": macd_divergence,
            "stochastic_rsi_k": _clean(stoch_k),
            "stochastic_rsi_d": _clean(stoch_d),
        },
        "volatility": {
            "atr": _clean(atr_value),
            "adx": _clean(adx_value),
            "adx_interpretation": adx_interp,
            "bollinger_upper": _clean(last_valid(bb_upper)),
            "bollinger_mid": _clean(last_valid(bb_mid)),
            "bollinger_lower": _clean(last_valid(bb_lower)),
        },
        "volume": {
            "current": _clean(quote.get("volume")),
            "average_20d": _clean(vol_avg),
            "abnormal": vol_abnormal,
            "vwap_60d": _clean(vwap_value),
        },
        "levels": levels,
        "fibonacci": fib,
        "fundamentals": {k: _clean(v) for k, v in fundamentals.items()},
        "analyst_target": analyst_target,
        "price_target": price_target,
        "score": score,
        "signal": signal,
        "short_score": short_score,
        "direction": direction,
        "trends": trends,
        "alerts": alerts,
        "conclusion": conclusion,
        "short_conclusion": short_conclusion,
        "trade_style": trade_style,
        "breakout": breakout,
        "strategies": strategies,
        "short_strategies": short_strategies,
        "chart": {
            "candles": candles,
            "ema_overlays": ema_overlays,
            "supports": [s["price"] for s in levels["supports"]],
            "resistances": [r["price"] for r in levels["resistances"]],
            "fibonacci_levels": [lv["price"] for lv in fib["levels"]] if fib else [],
        },
    }
