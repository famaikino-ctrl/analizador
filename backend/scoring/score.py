"""
Sistema de puntuación 0-100. Es un modelo cuantitativo simple y educativo,
NO una recomendación financiera. Pesos totales = 100:

  Tendencia EMA        25
  Momentum (MACD)      15
  RSI                  10
  MACD (cruce/hist)    10   [se reparte con Momentum: ver detalle abajo]
  Soportes/Resistencias 10
  Volumen              10
  Fundamentales        15
  Valuación             5
"""


def _score_trend(ema_flags: dict) -> float:
    checks = [
        ema_flags.get("ema9_gt_ema20"),
        ema_flags.get("ema20_gt_ema50"),
        ema_flags.get("ema50_gt_ema200"),
        ema_flags.get("price_gt_ema200"),
        ema_flags.get("price_gt_ema50"),
    ]
    valid = [c for c in checks if c is not None]
    if not valid:
        return 12.5  # neutral si no hay datos
    ratio = sum(1 for c in valid if c) / len(valid)
    return round(ratio * 25, 2)


def _score_momentum_macd(macd_info: dict) -> float:
    if not macd_info or macd_info.get("cross") == "N/D":
        return 7.5
    score = 7.5
    if macd_info["cross"] in ("cruce_alcista", "alcista"):
        score += 5
    elif macd_info["cross"] in ("cruce_bajista", "bajista"):
        score -= 5
    if macd_info.get("histogram") == "positivo":
        score += 2.5
    else:
        score -= 2.5
    return round(max(0, min(15, score)), 2)


def _score_rsi(rsi_value, rsi_interpretation: str) -> float:
    if rsi_value is None:
        return 5.0
    mapping = {
        "sobreventa": 7.0,   # posible rebote, no es automáticamente malo
        "debil": 4.0,
        "neutral": 6.0,
        "fortaleza": 9.0,
        "sobrecompra": 4.0,  # riesgo de corrección
    }
    return mapping.get(rsi_interpretation, 5.0)


def _score_levels(current_price, supports, resistances) -> float:
    if not supports and not resistances:
        return 5.0
    score = 5.0
    if supports:
        nearest_support = supports[0]
        if abs(nearest_support["distance_pct"]) <= 3:
            score += 3
        if nearest_support["strength"] == "fuerte":
            score += 2
    if resistances:
        nearest_resistance = resistances[0]
        if nearest_resistance["distance_pct"] <= 2:
            score -= 2  # muy pegado a resistencia, menos recorrido inmediato
    return round(max(0, min(10, score)), 2)


def _score_volume(volume_abnormal: bool, price_up: bool) -> float:
    if volume_abnormal is None:
        return 5.0
    if volume_abnormal and price_up:
        return 10.0
    if volume_abnormal and not price_up:
        return 2.0
    return 5.0


def _score_fundamentals(fundamentals: dict) -> float:
    checks = []
    rev_g = fundamentals.get("revenue_growth")
    if rev_g is not None:
        checks.append(rev_g > 0.05)
    net_margin = fundamentals.get("net_margin")
    if net_margin is not None:
        checks.append(net_margin > 0.08)
    roe = fundamentals.get("roe")
    if roe is not None:
        checks.append(roe > 0.10)
    de = fundamentals.get("debt_to_equity")
    if de is not None:
        checks.append(de < 150)
    fcf = fundamentals.get("free_cash_flow")
    if fcf is not None:
        checks.append(fcf > 0)

    if not checks:
        return 7.5
    ratio = sum(1 for c in checks if c) / len(checks)
    return round(ratio * 15, 2)


def _score_valuation(upside_pct) -> float:
    if upside_pct is None:
        return 2.5
    if upside_pct >= 20:
        return 5.0
    if upside_pct >= 5:
        return 4.0
    if upside_pct >= -5:
        return 2.5
    if upside_pct >= -20:
        return 1.0
    return 0.0


def compute_score(ema_flags, macd_info, rsi_value, rsi_interpretation,
                   supports, resistances, volume_abnormal, price_up,
                   fundamentals, upside_pct) -> dict:
    trend = _score_trend(ema_flags)
    momentum = _score_momentum_macd(macd_info)
    rsi_s = _score_rsi(rsi_value, rsi_interpretation)
    levels_s = _score_levels(None, supports, resistances)
    volume_s = _score_volume(volume_abnormal, price_up)
    fund_s = _score_fundamentals(fundamentals)
    val_s = _score_valuation(upside_pct)

    total = trend + momentum + rsi_s + levels_s + volume_s + fund_s + val_s
    total = round(total, 2)

    if total <= 30:
        label, emoji = "VENTA / MUY DEBIL", "red"
    elif total <= 45:
        label, emoji = "DEBIL", "red"
    elif total <= 55:
        label, emoji = "NEUTRAL", "yellow"
    elif total <= 70:
        label, emoji = "INTERESANTE", "green"
    elif total <= 85:
        label, emoji = "COMPRA", "green"
    else:
        label, emoji = "COMPRA FUERTE", "green"

    return {
        "total": total,
        "label": label,
        "color": emoji,
        "breakdown": {
            "tendencia_ema": trend,
            "momentum_macd": momentum,
            "rsi": rsi_s,
            "soportes_resistencias": levels_s,
            "volumen": volume_s,
            "fundamentales": fund_s,
            "valuacion": val_s,
        },
    }
