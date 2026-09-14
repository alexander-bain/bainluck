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


class _NullSession:
    """`update_event_fields_from_espn` only ever `add`s a ScoreSnapshot on this
    path; nothing in these tests reads it back."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


async def _drive_espn(row, ee):
    from app.utils.espn_helpers import update_event_fields_from_espn

    session = _NullSession()
    stats: dict = {}
    await update_event_fields_from_espn(session, row, ee, set(), stats)
    return session, stats


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
    session, stats = await _drive_espn(row, ee)

    assert row.home_score == 28
    assert row.away_score == 20, "the touchdown must not leave the page"
    assert row.game_clock == "5:21", "the clock must not go up"
    assert row.period == "5:21 - 4th Quarter"
    assert session.added == [], "a refused write must leave no ScoreSnapshot either"
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
    session, stats = await _drive_espn(row, ee)

    assert row.home_score == 28, "the extra point must not un-score itself"
    assert row.away_score == 14
    assert row.game_clock == "7:26"
    assert session.added == []
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
    session, stats = await _drive_espn(row, ee)

    assert (row.home_score, row.away_score) == (28, 20)
    assert row.game_clock == "5:21"
    assert row.period == "5:21 - 4th Quarter"
    assert len(session.added) == 1, "an accepted score change still snapshots"
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
    await _drive_espn(row, ee)

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
    await _drive_espn(row, ee)

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


async def _run_livescores(monkeypatch, *, fixtures, events):
    """Drive the real `_sync_statpal_livescores` and return the rows."""
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

    result = await _sync_statpal_livescores()
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
