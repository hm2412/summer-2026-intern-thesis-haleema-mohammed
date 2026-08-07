"""
data.py — Data loading for the Space Economy Streamlit app.

Contains:
- Company metadata
- Benchmark metadata
- Cached Yahoo Finance downloads
- Common financial calculations
"""

import pandas as pd
import streamlit as st
import yfinance as yf

# ---------------------------------------------------------------------
# Space Companies
# ---------------------------------------------------------------------
# Keyed by ticker so per-company metadata (name, category) lives in one
# place. If other views still key off company name, use
# SPACE_COMPANY_TICKERS below rather than re-hardcoding a ticker set.
SPACE_COMPANIES = {
    "RKLB": {"name": "Rocket Lab", "category": "Commercial Launch"},
    "LUNR": {"name": "Intuitive Machines", "category": "Lunar Exploration"},
    "ASTS": {"name": "AST SpaceMobile", "category": "Satellite Communications"},
    "PL": {"name": "Planet Labs", "category": "Earth Observation"},
    "BKSY": {"name": "BlackSky", "category": "Earth Observation"},
    "RDW": {"name": "Redwire", "category": "Space Infrastructure"},
    "IRDM": {"name": "Iridium Communications", "category": "Satellite Communications"},
    "SPCE": {"name": "Virgin Galactic", "category": "Space Tourism"},
    "LMT": {"name": "Lockheed Martin", "category": "Aerospace & Defence"},
    "LHX": {"name": "L3Harris Technologies", "category": "Aerospace & Defence"},
    "SIDU": {"name": "Sidus Space", "category": "Space Infrastructure"},
}

# Backwards-compatible name -> ticker mapping, in case other modules
# (e.g. the orbital map view) still key off company name.
SPACE_COMPANY_TICKERS = {meta["name"]: ticker for ticker, meta in SPACE_COMPANIES.items()}

# ---------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------
BENCHMARKS = {
    "S&P 500": "SPY",
    "Nasdaq Composite": "QQQ",
    "Procure Space ETF (UFO)": "UFO",
    "ARK Innovation ETF (ARKK)": "ARKK", #skibidi
    "iShares U.S. Aerospace & Defense ETF (ITA)": "ITA",
}

# ---------------------------------------------------------------------
# Combined Lists
# ---------------------------------------------------------------------
SPACE_TICKERS = list(SPACE_COMPANIES.keys())
BENCHMARK_TICKERS = list(BENCHMARKS.values())
ALL_TICKERS = SPACE_TICKERS + BENCHMARK_TICKERS

# ---------------------------------------------------------------------
# Data Range
# ---------------------------------------------------------------------
# Earliest IPO in the selected companies is Iridium (1997).
# Using 2015 captures the modern commercial space era while keeping
# download sizes reasonable.
START_DATE = "2015-01-01"
# Consider replacing with datetime.today() in production.
END_DATE = "2026-08-01"

# ---------------------------------------------------------------------
# Historical market events (space-economy relevant)
# ---------------------------------------------------------------------
# Fixed, publicly known date ranges — not sourced from yfinance. Used to
# annotate charts that cover 2020-2022.
HISTORICAL_EVENTS = [
    {
        "label": "COVID market disruption",
        "start": "2020-02-15",
        "end": "2020-12-31",
        "color": "#ff7a72",
    },
    {
        "label": "SPAC boom",
        "start": "2020-01-01",
        "end": "2021-12-31",
        "color": "#ffcf70",
    },
    {
        "label": "Growth-stock sell-off / rate rises",
        "start": "2022-01-01",
        "end": "2022-12-31",
        "color": "#ff7a72",
    },
]

# ---------------------------------------------------------------------
# Price Data (multi-ticker, fixed window — used by other views)
# ---------------------------------------------------------------------
@st.cache_data(ttl=60 * 60 * 12, show_spinner="Downloading market data...")
def load_price_data(
    tickers: list[str],
    start: str = START_DATE,
    end: str = END_DATE,
) -> pd.DataFrame:
    """
    Downloads adjusted daily close prices.

    Returns
    -------
    DataFrame
    Rows:
        Trading dates
    Columns:
        Ticker symbols
    """
    raw = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
    )
    prices = raw["Close"]
    return prices.dropna(axis=1, how="all")


# ---------------------------------------------------------------------
# Daily Returns
# ---------------------------------------------------------------------
@st.cache_data
def compute_daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Computes daily percentage returns.
    """
    return prices.pct_change().dropna(how="all")


# ---------------------------------------------------------------------
# Full single-ticker price history (IPO / listing to present)
# ---------------------------------------------------------------------
@st.cache_data(ttl=60 * 60, show_spinner=False)
def load_full_price_history(ticker: str) -> pd.DataFrame:
    """
    Downloads the full available daily close history for a single ticker,
    unconstrained by START_DATE. Used for the deep-dive view, where the
    requirement is "IPO to present" rather than a fixed analysis window.
    """
    hist = yf.Ticker(ticker).history(period="max", auto_adjust=True)
    hist = hist[["Close"]].dropna().copy()
    hist.index = pd.to_datetime(hist.index)
    if getattr(hist.index, "tz", None) is not None:
        hist.index = hist.index.tz_convert(None)
    return hist.sort_index()


# ---------------------------------------------------------------------
# Annual revenue only (for multi-year growth calculations)
# ---------------------------------------------------------------------
@st.cache_data(ttl=60 * 60, show_spinner=False)
def load_annual_revenue(ticker: str) -> dict[pd.Timestamp, float]:
    """
    Annual revenue only — deliberately does NOT fall back to quarterly
    data the way load_company_fundamentals() does for margins. A 3-year
    CAGR needs true multi-year annual figures; a handful of recent
    quarters would understate/overstate growth in a misleading way.
    Recently-listed companies without ~3 years of annual filings will
    simply return too few periods for compute_revenue_cagr() to use.
    """
    company = yf.Ticker(ticker)
    return _extract_row(company.financials, ["Total Revenue", "Operating Revenue"])


# ---------------------------------------------------------------------
# Company fundamentals (income statement / cash flow / balance sheet)
# ---------------------------------------------------------------------
def _extract_row(statement: pd.DataFrame | None, row_names: list[str]) -> dict[pd.Timestamp, float]:
    """
    Pulls a row from a yfinance financial statement DataFrame, trying each
    candidate row name in turn (yfinance's exact labels vary by ticker and
    library version). Returns {period_end_timestamp: value}.
    """
    if statement is None or statement.empty:
        return {}
    for row_name in row_names:
        if row_name in statement.index:
            series = statement.loc[row_name]
            values: dict[pd.Timestamp, float] = {}
            for idx, val in series.items():
                if pd.isna(val):
                    continue
                values[pd.Timestamp(idx)] = float(val)
            if values:
                return values
    return {}


@st.cache_data(ttl=60 * 60, show_spinner=False)
def load_company_fundamentals(ticker: str) -> dict:
    """
    Fetches income statement, cash flow, and balance sheet data for a
    single company via yfinance and derives the series the deep-dive
    dashboard needs: revenue, operating income / margin, net income,
    cash balance, and free cash flow (used as the cash-burn proxy).

    Falls back from annual to quarterly statements where annual data is
    unavailable (common for recently-listed companies).

    Returns a dict of {period_end_timestamp: value} series, plus the
    raw `info` blob and an `is_quarterly` flag describing which
    granularity was used for revenue/margins.
    """
    company = yf.Ticker(ticker)
    info = company.get_info() or {}

    financials = company.financials
    quarterly_financials = company.quarterly_financials
    cashflow = company.cashflow
    quarterly_cashflow = company.quarterly_cashflow
    balance_sheet = company.balance_sheet
    quarterly_balance_sheet = company.quarterly_balance_sheet

    revenue = _extract_row(financials, ["Total Revenue", "Operating Revenue"])
    is_quarterly = False
    if not revenue:
        revenue = _extract_row(quarterly_financials, ["Total Revenue", "Operating Revenue"])
        is_quarterly = True

    operating_income = _extract_row(
        financials if not is_quarterly else quarterly_financials,
        ["Operating Income", "Operating Income Loss", "EBIT"],
    )

    net_income = _extract_row(
        financials if not is_quarterly else quarterly_financials,
        ["Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations"],
    )

    cash_balance = _extract_row(
        balance_sheet,
        ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash Financial"],
    )
    cash_is_quarterly = False
    if not cash_balance:
        cash_balance = _extract_row(
            quarterly_balance_sheet,
            ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash Financial"],
        )
        cash_is_quarterly = True

    free_cash_flow = _extract_row(
        cashflow if not is_quarterly else quarterly_cashflow,
        ["Free Cash Flow"],
    )
    if not free_cash_flow:
        # Derive FCF = Operating Cash Flow - CapEx if it isn't reported directly.
        op_cf = _extract_row(
            financials if not is_quarterly else quarterly_financials,
            ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
        )
        capex = _extract_row(
            financials if not is_quarterly else quarterly_financials,
            ["Capital Expenditure", "Purchase Of PPE"],
        )
        if op_cf and capex:
            free_cash_flow = {
                period: op_cf[period] + capex.get(period, 0.0)  # capex is typically negative
                for period in op_cf
            }

    operating_margin = {}
    for period in sorted(set(revenue) & set(operating_income)):
        if revenue[period]:
            operating_margin[period] = operating_income[period] / revenue[period] * 100

    return {
        "info": info,
        "revenue": revenue,
        "operating_income": operating_income,
        "operating_margin": operating_margin,
        "net_income": net_income,
        "cash_balance": cash_balance,
        "free_cash_flow": free_cash_flow,
        "is_quarterly": is_quarterly,
        "cash_is_quarterly": cash_is_quarterly,
        "currency": info.get("financialCurrency") or info.get("currency") or "USD",
    }


# ---------------------------------------------------------------------
# Common financial calculations
# ---------------------------------------------------------------------
def latest_revenue_growth(revenue: dict[pd.Timestamp, float]) -> float | None:
    """Period-over-period growth (%) between the two most recent periods."""
    if len(revenue) < 2:
        return None
    periods = sorted(revenue)
    prev, curr = periods[-2], periods[-1]
    if not revenue[prev]:
        return None
    return (revenue[curr] / revenue[prev] - 1) * 100


def latest_operating_margin(operating_margin: dict[pd.Timestamp, float]) -> float | None:
    if not operating_margin:
        return None
    return operating_margin[max(operating_margin)]


def latest_value(series: dict[pd.Timestamp, float]) -> float | None:
    if not series:
        return None
    return series[max(series)]


def compute_cash_runway(
    cash_balance: float | None,
    free_cash_flow: float | None,
    is_quarterly: bool = False,
) -> tuple[float | None, bool | None]:
    """
    Returns (years_remaining, is_cash_generating).

    is_cash_generating is a genuine tri-state:
      - True  -> free cash flow is positive; no runway to report
      - False -> free cash flow is negative; years_remaining holds the runway
      - None  -> cash balance or free cash flow data is unavailable, so
                 cash-generating status itself is unknown — this is NOT
                 the same as "burning cash" and callers aggregating this
                 field (e.g. "N of M companies are cash-generating")
                 must exclude None from both the numerator and
                 denominator rather than counting it as False.
    """
    if cash_balance is None or free_cash_flow is None:
        return None, None
    annual_fcf = free_cash_flow * 4 if is_quarterly else free_cash_flow
    if annual_fcf >= 0:
        return None, True
    years = cash_balance / abs(annual_fcf)
    return years, False


def compute_revenue_cagr(revenue: dict[pd.Timestamp, float], years: int = 3) -> float | None:
    """
    Annualised revenue growth rate (%) over the requested window, using
    the earliest annual period that is at least `years` back from the
    latest one (falls back to the earliest period available if the
    company doesn't have that much history).

    Returns None — rather than a number computed from a shorter window —
    if the two periods used don't actually span close to the requested
    window. The bar scales with `years` (roughly `years - 0.5`, floored
    at 0.75) so a 1-year request isn't held to the same 2.5-year bar as
    the 3-year default; a recently-listed company still won't get a
    mislabeled "5-year" growth rate built from one or two annual reports.
    """
    if len(revenue) < 2:
        return None
    periods = sorted(revenue)
    latest_period = periods[-1]
    target_date = latest_period - pd.DateOffset(years=years)
    earlier_candidates = [p for p in periods if p <= target_date]
    start_period = max(earlier_candidates) if earlier_candidates else periods[0]

    span_years = (latest_period - start_period).days / 365.25
    min_span = max(years - 0.5, 0.75)
    if span_years < min_span:
        return None

    start_val = revenue[start_period]
    end_val = revenue[latest_period]
    if not start_val or start_val <= 0:
        return None
    return ((end_val / start_val) ** (1 / span_years) - 1) * 100


def compute_total_shareholder_return(price_history: pd.DataFrame, years: int = 3) -> float | None:
    """
    3-year total return (%) from a single-ticker price history DataFrame
    as returned by load_full_price_history() (a "Close" column, indexed
    by date). Because load_full_price_history() downloads with
    auto_adjust=True, this "Close" is already dividend- and
    split-adjusted, so the result approximates total shareholder return
    (price return + reinvested dividends), not just price return.

    Returns None if the ticker doesn't have ~3 years of trading history
    yet (e.g. a recent IPO) rather than computing a shorter-window
    number and mislabeling it.
    """
    if price_history is None or price_history.empty or "Close" not in price_history.columns:
        return None
    idx = price_history.index
    latest_date = idx.max()
    target_date = latest_date - pd.DateOffset(years=years)
    if idx.min() > target_date:
        return None

    eligible = price_history.loc[price_history.index >= target_date]
    if eligible.empty:
        return None
    start_price = eligible["Close"].iloc[0]
    end_price = price_history["Close"].iloc[-1]
    if not start_price:
        return None
    return (end_price / start_price - 1) * 100


def peer_growth_margin(ticker: str) -> tuple[float | None, float | None]:
    """
    Convenience wrapper for the peer-comparison scatter: latest revenue
    growth (%) and latest operating margin (%) for a given ticker.
    """
    fundamentals = load_company_fundamentals(ticker)
    growth = latest_revenue_growth(fundamentals["revenue"])
    margin = latest_operating_margin(fundamentals["operating_margin"])
    return growth, margin