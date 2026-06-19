Starting the Event Matching Ground Truth Sweep. I'll systematically capture today's sports events from Kalshi, Polymarket, and bainluck.com. Beginning with the Kalshi game sweep.

The direct category URL for baseball games returned a 404. I'll use the main sports page data and navigate to individual game pages to get tickers. Let me continue gathering the data from the all-sports page and click into individual games.

Completed Layer 1 sweeps. Since NHL and NBA are in offseason, I'll select 3 games for deep audit: 1 MLB game (Cincinnati vs New York Yankees), 1 WNBA game (Washington vs New York Liberty), and 1 more MLB game (Milwaukee vs Atlanta). Now proceeding with deep audit on Kalshi for these games.

Here is the completed Event Matching Ground Truth Sweep. The JSON file contains:

**Layer 1 (All games today):** 16 games captured across MLB (13 games) and WNBA (3 games). NHL and NBA are both in offseason with no games today.

**Layer 4 (Deep audit - 3 games):** 
1. Cincinnati Reds vs New York Yankees (MLB) — 13 Kalshi market types identified, 6 Polymarket market types
2. Milwaukee Brewers vs Atlanta Braves (MLB) — 6 Kalshi market types, 6 Polymarket market types  
3. Washington Mystics vs New York Liberty (WNBA) — 3 Kalshi market types, 3 Polymarket market types

**Layer 3 (bainluck.com event detail):**
- MLB games show full "Bigger Picture" sections with championship path (Make Playoffs → Division → AL/NL Champ → World Series), player MVP awards, and additional YRFI/NRFI markets
- WNBA event page is much simpler — no Bigger Picture section, no championship path, no player awards on the event detail page
- No player prop cards visible on bainluck event pages (player props appear to be on Kalshi/Polymarket directly)
- Player images use initials (not headshots)
- No wrong-sport or wrong-gender leaks detected
- No team filter pills visible on event detail pages

The JSON has been validated as syntactically correct.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/eBfPzAeqEmNvtptRjwPpTL/sandbox/CDq6lFt1wtddnMiRlndGU5_1781910882026_na1fn_L2hvbWUvdWJ1bnR1L2dyb3VuZF90cnV0aF9zd2VlcA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvZUJmUHpBZXFFbU52dHB0Ump3UHBUTC9zYW5kYm94L0NEcTZsRnQxd3RkZG5NaVJsbmRHVTVfMTc4MTkxMDg4MjAyNl9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJkeWIzVnVaRjkwY25WMGFGOXpkMlZsY0EuanNvbiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTc5ODc2MTYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=t2ld5j~QF7V26vGvjtYuUVHs354Dd1aypn-COjz-dp9JQtuM-0JRM2XY3UiBYLaWO6CQqlvs2ZGkPpw~Qlg980a0ajgQllGYbOQoqGhKzm7k-SspK6AUSdKD8Q8Y1Ry2lgi8xWJTOImcG2bkG0UTr5~IHRkhkPzL4zuOFrcsRe6he9jRbhFzBpZ44qrUV2CrPHSndz9~Q2fHuvbR-vCUGBmQDq37V43QNJwY2l3ymll2UGH9iexP9sxWH3ldlP1XY0mUoSAi9TSGMipD8eYep0CchxT41SAAgUkZdsjNz2w0qr1zqG7Qj10ueqZ5tHEVcMfFrXBpoZXouuQxR65ctQ__