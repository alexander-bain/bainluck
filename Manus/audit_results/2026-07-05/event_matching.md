Starting the Event Matching Ground Truth Sweep. I'll systematically capture today's sports events from Kalshi, Polymarket, and bainluck.com. Beginning with Kalshi's sports section.

Good progress. I've identified the market structure for Kalshi MLB games. I can see the Milwaukee vs Arizona game has these market types: Moneyline (Chance), Spread and Total, Team Totals, Game Lines (Spread, Point Total, YRFI/NRFI, First 5 Innings), Player Props, and Events. Now I'll continue collecting all games and then move to the other platforms.

Here is the completed Event Matching Ground Truth Sweep for July 5, 2026. The JSON file contains:

**Layer 1 (Games Today):** 6 MLB games on both Kalshi and Polymarket, plus 2 NBA Summer League games (Kalshi only) and 1 WNBA game (Polymarket). NHL and NBA regular season are both in offseason — no games today.

**Layer 4 (Deep Audit):** 3 MLB games fully audited:
1. San Diego Padres vs Los Angeles Dodgers (7:20 PM ET)
2. Boston Red Sox vs Los Angeles Angels (9:30 PM ET)  
3. Milwaukee Brewers vs Arizona Diamondbacks (4:00 PM ET)

Each game on Kalshi has: moneyline, spread (6 lines), total (11 lines), team totals (7 lines each), first 5 innings spread/total, YRFI/NRFI, and player props.

**Layer 3 (bainluck.com):** All 3 event detail pages captured with:
- Championship path (Make Playoffs, Division, AL/NL Champ, World Series) ✓
- Player props (7-13 cards per game) with no headshots (text only)
- No wrong-sport leaks detected
- No team filter pills visible on these pages
- No awards shown on individual game pages

The JSON is valid and complete.


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/hkVKEJqQEnXuDDaCSj5TWU/sandbox/UJXcqYqpIAFr8iukKCN8aQ_1783293401647_na1fn_L2hvbWUvdWJ1bnR1L2dyb3VuZF90cnV0aF9zd2VlcA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvaGtWS0VKcVFFblh1RERhQ1NqNVRXVS9zYW5kYm94L1VKWGNxWXFwSUFGcjhpdWtLQ044YVFfMTc4MzI5MzQwMTY0N19uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJkeWIzVnVaRjkwY25WMGFGOXpkMlZsY0EuanNvbiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTgzMDI5NzYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=b6UYJguYvMP~WzfhQ8XjHGzbjArL9TPbTIqqbSzjeh6P7ajIFvBZQmzWID954DN7MuS7t1Ajnnaqsiu4PlNHWeB95tBaxMHbEG0Uz0X5EhahwHVxNhOeJ81GnFnRfqRTa06DdjpMKc-oMcB5CwVCfJmzMi9muEEwiYPd6SJony8XLeS9XW1noXt4EIS313RgB3uw90AOW6dusK1hXiLchu3p5vayrUIjve4n2ATMATb9hJRRqNycN3XvuSq27kEk2y~WlFiJjMJbWyR3rE4u7RMFOltuF0kE5jj8lzEtZz1IFuahZKhrZNGFlqfKBds4Glw56MEuPzXvepbY95ZS6A__