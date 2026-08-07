"""
Space economy — animated orbital map.

  - planet size    = market cap (log scale, clamped)
  - orbit distance  = profitability (operating margin, tanh-compressed,
                       CONTINUOUS — close orbit = profitable, far orbit =
                       loss-making; unknown margin is pushed to the outer
                       edge and flagged rather than guessed)
  - orbit speed     = 3-year revenue CAGR (fast = high growth)
  - planet colour   = 3-year total shareholder return, diverging
                       red -> green scale
  - anywhere Yahoo Finance doesn't have enough history for a metric
    (common for recently-listed / small-cap tickers), that metric is
    left as None and the frontend renders it as grey / "insufficient
    data" instead of a fabricated number.

Clicking a planet is handled by a real bidirectional Streamlit component
(see orbital_frontend/index.html) that reports the clicked ticker straight
back to Python via Streamlit's component messaging protocol.

Run with:  streamlit run orbital_map.py
"""

import math
import os

import streamlit as st
import streamlit.components.v1 as components

from deepdive import render_deep_dive
import data

_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "orbital_frontend")
_orbital_component = components.declare_component("orbital_map", path=_FRONTEND_DIR)

# Year-window options the legend sliders can select between for revenue
# growth and shareholder return. Precomputing all of them server-side
# (cheap — reuses the annual_revenue / price_history already fetched per
# company) means the slider can switch instantly in the browser with no
# Streamlit round-trip.
YEAR_WINDOW_OPTIONS = (1, 2, 3, 4, 5)
DEFAULT_YEARS = 3


@st.cache_data(ttl=60 * 60, show_spinner="Loading live financials...")
def _load_live_planet_data() -> list[dict]:
    """
    Builds the per-planet dataset from live Yahoo Finance data via
    data.py, one company at a time. Every metric that Yahoo Finance
    doesn't have enough history to support for a given ticker is left
    as None (never estimated) — the frontend is responsible for
    rendering that as "insufficient data".
    """
    planets = []
    for ticker, meta in data.SPACE_COMPANIES.items():
        fundamentals = data.load_company_fundamentals(ticker)
        info = fundamentals["info"]

        market_cap = info.get("marketCap")

        operating_margin_pct = data.latest_operating_margin(fundamentals["operating_margin"])
        profitability_score = (
            math.tanh(operating_margin_pct / 100) if operating_margin_pct is not None else None
        )

        annual_revenue = data.load_annual_revenue(ticker)
        revenue_cagr_by_years = {
            n: data.compute_revenue_cagr(annual_revenue, years=n) for n in YEAR_WINDOW_OPTIONS
        }
        revenue_cagr_pct = revenue_cagr_by_years[DEFAULT_YEARS]

        price_history = data.load_full_price_history(ticker)
        tsr_by_years = {
            n: data.compute_total_shareholder_return(price_history, years=n) for n in YEAR_WINDOW_OPTIONS
        }
        tsr_3y_pct = tsr_by_years[DEFAULT_YEARS]
        ipo_date = (
            price_history.index.min().strftime("%Y-%m-%d")
            if not price_history.empty else "unknown"
        )

        cash_balance = data.latest_value(fundamentals["cash_balance"])
        free_cash_flow = data.latest_value(fundamentals["free_cash_flow"])
        cash_runway_years, is_cash_generating = data.compute_cash_runway(
            cash_balance, free_cash_flow, fundamentals["is_quarterly"]
        )

        planets.append({
            "ticker": ticker,
            "name": meta["name"],
            "category": meta["category"],
            "market_cap": market_cap,
            "ipo_date": ipo_date,
            "operating_margin_pct": operating_margin_pct,
            "profitability_score": profitability_score,
            "revenue_cagr_pct": revenue_cagr_pct,
            "revenue_cagr_by_years": revenue_cagr_by_years,
            "tsr_3y_pct": tsr_3y_pct,
            "tsr_by_years": tsr_by_years,
            "cash_runway_years": cash_runway_years,
            "is_cash_generating": is_cash_generating,
        })
    return planets


# ---------------------------------------------------------------------
# Sector KPI strip — the panel itself is rendered inside the HTML
# component (orbital_frontend/index.html) so both the universe toggle
# and the growth/return year sliders are instant with no Streamlit
# rerun. Python's job is just to supply the S&P 500 benchmark return for
# every year option the slider can select, since that's independent of
# the per-company `planets` data already being passed to the component.
# ---------------------------------------------------------------------
@st.cache_data(ttl=60 * 60, show_spinner=False)
def _load_benchmark_return(ticker: str = "SPY", years: int = 3) -> float | None:
    """S&P 500's 3-year total return, computed once — independent of the
    pure-play/all-companies universe toggle."""
    hist = data.load_full_price_history(ticker)
    return data.compute_total_shareholder_return(hist, years=years)


def render_orbital_map(
    stocks, height=850, benchmark_tsr_by_years=None, arkk_tsr_by_years=None, key="orbital_map"
):
    """
    Renders the animated orbital map, including the sector KPI panel and
    the growth/return year-window sliders — all of which live inside the
    component itself and update purely client-side (no Streamlit rerun).
    benchmark_tsr_by_years is the S&P 500 comparison; arkk_tsr_by_years
    is ARKK (a standard high-growth/pre-profit-stock proxy), shown
    alongside it so the reader can judge whether the sector's return
    pattern is space-specific or just how the market treats speculative
    growth generally. Returns the clicked ticker (a str), or None if
    nothing has been clicked yet — exactly what the frontend's
    setComponentValue(ticker) call sends back.
    """
    return _orbital_component(
        stocks=stocks, height=height, benchmark_tsr_by_years=benchmark_tsr_by_years,
        arkk_tsr_by_years=arkk_tsr_by_years, key=key, default=None,
    )


def main():
    st.set_page_config(page_title="Space economy — orbital map", layout="wide")

    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0.5rem;
            padding-bottom: 0rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 100%;
        }
        header[data-testid="stHeader"] { height: 0; visibility: hidden; }
        footer { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "selected_ticker" not in st.session_state:
        st.session_state.selected_ticker = None

    planets = _load_live_planet_data()

    if st.session_state.selected_ticker is not None:
        match = next(
            (p for p in planets if p["ticker"] == st.session_state.selected_ticker),
            None,
        )
        if match is None:
            st.session_state.selected_ticker = None
            st.rerun()
        render_deep_dive(match)
        return

    st.title("Mapping the space economy")

    benchmark_tsr_by_years = {
        n: _load_benchmark_return("SPY", years=n) for n in YEAR_WINDOW_OPTIONS
    }
    arkk_tsr_by_years = {
        n: _load_benchmark_return("ARKK", years=n) for n in YEAR_WINDOW_OPTIONS
    }
    clicked = render_orbital_map(
        planets, height=850,
        benchmark_tsr_by_years=benchmark_tsr_by_years,
        arkk_tsr_by_years=arkk_tsr_by_years,
    )
    if clicked:
        st.session_state.selected_ticker = clicked
        st.rerun()


if __name__ == "__main__":
    main()