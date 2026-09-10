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

# Yahoo Finance bloquea muy seguido las peticiones que vienen de IPs de
# proveedores cloud (Railway, Render, AWS, etc.) porque las detecta como
# trafico de "centro de datos" en vez de un navegador real. Usamos curl_cffi
# para que las peticiones imiten la huella digital (TLS fingerprint) de un
# navegador Chrome real, lo cual evita ese bloqueo en la gran mayoria de los
# casos. Si igualmente falla, es una limitacion de la fuente de datos
# gratuita, no de la aplicacion (ver README, seccion de limitaciones).
try:
    from curl_cffi import requests as cffi_requests
    _SESSION = cffi_requests.Session(impersonate="chrome")
except Exception:
    _SESSION = None


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
        if _SESSION is not None:
            return yf.Ticker(ticker.upper().strip(), session=_SESSION)
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


def _av_num(value):
    """Alpha Vantage devuelve 'None', '-', o cadena vacia para campos no
    disponibles en vez de omitirlos. Los convertimos a None real."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() in ("", "None", "-", "NaN"):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class AlphaVantageProvider(DataProvider):
    """Proveedor alternativo basado en Alpha Vantage (www.alphavantage.co).

    Se usa en vez de Yahoo Finance cuando la app corre en un servidor cloud
    (Railway, Render, etc.), porque Yahoo Finance bloquea muy seguido las
    peticiones que vienen de esas IPs. Alpha Vantage requiere una API key
    gratuita (variable de entorno ALPHAVANTAGE_API_KEY).

    Limitaciones del plan gratuito de Alpha Vantage (documentadas para que
    no sean sorpresa):
      - 25 peticiones por dia, 5 por minuto.
      - El historial diario gratuito trae solo los ultimos ~100 dias
        habiles (~5 meses), por lo que EMA100, EMA200 y SMA200 van a
        aparecer como "N/D" por falta de datos suficientes.
      - Algunos fundamentales que si trae Yahoo (free cash flow, deuda,
        cash, payout ratio) no estan en el endpoint gratuito OVERVIEW de
        Alpha Vantage y quedan como "N/D".
      - El precio no es en tiempo real: se actualiza al cierre de cada
        sesion para las cuentas gratuitas.

    Para reducir el consumo de la cuota diaria, esta clase cachea en
    memoria (60 segundos) las respuestas de cada endpoint, ya que una sola
    consulta de analisis llama a 4 metodos distintos de esta clase que
    pueden compartir los mismos 2 llamados a la API (TIME_SERIES_DAILY y
    OVERVIEW) en vez de hacer 4 llamados separados.
    """

    BASE_URL = "https://www.alphavantage.co/query"
    _CACHE_TTL_SECONDS = 60
    _MIN_SECONDS_BETWEEN_CALLS = 13.0  # el plan gratis permite 5 llamados/min (60/5=12s); dejamos margen
    _last_call_time = 0.0  # compartido entre instancias, para respetar el limite global de la cuenta

    def __init__(self, api_key: Optional[str] = None):
        import os
        self.api_key = api_key or os.environ.get("ALPHAVANTAGE_API_KEY", "")
        self._cache: dict = {}

    def _request(self, params: dict) -> dict:
        import time
        import requests

        cache_key = tuple(sorted(params.items()))
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]) < self._CACHE_TTL_SECONDS:
            return cached[1]

        # Throttle: nos aseguramos de no llamar a la API mas rapido que el
        # limite de 5 solicitudes por minuto del plan gratuito, sin importar
        # desde que endpoint (analisis individual, comparador, scanner o
        # portafolio) se este llamando.
        elapsed = time.time() - AlphaVantageProvider._last_call_time
        wait = self._MIN_SECONDS_BETWEEN_CALLS - elapsed
        if wait > 0:
            time.sleep(wait)
        AlphaVantageProvider._last_call_time = time.time()

        full_params = dict(params)
        full_params["apikey"] = self.api_key
        try:
            resp = requests.get(self.BASE_URL, params=full_params, timeout=15)
            data = resp.json()
        except Exception:
            data = {}

        self._cache[cache_key] = (time.time(), data)
        return data

    def _daily_series(self, ticker: str) -> dict:
        data = self._request({"function": "TIME_SERIES_DAILY", "symbol": ticker.upper()})
        return data.get("Time Series (Daily)", {}) or {}

    def _overview(self, ticker: str) -> dict:
        data = self._request({"function": "OVERVIEW", "symbol": ticker.upper()})
        # Si la clave es invalida, se supero la cuota, o el ticker no existe,
        # Alpha Vantage devuelve un dict sin los campos esperados (a veces
        # con "Note", "Information" o "Error Message" en su lugar).
        if not data or "Symbol" not in data:
            return {}
        return data

    def get_price_history(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        series = self._daily_series(ticker)
        if not series:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        rows = []
        for date_str, values in series.items():
            try:
                rows.append({
                    "Date": pd.to_datetime(date_str),
                    "Open": float(values["1. open"]),
                    "High": float(values["2. high"]),
                    "Low": float(values["3. low"]),
                    "Close": float(values["4. close"]),
                    "Volume": float(values["5. volume"]),
                })
            except (KeyError, ValueError):
                continue
        if not rows:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        df = pd.DataFrame(rows).set_index("Date").sort_index()
        return df

    def get_quote(self, ticker: str) -> dict:
        df = self.get_price_history(ticker)
        overview = self._overview(ticker)

        price = prev_close = day_high = day_low = volume = avg_volume = None
        change_pct = None
        if not df.empty:
            price = float(df["Close"].iloc[-1])
            day_high = float(df["High"].iloc[-1])
            day_low = float(df["Low"].iloc[-1])
            volume = float(df["Volume"].iloc[-1])
            avg_volume = float(df["Volume"].tail(20).mean())
            if len(df) >= 2:
                prev_close = float(df["Close"].iloc[-2])
                if prev_close:
                    change_pct = (price - prev_close) / prev_close * 100.0

        week52_high = _av_num(overview.get("52WeekHigh"))
        week52_low = _av_num(overview.get("52WeekLow"))
        if week52_high is None and not df.empty:
            week52_high = float(df["High"].max())
        if week52_low is None and not df.empty:
            week52_low = float(df["Low"].min())

        return {
            "price": price,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "day_high": day_high,
            "day_low": day_low,
            "volume": volume,
            "avg_volume": avg_volume,
            "week52_high": week52_high,
            "week52_low": week52_low,
            "market_cap": _av_num(overview.get("MarketCapitalization")),
            "currency": overview.get("Currency") or "USD",
            "exchange": overview.get("Exchange"),
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    def get_company_info(self, ticker: str) -> dict:
        overview = self._overview(ticker)
        return {
            "name": overview.get("Name") or ticker.upper(),
            "sector": overview.get("Sector"),
            "industry": overview.get("Industry"),
            "exchange": overview.get("Exchange"),
            "currency": overview.get("Currency") or "USD",
            "website": None,
            "employees": None,
            "description": overview.get("Description"),
        }

    def get_fundamentals(self, ticker: str) -> dict:
        o = self._overview(ticker)

        def pct(key):
            v = _av_num(o.get(key))
            return v if v is None else v  # ya vienen como fraccion (0.12 = 12%)

        return {
            "revenue": _av_num(o.get("RevenueTTM")),
            "revenue_growth": _av_num(o.get("QuarterlyRevenueGrowthYOY")),
            "eps_ttm": _av_num(o.get("EPS")),
            "eps_forward": None,
            "ebitda": _av_num(o.get("EBITDA")),
            "gross_margin": None,
            "operating_margin": _av_num(o.get("OperatingMarginTTM")),
            "net_margin": _av_num(o.get("ProfitMargin")),
            "free_cash_flow": None,
            "total_debt": None,
            "total_cash": None,
            "debt_to_equity": None,
            "roe": _av_num(o.get("ReturnOnEquityTTM")),
            "roa": _av_num(o.get("ReturnOnAssetsTTM")),
            "pe_trailing": _av_num(o.get("TrailingPE")) or _av_num(o.get("PERatio")),
            "pe_forward": _av_num(o.get("ForwardPE")),
            "peg_ratio": _av_num(o.get("PEGRatio")),
            "ps_ratio": _av_num(o.get("PriceToSalesRatioTTM")),
            "pb_ratio": _av_num(o.get("PriceToBookRatio")),
            "ev_to_ebitda": _av_num(o.get("EVToEBITDA")),
            "dividend_yield": _av_num(o.get("DividendYield")),
            "payout_ratio": None,
            "beta": _av_num(o.get("Beta")),
            "shares_outstanding": _av_num(o.get("SharesOutstanding")),
            "book_value": _av_num(o.get("BookValue")),
            "earnings_growth": _av_num(o.get("QuarterlyEarningsGrowthYOY")),
            "roic": None,
        }

    def get_analyst_target(self, ticker: str) -> Optional[dict]:
        o = self._overview(ticker)
        mean = _av_num(o.get("AnalystTargetPrice"))
        if mean is None:
            return None
        return {"low": None, "mean": mean, "high": None, "num_analysts": None}
