"""
Nivel de confianza por confluencia de señales.

IMPORTANTE: esto NO es una probabilidad de éxito ni una garantía de nada.
Es simplemente un conteo de cuántas familias de indicadores INDEPENDIENTES
(tendencia, momentum, RSI, volumen, soportes/resistencias, fundamentales,
valuación, EMAs largas) apuntan en la misma dirección que la señal
sugerida. Más señales de acuerdo entre sí suele ser un filtro razonable
para descartar entradas donde los indicadores se contradicen entre ellos,
pero no predice el futuro.
"""


def compute_confluence(direction: str, ema_flags: dict, macd_info: dict, rsi_interpretation: str,
                        volume_abnormal: bool, price_change_pct, nearest_level_favorable: bool,
                        fundamentals_favorable: bool, valuation_favorable: bool) -> dict:
    if direction not in ("LONG", "SHORT"):
        return {
            "level": "Sin dirección clara",
            "color": "gray",
            "agreeing": 0,
            "total_checked": 0,
            "factors": [],
        }

    is_long = direction == "LONG"
    factors = []

    # Tendencia (EMAs)
    trend_checks = [ema_flags.get(k) for k in ("ema9_gt_ema20", "ema20_gt_ema50", "ema50_gt_ema200", "price_gt_ema200", "price_gt_ema50")]
    valid_trend = [c for c in trend_checks if c is not None]
    if valid_trend:
        trend_agree = sum(1 for c in valid_trend if (c if is_long else not c))
        agrees = trend_agree >= len(valid_trend) / 2
        factors.append({"name": "Tendencia (EMAs)", "agrees": agrees})

    # Momentum (MACD)
    if macd_info and macd_info.get("cross") != "N/D":
        bullish_macd = macd_info.get("cross") in ("cruce_alcista", "alcista") and macd_info.get("histogram") == "positivo"
        bearish_macd = macd_info.get("cross") in ("cruce_bajista", "bajista") and macd_info.get("histogram") == "negativo"
        agrees = bullish_macd if is_long else bearish_macd
        factors.append({"name": "Momentum (MACD)", "agrees": agrees})

    # RSI
    if rsi_interpretation not in (None, "N/D"):
        favorable_long = rsi_interpretation in ("fortaleza", "neutral")
        favorable_short = rsi_interpretation in ("debil", "neutral")
        agrees = favorable_long if is_long else favorable_short
        factors.append({"name": "RSI", "agrees": agrees})

    # Volumen
    if volume_abnormal is not None and price_change_pct is not None:
        price_moving_favorably = (price_change_pct > 0) if is_long else (price_change_pct < 0)
        agrees = bool(volume_abnormal and price_moving_favorably)
        factors.append({"name": "Volumen", "agrees": agrees})

    # Soportes/Resistencias
    if nearest_level_favorable is not None:
        factors.append({"name": "Soportes/Resistencias", "agrees": bool(nearest_level_favorable)})

    # Fundamentales
    if fundamentals_favorable is not None:
        factors.append({"name": "Fundamentales", "agrees": bool(fundamentals_favorable)})

    # Valuación
    if valuation_favorable is not None:
        factors.append({"name": "Valuación", "agrees": bool(valuation_favorable)})

    total = len(factors)
    agreeing = sum(1 for f in factors if f["agrees"])

    if total == 0:
        level, color = "Datos insuficientes", "gray"
    else:
        ratio = agreeing / total
        if ratio >= 0.8:
            level, color = "Alta confluencia", "green"
        elif ratio >= 0.5:
            level, color = "Confluencia moderada", "yellow"
        else:
            level, color = "Baja confluencia (señales contradictorias)", "red"

    return {"level": level, "color": color, "agreeing": agreeing, "total_checked": total, "factors": factors}
