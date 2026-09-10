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


# #4728 — the SECOND consumer of the map above, and the reason it is keyed by sport.
#
# The backfill puts these aliases into `teams.alternate_names`, which is enough for
# the TEAM row to resolve: production 2026-09-10 answers `?q=pats` with the New
# England Patriots team, `?q=revs` with the Revolution, `?q=niners` with the 49ers.
# It is NOT enough for the team's MARKETS, because market names come from the venue
# and no venue writes "pats". Measured the same morning on open futures:
#
#     query    markets whose name contains the query   the team's real markets
#     pats     3   (all Kor*pats*ch WTA doubles)       31
#     revs     0                                       15
#     niners   0                                       36
#     bucs     5   (all Cristina *Bucs*a WTA tennis)   41
#
# So a fan typing their team's nickname gets ZERO of their team and, worse, a
# handful of unrelated tennis players whose surname happens to contain it.
#
# WHY A SPORT SCOPE, AND WHY IT IS NOT OPTIONAL. The obvious repair — expand `pats`
# to `patriots` — re-creates exactly the fan-out this map's key was designed to
# prevent. Of 53 open `%patriot%` markets on 2026-09-10 only 31 are New England's;
# the other 22 are Caribbean Premier League cricket (St. Kitts and Nevis Patriots),
# Boyaca Patriotas, and the Patriot League. Matching the PLURAL token drops the
# Patriotas and the League on spelling alone, but 15 cricket rows survive it — a
# 15/46 false-positive rate served to a Patriots fan. Scoping the arm to the
# franchise's own sport takes it to 0/31. `revs`, `niners` and `bucs` measured 0
# false positives either way; the scope costs them nothing and is what makes the
# mechanism safe to extend to the next nickname, which may not be so lucky.
#
# NOT A PREFIX ARM. `pat:*` would match `patriot` — and also `federico` for `fed`,
# the defect LAT-P033/LAT-P034 closed and LAT-P037 refuses in full. This is a
# curated, name-only, franchise-anchored alias: no prefix, no stemmer change.


def _canonical_market_token(team_name: str) -> str:
    """The word a venue actually prints for a franchise: the last of its name.

    "New England Patriots" -> "Patriots", "San Francisco 49ers" -> "49ers". Venues
    name games "Jets vs. Patriots" and "SF 49ers vs LA Rams" — the CITY is the part
    they drop, so the last word is the token that reaches market names. Pinned
    value-by-value in `test_team_nickname_search_expansions.py` so a future entry
    whose last word is wrong fails a test rather than quietly under-matching.
    """
    return team_name.split()[-1]


def team_nickname_search_expansions() -> dict[str, tuple[str, str]]:
    """`alias -> (canonical market token, llm_sport_category)` for search recall.

    Derived from `CURATED_TEAM_ALIASES` so there is ONE place to add a nickname.
    Pure — no DB, no I/O — so the guard tests pin it directly.

    Aliases that are already a SUBSTRING of their token are skipped: `9ers` is
    inside `49ers`, so the plain ILIKE arm already reaches those rows (verified on
    production — `?q=9ers` returns 10 real 49ers markets today, while `?q=niners`
    returns 0). An arm for them would be duplicate work for zero extra recall, the
    same reasoning `_phrase_alias_alternatives` applies to identical alternatives.
    """

    from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY

    expansions: dict[str, tuple[str, str]] = {}
    for (sport_key, team_name), aliases in CURATED_TEAM_ALIASES.items():
        category = SPORT_PREFIX_TO_LLM_CATEGORY.get(sport_key.split("_")[0])
        if not category:
            # An unmapped sport prefix means we cannot scope the arm, and an
            # UNSCOPED arm is the fan-out this map exists to prevent. Skip it:
            # the alias keeps working for the team row via `alternate_names`.
            continue
        token = _canonical_market_token(team_name)
        for alias in aliases:
            alias = alias.lower()
            if alias in token.lower():
                continue
            expansions[alias] = (token, category)
    return expansions
