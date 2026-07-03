Starting the Market Accuracy Ground Truth audit. I'll visit bainluck.com/feed to pick 4 events, then audit each for monotonicity, cross-game contamination, and cross-reference with Kalshi.

I've found that the completed NBA game (Knicks vs Spurs) has all markets settled at 0%/100%. I need to look at scheduled/upcoming games to properly test monotonicity with live probabilities. Let me check the MLB games and look for a game that's upcoming or recently started.

I have completed the Market Accuracy Ground Truth audit across 4 events on bainluck.com and cross-referenced with Kalshi. The findings are compiled in the attached JSON report.

**Key Findings:**
1. **No Cross-Game Contamination**: The NBA Finals events showed only markets for their specific games. While Game 4 showed more 1H total thresholds (18) than Kalshi (9), the extra thresholds were evenly spaced (1.5-point intervals) and are clearly from sportsbook sources, not leaked from other games in the series.
2. **Monotonicity**: All probabilities for totals and props correctly followed monotonicity (strictly decreasing or non-increasing as thresholds go up).
3. **Section Naming**: The actual section names on bainluck.com differ from the instructions. "Projected scoring" and "Period Markets" are actually labeled as "Total maps" (Full game, 1st half, 2nd half) and "Margin maps".

The JSON structure follows your requested format and includes the data from the 4 audited events.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/eBmB7ifS9DAsRtC9ToBU4s/sandbox/8akXIUqYQYhD0hho7hlpFW_1783070986505_na1fn_L2hvbWUvdWJ1bnR1L2F1ZGl0X3JlcG9ydA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvZUJtQjdpZlM5REFzUnRDOVRvQlU0cy9zYW5kYm94Lzhha1hJVXFZUVloRDBoaG83aGxwRldfMTc4MzA3MDk4NjUwNV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJGMVpHbDBYM0psY0c5eWRBLmpzb24iLCJDb25kaXRpb24iOnsiRGF0ZUxlc3NUaGFuIjp7IkFXUzpFcG9jaFRpbWUiOjE4MzAyOTc2MDB9fX1dfQ__&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=mQBC~cBELNYz2I-iOJF61Y7p2qykX79khpEmABM4mzCuXrUmrWRuD5Jhh77q8VQjzcM7NQDaSrurvGY1aV-ga~wSfbaD08ca-7SuisAn~df8lNWOcN0j0mzIq9B7xgPUCnPgLosl9gKkPYoCFqet8gFI0kcwHaetWNHWuzaQGGiBfMffEad5SKOyHTBPQnbG7Mg06sPOHvKqxlTeTeQ~doaB1CJRIrzPADsUaCRa338zT-NeUMKRTpTzu6qn84lCct7a2HPhtevwt1OuZ0t-iDK555m6qEviwYIZPu3qiHl5gQC36AmB4ONpXa-RPOSezyABy-WIBSxaDFR2jky-4g__