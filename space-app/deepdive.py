"""Requirements-driven deep-dive view for a single space-economy company.

Answers the project thesis: have publicly traded space economy stocks
delivered returns commensurate with the growth narrative, or do they
remain speculative with no near-term path to profitability?
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import (
    BENCHMARKS,
    HISTORICAL_EVENTS,
    SPACE_COMPANIES,
    compute_cash_runway,
    latest_operating_margin,
    latest_revenue_growth,
    latest_value,
    load_company_fundamentals,
    load_full_price_history,
    peer_growth_margin,
)

# ---------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------
THEME = {
    "bg": "#151b28",
    "text": "#e9edf5",
    "grid": "#2a3345",
    "blue": "#8fbcff",
    "blue_fill": "rgba(143,188,255,0.12)",
    "red": "#ff7a72",
    "green": "#7ce38b",
    "amber": "#ffcf70",
    "muted": "#4a5568",
}

# Only these three benchmarks are offered in the Chart 1 toggle, per the
# dashboard requirements (BENCHMARKS in data.py has a couple of extras
# used elsewhere in the app).
CHART1_BENCHMARKS = {
    name: BENCHMARKS[name] for name in ("S&P 500", "Nasdaq Composite", "ARK Space ETF (ARKX)")
}


# ---------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------
def _format_currency(value: float | None, prefix: str = "$") -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if abs(value) >= 1e12:
        return f"{prefix}{value / 1e12:.1f}T"
    if abs(value) >= 1e9:
        return f"{prefix}{value / 1e9:.1f}B"
    if abs(value) >= 1e6:
        return f"{prefix}{value / 1e6:.1f}M"
    return f"{prefix}{value:,.0f}"


def _format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.1f}%"


def _format_runway(years: float | None, is_cash_generating: bool) -> str:
    if is_cash_generating:
        return "Cash Generating"
    if years is None or pd.isna(years):
        return "N/A"
    return f"{years:.1f} yrs"


def _kpi_color(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "white"
    return THEME["green"] if value >= 0 else THEME["red"]


# ---------------------------------------------------------------------
# Chart theming / event annotation helpers
# ---------------------------------------------------------------------
def _apply_dark_theme(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        title=title,
        template="plotly_dark",
        paper_bgcolor=THEME["bg"],
        plot_bgcolor=THEME["bg"],
        font=dict(color=THEME["text"]),
        margin=dict(t=70, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.1),
        xaxis=dict(gridcolor=THEME["grid"]),
        yaxis=dict(gridcolor=THEME["grid"]),
        hovermode="x unified",
    )
    return fig


def _add_event_shading(fig: go.Figure, x_min, x_max) -> go.Figure:
    """
    Shades COVID / SPAC boom / rate-rise sell-off regions on any chart
    whose date range overlaps 2020-2022, per the "Historical Event
    Markers" requirement. Skipped entirely for charts with no overlap
    (e.g. a company with data only from 2023 onward).
    """
    if x_min is None or x_max is None:
        return fig
    x_min, x_max = pd.Timestamp(x_min), pd.Timestamp(x_max)

    for event in HISTORICAL_EVENTS:
        ev_start, ev_end = pd.Timestamp(event["start"]), pd.Timestamp(event["end"])
        if ev_end < x_min or ev_start > x_max:
            continue
        clipped_start = max(ev_start, x_min)
        clipped_end = min(ev_end, x_max)
        fig.add_vrect(
            x0=clipped_start,
            x1=clipped_end,
            fillcolor=event["color"],
            opacity=0.10,
            line_width=0,
        )
        midpoint = clipped_start + (clipped_end - clipped_start) / 2
        fig.add_annotation(
            x=midpoint,
            y=1.02,
            yref="paper",
            xref="x",
            text=event["label"],
            showarrow=False,
            font=dict(size=10, color=THEME["text"]),
            textangle=0,
        )
    return fig


# ---------------------------------------------------------------------
# Chart 1 — Stock Performance
# ---------------------------------------------------------------------
def _build_stock_performance_chart(ticker: str, company_hist: pd.DataFrame) -> go.Figure:
    benchmark_name = st.radio(
        "Compare against",
        list(CHART1_BENCHMARKS.keys()),
        horizontal=True,
        key=f"{ticker}_benchmark",
    )
    benchmark_ticker = CHART1_BENCHMARKS[benchmark_name]

    try:
        benchmark_hist = load_full_price_history(benchmark_ticker)
    except Exception:
        benchmark_hist = pd.DataFrame(columns=["Close"])

    # Normalise both series to 100 at the later of the two start dates,
    # so the comparison is apples-to-apples (a benchmark like ARKX only
    # exists from 2021, well after most of these companies' IPOs).
    common_start = company_hist.index.min()
    if not benchmark_hist.empty:
        common_start = max(common_start, benchmark_hist.index.min())

    company_window = company_hist.loc[company_hist.index >= common_start]
    fig = go.Figure()

    if not company_window.empty:
        company_indexed = company_window["Close"] / company_window["Close"].iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=company_window.index, y=company_indexed, mode="lines", name=ticker,
            line=dict(color=THEME["blue"], width=3),
            fill="tozeroy", fillcolor=THEME["blue_fill"],
        ))

    if not benchmark_hist.empty:
        benchmark_window = benchmark_hist.loc[benchmark_hist.index >= common_start]
        if not benchmark_window.empty:
            benchmark_indexed = benchmark_window["Close"] / benchmark_window["Close"].iloc[0] * 100
            fig.add_trace(go.Scatter(
                x=benchmark_window.index, y=benchmark_indexed, mode="lines", name=benchmark_name,
                line=dict(color=THEME["amber"], width=2, dash="dot"),
            ))
    else:
        st.caption(f"Could not load benchmark data for {benchmark_name} ({benchmark_ticker}).")

    x_min = company_window.index.min() if not company_window.empty else None
    x_max = company_window.index.max() if not company_window.empty else None
    _add_event_shading(fig, x_min, x_max)

    _apply_dark_theme(fig, f"{ticker} vs. {benchmark_name}: indexed return (start = 100)")
    fig.update_layout(yaxis_title="Index (start = 100)", xaxis_title="Date")
    return fig


# ---------------------------------------------------------------------
# Chart 2 — Revenue Trend
# ---------------------------------------------------------------------
def _build_revenue_chart(ticker: str, revenue: dict[pd.Timestamp, float], is_quarterly: bool) -> go.Figure:
    periods = sorted(revenue)
    values = [revenue[p] for p in periods]

    yoy = []
    for idx, p in enumerate(periods):
        if idx == 0 or not revenue[periods[idx - 1]]:
            yoy.append(None)
        else:
            yoy.append((revenue[p] / revenue[periods[idx - 1]] - 1) * 100)

    customdata = [[g] for g in yoy]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=periods, y=values, name="Revenue",
        marker_color=THEME["blue"],
        customdata=customdata,
        hovertemplate="%{x|%b %Y}<br>Revenue: %{y:$,.0f}<br>YoY growth: %{customdata[0]:.1f}%<extra></extra>",
    ))
    _add_event_shading(fig, min(periods) if periods else None, max(periods) if periods else None)
    granularity = "Quarterly" if is_quarterly else "Annual"
    _apply_dark_theme(fig, f"{ticker}: revenue trend ({granularity})")
    fig.update_layout(yaxis_title="Revenue ($)", xaxis_title="Period", showlegend=False)
    return fig


# ---------------------------------------------------------------------
# Chart 3 — Operating Margin Trend
# ---------------------------------------------------------------------
def _build_operating_margin_chart(ticker: str, operating_margin: dict[pd.Timestamp, float]) -> go.Figure:
    periods = sorted(operating_margin)
    values = [operating_margin[p] for p in periods]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=periods, y=values, mode="lines+markers", name="Operating margin",
        line=dict(color=THEME["red"], width=3),
        marker=dict(color=THEME["red"], size=7),
        hovertemplate="%{x|%b %Y}<br>Operating margin: %{y:.1f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=THEME["muted"])
    _add_event_shading(fig, min(periods) if periods else None, max(periods) if periods else None)
    _apply_dark_theme(fig, f"{ticker}: operating margin trend")
    fig.update_layout(yaxis_title="Operating margin (%)", xaxis_title="Period", showlegend=False)
    return fig


# ---------------------------------------------------------------------
# Chart 4 — Cash Balance vs. Cash Burn
# ---------------------------------------------------------------------
def _build_cash_chart(
    ticker: str,
    cash_balance: dict[pd.Timestamp, float],
    free_cash_flow: dict[pd.Timestamp, float],
    runway_years: float | None,
    is_cash_generating: bool,
) -> go.Figure:
    """
    Single-axis cash balance line. Each actual data point is colored by
    that period's burn state (red = burning cash, green = cash
    generating, gray = burn data unavailable for that period) so the
    per-period detail survives without a second y-axis. If the company
    is burning cash, a shaded, dashed projection extends the line to
    where it would hit zero at the current burn rate.
    """
    periods = sorted(cash_balance)
    values = [cash_balance[p] for p in periods]

    def burn_color(period: pd.Timestamp) -> str:
        fcf = free_cash_flow.get(period)
        if fcf is None:
            return THEME["muted"]
        return THEME["green"] if fcf >= 0 else THEME["red"]

    def burn_label(period: pd.Timestamp) -> str:
        fcf = free_cash_flow.get(period)
        if fcf is None:
            return "burn data unavailable"
        return "cash generating" if fcf >= 0 else "burning cash"

    point_colors = [burn_color(p) for p in periods]
    customdata = [[burn_label(p)] for p in periods]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=periods, y=values, mode="lines+markers", name="Cash balance",
        line=dict(color=THEME["blue"], width=2),
        marker=dict(color=point_colors, size=10, line=dict(width=1, color=THEME["bg"])),
        customdata=customdata,
        hovertemplate="%{x|%b %Y}<br>Cash balance: %{y:$,.0f}<br>%{customdata[0]}<extra></extra>",
    ))

    if periods and not is_cash_generating and runway_years:
        last_period, last_value = periods[-1], values[-1]
        # Cap the projected horizon so a very long runway doesn't stretch
        # the x-axis absurdly; note in the label when we've capped it.
        span_years = max((periods[-1] - periods[0]).days / 365.25, 1)
        display_years = min(runway_years, span_years * 1.5, 8)
        capped = display_years < runway_years
        projected_date = last_period + pd.DateOffset(days=int(display_years * 365.25))
        projected_value = 0 if not capped else last_value * (1 - display_years / runway_years)

        fig.add_trace(go.Scatter(
            x=[last_period, projected_date], y=[last_value, projected_value],
            mode="lines", name="Projected runway",
            line=dict(color=THEME["blue"], width=2, dash="dot"),
            fill="tozeroy", fillcolor=THEME["blue_fill"],
            hoverinfo="skip",
        ))
        label = (
            f"Runway exceeds {display_years:.0f} yrs (chart capped)"
            if capped else f"Projected cash-out: ~{runway_years:.1f} yrs"
        )
        fig.add_annotation(
            x=projected_date, y=projected_value,
            text=label, showarrow=True, arrowhead=2, ax=0, ay=-30,
            font=dict(size=10, color=THEME["text"]),
        )

    fig.add_hline(y=0, line_dash="dash", line_color=THEME["muted"])
    _add_event_shading(fig, periods[0] if periods else None, periods[-1] if periods else None)
    _apply_dark_theme(fig, f"{ticker}: cash balance and runway")
    fig.update_layout(xaxis_title="Period", yaxis_title="Cash balance ($)", showlegend=False)
    return fig


# ---------------------------------------------------------------------
# Chart 5 — Peer Comparison
# ---------------------------------------------------------------------
def _axis_bounds(values: list[float], pad_frac: float = 0.20) -> tuple[float, float]:
    """
    Robust axis bounds using Tukey's IQR fences, so one or two extreme
    outliers (e.g. a company whose revenue growth is +2000% off a tiny
    base) don't compress the rest of the peer set into a corner. Points
    outside these bounds get pulled to the edge by _clip_point below.
    """
    series = pd.Series([v for v in values if v is not None])
    if len(series) < 4:
        lo, hi = float(series.min()), float(series.max())
        pad = (hi - lo) * pad_frac or 10
        return lo - pad, hi + pad

    q1, q3 = series.quantile([0.25, 0.75])
    iqr = (q3 - q1) or (series.max() - series.min()) or 10
    fence_lo, fence_hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    lo = max(fence_lo, series.min())
    hi = min(fence_hi, series.max())
    pad = (hi - lo) * pad_frac or 10
    return lo - pad, hi + pad


def _clip_point(x, y, x_bounds, y_bounds, inset_frac: float = 0.12):
    """
    Pulls an out-of-range point to just inside the axis edge (rather than
    exactly on it, so its marker isn't cut off) and returns the display
    coordinates plus a directional triangle marker symbol indicating
    which way the true value lies off-chart.
    """
    x_lo, x_hi = x_bounds
    y_lo, y_hi = y_bounds
    x_pad, y_pad = (x_hi - x_lo) * inset_frac, (y_hi - y_lo) * inset_frac

    dx = 1 if x > x_hi else (-1 if x < x_lo else 0)
    dy = 1 if y > y_hi else (-1 if y < y_lo else 0)

    disp_x = (x_hi - x_pad) if dx == 1 else (x_lo + x_pad) if dx == -1 else x
    disp_y = (y_hi - y_pad) if dy == 1 else (y_lo + y_pad) if dy == -1 else y

    symbol_map = {
        (0, 0): "circle",
        (1, 0): "triangle-right", (-1, 0): "triangle-left",
        (0, 1): "triangle-up", (0, -1): "triangle-down",
        (1, 1): "triangle-ne", (1, -1): "triangle-se",
        (-1, 1): "triangle-nw", (-1, -1): "triangle-sw",
    }
    return disp_x, disp_y, symbol_map[(dx, dy)], bool(dx or dy)


def _peer_trace(rows: list[dict], x_bounds, y_bounds, *, muted: bool) -> go.Scatter:
    disp_x, disp_y, symbols, texts, customdata = [], [], [], [], []
    for r in rows:
        dx, dy, symbol, clipped = _clip_point(r["growth"], r["margin"], x_bounds, y_bounds)
        disp_x.append(dx)
        disp_y.append(dy)
        symbols.append(symbol)
        texts.append(r["ticker"])
        customdata.append([r["name"], r["category"], r["growth"], r["margin"], "yes" if clipped else "no"])

    color = THEME["muted"] if muted else THEME["blue"]
    size = 12 if muted else 18
    return go.Scatter(
        x=disp_x, y=disp_y,
        mode="markers+text",
        text=texts,
        textposition="top center",
        textfont=dict(size=10 if muted else 12, color=color if muted else THEME["blue"]),
        marker=dict(
            size=size, color=color, opacity=0.6 if muted else 1.0,
            symbol=symbols, line=dict(width=0 if muted else 2, color="white"),
        ),
        customdata=customdata,
        hovertemplate=(
            "%{customdata[0]} (%{customdata[1]})"
            "<br>Revenue growth: %{customdata[2]:.1f}%"
            "<br>Operating margin: %{customdata[3]:.1f}%"
            "<br>Off-scale, pulled to edge: %{customdata[4]}"
            "<extra></extra>"
        ),
    )


def _build_peer_comparison_chart(selected_ticker: str) -> go.Figure:
    rows = []
    for ticker, meta in SPACE_COMPANIES.items():
        try:
            growth, margin = peer_growth_margin(ticker)
        except Exception:
            growth, margin = None, None
        if growth is None or margin is None:
            continue
        rows.append({
            "ticker": ticker,
            "name": meta["name"],
            "category": meta["category"],
            "growth": growth,
            "margin": margin,
        })

    fig = go.Figure()
    if not rows:
        _apply_dark_theme(fig, "Growth vs. operating margin — peer comparison")
        return fig

    x_bounds = _axis_bounds([r["growth"] for r in rows])
    y_bounds = _axis_bounds([r["margin"] for r in rows])

    others = [r for r in rows if r["ticker"] != selected_ticker]
    selected = [r for r in rows if r["ticker"] == selected_ticker]

    if others:
        fig.add_trace(_peer_trace(others, x_bounds, y_bounds, muted=True))
    if selected:
        fig.add_trace(_peer_trace(selected, x_bounds, y_bounds, muted=False))

    fig.add_hline(y=0, line_dash="dash", line_color=THEME["grid"])
    fig.add_vline(x=0, line_dash="dash", line_color=THEME["grid"])
    _apply_dark_theme(fig, "Growth vs. operating margin — peer comparison")
    fig.update_layout(
        xaxis=dict(title="Revenue growth (%, latest period)", range=x_bounds, gridcolor=THEME["grid"]),
        yaxis=dict(title="Operating margin (%, latest period)", range=y_bounds, gridcolor=THEME["grid"]),
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------
def render_deep_dive(stock: dict):
    """Render the evidence-driven deep-dive screen for a company."""
    if st.button("← Back to orbital map"):
        st.session_state.selected_ticker = None
        st.rerun()

    ticker = stock["ticker"]

    try:
        hist = load_full_price_history(ticker)
    except Exception as exc:
        st.warning(f"Could not fetch price history for {ticker}: {exc}")
        hist = pd.DataFrame(columns=["Close"])

    try:
        fundamentals = load_company_fundamentals(ticker)
    except Exception as exc:
        st.warning(f"Could not fetch fundamentals for {ticker}: {exc}")
        fundamentals = {
            "info": {}, "revenue": {}, "operating_income": {}, "operating_margin": {},
            "net_income": {}, "cash_balance": {}, "free_cash_flow": {},
            "is_quarterly": False, "cash_is_quarterly": False, "currency": "USD",
        }

    info = fundamentals["info"]
    revenue = fundamentals["revenue"]
    operating_margin = fundamentals["operating_margin"]
    net_income = fundamentals["net_income"]
    cash_balance = fundamentals["cash_balance"]
    free_cash_flow = fundamentals["free_cash_flow"]
    is_quarterly = fundamentals["is_quarterly"]

    company_meta = SPACE_COMPANIES.get(ticker, {})
    category = company_meta.get("category", "Space Economy")

    st.title(f"{ticker} — {stock.get('name', company_meta.get('name', ticker))}")
    st.caption(f"{category} · IPO {stock.get('ipo_date', 'unknown')}")

    # ---- KPIs ----
    market_cap = info.get("marketCap") or stock.get("market_cap")
    revenue_growth = latest_revenue_growth(revenue)
    op_margin_latest = latest_operating_margin(operating_margin)
    net_income_latest = latest_value(net_income)
    cash_latest = latest_value(cash_balance)
    fcf_latest = latest_value(free_cash_flow)
    runway_years, is_cash_generating = compute_cash_runway(cash_latest, fcf_latest, is_quarterly)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.html(f"""
        <div>
        <div style="font-size:0.9rem;">Market cap</div>
        <div style="font-size:2.2rem;font-weight:600;color:white">{_format_currency(market_cap)}</div>
        </div>
        """)
    c2.html(f"""
        <div>
        <div style="font-size:0.9rem;">Revenue growth</div>
        <div style="font-size:2.2rem;font-weight:600;color:{_kpi_color(revenue_growth)}">{_format_pct(revenue_growth)}</div>
        </div>
        """)
    c3.html(f"""
        <div>
        <div style="font-size:0.9rem;">Operating margin</div>
        <div style="font-size:2.2rem;font-weight:600;color:{_kpi_color(op_margin_latest)}">{_format_pct(op_margin_latest)}</div>
        </div>
        """)
    c4.html(f"""
        <div>
        <div style="font-size:0.9rem;">Net income</div>
        <div style="font-size:2.2rem;font-weight:600;color:{_kpi_color(net_income_latest)}">{_format_currency(net_income_latest)}</div>
        </div>
        """)
    c5.html(f"""
        <div>
        <div style="font-size:0.9rem;">Cash runway</div>
        <div style="font-size:2.2rem;font-weight:600;color:white">{_format_runway(runway_years, is_cash_generating)}</div>
        </div>
        """)

    st.divider()

    # ---- Chart 1: Stock Performance ----
    st.subheader("Stock performance")
    st.caption("Have investors actually been rewarded?")
    if hist.empty:
        st.info("No price history available for this ticker.")
    else:
        st.plotly_chart(_build_stock_performance_chart(ticker, hist), width='stretch')

    st.divider()

    # ---- Chart 2: Revenue Trend ----
    st.subheader("Revenue trend")
    st.caption("Is the business actually growing?")
    if not revenue:
        st.info("Revenue data is not available for this ticker.")
    else:
        st.plotly_chart(_build_revenue_chart(ticker, revenue, is_quarterly), width='stretch')

    st.divider()

    # ---- Chart 3: Operating Margin Trend ----
    st.subheader("Operating margin trend")
    st.caption("Is the company becoming more profitable?")
    if not operating_margin:
        st.info("Not enough aligned revenue and operating income data to chart margin trend.")
    else:
        st.plotly_chart(_build_operating_margin_chart(ticker, operating_margin), width='stretch')

    st.divider()

    # ---- Chart 4: Cash Balance vs. Cash Burn ----
    st.subheader("Cash balance and runway")
    st.caption("Can the company sustain operations without raising more capital?")
    if not cash_balance:
        st.info("Cash balance data is not available for this ticker.")
    else:
        st.plotly_chart(
            _build_cash_chart(ticker, cash_balance, free_cash_flow, runway_years, is_cash_generating),
            width='stretch',
        )
        st.caption(
            "🔴 burning cash that period · 🟢 cash generating that period · "
            "shaded region = projected time to cash-out at the current burn rate."
        )

    st.divider()

    # ---- Chart 5: Peer Comparison ----
    st.subheader("Growth vs. valuation — peer comparison")
    st.caption("How does this company compare with its peers?")
    st.plotly_chart(_build_peer_comparison_chart(ticker), width='stretch')
    st.caption(
        "Axis range is set to where most peers cluster. Companies with extreme "
        "growth or margin swings are pulled to the edge as a ▲ arrow pointing "
        "toward their true value — hover over any point for the exact numbers."
    )