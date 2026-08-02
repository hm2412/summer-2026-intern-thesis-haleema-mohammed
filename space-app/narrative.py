"""
Reusable component: narrative vs. actual revenue vs. actual stock price,
all indexed to 100 at a common start year.

Usage in Streamlit:

    import streamlit as st
    from narrative_gap_chart import fetch_company_data, build_narrative_gap_chart

    data = fetch_company_data("RKLB", start_year=2020, end_year=2026)
    fig = build_narrative_gap_chart(
        ticker="RKLB",
        years=data["years"],
        revenue=data["revenue"],
        price=data["price"],
        narrative_cagr=0.091,   # McKinsey-implied 9.1%/yr, computed separately
        start_year=2020,
        bubble_band=(2021, 2022),  # shade SPAC-era peak/crash, or None
    )
    st.plotly_chart(fig, use_container_width=True)

Call this once per ticker inside your deep-dive view (the "click on a planet"
screen) — pass in whichever ticker was clicked.
"""

import plotly.graph_objects as go
import yfinance as yf

from narrative_config import NARRATIVE_FORECAST


# ---------------------------------------------------------------------------
# 1. NARRATIVE CAGR — compute once, reuse for every company
# ---------------------------------------------------------------------------

def narrative_cagr(start_value: float, end_value: float, years: float) -> float:
    """Turn a headline forecast into an annualised growth rate."""
    return (end_value / start_value) ** (1 / years) - 1


def narrative_cagr_from_config() -> float:
    """Compute the narrative CAGR from the editable configuration block."""
    baseline = NARRATIVE_FORECAST["baseline_value"]
    target = NARRATIVE_FORECAST["target_value"]
    years = NARRATIVE_FORECAST["target_year"] - NARRATIVE_FORECAST["baseline_year"]
    return narrative_cagr(baseline, target, years)


def index_series_from_cagr(cagr: float, num_years: int, base: float = 100.0) -> list[float]:
    """Build the dashed 'narrative-implied' line: 100 growing at a fixed CAGR."""
    return [base * (1 + cagr) ** i for i in range(num_years)]


# ---------------------------------------------------------------------------
# 2. DATA FETCHING — pull what the chart needs, per ticker
# ---------------------------------------------------------------------------

def fetch_company_data(ticker: str, start_year: int, end_year: int) -> dict:
    """
    Pulls the two real series the chart needs:
      - 'price':   year-end adjusted close, indexed to 100 at start_year
      - 'revenue': annual total revenue, indexed to 100 at start_year

    NOTE: yfinance's `.financials` typically only returns the last ~4 years
    of annual data for smaller/newer tickers. For companies that IPO'd
    recently (LUNR, VOYG, SATL), you will likely need to supplement missing
    early years by hand from investor-relations filings — the function
    below will simply return fewer years for those tickers, so check
    len(data["years"]) after fetching.
    """
    t = yf.Ticker(ticker)

    # --- Price series ---
    hist = t.history(start=f"{start_year}-01-01", end=f"{end_year}-12-31")
    hist["year"] = hist.index.year
    year_end_price = hist.groupby("year")["Close"].last()

    # --- Revenue series ---
    fin = t.financials  # annual income statement, columns = fiscal year-end dates
    revenue_row = fin.loc["Total Revenue"] if "Total Revenue" in fin.index else None
    revenue_by_year = {}
    if revenue_row is not None:
        for col, val in revenue_row.items():
            revenue_by_year[col.year] = val

    years = sorted(set(year_end_price.index) & set(revenue_by_year.keys()))
    if not years:
        raise ValueError(
            f"No overlapping price + revenue years found for {ticker}. "
            f"Price years: {list(year_end_price.index)}, "
            f"Revenue years: {list(revenue_by_year.keys())}. "
            f"You likely need to supplement revenue data by hand for this ticker."
        )

    base_price = year_end_price[years[0]]
    base_revenue = revenue_by_year[years[0]]

    price_indexed = [year_end_price[y] / base_price * 100 for y in years]
    revenue_indexed = [revenue_by_year[y] / base_revenue * 100 for y in years]

    return {"years": years, "price": price_indexed, "revenue": revenue_indexed}


# ---------------------------------------------------------------------------
# 3. THE REUSABLE CHART
# ---------------------------------------------------------------------------

def build_narrative_gap_chart(
    ticker: str,
    years: list[int],
    revenue: list[float],
    price: list[float],
    narrative_cagr: float,
    start_year: int,
    bubble_band: tuple[int, int] | None = (2021, 2022),
) -> go.Figure:
    """
    Builds the three-line indexed chart:
      - dashed gray: narrative-implied trajectory
      - solid blue:  actual revenue
      - solid red:   actual stock price
    """
    narrative = index_series_from_cagr(narrative_cagr, len(years))

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=years, y=narrative, name="Narrative-implied",
        line=dict(color="#888780", dash="dash", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=years, y=revenue, name="Actual revenue",
        line=dict(color="#2a78d6", width=2), mode="lines+markers",
    ))
    fig.add_trace(go.Scatter(
        x=years, y=price, name="Stock price",
        line=dict(color="#e34948", width=2), mode="lines+markers",
    ))

    if bubble_band and bubble_band[0] in years and bubble_band[1] in years:
        fig.add_vrect(
            x0=bubble_band[0], x1=bubble_band[1],
            fillcolor="#e34948", opacity=0.08, line_width=0,
        )

    fig.update_layout(
        title=f"{ticker}: narrative vs. fundamentals vs. price (indexed to 100, {start_year})",
        yaxis_title=f"Index ({start_year} = 100)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=60, b=40),
    )
    return fig