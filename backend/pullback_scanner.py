"""
Screener de dos patrones tecnicos especificos:

1. COMPRA por rebote en EMA150/EMA200 (calculadas sobre velas SEMANALES,
   porque el historial diario gratuito no alcanza para esas medias): el
   precio esta cerca de una media larga mientras la tendencia de fondo
   sigue siendo alcista. Es un patron clasico de "pullback a media larga
   en tendencia alcista", no una garantia de rebote.

2. VENTA/toma de ganancias por estar cerca de una resistencia relevante o
   de un maximo de 52 semanas: no significa que la accion vaya a caer,
   solo que esta en una zona historica donde el precio suele encontrar
   mas dificultad para seguir subiendo.

Ambos patrones son heuristicas de analisis tecnico, no predicciones.
"""

from indicators.moving_averages import compute_all_mas, last_valid


def check_ema_pullback_buy(weekly_df, tolerance_pct: float = 4.0) -> dict:
    """Analiza velas SEMANALES para ver si el precio esta cerca de su
    EMA150 o EMA200 semanal, en una tendencia de fondo alcista."""
    if weekly_df.empty or len(weekly_df) < 60:
        return {"triggered": False, "reason": "Historial semanal insuficiente para evaluar EMA150/200 (se necesitan ~60 semanas minimo, idealmente 150-200)."}

    close = weekly_df["Close"]
    mas = compute_all_mas(close)
    price = float(close.iloc[-1])
    ema150 = last_valid(mas["ema150"])
    ema200 = last_valid(mas["ema200"])

    if ema150 is None and ema200 is None:
        return {"triggered": False, "reason": "No hay suficiente historial semanal todavia para EMA150/200."}

    candidates = []
    for label, ema_value in (("EMA150 semanal", ema150), ("EMA200 semanal", ema200)):
        if ema_value is None:
            continue
        distance_pct = (price - ema_value) / ema_value * 100
        if abs(distance_pct) <= tolerance_pct:
            # tendencia de fondo alcista: precio por encima de la media mas larga disponible, o EMA150>EMA200
            uptrend = True
            if ema150 is not None and ema200 is not None:
                uptrend = ema150 >= ema200 * 0.98  # tolerancia chica para no ser demasiado estricto
            candidates.append({
                "ma_label": label,
                "ma_value": round(ema_value, 2),
                "distance_pct": round(distance_pct, 2),
                "uptrend_context": uptrend,
            })

    if not candidates:
        return {"triggered": False, "reason": "El precio no esta cerca de su EMA150 ni EMA200 semanal en este momento."}

    best = min(candidates, key=lambda c: abs(c["distance_pct"]))
    return {
        "triggered": bool(best["uptrend_context"]),
        "ma_label": best["ma_label"],
        "ma_value": best["ma_value"],
        "distance_pct": best["distance_pct"],
        "reason": (
            f"El precio esta a {best['distance_pct']:+.1f}% de su {best['ma_label']}, "
            f"{'con contexto de tendencia de largo plazo alcista' if best['uptrend_context'] else 'pero sin confirmar tendencia de fondo alcista'}."
        ),
    }


def check_resistance_or_ath_sell(current_price, week52_high, nearest_resistance, tolerance_pct: float = 3.0) -> dict:
    """Marca si el precio esta cerca de una resistencia relevante o de su
    maximo de 52 semanas (posible zona de toma de ganancias o de mayor
    dificultad para seguir subiendo)."""
    flags = []

    if week52_high and current_price:
        distance_to_ath = (week52_high - current_price) / week52_high * 100
        if 0 <= distance_to_ath <= tolerance_pct:
            flags.append(f"A {distance_to_ath:.1f}% de su maximo de 52 semanas (${week52_high}).")
        elif current_price >= week52_high:
            flags.append(f"En maximo de 52 semanas o superandolo (${week52_high}).")

    if nearest_resistance and abs(nearest_resistance.get("distance_pct", 999)) <= tolerance_pct:
        flags.append(
            f"A {nearest_resistance['distance_pct']:+.1f}% de una resistencia "
            f"{nearest_resistance['strength']} (${nearest_resistance['price']})."
        )

    return {"triggered": bool(flags), "reasons": flags}
