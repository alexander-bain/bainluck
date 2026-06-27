Starting the Event Matching Ground Truth Sweep. I'll systematically capture today's sports events from Kalshi, Polymarket, and bainluck.com. Beginning with Kalshi's sports section now.

Progress update: I've found the Kalshi page structure. The "all sports" page HTML doesn't contain MLB game tickers (they load dynamically on the pro-baseball sub-page). I've identified the ticker format (KXMLBGAME-26JUN271310NYYBOS) and found 15 MLB games today. Now I'll click into individual games to get their tickers, then check NBA and NHL.

Here is the completed Event Matching Ground Truth Sweep. The JSON is valid and contains:

**Layer 1 (All Games Today):**
- 15 MLB games captured from both Kalshi and Polymarket
- NBA and NHL are in offseason (late June) — no games today
- 4 Kalshi tickers confirmed via direct page visits, 11 predicted from established pattern
- 12 Polymarket slugs confirmed from the games listing page

**Layer 4 (Deep Audit — 3 Games):**
- NYY vs BOS, HOU vs DET, TEX vs TOR
- Kalshi markets per game: moneyline, spread (multi-line), total (multi-line), team totals (2), YRFI/NRFI, First 5 Innings (winner + spread), and 8 categories of player props (HR, SO, Hits, H+R+RBI, TB, Outs Recorded, RBI, SB)
- Polymarket markets per game: moneyline, spread, total, YRFI, extra innings, plus tabs for 5 Innings, Home Runs, Strikeouts
- Each Kalshi game shows "43" total contracts

**Layer 3 (bainluck.com Event Detail):**
- Championship path (World Series, AL/NL Champ, Division, Make Playoffs) present for both teams ✓
- Series outcome market present (from Polymarket) ✓
- Trade Watch section present ✓
- No wrong-sport leaks, no duplicates ✓
- Player props NOT displayed on completed games (all 3 audited games had already finished)
- No team filter pills or headshots visible on completed game pages

**Key Finding:** Today is June 27, 2026 UTC morning, but the 1:10 PM ET games have already been played (bainluck shows them as FINAL). This suggests the capture happened after game completion for the early games.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/Cz2UzQdnF7ePDXdTV4AzEF/sandbox/H1L5ZuOGbhldaxkLzs6nDm_1782550362406_na1fn_L2hvbWUvdWJ1bnR1L2dyb3VuZF90cnV0aF9zd2VlcA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvQ3oyVXpRZG5GN2VQRFhkVFY0QXpFRi9zYW5kYm94L0gxTDVadU9HYmhsZGF4a0x6czZuRG1fMTc4MjU1MDM2MjQwNl9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJkeWIzVnVaRjkwY25WMGFGOXpkMlZsY0EuanNvbiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTc5ODc2MTYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=Z3HJQ6KptceK1CNjFgzmIjX40~UUKdY~wYQO1pGFxzboXqfWhmuQgjsW2LWroTe5~-3c7L1fgipTC0hCCr-p0zAv0Fw7fnfvRYJl24qv3ugjx-f5CDC9gJBO490mIzn7E6qTflnS8VgDfSPWI2PR2U3mDpzfHzHOXRoGi2hf9qgiO67uCLkxnZE82qaJgy6rvNtdQHcEK5z4ckxZaoip9RObN098CunCyub7JoSrTLFhkv6x55KuXvrKQgRsBOv3IzlOlAtwQl9V8eEwMAjOyzudVjqqkNY30xzZiq4zML1gAuvDXLN2YgwNxSh~Ajk1Dzj-VqFMTcf7yrDh0lKnqw__