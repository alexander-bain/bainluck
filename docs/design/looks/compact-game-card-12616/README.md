# Compact game card look — #12616

Standalone design study only. No application route, shared component, production data, or deployed page changes. Open `index.html` locally after checking out this branch; all fonts and data are bundled. No API calls are made by the page.

## Compare

- A / Quiet table: simple aligned rows, no probability rule.
- B / Fine rule: the same grid with a thin probability rule, header dividers, and a shaded active number column.

Use `?variant=A&case=nba` (or B; nfl, soccer, tennis) to see the exact screenshot view. Each shows before, during with a live projection, during with a pregame projection, and after. The two during versions deliberately ask for a product choice rather than resolving it. Projected returns to the pregame estimate after the game.

Score/Final, Projected, Pregame, Now retain their horizontal positions. Missing headers and numbers are blank. Draw has probabilities but no score or projection. Tennis has no projection. During and final scores and probabilities use 16px tabular digits; no shrink-to-fit. Large text: `?variant=A&case=nba&text=large` uses 24px digits and names, placing each name above its four numeric slots. All numbers stay onscreen without horizontal scrolling. This is not a native Dynamic Type test.

## Sources and limits

`sources.json` contains the public fields used from the event and history APIs, including historical timestamps. NBA event 15344730 is a historical replay: final 123–101; pregame 54% / 46%; pregame projection 109.5 / 107.8 shown as 110 / 108. During pairs a 7:15 PM PT projection/probability point with the most recent score observation, 7:14:48 PM PT. Live chance 99.6025% / 0.3975% is displayed as >99% / <1%; live cards never display 100% or 0%. Finished cards omit Now.

NFL event 14639206 uses its API-rendered 41% / 59% pregame snapshot, which reported state_read_fresh=false; projected scores were unavailable (no_recent_lines). Its during/after scores, projections and frozen pregame chances are sample scenarios, not forecasts or actual results. Soccer and tennis are invented samples. Sample labeling is outside the compact card.

## Verification

`verify.cjs` requires Playwright and Chromium. Run `node verify.cjs` with Playwright available on NODE_PATH and optionally CHROMIUM_PATH pointing to an installed Chromium executable. It captures eight original views and ten round-two comparison screenshots at a 390px viewport.

Checks: stable column right edges across states; no wrapped names or overflowing normal-size cells; 16px numeric type; three-digit scores and >99% / <1%; blank draw scores/projections; blank tennis projection; no JavaScript errors; large text fits without scrolling or shrinking. Results are in `verification.json`.

The eight main screenshots were reviewed at phone width. No frontend/backend full build or suite was run: this is isolated static documentation with no application imports, not an implementation ready for production. Fable review and Alex’s choice are still needed. Nothing has been merged or deployed.

## Round two comparisons

Fable’s PR comment was read first. Both variants and all original states remain. Five separately labeled captures per variant are in `screenshots/r2-{a,b}-{comparison}-390.png`:

- `large`: 24px digits and names, two lines per team. Three-digit scores plus all four numeric columns fit at 390px without sideways scrolling. This is the largest text setting of this web study, not a claim to test the native app’s maximum Dynamic Type setting.
- `near`: >99% and <1% Now labels in both live and pregame projection views.
- `headers`: before cards with Pregame and Chance for comparison.
- `slots`: before card with fixed empty Now slot and a version closed to the right edge. Only the labeled closed-up comparison changes column positions; the original layout still holds them fixed.
- `soccer`: whole-goal versus one-decimal sample projected scores, before and during. Sample decimals 1.6 / 1.4 before and 2.4 / 1.6 during round to the shown whole-goal equivalents.

Open index.html with `?variant=B&case=nba&compare=headers`, `compare=slots`, or `compare=near`. For soccer use `?variant=B&case=soccer&compare=soccer`; for large text use `?variant=B&case=nba&text=large`. Change B to A for the quiet variant. These are decisions for Alex, not changes to production defaults.
