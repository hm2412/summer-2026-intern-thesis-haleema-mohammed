# data.py
import yfinance as yf
import pandas as pd
import streamlit as st

SPACE_STOCKS = ["RKLB", "ASTS", "PL", "BKSY", "SPCE"]
SPACE_ETFS = ["ARKX", "UFO"]
BENCHMARKS = ["SPY", "QQQ", "ARKK"]
ALL_TICKERS = SPACE_STOCKS + SPACE_ETFS + BENCHMARKS
START_DATE = "2021-04-30"
END_DATE = "2026-07-14"

@st.cache_data
def load_price_data(tickers, start, end):
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True)
    prices = raw["Close"]
    return prices.dropna(axis=1, how="all")

@st.cache_data
def compute_daily_returns(prices):
    return prices.pct_change().dropna(how="all")