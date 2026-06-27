Starting the Event Matching Ground Truth Sweep. I'll systematically capture today's sports events from Kalshi, Polymarket, and bainluck.com. Beginning with Kalshi's sports section now.

I've captured all the MLB games from Kalshi. I can see they list 43 games total (including future dates). Now I need to get the exact tickers by clicking into individual game pages. Let me also check NBA and NHL. I notice the page shows games for Jun 28 as well (which are tonight's late games in ET). Let me now check NBA/Basketball and NHL sections, then get individual game tickers.

Layer 1 complete. Both Kalshi and Polymarket have exactly 15 MLB games today. No NBA or NHL games (both in offseason). Now proceeding with Layer 4 deep audit on 3 selected MLB games:
1. NYY vs BOS (most popular)
2. LAD vs SD (marquee West Coast matchup)
3. PHI vs NYM (NL East rivalry)

Starting deep audit on Kalshi for these 3 games.

Here is the completed Event Matching Ground Truth Sweep. The JSON file contains:

**Layer 1 (All Games Today):**
- 15 MLB games with complete Kalshi tickers and Polymarket slugs/URLs
- NBA: No games (offseason - Spurs won 2026 championship)
- NHL: No games (offseason - only futures markets)

**Layer 4 (Deep Audit - 3 Games):**
1. **NYY vs BOS** — 11 market types on Kalshi (146 individual markets), 10 market categories on Polymarket
2. **LAD vs SD** — 11 market types on Kalshi (108 individual markets), 8 market categories on Polymarket
3. **PHI vs NYM** — 11 market types on Kalshi (91 individual markets), 8 market categories on Polymarket

**Kalshi market types found per game:** moneyline, spread, total, team_total, first_5_innings, player_prop_hits, player_prop_hr, player_prop_rbi, player_prop_sb, first_5_spread, first_5_total

**Layer 3 (Bainluck Event Detail):**
- Championship paths shown for both teams (Make Playoffs → Division → AL/NL Champ → World Series)
- Player awards shown (MVP candidates) on LAD vs SD page
- Trade Watch shown on NYY vs BOS page
- Player props visible (HR O/U, Strikeouts O/U)
- No wrong-sport leaks detected
- No team filter pills on event detail pages (those are on team pages)

The JSON is valid and complete.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/Py8D6AcX5jkEfDUKXH2oxC/sandbox/QkJSiCrMSaacYaJNgwZxpj_1782574426425_na1fn_L2hvbWUvdWJ1bnR1L2dyb3VuZF90cnV0aF9zd2VlcA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvUHk4RDZBY1g1amtFZkRVS1hIMm94Qy9zYW5kYm94L1FrSlNpQ3JNU2FhY1lhSk5nd1p4cGpfMTc4MjU3NDQyNjQyNV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJkeWIzVnVaRjkwY25WMGFGOXpkMlZsY0EuanNvbiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTc5ODc2MTYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=Wk3a05ujITTzBxsStB0KOz9~pct59zzajvpYacVBf6A8nL~JHlGpUvzhyvO2CMk4etPlHAd4lMwfu5dXheIxYQHirmPYRGWB9j3oOn93mgzPTW~HxaMyEqQm3V109hQkHC6yhs0LxN9M79AHKmHOH~nEegwLSRWluklfNRTONNLgCarP8yEUVyG3cfbkk47Rz2WaAiLJbX718Lb460EQAkyL31jLMjN8ZTI8Dai93cWEv-XQujC9Y8OeG-dsf6hv7pu87lbAFHatQXIYoV7EjPdbeR0C1d3PXs4bUk6QysX-8YLE5uKzenpvk2VX49gC-jQ6Zf-3tM7iFzGWtQJdyg__