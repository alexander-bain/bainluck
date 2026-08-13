"""#1779 R3 (c) — the ESPN caller's claim must keep reaching the registry's guard.

WHY THIS FILE EXISTS

An earlier read of this incident concluded ESPN had no caller emitting an
``EventClaim``, which would have made every ESPN fixture in
``test_event_registry_series_absorption.py`` a certification of a claim shape
production never sends. That read was wrong. ESPN is a first-class claim-emitting
caller — ``app/utils/espn_helpers.py`` (``utils/``, not ``services/``) imports the
registry and emits ``claim=EventClaim("espn", ee.espn_id)`` from
``create_events_from_unmatched_espn``.

But the reason the wrong read was even plausible is the actual defect this file
fixes: **Codex mutated the ESPN guard and the suite returned 63/63 green.** A
mutation that stays green is a mutation the suite cannot see, and a guard nothing
can see is a guard that will be deleted by the next person who finds it confusing.

WHAT MAKES THIS OBSERVABLE

Three disqualifications now protect the structured match, and they overlap: kill the
ESPN-specific one and the other two often still refuse, so the assertion stays green
for a reason that has nothing to do with ESPN. The fixtures below are chosen to sit
where **only** the ESPN id comparison can decide — an individuated candidate (so the
un-individuated half-day rule is silent) within 2h (so the cross-provider rule is
silent). At that point the sole remaining evidence is "ESPN gave these two games
different ids", and if that stops reaching ``_holds_distinct_provider_game_id``, one
of these tests goes red.

Behavioural throughout. No test here reads source text, because the whole lesson is
that the suite could not see a behavioural change.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event
from app.services.event_registry import (
    EventClaim,
    _find_by_structured_match,
    _sport_id_cache,
)
from tests.test_event_registry import _FakeRegistrySession

MLB_SPORT_ID = 53232
HOME = "Toronto Blue Jays"
AWAY = "Boston Red Sox"

# Real ids ESPN assigned two different Blue Jays/Red Sox games (production, 2026-08-12).
ESPN_GAME_1 = "401816469"
ESPN_GAME_2 = "401816479"


@pytest.fixture(autouse=True)
def _clear_sport_cache():
    """The registry memoises sport_key -> sport_id process-wide; keep runs independent."""
    _sport_id_cache.clear()
    yield
    _sport_id_cache.clear()


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _recent_whole_minute(days_ago: float) -> datetime:
    """A real (whole-minute) start time safely in the past under ANY wall clock.

    Gotcha #44: offset FIRST, then truncate. Truncating to a fixed hour would pin an
    hour rather than an age and swing a full day against the clock; an absolute
    literal would land in the future under a backwards-faked clock and silently trip
    ``espn_terminal_write_is_fold`` in the caller below.
    """
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(
        second=0, microsecond=0
    )


def _event(*, event_id, commence, espn_id=None, status="completed") -> Event:
    return Event(
        id=event_id,
        sport_id=MLB_SPORT_ID,
        away_team_name=AWAY,
        home_team_name=HOME,
        commence_time=commence,
        status=status,
        espn_id=espn_id,
        statpal_fixture_id=None,
        external_id=None,
        completed_at=None,
    )


# Offsets small enough that EVERY time-based disqualification stays silent, so the
# ESPN id comparison is the only thing left that can decide.
_TIGHT_OFFSETS = [
    ("same_instant", timedelta(0)),
    ("plus_1h", timedelta(hours=1)),
    ("plus_1h59m", timedelta(hours=1, minutes=59)),
]
_OFFSET_IDS = [o[0] for o in _TIGHT_OFFSETS]


class TestOnlyTheEspnIdCanDecideHere:
    """If the ESPN claim stops reaching the guard, these are the tests that go red."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label,offset", _TIGHT_OFFSETS, ids=_OFFSET_IDS)
    async def test_a_different_espn_id_is_refused_inside_every_time_window(
        self, label, offset
    ):
        base = _utc("2026-08-10T17:07:00")
        candidate = _event(event_id=1, commence=base, espn_id=ESPN_GAME_1)
        session = _FakeRegistrySession(
            structured_candidates=[candidate], sport_id=MLB_SPORT_ID
        )

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, HOME, AWAY, base + offset,
            EventClaim("espn", ESPN_GAME_2),
        )

        assert match is None, (
            f"{label}: ESPN id {ESPN_GAME_2} was absorbed into a row holding ESPN id "
            f"{ESPN_GAME_1}. Nothing else can refuse this pair — the candidate is "
            "individuated (so the un-individuated half-day rule is silent) and the "
            "times are under 2h apart (so the cross-provider rule is silent). The "
            "ESPN claim is no longer reaching _holds_distinct_provider_game_id."
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label,offset", _TIGHT_OFFSETS, ids=_OFFSET_IDS)
    async def test_the_same_espn_id_still_matches_at_the_same_offsets(
        self, label, offset
    ):
        """The complement, without which the test above is satisfied by "never match".

        A guard that refuses everything is not a guard. Same id, same distances: these
        must all still find their own row.
        """
        base = _utc("2026-08-10T17:07:00")
        candidate = _event(event_id=1, commence=base, espn_id=ESPN_GAME_1)
        session = _FakeRegistrySession(
            structured_candidates=[candidate], sport_id=MLB_SPORT_ID
        )

        match = await _find_by_structured_match(
            session, MLB_SPORT_ID, HOME, AWAY, base + offset,
            EventClaim("espn", ESPN_GAME_1),
        )
        assert match is candidate, f"{label}: a re-poll of the same ESPN game lost its row"

    @pytest.mark.asyncio
    async def test_a_dropped_claim_would_be_visible(self):
        """Pins the mechanism: with no claim, this pair IS absorbed.

        This is the shape of the regression — ``_find_by_structured_match``'s ``claim``
        is optional and defaults to None, so any caller or call site that stops passing
        it silently loses the guard. Asserting the difference makes "the claim arrived"
        an observable fact rather than an assumption.
        """
        base = _utc("2026-08-10T17:07:00")
        candidate = _event(event_id=1, commence=base, espn_id=ESPN_GAME_1)
        session = _FakeRegistrySession(
            structured_candidates=[candidate], sport_id=MLB_SPORT_ID
        )

        without_claim = await _find_by_structured_match(
            session, MLB_SPORT_ID, HOME, AWAY, base + timedelta(hours=1),
        )
        assert without_claim is candidate, (
            "if this is None the guard no longer needs the claim, and the tests above "
            "have stopped proving that ESPN's claim reaches it"
        )


# ── The real production caller ──────────────────────────────────────────


class _EspnTeamStub:
    def __init__(self, display_name):
        self.display_name = display_name
        self.name = display_name
        self.espn_id = "t-" + display_name[:3]


class _EspnEventStub:
    """The fields ``create_events_from_unmatched_espn`` reads off an ESPNEvent."""

    def __init__(self, *, espn_id, date, home, away, status="pre"):
        self.espn_id = espn_id
        self.date = date
        self.status = status
        self.home_team = _EspnTeamStub(home)
        self.away_team = _EspnTeamStub(away)
        self.home_win_probability = None
        self.home_score = None
        self.away_score = None
        self.clock = None
        self.status_detail = None


class TestTheEspnCallerActuallyEmitsAClaim:
    """End to end through ``app/utils/espn_helpers.create_events_from_unmatched_espn``.

    The unit tests above prove the guard works when handed an ESPN claim. These prove
    the ESPN caller is still the thing handing it one — the link that the "ESPN has no
    caller" misreading assumed was absent.

    Note the caller wraps each game in ``except Exception`` and only logs, so a
    silently-failed run looks like a quiet no-op (gotcha #53's shape). Every assertion
    below is on ``stats``, which is only written on the success path.
    """

    @pytest.mark.asyncio
    async def test_a_second_series_game_is_created_not_absorbed(self):
        from app.utils.espn_helpers import create_events_from_unmatched_espn

        game1_time = _recent_whole_minute(3)
        game2_time = game1_time + timedelta(hours=24)

        absorber = _event(event_id=15187583, commence=game1_time, espn_id=ESPN_GAME_1)
        session = _FakeRegistrySession(
            structured_candidates=[absorber], sport_id=MLB_SPORT_ID
        )
        stats: dict = {}

        await create_events_from_unmatched_espn(
            session,
            our_events=[],
            espn_events=[
                _EspnEventStub(espn_id=ESPN_GAME_2, date=game2_time,
                               home=HOME, away=AWAY)
            ],
            sport_key="baseball_mlb",
            stats=stats,
        )

        assert stats.get("espn_events_created") == 1, (
            "the ESPN caller did not create the second series game "
            f"(stats={stats}). Either its EventClaim stopped reaching the registry's "
            "disqualification path, or the call raised into the caller's catch-all."
        )
        assert stats.get("espn_events_attached") is None
        created = session.added[-1]
        assert created.espn_id == ESPN_GAME_2
        assert created.commence_time == game2_time
        # And the earlier game is left exactly as it was.
        assert absorber.espn_id == ESPN_GAME_1
        assert absorber.commence_time == game1_time

    @pytest.mark.asyncio
    async def test_a_same_instant_relisting_is_created_not_absorbed(self):
        """The claim has to survive ``find_or_create_event`` -> ``_find_existing`` too.

        Found by mutation: replacing ``identity.claim`` with ``None`` at the
        ``_find_existing`` call site left BOTH registry suites at 94/94 green. Every
        end-to-end fixture they had was ≥17h wide, so the cross-provider 2h rule
        refused the pair on its own and the claim was never load-bearing above
        ``_find_by_structured_match``.

        This closes that: two ESPN ids on the SAME instant. Nothing about the clock can
        separate them, so the claim must travel the whole path — caller -> identity ->
        _find_existing -> _find_by_structured_match -> the id comparison — or the second
        listing is swallowed by the first.
        """
        from app.utils.espn_helpers import create_events_from_unmatched_espn

        start = _recent_whole_minute(3)
        absorber = _event(event_id=15187583, commence=start, espn_id=ESPN_GAME_1)
        session = _FakeRegistrySession(
            structured_candidates=[absorber], sport_id=MLB_SPORT_ID
        )
        stats: dict = {}

        await create_events_from_unmatched_espn(
            session,
            our_events=[],
            espn_events=[
                _EspnEventStub(espn_id=ESPN_GAME_2, date=start, home=HOME, away=AWAY)
            ],
            sport_key="baseball_mlb",
            stats=stats,
        )

        assert stats.get("espn_events_created") == 1, (
            "ESPN's own id no longer reaches the guard through find_or_create_event "
            f"(stats={stats})"
        )
        assert session.added[-1].espn_id == ESPN_GAME_2
        assert absorber.espn_id == ESPN_GAME_1

    @pytest.mark.asyncio
    async def test_the_caller_still_attaches_when_it_is_genuinely_the_same_game(self):
        """The inverse direction (gotcha #43): the claim must still JOIN, not only refuse.

        A row odds_api created, at the same start time, must take ESPN's id rather than
        spawn a duplicate — and the id landing on it is direct evidence that the claim
        travelled all the way from the ESPN caller into ``_attach_claim``.
        """
        from app.utils.espn_helpers import create_events_from_unmatched_espn

        start = _recent_whole_minute(3)
        existing = _event(event_id=15187583, commence=start, espn_id=None)
        existing.external_id = "odds-game-1"
        session = _FakeRegistrySession(
            structured_candidates=[existing], sport_id=MLB_SPORT_ID
        )
        stats: dict = {}

        await create_events_from_unmatched_espn(
            session,
            our_events=[],
            espn_events=[
                _EspnEventStub(espn_id=ESPN_GAME_1, date=start, home=HOME, away=AWAY)
            ],
            sport_key="baseball_mlb",
            stats=stats,
        )

        assert stats.get("espn_events_attached") == 1, f"stats={stats}"
        assert stats.get("espn_events_created") is None
        assert existing.espn_id == ESPN_GAME_1, (
            "the ESPN claim never reached _attach_claim — the caller is no longer "
            "emitting EventClaim('espn', ee.espn_id)"
        )
        assert session.added == []
