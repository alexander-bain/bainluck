Starting the Market Accuracy Ground Truth audit. I'll visit bainluck.com/feed to pick 4 events, then systematically audit each one for monotonicity, cross-game contamination, and data accuracy.

Found the feed. Selecting 4 events for audit:
1. **NBA Playoff** - Boston Celtics vs Philadelphia 76ers (scheduled tonight)
2. **MLB** - New York Yankees vs Boston Red Sox (completed yesterday)
3. **NHL Playoff** - Colorado Avalanche vs Los Angeles Kings (completed today)
4. **NBA Playoff (completed)** - Denver Nuggets vs Minnesota Timberwolves (completed today)

Now navigating to each event page to audit markets.

Found the events. Now clicking into each one to get their URLs and audit their markets. Starting with the Boston Celtics vs Philadelphia 76ers NBA playoff game.

Completed auditing all 4 events on bainluck. Found significant issues including:
- **Event 1 (Celtics vs 76ers)**: Major monotonicity violation in First Half Total (118.5→121.5 jumps from 25%→58%)
- **Event 2 (Yankees vs Red Sox)**: Monotonicity violations in Projected Combined Scoring
- **Event 3 (Avalanche vs Kings)**: Clean - no scoring/period markets to audit
- **Event 4 (Nuggets vs Timberwolves)**: Duplicate Second Half spread section with massive violation; Denver team total violation

Now moving to cross-reference with Kalshi for the NBA and NHL events.

Completed Kalshi cross-reference for the Celtics vs 76ers series. Found that Game 1 has different thresholds (99.5-123.5) while Games 2 and 3 share the same thresholds (100.5-124.5). The contaminated values on Bainluck for Game 3 (121.5 at 58%, 124.5 at 56%) are clearly stale data from Game 2.

Now checking the Nuggets vs Timberwolves series on Kalshi for the duplicate Second Half spread section.

The Market Accuracy Ground Truth audit is complete. Here are the key findings:

**2 of 4 events have cross-game contamination issues:**

**CRITICAL — Event 1 (Celtics vs 76ers, Game 3):** The First Half Total market shows stale probabilities from a previous game at thresholds Over 121.5 (58% on Bainluck vs 17% on Kalshi) and Over 124.5 (56% vs 13%). The first 7 of 9 thresholds match Kalshi within 4%, but the last 2 are 41–43 percentage points off, creating a massive 25%→58% monotonicity break. Games 2 and 3 share the same threshold set (100.5–124.5), and the contaminated values appear to be cached from Game 2 (Apr 21).

**WARNING — Event 4 (Nuggets vs Timberwolves, Game 2):** A duplicate "Second Half" spread section appears with data from Game 1, containing a 19%→55% violation for Minnesota. The Period Markets (1H/2H Total) are clean.

**Event 2 (Yankees vs Red Sox):** Two minor monotonicity violations in projected combined scoring with suspiciously low probabilities (3–10% for MLB run totals), suggesting a data mapping issue.

**Event 3 (Avalanche vs Kings):** Clean — minimal market structure (no totals, spreads, or period markets to audit).

Both deliverables are attached: the structured JSON report and a detailed Markdown narrative.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/LskCQicQ5f4PSVV5ab8eBQ/sandbox/dNlnQNKmkbRo3shd60bGnw_1777066374176_na1fn_L2hvbWUvdWJ1bnR1L21hcmtldF9hY2N1cmFjeV9ncm91bmRfdHJ1dGg.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvTHNrQ1FpY1E1ZjRQU1ZWNWFiOGVCUS9zYW5kYm94L2RObG5RTktta2JSbzNzaGQ2MGJHbndfMTc3NzA2NjM3NDE3Nl9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDIxaGNtdGxkRjloWTJOMWNtRmplVjluY205MWJtUmZkSEoxZEdnLmpzb24iLCJDb25kaXRpb24iOnsiRGF0ZUxlc3NUaGFuIjp7IkFXUzpFcG9jaFRpbWUiOjE3OTg3NjE2MDB9fX1dfQ__&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=s1Qm63nojYJ~5dHE8IBIfhnm0lYLvDgS2R-w4H7awfaB7xWaduPuNkIh5Gb39LCC~qKghekJ5MbG9C~nIlSv9QoYRtPsK2gIT20l7-CrsvAZDcZwOx1VkIyMd1IzF8u2dOsRdVa6Uwz~AGNYMm112ggcDNSFE7uPjBET-NzkJeGrdbbOzvwCpvZOEYzUC88nyyXrrKmf3LpfshMeNj1rRLEHlajYKPvfSuaepZ8QXGtvHlsBtufvhgrAnYN8MbSjOO~GzLpsVcdSyki-FMofcssmmTni~eENe~hQisA4YCxsIcQ1eXSM-CigIWkgmxLCE~lPxT-cxrKprIHesHiW0Q__


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/LskCQicQ5f4PSVV5ab8eBQ/sandbox/dNlnQNKmkbRo3shd60bGnw_1777066374176_na1fn_L2hvbWUvdWJ1bnR1L21hcmtldF9hY2N1cmFjeV9ncm91bmRfdHJ1dGg.md?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvTHNrQ1FpY1E1ZjRQU1ZWNWFiOGVCUS9zYW5kYm94L2RObG5RTktta2JSbzNzaGQ2MGJHbndfMTc3NzA2NjM3NDE3Nl9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDIxaGNtdGxkRjloWTJOMWNtRmplVjluY205MWJtUmZkSEoxZEdnLm1kIiwiQ29uZGl0aW9uIjp7IkRhdGVMZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNzk4NzYxNjAwfX19XX0_&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=h-r6KoinDy2JuaS2RK3CNSFfkd9lS2BobgwBFCt-5CbNPMVjd0B5mTUCbGx62KV3N75JMsxg9hDzCeXAJUjupeGdCa1HtGjiMwt4hIOFDmKfkgtOzFcSZzEer8vrOLF2jAyp7ze58Rv0hKGlB4~X6uOtxVRM1gO2iJT2ojbSUmpbDWsm24dxTiVsMhjc~NBLJmpU6LN17ttV5QnnbMPVXF08Z6Z2Hpqpaeep3BVHIThnu0TCsPpnPrQVk2ZLha2sahBZKSvYDQzZG6LzQ6xG6I-4hStTprlrum~aTYplxO9rheApT3I~QmOjNNOTcNnf0ShGjQ2P037CfHCBzTaP-w__