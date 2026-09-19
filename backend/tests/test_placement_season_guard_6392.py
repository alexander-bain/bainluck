"""#6392 — a placement never files a fixture on a competition that is over.

THE READER'S COMPLAINT, IN THE FORM IT WOULD HAVE TAKEN. #5576's placer
relabels a `<prefix>_other` row with the real league both clubs share. A
national side and a tennis player belong to a competition PERMANENTLY in
`teams`, so "France" ∩ "Canada" is exactly one soccer league —
`soccer_fifa_world_cup` — and every one of the placer's four refusals is
satisfied. It would therefore have filed a **2026-09-17** friendly onto the
World Cup page, whose final was **2026-07-19**, and a **2026-09-12** tennis
match onto a French Open that finished **2026-06-07**.

EVERY FIXTURE BELOW IS A PRODUCTION ROW, read by db-query on 2026-09-15 ~16:55Z
over the 24 same-family catch-all rows minted since the #5544 guard landed on
09-13. The three wrong placements and the 21 correct ones are both here, because
the controls are the whole point: `baseball_npb`'s schedule is loaded only to
09-15 while Polymarket lists to 09-22, so the naive rule ("the kickoff must fall
inside the loaded schedule") refuses a CORRECT placement. What separates NPB
from the World Cup is not whether this fixture is known, it is whether the
competition is running at all.

THE RIG HONOURS THE PREDICATE, AND IT HAD TO BE REPLACED TO GO ON DOING SO.
This file used to serve rows by regex-parsing the compiled SQL — the league, the
time floor and the source exclusion read back out of the string, never from
re-importing the module's constants, so that deleting a WHERE clause turned
these tests red instead of leaving them green (the #6377 lesson).

#7086 gave the guard two more questions to ask, one of them a BAND
(`>= A AND <= B`) and one an OR of two bands. The regexes could not read either:
they found the first `>=`, took it for a floor and ignored every ceiling. The
whole file still passed — measured, not feared: at a kickoff 29 days past NPB's
only fixture the old fake answered True while the query itself excludes that row,
so `test_the_floor_is_measured_from_the_kickoff_not_the_clock` was asserting a
behaviour the code no longer had. A rig that mis-reads a predicate does not
weaken a test, it inverts one.

So the fake now lives in `tests/lib_placement_predicate.py` and EVALUATES the
statement's expression tree against each row, in SQL's three-valued logic. It
honours any predicate the code emits and raises on any clause it cannot read,
rather than skipping it.
"""
import ast
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.prediction_market_matching import (
    MARKET_BORN_COMMENCE_SOURCES,
    _PLACEMENT_SEASON_WINDOW_DAYS,
    league_is_running_at,
)
from tests.lib_placement_predicate import (
    PredicateSession as _FakeSession,
    ScheduleRow as _EventRow,
)


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


# ── The production population, 2026-09-15 ────────────────────────────────────
# The three competitions that were OVER, with the last schedule-born fixture
# each actually carries.
WORLD_CUP_LAST_REAL = _utc("2026-07-19 19:00:00")
FRENCH_OPEN_LAST_REAL = _utc("2026-06-07 13:00:00")

# The competitions that were RUNNING, likewise.
NPB_LAST_REAL = _utc("2026-09-15 09:01:14")
NBL_LAST_REAL = _utc("2026-09-20 07:06:00")
NATIONS_LEAGUE_LAST_REAL = _utc("2026-09-29 18:45:00")
SUDAMERICANA_LAST_REAL = _utc("2026-09-18 00:30:00")
SWISS_LAST_REAL = _utc("2026-09-20 14:30:00")

#: One fixture per season competition from the 30-to-60-day shoulder before
#: these kickoffs, added for #7086 and read by db-query on 2026-09-19.
#:
#: WHY THE LAST FIXTURE ALONE STOPPED BEING ENOUGH. #6392's guard asked one
#: question — is anything scheduled since the floor — and the last fixture is a
#: complete answer to it. #7086's asks a second: is this a season or a
#: tournament, decided on whether the competition was playing a month or two
#: BEFORE the kickoff. A one-row-per-league population cannot express that, and
#: leaving it would have made these controls assert the wrong mechanism rather
#: than a wrong verdict. Production carries 75 NPB fixtures in 07-25..08-20, 19
#: Sudamericana, 15 Libertadores and 18 Swiss.
#:
#: `basketball_nbl` and `soccer_uefa_nations_league` get none because production
#: has none — NBL opened its season on 09-19 and the Nations League plays in
#: windows. Their placements below are admitted by the tournament arm instead.
NPB_SHOULDER = _utc("2026-08-19 09:00:00")
SUDAMERICANA_SHOULDER = _utc("2026-08-19 22:00:00")
LIBERTADORES_SHOULDER = _utc("2026-08-19 22:00:00")
SWISS_SHOULDER = _utc("2026-08-09 14:30:00")

SCHEDULE_ROWS = [
    _EventRow("soccer_fifa_world_cup", WORLD_CUP_LAST_REAL, "odds_api"),
    _EventRow("tennis_atp_french_open", FRENCH_OPEN_LAST_REAL, "odds_api"),
    _EventRow("baseball_npb", NPB_LAST_REAL, "statpal"),
    _EventRow("baseball_npb", NPB_SHOULDER, "statpal"),
    _EventRow("basketball_nbl", NBL_LAST_REAL, "odds_api"),
    _EventRow("soccer_uefa_nations_league", NATIONS_LEAGUE_LAST_REAL, "odds_api"),
    _EventRow("soccer_conmebol_copa_sudamericana", SUDAMERICANA_LAST_REAL, "odds_api"),
    _EventRow(
        "soccer_conmebol_copa_sudamericana", SUDAMERICANA_SHOULDER, "odds_api"
    ),
    _EventRow("soccer_conmebol_copa_libertadores", SUDAMERICANA_LAST_REAL, "odds_api"),
    _EventRow(
        "soccer_conmebol_copa_libertadores", LIBERTADORES_SHOULDER, "odds_api"
    ),
    _EventRow("soccer_switzerland_superleague", SWISS_LAST_REAL, "espn"),
    _EventRow("soccer_switzerland_superleague", SWISS_SHOULDER, "espn"),
]

# The 3 rows the four refusals let through, each with its own kickoff.
WRONG_PLACEMENTS = [
    ("soccer_fifa_world_cup", _utc("2026-09-16 13:00:00"), "Brazil v USA"),
    ("soccer_fifa_world_cup", _utc("2026-09-17 13:00:00"), "France v Canada"),
    (
        "tennis_atp_french_open",
        _utc("2026-09-12 23:05:20"),
        "Thiago Seyboth Wild v Pedro Martinez",
    ),
]

# The 21 that are correct and must survive untouched.
CORRECT_PLACEMENTS = [
    ("baseball_npb", _utc("2026-09-20 05:00:00"), "Yomiuri Giants v Tokyo Yakult"),
    ("baseball_npb", _utc("2026-09-20 05:00:00"), "Tohoku Rakuten v SoftBank"),
    ("baseball_npb", _utc("2026-09-20 09:00:00"), "Chiba Lotte v Saitama Seibu"),
    ("baseball_npb", _utc("2026-09-21 04:00:00"), "Tohoku Rakuten v SoftBank"),
    ("baseball_npb", _utc("2026-09-21 09:00:00"), "Chiba Lotte v Saitama Seibu"),
    ("baseball_npb", _utc("2026-09-22 09:00:00"), "SoftBank v Saitama Seibu"),
    ("baseball_npb", _utc("2026-09-22 09:00:00"), "Chiba Lotte v Orix Buffaloes"),
    ("baseball_npb", _utc("2026-09-22 09:00:00"), "Tokyo Yakult v Hanshin Tigers"),
    ("basketball_nbl", _utc("2026-09-19 09:30:00"), "Melbourne United v Adelaide"),
    ("basketball_nbl", _utc("2026-09-20 05:00:00"), "NZ Breakers v Illawarra"),
    ("basketball_nbl", _utc("2026-09-20 07:00:00"), "Sydney Kings v Cairns"),
    (
        "soccer_conmebol_copa_libertadores",
        _utc("2026-09-15 22:00:00"),
        "Carabobo v Deportivo La Guaira",
    ),
    (
        "soccer_conmebol_copa_sudamericana",
        _utc("2026-09-16 23:30:00"),
        "Metropolitanos v Caracas",
    ),
    (
        "soccer_switzerland_superleague",
        _utc("2026-09-19 18:30:00"),
        "FC Sion v FC Zurich",
    ),
    ("soccer_uefa_nations_league", _utc("2026-09-27 16:00:00"), "Gibraltar v Andorra"),
    ("soccer_uefa_nations_league", _utc("2026-09-27 16:00:00"), "Austria v Kosovo"),
    ("soccer_uefa_nations_league", _utc("2026-09-27 16:30:00"), "Malta v Liechtenstein"),
    ("soccer_uefa_nations_league", _utc("2026-09-28 16:00:00"), "Armenia v Montenegro"),
    ("soccer_uefa_nations_league", _utc("2026-09-28 16:00:00"), "Georgia v Ukraine"),
    ("soccer_uefa_nations_league", _utc("2026-09-28 16:00:00"), "Latvia v Cyprus"),
    (
        "soccer_uefa_nations_league",
        _utc("2026-09-28 18:45:00"),
        "Northern Ireland v Hungary",
    ),
]


class TestTheThreeWrongPlacements:
    """The competition had already finished at the fixture's own kickoff."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("league,kickoff,label", WRONG_PLACEMENTS)
    async def test_a_finished_competition_does_not_admit_a_new_fixture(
        self, league, kickoff, label
    ):
        session = _FakeSession(SCHEDULE_ROWS)
        assert await league_is_running_at(session, league, kickoff) is False, (
            f"{label} would be filed on {league}, whose last real fixture is "
            f"months before this kickoff"
        )

    @pytest.mark.asyncio
    async def test_the_world_cup_gap_is_the_one_measured(self):
        """58d18h, and the guard must be reading the kickoff to see it."""
        kickoff = _utc("2026-09-16 13:00:00")
        gap = (kickoff - WORLD_CUP_LAST_REAL).total_seconds() / 86400
        assert 58.5 < gap < 59.0
        session = _FakeSession(SCHEDULE_ROWS)
        assert await league_is_running_at(
            session, "soccer_fifa_world_cup", kickoff
        ) is False


class TestTheTwentyOneCorrectPlacements:
    """Every placement #5576 gets right today survives this guard."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("league,kickoff,label", CORRECT_PLACEMENTS)
    async def test_a_running_competition_still_admits_its_fixture(
        self, league, kickoff, label
    ):
        session = _FakeSession(SCHEDULE_ROWS)
        assert await league_is_running_at(session, league, kickoff) is True, (
            f"{label} is a correct #5576 placement and this guard must not "
            f"take it back"
        )

    @pytest.mark.asyncio
    async def test_npb_is_placed_although_its_schedule_stops_short(self):
        """The control that rules out the naive rule.

        NPB's schedule is loaded to 09-15 and Polymarket lists to 09-22, so the
        kickoff sits SEVEN DAYS PAST the last known fixture and there is no
        counterpart for it anywhere. "The kickoff must fall inside the loaded
        schedule" would refuse this, and it is correct.
        """
        kickoff = _utc("2026-09-22 09:00:00")
        assert kickoff > NPB_LAST_REAL
        assert (kickoff - NPB_LAST_REAL).days == 6  # 6d 23h 58m
        session = _FakeSession(SCHEDULE_ROWS)
        assert await league_is_running_at(session, "baseball_npb", kickoff) is True


class TestTheThresholdItself:
    @pytest.mark.asyncio
    async def test_threshold_separates_the_measured_population(self):
        """The constant is measured, so assert the MARGIN, not the number.

        Worst gap among the correct placements is NPB's ~7 days; best among the
        wrong ones is the World Cup's 59. Any threshold in 8..58 gives the same
        verdict. If someone tunes the constant to the edge of that band this
        fails, which is the point (two records of one capability must assert
        the gap).
        """
        worst_correct = max(
            (kickoff - NPB_LAST_REAL).total_seconds() / 86400
            for league, kickoff, _ in CORRECT_PLACEMENTS
            if league == "baseball_npb"
        )
        best_wrong = min(
            (kickoff - (
                WORLD_CUP_LAST_REAL
                if league == "soccer_fifa_world_cup"
                else FRENCH_OPEN_LAST_REAL
            )).total_seconds() / 86400
            for league, kickoff, _ in WRONG_PLACEMENTS
        )
        assert worst_correct < _PLACEMENT_SEASON_WINDOW_DAYS < best_wrong
        assert worst_correct < 8
        assert best_wrong > 58

    @pytest.mark.asyncio
    async def test_the_floor_is_measured_from_the_kickoff_not_the_clock(self):
        """Same league, two kickoffs, two answers — so the row decides.

        A guard reading `now()` would give one answer for both and the test
        would branch on when it runs (gotcha #44).
        """
        session = _FakeSession(SCHEDULE_ROWS)
        just_inside = NPB_LAST_REAL + timedelta(
            days=_PLACEMENT_SEASON_WINDOW_DAYS - 1
        )
        well_outside = NPB_LAST_REAL + timedelta(
            days=_PLACEMENT_SEASON_WINDOW_DAYS + 1
        )
        assert await league_is_running_at(
            session, "baseball_npb", just_inside
        ) is True
        assert await league_is_running_at(
            session, "baseball_npb", well_outside
        ) is False


class TestPhantomsMayNotVouchForEachOther:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("source", MARKET_BORN_COMMENCE_SOURCES)
    async def test_a_market_born_row_is_not_a_season(self, source):
        """The circularity this closes: one bad placement admitting the next.

        The ONLY row in the target league is market-born and sits right on the
        kickoff. If the source exclusion stops being emitted, the fake serves it
        and this returns True — which is the first phantom licensing the second.
        """
        kickoff = _utc("2026-09-17 13:00:00")
        session = _FakeSession(
            [_EventRow("soccer_fifa_world_cup", kickoff, source)]
        )
        assert await league_is_running_at(
            session, "soccer_fifa_world_cup", kickoff
        ) is False

    @pytest.mark.asyncio
    async def test_a_legacy_null_source_row_still_anchors_a_season(self):
        """30,414 production rows carry NULL here and are schedule-born.

        Excluding them would refuse leagues whose only fixtures predate the
        column, so the measured predicate admits NULL explicitly.
        """
        kickoff = _utc("2026-09-17 13:00:00")
        session = _FakeSession(
            [_EventRow("soccer_fifa_world_cup", kickoff, None)]
        )
        assert await league_is_running_at(
            session, "soccer_fifa_world_cup", kickoff
        ) is True


class TestAnotherLeaguesSeasonIsNotThisOnes:
    @pytest.mark.asyncio
    async def test_a_running_sibling_does_not_vouch_for_a_finished_league(self):
        """The Nations League is playing this week; the World Cup is not. If the
        league predicate stops being emitted the sibling's row answers for it.

        The kickoff is one of the 21 measured correct placements (Armenia v
        Montenegro) rather than the bare 09-17 it used to be. #7086 refuses
        09-17 for the Nations League and is right to: its September window is
        09-27 to 09-29 and we hold no fixture within twelve days of the 17th, so
        the old date asserted a verdict this guard no longer gives — and the
        contrast it exists to draw survives the move intact. Dropping the league
        clause still turns this red, because the World Cup read then finds NPB's
        August fixture and reports a season.
        """
        session = _FakeSession(SCHEDULE_ROWS)
        kickoff = _utc("2026-09-28 16:00:00")
        assert await league_is_running_at(
            session, "soccer_uefa_nations_league", kickoff
        ) is True
        assert await league_is_running_at(
            session, "soccer_fifa_world_cup", kickoff
        ) is False


class TestTheNoSignalCasesFailClosed:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "session,league,kickoff",
        [
            (None, "baseball_npb", _utc("2026-09-20 05:00:00")),
            (_FakeSession(SCHEDULE_ROWS), None, _utc("2026-09-20 05:00:00")),
            (_FakeSession(SCHEDULE_ROWS), "", _utc("2026-09-20 05:00:00")),
            (_FakeSession(SCHEDULE_ROWS), "baseball_npb", None),
        ],
    )
    async def test_no_signal_leaves_the_row_in_the_catch_all(
        self, session, league, kickoff
    ):
        assert await league_is_running_at(session, league, kickoff) is False

    @pytest.mark.asyncio
    async def test_a_none_session_is_never_queried(self):
        """#2020's and #4242's call-site tests drive the create path with
        `session=None`; this may not raise and may not read."""
        assert await league_is_running_at(None, "baseball_npb", _utc(
            "2026-09-20 05:00:00"
        )) is False


class TestTheCallSiteActuallyAsks:
    """A predicate nothing consults is a vacuous ship.

    These read the create path's own source, because a unit test of
    `league_is_running_at` stays green with every call site deleted.
    """

    def _create_fn(self):
        from app.tasks import prediction_market_matching as module

        return module._create_event_from_prediction_market

    def test_the_create_path_calls_the_guard(self):
        source = inspect.getsource(self._create_fn())
        assert "league_is_running_at(" in source

    def test_the_guard_gates_the_placement_and_is_passed_the_kickoff(self):
        """Not merely called — its falsity must drop `placed_league`, and it
        must be handed the fixture's commence_time rather than a clock."""
        source = textwrap_dedent(inspect.getsource(self._create_fn()))
        tree = ast.parse(source)

        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "league_is_running_at"
        ]
        assert len(calls) == 1, "expected exactly one call site"
        call = calls[0]

        arg_names = [
            arg.id if isinstance(arg, ast.Name) else None for arg in call.args
        ]
        assert "commence_time" in arg_names, (
            "the guard must be given the fixture's own kickoff — passing a "
            "clock would make it drift between the create and a re-read"
        )

        # The call is negated inside an `if` whose body clears `placed_league`.
        gating = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and any(
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "league_is_running_at"
                for inner in ast.walk(node.test)
            )
        ]
        assert gating, "the guard's answer must gate something"
        cleared = False
        for node in gating:
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Assign)
                    and any(
                        isinstance(t, ast.Name) and t.id == "placed_league"
                        for t in inner.targets
                    )
                    and isinstance(inner.value, ast.Constant)
                    and inner.value.value is None
                ):
                    cleared = True
        assert cleared, (
            "a refusal must set `placed_league = None`, otherwise the row is "
            "relabelled anyway and this ship is inert"
        )


def textwrap_dedent(text: str) -> str:
    import textwrap

    return textwrap.dedent(text)
