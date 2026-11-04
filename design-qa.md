# Futures preview visual review

final result: passed

Reviewed Nov 3, 7:32 PM PT, on deployment `https://bainluck-1no21ut75-alexander-bain.vercel.app`, application commit `d32237d61f`.

Reference: the production event page `/events/15341541` and its composed chart/hero primitives, plus the old futures page at 390 px. These are hierarchy and design-system references, with different market content and lifecycle states; this is not a pixel clone. Reference captures and all final screenshots live in `docs/designs/futures-page-2026-11/`.

Iteration 1: collapsed review chrome, kept the leader stable when a field row is selected, aligned the duel's rounded pair and bar, labelled unavailable grades' numbers historical, and defaulted settled charts to the full journey. The final captures show the resulting hierarchy at 390 and 1280 px.

Iteration 2: hosted review found server/browser timezone hydration mismatches in the shared chart. The preview now mounts it client-side, with an SSR guard. A fresh hosted tab rendered all 16 final captures with zero console errors and no horizontal overflow.

Interactions: field expands to 24 rows, threshold selection changes the hero, time-range controls work, fullscreen opens, Escape closes it and returns focus. Every displayed probability location reserves the source mark; no sheet is built.

Accepted payload limitations are explicit in the design note: sparse Denver history, single-venue Kansas recorded history, CFP's stored nonexclusive field, and the retracted one-leg grade. Full-page mobile screenshots retain the site's fixed bottom navigation; Vercel's review toolbar is visible. These are preview chrome, not new app controls. No unresolved P0/P1/P2 visual defects found.
