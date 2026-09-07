def signal_from_score(score_total: float) -> dict:
    if score_total >= 56:
        return {"signal": "COMPRA", "color": "green"}
    if score_total >= 46:
        return {"signal": "ESPERAR", "color": "yellow"}
    return {"signal": "VENTA", "color": "red"}


def trend_label(price, ema_short, ema_mid, ema_long) -> str:
    if price is None or ema_short is None:
        return "N/D"
    if ema_mid is not None and ema_long is not None:
        if price > ema_short > ema_mid > ema_long:
            return "alcista"
        if price < ema_short < ema_mid < ema_long:
            return "bajista"
    if price > ema_short:
        return "alcista_debil"
    if price < ema_short:
        return "bajista_debil"
    return "neutral"


def multi_horizon_trend(mas: dict, price: float) -> dict:
    def last(s):
        s2 = s.dropna()
        return float(s2.iloc[-1]) if not s2.empty else None

    ema9, ema20, ema50, ema200 = last(mas["ema9"]), last(mas["ema20"]), last(mas["ema50"]), last(mas["ema200"])

    short = trend_label(price, ema9, ema20, None)
    medium = trend_label(price, ema20, ema50, None)
    long_ = trend_label(price, ema50, ema200, None)

    def simplify(t):
        if t in ("alcista", "alcista_debil"):
            return {"label": "Alcista", "color": "green"}
        if t in ("bajista", "bajista_debil"):
            return {"label": "Bajista", "color": "red"}
        if t == "neutral":
            return {"label": "Neutral", "color": "yellow"}
        return {"label": "N/D", "color": "gray"}

    return {
        "short_term": simplify(short),
        "medium_term": simplify(medium),
        "long_term": simplify(long_),
    }


def build_alerts(ema_cross_9_20, ema_cross_20_50, ema_cross_50_200, rsi_interp,
                  broke_resistance, lost_support, volume_abnormal) -> list:
    alerts = []
    if ema_cross_9_20 == "golden_recent":
        alerts.append("Precio: cruce alcista reciente EMA9/EMA20")
    if ema_cross_9_20 == "death_recent":
        alerts.append("Precio: cruce bajista reciente EMA9/EMA20")
    if ema_cross_20_50 == "golden_recent":
        alerts.append("EMA20 cruzo por encima de EMA50")
    if ema_cross_20_50 == "death_recent":
        alerts.append("EMA20 cruzo por debajo de EMA50")
    if ema_cross_50_200 == "golden_recent":
        alerts.append("Golden Cross (EMA50/EMA200)")
    if ema_cross_50_200 == "death_recent":
        alerts.append("Death Cross (EMA50/EMA200)")
    if rsi_interp == "sobreventa":
        alerts.append("RSI en zona de sobreventa")
    if rsi_interp == "sobrecompra":
        alerts.append("RSI en zona de sobrecompra")
    if broke_resistance:
        alerts.append("Ruptura de resistencia reciente")
    if lost_support:
        alerts.append("Perdida de soporte reciente")
    if volume_abnormal:
        alerts.append("Volumen anormal detectado")
    return alerts


def build_conclusion(score: dict, signal: dict, trends: dict, fundamentals_ok: bool,
                      upside_pct, current_price, atr_value, nearest_support, nearest_resistance):
    risk = "Alto"
    if score["total"] >= 60:
        risk = "Bajo" if score["total"] >= 75 else "Medio"

    entry_low = current_price
    entry_high = current_price * 1.01 if current_price else None
    if nearest_support and atr_value:
        entry_low = min(current_price, nearest_support["price"] + 0.25 * atr_value)

    stop = None
    if nearest_support and atr_value:
        stop = round(nearest_support["price"] - 0.5 * atr_value, 2)
    elif atr_value and current_price:
        stop = round(current_price - 2 * atr_value, 2)

    targets = []
    if atr_value and current_price:
        targets = [round(current_price + m * atr_value, 2) for m in (1.5, 3.0, 4.5)]
    if nearest_resistance:
        targets = targets[:1] + [nearest_resistance["price"]] + targets[1:2] if targets else [nearest_resistance["price"]]

    rr = None
    if stop and targets and current_price:
        risk_amount = current_price - stop
        reward_amount = targets[0] - current_price
        if risk_amount and risk_amount > 0:
            rr = round(reward_amount / risk_amount, 2)

    invalidation = "La estrategia se invalida si el precio cierra por debajo del stop loss técnico, " \
                   "o si se pierde el soporte relevante con volumen elevado, o si el score cae a zona de venta."

    return {
        "signal": signal["signal"],
        "color": signal["color"],
        "trend_summary": trends,
        "fundamentals": "Buenos" if fundamentals_ok else "Debiles/Mixtos",
        "valuation": "Atractiva" if (upside_pct or 0) > 10 else ("Moderada" if (upside_pct or 0) > -10 else "Cara"),
        "risk": risk,
        "entry_range": [round(entry_low, 2) if entry_low else None, round(entry_high, 2) if entry_high else None],
        "stop_loss": stop,
        "targets": targets,
        "risk_reward": rr,
        "invalidation": invalidation,
    }
