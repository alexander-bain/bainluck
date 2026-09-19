"""Two maps answer "how many periods does this sport have" — they must agree (#5588).

`sport_keys.EXPECTED_GAME_STATE_INDICATORS` is the documented single source of
truth (CLAUDE.md). `highlights.SPORT_TOTAL_PERIODS` is a second, local copy that
feeds `parse_game_progress`, which decides the user-facing overtime badge. Two
maps answering one question drifted in both directions before this guard:

* a DISAGREEMENT — the authority said `basketball_wncaab` had 2 periods while
  highlights said 4. Highlights was right: the women's college game has played
  four 10-minute quarters since 2015-16, and every one of the 55 distinct
  `basketball_wncaab` period labels on production last season is a quarter.
* a HOLE — `soccer_mexico_ligamx` and `soccer_fifa_world_cup` existed only in
  the local copy, so the authority did not know two sports the code did.

🔴 **Why this is a guard and not a derivation.** The obvious repair — delete the
local map and derive it from the authority — is the one thing that must not be
done casually, and this docstring is here so the next reader does not try it.
Measured for #5588 by running the shipped `parse_game_progress` over the real
production labels under both denominators: with the authority's wrong value of
2, **10 of 17 distinct labels change**, and every 3rd- and 4th-quarter women's
game reports `(1.0, True)` — 100% elapsed and badged OVERTIME — instead of
`(0.625, False)` / `(0.875, False)`. Deriving from an authority that is wrong
ships that to the reader. So the invariant asserted here is AGREEMENT, which is
cheap and always safe; the values themselves still have to be right, and this
test cannot tell you that they are.

The direction of the assertion matters. The authority is allowed to know sports
the local map does not (it carries the variable-round sports as `None`, plus
leagues highlights has no opinion on). The reverse is a defect: a key in the
local copy with no entry in the authority means the authority is incomplete.
"""

from app.utils.highlights import SPORT_TOTAL_PERIODS
from app.utils.sport_keys import EXPECTED_GAME_STATE_INDICATORS


def test_no_key_in_the_local_map_is_unknown_to_the_authority():
    """A sport the badge path knows must exist in the documented authority."""
    missing = sorted(set(SPORT_TOTAL_PERIODS) - set(EXPECTED_GAME_STATE_INDICATORS))
    assert missing == [], (
        "these sports have a period count in highlights.SPORT_TOTAL_PERIODS but "
        f"no entry in the authority sport_keys.EXPECTED_GAME_STATE_INDICATORS: {missing}. "
        "Add them to the authority — a hole there is what let the two maps drift."
    )


def test_the_two_period_maps_never_disagree():
    """Where both maps name a sport, they must answer with the same number."""
    disagreements = {
        key: {
            "authority": EXPECTED_GAME_STATE_INDICATORS[key],
            "highlights": SPORT_TOTAL_PERIODS[key],
        }
        for key in set(SPORT_TOTAL_PERIODS) & set(EXPECTED_GAME_STATE_INDICATORS)
        if EXPECTED_GAME_STATE_INDICATORS[key] != SPORT_TOTAL_PERIODS[key]
    }
    assert disagreements == {}, (
        "sport_keys.EXPECTED_GAME_STATE_INDICATORS and highlights.SPORT_TOTAL_PERIODS "
        f"disagree about how many periods these sports have: {disagreements}. "
        "Decide which is right against real period labels on production before "
        "changing either — highlights feeds the user-facing overtime badge."
    )


def test_the_college_basketball_games_are_not_conflated():
    """The specimen of #5588, pinned by name so a re-conflation is loud.

    The men's and women's college games genuinely differ, so a future edit that
    "tidies" them to one shared value is the exact regression this issue was.
    """
    assert EXPECTED_GAME_STATE_INDICATORS["basketball_ncaab"] == 2, (
        "men's college basketball plays two 20-minute halves and ESPN reports halves"
    )
    assert EXPECTED_GAME_STATE_INDICATORS["basketball_wncaab"] == 4, (
        "women's college basketball has played four 10-minute quarters since "
        "2015-16 and ESPN reports quarters — every wncaab period label measured "
        "on production is a quarter, none is a half"
    )
