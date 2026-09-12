"""
Panel de contexto general del mercado. A diferencia del analisis completo
de un ticker (que usa 2 llamados a la API: precio + fundamentales), este
modulo usa solo 1 llamado por simbolo (unicamente precio historico),
porque para el contexto de mercado no hace falta informacion fundamental.

Simbolos usados como proxy:
  SPY -> ETF que sigue al S&P 500
  QQQ -> ETF que sigue al Nasdaq 100
  DIA -> ETF que sigue al Dow Jones
  VIXY -> ETF que sigue a futuros del VIX (proxy de volatilidad; no es
          identico al indice VIX "spot", pero es la forma mas confiable
          de aproximarlo con un ticker operable en un proveedor de datos
          orientado a acciones/ETFs como Alpha Vantage).
"""

MARKET_SYMBOLS = [
    {"symbol": "SPY", "label": "S&P 500 (SPY)"},
    {"symbol": "QQQ", "label": "Nasdaq 100 (QQQ)"},
    {"symbol": "DIA", "label": "Dow Jones (DIA)"},
    {"symbol": "VIXY", "label": "Volatilidad (VIXY, proxy del VIX)"},
]


def _quote_from_history(df):
    if df.empty or len(df) < 2:
        return None
    price = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    change_pct = (price - prev_close) / prev_close * 100.0 if prev_close else None
    day_high = float(df["High"].iloc[-1])
    day_low = float(df["Low"].iloc[-1])
    last_date = df.index[-1]
    return {
        "price": round(price, 2),
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "day_high": round(day_high, 2),
        "day_low": round(day_low, 2),
        "as_of_date": last_date.strftime("%Y-%m-%d"),
    }


def get_market_snapshot(provider) -> dict:
    results = []
    for item in MARKET_SYMBOLS:
        try:
            df = provider.get_price_history(item["symbol"], period="1mo", interval="1d")
            quote = _quote_from_history(df)
        except Exception:
            quote = None

        if quote is None:
            results.append({"symbol": item["symbol"], "label": item["label"], "error": "Sin datos disponibles"})
        else:
            results.append({"symbol": item["symbol"], "label": item["label"], **quote})

    # Contexto general: mira SPY y QQQ (indices amplios) para decidir si el
    # tono general del dia es alcista, bajista o mixto. VIXY se interpreta
    # aparte (sube = mas miedo/volatilidad en el mercado).
    broad = [r for r in results if r["symbol"] in ("SPY", "QQQ") and "change_pct" in r and r["change_pct"] is not None]
    if broad:
        avg_change = sum(r["change_pct"] for r in broad) / len(broad)
        if avg_change > 0.3:
            context = {"label": "Alcista", "color": "green"}
        elif avg_change < -0.3:
            context = {"label": "Bajista", "color": "red"}
        else:
            context = {"label": "Mixto / Lateral", "color": "yellow"}
    else:
        context = {"label": "N/D", "color": "gray"}

    return {"symbols": results, "context": context}
