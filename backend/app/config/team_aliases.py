"""Curated search aliases for major teams — the durable data-side backfill for
`teams.alternate_names` (Queue #246 Item 1a).

Why this exists: bare colloquial nicknames ("pats", "revs") are how casual fans
type a team, but they are NOT in the ESPN/odds-provider alt-name sets, so search
misses them. The ESPN syncs UNION into `alternate_names` (they never overwrite an
existing entry — see `espn_helpers.upsert_team` / `espn_sync._backfill_team_logos`),
so curated aliases added here survive routine syncs.

Keyed by **(sport_key, canonical_team_name)** on purpose — there are multiple
"Patriots" (NFL New England, NCAA George Mason / Dallas Baptist), so a bare
"pats" must attach to the NFL franchise ONLY, never fan out across leagues.

Extend this map (that is its job) — add the (sport_key, name) → [aliases] rows,
then re-run `scripts/backfill_curated_team_aliases.py --apply`. Keep aliases
UNAMBIGUOUS: an alias that matches two franchises makes search worse, not better.
"""

# (sport_key, canonical_team_name) -> list of lowercase colloquial aliases.
CURATED_TEAM_ALIASES: dict[tuple[str, str], list[str]] = {
    ("americanfootball_nfl", "New England Patriots"): ["pats"],
    ("soccer_usa_mls", "New England Revolution"): ["revs"],
    ("americanfootball_nfl", "San Francisco 49ers"): ["niners", "9ers"],
    ("americanfootball_nfl", "Tampa Bay Buccaneers"): ["bucs"],
    ("basketball_nba", "Philadelphia 76ers"): ["sixers"],
}
