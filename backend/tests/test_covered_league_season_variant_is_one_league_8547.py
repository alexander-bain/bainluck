"""#8547 — a season variant beside its parent is one league, so the venue-instant relink can name it.

THE SPECIMEN. Friday 2026-09-25, Orioles @ Yankees doubleheader: game 1
`15318575` (20:05Z) and game 2 `15318665` (23:05Z). PR #8668 put the four
game-2 markets at the head of phase 1.5's venue-instant slice, and on the first
heavy run (21:5xZ) the receipt read `phase15_venue_instant_candidates 5`,
`relinked 1`: the Kalshi ticker KXMLBGAME-26SEP251905BALNYY moved to game 2 and
the three Polymarket rows of group 1053347 (venue 23:05Z) stayed on game 1.

WHY. The Kalshi arm takes its league from the ticker. The Polymarket arm asks
`covered_league_for_matchup(..., unambiguous_only=True)`, and `teams` carries
both clubs under `baseball_mlb` AND `baseball_mlb_preseason` (production
db-query, 2026-09-25), so the shared set was two keys and the resolver declined.

THE RULE. Only a season variant (`_preseason`, `_summer_league`) whose own
parent is also shared collapses into it. Two different leagues stay ambiguous
(#6377's AFL/AFLW is re-asserted here), and a variant alone still names itself.
"""

import pytest

from app.tasks.prediction_market_matching import covered_league_for_matchup


class _Row:
    def __init__(self, name, alternates, sport_key):
        self._values = (name, alternates, sport_key)

    def __iter__(self):
        return iter(self._values)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, statement):
        return list(self._rows)


# Verbatim shape from production `teams` ⋈ `sports`, 2026-09-25.
MLB = [
    _Row("Baltimore Orioles", None, "baseball_mlb"),
    _Row("Baltimore Orioles", None, "baseball_mlb_preseason"),
    _Row("New York Yankees", None, "baseball_mlb"),
    _Row("New York Yankees", None, "baseball_mlb_preseason"),
]
AFL = [
    _Row("Hawthorn Hawks", ["Hawks"], "aussierules_afl"),
    _Row("Hawthorn Hawks", ["Hawks"], "aussierules_aflw"),
    _Row("Brisbane Lions", ["Lions"], "aussierules_afl"),
    _Row("Brisbane Lions", ["Lions"], "aussierules_aflw"),
]
VARIANT_ONLY = [
    _Row("Summer Club A", None, "basketball_nba_summer_league"),
    _Row("Summer Club B", None, "basketball_nba_summer_league"),
]


@pytest.mark.asyncio
async def test_the_doubleheader_pair_names_mlb_for_the_relink():
    got = await covered_league_for_matchup(
        _FakeSession(MLB), "Baltimore Orioles", "New York Yankees",
        unambiguous_only=True,
    )
    assert got == "baseball_mlb", (
        "the Polymarket venue-instant arm is handed None for every MLB matchup "
        "while each club also has a preseason row"
    )


@pytest.mark.asyncio
async def test_the_tie_break_callers_answer_is_unchanged():
    got = await covered_league_for_matchup(
        _FakeSession(MLB), "Baltimore Orioles", "New York Yankees",
    )
    assert got == "baseball_mlb"


@pytest.mark.asyncio
async def test_two_different_leagues_stay_ambiguous_6377():
    got = await covered_league_for_matchup(
        _FakeSession(AFL), "Hawthorn Hawks", "Brisbane Lions",
        unambiguous_only=True,
    )
    assert got is None


@pytest.mark.asyncio
async def test_a_variant_with_no_parent_still_names_itself():
    got = await covered_league_for_matchup(
        _FakeSession(VARIANT_ONLY), "Summer Club A", "Summer Club B",
        unambiguous_only=True,
    )
    assert got == "basketball_nba_summer_league"


@pytest.mark.asyncio
async def test_a_variant_plus_an_unrelated_league_stays_ambiguous():
    rows = MLB + [
        _Row("Baltimore Orioles", None, "baseball_ncaa"),
        _Row("New York Yankees", None, "baseball_ncaa"),
    ]
    got = await covered_league_for_matchup(
        _FakeSession(rows), "Baltimore Orioles", "New York Yankees",
        unambiguous_only=True,
    )
    assert got is None


# =============================================================================
# End to end through phase 1.5, on the rail #8668 shipped with — plus the one
# thing that rail left out and production has: each club's preseason row.
# =============================================================================


def _rail_with_preseason_clubs():
    from app.models.models import Sport, Team
    from tests.test_phase15_venue_instant_relink_8547 import ORIOLES, YANKEES, _new_rail

    session, mlb = _new_rail()
    pre = Sport(key="baseball_mlb_preseason", name="MLB Preseason")
    session.add(pre)
    session.flush()
    session.add_all([
        Team(name=YANKEES, sport_id=pre.id, alternate_names=["Yankees"]),
        Team(name=ORIOLES, sport_id=pre.id, alternate_names=["Orioles"]),
    ])
    session.flush()
    return session, mlb


@pytest.mark.asyncio
async def test_the_doubleheader_market_moves_when_the_clubs_have_preseason_rows():
    from tests.test_phase15_venue_instant_relink_8547 import _on, _run_phase15, _specimen

    session, mlb = _rail_with_preseason_clubs()
    game_1, game_2, moved, moved_sib, friday = _specimen(session, mlb)

    stats, _ = await _run_phase15(session)

    assert _on(session, moved, moved_sib) == [game_1.id, game_1.id], (
        f"game 1 = {game_1.id}, game 2 = {game_2.id}: with production's "
        f"preseason team rows present the Polymarket group must still move"
    )
    assert _on(session, friday) == [game_2.id]
    assert stats["funnel"]["phase15_venue_instant_relinked"] >= 1
