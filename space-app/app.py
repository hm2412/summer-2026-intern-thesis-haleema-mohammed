"""
app.py — Streamlit UI for the Space Economy dashboard (lower tier).

Calls into data.py / analysis.py / charts.py. No computation lives here —
this file is purely: get inputs from the sidebar, call functions, render output.

Run with: python -m streamlit run app.py
"""
import streamlit as st

from data import (
    SPACE_STOCKS, SPACE_ETFS, BENCHMARKS, ALL_TICKERS,
    START_DATE, END_DATE, load_price_data, compute_daily_returns,
)
from analysis import (
    compute_correlation_matrix, compute_cross_correlation,
    compute_beta_table, compute_beta_and_r2,
    compute_vol_table, compute_cumulative_returns, compute_rolling_volatility,
)
from charts import (
    plot_correlation_heatmap, plot_regression_scatter, plot_vol_drawdown_bar,
    plot_cumulative_returns, plot_rolling_volatility,
)

st.set_page_config(page_title="Space Economy: Legitimate Theme or Speculative Bet?", layout="wide")

st.title("Space Economy: Early Stage or Pipe Dream?")
st.caption("Do space stocks behave like an established industry, or a speculative bet?")

# ---------------------------------------------------------------------------
# Load data (cached — see data.py)
# ---------------------------------------------------------------------------
prices = load_price_data(ALL_TICKERS, START_DATE, END_DATE)
returns = compute_daily_returns(prices)
space_tickers = [t for t in SPACE_STOCKS if t in returns.columns]

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
st.sidebar.header("Controls")

selected_space = st.sidebar.multiselect(
    "Space stocks", options=space_tickers, default=space_tickers,
)
selected_benchmark = st.sidebar.selectbox(
    "Benchmark for beta/regression", options=BENCHMARKS, index=0,
)

min_date, max_date = returns.index.min().date(), returns.index.max().date()
date_range = st.sidebar.slider(
    "Date range", min_value=min_date, max_value=max_date,
    value=(min_date, max_date), format="YYYY-MM-DD",
)

vol_window = st.sidebar.slider(
    "Rolling volatility window (days)", min_value=5, max_value=90, value=30, step=5,
)

if not selected_space:
    st.warning("Select at least one space stock in the sidebar to see the charts.")
    st.stop()

# Filter to selected date range once, reuse everywhere below
date_mask = (returns.index.date >= date_range[0]) & (returns.index.date <= date_range[1])
returns_f = returns.loc[date_mask]
prices_f = prices.loc[(prices.index.date >= date_range[0]) & (prices.index.date <= date_range[1])]

# ---------------------------------------------------------------------------
# Headline metrics
# ---------------------------------------------------------------------------
st.subheader("Headline metrics")
metric_tickers = list(dict.fromkeys(selected_space + SPACE_ETFS + [selected_benchmark]))
vol_table = compute_vol_table(prices_f, returns_f, metric_tickers)

cols = st.columns(len(selected_space))
for col, ticker in zip(cols, selected_space):
    row = vol_table.loc[ticker]
    col.metric(
        label=ticker,
        value=f"{row['annualised_volatility_pct']:.1f}% vol",
        delta=f"{row['max_drawdown_pct']:.1f}% max DD",
        delta_color="inverse",  # a deeper drawdown is "bad", so colour it red
    )

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_corr, tab_beta, tab_vol = st.tabs(
    ["Correlation", "Beta & Regression", "Volatility, Drawdown & Returns"]
)

with tab_corr:
    st.subheader("Space stocks vs each other")
    corr_space = compute_correlation_matrix(returns_f, selected_space)
    st.plotly_chart(
        plot_correlation_heatmap(corr_space, "Space Stocks: Return Correlation"),
        use_container_width=True,
    )

    st.subheader("Space stocks vs benchmarks")
    corr_cross = compute_cross_correlation(returns_f, selected_space, BENCHMARKS)
    st.plotly_chart(
        plot_correlation_heatmap(corr_cross, "Space Stocks vs Benchmarks: Return Correlation"),
        use_container_width=True,
    )
    st.caption(
        "Space stocks tend to correlate most with ARKK (speculative growth), though even "
        "that correlation is modest — evidence of largely independent price action."
    )

with tab_beta:
    st.subheader(f"Beta & R² vs {selected_benchmark}")
    beta_table = compute_beta_table(returns_f, selected_space + SPACE_ETFS, selected_benchmark)
    st.dataframe(beta_table, use_container_width=True)
    st.caption(
        "High beta with low R² means these stocks amplify market moves but are mostly "
        "driven by idiosyncratic, company-specific volatility rather than the market. "
        "ETFs (ARKX/UFO) show higher R² thanks to diversification."
    )

    st.subheader("Regression detail")
    st.caption("Click through tickers to see the underlying scatter and fit line.")
    beta_ticker_tabs = st.tabs(selected_space)
    for sub_tab, ticker in zip(beta_ticker_tabs, selected_space):
        with sub_tab:
            stats_row = compute_beta_and_r2(returns_f, ticker, selected_benchmark)
            fig = plot_regression_scatter(returns_f, ticker, selected_benchmark, stats_row)
            st.plotly_chart(fig, use_container_width=True)

with tab_vol:
    st.subheader("Annualised volatility & max drawdown")
    display_tickers = list(dict.fromkeys(selected_space + [selected_benchmark]))
    st.plotly_chart(
        plot_vol_drawdown_bar(vol_table.loc[display_tickers]),
        use_container_width=True,
    )
    with st.expander("Show underlying numbers"):
        st.dataframe(
            vol_table.sort_values("annualised_volatility_pct", ascending=False),
            use_container_width=True,
        )

    st.subheader("Cumulative returns")
    cum_tickers = list(dict.fromkeys(
        selected_space + [selected_benchmark] + [t for t in SPACE_ETFS if t in prices_f.columns]
    ))
    indexed = compute_cumulative_returns(prices_f, cum_tickers)
    st.plotly_chart(plot_cumulative_returns(indexed), use_container_width=True)
    st.caption("Indexed to 100 at the start of the selected date range — drag the sidebar date slider to rebase.")

    st.subheader("Rolling volatility")
    rolling_tickers = list(dict.fromkeys(selected_space + [selected_benchmark]))
    rolling_vol = compute_rolling_volatility(returns_f, rolling_tickers, window=vol_window)
    st.plotly_chart(plot_rolling_volatility(rolling_vol, vol_window), use_container_width=True)
    st.caption(
        "Drag the range slider below the chart to zoom into a specific period. "
        "Manually-curated event markers land here next."
    )