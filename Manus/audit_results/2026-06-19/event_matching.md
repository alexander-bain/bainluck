Starting the Event Matching Ground Truth Sweep. I'll systematically capture today's sports events from Kalshi, Polymarket, and bainluck.com. Beginning with Kalshi's sports section now.

I can see the Kalshi MLB games page. The games listed are mostly from June 18 (yesterday) with one game showing "Jun 19 @ 1:40AM" which was a late-night game. I notice today's (June 19) games may not be posted yet since it's still early in the day. Let me check the Kalshi API and also look at their "Today" filter or upcoming games. I'll also check Hockey and Basketball sections.

Here is the completed Event Matching Ground Truth Sweep for June 19, 2026. The JSON file contains:

**Layer 1 (Games Today):** 18 total games captured across both platforms:
- 14 MLB games (all matched on both Kalshi and Polymarket)
- 3 WNBA games (matched on both platforms)
- 1 AHL hockey game (Kalshi only — Calder Cup Finals)

**Key findings:**
- NBA: Season over, no game-level markets
- NHL: Season over, only a 2026-27 Stanley Cup futures market exists
- AHL: Calder Cup Finals (Chicago Wolves vs Toronto Marlies) is the only hockey game

**Layer 4 (Deep Audits):** 3 games audited:
1. **CIN vs NYY (MLB)** — 7 Kalshi event tickers (33 total markets), Polymarket has 4 tabs (Game Lines, 5 Innings, Home Runs, Strikeouts) with ~46 individual markets
2. **CWS vs DET (MLB)** — 4 Kalshi event tickers (22 total markets)
3. **WSH vs NYL (WNBA)** — 3 Kalshi event tickers (21 total markets)

**Layer 3 (bainluck.com):** Audited the CWS vs DET event page (/events/14959726):
- Championship path present (World Series, AL/NL Champ, Division, Make Playoffs)
- Player awards present (MVP only, using initials not headshots)
- No wrong-sport leaks detected
- No dedicated player props section on event detail pages
- No team filter pills on event pages
- 219 related futures referenced


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/CQs8QTZBJxMSF3m7RL4pcX/sandbox/61PT7VyiBp2HZHs5sekfU2_1781865927662_na1fn_L2hvbWUvdWJ1bnR1L2dyb3VuZF90cnV0aF9zd2VlcA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvQ1FzOFFUWkJKeE1TRjNtN1JMNHBjWC9zYW5kYm94LzYxUFQ3VnlpQnAySFpIczVzZWtmVTJfMTc4MTg2NTkyNzY2Ml9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJkeWIzVnVaRjkwY25WMGFGOXpkMlZsY0EuanNvbiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTc5ODc2MTYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=AYN8u-E7xOcNSwJ49VwBiP3pXdJ3n1YTPTpbWezyfCOmHfpIk3VS1HGLTp7b6X0jIO5hiV5UQ1Sy6c~MEDMeYXvJ9-FxXa5niuKSau7Cr8fKxG9IjW8qFhZkS8Mkuh6GZk3YY~tktWk1g77Z7LpLJf~HL0TAq4tZvtSF8Bx6tpR3EAC-SIZStHJ~YH~T2T0uWkoH33JvfQ0x16vbr3GVaChArruDu5buFdQK4UXcQ2B2fZY1Zwlo9EXWDQkESGXR4GDkz804s08Jp5rbwJZKX4Gq2~8uIdv5Ma7GVbD53Hs25THw5zKVxy2ucgcMr6MnE7EoFRg86LepbQ5vJ6QkmQ__