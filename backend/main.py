from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from typing import List
import math

from services.data_provider import YFinanceProvider, AlphaVantageProvider
from analysis import analyze_ticker

app = FastAPI(title="Stock Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# Para cambiar de proveedor de datos: reemplazar esta linea por otra clase
# que implemente la interfaz DataProvider (ver services/data_provider.py).
#
# Se usa AlphaVantageProvider en vez de YFinanceProvider porque Yahoo
# Finance bloquea las peticiones que vienen de IPs de servidores cloud
# (Railway, Render, etc.). Alpha Vantage si funciona desde ahi, pero
# requiere una API key gratuita configurada como variable de entorno
# ALPHAVANTAGE_API_KEY (ver README, seccion "Desplegar online").
# Si corres la app en tu propia PC y preferis Yahoo Finance (sin API key
# y con mas datos fundamentales disponibles), cambia la linea de abajo por:
#   provider = YFinanceProvider()
# --------------------------------------------------------------------------
provider = AlphaVantageProvider()


def _sanitize(obj):
    """Convierte NaN/Infinity (no válidos en JSON estándar) a None de forma
    recursiva antes de responder."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


@app.get("/api/analyze/{ticker}")
def api_analyze(ticker: str, timeframe: str = "1Y"):
    try:
        result = analyze_ticker(provider, ticker, timeframe)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error analizando {ticker}: {exc}")
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return JSONResponse(content=_sanitize(result))


@app.get("/api/compare")
def api_compare(tickers: str):
    """tickers: string separado por comas, ej: NVDA,AMD,AVGO,QCOM,TSM (max 5)."""
    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()][:5]
    if not symbols:
        raise HTTPException(status_code=400, detail="Debes indicar al menos un ticker.")

    rows = []
    for sym in symbols:
        try:
            data = analyze_ticker(provider, sym, "1Y")
        except Exception as exc:
            rows.append({"ticker": sym, "error": str(exc)})
            continue
        if "error" in data:
            rows.append({"ticker": sym, "error": data["error"]})
            continue

        quote = data["quote"]
        fundamentals = data["fundamentals"]
        rows.append({
            "ticker": sym,
            "price": quote.get("price"),
            "change_pct": quote.get("change_pct"),
            "rsi": data["oscillators"].get("rsi"),
            "pe_trailing": fundamentals.get("pe_trailing"),
            "revenue_growth": fundamentals.get("revenue_growth"),
            "roe": fundamentals.get("roe"),
            "net_margin": fundamentals.get("net_margin"),
            "score": data["score"]["total"],
            "score_label": data["score"]["label"],
            "price_target_base": data["price_target"].get("base"),
            "upside_pct": data["price_target"].get("upside_pct"),
        })
    return JSONResponse(content=_sanitize({"tickers": rows}))


@app.get("/api/scanner")
def api_scanner(tickers: str):
    """Screener de configuraciones de ruptura sobre una lista de tickers
    (maximo 6, para no agotar la cuota diaria gratuita de la API de datos).
    tickers: string separado por comas, ej: NVDA,AMD,AAPL,MSFT"""
    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()][:6]
    if not symbols:
        raise HTTPException(status_code=400, detail="Debes indicar al menos un ticker.")

    results = []
    for sym in symbols:
        try:
            data = analyze_ticker(provider, sym, "6M")
        except Exception as exc:
            results.append({"ticker": sym, "error": str(exc)})
            continue
        if "error" in data:
            results.append({"ticker": sym, "error": data["error"]})
            continue

        results.append({
            "ticker": sym,
            "price": data["quote"].get("price"),
            "change_pct": data["quote"].get("change_pct"),
            "score": data["score"]["total"],
            "signal": data["signal"]["signal"],
            "trade_style": data["trade_style"]["style"],
            "breakout_score": data["breakout"]["score"],
            "breakout_label": data["breakout"]["label"],
            "breakout_color": data["breakout"]["color"],
            "breakout_flags": data["breakout"]["flags"],
        })

    ok_results = [r for r in results if "error" not in r]
    err_results = [r for r in results if "error" in r]
    ok_results.sort(key=lambda r: r["breakout_score"], reverse=True)

    return JSONResponse(content=_sanitize({"results": ok_results + err_results}))


@app.post("/api/portfolio")
def api_portfolio(positions: List[dict] = Body(...)):
    """positions: [{ "ticker": "AAPL", "quantity": 10, "avg_price": 150.0 }, ...]"""
    if not positions:
        raise HTTPException(status_code=400, detail="La cartera esta vacia.")

    enriched = []
    total_value = 0.0
    for pos in positions:
        ticker = str(pos.get("ticker", "")).strip().upper()
        quantity = float(pos.get("quantity", 0) or 0)
        avg_price = float(pos.get("avg_price", 0) or 0)
        if not ticker or quantity <= 0:
            continue
        try:
            data = analyze_ticker(provider, ticker, "1Y")
        except Exception as exc:
            enriched.append({"ticker": ticker, "error": str(exc)})
            continue
        if "error" in data:
            enriched.append({"ticker": ticker, "error": data["error"]})
            continue

        current_price = data["quote"].get("price") or 0
        current_value = current_price * quantity
        cost_basis = avg_price * quantity
        gain_loss = current_value - cost_basis
        gain_loss_pct = (gain_loss / cost_basis * 100) if cost_basis else None
        total_value += current_value

        enriched.append({
            "ticker": ticker,
            "quantity": quantity,
            "avg_price": avg_price,
            "current_price": current_price,
            "current_value": round(current_value, 2),
            "cost_basis": round(cost_basis, 2),
            "gain_loss": round(gain_loss, 2),
            "gain_loss_pct": round(gain_loss_pct, 2) if gain_loss_pct is not None else None,
            "score": data["score"]["total"],
            "price_target_base": data["price_target"].get("base"),
            "upside_pct": data["price_target"].get("upside_pct"),
        })

    for item in enriched:
        if "current_value" in item and total_value > 0:
            item["weight_pct"] = round(item["current_value"] / total_value * 100, 2)

    return JSONResponse(content=_sanitize({"positions": enriched, "total_value": round(total_value, 2)}))


# --------------------------------------------------------------------------
# Frontend estatico
# --------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{filename}")
    def serve_static_file(filename: str):
        file_path = FRONTEND_DIR / filename
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        raise HTTPException(status_code=404, detail="No encontrado")
