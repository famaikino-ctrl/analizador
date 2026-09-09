"""
Screener de "configuraciones de ruptura" (breakout).

IMPORTANTE - que quede clarisimo: esto NO predice el futuro ni garantiza
que una accion vaya a subir. Es un detector de PATRONES TECNICOS que
historicamente suelen preceder movimientos fuertes (momentum + volumen +
cercania a resistencia + tendencia). Puede fallar, y de hecho falla
seguido: los mercados no son deterministicos. Se muestra como apoyo para
la propia investigacion del usuario, nunca como una senal garantizada.
"""


def compute_breakout_score(rsi_value, macd_info, adx_value, volume_abnormal,
                            distance_to_resistance_pct, momentum_5d_pct) -> dict:
    score = 0
    flags = []

    if rsi_value is not None and 50 <= rsi_value <= 70:
        score += 20
        flags.append("RSI en zona de momentum saludable (50-70)")

    if macd_info and macd_info.get("cross") in ("cruce_alcista", "alcista") and macd_info.get("histogram") == "positivo":
        score += 25
        flags.append("MACD alcista con histograma positivo")

    if adx_value is not None and adx_value >= 25:
        score += 20
        flags.append("Tendencia con fuerza (ADX >= 25)")

    if volume_abnormal:
        score += 20
        flags.append("Volumen muy por encima del promedio")

    if distance_to_resistance_pct is not None and 0 <= distance_to_resistance_pct <= 3:
        score += 15
        flags.append("Precio pegado a una resistencia clave")

    if momentum_5d_pct is not None and momentum_5d_pct > 3:
        score += 10
        flags.append(f"Impulso reciente: +{momentum_5d_pct:.1f}% en 5 sesiones")

    score = min(100, score)

    if score >= 70:
        label, color = "Configuracion de ruptura fuerte", "green"
    elif score >= 45:
        label, color = "Configuracion interesante, falta confirmacion", "yellow"
    else:
        label, color = "Sin señales de ruptura claras", "gray"

    return {"score": score, "label": label, "color": color, "flags": flags}


def compute_momentum_5d(close_series) -> float:
    """Retorno porcentual de los ultimos ~5 dias habiles."""
    s = close_series.dropna()
    if len(s) < 6:
        return None
    return float((s.iloc[-1] / s.iloc[-6] - 1) * 100)
