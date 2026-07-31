"""
Space economy — animated orbital map.

Implements the visualization spec from orbital-map-requirements.md:
  - planet size      = market cap (sqrt scale, clamped)
  - orbit ring        = years to consensus profitability (3 discrete rings)
  - orbit speed        = total return since IPO relative to a growth-narrative
                         benchmark. All planets orbit the same direction
                         (clockwise); FAST = beating the narrative, SLOW =
                         lagging it. A stroke color (green/red) reinforces
                         ahead/behind so the signal is readable even before
                         the difference in speed is obvious.

Built as a self-contained HTML/SVG/JS component rendered via
`streamlit.components.v1.html`, per the requirement that this NOT be animated
through native Streamlit reruns (too choppy) or Plotly frames (same problem).
No external JS libraries are used, so it has no extra dependencies beyond
Streamlit itself.

Run with:  streamlit run orbital_map.py
"""

import json

import streamlit as st

# --------------------------------------------------------------------------
# Sample data — matches the data model in orbital-map-requirements.md.
# Replace this with your real, computed dataset (market cap, return since
# IPO, benchmark return, years to profitability, etc.) once that pipeline
# is built. Numbers below are illustrative placeholders, not live figures.
# --------------------------------------------------------------------------

SAMPLE_STOCKS = [
    {
        "ticker": "IRDM", "name": "Iridium Communications",
        "market_cap": 4.2e9, "years_to_profitability": None,
        "is_profitable_now": True, "return_since_ipo_pct": 45,
        "benchmark_return_pct": 60, "tier": "mature", "ipo_date": "2009-02-01",
    },
    {
        "ticker": "LMT", "name": "Lockheed Martin",
        "market_cap": 110e9, "years_to_profitability": None,
        "is_profitable_now": True, "return_since_ipo_pct": 180,
        "benchmark_return_pct": 60, "tier": "mature", "ipo_date": "1995-03-01",
    },
    {
        "ticker": "RKLB", "name": "Rocket Lab",
        "market_cap": 14e9, "years_to_profitability": 1.5,
        "is_profitable_now": False, "return_since_ipo_pct": 210,
        "benchmark_return_pct": 90, "tier": "scaling", "ipo_date": "2021-08-25",
    },
    {
        "ticker": "LUNR", "name": "Intuitive Machines",
        "market_cap": 1.1e9, "years_to_profitability": 2,
        "is_profitable_now": False, "return_since_ipo_pct": -35,
        "benchmark_return_pct": 90, "tier": "scaling", "ipo_date": "2023-02-13",
    },
    {
        "ticker": "PL", "name": "Planet Labs",
        "market_cap": 2.6e9, "years_to_profitability": 1,
        "is_profitable_now": False, "return_since_ipo_pct": 15,
        "benchmark_return_pct": 90, "tier": "scaling", "ipo_date": "2021-12-08",
    },
    {
        "ticker": "ASTS", "name": "AST SpaceMobile",
        "market_cap": 9.5e9, "years_to_profitability": 4,
        "is_profitable_now": False, "return_since_ipo_pct": 650,
        "benchmark_return_pct": 90, "tier": "speculative", "ipo_date": "2021-04-06",
    },
    {
        "ticker": "RDW", "name": "Redwire",
        "market_cap": 1.3e9, "years_to_profitability": None,
        "is_profitable_now": False, "return_since_ipo_pct": -60,
        "benchmark_return_pct": 90, "tier": "speculative", "ipo_date": "2021-09-02",
    },
    {
        "ticker": "SPCE", "name": "Virgin Galactic",
        "market_cap": 0.3e9, "years_to_profitability": None,
        "is_profitable_now": False, "return_since_ipo_pct": -97,
        "benchmark_return_pct": 90, "tier": "speculative", "ipo_date": "2019-10-28",
    },
    {
        "ticker": "BKSY", "name": "BlackSky",
        "market_cap": 0.6e9, "years_to_profitability": None,
        "is_profitable_now": False, "return_since_ipo_pct": -55,
        "benchmark_return_pct": 90, "tier": "speculative", "ipo_date": "2021-09-09",
    },
]


def _compute_ring(years_to_profitability, is_profitable_now):
    """Map profitability data onto one of three discrete rings (0=inner)."""
    if is_profitable_now:
        return 0
    if years_to_profitability is None:
        return 2  # no analyst consensus -> outer "unknown" ring, by design
    if years_to_profitability <= 3:
        return 1
    return 2


def _prepare_data(stocks):
    prepared = []
    for s in stocks:
        relative_return = s["return_since_ipo_pct"] - s["benchmark_return_pct"]
        prepared.append({
            **s,
            "ring": _compute_ring(s.get("years_to_profitability"), s.get("is_profitable_now", False)),
            "relative_return_pct": relative_return,
        })
    return prepared


_HTML_TEMPLATE = """
<div id="orbital-root" style="position:relative;width:100%;height:__HEIGHT__px;
     background:#0b0d14;border-radius:12px;overflow:hidden;
     font-family:-apple-system,Segoe UI,Roboto,sans-serif;">
  <svg id="orbital-svg" width="100%" height="100%" viewBox="0 0 1400 850"
       preserveAspectRatio="xMidYMid meet"></svg>
  <div id="tooltip" style="position:absolute;pointer-events:none;display:none;
       background:rgba(20,22,28,0.96);color:#f2f2f2;padding:8px 10px;
       border-radius:6px;font-size:12px;line-height:1.5;max-width:220px;
       box-shadow:0 4px 12px rgba(0,0,0,0.4);z-index:5;"></div>
  <div id="legend" style="position:absolute;top:12px;left:12px;
       background:rgba(20,22,28,0.85);color:#ddd;padding:10px 14px;
       border-radius:8px;font-size:12px;line-height:1.7;">
    <div style="font-weight:600;margin-bottom:4px;">Legend</div>
    <div>Size &mdash; market cap</div>
    <div>Distance from sun &mdash; years to profitability</div>
    <div>Orbit speed &mdash; fast = ahead of narrative, slow = behind</div>
    <div><span style="color:#4fd1a5;">&#9679;</span> ahead of narrative &nbsp;
         <span style="color:#ff6b6b;">&#9679;</span> behind narrative</div>
  </div>
</div>
<script>
(function () {
  const STOCKS = __STOCKS_JSON__;
  const svgns = "http://www.w3.org/2000/svg";
  const svg = document.getElementById("orbital-svg");
  const tooltip = document.getElementById("tooltip");
  const root = document.getElementById("orbital-root");

  const CX = 700, CY = 425;
  const RING_RADII = [130, 290, 440];
  const RING_JITTER = 20; // px spread within a ring band so orbits don't fully overlap
  const RING_COLORS = { mature: "#4fd1a5", scaling: "#9aa6ff", speculative: "#ff8f6b" };
  const PERF_COLORS = { ahead: "#4fd1a5", behind: "#ff6b6b" };

  const reduceMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function el(tag, attrs) {
    const e = document.createElementNS(svgns, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  // --- static background: rings + sun ---
  RING_RADII.forEach(function (r) {
    svg.appendChild(el("circle", {
      cx: CX, cy: CY, r: r, fill: "none",
      stroke: "#333a4a", "stroke-width": 1, "stroke-dasharray": "3 5",
    }));
  });
  const sunGlow = el("circle", { cx: CX, cy: CY, r: 34, fill: "#f2a93b", opacity: 0.25 });
  const sun = el("circle", { cx: CX, cy: CY, r: 22, fill: "#f2c94c" });
  svg.appendChild(sunGlow);
  svg.appendChild(sun);
  const sunLabel = el("text", {
    x: CX, y: CY + 46, "text-anchor": "middle", fill: "#aaa", "font-size": 12,
  });
  sunLabel.textContent = "Profitability";
  svg.appendChild(sunLabel);

  // --- size scale: sqrt of market cap, clamped ---
  const capsBillions = STOCKS.map(function (s) { return s.market_cap / 1e9; });
  const maxCap = Math.max.apply(null, capsBillions);
  function radiusFor(marketCap) {
    const b = marketCap / 1e9;
    const r = 10 + (Math.sqrt(b) / Math.sqrt(maxCap)) * 42;
    return Math.max(10, Math.min(52, r));
  }

  // --- speed scale: HIGH speed = ahead of narrative, LOW speed = behind.
  // Scaled off the actual range of relative_return_pct in this dataset
  // (not its absolute value) so the worst laggard is nearly motionless and
  // the biggest outperformer is the fastest planet on the board.
  const MIN_SPEED_DEG = 2;   // nearly stationary = furthest behind narrative
  const MAX_SPEED_DEG = 45;  // fastest = furthest ahead of narrative
  const relReturns = STOCKS.map(function (s) { return s.relative_return_pct; });
  const relMin = Math.min.apply(null, relReturns);
  const relMax = Math.max.apply(null, relReturns);

  function speedDegPerSecFor(relativeReturnPct) {
    if (relMax === relMin) return (MIN_SPEED_DEG + MAX_SPEED_DEG) / 2;
    const t = (relativeReturnPct - relMin) / (relMax - relMin); // 0..1
    return MIN_SPEED_DEG + t * (MAX_SPEED_DEG - MIN_SPEED_DEG);
  }

  // --- build planet groups ---
  // All planets orbit the SAME direction (clockwise). Direction used to
  // encode ahead/behind the narrative, but that meant same-ring planets
  // moving opposite ways would periodically collide head-on, and CW vs CCW
  // is hard to read at a glance anyway. Ahead/behind is now a stroke color
  // instead; orbit speed still encodes the SIZE of the gap either way.
  const planets = STOCKS.map(function (s, i) {
    // spread planets within their ring band so same-direction orbits at
    // different speeds don't perfectly overlap when one laps another
    const jitter = ((i * 37) % RING_JITTER) - RING_JITTER / 2;
    const ringR = RING_RADII[s.ring] + jitter;
    const angle0 = (i / STOCKS.length) * Math.PI * 2;
    const direction = 1; // clockwise, always
    const speedDeg = speedDegPerSecFor(s.relative_return_pct);
    const r = radiusFor(s.market_cap);
    const fillColor = RING_COLORS[s.tier] || "#8a8a8a";
    const strokeColor = s.relative_return_pct >= 0 ? PERF_COLORS.ahead : PERF_COLORS.behind;

    const g = el("g", { style: "cursor:pointer;" });
    const circle = el("circle", {
      r: r, fill: fillColor, opacity: 0.9,
      stroke: strokeColor, "stroke-width": 2.5,
    });
    g.appendChild(circle);

    svg.appendChild(g);

    g.addEventListener("mouseenter", function () { showTooltip(s); });
    g.addEventListener("mousemove", function (ev) { positionTooltip(ev); });
    g.addEventListener("mouseleave", function () { tooltip.style.display = "none"; });
    g.addEventListener("click", function () { selectStock(s.ticker); });

    return { s: s, g: g, circle: circle, ringR: ringR, angle: angle0, direction: direction, speedDeg: speedDeg };
  });

  function showTooltip(s) {
    const relSign = s.relative_return_pct >= 0 ? "+" : "";
    tooltip.innerHTML =
      "<div style='font-weight:600;margin-bottom:2px;'>" + s.ticker + " &mdash; " + s.name + "</div>" +
      "<div>Market cap: $" + (s.market_cap / 1e9).toFixed(1) + "B</div>" +
      "<div>Return since IPO: " + s.return_since_ipo_pct.toFixed(0) + "%</div>" +
      "<div>Vs. narrative benchmark: " + relSign + s.relative_return_pct.toFixed(0) + " pts</div>" +
      "<div>Years to profitability: " + (s.years_to_profitability === null ? "no consensus" : s.years_to_profitability) + "</div>" +
      "<div style='margin-top:4px;color:#9aa;'>Click to view detail</div>";
    tooltip.style.display = "block";
  }

  function positionTooltip(ev) {
    const rect = root.getBoundingClientRect();
    tooltip.style.left = (ev.clientX - rect.left + 14) + "px";
    tooltip.style.top = (ev.clientY - rect.top + 14) + "px";
  }

  function selectStock(ticker) {
    // Pragmatic MVP interaction: navigate the parent Streamlit page with a
    // query param, read on the Python side via st.query_params. This causes
    // a full page reload (animation restarts) rather than an in-place
    // Streamlit rerun. If your Streamlit version sandboxes this iframe and
    // blocks top-level navigation, swap this for a proper bidirectional
    // custom component (streamlit-component-lib) or the `streamlit-javascript`
    // package instead.
    try {
      const url = new URL(window.parent.location.href);
      url.searchParams.set("selected", ticker);
      window.parent.location.href = url.toString();
    } catch (e) {
      console.warn("Could not navigate parent window:", e);
    }
  }

  // --- animation loop ---
  let lastTs = null;
  function frame(ts) {
    if (lastTs === null) lastTs = ts;
    const dtSec = (ts - lastTs) / 1000;
    lastTs = ts;

    planets.forEach(function (p) {
      if (!reduceMotion) {
        p.angle += p.direction * (p.speedDeg * Math.PI / 180) * dtSec;
      }
      const x = CX + p.ringR * Math.cos(p.angle);
      const y = CY + p.ringR * Math.sin(p.angle);
      p.g.setAttribute("transform", "translate(" + x + "," + y + ")");
    });

    if (!reduceMotion) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
</script>
"""


def render_orbital_map(stocks, height=850):
    """Render the animated orbital map inside the current Streamlit page."""
    data = _prepare_data(stocks)
    html = (
        _HTML_TEMPLATE
        .replace("__HEIGHT__", str(height))
        .replace("__STOCKS_JSON__", json.dumps(data))
    )
    st.iframe(html, height=height + 10)


def main():
    st.set_page_config(page_title="Space economy — orbital map", layout="wide")

    # Strip Streamlit's default chrome/padding so the map can use the full
    # browser width and as much vertical space as possible. `components.html`
    # renders in a fixed-height iframe, so we can't make it truly 100vh
    # responsive to window resizes without extra JS — instead we reclaim the
    # padding/header Streamlit normally takes and give the map a tall, fixed
    # height that fills most of a typical laptop/projector screen.
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0.5rem;
            padding-bottom: 0rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 100%;
        }
        header[data-testid="stHeader"] { height: 0; visibility: hidden; }
        footer { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Space economy — orbital map")
    st.caption(
        "Size = market cap · distance from sun = years to profitability · "
        "orbit speed = ahead (fast) or behind (slow) the growth-narrative benchmark"
    )

    render_orbital_map(SAMPLE_STOCKS, height=850)

    selected_ticker = st.query_params.get("selected")
    if selected_ticker:
        match = next((s for s in SAMPLE_STOCKS if s["ticker"] == selected_ticker), None)
        if match:
            st.divider()
            st.subheader(f"{match['ticker']} — {match['name']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Market cap", f"${match['market_cap']/1e9:.1f}B")
            c2.metric("Return since IPO", f"{match['return_since_ipo_pct']:.0f}%")
            relative = match["return_since_ipo_pct"] - match["benchmark_return_pct"]
            c3.metric("Vs. narrative benchmark", f"{relative:+.0f} pts")


if __name__ == "__main__":
    main()