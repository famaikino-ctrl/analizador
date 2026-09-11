"""
Sistema de puntuacion para el lado SHORT (venta en corto), simetrico al de
score.py mas para tendencia bajista. Igual que el score LONG: es un modelo
cuantitativo simple y educativo, NO una recomendacion financiera.

Pesos (total 100):
  Tendencia bajista EMA   25
  Momentum bajista MACD   15
  RSI (debilidad)         10
  Resistencia/Soporte     10
  Volumen (bajista)       10
  Fundamentales debiles   15
  Sobrevaluacion           5
"""


def _score_trend_bearish(ema_flags: dict) -> float:
    checks = [
        ema_flags.get("ema9_gt_ema20") is False,
        ema_flags.get("ema20_gt_ema50") is False,
        ema_flags.get("ema50_gt_ema200") is False,
        ema_flags.get("price_gt_ema200") is False,
        ema_flags.get("price_gt_ema50") is False,
    ]
    valid = [c for c in checks]
    if not any(v is not None for v in [ema_flags.get(k) for k in
               ("ema9_gt_ema20", "ema20_gt_ema50", "ema50_gt_ema200", "price_gt_ema200", "price_gt_ema50")]):
        return 12.5
    ratio = sum(1 for c in checks if c) / len(checks)
    return round(ratio * 25, 2)


def _score_momentum_bearish(macd_info: dict) -> float:
    if not macd_info or macd_info.get("cross") == "N/D":
        return 7.5
    score = 7.5
    if macd_info["cross"] in ("cruce_bajista", "bajista"):
        score += 5
    elif macd_info["cross"] in ("cruce_alcista", "alcista"):
        score -= 5
    if macd_info.get("histogram") == "negativo":
        score += 2.5
    else:
        score -= 2.5
    return round(max(0, min(15, score)), 2)


def _score_rsi_bearish(rsi_value, rsi_interpretation: str) -> float:
    if rsi_value is None:
        return 5.0
    mapping = {
        "sobreventa": 4.0,   # ya muy vendido, short mas riesgoso (rebote)
        "debil": 9.0,
        "neutral": 6.0,
        "fortaleza": 4.0,
        "sobrecompra": 7.0,  # posible techo, candidato a reversion bajista
    }
    return mapping.get(rsi_interpretation, 5.0)


def _score_levels_bearish(supports, resistances) -> float:
    if not supports and not resistances:
        return 5.0
    score = 5.0
    if resistances:
        nearest_resistance = resistances[0]
        if abs(nearest_resistance["distance_pct"]) <= 3:
            score += 3
        if nearest_resistance["strength"] == "fuerte":
            score += 2
    if supports:
        nearest_support = supports[0]
        if nearest_support["distance_pct"] >= -2:
            score -= 2  # muy pegado al soporte, poco recorrido bajista inmediato
    return round(max(0, min(10, score)), 2)


def _score_volume_bearish(volume_abnormal: bool, price_down: bool) -> float:
    if volume_abnormal is None:
        return 5.0
    if volume_abnormal and price_down:
        return 10.0
    if volume_abnormal and not price_down:
        return 2.0
    return 5.0


def _score_fundamentals_bearish(fundamentals: dict) -> float:
    checks = []
    rev_g = fundamentals.get("revenue_growth")
    if rev_g is not None:
        checks.append(rev_g < 0)
    net_margin = fundamentals.get("net_margin")
    if net_margin is not None:
        checks.append(net_margin < 0.05)
    roe = fundamentals.get("roe")
    if roe is not None:
        checks.append(roe < 0.05)
    de = fundamentals.get("debt_to_equity")
    if de is not None:
        checks.append(de > 200)
    fcf = fundamentals.get("free_cash_flow")
    if fcf is not None:
        checks.append(fcf < 0)

    if not checks:
        return 7.5
    ratio = sum(1 for c in checks if c) / len(checks)
    return round(ratio * 15, 2)


def _score_overvaluation(upside_pct) -> float:
    """Cuanto mas negativo el 'upside' (o sea, mas sobrevaluada segun el
    precio objetivo), mas puntos para el lado short."""
    if upside_pct is None:
        return 2.5
    if upside_pct <= -20:
        return 5.0
    if upside_pct <= -5:
        return 4.0
    if upside_pct <= 5:
        return 2.5
    if upside_pct <= 20:
        return 1.0
    return 0.0


def compute_short_score(ema_flags, macd_info, rsi_value, rsi_interpretation,
                         supports, resistances, volume_abnormal, price_down,
                         fundamentals, upside_pct) -> dict:
    trend = _score_trend_bearish(ema_flags)
    momentum = _score_momentum_bearish(macd_info)
    rsi_s = _score_rsi_bearish(rsi_value, rsi_interpretation)
    levels_s = _score_levels_bearish(supports, resistances)
    volume_s = _score_volume_bearish(volume_abnormal, price_down)
    fund_s = _score_fundamentals_bearish(fundamentals)
    val_s = _score_overvaluation(upside_pct)

    total = round(trend + momentum + rsi_s + levels_s + volume_s + fund_s + val_s, 2)

    if total <= 30:
        label, color = "SIN SESGO BAJISTA", "gray"
    elif total <= 45:
        label, color = "DEBIL", "gray"
    elif total <= 55:
        label, color = "NEUTRAL", "yellow"
    elif total <= 70:
        label, color = "INTERESANTE PARA SHORT", "red"
    elif total <= 85:
        label, color = "SHORT", "red"
    else:
        label, color = "SHORT FUERTE", "red"

    return {
        "total": total,
        "label": label,
        "color": color,
        "breakdown": {
            "tendencia_bajista": trend,
            "momentum_bajista": momentum,
            "rsi": rsi_s,
            "resistencia_soporte": levels_s,
            "volumen": volume_s,
            "fundamentales_debiles": fund_s,
            "sobrevaluacion": val_s,
        },
    }


def determine_direction(long_score_total: float, short_score_total: float) -> dict:
    """Decide LONG, SHORT o SIN DIRECCION CLARA comparando ambos scores.
    Requiere que el lado ganador supere 56 puntos (zona 'interesante' o
    mejor) Y que le saque una diferencia razonable al otro lado; si ambos
    scores son bajos o muy parecidos, no hay una direccion clara."""
    if long_score_total >= 56 and long_score_total >= short_score_total + 8:
        return {"direction": "LONG", "color": "green"}
    if short_score_total >= 56 and short_score_total >= long_score_total + 8:
        return {"direction": "SHORT", "color": "red"}
    return {"direction": "SIN DIRECCION CLARA", "color": "yellow"}
