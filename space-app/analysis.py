"""
analysis.py — Pure computation functions (stats only).

No Streamlit calls, no plotting. Everything here is testable in isolation and
mirrors the logic already validated in space_economy_analysis.ipynb.
"""
import numpy as np
import pandas as pd
from scipy import stats


def compute_correlation_matrix(returns: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Square correlation matrix for a set of tickers against each other."""
    return returns[tickers].corr().round(2)


def compute_cross_correlation(
    returns: pd.DataFrame, row_tickers: list[str], col_tickers: list[str]
) -> pd.DataFrame:
    """
    Correlation of each row_ticker against each col_ticker only —
    e.g. space stocks (rows) vs benchmarks (columns) — rather than a full
    square matrix that also includes stock-vs-stock and benchmark-vs-benchmark.
    """
    cross_corr = pd.DataFrame(index=row_tickers, columns=col_tickers, dtype=float)
    for row in row_tickers:
        for col in col_tickers:
            cross_corr.loc[row, col] = returns[row].corr(returns[col])
    return cross_corr.round(2)


def compute_beta_and_r2(returns: pd.DataFrame, ticker: str, benchmark: str = "SPY") -> dict:
    """Single-ticker OLS regression vs a benchmark."""
    df = returns[[ticker, benchmark]].dropna()
    slope, intercept, r_value, p_value, std_err = stats.linregress(df[benchmark], df[ticker])
    return {
        "ticker": ticker,
        "beta": round(slope, 3),
        "r_squared": round(r_value ** 2, 3),
        "p_value": round(p_value, 5),
        "n_observations": len(df),
        "intercept": intercept,  # kept unrounded for accurate regression-line plotting
    }


def compute_beta_table(returns: pd.DataFrame, tickers: list[str], benchmark: str = "SPY") -> pd.DataFrame:
    rows = [compute_beta_and_r2(returns, t, benchmark) for t in tickers if t in returns.columns]
    table = pd.DataFrame(rows).set_index("ticker")
    return table.drop(columns=["intercept"])  # intercept is plotting-only, not for display


def compute_volatility_and_drawdown(prices: pd.DataFrame, returns: pd.DataFrame, ticker: str) -> dict:
    daily_std = returns[ticker].std()
    annualised_vol = daily_std * np.sqrt(252)

    price_series = prices[ticker].dropna()
    running_max = price_series.cummax()
    drawdown_series = (price_series - running_max) / running_max
    max_drawdown = drawdown_series.min()

    return {
        "ticker": ticker,
        "annualised_volatility_pct": round(annualised_vol * 100, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
    }


def compute_vol_table(prices: pd.DataFrame, returns: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    seen, deduped = set(), []
    for t in tickers:
        if t not in seen and t in returns.columns:
            seen.add(t)
            deduped.append(t)
    rows = [compute_volatility_and_drawdown(prices, returns, t) for t in deduped]
    return pd.DataFrame(rows).set_index("ticker")


def compute_cumulative_returns(prices: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Indexed to 100 at the start of the (already date-filtered) price frame."""
    subset = prices[tickers].dropna()
    return subset / subset.iloc[0] * 100


def compute_rolling_volatility(returns: pd.DataFrame, tickers: list[str], window: int = 30) -> pd.DataFrame:
    """Rolling annualised volatility (%) per ticker."""
    cols = {ticker: returns[ticker].rolling(window).std() * np.sqrt(252) * 100 for ticker in tickers}
    return pd.DataFrame(cols)