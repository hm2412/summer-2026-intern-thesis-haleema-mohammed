"""
Space economy — animated orbital map.

  - planet size   = market cap (sqrt scale, clamped)
  - orbit ring     = years to consensus profitability (3 discrete rings)
  - orbit speed    = total return since IPO relative to a growth-narrative
                     benchmark. All planets orbit the same direction
                     (clockwise); FAST = beating the narrative, SLOW =
                     lagging it. Stroke color (green/red) reinforces
                     ahead/behind.

Clicking a planet is handled by a real bidirectional Streamlit component
(see orbital_frontend/index.html) that reports the clicked ticker straight
back to Python via Streamlit's component messaging protocol. An earlier
version tried to navigate window.parent.location from inside the iframe —
that's silently blocked by the sandbox Streamlit renders custom HTML in,
which is why clicks did nothing. declare_component() sidesteps that
entirely: no navigation happens, the click value is just passed back.

Run with:  streamlit run orbital_map.py
"""

import os

import streamlit as st
import streamlit.components.v1 as components

from deepdive import render_deep_dive

_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "orbital_frontend")
_orbital_component = components.declare_component("orbital_map", path=_FRONTEND_DIR)

# --------------------------------------------------------------------------
# Sample data — replace with your real, computed dataset once that
# pipeline is built. Numbers below are illustrative placeholders.
# --------------------------------------------------------------------------

SAMPLE_STOCKS = [
    {
        "ticker": "IRDM", "name": "Iridium Communications",
        "market_cap": 4.2e9, "years_to_profitability": None,
        "is_profitable_now": True, "return_since_ipo_pct": 45,
        "benchmark_return_pct": 60, "tier": "mature", "ipo_date": "2009-02-01",
        "listing_method": "Traditional", "sector_tier": "Prime",
    },
    {
        "ticker": "LMT", "name": "Lockheed Martin",
        "market_cap": 110e9, "years_to_profitability": None,
        "is_profitable_now": True, "return_since_ipo_pct": 180,
        "benchmark_return_pct": 60, "tier": "mature", "ipo_date": "1995-03-01",
        "listing_method": "Traditional", "sector_tier": "Prime",
    },
    {
        "ticker": "RKLB", "name": "Rocket Lab",
        "market_cap": 14e9, "years_to_profitability": 1.5,
        "is_profitable_now": False, "return_since_ipo_pct": 210,
        "benchmark_return_pct": 90, "tier": "scaling", "ipo_date": "2021-08-25",
        "listing_method": "SPAC-listed", "sector_tier": "Pure-play",
    },
    {
        "ticker": "LUNR", "name": "Intuitive Machines",
        "market_cap": 1.1e9, "years_to_profitability": 2,
        "is_profitable_now": False, "return_since_ipo_pct": -35,
        "benchmark_return_pct": 90, "tier": "scaling", "ipo_date": "2023-02-13",
        "listing_method": "SPAC-listed", "sector_tier": "Pure-play",
    },
    {
        "ticker": "PL", "name": "Planet Labs",
        "market_cap": 2.6e9, "years_to_profitability": 1,
        "is_profitable_now": False, "return_since_ipo_pct": 15,
        "benchmark_return_pct": 90, "tier": "scaling", "ipo_date": "2021-12-08",
        "listing_method": "Traditional", "sector_tier": "Pure-play",
    },
    {
        "ticker": "ASTS", "name": "AST SpaceMobile",
        "market_cap": 9.5e9, "years_to_profitability": 4,
        "is_profitable_now": False, "return_since_ipo_pct": 650,
        "benchmark_return_pct": 90, "tier": "speculative", "ipo_date": "2021-04-06",
        "listing_method": "SPAC-listed", "sector_tier": "Pure-play",
    },
    {
        "ticker": "RDW", "name": "Redwire",
        "market_cap": 1.3e9, "years_to_profitability": None,
        "is_profitable_now": False, "return_since_ipo_pct": -60,
        "benchmark_return_pct": 90, "tier": "speculative", "ipo_date": "2021-09-02",
        "listing_method": "SPAC-listed", "sector_tier": "Pure-play",
    },
    {
        "ticker": "SPCE", "name": "Virgin Galactic",
        "market_cap": 0.3e9, "years_to_profitability": None,
        "is_profitable_now": False, "return_since_ipo_pct": -97,
        "benchmark_return_pct": 90, "tier": "speculative", "ipo_date": "2019-10-28",
        "listing_method": "SPAC-listed", "sector_tier": "Pure-play",
    },
    {
        "ticker": "BKSY", "name": "BlackSky",
        "market_cap": 0.6e9, "years_to_profitability": None,
        "is_profitable_now": False, "return_since_ipo_pct": -55,
        "benchmark_return_pct": 90, "tier": "speculative", "ipo_date": "2021-09-09",
        "listing_method": "SPAC-listed", "sector_tier": "Pure-play",
    },
]


def _compute_ring(years_to_profitability, is_profitable_now):
    if is_profitable_now:
        return 0
    if years_to_profitability is None:
        return 2
    if years_to_profitability <= 3:
        return 1
    return 2


def _prepare_data(stocks):
    prepared = []
    for s in stocks:
        relative_return = s["return_since_ipo_pct"] - s["benchmark_return_pct"]
        prepared.append({
            **s,
            "ring": _compute_ring(s.get("years_to_profitability"), s.get("is_profitable_now", False)),
            "relative_return_pct": relative_return,
        })
    return prepared


def render_orbital_map(stocks, height=850, key="orbital_map"):
    """
    Renders the animated orbital map and returns the clicked ticker (a str),
    or None if nothing has been clicked yet. The return value is exactly
    what the frontend's setComponentValue(ticker) call sends back.
    """
    data = _prepare_data(stocks)
    return _orbital_component(stocks=data, height=height, key=key, default=None)


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

    if st.session_state.selected_ticker is not None:
        match = next(
            (s for s in SAMPLE_STOCKS if s["ticker"] == st.session_state.selected_ticker),
            None,
        )
        if match is None:
            st.session_state.selected_ticker = None
            st.rerun()
        render_deep_dive(match)
        return

    st.title("Space economy — orbital map")
    st.caption(
        "Size = market cap · distance from sun = years to profitability · "
        "orbit speed = ahead (fast) or behind (slow) the growth-narrative benchmark"
    )

    clicked = render_orbital_map(SAMPLE_STOCKS, height=850)
    if clicked:
        st.session_state.selected_ticker = clicked
        st.rerun()


if __name__ == "__main__":
    main()