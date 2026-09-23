"""#8084 — "North Carolina St." finds the Wolfpack crest it has been missing.

Arm C taught the grid to expand a college feed's "Ohio St." into the key
`ohio state` that a row already held. `North Carolina St.` expands the same way,
to `north carolina state` — and NO ROW HOLDS THAT KEY, because ours are all
spelled `NC State Wolfpack`. So the read side has been asking a question the data
cannot answer, and the row renders as bare text on two grids.

Measured on production 2026-09-22 over the 398 rows the 13 warm grids serve:
11 rows resolve to no metadata, two of them `North Carolina St.` —
/playoffs/ncaa-women-basketball (30 rows) and /playoffs/ncaa-football (40 rows),
both `team_id=None, logo=N, record=None`.

This is the alias half. It adds no route code at all: `_secondary_claims` already
feeds `teams.alternate_names` into the grid's lookup, so minting the key is the
whole fix.
"""
from app.config.team_aliases import (
    CURATED_TEAM_ALIASES,
    _alias_claim_counts,
    team_nickname_event_expansions,
    team_nickname_search_expansions,
)
from app.utils.name_normalization import (
    normalize_team_name,
    normalize_team_name_for_matching,
)
from scripts.backfill_curated_team_aliases import merge_aliases

ALIAS = "north carolina state"
CLUB = "NC State Wolfpack"

# The three rows this alias is for, and the one it is not. All four are named
# `NC State Wolfpack`; only the first three carry NC State's own espn anchor.
NCSU_SPORTS = {"basketball_wncaab", "americanfootball_ncaaf", "basketball_ncaab"}
EXCLUDED_SPORT = "baseball_ncaa"  # row 3211, espn 95 — a different anchor (#7727)


def test_alias_mints_exactly_the_key_the_grid_asks_for():
    """THE LOAD-BEARING ASSERTION: the two normalizers meet on one string.

    The grid's third rung (arm C) looks up the COLLEGE form of the feed's label;
    the alias is written into `alternate_names` and indexed under the PLAIN form.
    The fix works only because those two produce the same key — assert the meeting
    point rather than either side alone, because either one changing silently
    un-does this without touching this file.
    """
    grid_asks_for = normalize_team_name_for_matching("North Carolina St.")
    alias_is_indexed_under = normalize_team_name(ALIAS)
    assert grid_asks_for == alias_is_indexed_under == ALIAS


def test_the_feed_spelling_does_not_already_reach_the_club_without_the_alias():
    """Proves the alias is load-bearing and not decoration.

    `NC State Wolfpack` normalizes to neither form of the feed's label, so nothing
    the row already carries answers the grid's question. If this ever stops being
    true the alias is redundant and should be removed, not kept on faith.
    """
    for form in (normalize_team_name(CLUB), normalize_team_name_for_matching(CLUB)):
        assert form != ALIAS
    assert normalize_team_name("NC State") != ALIAS


def test_all_three_ncsu_rows_carry_the_alias_and_baseball_does_not():
    claimed = {
        sport for (sport, name) in CURATED_TEAM_ALIASES if name == CLUB
    }
    assert claimed == NCSU_SPORTS
    assert (EXCLUDED_SPORT, CLUB) not in CURATED_TEAM_ALIASES
    for sport in NCSU_SPORTS:
        assert CURATED_TEAM_ALIASES[(sport, CLUB)] == [ALIAS]


def test_the_union_preserves_a_contaminated_row_rather_than_repairing_it():
    """Row 735's real `alternate_names` on production 2026-09-22.

    It claims `Iowa` and `Iowa Hawkeyes` while being NC State — a #7727 specimen
    sitting in the very row this change edits. The backfill is union-only, so the
    alias lands and the contamination is left exactly as found: this issue does not
    own that defect, and a write that quietly "tidied" it would be an unreviewed
    repair of someone else's bug hidden inside an alias change.
    """
    real_735 = ["Iowa", "NC State", "Hawkeyes", "Iowa Hawkeyes", "Wolfpack"]
    merged = merge_aliases(real_735, [ALIAS])
    assert merged == real_735 + [ALIAS]
    assert merged[: len(real_735)] == real_735  # nothing reordered or dropped


def test_union_is_idempotent_on_the_real_rows():
    for existing in (["NC State", "Wolfpack"], ["Wolfpack", "NC State"]):
        once = merge_aliases(existing, [ALIAS])
        assert merge_aliases(once, [ALIAS]) == once
        assert once[-1] == ALIAS


def test_search_and_game_card_expansions_are_byte_identical_to_before():
    """The entry must not move search at all — asserted against pinned values.

    Captured from the tree immediately before this change. Pinned literally rather
    than recomputed, so a regression in the skip rule shows up as a diff here
    instead of both sides moving together.
    """
    assert team_nickname_search_expansions() == {
        "pats": ("Patriots", "football"),
        "revs": ("Revolution", "soccer"),
        "niners": ("49ers", "football"),
        "bucs": ("Buccaneers", "football"),
        "sixers": ("76ers", "basketball"),
    }
    assert team_nickname_event_expansions() == {
        "pats": ("Patriots", "americanfootball_nfl"),
        "revs": ("Revolution", "soccer_usa_mls"),
        "niners": ("49ers", "americanfootball_nfl"),
        "9ers": ("49ers", "americanfootball_nfl"),
        "bucs": ("Buccaneers", "americanfootball_nfl"),
        "sixers": ("76ers", "basketball_nba"),
    }


def test_the_contested_alias_is_refused_by_both_derived_maps():
    assert _alias_claim_counts()[ALIAS] == 3
    assert ALIAS not in team_nickname_search_expansions()
    assert ALIAS not in team_nickname_event_expansions()


def test_an_uncontested_alias_is_still_expanded():
    """The control for the refusal above.

    `sixers` is claimed once and DOES appear, so the skip is discriminating between
    contested and uncontested aliases rather than dropping everything — which is
    the reading under which the previous test would pass for the wrong reason.
    """
    counts = _alias_claim_counts()
    assert counts["sixers"] == 1
    assert team_nickname_search_expansions()["sixers"] == ("76ers", "basketball")
    assert team_nickname_event_expansions()["sixers"] == ("76ers", "basketball_nba")


def test_no_other_club_in_the_map_claims_this_alias():
    """#7727's rule in miniature: an alias may not be another club's identity."""
    for (_sport, name), aliases in CURATED_TEAM_ALIASES.items():
        if ALIAS in aliases:
            assert name == CLUB
