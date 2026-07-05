Starting the Event Matching Ground Truth Sweep. I'll systematically capture today's sports events from Kalshi, Polymarket, and bainluck.com. Beginning with Kalshi's sports section.

I can see the Kalshi sports page is showing Baseball games. I can see "PRO BASEBALL 3 OF 16" in the top carousel showing games like "New York M vs Atlanta", "Pittsburgh vs Washington", "Baltimore vs Cincinnati". I need to scroll down to see the full list of MLB games. Let me navigate directly to the Pro Baseball category and use the Kalshi API for more efficient data collection.

Kalshi data collection complete. Found 15 MLB games today (no NBA or NHL games - both offseason). Now moving to Polymarket to find matching markets.

The Event Matching Ground Truth Sweep is complete. Here's a summary of findings:

**Layer 1 — Games Today:**
- **MLB**: 15 games found on both Kalshi and Polymarket (perfect 1:1 match)
- **NBA**: No games today (offseason)
- **NHL**: No games today (offseason)

**Layer 4 — Deep Audit (3 games):**
Since NBA and NHL are both in offseason, all 3 deep audit games are MLB:
1. **NYM vs ATL** — 10 Kalshi market types (78 outcomes), 6 Polymarket market types
2. **SD vs LAD** — 10 Kalshi market types (120 outcomes), 6 Polymarket market types  
3. **CWS vs CLE** — 10 Kalshi market types, 6 Polymarket market types

Kalshi series found: KXMLBGAME, KXMLBTOTAL, KXMLBSPREAD, KXMLBHIT, KXMLBHR, KXMLBRBI, KXMLBSB, KXMLBF5, KXMLBTB, KXMLBTEAMTOTAL

**Layer 3 — Bainluck Event Detail:**
- Championship (World Series) odds: ✓ Present on all 3
- Conference/Pennant (NL/AL Champ): ✓ Present on all 3
- Division odds: ✓ Present on all 3
- Make Playoffs: ✓ Present on all 3
- Player awards: Not shown on event detail pages
- Wrong-sport leaks: None detected
- Player headshots: Not present (team logos only)
- Team filter pills: Not present on event pages

The JSON output file is attached below.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/Z8ALZ2qyMpFGSGcoRZS7He/sandbox/8jGazYdAxkJa7O0plgHbwJ_1783242644242_na1fn_L2hvbWUvdWJ1bnR1L2dyb3VuZF90cnV0aF9zd2VlcA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvWjhBTFoycXlNcEZHU0djb1JaUzdIZS9zYW5kYm94LzhqR2F6WWRBeGtKYTdPMHBsZ0hid0pfMTc4MzI0MjY0NDI0Ml9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJkeWIzVnVaRjkwY25WMGFGOXpkMlZsY0EuanNvbiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTgzMDI5NzYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=nTVDCy-YrkNyinNfwJrl2sjyu0GMWs6homU1~~ZCc6BX~nRRrVlmR14uRpLDaAyLD~uVt9-89LFz2DeLGaqmXjCe8GiLNdQBbggnHSrOCnsnGV4AycOPYIsG8tmaXmmEjLOJAcx609twdlgpRAsxI-8pfQo7eyHG8ck6PjUJTTCH4YS~eHDkjr12beyPyb0omJMeslRvOgrrXrxBVP2XidCtBD2W7fVdlubqXbnLs7yCaO1E1JEwZ9-q8-etHZMrxrYAIB4bLStxvlzCIgv4FlGPD~pJpEV5nZQnGtkTbw2I-De9Tt7kOCuyfkaw-LLaYoS44o03YYJHmkyzDnt9nw__