# Bain Luck Site Sweep: Latency & UI Audit (Mobile 375px)

**Date:** April 25, 2026
**Viewport:** Mobile (375px width)
**Pages Audited:** Homepage, Event Detail (NBA), NBA League, Weather, Championship Grid

This report details the findings from a comprehensive mobile viewport audit of bainluck.com. The audit focused on page latency, UI/UX issues, and data quality across five key pages. Findings are categorized into "Fix This" (clearly broken or confusing issues) and "Consider This" (subjective design observations).

---

## 1. Homepage (bainluck.com)

**Load Time:** Slow (24.47s to network idle)

The homepage feed takes a significant amount of time to fully load, likely due to the large volume of data and the sheer length of the page (over 21,000 pixels tall). While the single-column card layout renders correctly at 375px without horizontal scrolling, the initial load experience is poor.

### Fix This
*   **Latency:** The 24.47s load time is unacceptable for a mobile feed. The page appears to load all content at once rather than utilizing pagination or infinite scroll effectively.
*   **Cookie Banner Overlap:** The cookie consent banner partially obscures the bottom navigation bar and the lowest feed cards, making interaction difficult until dismissed.
*   **Small Text:** There are 388 elements with a font size under 11px. Specifically, the insight text on the cards (e.g., "New York Knicks odds shifted 19%") and the "Opened 46/54" text are very small and difficult to read on a mobile screen.

### Consider This
*   **Sport Filter Chips:** The horizontal scroll for the sport filter chips at the top (NBA, NFL, MLB, etc.) works well, but the last visible chip is often cut off abruptly. Adding a slight fade effect could indicate more options are available.
*   **Card Density:** The cards are information-dense. While the progress bars and main percentages are clear, the secondary information feels cramped.

---

## 2. Event Detail (NBA: Hawks vs Knicks)

**URL:** https://www.bainluck.com/events/14595959
**Load Time:** Medium-Slow (11.14s to DOM loaded, plus additional time for chart rendering)

The event detail page struggles with initial rendering, particularly the win probability chart, which displays a loading spinner for an extended period.

### Fix This
*   **Chart Loading Latency:** The win probability chart area shows a "25s" loading spinner long after the rest of the page has loaded.
*   **Missing Team Logos:** Team logos in the header area fail to render, displaying as pink and grey placeholder circles instead.
*   **Non-Chronological X-Axis:** The x-axis timestamps on the win probability chart are out of order (e.g., 9:47 PM, then 2:53 PM, then 7:08 PM). This makes tracking the game's progression confusing.
*   **Missing Period Markers:** There are no visible quarter or period markers (Q1, Q2, Half) on the chart to contextualize the probability shifts.
*   **Game Props Naming:** In the "Game Props - Live" section, the team names are missing. It displays "Team 199.5 84%" instead of "Hawks 199.5 84%".
*   **Data Discrepancy:** A massive 28% gap is explicitly called out: "Polymarket has Hawks at 55% vs sportsbooks at 27%". While the callout is good, this level of discrepancy warrants investigation into the data feeds.

### Consider This
*   **Mirrored Y-Axis:** The y-axis is mirrored (100% to 50% for ATL on top, 50% to 100% for NY on bottom). While the labels (12px) are readable, the mirrored design might be unintuitive for some users compared to a standard 0-100% scale for a single team.
*   **Unexplained Chart Label:** There is a "5" label next to the 50% dashed midline on the chart that lacks context.
*   **Kalshi Line:** The Kalshi line (green dashed) tracks closely with other sources and does not show wild spikes in this specific game, but it does diverge slightly around the 80-90% mark.

---

## 3. NBA League Page

**URL:** https://www.bainluck.com/sport/basketball/nba
**Load Time:** Slow (14.17s to network idle)

The page initially displays a "Loading..." text state for several seconds before the content populates. The layout works on mobile, but the data tables are problematic.

### Fix This
*   **Charlotte Hornets Data Anomaly:** The Charlotte Hornets have a 44-38 record but show a "Make Playoffs: 1.0%" probability. This is highly suspicious for a team with a winning record and likely represents a data error.
*   **1.0% Probability Floor:** Many teams show exactly "1.0%" for Conference and Champion odds across multiple sources (especially Kalshi). This appears to be a minimum tick size or floor value rather than a true 1.0% probability, which is misleading.
*   **Cleveland Cavaliers Record:** The Cavaliers show a 38-24 record (62 games played), while most other teams show 75-82 games played. This suggests stale data for this specific team.
*   **Small Text in Tables:** The source breakdown text (e.g., "P65K65") and the 24-hour change indicators in the championship odds table are extremely small and difficult to read on mobile.

### Consider This
*   **Chart Cramping:** The "Odds Movement" chart is readable but feels cramped on a 375px screen.
*   **Table Column Visibility:** On mobile, the championship odds table requires horizontal scrolling to see the most important columns (Conference, Champion), which is not immediately obvious.

---

## 4. Weather Page

**URL:** https://www.bainluck.com/weather
**Load Time:** Medium (5.02s to network idle)

The weather page loads reasonably well and the single-column layout stacks correctly on mobile. However, there are significant data quality issues.

### Fix This
*   **Stale Temperature Map Data:** The Global Temperature Map header reads "HIGH · APR 20, 2026", but the current date is April 25. The data is five days stale.
*   **April Rainfall Data Bug:** In the "Above 1 inch this month" section, the city "NYC" is listed eight times with conflicting probabilities (mostly 0%, one 100%), instead of showing 10 distinct cities. This is a critical rendering or data feed bug.
*   **Non-Chronological Tornado Months:** The Tornadoes section lists months out of order (Apr, May, Nov, Dec, Oct, Aug, Jun, Sep, Jul).

### Consider This
*   **Map Pin Overlap:** On the 375px viewport, the pins on the Global Temperature Map overlap significantly, making it difficult to tap individual cities to view their distribution charts.
*   **Zero Percent Probabilities:** Many future months in the Tornado section show 0%. It is unclear if this means a true 0% probability or if the market simply hasn't resolved/populated yet.

---

## 5. Championship Grid

**URL:** https://www.bainluck.com/playoffs/nba
**Load Time:** Medium (5.28s to network idle)

The page utilizes skeleton loading placeholders effectively, improving the perceived load time. The layout is clean, but it suffers from the same data issues as the NBA League page.

### Fix This
*   **Hidden Columns on Mobile:** The Eastern and Western Conference tables only display the "Team" and "Make Playoffs" columns on initial load. Users must scroll horizontally within the table to see the crucial "Champion" column, and there is no visual cue indicating that horizontal scrolling is possible.
*   **1.0% Floor Issue (Repeated):** The issue of teams showing exactly "1.0%" (likely a Kalshi minimum tick) persists here, making the aggregated odds misleading.
*   **Charlotte Hornets Anomaly (Repeated):** The Hornets again show a 1.0% playoff probability despite a 44-38 record.

### Consider This
*   **Chart Legend Truncation:** In the "Championship Odds Trend" chart, team names in the legend are truncated (e.g., "Oklahoma City Thu..."), and the text is quite small.
*   **Small Source Indicators:** The source indicators (B, P, K) and 24-hour change values in the tables are very small, contributing to the 238 elements with a font size under 11px on this page.
