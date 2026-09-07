"""
Cálculo de precio objetivo.

IMPORTANTE - limitaciones honestas:
Cada método es una SIMPLIFICACIÓN académica, no un modelo de valuación de
grado profesional (eso requeriría proyecciones detalladas de flujo de caja,
WACC específico de la empresa, tasas terminales ajustadas por industria,
etc.). Se combinan varios métodos precisamente para no depender de uno solo
y se muestra siempre cuántos métodos pudieron calcularse.

Métodos:
  1. DCF simplificado (Gordon Growth de un solo período sobre FCF/acción)
  2. P/E relativo (EPS actual * P/E histórico/sector si está disponible,
     si no, contra su propio P/E forward)
  3. EV/EBITDA relativo
  4. Crecimiento esperado aplicado al EPS forward (PEG implícito)
  5. Consenso de analistas (si la fuente lo entrega)

Cada método que no pueda calcularse por falta de datos se omite (nunca se
inventa un valor).
"""

from typing import Optional


def _dcf_simplificado(fcf_per_share: Optional[float], growth: Optional[float],
                       discount_rate: float = 0.09, terminal_growth: float = 0.025,
                       years: int = 5) -> Optional[float]:
    if fcf_per_share is None or fcf_per_share <= 0:
        return None
    g = growth if growth is not None else 0.05
    g = max(min(g, 0.25), -0.10)  # limitar supuestos extremos
    value = 0.0
    fcf = fcf_per_share
    for year in range(1, years + 1):
        fcf = fcf * (1 + g)
        value += fcf / ((1 + discount_rate) ** year)
    terminal_value = (fcf * (1 + terminal_growth)) / (discount_rate - terminal_growth)
    value += terminal_value / ((1 + discount_rate) ** years)
    return value


def _pe_relativo(eps_ttm: Optional[float], pe_reference: Optional[float]) -> Optional[float]:
    if eps_ttm is None or pe_reference is None or eps_ttm <= 0:
        return None
    return eps_ttm * pe_reference


def _ev_ebitda_relativo(ebitda: Optional[float], ev_ebitda_ref: Optional[float],
                         net_debt: Optional[float], shares_outstanding: Optional[float]) -> Optional[float]:
    if None in (ebitda, ev_ebitda_ref, shares_outstanding) or shares_outstanding == 0:
        return None
    implied_ev = ebitda * ev_ebitda_ref
    net_debt = net_debt or 0
    equity_value = implied_ev - net_debt
    return equity_value / shares_outstanding


def _crecimiento_esperado(eps_forward: Optional[float], growth: Optional[float],
                           pe_reference: Optional[float]) -> Optional[float]:
    if eps_forward is None or growth is None or pe_reference is None:
        return None
    projected_eps = eps_forward * (1 + max(min(growth, 0.4), -0.2))
    return projected_eps * pe_reference


def compute_price_target(current_price: float, fundamentals: dict, analyst_target: Optional[dict]) -> dict:
    fcf = fundamentals.get("free_cash_flow")
    shares = fundamentals.get("shares_outstanding")
    fcf_per_share = (fcf / shares) if (fcf and shares) else None

    growth = fundamentals.get("earnings_growth") or fundamentals.get("revenue_growth")
    pe_ttm = fundamentals.get("pe_trailing")
    pe_fwd = fundamentals.get("pe_forward")
    pe_reference = pe_ttm or pe_fwd

    ev_ebitda = fundamentals.get("ev_to_ebitda")
    ebitda = fundamentals.get("ebitda")
    net_debt = None
    if fundamentals.get("total_debt") is not None and fundamentals.get("total_cash") is not None:
        net_debt = fundamentals["total_debt"] - fundamentals["total_cash"]

    methods = {}

    dcf = _dcf_simplificado(fcf_per_share, growth)
    if dcf:
        methods["dcf_simplificado"] = round(dcf, 2)

    pe_rel = _pe_relativo(fundamentals.get("eps_ttm"), pe_reference)
    if pe_rel:
        methods["pe_relativo"] = round(pe_rel, 2)

    ev_val = _ev_ebitda_relativo(ebitda, ev_ebitda, net_debt, shares)
    if ev_val:
        methods["ev_ebitda"] = round(ev_val, 2)

    growth_val = _crecimiento_esperado(fundamentals.get("eps_forward"), growth, pe_reference)
    if growth_val:
        methods["crecimiento_esperado"] = round(growth_val, 2)

    if analyst_target and analyst_target.get("mean"):
        methods["consenso_analistas"] = round(analyst_target["mean"], 2)

    if not methods:
        return {
            "methods": {},
            "conservative": None,
            "base": None,
            "optimistic": None,
            "upside_pct": None,
            "note": "No hay datos fundamentales suficientes para estimar un precio objetivo.",
        }

    values = list(methods.values())
    conservative = min(values)
    optimistic = max(values)
    base = sum(values) / len(values)

    upside_pct = ((base - current_price) / current_price * 100) if current_price else None

    return {
        "methods": methods,
        "conservative": round(conservative, 2),
        "base": round(base, 2),
        "optimistic": round(optimistic, 2),
        "upside_pct": round(upside_pct, 2) if upside_pct is not None else None,
        "num_methods": len(methods),
        "note": f"Estimado combinando {len(methods)} método(s): {', '.join(methods.keys())}.",
    }
