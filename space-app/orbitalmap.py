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
        revenue_cagr_pct = data.compute_revenue_cagr(annual_revenue, years=3)

        price_history = data.load_full_price_history(ticker)
        tsr_3y_pct = data.compute_total_shareholder_return(price_history, years=3)
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
            "tsr_3y_pct": tsr_3y_pct,
            "cash_runway_years": cash_runway_years,
            "is_cash_generating": is_cash_generating,
        })
    return planets


# ---------------------------------------------------------------------
# Sector KPI strip — the panel itself is rendered inside the HTML
# component (orbital_frontend/index.html) so the universe toggle is
# instant with no Streamlit rerun. The only thing Python needs to supply
# is the S&P 500 benchmark return, since that's independent of the
# per-company `planets` data already being passed to the component.
# ---------------------------------------------------------------------
@st.cache_data(ttl=60 * 60, show_spinner=False)
def _load_benchmark_return(ticker: str = "SPY", years: int = 3) -> float | None:
    """S&P 500's 3-year total return, computed once — independent of the
    pure-play/all-companies universe toggle."""
    hist = data.load_full_price_history(ticker)
    return data.compute_total_shareholder_return(hist, years=years)


def render_orbital_map(stocks, height=850, benchmark_tsr=None, key="orbital_map"):
    """
    Renders the animated orbital map, including the sector KPI panel
    (which lives inside the component itself and updates purely
    client-side when the universe toggle is clicked — no Streamlit
    rerun). Returns the clicked ticker (a str), or None if nothing has
    been clicked yet — exactly what the frontend's setComponentValue(ticker)
    call sends back.
    """
    return _orbital_component(
        stocks=stocks, height=height, benchmark_tsr=benchmark_tsr, key=key, default=None
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

    st.title("Space economy — orbital map")
    st.caption(
        "Size = market cap · distance from sun = profitability (operating margin) · "
        "orbit speed = 3-year revenue growth · colour = 3-year shareholder return"
    )

    benchmark_tsr = _load_benchmark_return("SPY", years=3)
    clicked = render_orbital_map(planets, height=850, benchmark_tsr=benchmark_tsr)
    if clicked:
        st.session_state.selected_ticker = clicked
        st.rerun()


if __name__ == "__main__":
    main()