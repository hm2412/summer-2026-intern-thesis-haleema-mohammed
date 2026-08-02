"""Requirements-driven deep-dive view for a single space-economy company."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from narrative import build_narrative_gap_chart, narrative_cagr_from_config
from narrative_config import NARRATIVE_FORECAST


def _format_currency(value: float | None, prefix: str = "$") -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if abs(value) >= 1e9:
        return f"{prefix}{value / 1e9:.1f}B"
    if abs(value) >= 1e6:
        return f"{prefix}{value / 1e6:.1f}M"
    return f"{prefix}{value:,.0f}"


def _format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.1f}%"


def _format_ratio(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.2f}x"


def _infer_company_tier(stock: dict) -> str:
    if stock.get("sector_tier"):
        return str(stock["sector_tier"])
    ticker = stock.get("ticker", "")
    pure_play_tickers = {"RKLB", "ASTS", "PL", "SPCE", "BKSY", "LUNR", "RDW"}
    return "Pure-play" if ticker in pure_play_tickers else "Prime"


def _infer_listing_method(stock: dict) -> str:
    if stock.get("listing_method"):
        return str(stock["listing_method"])
    ticker = stock.get("ticker", "")
    if ticker in {"RKLB", "ASTS", "PL", "SPCE", "BKSY", "LUNR", "RDW"}:
        return "SPAC-listed"
    return "Traditional"


def _extract_series(statement: pd.DataFrame | None, row_name: str) -> dict[str, float]:
    if statement is None or statement.empty:
        return {}
    if row_name in statement.index:
        series = statement.loc[row_name]
    else:
        return {}

    values: dict[str, float] = {}
    for idx, val in series.items():
        if pd.isna(val):
            continue
        try:
            period = pd.Timestamp(idx).to_period("Q") if isinstance(idx, pd.Timestamp) else idx
        except Exception:
            period = idx
        if hasattr(period, "strftime"):
            key = period.strftime("%YQ%q") if hasattr(period, "quarter") else str(period)
        else:
            key = str(period)
        values[key] = float(val)
    return values


def _coerce_years(series: dict[str, float]) -> list[int]:
    years: list[int] = []
    for key in series:
        if isinstance(key, int):
            years.append(key)
        elif isinstance(key, str):
            digits = "".join(ch for ch in key if ch.isdigit())[:4]
            if digits:
                years.append(int(digits))
    return sorted(set(years))


def _get_company_snapshot(ticker: str) -> dict:
    company = yf.Ticker(ticker)
    info = company.get_info() or {}
    hist = company.history(period="max", auto_adjust=True)
    hist = hist[["Close"]].dropna().copy()
    hist.index = pd.to_datetime(hist.index)
    hist.index = hist.index.tz_convert(None) if getattr(hist.index, "tz", None) is not None else hist.index
    hist = hist.sort_index()

    financials = company.financials
    cashflow = company.cashflow
    quarterly_financials = company.quarterly_financials
    quarterly_cashflow = company.quarterly_cashflow

    revenue_series = _extract_series(financials, "Total Revenue")
    if not revenue_series:
        revenue_series = _extract_series(quarterly_financials, "Total Revenue")

    free_cash_flow_series = {}
    for row_name in ["Free Cash Flow", "Capital Expenditure", "Operating Cash Flow"]:
        candidate = _extract_series(cashflow, row_name)
        if candidate:
            free_cash_flow_series = candidate
            break
    if not free_cash_flow_series:
        for row_name in ["Free Cash Flow", "Capital Expenditure", "Operating Cash Flow"]:
            candidate = _extract_series(quarterly_cashflow, row_name)
            if candidate:
                free_cash_flow_series = candidate
                break

    if free_cash_flow_series and revenue_series:
        periods = sorted(set(free_cash_flow_series) & set(revenue_series))
        revenue_periods = {p: revenue_series[p] for p in periods}
        fcf_periods = {p: free_cash_flow_series[p] for p in periods}
        fcf_margin_series = {p: (fcf_periods[p] / revenue_periods[p]) * 100 for p in periods if revenue_periods[p] not in (0, None)}
    else:
        fcf_margin_series = {}

    return {
        "info": info,
        "hist": hist,
        "revenue_series": revenue_series,
        "fcf_series": free_cash_flow_series,
        "fcf_margin_series": fcf_margin_series,
        "company_currency": info.get("financialCurrency") or info.get("currency") or "USD",
    }


@st.cache_data(show_spinner="Fetching company data...", ttl=60 * 60)
def _load_cached_snapshot(ticker: str) -> dict:
    return _get_company_snapshot(ticker)


def classify_closing_gap(fcf_margin_series: list[float], periods: list[str]) -> tuple[str, list[str]]:
    latest = periods[-4:]
    if len(latest) < 4:
        return "Not yet closing the gap", []

    values_by_period = {period: fcf_margin_series[idx] for idx, period in enumerate(periods)}
    improvements = []
    for idx in range(1, len(latest)):
        previous = values_by_period[latest[idx - 1]]
        current = values_by_period[latest[idx]]
        if current > previous:
            improvements.append(latest[idx])

    if len(improvements) >= 3:
        return "Closing the gap", improvements
    return "Not yet closing the gap", []


def _build_price_return_chart(hist: pd.DataFrame, ipo_date: str | None, ticker: str) -> go.Figure:
    horizons = ["Since IPO", "3Y", "1Y", "YTD"]
    horizon = st.radio("Time horizon", horizons, horizontal=True, key=f"{ticker}_horizon")
    latest_date = hist.index.max()

    if horizon == "Since IPO":
        anchor = pd.to_datetime(ipo_date) if ipo_date else hist.index.min()
    elif horizon == "3Y":
        anchor = latest_date - pd.DateOffset(years=3)
    elif horizon == "1Y":
        anchor = latest_date - pd.DateOffset(years=1)
    else:
        anchor = pd.Timestamp(year=latest_date.year, month=1, day=1)

    if getattr(hist.index, "tz", None) is not None:
        hist = hist.copy()
        hist.index = hist.index.tz_convert(None)

    anchor = pd.Timestamp(anchor).tz_localize(None) if getattr(anchor, "tzinfo", None) is not None else pd.Timestamp(anchor)
    window = hist.loc[hist.index >= anchor]
    if window.empty:
        window = hist

    window = window.copy()
    window.index = pd.to_datetime(window.index)
    window = window.loc[window.index >= window.index.min()]
    first_value = window.iloc[0]["Close"]
    indexed = window["Close"] / first_value * 100.0

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=window.index, y=indexed, mode="lines", name="Indexed price",
        line=dict(color="#8fbcff", width=3),
        fill="tozeroy", fillcolor="rgba(143,188,255,0.12)",
    ))
    fig.add_vrect(x0=pd.Timestamp("2021-01-01"), x1=pd.Timestamp("2022-12-31"), fillcolor="#ff7a72", opacity=0.12, line_width=0)
    fig.update_layout(
        title=f"{ticker}: indexed price return",
        xaxis_title="Date",
        yaxis_title="Index (start = 100)",
        template="plotly_dark",
        paper_bgcolor="#151b28",
        plot_bgcolor="#151b28",
        font=dict(color="#e9edf5"),
        margin=dict(t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        xaxis=dict(range=[window.index.min(), window.index.max()], gridcolor="#2a3345"),
        yaxis=dict(gridcolor="#2a3345"),
    )
    return fig


def _build_fundamentals_chart(revenue_series: dict[str, float], fcf_margin_series: dict[str, float], ticker: str) -> go.Figure:
    periods = sorted(set(revenue_series) & set(fcf_margin_series))
    if len(periods) < 2:
        periods = sorted(set(revenue_series) | set(fcf_margin_series))

    revenue_growth = []
    for idx, period in enumerate(periods):
        if idx == 0:
            revenue_growth.append(None)
            continue
        prev_period = periods[idx - 1]
        prev_value = revenue_series[prev_period]
        current_value = revenue_series[period]
        if prev_value in (0, None):
            revenue_growth.append(None)
        else:
            revenue_growth.append((current_value / prev_value - 1) * 100)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=periods, y=[fcf_margin_series.get(p) for p in periods], mode="lines+markers", name="FCF margin (%)", yaxis="y1", line=dict(color="#ff7a72", width=2), marker=dict(color="#ff7a72")))
    fig.add_trace(go.Scatter(x=periods, y=revenue_growth, mode="lines+markers", name="Revenue growth YoY (%)", yaxis="y2", line=dict(color="#8fbcff", width=2), marker=dict(color="#8fbcff")))
    fig.update_layout(
        title=f"{ticker}: fundamentals trend",
        template="plotly_dark",
        paper_bgcolor="#151b28",
        plot_bgcolor="#151b28",
        font=dict(color="#e9edf5"),
        yaxis=dict(title="FCF margin (%)", showgrid=False),
        yaxis2=dict(title="Revenue growth YoY (%)", overlaying="y", side="right", showgrid=False),
        margin=dict(t=50, b=20),
    )
    return fig


def _build_narrative_chart(ticker: str, years: list[int], revenue_series: list[float], price_series: list[float], narrative_cagr: float) -> go.Figure:
    fig = build_narrative_gap_chart(
        ticker=ticker,
        years=years,
        revenue=revenue_series,
        price=price_series,
        narrative_cagr=narrative_cagr,
        start_year=years[0],
        bubble_band=(2021, 2022),
    )
    # narrative.py builds this figure with its own trace colors, so we only
    # override the theme-level settings here rather than individual traces.
    fig.update_layout(
        title=f"{ticker}: narrative vs. fundamentals vs. price",
        template="plotly_dark",
        paper_bgcolor="#151b28",
        plot_bgcolor="#151b28",
        font=dict(color="#e9edf5"),
    )
    return fig


def render_deep_dive(stock: dict):
    """Render the evidence-driven deep-dive screen for a company."""
    if st.button("← Back to orbital map"):
        st.session_state.selected_ticker = None
        st.rerun()

    ticker = stock["ticker"]
    try:
        snapshot = _load_cached_snapshot(ticker)
    except Exception as exc:
        st.warning(f"Could not fetch live data for {ticker}: {exc}. Showing the screen with placeholders instead.")
        snapshot = {
            "info": {},
            "hist": pd.DataFrame(columns=["Close"]),
            "revenue_series": {},
            "fcf_series": {},
            "fcf_margin_series": {},
            "company_currency": "USD",
        }
    info = snapshot["info"]
    hist = snapshot["hist"]
    revenue_series = snapshot["revenue_series"]
    fcf_series = snapshot["fcf_series"]
    fcf_margin_series = snapshot["fcf_margin_series"]
    company_currency = snapshot["company_currency"]

    st.title(f"{ticker} — {stock['name']}")
    st.caption(
        f"{_infer_company_tier(stock)} · IPO {stock.get('ipo_date', 'unknown')} · {_infer_listing_method(stock)}"
    )

    latest_price = hist["Close"].iloc[-1] if not hist.empty else None
    latest_revenue = None
    if revenue_series:
        latest_revenue = list(revenue_series.values())[-1]

    market_cap = info.get("marketCap")
    if market_cap is None and stock.get("market_cap"):
        market_cap = stock["market_cap"]

    latest_fcf = None
    if fcf_series:
        latest_fcf = list(fcf_series.values())[-1]

    revenue_growth = None
    if len(revenue_series) >= 2:
        sorted_periods = sorted(revenue_series)
        recent = sorted_periods[-1]
        previous = sorted_periods[-2]
        if revenue_series[previous] not in (0, None):
            revenue_growth = (revenue_series[recent] / revenue_series[previous] - 1) * 100

    price_to_sales = None
    if market_cap and latest_revenue not in (None, 0):
        price_to_sales = market_cap / latest_revenue
    elif info.get("priceToSalesTrailing12Months"):
        price_to_sales = info.get("priceToSalesTrailing12Months")

    c1, c2, c3, c4 = st.columns(4)
    c1.html(f"""
            <div>
            <div style="font-size:0.9rem;">Market cap</div>
            <div style="font-size:2.5rem;font-weight:600; color: white">{_format_currency(market_cap)}</div>
            </div>
            """)
    c2.html(f"""
        <div>
        <div style="font-size:0.9rem;">Free cash flow</div>
        <div style="font-size:2.5rem;font-weight:600;
                    color:{'green' if latest_fcf >= 0 else 'red'}">
            {_format_currency(latest_fcf)}
        </div>
        </div>
        """)
    c3.html(f"""
    <div>
    <div style="font-size:0.9rem;">Revenue growth YoY</div>
    <div style="font-size:2.5rem;font-weight:600;
                color:{'green' if revenue_growth >= 0 else 'red'}">
        {_format_pct(revenue_growth)}
    </div>
    </div>
    """)
    c4.html(f"""
            <div>
            <div style="font-size:0.9rem;">Price/sales</div>
            <div style="font-size:2.5rem;font-weight:600; color: white">{_format_ratio(price_to_sales)}</div>
            </div>
            """)

    st.divider()

    st.subheader("Price return chart")
    fig_price = _build_price_return_chart(hist, stock.get("ipo_date"), ticker)
    st.plotly_chart(fig_price, use_container_width=True)
    st.caption("The return window changes the conclusion, which is the point of the toggle.")

    st.subheader("Narrative vs. fundamentals vs. price")
    narrative_cagr = narrative_cagr_from_config()
    if hist.empty or not revenue_series:
        st.warning("The available data for this ticker is incomplete, so the chart is shown as a placeholder until more fundamentals are available.")
        years = list(range(2020, 2026))
        revenue_series_placeholder = [100 + i * 8 for i in range(len(years))]
        price_series_placeholder = [100 + i * 10 for i in range(len(years))]
        st.plotly_chart(_build_narrative_chart(ticker, years, revenue_series_placeholder, price_series_placeholder, narrative_cagr), use_container_width=True)
    else:
        years = _coerce_years(revenue_series)
        if not years:
            years = list(range(2020, 2026))
        revenue_by_year = {}
        for key, value in revenue_series.items():
            year = None
            if isinstance(key, int):
                year = key
            elif isinstance(key, str):
                digits = "".join(ch for ch in key if ch.isdigit())[:4]
                if digits:
                    year = int(digits)
            if year is not None:
                revenue_by_year[year] = value

        if years and len(years) >= 2:
            base_revenue = revenue_by_year.get(years[0])
            if base_revenue in (None, 0):
                base_revenue = next((value for value in revenue_by_year.values() if value not in (None, 0)), 1.0)
            revenue_indexed = [revenue_by_year.get(year, 0) / base_revenue * 100 if base_revenue not in (None, 0) else 100 for year in years]
            yearly_prices = hist.groupby(hist.index.year)["Close"].last()
            price_indexed = []
            for year in years:
                price = yearly_prices.get(year)
                if price is None:
                    price_indexed.append(None)
                else:
                    price_indexed.append(price)
            first_price = next((value for value in price_indexed if value is not None), None)
            if first_price is not None:
                price_indexed = [100.0 if value is None else (value / first_price * 100.0) for value in price_indexed]
            else:
                price_indexed = [100.0 for _ in years]
            fig_narrative = _build_narrative_chart(ticker, years, revenue_indexed, price_indexed, narrative_cagr)
            st.plotly_chart(fig_narrative, use_container_width=True)
        else:
            st.info("Not enough aligned annual data to plot the narrative chart yet.")

    if company_currency and company_currency != NARRATIVE_FORECAST["currency"]:
        st.caption(f"The narrative forecast is configured in {NARRATIVE_FORECAST['currency']}; the company currency is {company_currency}, so the chart reflects the configured conversion rate explicitly.")
    else:
        st.caption(f"Narrative source: {NARRATIVE_FORECAST['citation']}.")

    st.subheader("Fundamentals trend")
    if fcf_margin_series:
        fig_fund = _build_fundamentals_chart(revenue_series, fcf_margin_series, ticker)
        st.plotly_chart(fig_fund, use_container_width=True)
    else:
        st.info("Quarterly or annual fundamentals are not available for this ticker, so the trend view is limited to the data that could be fetched.")

    st.subheader("Closing the gap")
    periods = list(fcf_margin_series.keys())
    if len(periods) >= 4:
        status, improving_periods = classify_closing_gap(list(fcf_margin_series.values()), periods)
        st.write(f"**{status}**")
        if improving_periods:
            st.caption(f"Periods driving the signal: {', '.join(improving_periods)}")
        else:
            st.caption("Rule: FCF margin must improve in at least 3 of the last 4 reporting periods.")
    else:
        st.write("**Not yet closing the gap**")
        st.caption("Insufficient reporting periods are available to apply the closing-gap rule.")