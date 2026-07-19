"""
data.py — Data loading for the Space Economy Streamlit app.

Pure functions only. Caching lives here via @st.cache_data so app.py doesn't
need to know anything about caching strategy.
"""
import streamlit as st
import yfinance as yf
import pandas as pd

SPACE_STOCKS = ["RKLB", "ASTS", "PL", "BKSY", "SPCE"]
SPACE_ETFS = ["ARKX", "UFO"]
BENCHMARKS = ["SPY", "QQQ", "ARKK"]
ALL_TICKERS = SPACE_STOCKS + SPACE_ETFS + BENCHMARKS

START_DATE = "2021-04-30"  # adjusted to youngest ticker's IPO (RKLB/ASTS, 2021)
END_DATE = "2026-07-14"    # future improvement: set to today() at runtime


@st.cache_data(ttl=60 * 60 * 12, show_spinner="Downloading price data...")
def load_price_data(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Downloads daily adjusted close prices. Rows = dates, columns = tickers."""
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True)
    prices = raw["Close"]
    prices = prices.dropna(axis=1, how="all")  # drop tickers that fail to download
    return prices


@st.cache_data
def compute_daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Daily pct-change returns from a price frame."""
    return prices.pct_change().dropna(how="all")