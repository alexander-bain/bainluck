Starting the Event Matching Ground Truth Sweep. I'll systematically capture today's sports events from Kalshi, Polymarket, and bainluck.com. Beginning with Kalshi's sports section.

The Kalshi page seems to have rendering issues with the game listings. Let me try using their API to get the data more reliably, and also try a different approach to access the game data.

Here is the completed Event Matching Ground Truth Sweep for June 15, 2026. The JSON file contains:

**Layer 1 (All Games Today):** 10 MLB games captured from both Kalshi and Polymarket. No NBA or NHL games today (both in offseason).

**Layer 4 (Deep Audit - 3 Games):**
1. **TB vs LAD** — 67 Kalshi markets (moneyline, hits, HRs, first 5 innings, total bases) + ~55 Polymarket markets (moneyline, spreads, totals, first inning, extra innings, 5 innings, HR props for 9 players, K props for 2 pitchers)
2. **NYM vs CIN** — 15 Kalshi markets + Polymarket full game lines + props
3. **MIA vs PHI** — 37 Kalshi markets + Polymarket full game lines + props

**Layer 3 (Bainluck Event Detail):**
- MIA vs PHI (`/events/14915815`) and NYM vs CIN (`/events/14916143`) both audited
- "Bigger Picture" section shows: Championship (World Series), Conference/Pennant (AL/NL Champ), Division, Make Playoffs, and Player Awards (MVP) — all correctly scoped to baseball
- No player props section visible on bainluck event pages (no headshots, no team filter pills)
- No wrong-sport leaks or duplicates detected
- TB vs LAD today's game not yet created on bainluck (only yesterday's final exists)

Key finding: Kalshi uses 5 series for MLB game markets (KXMLBGAME, KXMLBHIT, KXMLBHR, KXMLBF5, KXMLBTB). Polymarket organizes under tabs (Game Lines, 5 Innings, Home Runs, Strikeouts).


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/Xmb6ob3VcgNogdbUjxKQ9c/sandbox/vLZR3IP2L6fDXKoVLHH13t_1781539300767_na1fn_L2hvbWUvdWJ1bnR1L2dyb3VuZF90cnV0aF9zd2VlcA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvWG1iNm9iM1ZjZ05vZ2RiVWp4S1E5Yy9zYW5kYm94L3ZMWlIzSVAyTDZmRFhLb1ZMSEgxM3RfMTc4MTUzOTMwMDc2N19uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJkeWIzVnVaRjkwY25WMGFGOXpkMlZsY0EuanNvbiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTc5ODc2MTYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=Xax9XFUoj8DSMRQqOEggUq4PX7yrE-pw5yhIY3U8kkaphyAquvxQicP6ooU9F8TtX~yLcnd58qvOlA4~aa4XtU-JzOZa4C1jr9V~Qu9RKTk4a5HM5EMOAGR1reONCg8cIc3K7P5N9vIB2x~MWPfCVqX4Nd86ZVsp~InduLc1bN7fGaTht6rj2Lh3DOUPkptBlGrJdd~NLlkPD6wq9QFwBwxZ6zmLVNUFX3cRfcQB5e7XYKXdm9uNkOktiri~KbpISDcGBvnddvEnC9JJIjW3ZdA4P-~6MLj97ID56MtK2yZPKYAW-LqJ1vvoRlf0qXB~8QXOFJHNZkAKIWsl6b5fTQ__