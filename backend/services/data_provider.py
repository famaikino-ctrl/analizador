"""
Capa de datos. TODA la aplicación accede a datos de mercado ÚNICAMENTE
a través de la interfaz DataProvider. Para cambiar de fuente de datos
(Alpha Vantage, Finnhub, Polygon, IEX, un broker, etc.) sólo hay que:

  1. Crear una nueva clase que herede de DataProvider e implemente sus métodos.
  2. Cambiar la línea `provider = YFinanceProvider()` en main.py por la nueva clase.

Ningún otro módulo (indicadores, niveles, valuación, scoring, endpoints)
debe importar yfinance directamente. Así se evita tener que tocar 20
archivos cuando cambie el proveedor de datos.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
import yfinance as yf


class DataProvider(ABC):
    @abstractmethod
    def get_price_history(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Debe devolver un DataFrame con columnas: Open, High, Low, Close, Volume
        e índice de tipo datetime (ascendente)."""
        ...

    @abstractmethod
    def get_quote(self, ticker: str) -> dict:
        """Debe devolver: price, change_pct, day_high, day_low, prev_close,
        volume, avg_volume, week52_high, week52_low, market_cap, currency,
        exchange, as_of (ISO datetime)."""
        ...

    @abstractmethod
    def get_company_info(self, ticker: str) -> dict:
        """name, sector, industry, exchange, currency, website, employees."""
        ...

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> dict:
        """Métricas fundamentales crudas (ver `fields` abajo). Cualquier campo
        no disponible debe omitirse (nunca inventarse); el resto de la app
        interpretará su ausencia como 'N/D'."""
        ...

    @abstractmethod
    def get_analyst_target(self, ticker: str) -> Optional[dict]:
        """Precio objetivo de consenso de analistas si la fuente lo provee."""
        ...


def _safe(info: dict, key: str):
    v = info.get(key)
    if v is None:
        return None
    # yfinance a veces devuelve NaN
    try:
        if isinstance(v, float) and pd.isna(v):
            return None
    except Exception:
        pass
    return v


class YFinanceProvider(DataProvider):
    """Implementación gratuita basada en yfinance (Yahoo Finance).

    Limitaciones conocidas (documentadas para quien quiera reemplazarla):
      - No es una API oficial; Yahoo puede cambiar/romper el scraping.
      - Datos con posible retraso de 15 minutos en el precio "real time".
      - Rate limiting no documentado oficialmente: uso intensivo puede
        devolver respuestas vacías temporalmente.
      - Fundamentales históricos limitados (no siempre hay serie larga).
    """

    def _ticker(self, ticker: str) -> yf.Ticker:
        return yf.Ticker(ticker.upper().strip())

    def get_price_history(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        t = self._ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
        return df

    def get_quote(self, ticker: str) -> dict:
        t = self._ticker(ticker)
        info = {}
        try:
            info = t.get_info()
        except Exception:
            info = {}

        hist = t.history(period="1y", interval="1d", auto_adjust=False)
        price = _safe(info, "currentPrice") or _safe(info, "regularMarketPrice")
        prev_close = _safe(info, "previousClose") or _safe(info, "regularMarketPreviousClose")

        if price is None and not hist.empty:
            price = float(hist["Close"].iloc[-1])
        if prev_close is None and len(hist) >= 2:
            prev_close = float(hist["Close"].iloc[-2])

        change_pct = None
        if price is not None and prev_close not in (None, 0):
            change_pct = (price - prev_close) / prev_close * 100.0

        week52_high = _safe(info, "fiftyTwoWeekHigh")
        week52_low = _safe(info, "fiftyTwoWeekLow")
        if (week52_high is None or week52_low is None) and not hist.empty:
            week52_high = week52_high or float(hist["High"].max())
            week52_low = week52_low or float(hist["Low"].min())

        return {
            "price": price,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "day_high": _safe(info, "dayHigh"),
            "day_low": _safe(info, "dayLow"),
            "volume": _safe(info, "volume") or _safe(info, "regularMarketVolume"),
            "avg_volume": _safe(info, "averageVolume"),
            "week52_high": week52_high,
            "week52_low": week52_low,
            "market_cap": _safe(info, "marketCap"),
            "currency": _safe(info, "currency") or "USD",
            "exchange": _safe(info, "exchange") or _safe(info, "fullExchangeName"),
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    def get_company_info(self, ticker: str) -> dict:
        t = self._ticker(ticker)
        try:
            info = t.get_info()
        except Exception:
            info = {}
        return {
            "name": _safe(info, "longName") or _safe(info, "shortName") or ticker.upper(),
            "sector": _safe(info, "sector"),
            "industry": _safe(info, "industry"),
            "exchange": _safe(info, "exchange") or _safe(info, "fullExchangeName"),
            "currency": _safe(info, "currency") or "USD",
            "website": _safe(info, "website"),
            "employees": _safe(info, "fullTimeEmployees"),
            "description": _safe(info, "longBusinessSummary"),
        }

    def get_fundamentals(self, ticker: str) -> dict:
        t = self._ticker(ticker)
        try:
            info = t.get_info()
        except Exception:
            info = {}

        fields = {
            "revenue": "totalRevenue",
            "revenue_growth": "revenueGrowth",
            "eps_ttm": "trailingEps",
            "eps_forward": "forwardEps",
            "ebitda": "ebitda",
            "gross_margin": "grossMargins",
            "operating_margin": "operatingMargins",
            "net_margin": "profitMargins",
            "free_cash_flow": "freeCashflow",
            "total_debt": "totalDebt",
            "total_cash": "totalCash",
            "debt_to_equity": "debtToEquity",
            "roe": "returnOnEquity",
            "roa": "returnOnAssets",
            "pe_trailing": "trailingPE",
            "pe_forward": "forwardPE",
            "peg_ratio": "pegRatio",
            "ps_ratio": "priceToSalesTrailing12Months",
            "pb_ratio": "priceToBook",
            "ev_to_ebitda": "enterpriseToEbitda",
            "dividend_yield": "dividendYield",
            "payout_ratio": "payoutRatio",
            "beta": "beta",
            "shares_outstanding": "sharesOutstanding",
            "book_value": "bookValue",
            "earnings_growth": "earningsGrowth",
        }
        out = {}
        for our_key, yf_key in fields.items():
            out[our_key] = _safe(info, yf_key)

        # ROIC no lo expone yfinance directamente -> se marca como no disponible.
        out["roic"] = None
        return out

    def get_analyst_target(self, ticker: str) -> Optional[dict]:
        t = self._ticker(ticker)
        try:
            info = t.get_info()
        except Exception:
            info = {}
        low = _safe(info, "targetLowPrice")
        high = _safe(info, "targetHighPrice")
        mean = _safe(info, "targetMeanPrice")
        n = _safe(info, "numberOfAnalystOpinions")
        if mean is None and low is None and high is None:
            return None
        return {"low": low, "mean": mean, "high": high, "num_analysts": n}
