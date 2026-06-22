Starting the Event Matching Ground Truth Sweep. I'll systematically capture today's sports events from Kalshi, Polymarket, and bainluck.com. Beginning with Kalshi's sports section now.

Progress update: I've found today's MLB games on Kalshi (NYY vs DET at 6:10pm EDT, BAL vs LAA at 9:38pm EDT). NBA and NHL are in their offseasons with no games today. Now checking for any additional MLB games and moving to Polymarket.

Progress: Completed Layer 1 sweeps on both Kalshi and Polymarket. Found 13 MLB games today on both platforms. NBA and NHL are in offseason with no games. Now performing deep audits on 3 selected games. Since only MLB is available, I'll pick 3 MLB games: NYY vs DET, BAL vs LAA, and LAD vs MIN.

Here is the completed Event Matching Ground Truth Sweep for June 22, 2026. The JSON file is valid and contains:

**Layer 1 (Games Today):** 13 MLB games captured from both Kalshi and Polymarket with full tickers and URLs. NBA and NHL are both in their offseasons with no games today.

**Layer 4 (Deep Audit):** 3 MLB games audited in detail:
1. NYY vs DET — 5 market types on Kalshi, 8 on Polymarket (including player props for HR and strikeouts)
2. LAD vs MIN — 5 market types on Kalshi, 3 on Polymarket
3. BAL vs LAA — 5 market types on Kalshi, 3 on Polymarket

**Layer 3 (bainluck.com):** Event detail pages are currently minimal — no player props section, no "Related Futures" or "Bigger Picture" section exists on any of the pages. Odds show 50/50 (not yet populated from sources). Only basic additional markets (NRFI, moneyline) are visible.

**Key observations:**
- Kalshi ticker format: `KXMLBGAME-26JUN22[HHMM_EDT][AWAY_ABBR][HOME_ABBR]`
- Polymarket slug format: `mlb-[away]-[home]-2026-06-22`
- Kalshi game pages show 5 market types: moneyline, spread, total, team total (away), team total (home)
- Polymarket game pages show more variety: moneyline, spreads, totals, first inning run, extra innings, 5-inning winner, HR props, strikeout props


**Attachment:** None — https://private-us-east-1.manuscdn.com/sessionFile/Rs4VYPWRd2nsobvQgopQjg/sandbox/dUwE7g4eaWaqCi71SUObSb_1782142340261_na1fn_L2hvbWUvdWJ1bnR1L2dyb3VuZF90cnV0aF9zd2VlcA.json?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvUnM0VllQV1JkMm5zb2J2UWdvcFFqZy9zYW5kYm94L2RVd0U3ZzRlYVdhcUNpNzFTVU9iU2JfMTc4MjE0MjM0MDI2MV9uYTFmbl9MMmh2YldVdmRXSjFiblIxTDJkeWIzVnVaRjkwY25WMGFGOXpkMlZsY0EuanNvbiIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTc5ODc2MTYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=X549dFxth3JQBw7LpjyVAAiASsJxCFwjrY7GY0~hvoWdSkTIJqUTfF3pbRvtXep9IVuRq3N2lrZiBWbXR03P6d44Zsxx0toQTs8h~qsDoXxaerm1XIDOLRNvvbNQhpDtMchrq-CNW16ZXAzxWEZatVyX6T-AMcu~zdm1XX99LKHQoNH9bl9PZ1fkOQPlCzHGl8cInd2Pmts-4FtnFGhiXmROlP9Fc6Rpdnw~IO1DaiVfmiZMdvX9j7dHbpvOxnrNQyQZqwvqxqRci0oh9hm2CyySUUa1s6cZnEs~BywOA098JFUwxO15GyXKWjUylKFiHvKogGTLUbpURuMcNh~qCw__