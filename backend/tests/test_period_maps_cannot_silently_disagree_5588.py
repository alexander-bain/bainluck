"""#5588 — two maps answer "how many periods does this sport have".

`sport_keys.EXPECTED_GAME_STATE_INDICATORS` is the documented authority
(CLAUDE.md names `sport_keys.py` as the single source of truth for sport-key
maps) and feeds one diagnostic admin panel. `highlights.SPORT_TOTAL_PERIODS` is
a local copy, and it feeds `parse_game_progress`, which decides the USER-FACING
"Overtime" badge. Two records of one capability, and they had drifted in both
directions.

THE DRIFT THAT MATTERED, AND WHY THE OBVIOUS REPAIR WAS THE WRONG ONE.
The authority said `basketball_wncaab: 2`; the local copy said `4`. Deriving the
local copy from the authority — the clean-looking fix — would have flipped the
badge path to 2 and shipped a regression, because NCAA women's basketball has
played four 10-minute QUARTERS since 2015-16 while the NCAA men's game is still
two 20-minute HALVES. The authority's comment ("halves for college") lumped the
two college games together and that is exactly how the wrong value got in. So
the authority was corrected UP to 4, not the badge path down to 2.

WHAT THIS GUARD IS FOR. Not to re-assert today's numbers — a test that only
restates the map it reads is worth nothing. It asserts the RELATIONSHIP the two
maps must keep, so that changing either one alone fails:

  1. every key they share carries the same value;
  2. the authority is a superset — a sport the badge path knows about cannot be
     missing from the source of truth;
  3. a sport the authority calls variable-round (`None`) can never be given a
     fixed period count by the badge path.

Arm 4 pins the specific pair that was confused, because it is the one a future
editor is most likely to "correct" back.
"""

from app.utils.highlights import SPORT_TOTAL_PERIODS
from app.utils.sport_keys import EXPECTED_GAME_STATE_INDICATORS


def test_shared_keys_agree_on_the_period_count():
    """The invariant the drift broke: one capability, one answer."""
    shared = set(SPORT_TOTAL_PERIODS) & set(EXPECTED_GAME_STATE_INDICATORS)
    assert shared, "the two maps share no keys at all — one of them was renamed"

    disagreements = {
        key: (SPORT_TOTAL_PERIODS[key], EXPECTED_GAME_STATE_INDICATORS[key])
        for key in sorted(shared)
        if SPORT_TOTAL_PERIODS[key] != EXPECTED_GAME_STATE_INDICATORS[key]
    }
    assert not disagreements, (
        "SPORT_TOTAL_PERIODS and EXPECTED_GAME_STATE_INDICATORS disagree "
        f"(badge path, authority): {disagreements}. Decide which is RIGHT before "
        "you make them match — #5588 is the case where the authority was wrong."
    )


def test_the_authority_names_every_sport_the_badge_path_knows():
    """`sport_keys.py` is the documented source of truth, so it cannot be the
    smaller map. This is the direction the drift ran the second time: the badge
    path had `soccer_mexico_ligamx` and `soccer_fifa_world_cup` and the authority
    did not."""
    missing = sorted(set(SPORT_TOTAL_PERIODS) - set(EXPECTED_GAME_STATE_INDICATORS))
    assert not missing, (
        "these sports have a period count in the badge path but are absent from "
        f"the authority: {missing}"
    )


def test_a_variable_round_sport_is_never_given_a_fixed_period_count():
    """`None` in the authority means "no fixed regulation" — tennis, golf, MMA,
    boxing. Giving such a sport an integer total in the badge path is what lets
    `parse_game_progress` assert a game is past regulation when that sentence has
    no meaning for it."""
    variable_round = {
        key for key, total in EXPECTED_GAME_STATE_INDICATORS.items() if total is None
    }
    contradicted = sorted(variable_round & set(SPORT_TOTAL_PERIODS))
    assert not contradicted, (
        "the authority calls these variable-round, but the badge path gives them a "
        f"fixed period count: {contradicted}"
    )


def test_the_two_college_basketball_games_are_not_the_same_shape():
    """The specific confusion #5588 was filed about, pinned in both maps.

    A future editor reading "college basketball plays halves" will be tempted to
    put `basketball_wncaab` back to 2. It has been 4 since the 2015-16 season.
    """
    assert SPORT_TOTAL_PERIODS["basketball_ncaab"] == 2, "NCAA men play two halves"
    assert (
        SPORT_TOTAL_PERIODS["basketball_wncaab"] == 4
    ), "NCAA women have played four quarters since 2015-16"
    assert EXPECTED_GAME_STATE_INDICATORS["basketball_ncaab"] == 2
    assert EXPECTED_GAME_STATE_INDICATORS["basketball_wncaab"] == 4
