Starting the Event Matching Ground Truth Sweep. I'll systematically capture today's sports events from Kalshi, Polymarket, and bainluck.com. Beginning with Kalshi's sports section.

Progress update: Completed Kalshi sweep. Key findings:
- **MLB**: 15 games today (full slate)
- **NBA**: No games today — NBA Finals (Knicks vs Spurs) starts June 4
- **NHL**: No games today — Stanley Cup Finals (Vegas vs Carolina) starts June 3

Since there are no NBA or NHL games today, I'll focus the deep audit on MLB games. Now moving to Polymarket to capture their sports markets.

The Event Matching Ground Truth Sweep is complete. Here's the summary:

**Layer 1 (Game Sweep):**
- **15 MLB games** captured across both Kalshi and Polymarket (full match between platforms)
- **No NBA games today** — NBA Finals (Knicks vs Spurs) starts June 4
- **No NHL games today** — Stanley Cup Finals (Golden Knights vs Hurricanes) starts June 3

**Layer 4 (Deep Audit - 3 Games):**
- Yankees vs Athletics, Braves vs Reds, Phillies vs Dodgers
- Kalshi: 5 market types per game (moneyline, spread, total, 2x team totals) — NO player props on game pages
- Polymarket: 4 market types per game (moneyline, spreads, totals, first inning run) — NO player props

**Layer 3 (bainluck.com):**
- bainluck.com was **non-functional during capture** — all pages stuck on loading spinners, API intermittently timing out
- Successfully identified event IDs via API: Yankees vs A's = 14820214, Phillies vs Dodgers = 14820216
- Could not audit player props, related futures, or bigger picture sections due to site being down

**Key finding:** Neither Kalshi nor Polymarket currently offer player props on their MLB game pages. The market types are limited to moneyline, spread/run line, totals, and team totals (Kalshi) / first inning (Polymarket).

The JSON output file is attached below.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/PLZyUTgukGZvePs5TnLw8F/sandbox/9bnXZo9xlX2BMA9tSVtsSa_1780241635222_na1fn_L2hvbWUvdWJ1bnR1L2dyb3VuZF90cnV0aF9zd2VlcA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvUExaeVVUZ3VrR1p2ZVBzNVRuTHc4Ri9zYW5kYm94Lzliblhabzl4bFgyQk1BOXRTVnRzU2FfMTc4MDI0MTYzNTIyMl9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJkeWIzVnVaRjkwY25WMGFGOXpkMlZsY0EuanNvbiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTc5ODc2MTYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=UE6coy58Za2xI8b9vMMYFMLOiX-jXv2Up8TaWFcPZARfW3gDGTtmSUsJgOyyRDEyzkGbC4TEQ2kw~mVmaa~phtYHOWF2cOwSaumYIKRj~NFAQaRUbrVAOpX7gUQtymAv8nOIhVPWVyvopGz6BJPccnUmKjei8CBUy13voDHR4BYD3kI~PRDphiL~RDbKyPnYo2BQDSPx2HPDSrVmw7s0jbFaMU-ifXM5ek9MDy4Cl0dxGwMztT~uN33N54JPQuuJLyleBUaVOnNuQis-Et0ZkZkJlBVVEM-0eZmJyU1TzxEQSKENYHjKW352MO4WOOcpWEli4ZVAoojiNA~RLWtNMw__