"""#6056 — a live score and clock stop running backwards under the reader.

WHAT A READER SAW
=================
On 2026-09-14, during the Giants–Cowboys Sunday-night game, `/api/events/14637256`
served (ux/1247's table, sequential reads, one parser):

    28–14  →  27–14  →  28–14                  an extra point un-scoring itself
    6:41 → 5:42 → 6:41 → 5:53 → 5:42           a football clock going UP
    28–20 @5:21 → 28–14 @5:26 → 28–20 @5:21    a touchdown gone for a minute

WHAT IT ACTUALLY WAS, MEASURED
==============================
Not a cache and not one bad feed. `events.home_score` / `away_score` /
`game_clock` / `period` have THREE unarbitrated writers —
`espn_helpers.update_event_fields_from_espn`, `statpal_sync`'s livescores pass,
and `odds_polling`'s scores feed — and each writes whatever it last fetched. Last
write wins, so when two of them disagree the served state does not converge, it
ALTERNATES.

Our own `score_snapshots` table had recorded it, separable by cadence offset:

    02:58:37  28–14   :37 writer        03:11:37  28–20   :37 writer
    02:59:09  21–14   another           03:12:09  28–14   another
    02:59:37  28–14   :37 writer        03:12:37  28–20   :37 writer
    03:00:09  27–14   another           03:13:09  28–14   another

ESPN is exonerated by its own table: `espn_snapshots` over the same window is
strictly monotonic in game time, 32 rows, no 27 and no clock rise. So no feed is
corrupt — one of them is simply BEHIND, and nothing stopped a behind observation
overwriting an ahead one. It was systemic, not one game: all 13 NFL rows that day
carry both writers' snapshots.

WHY NOT "A SCORE MAY NOT GO DOWN"
=================================
Because a score going down is exactly what a legitimate correction looks like —
a touchdown reversed on review, a point removed after a penalty. A monotonic
clamp pins the first wrong number ever written and calls it truth, which never
heals. So the fix orders by WHEN the observation was taken, in game time, and
never consults the score at all: earlier-than-stored cannot be news whatever it
says; at-or-after is accepted whatever it says, lower scores included.

THE ONE FEED THAT CANNOT BE ORDERED
===================================
`odds_polling`'s scores feed carries no clock and no period, so there is no
observation to place on that scale — only a number. It gets a precedence rule
instead (`clockless_write_defers_to_authority`), which is the judgement the same
function already makes forty lines lower for the stat model, in as many words:
"Running both paths causes oscillation ... and they fight."

BOTH DIRECTIONS, EVERYWHERE (gotcha #43)
========================================
Every refusal below has a twin asserting the write still LANDS — a guard that
freezes a live game is worse than the flicker it replaces, and a suite that only
proves refusals would pass with the writers commented out entirely.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.utils.game_pairing import clockless_write_defers_to_authority
from app.utils.game_state import (
    live_progress_position,
    live_write_would_revert,
)


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


# ---------------------------------------------------------------------------
# 1. Placing an observation in its own game
#
# The vocabulary below is MEASURED, not invented: a `GROUP BY` over
# `espn_snapshots.period` for the two days to 2026-09-14 returned exactly these
# shapes and no others — `'5:21 - 4th Quarter'`, `'Halftime'`,
# `'End of 3rd Quarter'`, `'Delayed'`, `'10:00 - OT'`, `'Top 9th'`. StatPal's
# raw statuses are the same words by construction (#5017 made the two writers
# compose byte-identical strings on purpose).
# ---------------------------------------------------------------------------


class TestAnObservationIsPlacedInGameTime:
    def test_later_in_the_same_quarter_is_a_bigger_position(self):
        """The specimen pair. 5:21 remaining is LATER than 5:26 remaining."""
        earlier = live_progress_position("5:26 - 4th Quarter", "5:26")
        later = live_progress_position("5:21 - 4th Quarter", "5:21")
        assert earlier is not None and later is not None
        assert earlier < later

    def test_a_later_quarter_outranks_any_clock_in_an_earlier_one(self):
        assert live_progress_position(
            "14:59 - 4th Quarter", "14:59"
        ) > live_progress_position("0:01 - 3rd Quarter", "0:01")

    def test_end_of_a_quarter_sits_after_every_clocked_moment_in_it(self):
        assert live_progress_position(
            "End of 3rd Quarter", None
        ) > live_progress_position("0:04 - 3rd Quarter", "0:04")

    def test_end_of_a_quarter_sits_before_the_next_one(self):
        assert live_progress_position(
            "End of 3rd Quarter", None
        ) < live_progress_position("15:00 - 4th Quarter", "15:00")

    def test_overtime_outranks_regulation(self):
        assert live_progress_position("10:00 - OT", "10:00") > live_progress_position(
            "0:01 - 4th Quarter", "0:01"
        )

    def test_a_second_overtime_outranks_the_first(self):
        assert live_progress_position("5:00 - 2OT", "5:00") > live_progress_position(
            "0:02 - OT", "0:02"
        )

    def test_hockey_periods_read_the_same_way_as_quarters(self):
        """Same countdown grammar, same string shape; NHL simply had no live row
        in the measured window, which is not the same as being unsupported."""
        assert live_progress_position(
            "3:10 - 2nd Period", "3:10"
        ) > live_progress_position("18:40 - 2nd Period", "18:40")

    @pytest.mark.parametrize(
        "earlier,later",
        [
            ("Top 1st", "Bottom 1st"),
            ("Bottom 1st", "Top 2nd"),
            ("Top 8th", "Bottom 9th"),
            ("Bottom 9th", "Top 10th"),
        ],
    )
    def test_baseball_orders_on_the_label_alone(self, earlier, later):
        """Baseball has no clock, so the half-inning label carries the ordering
        by itself — top before bottom, inning before inning."""
        assert live_progress_position(earlier, None) < live_progress_position(later, None)

    def test_the_clock_can_come_from_the_separate_column(self):
        """A writer that fills `game_clock` but leaves the clock off the period
        label is still placeable."""
        assert live_progress_position("4th Quarter", "2:00") == live_progress_position(
            "2:00 - 4th Quarter", None
        )

    def test_a_tenths_clock_parses(self):
        """ESPN serves `0:04.2` inside the last minute of a period."""
        assert live_progress_position("0:04.2 - 4th Quarter", "0:04.2") is not None


class TestWhatItRefusesToPlace:
    """Every one of these must be unplaceable, and the guard must therefore
    stand down on it. These are not gaps — they are the whole reason the guard
    cannot freeze a game it does not understand."""

    @pytest.mark.parametrize(
        "period",
        [
            "Halftime",  # measured, 168 NFL rows
            "Delayed",  # measured, 3 NCAAF rows
            "FT",  # soccer terminal
            "Final",
            "Final/OT",
            "1H",
            "2H",
            "Middle 3rd",  # StatPal MLB, #5017's unobserved-family list
            "End 9th",
            "",
            None,
        ],
    )
    def test_unplaceable_labels_are_none(self, period):
        assert live_progress_position(period, "5:00") is None

    def test_a_half_is_deliberately_unplaceable_because_direction_is_unknown(self):
        """Soccer's clock counts UP and college basketball's counts DOWN, and one
        `Half` label cannot be given a direction from the string alone. Guessing
        it would invert the comparison for a whole sport, so `Half` is out."""
        assert live_progress_position("38:00 - 1st Half", "38:00") is None
        assert live_progress_position("2nd Half", "12:00") is None

    def test_a_countdown_period_with_no_clock_anywhere_is_unplaceable(self):
        """The label alone says which quarter, not where in it — and the guard
        needs the second half of that to be worth anything."""
        assert live_progress_position("4th Quarter", None) is None

    def test_a_pregame_date_is_not_a_period(self):
        """#5390's population. `_sanitize_period` already refuses to STORE these,
        and this is the belt: were one to arrive, it must not be read as a
        position (`'5/23 - TBD'` must never place as quarter 5)."""
        assert live_progress_position("Wed, March 25th at 10:00 PM EDT", None) is None
        assert live_progress_position("5/23 - TBD", None) is None


# ---------------------------------------------------------------------------
# 2. The refusal itself
# ---------------------------------------------------------------------------


class TestTheGuardRefusesOnlyProvenReversions:
    def test_the_measured_specimen_is_refused(self):
        """The exact pair from production: the row is at 28–20 @5:21 and a feed
        offers 28–14 @5:26, which is five seconds EARLIER in the game."""
        assert live_write_would_revert(
            "5:21 - 4th Quarter", "5:21", "5:26 - 4th Quarter", "5:26"
        )

    def test_the_measured_recovery_is_not_refused(self):
        """The other half of the same flip: the ahead feed writing over the
        behind one must keep landing, or the page never recovers."""
        assert not live_write_would_revert(
            "5:26 - 4th Quarter", "5:26", "5:21 - 4th Quarter", "5:21"
        )

    def test_a_clock_going_up_is_refused(self):
        """ux's second symptom: 5:42 on the row, 6:41 offered."""
        assert live_write_would_revert(
            "5:42 - 4th Quarter", "5:42", "6:41 - 4th Quarter", "6:41"
        )

    def test_an_exact_tie_is_accepted(self):
        """A same-moment correction — two feeds at 5:21, one with a newer score —
        is the case the reader most needs to land."""
        assert not live_write_would_revert(
            "5:21 - 4th Quarter", "5:21", "5:21 - 4th Quarter", "5:21"
        )

    def test_a_correction_at_a_later_moment_is_accepted(self):
        """THE REASON THIS ORDERS ON TIME AND NOT ON SCORE. A touchdown reversed
        on review arrives as a LOWER score from a LATER moment, and must land.
        The guard cannot even see the score — which is the point — so the test
        asserts the position it does see."""
        assert not live_write_would_revert(
            "5:21 - 4th Quarter", "5:21", "4:58 - 4th Quarter", "4:58"
        )

    def test_an_earlier_quarter_is_refused_however_small_its_clock(self):
        assert live_write_would_revert(
            "14:00 - 4th Quarter", "14:00", "0:02 - 3rd Quarter", "0:02"
        )

    @pytest.mark.parametrize(
        "stored_period,incoming_period",
        [
            ("Halftime", "5:26 - 4th Quarter"),  # stored unplaceable
            ("5:21 - 4th Quarter", "Halftime"),  # incoming unplaceable
            (None, "5:26 - 4th Quarter"),  # a row with nothing in it yet
            ("5:21 - 4th Quarter", None),
            (None, None),
        ],
    )
    def test_it_stands_down_whenever_either_side_is_unplaceable(
        self, stored_period, incoming_period
    ):
        """NO EVIDENCE IS NOT EVIDENCE OF STALENESS. A guard that blocked writes
        it could not place would freeze every sport it does not parse."""
        assert not live_write_would_revert(
            stored_period, None, incoming_period, None
        )

    def test_a_frozen_row_unsticks_itself_as_the_game_moves_past_it(self):
        """There is no deadlock to time out of. The bar is the STORED position,
        which the game itself moves past: a feed refused at 5:26 against a row at
        5:21 is accepted the moment it reaches 5:20, with nothing reset."""
        row = ("5:21 - 4th Quarter", "5:21")
        assert live_write_would_revert(*row, "5:26 - 4th Quarter", "5:26")
        assert not live_write_would_revert(*row, "5:20 - 4th Quarter", "5:20")

    def test_it_is_symmetric_and_names_no_winning_feed(self):
        """Whichever feed is ahead at that instant wins that instant. Swap the
        two arguments and the verdict must swap with them — a guard that always
        favoured one writer would be an authority rule wearing a clock."""
        a = ("5:21 - 4th Quarter", "5:21")
        b = ("5:26 - 4th Quarter", "5:26")
        assert live_write_would_revert(*a, *b) is True
        assert live_write_would_revert(*b, *a) is False


# ---------------------------------------------------------------------------
# 3. The ESPN writer, driven through the real function
# ---------------------------------------------------------------------------


class _EspnEvent:
    """An ESPN board row shaped as `update_event_fields_from_espn` reads it."""

    def __init__(self, *, clock, status_detail, home_score, away_score):
        self.clock = clock
        self.status_detail = status_detail
        self.home_score = home_score
        self.away_score = away_score
        self.date = None
        self.period = None
        self.broadcasts = []
        self.season_type = None
        self.state = "in"
        self.status = "in"
        self.completed = False
        self.status_type = "STATUS_IN_PROGRESS"


async def _drive_espn(spec, ee, *, interloper=None, monkeypatch=None):
    """Drive the real ESPN writer against a real row, and read the DATABASE back.

    ⚠️ THIS RAIL USED TO BE A FAKE SESSION AND A PLAIN OBJECT, and that was a
    hole, not a shortcut. Once the four live-state columns are written by a
    conditional UPDATE rather than by ORM assignment (#6056 / CERT-2829), a
    write that matched ZERO ROWS is indistinguishable from one that landed if
    the assertions read an in-memory object — SQLAlchemy's `synchronize_session`
    mirrors the values onto the instance either way, and a fake session cannot
    execute the statement at all. Every assertion in this section would have
    been satisfiable with the database untouched. So the row is re-read through
    `expire_all()` after the commit, and what the tests assert on is what the
    next reader would actually be served.

    `interloper(engine, event_id)` runs in its OWN session at the one instant
    that matters — after the real writer has read the row's position and decided
    the fetch is not a reversion, and before it writes. Hung on
    `live_write_would_revert` rather than on a sleep, for the same reason the
    schedule rail does it: a timing test that passes by luck is not a test.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models.models import Base, Event, ScoreSnapshot, Sport
    from app.utils.espn_helpers import update_event_fields_from_espn

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Event.__table__, Sport.__table__, ScoreSnapshot.__table__]
    )
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key="americanfootball_nfl", name="americanfootball_nfl")
    session.add(sport)
    session.flush()
    event = Event(
        sport_id=sport.id,
        home_team_name=spec.home_team_name,
        away_team_name=spec.away_team_name,
        commence_time=spec.commence_time,
        status=spec.status,
        period=spec.period,
        game_clock=spec.game_clock,
        home_score=spec.home_score,
        away_score=spec.away_score,
        espn_id=spec.espn_id,
        commence_time_source=spec.commence_time_source,
        win_probability_sources={},
    )
    session.add(event)
    session.commit()
    event_id = event.id

    class _AsyncShim:
        """The writer is async and this engine is not; nothing else is shimmed."""

        def __init__(self, inner):
            self._s = inner

        async def execute(self, statement):
            return self._s.execute(statement)

        def add(self, obj):
            self._s.add(obj)

        async def flush(self):
            self._s.flush()

        async def commit(self):
            self._s.commit()

    stats: dict = {}
    if interloper is not None:
        import app.utils.espn_helpers as espn_helpers

        _real_would_revert = espn_helpers.live_write_would_revert
        _fired = []

        def _revert_then_race(*args, **kwargs):
            verdict = _real_would_revert(*args, **kwargs)
            # Only race the branch that is about to WRITE — racing a refusal
            # would prove nothing, there being no write to overtake.
            if not verdict and not _fired:
                _fired.append(True)
                interloper(engine, event_id)
            return verdict

        monkeypatch.setattr(
            espn_helpers, "live_write_would_revert", _revert_then_race
        )

    await update_event_fields_from_espn(_AsyncShim(session), event, ee, set(), stats)
    session.commit()

    # The whole point of the rail: drop every cached value and ask the database.
    session.expire_all()
    row = session.execute(select(Event).where(Event.id == event_id)).scalar_one()
    snaps = session.execute(select(ScoreSnapshot)).scalars().all()
    return row, snaps, stats


class _Row:
    """The live event row, with only the columns this writer touches."""

    def __init__(self, *, period, game_clock, home_score, away_score):
        self.id = 14637256
        self.period = period
        self.game_clock = game_clock
        self.home_score = home_score
        self.away_score = away_score
        self.home_team_name = "New York Giants"
        self.away_team_name = "Dallas Cowboys"
        self.commence_time = datetime.now(timezone.utc) - timedelta(hours=3)
        self.completed_at = None
        self.commence_time_source = "espn"
        self.status = "live"
        self.espn_id = "401872930"
        self.broadcast_info = None
        self.llm_importance = None
        self.win_probability_sources = {}


@pytest.mark.asyncio
async def test_espn_does_not_write_an_observation_from_earlier_in_the_game():
    """The row is at 28–20 @5:21; ESPN offers 28–14 @5:26. Every one of the four
    live-state columns must be left alone — not three of them."""
    row = _Row(
        period="5:21 - 4th Quarter", game_clock="5:21", home_score=28, away_score=20
    )
    ee = _EspnEvent(
        clock="5:26",
        status_detail="5:26 - 4th Quarter",
        home_score=28,
        away_score=14,
    )
    row, snaps, stats = await _drive_espn(row, ee)

    assert row.home_score == 28
    assert row.away_score == 20, "the touchdown must not leave the page"
    assert row.game_clock == "5:21", "the clock must not go up"
    assert row.period == "5:21 - 4th Quarter"
    assert snaps == [], "a refused write must leave no ScoreSnapshot either"
    assert stats["live_state_reversions_refused"] == 1


@pytest.mark.asyncio
async def test_the_refusal_covers_the_home_side_too():
    """The measured 02:59:09 write was `21–14` over a stored `28–14` — the HOME
    number reverting, with away unchanged. Written because a mutation run proved
    the specimen above could not see it: both of its scores share a home value,
    so removing the home-side gate killed nothing. Two near-identical tests, one
    per side, is the price of a specimen whose two columns are not symmetric."""
    row = _Row(
        period="7:26 - 4th Quarter", game_clock="7:26", home_score=28, away_score=14
    )
    ee = _EspnEvent(
        clock="9:01",
        status_detail="9:01 - 4th Quarter",
        home_score=21,
        away_score=14,
    )
    row, snaps, stats = await _drive_espn(row, ee)

    assert row.home_score == 28, "the extra point must not un-score itself"
    assert row.away_score == 14
    assert row.game_clock == "7:26"
    assert snaps == []
    assert stats["live_state_reversions_refused"] == 1


@pytest.mark.asyncio
async def test_espn_still_writes_an_observation_from_later_in_the_game():
    """The twin. A guard with no accepting branch would pass the test above."""
    row = _Row(
        period="5:26 - 4th Quarter", game_clock="5:26", home_score=28, away_score=14
    )
    ee = _EspnEvent(
        clock="5:21",
        status_detail="5:21 - 4th Quarter",
        home_score=28,
        away_score=20,
    )
    row, snaps, stats = await _drive_espn(row, ee)

    assert (row.home_score, row.away_score) == (28, 20)
    assert row.game_clock == "5:21"
    assert row.period == "5:21 - 4th Quarter"
    assert len(snaps) == 1, "an accepted score change still snapshots"
    assert "live_state_reversions_refused" not in stats


@pytest.mark.asyncio
async def test_espn_writes_normally_onto_a_row_it_cannot_be_placed_against():
    """A row with no period yet — every game's first live write. The guard must
    be invisible here, or nothing would ever start."""
    row = _Row(period=None, game_clock=None, home_score=None, away_score=None)
    ee = _EspnEvent(
        clock="12:00",
        status_detail="12:00 - 1st Quarter",
        home_score=0,
        away_score=7,
    )
    row, _snaps, _stats = await _drive_espn(row, ee)

    assert (row.home_score, row.away_score) == (0, 7)
    assert row.period == "12:00 - 1st Quarter"


@pytest.mark.asyncio
async def test_a_lower_score_from_a_later_moment_still_lands_from_espn():
    """The correction case, end to end: a point comes off the board at a later
    clock and must reach the row."""
    row = _Row(
        period="5:21 - 4th Quarter", game_clock="5:21", home_score=28, away_score=20
    )
    ee = _EspnEvent(
        clock="5:02",
        status_detail="5:02 - 4th Quarter",
        home_score=27,
        away_score=20,
    )
    row, _snaps, _stats = await _drive_espn(row, ee)

    assert row.home_score == 27, "a reviewed-away point must still come off"


# ---------------------------------------------------------------------------
# 4. The StatPal writer, driven through the real task
#
# Harness shape borrowed from #5017's suite, which tests the same loop.
# ---------------------------------------------------------------------------


class _Fixture:
    def __init__(self, start_time, home, away, *, raw_status, game_clock, scores):
        self.start_time = start_time
        self.home_team = home
        self.away_team = away
        self.status = "live"
        self.fixture_id = "280459"
        self.odds_id = None
        self.home_score, self.away_score = scores
        self.raw_status = raw_status
        self.game_clock = game_clock
        self.clock_field_served = True


async def _run_livescores(monkeypatch, *, fixtures, events, interloper=None):
    """Drive the real `_sync_statpal_livescores` and return the rows.

    `interloper(engine, event_ids)` makes the realtime/realtime race
    deterministic (#6056, CERT-2829): it is called exactly once, from a SECOND
    `Session`, at the instant the real task has read the row's position, decided
    the fixture is not a reversion, and has not yet written — the only window in
    which a newer writer can be overtaken. Hung on `live_write_would_revert`,
    not on a sleep.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    import app.services.statpal_api as statpal_api
    import app.tasks.base as task_base
    from app.models.models import Base, Event, ScoreSnapshot, Sport
    from app.tasks.statpal_sync import _sync_statpal_livescores

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Event.__table__, Sport.__table__, ScoreSnapshot.__table__]
    )
    sync_session = Session(engine, expire_on_commit=False)

    # sqlite reloads datetimes naive and the premature-live guard (#1945)
    # compares against an aware `now`. Rail fidelity gap, not a production shape.
    @sa_event.listens_for(sync_session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    sport = Sport(key="americanfootball_nfl", name="americanfootball_nfl")
    sync_session.add(sport)
    sync_session.flush()
    ids = []
    for home, away, clock, period, scores in events:
        row = Event(
            sport_id=sport.id,
            home_team_name=home,
            away_team_name=away,
            commence_time=now - timedelta(hours=3),
            status="live",
            game_clock=clock,
            period=period,
            home_score=scores[0],
            away_score=scores[1],
        )
        sync_session.add(row)
        sync_session.flush()
        ids.append(row.id)
    sync_session.commit()

    class _AsyncShim:
        def __init__(self, session):
            self._s = session

        async def execute(self, statement):
            return self._s.execute(statement)

        def add(self, obj):
            self._s.add(obj)

        async def commit(self):
            self._s.commit()

        async def flush(self):
            self._s.flush()

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(sync_session)

        async def __aexit__(self_inner, *exc):
            sync_session.commit()
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    class _Service:
        async def get_live_scores(self, sport):
            return list(fixtures)

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    if interloper is not None:
        import app.tasks.statpal_sync as statpal_sync

        _real_would_revert = statpal_sync.live_write_would_revert
        _fired = []

        def _revert_then_race(*args, **kwargs):
            verdict = _real_would_revert(*args, **kwargs)
            if not verdict and not _fired:
                _fired.append(True)
                interloper(engine, ids)
            return verdict

        monkeypatch.setattr(
            statpal_sync, "live_write_would_revert", _revert_then_race
        )

    result = await _sync_statpal_livescores()
    # EXPIRE BEFORE READING. Without it a conditional UPDATE that matched zero
    # rows reads identically to one that landed, because `synchronize_session`
    # mirrors the values onto the loaded instance regardless (#6056).
    sync_session.expire_all()
    rows = [
        sync_session.execute(select(Event).where(Event.id == i)).scalar_one()
        for i in ids
    ]
    snaps = sync_session.execute(select(ScoreSnapshot)).scalars().all()
    return rows, snaps, result


@pytest.mark.asyncio
async def test_statpal_does_not_write_a_fixture_from_earlier_in_the_game(monkeypatch):
    now = datetime.now(timezone.utc)
    fixture = _Fixture(
        now - timedelta(hours=3),
        "New York Giants",
        "Dallas Cowboys",
        raw_status="4th Quarter",
        game_clock="5:26",
        scores=(28, 14),
    )
    rows, snaps, result = await _run_livescores(
        monkeypatch,
        fixtures=[fixture],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "5:21",
                "5:21 - 4th Quarter",
                (28, 20),
            )
        ],
    )

    assert rows[0].away_score == 20, "the touchdown must not leave the page"
    assert rows[0].game_clock == "5:21"
    assert rows[0].period == "5:21 - 4th Quarter"
    assert snaps == [], "a refused write must not snapshot the score it did not store"
    assert result["reverting_live_skipped"] == 1


@pytest.mark.asyncio
async def test_statpal_refusal_covers_the_home_side_too(monkeypatch):
    """Same gap, same reason, on the other writer's rail."""
    now = datetime.now(timezone.utc)
    fixture = _Fixture(
        now - timedelta(hours=3),
        "New York Giants",
        "Dallas Cowboys",
        raw_status="4th Quarter",
        game_clock="9:01",
        scores=(21, 14),
    )
    rows, snaps, result = await _run_livescores(
        monkeypatch,
        fixtures=[fixture],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "7:26",
                "7:26 - 4th Quarter",
                (28, 14),
            )
        ],
    )

    assert rows[0].home_score == 28
    assert rows[0].away_score == 14
    assert rows[0].game_clock == "7:26"
    assert snaps == []
    assert result["reverting_live_skipped"] == 1


@pytest.mark.asyncio
async def test_statpal_still_writes_a_fixture_from_later_in_the_game(monkeypatch):
    """The twin, on the same rail — without it the test above passes with the
    StatPal writer deleted."""
    now = datetime.now(timezone.utc)
    fixture = _Fixture(
        now - timedelta(hours=3),
        "New York Giants",
        "Dallas Cowboys",
        raw_status="4th Quarter",
        game_clock="5:21",
        scores=(28, 20),
    )
    rows, snaps, result = await _run_livescores(
        monkeypatch,
        fixtures=[fixture],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "5:26",
                "5:26 - 4th Quarter",
                (28, 14),
            )
        ],
    )

    assert rows[0].away_score == 20
    assert rows[0].game_clock == "5:21"
    assert rows[0].period == "5:21 - 4th Quarter"
    assert len(snaps) == 1
    assert result["reverting_live_skipped"] == 0


@pytest.mark.asyncio
async def test_statpal_halftime_is_untouched_by_the_guard(monkeypatch):
    """`Halftime` is unplaceable on purpose, so #5017's behaviour — the period
    advances and the venue's cleared clock is honoured — must be unchanged."""
    now = datetime.now(timezone.utc)
    fixture = _Fixture(
        now - timedelta(hours=3),
        "New York Giants",
        "Dallas Cowboys",
        raw_status="Halftime",
        game_clock=None,
        scores=(14, 10),
    )
    rows, _snaps, result = await _run_livescores(
        monkeypatch,
        fixtures=[fixture],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "0:00",
                "0:00 - 2nd Quarter",
                (14, 7),
            )
        ],
    )

    assert rows[0].period == "Halftime"
    assert rows[0].game_clock is None
    assert rows[0].away_score == 10
    assert result["reverting_live_skipped"] == 0


# ---------------------------------------------------------------------------
# 5. The clockless feed
# ---------------------------------------------------------------------------


class TestTheClocklessFeedStandsDown:
    def test_it_defers_on_a_live_row_an_authority_feed_covers(self):
        assert clockless_write_defers_to_authority("live", "401872930")

    def test_it_does_not_defer_when_no_authority_feed_is_attached(self):
        """Most college football, handball, the smaller soccer leagues — this
        feed is the only score writer they have, and deferring there would be
        deferring to nobody. Measured: NCAAF and handball rows carry non-ESPN
        score snapshots and no StatPal coverage at all."""
        assert not clockless_write_defers_to_authority("live", None)
        assert not clockless_write_defers_to_authority("live", "")

    @pytest.mark.parametrize("status", ["completed", "closed", "scheduled", "suspended", None])
    def test_it_never_defers_off_a_live_row(self, status):
        """THE FINAL SCORE IS THE CASE THAT MATTERS. A settled row is not being
        fought over, and the write that lands the final number must never be
        withheld — that is the one moment this feed noticing first is worth more
        than the flicker."""
        assert not clockless_write_defers_to_authority(status, "401872930")

    def test_both_conditions_are_load_bearing(self):
        """Neither is a proxy for the other: dropping `live` would withhold final
        scores, dropping `espn_id` would silence the only writer some sports
        have. Asserted together so a later simplification to one term reddens."""
        assert clockless_write_defers_to_authority("live", 1) is True
        assert clockless_write_defers_to_authority("live", None) is False
        assert clockless_write_defers_to_authority("completed", 1) is False
        assert clockless_write_defers_to_authority("completed", None) is False


def test_the_odds_feed_actually_consults_the_predicate():
    """The predicate is only worth testing if the loop reads it. `odds_polling`
    is a thousand-line async pass over a live HTTP client, so this asserts the
    wiring by import rather than by driving it — the four cases above then carry
    the behaviour."""
    import app.tasks.odds_polling as odds_polling

    assert odds_polling.clockless_write_defers_to_authority is (
        clockless_write_defers_to_authority
    )


# ---------------------------------------------------------------------------
# 6. The HOURLY writer nobody had counted (CERT-2824)
#
# The guard above covers `_sync_statpal_livescores`, the 30-second writer. It is
# not the only StatPal live-score writer: `_sync_statpal_schedules` fetches
# `get_live_scores(sport)` at the top of its sport loop "to get current game
# state" and assigns `event.home_score` / `away_score` from it — and FOUR beats
# reach that function every hour (NBA `:00`, NHL `:01`, MLB `:02`, NFL `:03`,
# `app/tasks/__init__.py`). So once an hour, on a live row, the same reversion
# could still land at a slower cadence. Found by an independent reviewer's AST
# probe of the real function, not by reading.
#
# These drive the REAL hourly task, not the predicate: the predicate is already
# covered above, and what was wrong here was the wiring.
# ---------------------------------------------------------------------------


class _ScheduleFixture:
    """A season-schedule row. Separate from `_Fixture` because the schedule and
    livescore boards are different payloads and this path reads `fixture_id` to
    find the row it will enrich."""

    def __init__(self, start_time, home, away, *, fixture_id, status="scheduled"):
        self.fixture_id = fixture_id
        self.home_team = home
        self.away_team = away
        self.start_time = start_time
        self.end_time = None
        self.status = status
        self.raw_status = None
        self.game_clock = None
        self.clock_field_served = True


class _LiveFixture:
    """A live-board row as the hourly pass consumes it."""

    def __init__(self, start_time, home, away, *, raw_status, game_clock, scores):
        self.fixture_id = "280459"
        self.home_team = home
        self.away_team = away
        self.start_time = start_time
        self.end_time = None
        self.status = "live"
        self.raw_status = raw_status
        self.game_clock = game_clock
        self.home_score, self.away_score = scores
        self.clock_field_served = True


class _FixtureFetch:
    def __init__(self, fixtures):
        self.fixtures = fixtures
        self.reason = "ok"
        self.sport = "nfl"
        self.endpoint = "/v1/nfl/schedule"
        self.asked = True
        self.is_alarm = False


async def _run_schedules(
    monkeypatch, *, schedule, live, events, interloper=None, on_finish=None
):
    """Drive the real `_sync_statpal_schedules` for NFL and return the rows.

    Same rail as `_run_livescores` above, plus the two collaborators this path
    reaches that the livescore path does not: team identity resolution and the
    event registry. Both are stubbed to no-ops — this is a test about which
    score lands on a row, and a real `resolve_team` would only add a second
    source of failure to a question it has no part in.

    `interloper` makes the background/realtime RACE deterministic (#6056,
    CERT-2825). It is called `interloper(engine, event_ids)` exactly once, at
    the instant the real task has read the row's position, decided the incoming
    observation is not a reversion, and has not yet written — i.e. the only
    window in which a newer writer can be overtaken. It is invoked from a
    SECOND `Session`, so the task's session holds a stale in-memory row exactly
    as the background worker would while realtime commits underneath it. The
    hook is hung on `live_write_would_revert` rather than on a sleep because a
    timing test that passes by luck is not a test.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    import app.services.statpal_api as statpal_api
    import app.tasks.base as task_base
    import app.tasks.statpal_sync as statpal_sync
    from app.models.models import Base, Event, ScoreSnapshot, Sport
    from app.tasks.statpal_sync import _sync_statpal_schedules

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Event.__table__, Sport.__table__, ScoreSnapshot.__table__]
    )
    sync_session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(sync_session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    sport = Sport(key="americanfootball_nfl", name="americanfootball_nfl")
    sync_session.add(sport)
    sync_session.flush()
    ids = []
    for home, away, clock, period, scores, fixture_id in events:
        row = Event(
            sport_id=sport.id,
            home_team_name=home,
            away_team_name=away,
            commence_time=now - timedelta(hours=3),
            status="live",
            game_clock=clock,
            period=period,
            home_score=scores[0],
            away_score=scores[1],
            statpal_fixture_id=fixture_id,
            home_team_id=1,
            away_team_id=2,
        )
        sync_session.add(row)
        sync_session.flush()
        ids.append(row.id)
    sync_session.commit()

    class _AsyncShim:
        def __init__(self, session):
            self._s = session

        async def execute(self, statement):
            return self._s.execute(statement)

        def add(self, obj):
            self._s.add(obj)

        async def commit(self):
            self._s.commit()

        async def flush(self):
            self._s.flush()

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(sync_session)

        async def __aexit__(self_inner, *exc):
            sync_session.commit()
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    class _Service:
        async def get_fixtures_result(self, sport):
            return _FixtureFetch(list(schedule))

        async def get_live_scores(self, sport):
            return list(live)

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    class _Team:
        id = 1

    async def _resolve_team(session, source, sport_key, source_name=None):
        return _Team()

    from app.services import team_identity

    monkeypatch.setattr(
        team_identity.team_identity_service, "resolve_team", _resolve_team
    )
    # Every row in these fixtures is pre-bound (`home_team_id` set), so the
    # binder is never consulted for a decision; stubbed only so a real one
    # cannot introduce a second failure mode.
    monkeypatch.setattr(
        statpal_sync, "accept_team_binding", lambda **kw: False, raising=False
    )

    if interloper is not None:
        _real_would_revert = statpal_sync.live_write_would_revert
        _fired = []

        def _revert_then_race(*args, **kwargs):
            verdict = _real_would_revert(*args, **kwargs)
            # Only race the branch that is about to WRITE. Firing on a refusal
            # would prove nothing: there is no write to overtake.
            if not verdict and not _fired:
                _fired.append(True)
                interloper(engine, ids)
            return verdict

        monkeypatch.setattr(
            statpal_sync, "live_write_would_revert", _revert_then_race
        )

    result = await _sync_statpal_schedules("americanfootball_nfl")
    # EXPIRE BEFORE READING, or this rail cannot tell a write that reached
    # Postgres from one that only reached an attribute (#6056, second
    # presentation). The task now writes the live score with a Core
    # compare-and-write and mirrors it onto the loaded object with
    # `set_committed_value`, so a `select(Event)` here returns the identity-mapped
    # instance and would report the mirrored value even if the UPDATE had
    # matched zero rows — every assertion below would pass with the database
    # untouched. Expiring forces a re-SELECT, so `rows` is what the next reader
    # of the row would actually be served.
    #
    # `on_finish` runs BEFORE the expiry, and is the only way to see the loaded
    # instances as the task left them — which is a separate contract from what
    # the database holds. See
    # `test_the_loaded_row_agrees_with_the_database_after_a_compare_and_write`.
    if on_finish is not None:
        on_finish(
            [
                sync_session.execute(select(Event).where(Event.id == i)).scalar_one()
                for i in ids
            ]
        )
    sync_session.expire_all()
    rows = [
        sync_session.execute(select(Event).where(Event.id == i)).scalar_one()
        for i in ids
    ]
    return rows, result


@pytest.mark.asyncio
async def test_schedule_sync_cannot_restore_an_earlier_live_score_6056(monkeypatch):
    """THE REQUIRED TEST (CERT-2824).

    The row is at `28-20 @ 5:21 Q4`. The hourly board offers `28-14 @ 5:26 Q4` —
    the same touchdown #6056 watched leave the page, arriving an hour later
    through a writer the first fix did not cover. `5:26` remaining is EARLIER in
    a countdown quarter than `5:21`, so it cannot be news.
    """
    now = datetime.now(timezone.utc)
    rows, result = await _run_schedules(
        monkeypatch,
        schedule=[
            _ScheduleFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                fixture_id="280459",
            )
        ],
        live=[
            _LiveFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="5:26",
                scores=(28, 14),
            )
        ],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "5:21",
                "5:21 - 4th Quarter",
                (28, 20),
                "280459",
            )
        ],
    )

    assert rows[0].away_score == 20, "the touchdown must not leave the page"
    assert rows[0].home_score == 28
    assert result["schedule_reverting_live_skipped"] == 1


@pytest.mark.asyncio
async def test_schedule_sync_refusal_covers_the_home_side_too(monkeypatch):
    """The specimen above differs only on the AWAY score, so deleting the
    home-side assignment would survive it. This one moves the other column."""
    now = datetime.now(timezone.utc)
    rows, result = await _run_schedules(
        monkeypatch,
        schedule=[
            _ScheduleFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                fixture_id="280459",
            )
        ],
        live=[
            _LiveFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="9:01",
                scores=(21, 7),
            )
        ],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "7:26",
                "7:26 - 4th Quarter",
                (28, 14),
                "280459",
            )
        ],
    )

    assert rows[0].home_score == 28
    assert rows[0].away_score == 14
    assert result["schedule_reverting_live_skipped"] == 1


@pytest.mark.asyncio
async def test_schedule_sync_still_writes_a_later_observation(monkeypatch):
    """THE CONTROL, and the one that matters most: without it every assertion
    above passes with the hourly score write deleted outright. A LOWER score
    from a LATER moment — a touchdown reversed on review — must still land."""
    now = datetime.now(timezone.utc)
    rows, result = await _run_schedules(
        monkeypatch,
        schedule=[
            _ScheduleFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                fixture_id="280459",
            )
        ],
        live=[
            _LiveFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="3:04",
                scores=(28, 14),
            )
        ],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "5:21",
                "5:21 - 4th Quarter",
                (28, 20),
                "280459",
            )
        ],
    )

    assert rows[0].away_score == 14, "a later correction must still land"
    assert result["schedule_reverting_live_skipped"] == 0


@pytest.mark.asyncio
async def test_schedule_sync_accepts_a_same_position_correction(monkeypatch):
    """An exact tie is accepted — the guard refuses proven reversions, it does
    not gatekeep live updates. Same moment, corrected number."""
    now = datetime.now(timezone.utc)
    rows, result = await _run_schedules(
        monkeypatch,
        schedule=[
            _ScheduleFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                fixture_id="280459",
            )
        ],
        live=[
            _LiveFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="5:21",
                scores=(28, 19),
            )
        ],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "5:21",
                "5:21 - 4th Quarter",
                (28, 20),
                "280459",
            )
        ],
    )

    assert rows[0].away_score == 19
    assert result["schedule_reverting_live_skipped"] == 0


@pytest.mark.asyncio
async def test_schedule_sync_writes_when_the_row_has_no_position(monkeypatch):
    """A row with no stored period is the common case on this path, and it must
    stay writable: "cannot place it" is not evidence of staleness, and a guard
    that froze those rows would be worse than the flicker."""
    now = datetime.now(timezone.utc)
    rows, result = await _run_schedules(
        monkeypatch,
        schedule=[
            _ScheduleFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                fixture_id="280459",
            )
        ],
        live=[
            _LiveFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="5:26",
                scores=(28, 14),
            )
        ],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                None,
                None,
                (0, 0),
                "280459",
            )
        ],
    )

    assert (rows[0].home_score, rows[0].away_score) == (28, 14)
    assert result["schedule_reverting_live_skipped"] == 0


# ---------------------------------------------------------------------------
# 6. THE RACE BETWEEN THE DECISION AND THE WRITE (CERT-2825)
#
# Guarding the hourly writer sequentially is not enough on the real topology.
# `_sync_statpal_schedules` runs on the BACKGROUND queue; the 30-second StatPal
# livescore writer and the ESPN writer run on REALTIME at concurrency 4. The
# hourly path plain-SELECTs its rows, decides, mutates ORM state and commits at
# session exit with no lock, no version column and — measured, per the #4307
# note in that file — NO intermediate commit, so the window between reading
# `event.period` and the score reaching Postgres spans every remaining fixture
# in the sport, network calls included.
#
# An older accepted observation could therefore commit its score AFTER a newer
# realtime one, and the reader watches the touchdown leave the page for exactly
# the reason #6056 is about, one layer down.
#
# These drive the REAL task with a deterministic interleave: the second session
# commits the newer position at the precise instant the task has decided and
# not yet written. Both directions, as everywhere in this file — the losing
# race refuses, the uncontested write still lands.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_schedule_writer_cannot_commit_older_position_last_6056(
    monkeypatch,
):
    """THE REQUIRED TEST (CERT-2825).

    The row is at `21-10 @ 5:31 Q4` when the hourly pass reads it. The board
    offers `28-14 @ 5:26 Q4` — later in the quarter, so NOT a reversion, and the
    sequential guard correctly says write. Then, before that write lands, the
    realtime writer commits `28-20 @ 5:21 Q4`: later still.

    Read-newer-commit-older. Without the compare-and-write the hourly session's
    `away_score = 14` reaches the database last and the reader watches 20 fall
    back to 14 beside a clock that says 5:21. With it, the UPDATE's predicate no
    longer matches the row and the newer state survives.

    ⚠️ THE SPECIMEN IS CHOSEN SO BOTH COLUMNS ARE GENUINELY DIRTY. The first
    draft of this test used the measured `28-14` on both sides; an ORM
    assignment of the value a column already holds does not mark it dirty, so
    the unfixed parent wrote nothing and the test passed on the defect. Every
    number below differs from the one beside it for that reason.
    """
    from sqlalchemy import create_engine, select, update
    from sqlalchemy.orm import Session

    from app.models.models import Event

    def _realtime_writer_commits_a_later_position(engine, ids):
        """The other queue, in its own session — a second identity map, and a
        commit the task's session knows nothing about."""
        other = Session(engine, expire_on_commit=False)
        try:
            other.execute(
                update(Event)
                .where(Event.id == ids[0])
                .values(
                    period="5:21 - 4th Quarter",
                    game_clock="5:21",
                    home_score=28,
                    away_score=20,
                )
            )
            other.commit()
        finally:
            other.close()

    now = datetime.now(timezone.utc)
    rows, result = await _run_schedules(
        monkeypatch,
        schedule=[
            _ScheduleFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                fixture_id="280459",
            )
        ],
        live=[
            _LiveFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="5:26",
                scores=(28, 14),
            )
        ],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "5:31",
                "5:31 - 4th Quarter",
                (21, 10),
                "280459",
            )
        ],
        interloper=_realtime_writer_commits_a_later_position,
    )

    # What the next reader is served. The touchdown stays scored.
    assert (rows[0].home_score, rows[0].away_score) == (28, 20)
    assert (rows[0].period, rows[0].game_clock) == ("5:21 - 4th Quarter", "5:21")
    # And the sequential guard is exonerated: it said WRITE, correctly, on the
    # position it was shown. The race is what refused, and it is counted under
    # its own name so the two causes stay distinguishable in `task-metrics`.
    assert result["schedule_reverting_live_skipped"] == 0
    assert result["schedule_live_write_lost_race"] == 1


@pytest.mark.asyncio
async def test_the_race_is_refused_when_only_the_period_moved_6056(monkeypatch):
    """The twin of the test below, and the other half of the predicate.

    Baseball is the natural specimen: the period label carries the whole
    position (`live_progress_position('Top 9th', None)` is placeable, and the
    `GROUP BY` behind this file's vocabulary found exactly these shapes) and
    `game_clock` stays NULL all game. So a realtime writer moves the game on by
    rewriting `period` alone.

    The required test moves both columns, so `game_clock` alone catches it — a
    predicate that re-asserted only the clock would pass it and let this
    through. Found alive as a mutant.
    """
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from app.models.models import Event

    def _realtime_writer_moves_only_the_period(engine, ids):
        other = Session(engine, expire_on_commit=False)
        try:
            other.execute(
                update(Event)
                .where(Event.id == ids[0])
                .values(period="Bot 9th", home_score=3, away_score=2)
            )
            other.commit()
        finally:
            other.close()

    now = datetime.now(timezone.utc)
    rows, result = await _run_schedules(
        monkeypatch,
        schedule=[
            _ScheduleFixture(
                now - timedelta(hours=3),
                "Boston Red Sox",
                "New York Yankees",
                fixture_id="280459",
            )
        ],
        live=[
            _LiveFixture(
                now - timedelta(hours=3),
                "Boston Red Sox",
                "New York Yankees",
                raw_status="Top 9th",
                game_clock=None,
                scores=(3, 1),
            )
        ],
        events=[
            (
                "Boston Red Sox",
                "New York Yankees",
                None,
                "Top 9th",
                (2, 1),
                "280459",
            )
        ],
        interloper=_realtime_writer_moves_only_the_period,
    )

    assert (rows[0].home_score, rows[0].away_score) == (3, 2)
    assert rows[0].game_clock is None, "the specimen's point is that it did not move"
    assert result["schedule_live_write_lost_race"] == 1


@pytest.mark.asyncio
async def test_the_race_is_refused_when_only_the_clock_moved_6056(monkeypatch):
    """BOTH columns the decision reads are in the predicate, not just `period`.

    The decision is taken on the pair `(period, game_clock)` — `game_clock` is a
    column in its own right, and `live_progress_position("4th Quarter", "5:26")`
    is placeable precisely because a writer may fill the clock while leaving it
    off the label (ESPN's `status_detail` is `'Top 9th'` / `'4th Quarter'` for
    several sports; only StatPal composes the compound string). So a realtime
    writer can move the game a quarter-minute forward without touching `period`
    at all.

    A predicate that re-asserted only `period` would pass the required test
    above — it moves both — and still let this one through. That mutant was
    found alive; this is what kills it.
    """
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from app.models.models import Event

    def _realtime_writer_moves_only_the_clock(engine, ids):
        other = Session(engine, expire_on_commit=False)
        try:
            other.execute(
                update(Event)
                .where(Event.id == ids[0])
                .values(game_clock="5:21", home_score=28, away_score=20)
            )
            other.commit()
        finally:
            other.close()

    now = datetime.now(timezone.utc)
    rows, result = await _run_schedules(
        monkeypatch,
        schedule=[
            _ScheduleFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                fixture_id="280459",
            )
        ],
        live=[
            _LiveFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="5:24",
                scores=(28, 14),
            )
        ],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "5:26",
                "4th Quarter",
                (21, 10),
                "280459",
            )
        ],
        interloper=_realtime_writer_moves_only_the_clock,
    )

    assert (rows[0].home_score, rows[0].away_score) == (28, 20)
    assert rows[0].period == "4th Quarter", "the specimen's point is that it did not move"
    assert result["schedule_live_write_lost_race"] == 1


@pytest.mark.asyncio
async def test_an_uncontested_schedule_write_still_lands_under_the_compare_and_write(
    monkeypatch,
):
    """The twin (gotcha #43). The same specimen with a race that touches a
    DIFFERENT row: the predicate must not refuse a write merely because some
    other session committed. A compare-and-write that refused everything would
    pass the test above and freeze every live score on the site."""
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from app.models.models import Event

    def _realtime_writer_touches_the_other_game(engine, ids):
        other = Session(engine, expire_on_commit=False)
        try:
            other.execute(
                update(Event).where(Event.id == ids[1]).values(home_score=3)
            )
            other.commit()
        finally:
            other.close()

    now = datetime.now(timezone.utc)
    rows, result = await _run_schedules(
        monkeypatch,
        schedule=[
            _ScheduleFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                fixture_id="280459",
            )
        ],
        live=[
            _LiveFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="5:21",
                scores=(28, 20),
            )
        ],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "5:26",
                "5:26 - 4th Quarter",
                (28, 14),
                "280459",
            ),
            (
                "Kansas City Chiefs",
                "Denver Broncos",
                "2:00",
                "2:00 - 2nd Quarter",
                (0, 0),
                "280460",
            ),
        ],
        interloper=_realtime_writer_touches_the_other_game,
    )

    assert (rows[0].home_score, rows[0].away_score) == (28, 20)
    assert result["schedule_live_write_lost_race"] == 0


@pytest.mark.asyncio
async def test_the_loaded_row_agrees_with_the_database_after_a_compare_and_write(
    monkeypatch,
):
    """The mirror is load-bearing, so it is killable.

    The compare-and-write puts the score in the database with Core SQL, which
    leaves the loaded ORM instance holding the value it was SELECTed with. The
    task mirrors the new score back with `set_committed_value` — committed, not
    assigned, because a plain assignment would re-write both columns
    unconditionally at commit and undo the predicate the UPDATE just enforced.

    Without the mirror the session hands the rest of the loop a row whose score
    is a lie, which is the same class of defect this whole file exists to fix,
    just in memory instead of on the page. Asserted here rather than left to the
    next reader to discover: every other assertion in this section expires the
    session first and so cannot see it.
    """
    seen = []
    now = datetime.now(timezone.utc)
    rows, _ = await _run_schedules(
        monkeypatch,
        schedule=[
            _ScheduleFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                fixture_id="280459",
            )
        ],
        live=[
            _LiveFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="5:21",
                scores=(28, 20),
            )
        ],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "5:26",
                "5:26 - 4th Quarter",
                (21, 10),
                "280459",
            )
        ],
        on_finish=lambda loaded: seen.append(
            (loaded[0].home_score, loaded[0].away_score)
        ),
    )

    assert seen == [(28, 20)], "the loaded row still holds the pre-UPDATE score"
    # And the database agrees — the mirror reports what actually landed rather
    # than replacing the check.
    assert (rows[0].home_score, rows[0].away_score) == (28, 20)


def test_the_schedule_path_never_assigns_the_columns_its_cas_compares():
    """WHY THE COMPARE-AND-WRITE IS WELL-DEFINED UNDER GOTCHA #5.

    The Core UPDATE lives in a loop that also sets `commence_time`, `status`,
    `statpal_end_time`, the team ids and the `win_probability_sources` JSONB as
    ORM attribute assignments on the same objects in the same session. Gotcha #5
    says mixing the two is where flush ordering starts deciding outcomes: if
    this function could assign `period` or `game_clock`, the predicate would
    compare against whichever side of the flush it happened to land on, and the
    guard would be a coin toss.

    It cannot, and that is the load-bearing fact — so it is asserted here rather
    than left in the comment beside the UPDATE. The moment somebody adds a
    `event.period = ...` to this function, this test reddens and the
    compare-and-write needs re-deriving, not merely re-running.
    """
    import ast
    import inspect
    import textwrap

    import app.tasks.statpal_sync as statpal_sync

    tree = ast.parse(
        textwrap.dedent(inspect.getsource(statpal_sync._sync_statpal_schedules))
    )
    assigned = {
        target.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Attribute)
    }
    assert "period" not in assigned
    assert "game_clock" not in assigned
    # Not vacuous: the same probe DOES see the attribute assignments this
    # function really makes, so an empty set could never manufacture the pass.
    assert "commence_time" in assigned
    assert "status" in assigned

    # AND THE SECOND HALF OF THE CLAIM: the live-update site no longer assigns
    # the scores as ORM attributes at all — it writes them through the Core
    # compare-and-write. The only remaining score assignments are the two in the
    # creation branch, which CERT-2824/2825 both left deliberately unguarded
    # (see `test_a_created_row_has_no_position_to_revert_from` for why). If a
    # future edit puts an ORM score assignment back on the update path, the
    # behavioural race test above would still pass — the ORM write would simply
    # land last — so this is the assertion that catches it.
    def _score_assign_nodes(root):
        return [
            node
            for node in ast.walk(root)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Attribute)
            and target.attr in ("home_score", "away_score")
        ]

    creation_branches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "was_created"
    ]
    assert creation_branches, "the creation branch moved; re-derive this probe"
    in_creation = {
        id(n) for branch in creation_branches for n in _score_assign_nodes(branch)
    }
    all_score_assigns = _score_assign_nodes(tree)
    assert len(all_score_assigns) == 2, (
        "expected exactly the two creation-path score assignments, found "
        f"{len(all_score_assigns)}"
    )
    assert all(id(n) in in_creation for n in all_score_assigns)


def test_the_hourly_writer_actually_consults_the_guard():
    """The AST claim CERT-2824 made, asserted as a test so it cannot regress
    silently: the real `_sync_statpal_schedules` reaches `live_write_would_revert`
    on the path to its `home_score` / `away_score` assignments. The behavioural
    tests above carry the meaning; this one catches a refactor that keeps them
    passing by accident (e.g. the write moving into a helper the stub shadows)."""
    import ast
    import inspect
    import textwrap

    import app.tasks.statpal_sync as statpal_sync

    tree = ast.parse(
        textwrap.dedent(inspect.getsource(statpal_sync._sync_statpal_schedules))
    )
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "live_write_would_revert" in called
    assert "statpal_live_position" in called
    assert statpal_sync.live_write_would_revert is live_write_would_revert


def test_the_position_helper_composes_what_the_writers_store():
    """`statpal_live_position` must compose the SAME string the live writers
    store, or the comparison is against a label no row ever holds."""
    from app.tasks.statpal_sync import statpal_live_position

    clocked = _LiveFixture(
        None, "h", "a", raw_status="4th Quarter", game_clock="5:26", scores=(0, 0)
    )
    assert statpal_live_position(clocked) == ("5:26 - 4th Quarter", "5:26")

    clockless = _LiveFixture(
        None, "h", "a", raw_status="Halftime", game_clock=None, scores=(0, 0)
    )
    assert statpal_live_position(clockless) == ("Halftime", None)

    # A bare `live` carries no position at all — it must not be composed into
    # one, or every such fixture would compare as an unplaceable string that
    # happens to parse.
    bare = _LiveFixture(
        None, "h", "a", raw_status="live", game_clock="5:26", scores=(0, 0)
    )
    assert statpal_live_position(bare) == (None, "5:26")


def test_a_created_row_has_no_position_to_revert_from():
    """Why the creation-path score write in `_sync_statpal_schedules` carries no
    reversion guard, asserted rather than claimed in a comment.

    That write is inside `if was_created`, which `find_or_create_event` returns
    only for a row it has just inserted — and `EventIdentity` carries neither
    `period` nor `game_clock`, so there is nothing stored to run backwards from.
    A guard there could only ever return False. If a future creation path starts
    pre-filling a position, this reddens and the guard becomes real work."""
    import inspect

    from app.services.event_registry import EventIdentity

    fields = set(inspect.signature(EventIdentity).parameters)
    assert "period" not in fields
    assert "game_clock" not in fields
    # And the decision itself, on the state such a row actually has:
    assert live_write_would_revert(None, None, "5:26 - 4th Quarter", "5:26") is False


# ---------------------------------------------------------------------------
# 7. The REALTIME producers write atomically too (#6056, CERT-2829)
#
# CERT-2825 was answered by making the hourly schedule pass compare-and-write.
# CERT-2829's finding is that this was one third of the job: the two writers on
# the REALTIME queue — `_sync_statpal_livescores` on a 30-second beat and
# `update_event_fields_from_espn` on ESPN's — still read the row's position,
# decided, and then ORM-assigned into a transaction that commits much later. At
# concurrency 4 an older accepted observation can wait behind a newer commit and
# then land on top of it, and a realtime write still pending can overwrite the
# hourly path's freshly-committed compare-and-write. Same reader-visible defect,
# same two columns, two more producers.
#
# The accepting branches for both producers are already covered above
# (`test_espn_still_writes_an_observation_from_later_in_the_game`,
# `test_statpal_still_writes_a_fixture_from_later_in_the_game`), and both now
# read the database rather than an in-memory object, so they are not repeated
# here.
# ---------------------------------------------------------------------------


def _commits_a_later_position(period, game_clock, scores):
    """A writer on ANOTHER queue, in its own session, committing a newer state.

    Its own `Session` is the point: the task under test keeps a stale in-memory
    row exactly as a concurrent worker would, and nothing about this commit is
    visible to the task's identity map.
    """

    def _run(engine, ids):
        from sqlalchemy import update
        from sqlalchemy.orm import Session

        from app.models.models import Event

        event_id = ids[0] if isinstance(ids, (list, tuple)) else ids
        other = Session(engine, expire_on_commit=False)
        try:
            other.execute(
                update(Event)
                .where(Event.id == event_id)
                .values(
                    period=period,
                    game_clock=game_clock,
                    home_score=scores[0],
                    away_score=scores[1],
                )
            )
            other.commit()
        finally:
            other.close()

    return _run


@pytest.mark.asyncio
async def test_concurrent_realtime_writers_cannot_commit_older_position_last_6056(
    monkeypatch,
):
    """THE REQUIRED TEST (CERT-2829), in both commit orders.

    One specimen, run twice with the producers swapped, because the defect is
    symmetric and a fix that only ordered one of the two would leave the other
    serving the same reader the same disappearing touchdown.

    The row is at `21–10 @ 5:31 Q4` when the realtime producer reads it. The
    feed offers `28–14 @ 5:26 Q4` — LATER in the quarter, so not a reversion,
    and the sequential guard correctly says write. Then, in the window between
    that decision and the write, the OTHER realtime producer commits
    `28–20 @ 5:21 Q4`: later still.

    Read-newer-commit-older. Without a write-time predicate the first producer's
    `away_score = 14` reaches Postgres last and the reader watches 20 fall back
    to 14 beside a clock reading 5:21.

    ⚠️ EVERY NUMBER DIFFERS FROM THE ONE BESIDE IT, deliberately. An ORM
    assignment of a value a column already holds does not mark it dirty, so a
    specimen that reuses a number lets the unfixed parent write nothing and pass
    on the defect. That mistake cost a presentation on the hourly twin of this
    test; it is not repeated.
    """
    now = datetime.now(timezone.utc)

    # ── ORDER 1: StatPal is the slow producer, ESPN commits underneath it ────
    rows, snaps, result = await _run_livescores(
        monkeypatch,
        fixtures=[
            _Fixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="5:26",
                scores=(28, 14),
            )
        ],
        events=[
            ("New York Giants", "Dallas Cowboys", "5:31", "5:31 - 4th Quarter", (21, 10))
        ],
        interloper=_commits_a_later_position(
            "5:21 - 4th Quarter", "5:21", (28, 20)
        ),
    )

    assert (rows[0].home_score, rows[0].away_score) == (28, 20), (
        "the touchdown must stay scored — StatPal's older write lost the race"
    )
    assert (rows[0].period, rows[0].game_clock) == ("5:21 - 4th Quarter", "5:21")
    # The sequential guard is exonerated: it said WRITE, correctly, about the
    # row it was shown. The race is what refused, and it is counted under its
    # own name so the two causes stay apart in `task-metrics`.
    assert result["reverting_live_skipped"] == 0
    assert result["livescore_live_write_lost_race"] == 1
    assert snaps == [], (
        "a refused score must not reach score_snapshots either — that table is "
        "where this defect was diagnosed from"
    )

    # ── ORDER 2: ESPN is the slow producer, StatPal commits underneath it ────
    row, snaps, stats = await _drive_espn(
        _Row(
            period="5:31 - 4th Quarter",
            game_clock="5:31",
            home_score=21,
            away_score=10,
        ),
        _EspnEvent(
            clock="5:26",
            status_detail="5:26 - 4th Quarter",
            home_score=28,
            away_score=14,
        ),
        interloper=_commits_a_later_position(
            "5:21 - 4th Quarter", "5:21", (28, 20)
        ),
        monkeypatch=monkeypatch,
    )

    assert (row.home_score, row.away_score) == (28, 20), (
        "the touchdown must stay scored — ESPN's older write lost the race"
    )
    assert (row.period, row.game_clock) == ("5:21 - 4th Quarter", "5:21")
    assert "live_state_reversions_refused" not in stats
    assert stats["live_state_write_lost_race"] == 1
    assert snaps == []


@pytest.mark.asyncio
async def test_a_pending_realtime_write_cannot_overwrite_the_hourly_cas_6056(
    monkeypatch,
):
    """The inverse of the schedule race, which CERT-2829 named specifically.

    `test_concurrent_schedule_writer_cannot_commit_older_position_last_6056`
    proves the BACKGROUND pass cannot land on top of a newer REALTIME commit.
    This is the other direction: a realtime write already decided and still
    pending, with the hourly compare-and-write committing a newer position
    underneath it. Guarding only one direction would leave the pair no better
    off than guarding neither — whichever producer happened to be slow that
    minute would still win.

    The interloper here commits the position the hourly pass produces, from its
    own session, in the realtime producer's decision-to-write window.
    """
    now = datetime.now(timezone.utc)
    rows, snaps, result = await _run_livescores(
        monkeypatch,
        fixtures=[
            _Fixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="2:14",
                scores=(31, 20),
            )
        ],
        events=[
            ("New York Giants", "Dallas Cowboys", "2:19", "2:19 - 4th Quarter", (28, 20))
        ],
        interloper=_commits_a_later_position(
            "1:58 - 4th Quarter", "1:58", (31, 27)
        ),
    )

    assert (rows[0].home_score, rows[0].away_score) == (31, 27)
    assert (rows[0].period, rows[0].game_clock) == ("1:58 - 4th Quarter", "1:58")
    assert result["livescore_live_write_lost_race"] == 1
    assert result["reverting_live_skipped"] == 0


@pytest.mark.asyncio
async def test_a_clockless_authority_is_not_frozen_by_the_compare_and_write_6056():
    """THE CONTROL THAT MATTERS MOST: the guard must not become a freeze.

    An observation the position helper cannot place — halftime, and every sport
    whose label carries no clock — is "no evidence", never "earliest". It has
    always been written, and the compare-and-write must not quietly change that
    into a refusal: an unplaceable authority that could not write would strand a
    live row at whatever the last placeable writer said, which is a worse and
    much quieter failure than the flicker this ship fixes.

    Uncontested, so the predicate matches and the write lands. That is the
    whole claim, and it is the branch a too-strict predicate would break.
    """
    row, _snaps, stats = await _drive_espn(
        _Row(
            period="0:00 - 2nd Quarter",
            game_clock="0:00",
            home_score=14,
            away_score=7,
        ),
        _EspnEvent(
            clock=None,
            status_detail="Halftime",
            home_score=14,
            away_score=10,
        ),
    )

    assert row.period == "Halftime", "an unplaceable label must still be written"
    assert (row.home_score, row.away_score) == (14, 10)
    assert "live_state_reversions_refused" not in stats, (
        "there is no evidence of a reversion here, so nothing may be refused"
    )
    assert "live_state_write_lost_race" not in stats, (
        "an uncontested write is not a lost race"
    )


def test_no_realtime_producer_assigns_the_columns_its_cas_compares():
    """Gotcha #5, asserted rather than promised.

    The compare-and-write's predicate reads `period` and `game_clock` off the
    row. If either producer ALSO assigned one of the four live-state columns as
    an ORM attribute, SQLAlchemy would flush that assignment ahead of the
    UPDATE and the predicate would end up comparing the row against a value the
    same pass had just written — a guard that has silently stopped guarding, and
    one no behavioural test would catch, because it fails only under
    concurrency.

    Walked as an AST, not grepped. The first draft of this scan was a regex and
    it failed on its own first run against a COMMENT — the line in
    `_sync_statpal_livescores` that quotes `event.period = ee.status_detail`
    while explaining what ESPN writes. A text scan for source structure reads
    prose, strings and dead code as if they were statements; only the parse
    tree distinguishes an assignment from a sentence about one.

    Non-vacuity is asserted twice over, and the SECOND way is the one that
    survives the subject changing shape. "The walk found some assignment" was
    the obvious check and it is wrong here: `_sync_statpal_livescores` now
    assigns no `event.*` attribute at all (its remaining writes go through
    `_set_statpal_id`), so that assertion fails on a clean tree and tempts
    whoever hits it to delete the safeguard. So the detector is instead run
    against a synthetic source that DOES contain the offence, and must find it —
    a check on the detector, independent of what the subjects happen to contain.
    """
    import ast
    import inspect
    import textwrap

    from app.tasks.mlb_sync import _sync_mlb_win_probability
    from app.tasks.statpal_sync import _sync_statpal_livescores
    from app.utils.espn_helpers import update_event_fields_from_espn
    from app.utils.live_state_write import LIVE_STATE_COLUMNS

    assert LIVE_STATE_COLUMNS == (
        "period", "game_clock", "home_score", "away_score"
    )

    def _event_attrs_assigned(source: str) -> set[str]:
        found = set()
        for node in ast.walk(ast.parse(source)):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "event"
                ):
                    found.add(target.attr)
        return found

    # The detector fires on the exact defect it exists to catch — including the
    # comment that broke the regex draft, which must NOT be picked up.
    assert _event_attrs_assigned(
        "# event.game_clock = ee.clock\n"
        "event.period = 'x'\n"
        "event.status = 'live'\n"
        "if event.home_score != 3:\n    pass\n"
    ) == {"period", "status"}

    for fn in (
        _sync_statpal_livescores,
        update_event_fields_from_espn,
        _sync_mlb_win_probability,
    ):
        source = textwrap.dedent(inspect.getsource(fn))

        calls = {
            node.func.id
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "write_live_state_if_unmoved" in calls, (
            f"{fn.__name__} no longer routes its live-state write through the "
            "compare-and-write — this scan would be measuring nothing"
        )

        offenders = _event_attrs_assigned(source) & set(LIVE_STATE_COLUMNS)
        assert not offenders, (
            f"{fn.__name__} assigns {sorted(offenders)} directly; every "
            f"live-state column must go through write_live_state_if_unmoved, "
            f"or the predicate ends up comparing the row against this pass's "
            f"own pending write"
        )


@pytest.mark.asyncio
async def test_the_compare_and_write_touches_only_its_own_row_6056(monkeypatch):
    """🔴 FOUND BY MUTATION, and the worst failure in this file if it were real.

    Dropping `Event.id == event.id` from the predicate left a LIVE mutant: every
    test here had a single row, so a statement that updated the whole table
    passed all of them. The remaining predicate is a POSITION, and a position is
    emphatically not unique — every row that has not started yet holds
    `(NULL, NULL)`, so the unscoped statement would stamp one game's score
    across every other game sharing its clock. A silent whole-table write is not
    a worse version of this defect; it is a different and much larger one.

    Two live rows at the SAME position, one fixture. The other row must not
    move.
    """
    now = datetime.now(timezone.utc)
    rows, _snaps, _result = await _run_livescores(
        monkeypatch,
        fixtures=[
            _Fixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="5:26",
                scores=(28, 14),
            )
        ],
        events=[
            ("New York Giants", "Dallas Cowboys", "5:31", "5:31 - 4th Quarter", (21, 10)),
            # Same clock, same period — a different game, and the only thing
            # separating the two in the statement is the id.
            ("Green Bay Packers", "Chicago Bears", "5:31", "5:31 - 4th Quarter", (3, 7)),
        ],
    )

    assert (rows[0].home_score, rows[0].away_score) == (28, 14), (
        "the row the fixture is about must still be written"
    )
    assert (rows[1].home_score, rows[1].away_score) == (3, 7), (
        "a different game sharing the same clock was overwritten"
    )
    assert (rows[1].period, rows[1].game_clock) == ("5:31 - 4th Quarter", "5:31")


@pytest.mark.asyncio
async def test_a_refused_realtime_write_leaves_no_score_snapshot(monkeypatch):
    """The implication the snapshot gate leans on, asserted directly.

    The gate reads `if updated and ...`, which is correct only because nothing
    before it sets `updated` except the compare-and-write itself. Spelling the
    condition `_live_write_landed and updated` made that explicit and was
    unkillable by mutation — the extra term is implied — so the term went and
    this took its place. If a future change sets `updated` earlier for some
    reason unrelated to live state, this test is what fails.
    """
    now = datetime.now(timezone.utc)
    _rows, snaps, result = await _run_livescores(
        monkeypatch,
        fixtures=[
            _Fixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="4th Quarter",
                game_clock="5:26",
                scores=(28, 14),
            )
        ],
        events=[
            ("New York Giants", "Dallas Cowboys", "5:31", "5:31 - 4th Quarter", (21, 10))
        ],
        interloper=_commits_a_later_position(
            "5:21 - 4th Quarter", "5:21", (28, 20)
        ),
    )

    assert result["livescore_live_write_lost_race"] == 1
    assert snaps == [], (
        "the refused 28-14 reached score_snapshots — the chart would show the "
        "overtaken observation the row correctly rejected"
    )
    assert result["score_snapshots_created"] == 0


# ---------------------------------------------------------------------------
# 7. The MLB writer — THE FOURTH PRODUCER (CERT-2833)
#
# Four presentations of this ship converted three writers, and a fourth was
# sitting in plain sight the whole time: `sync_mlb_win_probability`, a 120-second
# REALTIME task that ORM-assigned `period` and `game_clock` on live baseball rows
# that StatPal and ESPN also write.
#
# It is worth being precise about why this one is not merely a fourth instance
# of the same race, because the difference decides what the fix has to contain.
# The other three READ the row, DECIDED, and then lost a race writing. MLB never
# asked anything at all: two unconditional assignments, whatever the feed last
# said. So it had both failure modes at once — it could lose a race like its
# siblings, AND it could walk a row backwards with no concurrency whatever, any
# minute its feed ran a poll behind ESPN's. Both are tested below, separately,
# because a fix containing only the compare-and-write would pass the race test
# and leave a reader watching the innings count down.
# ---------------------------------------------------------------------------


class _MlbGame:
    """One in-progress game as `MLBAPIService.get_live_games()` returns it."""

    def __init__(
        self, *, inning, inning_half, home_score, away_score,
        home_wp=0.61, away_wp=0.39,
    ):
        self.game_pk = 776541
        self.home_team = "Boston Red Sox"
        self.away_team = "New York Yankees"
        self.game_datetime = None
        self.home_win_probability = home_wp
        self.away_win_probability = away_wp
        self.home_score = home_score
        self.away_score = away_score
        self.inning = inning
        self.inning_half = inning_half


async def _drive_mlb(
    monkeypatch, *, row_period, row_clock, game, interloper=None, extra_rows=(),
):
    """Drive the REAL MLB task against a REAL row and read the DATABASE back.

    Same rail as `_drive_espn`, and for the same reason: once these columns are
    written by a conditional UPDATE, an assertion that reads an in-memory object
    cannot tell a write that matched zero rows from one that landed — SQLAlchemy
    mirrors the values onto the instance either way. So the row is re-read after
    `expire_all()`, and what the tests assert on is what the next reader is
    served.

    Two things are substituted and nothing else. The MLB API service, because
    there is no network here; and `_create_or_update_win_prob_snapshot`, because
    the win-probability snapshot is a different column family on a different
    table and keeping the real one would buy this test nothing but a dialect
    dependency. THE `win_probability_sources` CORE UPDATE IS LEFT REAL AND
    DELIBERATELY SO: in production that statement is what takes the row lock,
    just before the live-state write, and it is therefore part of the ordering
    under test.

    `interloper(engine, event_id)` runs in its own session at the one instant
    that matters — after the task has loaded the row's position and before it
    writes over it — and it is hung on the SNAPSHOT CALL, never on a sleep.

    ⚠️ THE CHOICE OF HOOK IS THE WHOLE REASON THIS RAIL CAN BE RUN ON THE
    PARENT. The obvious hook is `live_write_would_revert`, which is what the
    ESPN and StatPal rails above use — but this producer does not import that
    symbol until the commit under test adds it, so a rail hung there raises
    `AttributeError` on the parent and yields a harness story instead of a
    witness. `_create_or_update_win_prob_snapshot` is called by BOTH trees, at
    the same point in the pass, between the load and the live-state write; it
    is also where the real window lives, since that call and the MLB fetches
    around it are what the decision-to-write gap is actually made of.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    import app.tasks.mlb_sync as mlb_sync
    from app.models.models import Base, Event, Sport

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Event.__table__, Sport.__table__])
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key="baseball_mlb", name="baseball_mlb")
    session.add(sport)
    session.flush()

    started = datetime.now(timezone.utc) - timedelta(hours=2)
    specs = [
        ("Boston Red Sox", "New York Yankees", row_period, row_clock)
    ] + list(extra_rows)
    ids = []
    for home, away, period, clock in specs:
        ev = Event(
            sport_id=sport.id,
            home_team_name=home,
            away_team_name=away,
            commence_time=started,
            status="live",
            period=period,
            game_clock=clock,
            win_probability_sources={},
        )
        session.add(ev)
        session.flush()
        ids.append(ev.id)
    session.commit()

    class _AsyncShim:
        """The task is async and this engine is not; nothing else is shimmed."""

        def __init__(self, inner):
            self._s = inner

        async def execute(self, statement):
            return self._s.execute(statement)

        def add(self, obj):
            self._s.add(obj)

        async def flush(self):
            self._s.flush()

        async def commit(self):
            self._s.commit()

    class _SessionCM:
        async def __aenter__(self):
            return _AsyncShim(session)

        async def __aexit__(self, *exc):
            return False

    class _Service:
        async def get_live_games(self):
            return [game]

        async def close(self):
            return None

    import app.services.mlb_api as mlb_api

    monkeypatch.setattr(mlb_api, "MLBAPIService", lambda *a, **k: _Service())
    monkeypatch.setattr(mlb_sync, "get_task_session", lambda: _SessionCM())

    _fired = []

    async def _no_snapshot(*_a, **_k):
        if interloper is not None and not _fired:
            _fired.append(True)
            interloper(engine, ids[0])
        return (None, False)

    monkeypatch.setattr(
        mlb_sync, "_create_or_update_win_prob_snapshot", _no_snapshot
    )

    stats = await mlb_sync._sync_mlb_win_probability()

    if interloper is not None:
        assert _fired, (
            "the interloper never ran — this rail proved nothing about a race"
        )

    session.expire_all()
    rows = [
        session.execute(select(Event).where(Event.id == i)).scalar_one()
        for i in ids
    ]
    return rows, stats


@pytest.mark.asyncio
async def test_mlb_realtime_writer_cannot_commit_older_position_last_6056(
    monkeypatch,
):
    """THE REQUIRED TEST (CERT-2833), with its uncontested twin.

    The row is at `Top 4th` when the MLB task reads it. MLB's feed offers
    `Top 5th` — LATER, so not a reversion, and the sequential guard correctly
    says write. Then, in the window between that decision and the write, ESPN
    commits `Bottom 6th` from its own session: later still.

    Read-newer-commit-older. MLB's pass holds ONE session across every game and
    commits at the very end, so without a write-time predicate its `Top 5th`
    reaches Postgres last and the reader watches the sixth inning fall back to
    the fifth.

    ⚠️ EVERY POSITION DIFFERS FROM THE ONE BESIDE IT, deliberately: an ORM
    assignment of a value the column already holds does not mark it dirty, so a
    specimen that reuses one lets the unfixed parent write nothing and pass on
    the defect. That mistake cost a presentation on the hourly twin of this
    test.
    """
    # ── CONTESTED: ESPN commits underneath MLB's decided-but-unwritten pass ──
    rows, stats = await _drive_mlb(
        monkeypatch,
        row_period="Top 4th",
        row_clock="Top 4",
        game=_MlbGame(inning=5, inning_half="top", home_score=2, away_score=1),
        interloper=_commits_a_later_position("Bottom 6th", "Bottom 6", (4, 3)),
    )

    assert (rows[0].period, rows[0].game_clock) == ("Bottom 6th", "Bottom 6"), (
        "the game must not go back an inning — MLB's older write lost the race"
    )
    # The sequential guard is exonerated: it said WRITE, correctly, about the
    # row it was shown. The race is what refused, and the two causes are counted
    # apart so `task-metrics` can tell them apart.
    assert stats["mlb_reverting_live_skipped"] == 0
    assert stats["mlb_live_write_lost_race"] == 1

    # ── THE UNCONTESTED TWIN: nothing races, so the write must LAND ─────────
    #
    # Without this, a compare-and-write that refused everything — or one whose
    # predicate could never match — would pass the assertion above and freeze
    # every live baseball row at its first position.
    rows, stats = await _drive_mlb(
        monkeypatch,
        row_period="Top 4th",
        row_clock="Top 4",
        game=_MlbGame(inning=5, inning_half="top", home_score=2, away_score=1),
    )

    assert (rows[0].period, rows[0].game_clock) == ("Top 5th", "Top 5"), (
        "an uncontested MLB write must still reach the row"
    )
    assert stats["mlb_live_write_lost_race"] == 0
    assert stats["mlb_reverting_live_skipped"] == 0


@pytest.mark.asyncio
async def test_mlb_does_not_walk_a_row_back_to_an_earlier_inning_6056(monkeypatch):
    """The half of this producer's defect that needs no concurrency at all.

    MLB assigned both columns unconditionally, so the ONLY thing that kept a
    live row moving forwards was MLB's feed happening to be the freshest of the
    three. The moment it ran a poll behind ESPN's — routine, on a 120-second
    beat against a feed nobody arbitrates — it wrote the earlier inning straight
    over the later one, no race required.

    The row is at `Bottom 6th`; MLB offers `Top 5th`. Nothing else is running.
    """
    rows, stats = await _drive_mlb(
        monkeypatch,
        row_period="Bottom 6th",
        row_clock="Bottom 6",
        game=_MlbGame(inning=5, inning_half="top", home_score=2, away_score=1),
    )

    assert (rows[0].period, rows[0].game_clock) == ("Bottom 6th", "Bottom 6"), (
        "MLB walked the row back an inning and a half with nothing racing it"
    )
    assert stats["mlb_reverting_live_skipped"] == 1
    assert stats["mlb_live_write_lost_race"] == 0, (
        "this is the sequential guard's refusal, not a lost race — counting it "
        "as one would send the next reader of task-metrics after a phantom"
    )


@pytest.mark.asyncio
async def test_mlb_still_writes_an_inning_the_row_has_not_reached_6056(monkeypatch):
    """The accepting twin of the refusal above.

    A guard with no accepting branch passes every refusal test ever written and
    strands every live baseball row at whatever position it happened to hold
    when this shipped.
    """
    rows, stats = await _drive_mlb(
        monkeypatch,
        row_period="Top 5th",
        row_clock="Top 5",
        game=_MlbGame(inning=6, inning_half="bottom", home_score=4, away_score=3),
    )

    assert (rows[0].period, rows[0].game_clock) == ("Bottom 6th", "Bottom 6")
    assert stats["mlb_reverting_live_skipped"] == 0
    assert stats["mlb_live_write_lost_race"] == 0


@pytest.mark.asyncio
async def test_mlb_writes_normally_onto_a_row_with_no_position_yet_6056(monkeypatch):
    """Every baseball game's first live write, and the branch a too-strict
    predicate breaks. The row holds `(NULL, NULL)`; the write must land."""
    rows, stats = await _drive_mlb(
        monkeypatch,
        row_period=None,
        row_clock=None,
        game=_MlbGame(inning=1, inning_half="top", home_score=0, away_score=0),
    )

    assert (rows[0].period, rows[0].game_clock) == ("Top 1st", "Top 1")
    assert stats["mlb_live_write_lost_race"] == 0


@pytest.mark.asyncio
async def test_the_mlb_write_touches_only_its_own_row_6056(monkeypatch):
    """The whole-table mutant, on this producer's statement.

    `Event.id == event.id` is the only term separating two rows at the same
    position, and every unstarted baseball row in the table holds the same
    `(NULL, NULL)`. A statement missing that term would stamp one game's inning
    across every other game that had not started yet.
    """
    rows, _stats = await _drive_mlb(
        monkeypatch,
        row_period=None,
        row_clock=None,
        game=_MlbGame(inning=3, inning_half="bottom", home_score=1, away_score=0),
        extra_rows=[("Chicago Cubs", "St. Louis Cardinals", None, None)],
    )

    assert (rows[0].period, rows[0].game_clock) == ("Bottom 3rd", "Bottom 3"), (
        "the row the feed is about must still be written"
    )
    assert (rows[1].period, rows[1].game_clock) == (None, None), (
        "a different game sharing the same empty position was overwritten"
    )


# ---------------------------------------------------------------------------
# 7b. THE TENNIS AUTHORITY PASS (live/224) — THE FIFTH PRODUCER
#
# `_sync_tennis_from_espn` is a `*/5` beat on `background` that writes
# `home_score`/`away_score` on live tennis rows, while ESPN and StatPal write
# the same rows from `realtime` at concurrency 4. It holds ONE session across
# the WHOLE pass — opened before the first row, committed after the last, two
# blocking HTTP fetches in between — so its decision-to-write window is the
# widest of the five, not the narrowest.
#
# ⚠️ ITS PREDICATE IS NOT POSITION, AND THAT IS THE DESIGN, NOT AN OMISSION.
# This pass never reads or writes `period`/`game_clock`; its decision
# (`authority_score_write`) compares ESPN's set score against the row's own
# `home_score`/`away_score`. On a tennis row the two position columns are
# routinely NULL, so predicating on them would produce a compare-and-write that
# is called, green, and arbitrating nothing — the exact failure this suite's
# structural guard exists to catch, wearing the costume of a fix. So it
# re-asserts the two columns its decision actually consumed.
# ---------------------------------------------------------------------------


def _tennis_competition(comp_id, names, *, home_sets, away_sets, date):
    """ESPN's real competition shape, scored by the per-set WINNER flag.

    `date` is passed in rather than fixed: the anchor refuses any competition
    outside a window around the row's own `commence_time`, so a literal here
    would silently make every one of these specimens `off-board` the moment the
    suite was run on a different day (gotcha #44 — an anchor that drifts against
    the clock is not an anchor).
    """
    def _line(games, won):
        return [{"value": float(g), "winner": w} for g, w in zip(games, won)]

    sets = home_sets + away_sets
    return {
        "id": comp_id,
        "date": date,
        "status": {
            "period": sets,
            "type": {
                "name": "STATUS_IN_PROGRESS",
                "state": "in",
                "detail": "detail",
                "shortDetail": "",
            },
        },
        "competitors": [
            {
                "id": "3203",
                "type": "athlete",
                "athlete": {"displayName": names[0], "id": "3203"},
                "linescores": _line([6] * sets, [True] * home_sets + [False] * away_sets),
            },
            {
                "id": "3204",
                "type": "athlete",
                "athlete": {"displayName": names[1], "id": "3204"},
                "linescores": _line([4] * sets, [False] * home_sets + [True] * away_sets),
            },
        ],
    }


async def _drive_tennis(
    monkeypatch, *, row_home, row_away, espn_home_sets, espn_away_sets,
    interloper=None,
):
    """Drive the REAL tennis task against a REAL row and read the DATABASE back.

    Same rail and same reason as `_drive_espn` / `_drive_mlb`: once the score is
    written by a conditional UPDATE, an assertion that reads the in-memory object
    cannot tell a write that matched zero rows from one that landed, because
    SQLAlchemy mirrors the values onto the instance either way. The row is
    re-read after `expire_all()`, so what is asserted is what the next reader of
    the US Open page is served.

    ⚠️ THE HOOK IS `authority_score_write`, AND THE CHOICE IS THE WHOLE REASON
    THIS RAIL CAN BE RUN ON THE PARENT. It is called by BOTH trees at the same
    point — after the row's two scores have been read, before either is written
    — so it is exactly the decision-to-write window, and a rail hung there
    yields a witness on the unfixed tree instead of an `AttributeError` wearing
    a harness story. `write_row_if_unmoved` would have been the obvious hook and
    is the wrong one: the parent does not import it.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    import app.tasks.espn_sync as espn_sync
    import app.services.espn_tennis as espn_tennis
    import app.utils.espn_tennis_anchor as anchor
    from app.models.models import Base, Event, Sport

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Event.__table__, Sport.__table__])
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key="tennis_atp_us_open", name="tennis_atp_us_open")
    session.add(sport)
    session.flush()

    started = datetime.now(timezone.utc) - timedelta(hours=2)
    event = Event(
        sport_id=sport.id,
        home_team_name="Carlos Alcaraz",
        away_team_name="Roman Safiullin",
        commence_time=started,
        status="live",
        espn_id="182705",
        home_score=row_home,
        away_score=row_away,
    )
    session.add(event)
    session.flush()
    event_id = event.id
    session.commit()

    class _AsyncShim:
        """The task is async and this engine is not; nothing else is shimmed."""

        def __init__(self, inner):
            self._s = inner

        async def execute(self, statement):
            return self._s.execute(statement)

        def add(self, obj):
            self._s.add(obj)

        async def flush(self):
            self._s.flush()

        async def commit(self):
            self._s.commit()

    class _SessionCM:
        async def __aenter__(self):
            return _AsyncShim(session)

        async def __aexit__(self, *exc):
            return False

    board = [{
        "events": [{
            "name": "US Open",
            "groupings": [{
                "grouping": {"slug": "mens-singles"},
                "competitions": [_tennis_competition(
                    "182705", ["Carlos Alcaraz", "Roman Safiullin"],
                    home_sets=espn_home_sets, away_sets=espn_away_sets,
                    date=started.strftime("%Y-%m-%dT%H:%MZ"),
                )],
            }],
        }]
    }]

    monkeypatch.setattr(espn_tennis, "fetch_scoreboards", lambda dates=None: (board, []))
    monkeypatch.setattr(espn_sync, "get_task_session", lambda: _SessionCM())

    _fired = []
    _real_decision = anchor.authority_score_write

    def _decide_then_let_the_other_writer_in(**kwargs):
        verdict = _real_decision(**kwargs)
        if interloper is not None and not _fired:
            _fired.append(True)
            interloper(engine, event_id)
        return verdict

    monkeypatch.setattr(
        anchor, "authority_score_write", _decide_then_let_the_other_writer_in
    )

    stats = await espn_sync._sync_tennis_from_espn()

    if interloper is not None:
        assert _fired, (
            "the interloper never ran — this rail proved nothing about a race"
        )

    session.expire_all()
    row = session.execute(select(Event).where(Event.id == event_id)).scalar_one()
    return row, stats


def _commits_a_different_score(home_score, away_score):
    """A realtime writer, in its own session, committing a newer score."""

    def _run(engine, event_id):
        from sqlalchemy import update
        from sqlalchemy.orm import Session

        from app.models.models import Event

        other = Session(engine, expire_on_commit=False)
        try:
            other.execute(
                update(Event)
                .where(Event.id == event_id)
                .values(home_score=home_score, away_score=away_score)
            )
            other.commit()
        finally:
            other.close()

    return _run


@pytest.mark.asyncio
async def test_tennis_authority_writer_cannot_commit_an_older_score_last_6056(
    monkeypatch,
):
    """THE FIFTH PRODUCER'S RACE, with its uncontested twin.

    The row reads 1-0 when the tennis pass loads it. ESPN's board says the match
    is at 2-0, so the authority decides to write 2-0 — correctly, about the row
    it was shown. Then, in the window between that decision and the write, the
    realtime writer commits 3-0 from its own session: Alcaraz has closed it out.

    Read-newer-commit-older. The tennis pass holds ONE session across the whole
    board and commits at the very end, so without a write-time predicate its
    2-0 reaches Postgres last and the set that won the match disappears off the
    US Open page until the next beat five minutes later.

    ⚠️ EVERY SCORE DIFFERS FROM THE ONE BESIDE IT — 1, then 2, then 3 — and the
    interloper's value differs from the one the authority is OFFERING, not just
    from the one the row held. `authority_score_write` emits only the columns
    that changed, so an interloper that happens to commit the same `home_score`
    the authority offers leaves the parent writing a value already in the column:
    not dirty, not flushed, no reversion, and a test that passes on the unfixed
    tree while proving nothing. The first draft of this test did exactly that.
    """
    # ── CONTESTED: the realtime writer commits under a decided-but-unwritten pass
    row, stats = await _drive_tennis(
        monkeypatch,
        row_home=1, row_away=0,
        espn_home_sets=2, espn_away_sets=0,
        interloper=_commits_a_different_score(3, 0),
    )

    assert (row.home_score, row.away_score) == (3, 0), (
        "the set that won the match must not vanish — the tennis pass's older "
        "write lost the race and had to be dropped"
    )
    assert stats["score_write_lost_race"] == 1
    assert stats["score_writes"] == 0, (
        "a refused write must not also be counted as a write — `score_writes` "
        "is what tells the next reader the authority moved a row"
    )

    # ── THE UNCONTESTED TWIN: nothing races, so the write must LAND ─────────
    #
    # Without this, a compare-and-write whose predicate could never match would
    # pass the assertion above and silently freeze every live tennis score.
    row, stats = await _drive_tennis(
        monkeypatch,
        row_home=1, row_away=0,
        espn_home_sets=2, espn_away_sets=0,
    )

    assert (row.home_score, row.away_score) == (2, 0), (
        "an uncontested tennis score write must still reach the row"
    )
    assert stats["score_write_lost_race"] == 0
    assert stats["score_writes"] == 1


@pytest.mark.asyncio
async def test_a_compare_and_write_with_nothing_to_compare_is_refused_6056():
    """An empty predicate is an unconditional UPDATE wearing the name of a CAS.

    The failure this forecloses is the quiet one. `write_row_if_unmoved` takes
    its predicate as a mapping, so a caller that builds one and gets an empty
    dict — a column list that filtered to nothing, a rename, a typo'd key —
    would compile, run, overwrite unconditionally, return True, and be counted
    as a successful guarded write forever after. There is no symptom to notice.

    Raising is right rather than returning False: an empty predicate is a
    programming error at the call site, not a lost race, and reporting it as a
    lost race would send the next reader of `task-metrics` after a phantom.
    """
    from app.utils.live_state_write import write_row_if_unmoved

    class _Blowup:
        async def flush(self):  # pragma: no cover - must never be reached
            raise AssertionError("the empty predicate was not refused")

        async def execute(self, *a, **k):  # pragma: no cover - same
            raise AssertionError("the empty predicate was not refused")

    with pytest.raises(ValueError, match="nothing to compare"):
        await write_row_if_unmoved(
            _Blowup(), object(), {"home_score": 2}, observed={}, what="test",
        )


@pytest.mark.asyncio
async def test_tennis_refuses_when_only_the_other_side_of_the_score_moved_6056(
    monkeypatch,
):
    """THE HALF A ONE-COLUMN PREDICATE WOULD MISS.

    `authority_score_write` emits a `changes` dict holding only the columns that
    differ — so when ESPN moves the home side alone, the statement WRITES one
    column. Its decision, though, read BOTH: it compared `away_score` too, and
    concluded it was already correct.

    So the predicate has to cover both columns, not just the written one. Here
    the home side is what the authority changes (1 -> 2) and the away side is
    what the interloper moves underneath (0 -> 1). A compare-and-write
    predicated only on the column it writes would match, land, and quietly erase
    the set Safiullin just won.
    """
    row, stats = await _drive_tennis(
        monkeypatch,
        row_home=1, row_away=0,
        espn_home_sets=2, espn_away_sets=0,
        interloper=_commits_a_different_score(1, 1),
    )

    assert (row.home_score, row.away_score) == (1, 1), (
        "the predicate read only the column it writes: the away set the "
        "realtime writer had just committed was erased"
    )
    assert stats["score_write_lost_race"] == 1


# ---------------------------------------------------------------------------
# 8. THE GUARD THAT SHOULD HAVE EXISTED FIRST (CERT-2833)
#
# Four presentations of this ship each converted the producers someone had
# thought of, and the guard above asserted that THOSE producers stayed clean. It
# could never have found MLB, because its population was a hand-written tuple of
# two names, and a hand-written population can only ever re-check the thing that
# was already known. The defect was not that MLB was missed once; it was that
# nothing in the suite was capable of noticing it.
#
# So the population is DISCOVERED here instead of declared, and what is declared
# is the much smaller thing: for each function that writes one of these columns
# outside the compare-and-write, WHY that is allowed. A new producer — or an old
# one growing a new assignment — lands in the discovered set, matches no entry,
# and turns this red with the file and function named.
# ---------------------------------------------------------------------------

#: Every function that assigns a live-state column as an ORM attribute, with the
#: reason it does not go through `write_live_state_if_unmoved`. An entry here is
#: a claim someone has to defend; an absence is a build break.
#:
#: The first four are REPAIR AND CREATION paths, not live-feed position writes —
#: there is no concurrent observation of a running game for them to land behind.
#: The LAST ONE is neither, and is recorded as what it is: a live-state writer of
#: the same class as the five this ship has converted, still outside the
#: compare-and-write. It is named rather than quietly absent precisely because
#: being quietly absent is what cost this ship four presentations.
#:
#: This list SHRINKS as the ship lands, and the guard below asserts it in both
#: directions — a declared writer that no longer offends fails just as loudly as
#: an undeclared one that does, so a spent exemption cannot sit here looking like
#: a live one. `_sync_tennis_from_espn` left this list in live/224 when it was
#: converted; it did not leave quietly.
_DECLARED_UNGUARDED_WRITERS = {
    "espn_sync._backfill_box_scores": (
        "REPAIR. Writes `None` over the 0–0 of a row wrongly marked completed, "
        "and over the phantom score of a settled row with a future start "
        "(gotcha #46). Both populations are rows whose score is already known "
        "to be fiction; neither is a position in a running game."
    ),
    "espn_sync._transition_event_statuses_impl": (
        "SETTLEMENT. `_corrected_final_score` writes a FINAL score as the game "
        "closes, not a moment inside it. There is no later observation for it "
        "to land behind — the game is over."
    ),
    "statpal_sync._sync_statpal_schedules": (
        "CREATION PATH ONLY. Guarded by `if was_created`, which is true only "
        "for a row this statement just INSERTed, whose position columns are "
        "therefore unset. Nothing to revert from, and a compare-and-write here "
        "would read as load-bearing while provably doing nothing. Asserted by "
        "`test_a_created_row_has_no_position_to_revert_from`, not by comment. "
        "This function's LIVE writes do go through the compare-and-write."
    ),
    "espn_helpers.backfill_missing_scores": (
        "BACKFILL over FINISHED rows that hold no score at all. Selects on the "
        "absence it fills, and runs against games ESPN has already closed."
    ),
    "admin_providers.sync_espn_live_events": (
        "KNOWN GAP, different exposure (#6056). Writes `period`/`game_clock` "
        "on live rows, but only when a person invokes the admin route — it is "
        "not on a beat, so it cannot race anything unattended. Converted after "
        "the tennis producer, which is scheduled and therefore the larger "
        "exposure of the two."
    ),
}


def test_no_undeclared_writer_assigns_a_live_state_column_6056():
    """THE POPULATION IS DISCOVERED, NOT LISTED — that is the whole point.

    Walked as an AST over every module under `backend/app/`, so a fifth
    producer cannot arrive by being somewhere nobody thought to look. The
    detector is self-tested against a synthetic source containing the offence,
    because "the walk found something" is the wrong non-vacuity check here: a
    correctly converted tree contains fewer of these every time this ship lands,
    and a scan asserted on its own yield would start failing for the best
    possible reason and tempt whoever hit it to delete the safeguard.
    """
    import ast
    import pathlib

    from app.utils.live_state_write import LIVE_STATE_COLUMNS

    def _assigners(source: str) -> dict[str, set[str]]:
        """{function name: {live-state columns it ORM-assigns}}."""
        found: dict[str, set[str]] = {}
        tree = ast.parse(source)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                targets = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                    targets = [node.target]
                flat = []
                for target in targets:
                    flat.extend(
                        target.elts if isinstance(target, ast.Tuple) else [target]
                    )
                for target in flat:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr in LIVE_STATE_COLUMNS
                        and isinstance(target.value, ast.Name)
                    ):
                        found.setdefault(fn.name, set()).add(target.attr)
        return found

    # The detector fires on the offence, ignores a COMMENT quoting it (the
    # mistake that broke the regex draft of the guard above), ignores a READ,
    # and sees a tuple-unpacked assignment — which is how
    # `_transition_event_statuses_impl` writes both scores at once and would
    # otherwise have been missed by a scan that only looked at plain targets.
    probe = _assigners(
        "def f():\n"
        "    # event.game_clock = ee.clock\n"
        "    event.period = 'x'\n"
        "    event.status = 'live'\n"
        "    if event.home_score != 3:\n"
        "        pass\n"
        "def g():\n"
        "    event.home_score, event.away_score = pair\n"
    )
    assert probe == {"f": {"period"}, "g": {"home_score", "away_score"}}, probe

    app_root = pathlib.Path(__file__).resolve().parents[1] / "app"
    assert app_root.is_dir(), app_root

    discovered = {}
    for path in sorted(app_root.rglob("*.py")):
        for name, columns in _assigners(path.read_text()).items():
            discovered[f"{path.stem}.{name}"] = sorted(columns)

    undeclared = sorted(set(discovered) - set(_DECLARED_UNGUARDED_WRITERS))
    assert not undeclared, (
        "a live-state column is being ORM-assigned by a writer nothing in this "
        f"suite knows about: {undeclared}. Every one of "
        f"{list(LIVE_STATE_COLUMNS)} on a live row must go through "
        "`write_live_state_if_unmoved`, or the write can land on top of a "
        "newer observation another producer committed in between (#6056). If "
        "the writer genuinely cannot race — a repair, a settlement, or a row "
        "it just created — add it to _DECLARED_UNGUARDED_WRITERS with the "
        "reason, and say which test holds the claim up."
    )

    # The other direction, so the declaration cannot rot into a list of
    # functions that no longer exist and quietly stop meaning anything.
    stale = sorted(set(_DECLARED_UNGUARDED_WRITERS) - set(discovered))
    assert not stale, (
        f"declared as unguarded but no longer assigns a live-state column: "
        f"{stale} — delete the entry, the exemption it carries is spent"
    )


def test_the_converted_producers_are_absent_from_the_declared_list_6056():
    """The list must never become the place a converted producer goes back.

    An exemption is easier to write than a compare-and-write, so the producers
    this ship converted are named here: if one of them ever appears in the
    declaration, someone has un-converted it and written a reason, and that is
    exactly the move this test exists to refuse. Each name is checked to be a
    real caller of the helper first, so a rename cannot turn this into an
    assertion about three strings that no longer denote anything.
    """
    import ast
    import inspect
    import textwrap

    from app.tasks.espn_sync import _sync_tennis_from_espn
    from app.tasks.mlb_sync import _sync_mlb_win_probability
    from app.tasks.statpal_sync import (
        _sync_statpal_livescores,
        _sync_statpal_schedules,
    )
    from app.utils.espn_helpers import update_event_fields_from_espn

    #: Producer -> the spelling of the compare-and-write it is expected to call.
    #: The tennis pass predicates on the two SCORE columns its decision read
    #: rather than on position, so it calls the general form; requiring the
    #: position-named one here would have forced it back to a predicate that
    #: cannot refuse on a tennis row.
    converted = {
        "statpal_sync._sync_statpal_livescores": (
            _sync_statpal_livescores, "write_live_state_if_unmoved",
        ),
        "statpal_sync._sync_statpal_schedules": (
            _sync_statpal_schedules, "write_live_state_if_unmoved",
        ),
        "espn_helpers.update_event_fields_from_espn": (
            update_event_fields_from_espn, "write_live_state_if_unmoved",
        ),
        "mlb_sync._sync_mlb_win_probability": (
            _sync_mlb_win_probability, "write_live_state_if_unmoved",
        ),
        "espn_sync._sync_tennis_from_espn": (
            _sync_tennis_from_espn, "write_row_if_unmoved",
        ),
    }
    for name, (fn, helper) in converted.items():
        source = textwrap.dedent(inspect.getsource(fn))
        calls = {
            node.func.id
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert helper in calls, (
            f"{name} no longer calls the compare-and-write — this test would "
            "be asserting about a producer that has stopped being one"
        )

    # `_sync_statpal_schedules` is in BOTH sets on purpose: its live writes go
    # through the helper and its creation path does not, which is why its
    # declaration says "CREATION PATH ONLY" rather than exempting the function.
    readmitted = sorted(
        (set(converted) - {"statpal_sync._sync_statpal_schedules"})
        & set(_DECLARED_UNGUARDED_WRITERS)
    )
    assert not readmitted, (
        f"{readmitted} went through the compare-and-write and now carries an "
        "exemption instead — that is a regression of #6056, not a declaration"
    )


def test_the_clockless_feed_is_out_of_the_orm_scans_reach_by_construction_6056():
    """A fact about the scan's BLIND SPOT, recorded so nobody trusts it too far.

    `odds_polling` is the fourth producer this ship arbitrated, and it is the
    one the AST scan above can never see: it writes through an `update_values`
    dict and a Core statement, so there is no ORM attribute assignment to find.
    It is also arbitrated by a different mechanism on purpose — it carries no
    clock and no period, so it cannot be placed on the game-time scale at all,
    and it defers to an attached authority instead of being ordered against it.

    Written as a test rather than a comment because the dangerous reading of the
    guard above is "everything that writes these columns is in that scan", and
    that is false. A future producer that writes via Core SQL needs its own
    reasoning, and this is where the next reader finds that out.
    """
    import ast
    import inspect
    import textwrap

    from app.tasks import odds_polling

    source = textwrap.dedent(inspect.getsource(odds_polling))
    calls = {
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "clockless_write_defers_to_authority" in calls, (
        "the clockless feed's precedence rule is gone, and the ORM scan cannot "
        "see this producer — nothing else in this suite is holding it up"
    )
    assert '"home_score"' in source or "'home_score'" in source, (
        "this producer is supposed to write its score as a Core value, keyed "
        "by string; if that changed, re-check whether the ORM scan now covers "
        "it and delete this test if it does"
    )


def test_the_cas_is_given_a_captured_position_never_a_fresh_read_6056():
    """🔴 FOUND BY MUTATION, and the reason it needs a STRUCTURAL guard.

    Replacing `observed_period=_observed_period` with `observed_period=
    event.period` at the call site leaves a LIVE mutant: every behavioural test
    in this file still passes. It has to, and the reason is worth writing down.
    A concurrent writer commits from its own session, so it moves the DATABASE
    row and not this session's instance — and nothing between the capture and
    the write refreshes that instance today. The two spellings therefore read
    the same value, and no specimen can separate them.

    What separates them is a change nobody has made yet. The moment one of these
    passes grows an intermediate commit — the standard remedy for holding a row
    lock too long (gotcha #13), and the remedy this ship's own watch item names
    for these very tasks — a default `expire_on_commit` session re-reads
    `event.period` from the database on next access. The compare-and-write would
    then be handed the row's CURRENT position as the position its decision was
    taken on, compare the row against itself, and match every time. The guard
    would still be there, still be called, still be green, and would arbitrate
    nothing whatsoever.

    That is not a hypothetical worth a comment; it is a silent, total regression
    of the ship that no behavioural test in this file can see. So the invariant
    is asserted where it lives — in the shape of the call.
    """
    import ast
    import inspect
    import textwrap

    from app.tasks.espn_sync import _sync_tennis_from_espn
    from app.tasks.mlb_sync import _sync_mlb_win_probability
    from app.tasks.statpal_sync import (
        _sync_statpal_livescores,
        _sync_statpal_schedules,
    )
    from app.utils.espn_helpers import update_event_fields_from_espn

    OBSERVED = ("observed_period", "observed_clock")

    def _fresh_reads(source: str) -> list[str]:
        """Names of `observed_*` arguments passed as an attribute read."""
        offenders = []
        for node in ast.walk(ast.parse(source)):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "write_live_state_if_unmoved"
            ):
                continue
            seen = set()
            for kw in node.keywords:
                if kw.arg not in OBSERVED:
                    continue
                seen.add(kw.arg)
                # A captured local is a bare Name. Anything that reaches
                # through an object — `event.period`, `row.game_clock` — is a
                # read taken at write time, which is the defect.
                if not isinstance(kw.value, ast.Name):
                    offenders.append(f"{kw.arg}={ast.unparse(kw.value)}")
            missing = [name for name in OBSERVED if name not in seen]
            offenders.extend(f"{name} not passed at all" for name in missing)
        return offenders

    # The detector is self-tested against a synthetic source carrying the
    # offence, both spellings, rather than against whatever the subjects happen
    # to contain — a scan asserted on its own yield goes quiet for the best
    # possible reason.
    assert _fresh_reads(
        "write_live_state_if_unmoved(s, e, v, observed_period=event.period,\n"
        "                            observed_clock=_observed_clock)\n"
    ) == ["observed_period=event.period"]
    assert _fresh_reads(
        "write_live_state_if_unmoved(s, e, v, observed_period=_p,\n"
        "                            observed_clock=e.game_clock)\n"
    ) == ["observed_clock=e.game_clock"]
    assert _fresh_reads(
        "write_live_state_if_unmoved(s, e, v, observed_period=_p)\n"
    ) == ["observed_clock not passed at all"]
    assert _fresh_reads(
        "write_live_state_if_unmoved(s, e, v, observed_period=_p,\n"
        "                            observed_clock=_c)\n"
    ) == []

    # ── THE SAME MUTANT, IN THE DICT-PREDICATED SPELLING (live/224) ──
    #
    # `write_row_if_unmoved` takes its predicate as `observed={column: value}`
    # rather than as two named arguments, so the kwarg walk above cannot see
    # into it: the tennis call site would have been structurally unguarded
    # against exactly the mutant this test exists for. The offence is identical
    # — a value that reaches through an object is a read taken at write time —
    # it is just one level deeper.
    def _fresh_reads_in_observed(source: str) -> list[str]:
        """Predicate values passed as an attribute read, not a captured local."""
        offenders = []
        for node in ast.walk(ast.parse(source)):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "write_row_if_unmoved"
            ):
                continue
            observed = [kw for kw in node.keywords if kw.arg == "observed"]
            if not observed:
                offenders.append("observed not passed at all")
                continue
            mapping = observed[0].value
            if not isinstance(mapping, ast.Dict):
                # A dict built elsewhere and handed in cannot be read here, so
                # it cannot be certified here either. Refuse it rather than
                # skip it silently.
                offenders.append(f"observed={ast.unparse(mapping)} is not a literal")
                continue
            if not mapping.keys:
                offenders.append("observed={} has nothing to compare")
            for key, value in zip(mapping.keys, mapping.values):
                if not isinstance(value, ast.Name):
                    offenders.append(
                        f"observed[{ast.unparse(key)}]={ast.unparse(value)}"
                    )
        return offenders

    assert _fresh_reads_in_observed(
        "write_row_if_unmoved(s, e, v, observed={'home_score': event.home_score,\n"
        "                                        'away_score': _away})\n"
    ) == ["observed['home_score']=event.home_score"]
    assert _fresh_reads_in_observed(
        "write_row_if_unmoved(s, e, v, observed=built_elsewhere)\n"
    ) == ["observed=built_elsewhere is not a literal"]
    assert _fresh_reads_in_observed(
        "write_row_if_unmoved(s, e, v, observed={})\n"
    ) == ["observed={} has nothing to compare"]
    assert _fresh_reads_in_observed("write_row_if_unmoved(s, e, v)\n") == [
        "observed not passed at all"
    ]
    assert _fresh_reads_in_observed(
        "write_row_if_unmoved(s, e, v, observed={'home_score': _home,\n"
        "                                        'away_score': _away})\n"
    ) == []

    tennis = textwrap.dedent(inspect.getsource(_sync_tennis_from_espn))
    assert "write_row_if_unmoved(" in tennis, (
        "the tennis producer no longer calls the compare-and-write — this scan "
        "would be measuring nothing"
    )
    assert _fresh_reads_in_observed(tennis) == [], (
        "the tennis compare-and-write is being handed a position it read at "
        "write time, which compares the row against itself"
    )

    producers = {
        "statpal_sync._sync_statpal_livescores": _sync_statpal_livescores,
        "statpal_sync._sync_statpal_schedules": _sync_statpal_schedules,
        "espn_helpers.update_event_fields_from_espn": update_event_fields_from_espn,
        "mlb_sync._sync_mlb_win_probability": _sync_mlb_win_probability,
    }
    for name, fn in producers.items():
        source = textwrap.dedent(inspect.getsource(fn))
        assert "write_live_state_if_unmoved(" in source, (
            f"{name} no longer calls the compare-and-write — this scan would "
            "be measuring nothing"
        )
        offenders = _fresh_reads(source)
        assert not offenders, (
            f"{name} hands the compare-and-write {offenders}. The two "
            "`observed_*` arguments are the position the decision was taken "
            "on, and must be locals captured BEFORE the decision — reading "
            "them off the row at the call site compares the row against "
            "itself and the predicate matches every time (#6056)."
        )
