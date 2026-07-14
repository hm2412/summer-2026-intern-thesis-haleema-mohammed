# app.py
import streamlit as st
import matplotlib.pyplot as plt
from data import load_price_data, compute_daily_returns, ALL_TICKERS, START_DATE, END_DATE

prices = load_price_data(ALL_TICKERS, START_DATE, END_DATE)
returns = compute_daily_returns(prices)

selected = st.multiselect("Choose tickers", prices.columns.tolist(), default=["SPY", "RKLB"])

if selected:
    indexed = prices[selected] / prices[selected].iloc[0] * 100
    fig, ax = plt.subplots()
    ax.plot(indexed)
    ax.legend(selected)
    st.pyplot(fig)