Starting the Event Matching Ground Truth Sweep. I'll systematically capture today's sports events from Kalshi, Polymarket, and bainluck.com. Beginning with Kalshi's sports section now.

Found 15 MLB games on Kalshi for today. Now checking for NBA and NHL games, then moving to Polymarket.

Completed Layer 1 sweep. Key findings: MLB has 15 games today on both Kalshi and Polymarket. NBA is in offseason (no games, only NBA Finals history on Polymarket and futures on Kalshi). NHL season is over (no active games). NBA Summer League has 4 games on Kalshi but not on Polymarket. 

Since only MLB has games today, I'll select 3 MLB games for the deep audit. Now proceeding to Layer 4 deep audit on Kalshi for 3 selected games: (1) Mets vs Braves, (2) Twins vs Yankees, (3) Rays vs Astros.

Here is the completed Event Matching Ground Truth Sweep for July 5, 2026. The JSON file contains:

**Layer 1 (All Games Today):** 15 MLB games captured from both Kalshi and Polymarket with full tickers, slugs, and URLs. NBA and NHL are both in offseason with no active game markets.

**Layer 4 (Deep Audit - 3 Games):** 
- NYM @ ATL (12:30 PM ET)
- MIN @ NYY (1:35 PM ET)  
- TB @ HOU (3:30 PM ET)

Each game's Kalshi markets (5 market types: moneyline, spread, total, 2 team totals) and Polymarket markets (Game Lines, 5 Innings, Home Runs, Strikeouts tabs with ~19+ individual markets per game) are documented.

**Layer 3 (bainluck.com):** Event detail pages show Win Probability charts, Additional Markets (player props from Polymarket), and a "Bigger Picture" section with championship path odds (Make Playoffs, Division, AL/NL Champ, World Series). No player headshots, no team filter pills, no awards on event pages (awards are on the league page instead).

**Key Observations:**
- Kalshi ticker format: `KXMLBGAME-26JUL05{HHMM}{AWAY}{HOME}`
- Polymarket slug format: `mlb-{away}-{home}-2026-07-05`
- Kalshi does NOT show player props on game pages
- Polymarket shows extensive player props (HR, strikeouts) on game pages
- bainluck aggregates from multiple sources and shows ~9 player props per game in the "Additional Markets" section


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/ECcsty5ujfwGZBXtvFQo8W/sandbox/Mm7LDl2MzO0VPxQh4a46bq_1783265187978_na1fn_L2hvbWUvdWJ1bnR1L2dyb3VuZF90cnV0aF9zd2VlcA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvRUNjc3R5NXVqZndHWkJYdHZGUW84Vy9zYW5kYm94L01tN0xEbDJNek8wVlB4UWg0YTQ2YnFfMTc4MzI2NTE4Nzk3OF9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJkeWIzVnVaRjkwY25WMGFGOXpkMlZsY0EuanNvbiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTgzMDI5NzYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=XcCzmxqt07gWrcQ5kXRVLD9LkGeUVPryHXnqU5ER8P4FYL6NwQttu9I2DZwhVpWOsvckC4MRfoY5u29z7ezBpAI16euMkF5y6weGTqQr3ENkbbfsyLwpy7XJWXE6-LhmgJeav6q5EqzcyteLtDXvOFTCR2aCRqalaQbPFbaq95pOEkTPzYT6PUP16A~L-k3eSRq1noBBrNiyvUOsyPLzyE~lqouMxYXKNeBOYwNOiW6c86Mqe1ZFH6HYs81KF-Xd4AfvNOkUP2zOAPw76~M5DBDiBoWeNND48BQVsBnU3Pt-YB-GWE4a~BG-tt4TQ8B8mTPZ1cS8L3Kp3mvOtbMWvw__