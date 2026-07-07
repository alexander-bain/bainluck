# Chart Design Spec — "clean like Kalshi/ESPN, honest like us"

Written 2026-07-06 (Fable, from Alex's taste interview). Binding for all probability-chart work. Stack: recharts (`OddsChart.tsx` is the reference implementation to migrate first).

## The four principles (Alex's calls, binding)

**P1 — NO SMOOTHING. EVER.** *"The movement in the line is part of the value of our product."* No interpolation, moving averages, or curve-fitting that alters what the data says. If a line looks ugly — spikes, stale flatlines, sawtooth — that is a **data-quality bug to fix upstream, fast**, not a rendering problem to hide. Any chart artifact spotted in review gets filed like a calibration bug (route per `docs/calibration-diagnosis-playbooks.md` discipline). Performance thinning is permitted only if visually lossless: point-reduction must preserve every local extremum (LTTB-style), never average.

**P2 — Kalshi/Polymarket-minimal chrome.** One hero line, almost nothing else. Specifically: no `CartesianGrid`; a single faint dashed 50% `ReferenceLine`; Y-axis ticks at 0/50/100 only, small and muted (`text-text-muted`); sparse X ticks (dates or period labels, never every point); no chart border/box; soft gradient area fill under the hero line (accent → transparent, ~12% peak opacity); hero line 2.5–3px with rounded caps; the **big current number + 24h/7d delta chip** lives above the chart in tabular figures (`font-variant-numeric: tabular-nums`) — the number is the headline, the chart is the texture.

**P3 — Prominent blend + VERY faint sources.** The blended probability is the chart: full accent color, full weight, gradient fill. Individual sources render at ~1px and 12–18% opacity in desaturated gray — visible as texture, never competing. No per-source legend by default; a small "sources" affordance expands names/toggles. Tooltip leads with the blend; per-source values behind the same expansion. (Extends the blend-only rule: on event charts sources may be *faintly* present; on futures detail they stay absent.)

**P4 — Fixed 0–100 axis, no drama-zoom.** Probability charts always render the full 0–100 domain. Auto-zooming the Y-axis to amplify small moves is a volatility-drama trick — an enticement pattern (see no-gambling-enticements, D1). Movement emphasis comes from the delta chip and the line itself, not axis manipulation.

## Supporting rules

- **Gaps are gaps:** `connectNulls={false}` everywhere. Never draw a line across a period with no data; a source that stops reporting fades out at its last real point (gotcha #22 — chart domains end at the last real snapshot, not processing timestamps).
- **Color:** design-system tokens only, light mode. One accent for the blend; team colors permitted for the two-team win-prob chart; sources always neutral gray.
- **Animation:** off (or ≤300ms mount-only). Live charts update by data, not by wiggle.
- **Interaction:** crosshair + single consolidated tooltip; tap-hold scrub on mobile (#925 readout rules apply — never invent a clock).
- **Density:** discover-card sparklines get P2 stripped further — no axes at all, just line + fill + current value.

## /calibration page (the stats exception)

CIs stay — they carry the small-n honesty — but redesigned: slim whiskers or soft shaded band at ~40% opacity; bucket dot radius scales with log(n); buckets with n < 30 render hollow/faded so a noise point (the 75%→0% totals bucket) reads as noise instead of screaming; the n and the faded treatment are self-explanatory on hover. Excluded-count transparency per D3 (well-priced default + full view one click away).

## Implementation notes (recharts, first pass = OddsChart.tsx)

Remove `CartesianGrid`; `YAxis ticks={[0,50,100]} axisLine={false} tickLine={false}`; `XAxis` interval tuned for ~4–6 labels, `axisLine={false}`; blend as `Area` (gradient `<defs>`) + `Line strokeWidth={2.75} dot={false}`; sources as `Line strokeWidth={1} strokeOpacity={0.15} dot={false}`; `ReferenceLine y={50} strokeDasharray="4 4"` muted; `isAnimationActive={false}` on live surfaces; margins trimmed to content. Keep `tsc --noEmit` in the loop (gotcha #10) and the 3 GA4 hooks on any touched page.

## Rollout order

1. `OddsChart.tsx` (event pages — highest traffic, currently busiest chart), 2. futures-detail trend line (pairs with the #883 parity audit), 3. discover sparklines, 4. /calibration CI redesign. Each ships with before/after screenshots in the report; the Alex eyeball is the acceptance gate.
