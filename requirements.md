# Deep-dive dashboard — requirements

## Context

This is one screen of a larger "orbital map" Streamlit app about publicly
traded space economy companies. Clicking a company on the map opens this
deep-dive screen for that single company.

The project's research verdict, which this screen exists to provide
evidence for, is:

> Publicly traded space economy stocks have not, on average, delivered
> returns commensurate with the scale of the growth narrative — but that
> average conceals a real split. Established aerospace primes with space
> divisions have delivered modest, fundamentals-backed returns that
> broadly track their business performance. Pure-play space companies, by
> contrast, remain largely speculative: price returns have been dominated
> by sentiment swings — a 2021 SPAC-era boom, a 2022 crash, and an uneven
> recovery — that have moved far faster than the underlying revenue and
> cash-flow fundamentals actually improved. Some of these pure-plays are
> now closing that gap; most are not yet there. The industry-level growth
> story is real and measurable, but public shareholders in the pure-play
> companies specifically have not yet been reliably compensated for it —
> they've been paid, when they've been paid at all, for correctly timing
> sentiment rather than for the underlying business catching up.

Every element of this screen should exist because it provides evidence for
one of the claims in that verdict. Do not add sections, metrics, or charts
that don't trace back to a claim above — the design goal is the simplest
screen that still fully supports the verdict, not a comprehensive finance
dashboard.

## Repo note

Any existing `orbital_map.py`, `deep_dive.py`, `narrative_gap_chart.py`, or
`orbital_frontend/` files in this repo were prototyping/testing code only.
Treat none of it as a fixed constraint — delete, rewrite, or restructure
any of it freely if a cleaner implementation better serves the
requirements below. There is no need to preserve current function names,
file boundaries, or the existing component architecture.

Nevertheless, the general look and functionality of the orbital map is good right now. You can optimise it if necessary, but preserve the look and feel. You can make it into sub files or combine it back into one file, but confirm first. If you want to change the orbital map UI, give reasoning and confirm whether to make the change.

## Data model required per company

Only pull/store what's needed to drive the sections below:

| Field | Frequency | Used for |
|---|---|---|
| Ticker, name, sector/tier (prime vs. pure-play) | static | identity, grouping |
| IPO date, listing method (SPAC vs. traditional) | static | horizon anchoring, SPAC-cohort flag |
| Adjusted close price | daily, full history available | price chart, returns, indexed chart |
| Market cap | latest | metric card |
| Revenue | annual (quarterly if available) | growth rate, indexed chart, fundamentals chart |
| Free cash flow | annual (quarterly if available) | metric card, fundamentals chart, "closing the gap" flag |
| Net income | annual | optional secondary profitability figure |

If quarterly fundamentals aren't reliably available for a ticker (common
for recent SPAC listings), fall back to annual — don't block the screen on
missing quarterly data.

## Required sections

### 1. Header
Ticker, company name, sector/tier tag (prime vs. pure-play), IPO year +
listing method (e.g. "SPAC-listed 2021").

### 2. Metric cards (minimum set — do not add more)
- Market cap
- Free cash flow (TTM or latest annual)
- Revenue growth YoY
- Price/sales ratio

These four cover: scale (market cap), the profitability claim (FCF), the
fundamentals-growth claim (revenue growth), and the "how much optimism is
priced in" claim (P/S) — each ties directly to a piece of the verdict.

### 3. Price return chart with time-horizon toggle
Line chart of indexed price, with a toggle/selector for: since IPO, 3Y, 1Y,
YTD. Visually mark the 2021–2022 period (shaded band or similar) so the
SPAC boom/crash is identifiable without a caption.

This directly supports the "2021 SPAC-era boom, 2022 crash, uneven
recovery" claim — the toggle exists specifically so the audience can see
the conclusion change depending on the window measured, which is itself
part of the argument.

### 4. Narrative vs. fundamentals vs. price chart (core chart)
One chart, three lines, all indexed to 100 at a common start year:
- **Narrative-implied trajectory** (dashed) — a smooth curve built from a
  single CAGR derived from an external industry growth forecast (e.g.
  "$630bn in 2023 → $1.8tn in 2035")
- **Actual revenue** (solid) — the company's real indexed revenue
- **Actual stock price** (solid) — the company's real indexed price

This is the single most important chart on the screen: it makes the
verdict's central claim visible directly — that price has detached from
fundamentals, and fundamentals have grown but not as fast as the
narrative implies.

**The narrative line must be configurable, not hardcoded.** Whatever
source, baseline value/year, and target value/year are used to compute the
narrative CAGR should live in one clearly-named, easily-edited place (a
config file, constants block, or UI input — implementer's choice) with at
minimum these fields: source name/citation, baseline value, baseline year,
target value, target year, currency. Swapping in a different forecast
(different research firm, updated numbers, a different growth scenario)
should require editing that config only — never touching chart-building or
data-fetching code.

If the narrative source's forecast is denominated in a different currency
than the stock's market (e.g. GBP forecast vs. USD-denominated stock),
that should be handled explicitly (flagged or converted), not silently
mismatched.

### 5. Fundamentals trend chart
FCF and revenue growth over the last several years/quarters, same time
axis, so the audience can see whether losses are narrowing while growth
holds up (or not).

This is the evidence for "some pure-plays are closing the gap; most are
not" — it needs to show trend/direction, not just a current snapshot.

### 6. "Closing the gap" classification
A short, explicit, rule-based label — not a subjective one-off judgment —
answering whether this specific company is closing the fundamentals gap.
Suggested rule (adjust as needed, but keep it a stated, applied rule):
FCF margin improved in at least 3 of the last 4 reporting periods. Display
the label and, ideally, which periods drove it.

## Explicit non-goals (keep this simple)

- No real-time/live price streaming — periodic data refresh is fine
- No full valuation model (DCF, comps, etc.) — this is an evidence screen,
  not an investment tool
- No need for every financial metric available — stick to the four metric
  cards listed above
- No per-quarter granularity requirement where annual data is sufficient
  and quarterly isn't reliably available
- No separate settings/admin screen — narrative config can be a simple
  file or constants block, not a full UI

## Acceptance criteria

- [ ] Every chart/section on the screen maps to a specific claim in the
      verdict above (a reviewer should be able to point at any element and
      say which sentence of the verdict it supports)
- [ ] Narrative CAGR is computed from a clearly-labeled, easily-edited
      source config — not a magic number buried in chart code
- [ ] Missing/incomplete fundamentals data for a ticker degrades
      gracefully (clear message, no crash) rather than blocking the screen
- [ ] Price chart's time-horizon toggle actually changes the displayed
      return, not just the chart's x-axis window
- [ ] Works for both a "prime" company (e.g. Lockheed Martin) and a
      "pure-play" company (e.g. Rocket Lab) without special-casing —
      the same screen, same data model, same charts