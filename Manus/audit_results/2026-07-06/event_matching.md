Starting the Event Matching Ground Truth Sweep. I'll systematically capture today's sports events from Kalshi, Polymarket, and bainluck.com. Beginning with the Kalshi game sweep.

Found the first MLB game with detailed market structure. I can see the game page has Moneyline (Chance), Spread and Total, and Team Totals sections. Now I'll continue sweeping all MLB games and check for NHL. I notice there's no NBA (offseason) but WNBA games exist.

Here is the completed Event Matching Ground Truth Sweep for July 6, 2026. The JSON file is valid and contains:

**Layer 1 (All games today):**
- 8 MLB games on both Kalshi and Polymarket
- 3 WNBA games on both Kalshi and Polymarket
- NBA and NHL are both in offseason — no games today

**Layer 4 (Deep audit — 3 games):**
1. **PHI vs KC (MLB)** — 15 Kalshi market types (119 total outcomes), 10 Polymarket market types
2. **NYY vs TB (MLB)** — 15 Kalshi market types (97 total outcomes), 8 Polymarket market types  
3. **GS Valkyries vs WSH Mystics (WNBA)** — 3 Kalshi market types (20 outcomes), 3 Polymarket market types

**Layer 3 (bainluck.com):**
- PHI vs KC event detail page fully audited (event ID 14970501)
- Championship path, division, make playoffs, and player awards all present
- 7 player prop cards (strikeouts only — Luinder Avila, Aaron Nola)
- No wrong-sport leaks, no duplicates
- Player headshots: initials only (no photos)
- Team filter pills: not present on event detail page
- NYY/TB and WNBA games not yet listed in bainluck's "Today's Games" section

**Key findings:**
- Kalshi uses a consistent ticker pattern: `KX{SPORT}{TYPE}-26JUL06{TIME}{TEAMS}`
- Polymarket uses slug pattern: `{sport}-{away}-{home}-2026-07-06`
- All 8 MLB games match 1:1 between Kalshi and Polymarket
- Bainluck only shows 3 of 8 MLB games in its "Today's Games" feed (possible data lag)


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/UUUjcyQHeaaXBfqwkgJZ2c/sandbox/03xF1Gp40bUgY90FmM3B3p_1783346396716_na1fn_L2hvbWUvdWJ1bnR1L2dyb3VuZF90cnV0aF9zd2VlcA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvVVVVamN5UUhlYWFYQmZxd2tnSloyYy9zYW5kYm94LzAzeEYxR3A0MGJVZ1k5MEZtTTNCM3BfMTc4MzM0NjM5NjcxNl9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJkeWIzVnVaRjkwY25WMGFGOXpkMlZsY0EuanNvbiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTgzMDI5NzYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=ndan7PkYZBorq2FSdl4~sOzcJWfXC-YcZ2ALzfMDg3v12Oq6A8-4YY5oXpaT2B8VVFyErKeN~0lFBBQMXBRI8RspanhU6L23ayPJ4VNkdDo6Cd-QZpcyvMsiP-zmDzlRZICtjiY2nm4g5pZBkFyb7gjBgPzY3TulvsJoaeMAeu~5xdm0~glU~dBfTYRH513dE7t3Gf8w5wjBVd0nXHRaSGS-SQOGDdFKGBnn2KNRnIJo3QiHOLuKY3cvfBzUGMk4SQ~VGDSvInzmo4ZJjC4cf1-CA0WqOz0Qif3JvJWpaxAVSuJ2RxQ6rrRNuwgtBM92BXkitFYS5k7FYh-Dkc3dLg__