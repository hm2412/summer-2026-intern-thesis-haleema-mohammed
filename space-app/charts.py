"""
charts.py — Plotly figure builders.

No Streamlit calls, no computation. Each function takes already-computed
data (from analysis.py) and returns a go.Figure for app.py to render with
st.plotly_chart(). Plotly (not matplotlib) is used deliberately so hover
tooltips, zoom, and range sliders come for free in Streamlit.
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def plot_correlation_heatmap(corr_matrix: pd.DataFrame, title: str = "Correlation Matrix") -> go.Figure:
    fig = px.imshow(
        corr_matrix,
        text_auto=True,
        color_continuous_scale="RdYlGn",
        zmin=-1,
        zmax=1,
        aspect="auto",
        labels=dict(color="Correlation"),
    )
    fig.update_layout(title=title, xaxis_title=None, yaxis_title=None)
    fig.update_traces(hovertemplate="%{y} vs %{x}<br>corr = %{z:.2f}<extra></extra>")
    return fig


def plot_regression_scatter(returns: pd.DataFrame, ticker: str, benchmark: str, beta_stats: dict) -> go.Figure:
    df = returns[[ticker, benchmark]].dropna()
    slope = beta_stats["beta"]
    intercept = beta_stats["intercept"]
    r_squared = beta_stats["r_squared"]

    x_line = np.linspace(df[benchmark].min(), df[benchmark].max(), 100)
    y_line = slope * x_line + intercept

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[benchmark], y=df[ticker], mode="markers",
        marker=dict(size=6, opacity=0.4),
        name=f"{ticker} daily returns",
        hovertemplate=f"{benchmark}: %{{x:.2%}}<br>{ticker}: %{{y:.2%}}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x_line, y=y_line, mode="lines",
        line=dict(color="red"),
        name=f"Beta = {slope:.2f}, R² = {r_squared:.2f}",
    ))
    fig.update_layout(
        title=f"{ticker} vs {benchmark} Daily Returns",
        xaxis_title=f"{benchmark} daily return",
        yaxis_title=f"{ticker} daily return",
        xaxis_tickformat=".1%",
        yaxis_tickformat=".1%",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    return fig


def plot_vol_drawdown_bar(vol_table: pd.DataFrame) -> go.Figure:
    """Grouped bar: annualised volatility vs max drawdown, one bar-pair per ticker."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=vol_table.index, y=vol_table["annualised_volatility_pct"],
        name="Annualised volatility (%)",
    ))
    fig.add_trace(go.Bar(
        x=vol_table.index, y=vol_table["max_drawdown_pct"],
        name="Max drawdown (%)",
    ))
    fig.update_layout(
        title="Annualised Volatility vs Max Drawdown",
        barmode="group",
        yaxis_title="%",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def plot_cumulative_returns(indexed: pd.DataFrame, title: str = "Cumulative Return (Indexed to 100)") -> go.Figure:
    fig = go.Figure()
    for ticker in indexed.columns:
        fig.add_trace(go.Scatter(x=indexed.index, y=indexed[ticker], mode="lines", name=ticker))
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Value of $100 invested",
        hovermode="x unified",
    )
    fig.update_xaxes(rangeslider_visible=True)
    return fig


def plot_rolling_volatility(
    rolling_vol: pd.DataFrame, window: int, event_markers: list[dict] | None = None
) -> go.Figure:
    """
    event_markers: optional list of {"date": ..., "label": ...} dicts for the
    manually-curated news/event overlay (deferred — see NEXT STEPS). Passing
    None renders the plain rolling-vol chart with a range slider.
    """
    fig = go.Figure()
    for ticker in rolling_vol.columns:
        fig.add_trace(go.Scatter(x=rolling_vol.index, y=rolling_vol[ticker], mode="lines", name=ticker))

    if event_markers:
        for event in event_markers:
            fig.add_vline(x=event["date"], line_dash="dot", line_color="gray", opacity=0.6)
            fig.add_annotation(
                x=event["date"], y=1, yref="paper", showarrow=False,
                text=event["label"], textangle=-90, xanchor="right",
                font=dict(size=10, color="gray"),
            )

    fig.update_layout(
        title=f"{window}-Day Rolling Annualised Volatility",
        xaxis_title="Date",
        yaxis_title="Annualised volatility (%)",
        hovermode="x unified",
    )
    fig.update_xaxes(rangeslider_visible=True)
    return fig