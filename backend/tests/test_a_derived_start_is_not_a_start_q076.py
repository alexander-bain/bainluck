"""A start nobody reported does not start the clock (q076).

PILLAR: TRUTH.  SHIP: a US Open match that is played tomorrow afternoon stops
showing as LIVE tonight, and stops being marked FINAL, with no score, before it
is played.

## The specimen, measured on production 2026-09-01 ~19:20Z

q066b stopped the CODE manufacturing placeholder starts from The Odds API, and
that half worked: every one of Sep 1's US Open rows carried a real staggered
first-serve time by noon (19:10, 19:20, 19:30, 19:55 x4, 20:05 x2 ...), written
by ``odds_api`` revising its own record.

A SECOND producer was underneath it, and it is not the Odds API::

    commence_time             commence_time_source   n
    2026-09-02 00:00:00+00    kalshi_ticker          40   <- 20 ATP, 20 WTA
    2026-09-02 15:00:00+00    odds_api               41   <- the q066b shape

``kalshi_ticker`` is stamped by ``auto_create_commence_time`` when it falls back
to the DATE parsed out of a Kalshi ticker, because Kalshi's own
``commence_time`` is a close/resolution time (gotcha #14).  A ticker date has no
time-of-day, so it resolves to **midnight UTC** — a day, rendered as an instant.

Those 40 rows are the marquee September 2 US Open draw — Alcaraz, Sabalenka,
Swiatek, Osaka, Medvedev, Tsitsipas, Pegula, Auger-Aliassime — and **every one of
them holds live Kalshi markets** (1 to 13 each; Li v Vekic holds 13).  Their
matches are played on the AFTERNOON of September 2.  Their stand-in start is
midnight UTC on September 2, which is **5:00 pm PT on September 1**.

So, unfixed, on the evening of the 1st:

* 17:00 PT — ``transition_event_statuses`` (every 60s) sees
  ``commence_time <= now`` and promotes all 40 to ``live``;
* 23:30 PT — 6.5h later, tennis's own maximum duration having elapsed with no
  post-commence snapshot to hold them (they carry zero: Kalshi prices live in
  ``futures_markets``, not ``odds_snapshots``), the same net closes all 40 with
  ``completed_at`` NULL and no score.

## Why declining is measurably free

Of every event ever stamped ``kalshi_ticker``, on the same read::

    status      n     unscored    in the last 7 days
    closed    705          705                   468
    scheduled 181          181                   181

**705 closed, 705 unscored.**  Not "mostly" — the entire population.  This
provenance has never once produced a settled row carrying a result, so refusing
to run a clock from it cannot cost a single real one.  468 in seven days is the
rate at which the site was manufacturing finished matches that were never
played, ~67 a night.

## THE GUARD THIS FILE DOES *NOT* WRITE

Not "assert no tennis event sits at midnight UTC", and not "assert a start is
not a round hour".  q066b already measured why: clustering is not a placeholder
signature (soccer_other puts 130 events on one stamp, and ESPN's real order of
play gives 15:05Z to three US Open matches at once), and a real match genuinely
can start on the hour.  Nothing below binds on a date, an hour, or a count.

The signature is **the writer's own provenance stamp**, which already records
that it derived the value because no schedule published one.  The guards are on
that, and on the two doors that read it.
"""

from __future__ import annotations

import contextlib
import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.services.event_registry import _SOURCE_PRIORITY
from app.utils.event_completion import (
    DERIVED_COMMENCE_SOURCES,
    TICKER_DERIVED_COMMENCE_SOURCE,
    commence_time_is_a_reported_start,
)

UTC = timezone.utc

#: The production stand-in and the production truth, so the fixture is the
#: specimen rather than a re-description of it.  Faria v Alcaraz, event
#: 15299547: our row said 2026-09-02T00:00:00Z; the match is a Sep 2 afternoon
#: fixture that ESPN still lists as ``shortDetail: "TBD"``.
MIDNIGHT_STAND_IN = datetime(2026, 9, 2, 0, 0, 0, tzinfo=UTC)

#: 17:02 PT on the 1st — two minutes after the promotion would have fired.
NOW = datetime(2026, 9, 2, 0, 2, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 1. THE PREDICATE.  Provenance, and deliberately nothing else.
# ---------------------------------------------------------------------------


class TestOnlyASelfDeclaredDerivedSourceIsRefused:
    def test_the_ticker_derived_stamp_is_not_a_start(self):
        assert (
            commence_time_is_a_reported_start(TICKER_DERIVED_COMMENCE_SOURCE) is False
        )

    @pytest.mark.parametrize(
        "source", ["odds_api", "espn", "statpal", "mlb_schedule_repair"]
    )
    def test_every_real_schedule_source_is_a_start(self, source):
        assert commence_time_is_a_reported_start(source) is True

    @pytest.mark.parametrize("source", ["kalshi", "polymarket"])
    def test_a_prediction_markets_OWN_time_is_still_a_start(self, source):
        """The narrowness that makes this safe, and the easiest thing to get wrong.

        A bare ``kalshi`` stamp means the market's own ``commence_time`` was used
        and it AGREED with the ticker — ``auto_create_commence_time`` returns the
        ticker only when the fallback contradicts it.  That is a reading about
        this match, not a stand-in for the absence of one.  Widening the refusal
        to the whole provider would strand the 9 rows on the same production read
        that carry real staggered European order-of-play times (08:00, 09:10 x5,
        10:00 x3, 10:20 x4, 11:10 x3 ...).
        """
        assert commence_time_is_a_reported_start(source) is True

    def test_an_unknown_provenance_is_a_start(self):
        """A ``None`` source is NOT derived, and this is load-bearing.

        Most of ``events`` predates the column.  A mutant that reads unknown
        provenance as un-startable does not fix 40 rows — it freezes the ordinary
        ``scheduled -> live`` promotion for nearly every event on the site, which
        is the same defect pointed the other way and vastly larger.
        """
        assert commence_time_is_a_reported_start(None) is True
        assert commence_time_is_a_reported_start("") is True
        assert commence_time_is_a_reported_start("something_new") is True

    def test_the_refused_set_is_exactly_one_provenance(self):
        """Named as a set so a future derived source JOINS the rule.

        A source omitted from this set inherits the clock by default, which is
        the right default and the reason the set is asserted rather than the
        single string: adding one is a deliberate edit here, never a silent one.
        """
        assert DERIVED_COMMENCE_SOURCES == frozenset({"kalshi_ticker"})

    def test_the_derived_source_is_NOT_in_the_write_authority_ladder(self):
        """Which is what lets a real schedule rescue the row rather than strand it.

        ``_SOURCE_PRIORITY`` ranks an unrecognised current source 0, and #2018's
        rule is that "an unknown current source confers no immunity".  So the
        moment odds_api / espn / statpal publishes a real time onto one of these
        rows, the write is authorised, the source changes with it, and the clock
        starts normally.  If this provenance were ever ADDED to the ladder above
        0, holding the clock would become permanent for these rows.
        """
        assert TICKER_DERIVED_COMMENCE_SOURCE not in _SOURCE_PRIORITY
        for real in ("odds_api", "statpal", "espn", "mlb_schedule_repair"):
            assert _SOURCE_PRIORITY[real] > _SOURCE_PRIORITY.get(
                TICKER_DERIVED_COMMENCE_SOURCE, 0
            )


class TestOneStringThreeReaders:
    def test_the_matcher_and_the_clocks_read_the_same_literal(self):
        """If these drift, ``_choose_segment_event`` calls a row schedule-derived
        that the clocks call a stand-in, and the two halves of the same repair
        start disagreeing about which row is the real match.
        """
        import app.tasks.prediction_market_matching as pmm

        assert pmm._TICKER_DERIVED_COMMENCE_SOURCE is TICKER_DERIVED_COMMENCE_SOURCE

    def test_the_writer_stamps_the_value_the_readers_refuse(self):
        """The end of the loop: what ``auto_create_commence_time`` WRITES is what
        ``commence_time_is_a_reported_start`` refuses.  Asserted through the
        writer's real return value, not by comparing two constants.
        """
        from app.tasks.prediction_market_matching import auto_create_commence_time

        market = type(
            "M",
            (),
            {
                # A real production ticker: date 26AUG21, close time two days later.
                "source": "kalshi",
                "external_id": "KXLOLGAME-26AUG210500GAMTSW",
                "commence_time": datetime(2026, 8, 23, 9, 0, tzinfo=UTC),
            },
        )()
        _, source = auto_create_commence_time(market, market.commence_time)
        assert source == TICKER_DERIVED_COMMENCE_SOURCE
        assert commence_time_is_a_reported_start(source) is False


# ---------------------------------------------------------------------------
# 2. DOOR ONE — the 60s promotion, exercised through the net that runs it.
#
# Not a source scan and not a predicate call: the loop is what shipped the
# defect, so the loop is what is driven.  Same fake-session shape as
# `test_event_completion.py`'s harness, extended to feed the SCHEDULED select
# (slot 0), which that file always leaves empty.
# ---------------------------------------------------------------------------


class _Row:
    """Mutable stand-in for an Event row — the net assigns to it directly."""

    def __init__(self, id, sport_key, commence_time, commence_time_source):
        self.id = id
        self.status = "scheduled"
        self.commence_time = commence_time
        self.commence_time_source = commence_time_source
        self.completed_at = None
        self.home_score = None
        self.away_score = None
        self.win_probability_sources = {}
        self.home_team_name = "Home"
        self.away_team_name = "Away"
        self.sport = type("S", (), {"key": sport_key})()


class _NetSession:
    def __init__(self, scheduled):
        # scheduled, live, bogus-completed, future-settled — the net's four
        # selects, in the order it issues them.
        self._selects = [scheduled, [], [], []]

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "MAX(x.captured_at)" in sql:
            return type("R", (), {"all": lambda _s: []})()
        if sql.startswith("UPDATE"):
            return None
        rows = self._selects.pop(0)
        return type(
            "R", (), {"scalars": lambda _s: type("S", (), {"all": lambda _x: rows})()}
        )()

    async def commit(self):
        pass


async def _run_net(scheduled, now=NOW):
    session = _NetSession(scheduled)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.espn_sync as mod

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch("app.tasks.base.get_task_session", _fake_session), patch.object(
        mod, "datetime", _FrozenNow
    ):
        return await mod._transition_event_statuses_impl()


def _alcaraz():
    """Event 15299547, Faria v Alcaraz, as production held it."""
    return _Row(15299547, "tennis_atp", MIDNIGHT_STAND_IN, "kalshi_ticker")


def _real_start():
    """A row whose start a schedule actually published, two minutes ago."""
    return _Row(15299000, "tennis_atp_us_open", NOW - timedelta(minutes=2), "odds_api")


class TestTheClockDoesNotStartFromAStandIn:
    @pytest.mark.asyncio
    async def test_a_derived_start_does_not_promote_the_row_to_live(self):
        row = _alcaraz()
        stats = await _run_net([row])
        assert row.status == "scheduled"
        assert stats["scheduled_to_live"] == 0
        assert stats["held_derived_start"] == 1

    @pytest.mark.asyncio
    async def test_a_real_start_STILL_promotes(self):
        """The regression arm.  Without it, deleting the promotion entirely — the
        crudest possible "fix" — passes the test above.
        """
        row = _real_start()
        stats = await _run_net([row])
        assert row.status == "live"
        assert stats["scheduled_to_live"] == 1
        assert stats["held_derived_start"] == 0

    @pytest.mark.asyncio
    async def test_the_two_are_decided_independently_in_one_pass(self):
        """Both arms in ONE run, which is the arm neither of the above can be.

        A held row must not suppress a healthy sibling (gotcha #42), and a
        promoted sibling must not drag the held one through with it.  This is
        also the case that fails for a mutant which inverts the predicate: the
        counts swap and the statuses swap with them.
        """
        held, promoted = _alcaraz(), _real_start()
        stats = await _run_net([held, promoted])
        assert (held.status, promoted.status) == ("scheduled", "live")
        assert (stats["held_derived_start"], stats["scheduled_to_live"]) == (1, 1)

    @pytest.mark.asyncio
    async def test_holding_nothing_reports_zero_rather_than_absent(self):
        """`stats` always carries the key, so a dashboard reading it cannot
        confuse "the guard held nothing" with "the guard is not deployed".
        """
        stats = await _run_net([])
        assert stats["held_derived_start"] == 0

    def test_the_hold_is_in_the_LOG_TRIGGER_and_not_only_in_the_stats(self):
        """A bound that drops work silently reads as "there was none".

        On a quiet night the other four counters are all zero and the hold is 40
        — exactly the night somebody needs to see the line.  Asserted on the
        trigger condition, not merely on the message, because a count printed
        inside an `if` that never fires is not logged.
        """
        from app.tasks.espn_sync import _transition_event_statuses_impl

        src = inspect.getsource(_transition_event_statuses_impl)
        trigger = src[src.index('if (stats["scheduled_to_live"] > 0') :]
        trigger = trigger[: trigger.index("logger.info")]
        assert 'stats["held_derived_start"] > 0' in trigger


# ---------------------------------------------------------------------------
# 3. DOOR TWO — the row that is BORN live.
# ---------------------------------------------------------------------------


class TestAStandInDoesNotBirthALiveRow:
    def test_a_ticker_derived_time_already_past_is_born_scheduled(self):
        from app.tasks.prediction_market_matching import auto_create_status

        assert (
            auto_create_status(MIDNIGHT_STAND_IN, TICKER_DERIVED_COMMENCE_SOURCE, NOW)
            == "scheduled"
        )

    def test_a_real_start_already_past_is_STILL_born_live(self):
        """Regression arm.  ``status = "scheduled"`` unconditionally would pass
        the test above and break every Polymarket auto-create of a game already
        under way.
        """
        from app.tasks.prediction_market_matching import auto_create_status

        assert auto_create_status(NOW - timedelta(minutes=1), None, NOW) == "live"
        assert auto_create_status(NOW - timedelta(minutes=1), "odds_api", NOW) == "live"

    def test_a_future_start_is_scheduled_whatever_its_provenance(self):
        from app.tasks.prediction_market_matching import auto_create_status

        later = NOW + timedelta(hours=3)
        assert auto_create_status(later, None, NOW) == "scheduled"
        assert (
            auto_create_status(later, TICKER_DERIVED_COMMENCE_SOURCE, NOW)
            == "scheduled"
        )

    def test_the_creator_decides_through_the_helper_and_not_beside_it(self):
        """Containment, asserted in BOTH directions.

        Naming the helper is not enough — the old ternary sitting next to a call
        that is never reached would satisfy a presence check.  So the literal it
        replaced must also be GONE from the creator.
        """
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        src = inspect.getsource(_create_event_from_prediction_market)
        assert "auto_create_status(" in src
        assert 'status = "live" if commence_time <= now' not in src
