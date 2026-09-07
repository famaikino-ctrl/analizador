"""
Detección de soportes y resistencias.

Metodología (documentada para que el criterio no sea una caja negra):

1. Se identifican "swing highs" y "swing lows": velas cuyo máximo/mínimo es
   el más alto/bajo dentro de una ventana de `swing_window` velas a cada lado.
2. Esos swing points se agrupan ("clustering") cuando están dentro de un
   `cluster_pct` de distancia entre sí: varios rechazos cercanos en precio
   se consideran el mismo nivel.
3. La "fuerza" del nivel = número de toques (velas que reaccionaron cerca
   de ese precio) + un bono si coincide con el máximo/mínimo de 52 semanas.
4. Se separan los niveles en soportes (por debajo del precio actual) y
   resistencias (por encima), ordenados por cercanía al precio.

Esto es una heurística estadística sobre precio y no una predicción.
"""

import pandas as pd
import numpy as np


def _swing_points(df: pd.DataFrame, window: int = 3):
    highs, lows = [], []
    h, l = df["High"].values, df["Low"].values
    n = len(df)
    for i in range(window, n - window):
        seg_h = h[i - window:i + window + 1]
        seg_l = l[i - window:i + window + 1]
        if h[i] == seg_h.max():
            highs.append((df.index[i], h[i]))
        if l[i] == seg_l.min():
            lows.append((df.index[i], l[i]))
    return highs, lows


def _cluster(points, cluster_pct: float):
    """points: lista de (fecha, precio). Devuelve lista de dicts con
    price (promedio del cluster), touches y fechas."""
    if not points:
        return []
    prices = sorted(points, key=lambda p: p[1])
    clusters = []
    current = [prices[0]]
    for p in prices[1:]:
        ref = current[-1][1]
        if ref == 0:
            continue
        if abs(p[1] - ref) / ref <= cluster_pct:
            current.append(p)
        else:
            clusters.append(current)
            current = [p]
    clusters.append(current)

    out = []
    for c in clusters:
        avg_price = float(np.mean([x[1] for x in c]))
        out.append({
            "price": avg_price,
            "touches": len(c),
            "dates": [x[0].strftime("%Y-%m-%d") if hasattr(x[0], "strftime") else str(x[0]) for x in c],
        })
    return out


def detect_levels(df: pd.DataFrame, current_price: float, week52_high=None, week52_low=None,
                   swing_window: int = 3, cluster_pct: float = 0.015, max_levels: int = 3):
    if df.empty or len(df) < (swing_window * 2 + 5):
        return {"supports": [], "resistances": []}

    highs, lows = _swing_points(df, swing_window)
    high_clusters = _cluster(highs, cluster_pct)
    low_clusters = _cluster(lows, cluster_pct)

    # Bonus de fuerza si coincide con máx/min de 52 semanas.
    def enrich(clusters, is_high):
        for c in clusters:
            bonus = 0
            ref = week52_high if is_high else week52_low
            if ref and ref != 0 and abs(c["price"] - ref) / ref <= 0.01:
                bonus = 2
            c["strength_score"] = c["touches"] + bonus
            c["near_52w_extreme"] = bonus > 0
        return clusters

    high_clusters = enrich(high_clusters, True)
    low_clusters = enrich(low_clusters, False)

    all_levels = high_clusters + low_clusters

    resistances = [lvl for lvl in all_levels if lvl["price"] > current_price]
    supports = [lvl for lvl in all_levels if lvl["price"] <= current_price]

    resistances.sort(key=lambda x: x["price"])  # más cercana primero
    supports.sort(key=lambda x: -x["price"])    # más cercana primero

    def finalize(levels, label_prefix):
        result = []
        for i, lvl in enumerate(levels[:max_levels]):
            dist_pct = (lvl["price"] - current_price) / current_price * 100
            strength = "fuerte" if lvl["strength_score"] >= 4 else ("moderado" if lvl["strength_score"] >= 2 else "debil")
            reason_parts = [f"{lvl['touches']} reacciones detectadas en velas swing"]
            if lvl.get("near_52w_extreme"):
                reason_parts.append("coincide con extremo de 52 semanas")
            result.append({
                "label": f"{label_prefix}{i + 1}",
                "price": round(lvl["price"], 4),
                "distance_pct": round(dist_pct, 2),
                "strength": strength,
                "touches": lvl["touches"],
                "reason": "; ".join(reason_parts) + ".",
            })
        return result

    return {
        "supports": finalize(supports, "S"),
        "resistances": finalize(resistances, "R"),
    }
