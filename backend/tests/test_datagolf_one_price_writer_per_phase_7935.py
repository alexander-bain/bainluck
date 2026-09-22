"""#7935 — one DataGolf price writer per phase, so a settled golf chart stops
saw-toothing between 84% and 0%.

WHAT WAS WRONG. Two tasks write `bookmaker="datagolf_model"` for the same
outcome. `_poll_datagolf_markets` (hourly) raises the in-play window flag when
today falls inside the current event's `[start, end]` window — which is what
WAKES the 90s `_poll_datagolf_inplay` beat — and then fetches
`get_pre_tournament()` and writes those numbers as snapshots ANYWAY, for a
tournament already being played. `get_pre_tournament` returns probabilities
computed BEFORE the event started, so once a cut has fallen the hourly poll
stamps a player's stale pre-cut 0.83825 onto a leg the beat has graded 0.0, and
~60 minutes later does it again.

Write-time dedup cannot save it: both sites compare the incoming value against
the single LATEST snapshot for that outcome+bookmaker, whoever wrote it. The two
families always differ by ~0.84, so the comparison always says "changed", both
always insert, and each closes the other's `valid_until`. Measured lags between
the paired writes on the production specimen: 56s, 22s, 48s, 17s, 50s, 16s —
all inside one 90s beat interval. Pair period 62–96 min, matching the 1h gate.

Three post-cut tournaments, three hits (snapshots / distinct values over 48h):
BMW PGA Make-the-Cut 4,176 / 146, Biltmore 3,930 / 132, Nationwide Children's
3,277 / 115 — where 146 ≈ 144 pre-cut player prices + 0.0 + 1.0, i.e. EVERY leg
alternating. Sibling market types on the same tournaments are healthy (Top 20:
9,386 / 4,331). THE SHIP: a settled golf leg's chart is the journey it actually
took, not a forty-tooth comb.

── WHAT THESE TESTS RUN, AND WHY NOT A SOURCE SCAN ─────────────────────────

`test_datagolf_live_event_guard.py` reads `_poll_datagolf_markets`' source and
asserts substrings, which is the repo idiom for these large async polls and is
the wrong instrument here: every mutation this fix has to survive leaves the
words in place and changes which rows get written. Gating on the fleet-wide
`INPLAY_WINDOW_KEY` instead of this tour's own window still contains
"inplay"; restoring the unconditional snapshot still contains "datagolf_model".

So these drive the REAL `_poll_datagolf_markets` over a fake session that keeps
every write, with the real `DataGolfPlayer`/`DataGolfTournament` models as
input — a hand-built payload shape would just route the task down its own
"no data" branch and pass (which is not a result).

── BOTH DIRECTIONS, EVERY TIME ─────────────────────────────────────────────

A poll that refuses to write prices is not a fix, it is an outage with good
intentions: DataGolf covers some tours' events in-play and not others, and a
tour inside its date window with NO live board would be frozen for four days
with `last_updated` going stale. So the deferral is keyed on TWO per-tour
signals — this event's own window AND `LIVE_KEY_PREFIX:{tour}`, which
`_poll_datagolf_live` sets only when the in-play endpoint actually returned a
board — and every test below runs its control: the same poll, one signal
removed, must still write.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.sql.dml import Update

import app.services.datagolf_api as datagolf_api
import app.tasks.base as task_base
import app.tasks.datagolf as datagolf
import app.tasks.redis_state as redis_state
from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
from app.services.datagolf_api import DataGolfPlayer, DataGolfTournament

PGA_EVENT_ID = "2026136"
EURO_EVENT_ID = "2026150"

#: The graded value the 90s beat wrote for a player who has missed the cut.
GRADED = 0.0

#: What `get_pre_tournament` still returns for that player mid-event — the
#: number that drew the other half of the saw-tooth.
PRE_TOURNAMENT = 0.83825

#: A euro leg that has NOT teed off: the control population.
EURO_PRE_TOURNAMENT = 0.72

PGA_PLAYER_ID = 18417
PGA_NEWCOMER_ID = 99999
PGA_VANISHED_ID = 77777
EURO_PLAYER_ID = 12345


# --------------------------------------------------------------- fixtures --


def _dates(start_offset_days: int, length_days: int = 3) -> tuple[str, str]:
    """Offset FIRST, then truncate (gotcha #44) — no branch on the clock."""
    now = datetime.now(timezone.utc)
    start = now + timedelta(days=start_offset_days)
    end = start + timedelta(days=length_days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _tournament(tour: str, event_id: str, name: str, start_offset: int) -> DataGolfTournament:
    start, end = _dates(start_offset)
    return DataGolfTournament(
        event_id=event_id,
        event_name=name,
        course="Wentworth",
        start_date=start,
        end_date=end,
        # Deliberately absent. DataGolf's schedule STATUS string is unreliable
        # (the reason #1076 and #144 both exist) and the DATES are the signal
        # the poll trusts; pinning the tests to a status string would prove the
        # belt and not the braces.
        status=None,
        tour=tour,
    )


def _player(dg_id: int, name: str, make_cut: float) -> DataGolfPlayer:
    """Only `make_cut` is priced.

    `_get_prob` returns None for every other market type, so the four sibling
    markets take the `prob is None: continue` path and this file's assertions
    are about one market without having to be scoped to one.
    """
    return DataGolfPlayer(dg_id=dg_id, player_name=name, make_cut=make_cut)


class _FakeResult:
    def __init__(self, rows=(), rowcount: int = 0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """Answers the poll's SELECTs from a seeded world and keeps every write."""

    def __init__(self, markets, outcomes, snapshots):
        #: ext_id -> FuturesMarket
        self.markets = markets
        #: (market_id, ext_id) -> FuturesOutcome
        self.outcomes = outcomes
        #: outcome_id -> FuturesOddsSnapshot (the "latest" the poll dedups on)
        self.snapshots = snapshots
        self.added: list[object] = []
        self.reranked: list[Update] = []
        self._next_id = 5000

    # -- writes --------------------------------------------------------

    def add(self, obj) -> None:
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = self._next_id
            self._next_id += 1

    async def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:  # pragma: no cover - defensive
                obj.id = self._next_id
                self._next_id += 1

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:  # pragma: no cover - defensive
        return None

    # -- reads ---------------------------------------------------------

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            if stmt.table.name == "futures_outcomes":
                self.reranked.append(stmt)
            # The #1076 restore and the completed-event resolve. Nothing in
            # this file turns on them; rowcount 0 keeps them silent.
            return _FakeResult(rowcount=0)

        entity = stmt.column_descriptions[0]["entity"]
        params = stmt.compile().params
        # An expanding `IN` binds its whole collection under ONE key, so the
        # stale scan's fresh-player set arrives as a list. Flattening is not
        # cosmetic: reading only the scalar params made `fresh` empty, and the
        # null-out then treated every seeded leg as withdrawn.
        values: list[str] = []
        for value in params.values():
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, (list, tuple, set, frozenset)):
                values.extend(v for v in value if isinstance(v, str))

        if entity is FuturesMarket:
            ext = next((v for v in values if v.count(":") == 3), None)
            market = self.markets.get(ext)
            return _FakeResult([market] if market else [])

        if entity is FuturesOddsSnapshot:
            # The batch "latest snapshot per outcome" load. Scoped by market in
            # the real query; the seeded world has one market with snapshots.
            return _FakeResult(list(self.snapshots.values()))

        if entity is FuturesOutcome:
            if "current_probability IS NOT NULL" in str(stmt):
                # The stale/withdrawn scan: every seeded leg on this market
                # that the fresh player set does not name.
                market_id = next(
                    (v for v in params.values() if isinstance(v, int)), None
                )
                fresh = {v for v in values if v.startswith("dg_")}
                return _FakeResult([
                    o for (mid, ext), o in self.outcomes.items()
                    if mid == market_id
                    and o.current_probability is not None
                    and ext not in fresh
                ])
            ext = next((v for v in values if v.startswith("dg_")), None)
            market_id = next((v for v in params.values() if isinstance(v, int)), None)
            outcome = self.outcomes.get((market_id, ext))
            return _FakeResult([outcome] if outcome else [])

        raise AssertionError(f"unexpected select: {entity}")  # pragma: no cover


class _FakeRedis:
    def __init__(self, present: dict[str, str]):
        self.present = dict(present)
        self.sets: list[str] = []

    def get(self, key):
        return self.present.get(key)

    def set(self, key, value, ex=None):
        self.sets.append(key)
        self.present[key] = value


class _FakeService:
    def __init__(self, schedules, players):
        self._schedules = schedules
        self._players = players
        self.closed = False

    async def get_schedule(self, tour: str):
        return list(self._schedules.get(tour, []))

    async def get_pre_tournament(self, tour: str):
        return list(self._players.get(tour, []))

    async def close(self):
        self.closed = True


def _world(*, with_vanished: bool = False):
    """Five markets per tour, one priced leg each, plus the seeded snapshots."""
    markets: dict[str, FuturesMarket] = {}
    outcomes: dict[tuple[int, str], FuturesOutcome] = {}
    snapshots: dict[int, FuturesOddsSnapshot] = {}

    market_id = 10
    for tour, event_id in (("pga", PGA_EVENT_ID), ("euro", EURO_EVENT_ID)):
        for market_type, _category in datagolf.MARKET_TYPES:
            ext = datagolf._external_id(tour, event_id, market_type)
            market = FuturesMarket(
                source="datagolf",
                external_id=ext,
                name=f"{tour} - {market_type}",
                status="open",
            )
            market.id = market_id
            market.market_metadata = {}
            markets[ext] = market
            market_id += 1

    pga_cut = markets[datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")].id
    euro_cut = markets[datagolf._external_id("euro", EURO_EVENT_ID, "make_cut")].id

    def _leg(mid: int, dg_id: int, name: str, probability: float, oid: int):
        outcome = FuturesOutcome(
            market_id=mid,
            external_id=f"dg_{dg_id}",
            name=name,
            current_probability=probability,
        )
        outcome.id = oid
        outcome.last_updated = datetime(2026, 1, 1, tzinfo=timezone.utc)
        outcome.price_changed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        outcomes[(mid, f"dg_{dg_id}")] = outcome
        snapshots[oid] = FuturesOddsSnapshot(
            outcome_id=oid,
            bookmaker="datagolf_model",
            probability=probability,
        )
        return outcome

    # The specimen: a leg the 90s beat has already graded to 0.0.
    _leg(pga_cut, PGA_PLAYER_ID, "Tommy Fleetwood", GRADED, 101)
    # The control population on a tour that has not teed off.
    _leg(euro_cut, EURO_PLAYER_ID, "Rasmus Hojgaard", 0.55, 201)
    if with_vanished:
        # Graded 0.0 by the beat AND dropped from the pre-tournament field.
        _leg(pga_cut, PGA_VANISHED_ID, "Missed The Cut", GRADED, 102)

    return markets, outcomes, snapshots


def _run(monkeypatch, *, tours, live_flags, with_vanished=False, newcomer=False):
    markets, outcomes, snapshots = _world(with_vanished=with_vanished)
    session = _FakeSession(markets, outcomes, snapshots)

    pga_players = [_player(PGA_PLAYER_ID, "Tommy Fleetwood", PRE_TOURNAMENT)]
    if newcomer:
        pga_players.append(_player(PGA_NEWCOMER_ID, "Late Alternate", 0.41))

    schedules: dict[str, list] = {}
    players: dict[str, list] = {}
    if "pga" in tours:
        # start_offset -1: today sits inside [start, end] — in play.
        schedules["pga"] = [
            _tournament("pga", PGA_EVENT_ID, "BMW PGA Championship", -1)
        ]
        players["pga"] = pga_players
    if "euro" in tours:
        # start_offset +7: tees off next week — not in play.
        schedules["euro"] = [
            _tournament("euro", EURO_EVENT_ID, "Open de France", 7)
        ]
        players["euro"] = [
            _player(EURO_PLAYER_ID, "Rasmus Hojgaard", EURO_PRE_TOURNAMENT)
        ]

    service = _FakeService(schedules, players)
    redis = _FakeRedis({
        f"{datagolf.LIVE_KEY_PREFIX}:{tour}": "1" for tour in live_flags
    })

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(datagolf, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(datagolf_api, "DataGolfAPIService", lambda *a, **kw: service)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: redis)

    stats = asyncio.run(datagolf._poll_datagolf_markets())
    return stats, session, redis, markets, outcomes


def _snapshots_written(session) -> list[FuturesOddsSnapshot]:
    return [o for o in session.added if isinstance(o, FuturesOddsSnapshot)]


def _leg(outcomes, markets, tour, event_id, dg_id) -> FuturesOutcome:
    mid = markets[datagolf._external_id(tour, event_id, "make_cut")].id
    return outcomes[(mid, f"dg_{dg_id}")]


# ------------------------------------------------------------------ tests --


class TestTheBeatOwnsThePriceWhilePlayIsHappening:
    def test_the_graded_price_survives_the_hourly_poll(self, monkeypatch):
        """The defect itself: the hourly poll must not overwrite 0.0 with 0.83825."""
        stats, session, _redis, markets, outcomes = _run(
            monkeypatch, tours=["pga"], live_flags=["pga"]
        )

        leg = _leg(outcomes, markets, "pga", PGA_EVENT_ID, PGA_PLAYER_ID)
        assert leg.current_probability == GRADED, (
            "the hourly poll overwrote the beat's graded price with a "
            f"pre-tournament number ({leg.current_probability}) — this is the "
            "saw-tooth"
        )
        assert leg.price_changed_at == datetime(2026, 1, 1, tzinfo=timezone.utc), (
            "a price that was not written must not be stamped as having moved"
        )
        assert leg.last_updated == datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _snapshots_written(session) == [], (
            "a pre-tournament snapshot was written during play — the other "
            "half of the saw-tooth"
        )
        assert stats["snapshots_written"] == 0
        assert stats["inplay_price_writes_deferred"] == 1

    def test_the_SAME_poll_writes_when_no_beat_is_running(self, monkeypatch):
        """The control that makes the test above mean something.

        Same tour, same in-play window, no `LIVE_KEY_PREFIX:pga` — so nothing
        else is writing this board and the hourly poll must still be the
        writer. A fix that keyed on the window alone would freeze every tour
        DataGolf does not cover in-play, for the length of its event.
        """
        stats, session, _redis, markets, outcomes = _run(
            monkeypatch, tours=["pga"], live_flags=[]
        )

        leg = _leg(outcomes, markets, "pga", PGA_EVENT_ID, PGA_PLAYER_ID)
        assert leg.current_probability == PRE_TOURNAMENT, (
            "no in-play writer is active and the poll declined to write — the "
            "board is frozen"
        )
        written = _snapshots_written(session)
        assert [float(s.probability) for s in written] == [PRE_TOURNAMENT]
        assert stats["snapshots_written"] == 1
        assert stats["inplay_price_writes_deferred"] == 0

    def test_the_window_flag_that_wakes_the_beat_is_still_raised(self, monkeypatch):
        """#144's half of this block must survive #7935's half.

        The deferral reads the same boolean that raises the flag; a rearrangement
        that stops setting it would silence the 90s beat entirely and leave the
        board with NO writer — the failure this fix exists to avoid.
        """
        _stats, _session, redis, _markets, _outcomes = _run(
            monkeypatch, tours=["pga"], live_flags=["pga"]
        )
        assert datagolf.INPLAY_WINDOW_KEY in redis.sets


class TestTheDeferralIsPerTourAndNotFleetWide:
    def test_a_tour_that_has_not_teed_off_still_gets_its_prices(self, monkeypatch):
        """The trap in this fix, pinned.

        `INPLAY_WINDOW_KEY` is ONE key for all of POLL_TOURS, and pga is polled
        before euro — so a deferral keyed on it would have the live pga event
        starve the pre-tournament writes of a euro event that tees off next
        week. The signals must both be per-tour.
        """
        stats, session, redis, markets, outcomes = _run(
            monkeypatch, tours=["pga", "euro"], live_flags=["pga"]
        )

        pga_leg = _leg(outcomes, markets, "pga", PGA_EVENT_ID, PGA_PLAYER_ID)
        euro_leg = _leg(outcomes, markets, "euro", EURO_EVENT_ID, EURO_PLAYER_ID)

        assert pga_leg.current_probability == GRADED
        assert euro_leg.current_probability == EURO_PRE_TOURNAMENT, (
            "the euro event has not started and nothing else writes it, but "
            "the live pga event suppressed its prices — the deferral is "
            "reading a fleet-wide signal"
        )

        # The pga window flag IS set by the time euro is polled, which is
        # exactly what makes the fleet-wide mutant look correct until now.
        assert redis.get(datagolf.INPLAY_WINDOW_KEY) == "1"

        written = _snapshots_written(session)
        assert [float(s.probability) for s in written] == [EURO_PRE_TOURNAMENT]
        assert stats["snapshots_written"] == 1


class TestTheFieldStillMovesWhilePricesAreDeferred:
    def test_a_player_added_mid_event_is_still_born(self, monkeypatch):
        """Deferring the PRICE is not deferring the poll.

        A late alternate appears in the field mid-event and must get a row, or
        the beat has nothing to write to and the player is invisible until the
        next tournament. The row is born with the pre-tournament number as its
        opening; the beat corrects it inside 90s.
        """
        _stats, session, _redis, markets, _outcomes = _run(
            monkeypatch, tours=["pga"], live_flags=["pga"], newcomer=True
        )

        pga_cut = markets[datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")].id
        born = [
            o for o in session.added
            if isinstance(o, FuturesOutcome)
            and o.external_id == f"dg_{PGA_NEWCOMER_ID}"
            and o.market_id == pga_cut
        ]
        assert len(born) == 1, (
            "a player who joined the field during play was not created — the "
            "deferral swallowed the upsert, not just the price"
        )
        assert _snapshots_written(session) == []

    def test_a_vanished_player_keeps_the_grade_the_beat_gave_him(self, monkeypatch):
        """The null-out is a price write too, and the worst one to make here.

        A player the pre-tournament endpoint has stopped returning still holds
        the 0.0 the beat graded him. Nulling it does not just stale the number,
        it removes the row from the served board (the /golf route skips None
        outcomes) — a leg disappearing off a live leaderboard.
        """
        _stats, _session, _redis, markets, outcomes = _run(
            monkeypatch, tours=["pga"], live_flags=["pga"], with_vanished=True
        )

        gone = _leg(outcomes, markets, "pga", PGA_EVENT_ID, PGA_VANISHED_ID)
        assert gone.current_probability == GRADED, (
            "the pre-tournament field nulled a leg the in-play board had "
            "graded — the row leaves the served board mid-tournament"
        )

    def test_the_null_out_still_runs_when_the_beat_is_not_writing(self, monkeypatch):
        """Control for the test above: withdrawals must still be cleared."""
        _stats, _session, _redis, markets, outcomes = _run(
            monkeypatch, tours=["pga"], live_flags=[], with_vanished=True
        )

        gone = _leg(outcomes, markets, "pga", PGA_EVENT_ID, PGA_VANISHED_ID)
        assert gone.current_probability is None, (
            "nothing is in play and a withdrawn player kept his price — the "
            "deferral is over-reaching"
        )


class TestTheRankDerivationIsUnaffected:
    def test_the_field_is_still_reranked_during_play(self, monkeypatch):
        """#6598's statement is a pure derivation of `current_probability`.

        Two writers of one deterministic function of the same input cannot
        disagree, so this one keeps running on the beat's numbers — and a
        market whose ranks froze for the length of a tournament would be the
        defect #6598 shipped to fix.
        """
        _stats, session, _redis, _markets, _outcomes = _run(
            monkeypatch, tours=["pga"], live_flags=["pga"]
        )
        assert session.reranked, "no market was re-ranked while prices deferred"


def test_the_fake_session_is_not_silently_answering_nothing(monkeypatch):
    """Rig control (the fixture-is-the-specimen trap).

    Every assertion above reads a seeded object. If the fake answered the
    per-player SELECT with None the poll would CREATE a second leg instead of
    updating the seeded one, and "the graded price survived" would be true of a
    row nobody looked at. So: the seeded leg is the row the poll found.
    """
    _stats, session, _redis, markets, _outcomes = _run(
        monkeypatch, tours=["pga"], live_flags=[]
    )
    pga_cut = markets[datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")].id
    duplicates = [
        o for o in session.added
        if isinstance(o, FuturesOutcome)
        and o.external_id == f"dg_{PGA_PLAYER_ID}"
        and o.market_id == pga_cut
    ]
    assert duplicates == [], (
        "the poll created a leg the fixture had already seeded — the fake is "
        "not serving the upsert lookup and every assertion here is vacuous"
    )
