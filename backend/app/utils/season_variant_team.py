"""Which of two rows for one club a reader is served (#2498).

`sports` holds a league and its SEASON VARIANT as two rows — `baseball_mlb` and
`baseball_mlb_preseason`, `americanfootball_nfl` and its `_preseason`,
`basketball_nba` and `basketball_nba_summer_league`. `utils.sport_keys` already
names that relationship (`is_season_variant`, `league_identity`, #4945/#1798)
and its docstring already states the preference: *"Callers that must choose ONE
row per league prefer the parent."* This module is the part that lets a caller
act on it, and nothing more.

## What it is for, measured

Production 2026-09-11 22:2xZ. `teams` carries 30 `baseball_mlb_preseason` clubs,
and **all 30 hold the clean slug** — `boston-red-sox` is the spring row (853,
`current_record` 13-15, `standings_data` NULL), while the club playing a pennant
race is `boston-red-sox-mlb` (10709, 80-67, standings present). So
`/api/teams/boston-red-sox` served a 13-15 record in September, with the
breadcrumb reading "MLB PRESEASON", which is #2498 exactly as Alex filed it.

MLB is alone in this: the 32 `americanfootball_nfl_preseason` and 29
`basketball_nba_summer_league` rows carry **no** `espn_id`, so none of them ever
won a slug from its parent, and `/sport/football/nfl/team/houston-texans`
already renders the real NFL row.

## The whole rule is the shared id

The 30 MLB pairs share their `espn_id`, both directions. That is what makes
preferring the parent safe to do at the serving boundary: the correspondence is
ID-ANCHORED, so this never reasons about names or kickoff times and ruling 048's
prohibition on name-and-time absorption is not in play. Nothing here writes, and
nothing here merges — the two rows both survive; one of them stops being what a
URL resolves to.

## Ambiguity DECLINES, it does not guess

`espn_id=24` maps to two `baseball_mlb` rows: `10740 "St. Louis Cardinals"` and
`13437 "St.Louis Cardinals"`, no space — the variant of #4865 / native-098, and
#1798's duplicate to drain. With two candidates this returns `None` and the
caller serves whatever it already found, so the Cardinals keep the spring row
until #1798 lands: **29 of 30**. Picking one of the two on a content hunch (say,
"the one with standings") would be a second matcher deciding an identity
question, which is the failure ruling 048 exists to end. Declining is the
answer, and it is the reason this returns an Optional rather than a best guess.

Zero candidates declines for the same reason, and that is the common path: every
non-variant team on the site takes it in one `is_season_variant` call, before any
query is considered.
"""

from typing import Iterable, Optional, Tuple

from app.utils.sport_keys import is_season_variant, league_identity

#: `(row id, sport key)` for one candidate row.
Candidate = Tuple[int, Optional[str]]


def wants_parent_league_row(sport_key: Optional[str]) -> bool:
    """True when a row under `sport_key` should defer to its parent league.

    The cheap gate, and the only thing a caller has to run for the vast majority
    of teams: a row that is not a season variant is already the canonical row for
    its league, so no lookup is worth doing.
    """
    return is_season_variant(sport_key)


def choose_parent_league_row(
    variant_sport_key: Optional[str],
    candidates: Iterable[Candidate],
) -> Optional[int]:
    """The one parent-league row that `variant_sport_key`'s row defers to.

    `candidates` are rows already proven to correspond to the variant row by a
    SHARED PROVIDER ID — this function does not establish correspondence, it only
    picks among rows the caller has established it for. Feeding it rows matched
    by name would make it a name-and-time absorber, which ruling 048 forbids.

    Returns the row id when EXACTLY ONE candidate is a non-variant row in the
    same league, and `None` in every other case: not a variant, no candidate,
    or more than one. See the module docstring for why more-than-one declines
    rather than choosing.
    """
    if not is_season_variant(variant_sport_key):
        return None
    identity = league_identity(variant_sport_key)
    if identity is None:
        return None

    matches = [
        row_id
        for row_id, sport_key in candidates
        # Not another variant: `baseball_mlb_preseason` must never defer to
        # a second variant of its own league, only to the parent.
        if not is_season_variant(sport_key)
        # Same league. `league_identity` collapses the variant suffix AND the
        # `SPORT_LEAGUE_MAP` aliases, so this is the comparison that answers
        # "one league?" — `sport_id` cannot (#4945).
        and league_identity(sport_key) == identity
    ]
    if len(matches) != 1:
        return None
    return matches[0]
