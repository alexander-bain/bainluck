# RULING 148 — In live play, Kalshi and Polymarket carry the sportsbook consensus's base weight

date: 2026-11-01
author: Alex
issues: #10090

Alex's words, in the Day 0 brief (chat, 2026-11-01, ~7:20 PM PT): "anything that changes a published number or its
order is labeled tier-b and Codex reviews it - that includes decision D's live-play blend weights, which Alex ratified
on Nov 1 and the freeze PR writes into PRODUCT-BRAIN."

THE DECISION (decision D, taken in the Speed chat on Oct 31 ~10:20 PM PT and shipped as G4F51, production v6049): in
live play the two real-time markets, Kalshi and Polymarket, carry the betting base weight (3.0) instead of their
pre-game 0.8. It reaches every place the live blend is drawn: the hero, the receipt previews, and the chart's live
buckets (`app/utils/aggregation.py`, `LIVE_MARKET_SOURCES` and `_live_base_weight`). The #1829 share cap and the
relative recency decay apply on top, unchanged. Pre-game and settled blends keep `SOURCE_WEIGHTS`.

WHY: in live play the sportsbook consensus refreshes about every 30 s while the venues tick continuously. On
UNLV-NIU (Oct 31) Kalshi and Polymarket were about a quarter of the live headline, so a real move on both venues
barely moved the number a reader watched. At the books' weight each venue tick moves the headline about twice as far.

THIS IS A CHANGE TO THE BLEND, which is the product, so it is a tier-b change and it was decided by Alex, not by the
race. Smarter blending is #11850: a one-page analysis on the forward record comes first, and a build follows only if
it earns it. Until then this weight table is the live rule.
