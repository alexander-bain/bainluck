"""#2017 — an espn_id is never stamped onto a row when another row holds it.

## The mechanism these tests pin (measured live 2026-08-20 00:20–01:00Z)

1. ``ODDS_LISTING_IS_NOT_A_DEREFERENCE`` is ``False``, so every odds_api claim is
   unanchored and ruling 048 refuses the structured absorb.
2. The Odds API issues a NEW event id for a fixture we already hold, so step 1
   (exact source id) misses and ``find_or_create_event`` CREATEs.
3. ``sports.py`` then stamped the ESPN id it had matched by NAME onto that fresh
   row, checking only whether *this* row had one — never whether another row
   already held it. ``ix_events_espn_id`` is a plain btree, not UNIQUE, so the
   database accepted the contradiction. The duplicate was BORN with it, in the
   same transaction.

Live specimen: keeper ``14947545`` Marseille/Strasbourg ``espn_id=401876489``,
``external_id=8e25c99f…``; new row ``15249444``, same clubs, same ``espn_id``,
``external_id=600aeb35…``.

## What is IN scope here, and what is not

In scope: the WRITE refuses and the refusal is counted. Out of scope: preventing
the CREATE. Making ``espn_id`` a registry lookup key was considered and rejected
— ``app/utils/event_merge_invariant.py`` measured that of 13 pairs sharing an
``espn_id`` in a 60-day window, at least three are genuinely different games, so
a wrong id used as a key resolves a claim onto a different real game, which is
strictly worse than the duplicate.

Every test here is MOCK-BASED (async session doubles). There is no local
Postgres in the sandbox, so no test in this file asserts real-PG behaviour; the
non-UNIQUE index is stated as a fact of production, not exercised.
"""

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event
from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    ODDS_LISTING_IS_NOT_A_DEREFERENCE,
    _sport_id_cache,
    find_or_create_event,
)
from app.utils.espn_id_stamp import (
    REFUSED,
    SKIPPED,
    STAMPED,
    espn_id_holder,
    stamp_espn_id_if_unheld,
)

from tests.test_event_registry import _FakeRegistrySession


# ---------------------------------------------------------------------------
# Session double for the holder lookup
# ---------------------------------------------------------------------------

class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeStampSession:
    """Answers exactly the one query shape ``espn_id_holder`` issues."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.queries = 0

    async def execute(self, statement):
        self.queries += 1
        text = str(statement)
        assert "FROM events" in text and "events.espn_id =" in text, text
        params = statement.compile().params
        espn_id = params.get("espn_id_1")
        exclude = params.get("id_1")
        matched = [
            row.id
            for row in self.rows
            if row.espn_id == espn_id and (exclude is None or row.id != exclude)
        ]
        return _FakeResult(matched)


def _row(event_id, espn_id, *, home="Marseille", away="Strasbourg"):
    return Event(
        id=event_id,
        sport_id=1,
        home_team_name=home,
        away_team_name=away,
        espn_id=espn_id,
        commence_time=datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc),
        status="scheduled",
    )


# ---------------------------------------------------------------------------
# The forward case — the live #2017 specimen, end to end
# ---------------------------------------------------------------------------

class TestForwardCaseDuplicateIsBornClean:

    @pytest.mark.asyncio
    async def test_new_odds_id_creates_a_row_that_does_not_steal_the_espn_id(self):
        """A new external_id for a held fixture creates — but WITHOUT the collision.

        This is deliberately the composition ``sports.py`` performs: the registry
        call, then the stamp, in one transaction. The assertion is not that the
        create is avoided (ruling 048 says it is not), but that the row that gets
        created carries a NULL ``espn_id`` instead of the keeper's.
        """
        # The two Odds ids are bound to names rather than written inline. The
        # source string "odds_api" contains "api", so gitleaks' generic-api-key
        # rule reads any quoted literal sitting next to it as a secret — a false
        # positive that reds CI (queue 378).
        keeper_odds_id = "keeper-mar-str"
        gen2_odds_id = "gen2-mar-str"

        keeper = _row(14947545, "401876489")
        keeper.external_id = keeper_odds_id
        keeper.commence_time_source = "odds_api"

        registry_session = _FakeRegistrySession(structured_candidates=[keeper])
        _sport_id_cache.clear()

        # Step 1 misses: the Odds API minted a brand-new id for the same fixture.
        assert ODDS_LISTING_IS_NOT_A_DEREFERENCE is False
        created, was_created = await find_or_create_event(
            registry_session,
            EventIdentity(
                sport_key="soccer_france_ligue_one",
                home_team_name="Marseille",
                away_team_name="Strasbourg",
                commence_time=keeper.commence_time,
                claim=EventClaim(
                    "odds_api", gen2_odds_id,
                    schedule_derived=ODDS_LISTING_IS_NOT_A_DEREFERENCE,
                ),
                status="scheduled",
            ),
        )
        assert was_created is True, "ruling 048 gate changed — that is a different bug"
        assert created.espn_id is None

        # The stamp: the ESPN id was matched by NAME off the scoreboard, and the
        # keeper already holds it.
        stamp_session = _FakeStampSession([keeper, created])
        refused = 0
        verdict, holder = await stamp_espn_id_if_unheld(
            stamp_session, created, "401876489", context="discover_events[test]",
        )
        if verdict == REFUSED:
            refused += 1

        assert verdict == REFUSED
        assert holder == 14947545
        assert created.espn_id is None, (
            "the duplicate was born carrying the keeper's espn_id — #2017"
        )
        assert keeper.espn_id == "401876489", "the keeper must be untouched"
        assert refused == 1, "a refusal that is not counted is invisible"


# ---------------------------------------------------------------------------
# The negative direction — doubleheaders must NOT be affected
# ---------------------------------------------------------------------------

class TestDoubleheaderStillGetsTwoEvents:
    """CIN/STL 2026-08-17, confirmed live: two real games, same teams, same day.

    ESPN ids ``401873710`` (17:40Z) and ``401816567`` (22:40Z). Nothing in this
    fix may collapse them: the guard keys on EXACT espn_id equality, so two
    distinct ids never see each other, and ruling 048's create-instead-of-absorb
    behaviour is untouched.
    """

    @pytest.mark.asyncio
    async def test_distinct_espn_ids_both_stamp_and_stay_distinct(self):
        game_one = _row(500001, None, home="St. Louis Cardinals", away="Cincinnati Reds")
        game_one.commence_time = datetime(2026, 8, 17, 17, 40, tzinfo=timezone.utc)
        game_two = _row(500002, None, home="St. Louis Cardinals", away="Cincinnati Reds")
        game_two.commence_time = datetime(2026, 8, 17, 22, 40, tzinfo=timezone.utc)

        session = _FakeStampSession([game_one, game_two])
        claimed: set = set()
        refused = 0

        for row, espn_id in ((game_one, "401873710"), (game_two, "401816567")):
            verdict, _holder = await stamp_espn_id_if_unheld(
                session, row, espn_id, context="test", claimed=claimed,
            )
            if verdict == REFUSED:
                refused += 1

        assert refused == 0, "the guard refused a legitimate doubleheader stamp"
        assert game_one.espn_id == "401873710"
        assert game_two.espn_id == "401816567"
        assert game_one.id != game_two.id

    @pytest.mark.asyncio
    async def test_unanchored_doubleheader_claim_still_creates_a_second_event(self):
        """Ruling 048's gate is not widened by this fix — same teams, same day, 5h apart."""
        game_one = _row(500001, "401873710", home="St. Louis Cardinals", away="Cincinnati Reds")
        game_one.commence_time = datetime(2026, 8, 17, 17, 40, tzinfo=timezone.utc)
        game_one.external_id = "odds-cin-stl-g1"
        game_one.commence_time_source = "odds_api"

        session = _FakeRegistrySession(structured_candidates=[game_one])
        _sport_id_cache.clear()

        event, was_created = await find_or_create_event(
            session,
            EventIdentity(
                sport_key="baseball_mlb",
                home_team_name="St. Louis Cardinals",
                away_team_name="Cincinnati Reds",
                commence_time=game_one.commence_time + timedelta(hours=5),
                claim=EventClaim(
                    "odds_api", "odds-cin-stl-g2",
                    schedule_derived=ODDS_LISTING_IS_NOT_A_DEREFERENCE,
                ),
            ),
        )

        assert was_created is True
        assert event is not game_one
        assert event.espn_id is None


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------

class TestStampGuard:

    @pytest.mark.asyncio
    async def test_stamps_when_no_other_row_holds_the_id(self):
        target = _row(2, None)
        session = _FakeStampSession([_row(1, "999999"), target])
        verdict, holder = await stamp_espn_id_if_unheld(
            session, target, "401876489", context="test",
        )
        assert (verdict, holder) == (STAMPED, None)
        assert target.espn_id == "401876489"

    @pytest.mark.asyncio
    async def test_refuses_when_another_row_holds_the_id(self):
        holder_row = _row(1, "401876489")
        target = _row(2, None)
        session = _FakeStampSession([holder_row, target])
        verdict, holder = await stamp_espn_id_if_unheld(
            session, target, "401876489", context="test",
        )
        assert (verdict, holder) == (REFUSED, 1)
        assert target.espn_id is None

    @pytest.mark.asyncio
    async def test_unflushed_row_still_sees_the_holder(self):
        """``id <> NULL`` is NULL. Excluding an unflushed row must not disable the check.

        If the exclusion clause were applied unconditionally with ``id=None``, the
        SELECT would match nothing and the guard would become a rubber stamp on
        exactly the path that matters — a row created moments earlier.
        """
        holder_row = _row(1, "401876489")
        unflushed = _row(None, None)
        session = _FakeStampSession([holder_row])
        verdict, holder = await stamp_espn_id_if_unheld(
            session, unflushed, "401876489", context="test",
        )
        assert (verdict, holder) == (REFUSED, 1)
        assert unflushed.espn_id is None

    @pytest.mark.asyncio
    async def test_row_that_already_has_an_id_is_left_alone(self):
        target = _row(2, "401816567")
        session = _FakeStampSession([target])
        verdict, _holder = await stamp_espn_id_if_unheld(
            session, target, "401876489", context="test",
        )
        assert verdict == SKIPPED
        assert target.espn_id == "401816567"
        assert session.queries == 0, "no query needed when there is nothing to write"

    @pytest.mark.asyncio
    async def test_no_incoming_id_is_a_noop(self):
        target = _row(2, None)
        session = _FakeStampSession([target])
        for empty in (None, ""):
            verdict, _holder = await stamp_espn_id_if_unheld(
                session, target, empty, context="test",
            )
            assert verdict == SKIPPED
        assert target.espn_id is None

    @pytest.mark.asyncio
    async def test_id_claimed_earlier_in_the_same_pass_is_refused(self):
        """The in-pass set, for when the DB has not seen the earlier stamp yet."""
        first = _row(1, None)
        second = _row(2, None)
        session = _FakeStampSession([first, second])
        claimed: set = set()

        v1, _ = await stamp_espn_id_if_unheld(
            session, first, "401876489", context="test", claimed=claimed,
        )
        v2, _ = await stamp_espn_id_if_unheld(
            session, second, "401876489", context="test", claimed=claimed,
        )

        assert v1 == STAMPED
        assert v2 == REFUSED
        assert second.espn_id is None

    @pytest.mark.asyncio
    async def test_holder_lookup_ignores_the_row_being_stamped(self):
        row = _row(7, "401876489")
        session = _FakeStampSession([row])
        assert await espn_id_holder(session, "401876489", exclude_event_id=7) is None
        assert await espn_id_holder(session, "401876489") == 7


# ---------------------------------------------------------------------------
# The call sites cannot quietly go back to a raw assignment
# ---------------------------------------------------------------------------

class TestCallSitesRouteThroughTheGuard:
    """A guard one edit away from not existing is not a guard (#1947's lesson)."""

    def test_discover_events_has_no_raw_espn_id_assignment(self):
        from app.tasks import sports

        source = inspect.getsource(sports._discover_events)
        assert "stamp_espn_id_if_unheld" in source, (
            "discover_events stopped routing its espn_id write through the guard"
        )
        assert "event.espn_id = espn_event_id" not in source, (
            "the raw #2017 assignment is back in discover_events"
        )
        assert "espn_id_stamps_refused" in inspect.getsource(sports._discover_events)

    def test_sync_scheduled_events_has_no_raw_espn_id_assignment(self):
        from app.utils import espn_helpers

        source = inspect.getsource(espn_helpers.sync_scheduled_events)
        assert "stamp_espn_id_if_unheld" in source, (
            "the scheduled pass stopped routing its espn_id write through the guard"
        )
        assert "event.espn_id = ee.espn_id" not in source, (
            "the raw assignment is back in the 60s scheduled pass — this loop has "
            "no time window, so it re-stamps every duplicate on every tick"
        )
        assert "scheduled_espn_id_refused" in source
