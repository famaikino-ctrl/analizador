def build_strategies(current_price, atr_value, ema20, ema50, nearest_support, nearest_resistance, rsi_value):
    strategies = {}

    # --- Conservadora: esperar recuperación/confirmación de EMA relevante ---
    if ema50 is not None and atr_value:
        entry_c = round(ema50 * 1.005, 2)
        stop_c = round(ema50 - 1.0 * atr_value, 2)
        target_c = round(entry_c + 2.0 * atr_value, 2)
        risk_pct_c = round((entry_c - stop_c) / entry_c * 100, 2) if entry_c else None
        reward_pct_c = round((target_c - entry_c) / entry_c * 100, 2) if entry_c else None
        rr_c = round((target_c - entry_c) / (entry_c - stop_c), 2) if (entry_c - stop_c) > 0 else None
        strategies["conservadora"] = {
            "descripcion": "Espera confirmacion de tendencia y recuperacion de EMA50 antes de entrar.",
            "entrada": entry_c, "stop": stop_c, "objetivo": target_c,
            "riesgo_pct": risk_pct_c, "potencial_pct": reward_pct_c, "risk_reward": rr_c,
        }
    else:
        strategies["conservadora"] = None

    # --- Moderada: entrada cerca de soporte con confirmación RSI/volumen ---
    if nearest_support and atr_value:
        entry_m = round(nearest_support["price"] * 1.01, 2)
        stop_m = round(nearest_support["price"] - 0.75 * atr_value, 2)
        target_m = round(entry_m + 2.5 * atr_value, 2)
        risk_pct_m = round((entry_m - stop_m) / entry_m * 100, 2) if entry_m else None
        reward_pct_m = round((target_m - entry_m) / entry_m * 100, 2) if entry_m else None
        rr_m = round((target_m - entry_m) / (entry_m - stop_m), 2) if (entry_m - stop_m) > 0 else None
        strategies["moderada"] = {
            "descripcion": "Entrada cerca del soporte mas cercano, confirmando con RSI y volumen.",
            "entrada": entry_m, "stop": stop_m, "objetivo": target_m,
            "riesgo_pct": risk_pct_m, "potencial_pct": reward_pct_m, "risk_reward": rr_m,
        }
    else:
        strategies["moderada"] = None

    # --- Agresiva: entrada anticipada por momentum ---
    if current_price and atr_value:
        entry_a = round(current_price, 2)
        stop_a = round(current_price - 1.2 * atr_value, 2)
        target_a = round(current_price + 2.0 * atr_value, 2)
        risk_pct_a = round((entry_a - stop_a) / entry_a * 100, 2)
        reward_pct_a = round((target_a - entry_a) / entry_a * 100, 2)
        rr_a = round((target_a - entry_a) / (entry_a - stop_a), 2) if (entry_a - stop_a) > 0 else None
        strategies["agresiva"] = {
            "descripcion": "Entrada inmediata basada en momentum y cruces de EMA de corto plazo.",
            "entrada": entry_a, "stop": stop_a, "objetivo": target_a,
            "riesgo_pct": risk_pct_a, "potencial_pct": reward_pct_a, "risk_reward": rr_a,
        }
    else:
        strategies["agresiva"] = None

    return strategies
