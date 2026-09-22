"""#7958 — in-play ownership is published by a committed write and names the
event written, so a live golf leaderboard never runs with no price writer at all.

WHAT WAS WRONG. #7935 stood the hourly `_poll_datagolf_markets` down from price
writes while the 90s in-play beat owns a tour's board, and took
`LIVE_KEY_PREFIX:{tour}` as its proof that the beat is writing. That key cannot
carry that claim. `_poll_datagolf_live` raises it the instant the per-tour
in-play endpoint returns a non-empty board — BEFORE `_in_play_event_matches`
decides whether the board belongs to any of our open markets, BEFORE the
future-date guard, and BEFORE the session commits.

So when DataGolf serves event A's board over our event-B markets — #191's own
case, a stale winner's board outliving its tournament — the live poll skips
every market on identity, writes nothing, raises the flag anyway, and the hourly
poll then stands down too. **Zero writers.** The beat re-raises the flag every
90s against its 30-minute TTL, so it never expires while the stale board
persists: prices and `last_updated` frozen for the length of event B.

That is precisely the failure #7935's two-signal design exists to prevent — its
own comment calls a tour with no writer "a worse defect than the one being
fixed" — reached through the guard meant to prevent it.

THE FIX. `INPLAY_OWNER_KEY_PREFIX:{tour}` carries the datagolf event_ids the
live poll actually wrote prices for, published only after its transaction
commits and cleared for any tour that wrote nothing. The hourly poll defers only
when that key names the event it is about to write.

`LIVE_KEY_PREFIX` keeps its old meaning and its old values, deliberately: its
other two consumers — `_golf_inplay_window_active`, which wakes the beat and
must stay generous or play is starved, and `_snapshot_leaderboard`, which is
tour-level and does not care which event — need the loose signal. Moving one
flag under three consumers is how a narrow fix becomes a broad outage, so the
last test below pins that those two still see what they saw.

── WHY THE TESTS LOOK LIKE THIS ────────────────────────────────────────────

Both real polls are driven over fake sessions that keep every write, with the
real `DataGolfPlayer`/`DataGolfTournament` payload models as input — a
hand-built payload of the wrong shape routes the task down its own "no data"
branch and passes, which is not a result. The consumer half reuses #7935's rig
so the two files cannot drift on what "the poll deferred" means.

🪤 THE TRAP THIS FILE EXISTS TO CATCH TWICE. `get_redis_client()` sets no
`decode_responses`, so a real client answers `get()` with BYTES while a
dict-backed fake answers with `str`. The old signal was only ever read for
truthiness, which is bytes-safe; an event-id comparison is not. Written as
`r.get(key) == event_id` it is False in production and True under a str-seeded
fake: the deferral never fires, #7935's saw-tooth returns, and the suite stays
green the whole time. Every seeding below is bytes, and
`TestTheOwnerKeyIsReadTheWayRedisAnswersIt` reads the decode directly.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.sql.dml import Update

import app.services.datagolf_api as datagolf_api
import app.tasks.base as task_base
import app.tasks.datagolf as datagolf
import app.tasks.redis_state as redis_state
from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome

# #7935's rig is the authority on what "the hourly poll deferred" looks like.
# Importing it rather than re-deriving it means a later change to the deferral
# cannot leave these two files disagreeing about the same behaviour.
from tests.test_datagolf_one_price_writer_per_phase_7935 import (  # noqa: E402
    GRADED,
    PGA_EVENT_ID,
    PGA_PLAYER_ID,
    PRE_TOURNAMENT,
    _leg,
    _run,
    _snapshots_written,
)

DataGolfPlayer = datagolf_api.DataGolfPlayer
DataGolfTournament = datagolf_api.DataGolfTournament

#: The event our open pga markets belong to, and the one the hourly poll is
#: about to write. `PGA_EVENT_ID` from #7935's fixtures.
LIVE_EVENT_NAME = "BMW PGA Championship"

#: The event DataGolf's in-play endpoint is still serving a board for: last
#: week's, finished, and nothing to do with our open markets. #191's case.
STALE_EVENT_ID = "2026129"
STALE_EVENT_NAME = "Procore Championship"


# ------------------------------------------------- the consumer: hourly poll --


class TestAStaleBoardDoesNotOwnATourItNeverWrote:
    """The defect: the hourly poll must keep writing when the beat is not."""

    def test_the_poll_writes_when_the_owner_key_names_a_different_event(
        self, monkeypatch
    ):
        stats, session, _redis, markets, outcomes = _run(
            monkeypatch,
            tours=["pga"],
            live_flags=[],
            owner_events={"pga": STALE_EVENT_ID.encode()},
            extra_live_keys=["pga"],
        )

        leg = _leg(outcomes, markets, "pga", PGA_EVENT_ID, PGA_PLAYER_ID)
        assert leg.current_probability == PRE_TOURNAMENT, (
            "the in-play board belongs to a different event, so nothing else is "
            "writing this tournament — and the hourly poll stood down anyway. "
            "That is a live leaderboard with no price writer at all, frozen for "
            "the length of the event"
        )
        assert [float(s.probability) for s in _snapshots_written(session)] == [
            PRE_TOURNAMENT
        ]
        assert stats["inplay_price_writes_deferred"] == 0

    def test_the_old_signal_alone_no_longer_defers(self, monkeypatch):
        """The revert mutant, pinned by name.

        `LIVE_KEY_PREFIX:pga` is set and no ownership is published — exactly the
        state a stale board produces. A change that reads the old key again
        passes every #7935 test and fails here.
        """
        stats, session, _redis, markets, outcomes = _run(
            monkeypatch, tours=["pga"], live_flags=[], extra_live_keys=["pga"]
        )

        leg = _leg(outcomes, markets, "pga", PGA_EVENT_ID, PGA_PLAYER_ID)
        assert leg.current_probability == PRE_TOURNAMENT
        assert stats["inplay_price_writes_deferred"] == 0

    def test_the_control_the_ship_itself_still_defers(self, monkeypatch):
        """#7935's claim, restated here so this file carries both directions.

        Ownership names THIS event ⇒ the beat is writing it ⇒ the hourly poll
        must not stamp its pre-tournament number over the graded one.
        """
        stats, _session, _redis, markets, outcomes = _run(
            monkeypatch, tours=["pga"], live_flags=["pga"]
        )

        leg = _leg(outcomes, markets, "pga", PGA_EVENT_ID, PGA_PLAYER_ID)
        assert leg.current_probability == GRADED
        assert stats["inplay_price_writes_deferred"] == 1

    def test_one_tour_owning_two_events_defers_for_both(self, monkeypatch):
        """The key holds a SET, so a comma-joined value is membership.

        A tour can carry open markets for two events whose names both match the
        board (duplicate rows, a renamed event). A scalar `==` would pick one
        and un-defer the other, re-opening the saw-tooth on it.
        """
        stats, _session, _redis, markets, outcomes = _run(
            monkeypatch,
            tours=["pga"],
            live_flags=[],
            owner_events={"pga": f"{STALE_EVENT_ID},{PGA_EVENT_ID}".encode()},
        )

        leg = _leg(outcomes, markets, "pga", PGA_EVENT_ID, PGA_PLAYER_ID)
        assert leg.current_probability == GRADED
        assert stats["inplay_price_writes_deferred"] == 1


class TestTheOwnerKeyIsReadTheWayRedisAnswersIt:
    """The bytes trap, read directly rather than only through a seeded fake."""

    class _Redis:
        def __init__(self, value):
            self._value = value

        def get(self, _key):
            return self._value

    def test_bytes_are_decoded(self):
        owned = datagolf._inplay_owned_events(self._Redis(b"2026136"), "pga")
        assert owned == {"2026136"}, (
            "a real client answers with bytes and this read did not decode "
            "them — every ownership comparison is False in production and the "
            "deferral silently never fires"
        )

    def test_str_is_accepted_too(self):
        """Fakes, and any future client built with `decode_responses`."""
        assert datagolf._inplay_owned_events(self._Redis("2026136"), "pga") == {
            "2026136"
        }

    def test_a_comma_joined_value_is_a_set(self):
        assert datagolf._inplay_owned_events(
            self._Redis(b"2026129,2026136"), "pga"
        ) == {"2026129", "2026136"}

    def test_absence_is_empty_not_a_raise(self):
        assert datagolf._inplay_owned_events(self._Redis(None), "pga") == set()

    def test_a_redis_error_fails_open(self):
        """Fail-open is the deliberate posture: an unreadable flag means the
        hourly poll keeps writing. Silence is the worse failure."""

        class _Broken:
            def get(self, _key):
                raise RuntimeError("redis down")

        assert datagolf._inplay_owned_events(_Broken(), "pga") == set()


class TestTheEventIdIsParsedFromTheMarketId:
    def test_a_well_formed_id_yields_its_event(self):
        assert (
            datagolf._event_id_of("datagolf:pga:2026136:make_cut") == "2026136"
        )

    def test_a_malformed_id_is_never_published(self):
        """A shape this does not recognise must not become an owned event —
        publishing garbage would defer a poll against an event that cannot
        exist, which is the freeze again."""
        for bad in (
            None,
            "",
            "datagolf:pga:make_cut",        # arity
            "datagolf::2026136:win",        # empty tour
            "datagolf:pga::win",            # empty event
            "kalshi:pga:2026136:win",       # foreign source
            "datagolf:pga:2026136:win:x",   # arity
        ):
            assert datagolf._event_id_of(bad) is None, bad


# --------------------------------------------------- the producer: live poll --


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


class _LiveSession:
    """Answers `_poll_datagolf_live`'s SELECTs and keeps every write."""

    def __init__(self, markets, outcomes, snapshots, log):
        self.markets = markets
        self.outcomes = outcomes
        self.snapshots = snapshots
        self.added: list[object] = []
        self.log = log
        self._next_id = 9000

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

    async def commit(self) -> None:  # pragma: no cover - the ctx commits
        return None

    async def rollback(self) -> None:  # pragma: no cover - defensive
        return None

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            return _FakeResult(rowcount=0)

        entity = stmt.column_descriptions[0]["entity"]
        params = stmt.compile().params
        values: list[str] = []
        for value in params.values():
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, (list, tuple, set, frozenset)):
                values.extend(v for v in value if isinstance(v, str))

        if entity is FuturesMarket:
            # The live poll's only market read is the per-tour LIKE scan
            # (`datagolf:{tour}:%`), which has two colons, not three.
            prefix = next((v for v in values if v.endswith(":%")), None)
            if prefix is None:  # pragma: no cover - defensive
                return _FakeResult([])
            head = prefix[:-1]
            return _FakeResult(
                [m for ext, m in self.markets.items() if ext.startswith(head)]
            )

        if entity is FuturesOddsSnapshot:
            outcome_id = next(
                (v for v in params.values() if isinstance(v, int)), None
            )
            snap = self.snapshots.get(outcome_id)
            return _FakeResult([snap] if snap else [])

        if entity is FuturesOutcome:
            market_id = next(
                (v for v in params.values() if isinstance(v, int)), None
            )
            if "current_probability IS NOT NULL" in str(stmt):
                fresh = {v for v in values if v.startswith("dg_")}
                return _FakeResult([
                    o for (mid, ext), o in self.outcomes.items()
                    if mid == market_id
                    and o.current_probability is not None
                    and ext not in fresh
                ])
            ext = next((v for v in values if v.startswith("dg_")), None)
            outcome = self.outcomes.get((market_id, ext))
            return _FakeResult([outcome] if outcome else [])

        raise AssertionError(f"unexpected select: {entity}")  # pragma: no cover


class _LiveRedis:
    """Records the ORDER of every mutation, so "after the commit" is provable."""

    def __init__(self, present=None, log=None):
        self.present = dict(present or {})
        self.log = log if log is not None else []

    def get(self, key):
        return self.present.get(key)

    def set(self, key, value, ex=None):
        self.present[key] = value
        self.log.append(("set", key, value))

    def delete(self, key):
        self.present.pop(key, None)
        self.log.append(("delete", key))


class _LiveService:
    def __init__(self, board, event_name, schedule=()):
        self._board = list(board)
        self._event_name = event_name
        self._schedule = list(schedule)
        self.closed = False

    async def get_in_play_with_info(self, tour: str):
        if tour != "pga":
            return [], {}
        return list(self._board), {"event_name": self._event_name}

    async def get_schedule(self, tour: str):
        return list(self._schedule)

    async def close(self):
        self.closed = True


def _live_world():
    """Five open pga markets for `PGA_EVENT_ID`, one seeded leg on make_cut."""
    markets: dict[str, FuturesMarket] = {}
    outcomes: dict[tuple[int, str], FuturesOutcome] = {}
    snapshots: dict[int, FuturesOddsSnapshot] = {}

    started = datetime.now(timezone.utc) - timedelta(days=1)
    market_id = 30
    for market_type, _category in datagolf.MARKET_TYPES:
        ext = datagolf._external_id("pga", PGA_EVENT_ID, market_type)
        market = FuturesMarket(
            source="datagolf",
            external_id=ext,
            # The name the identity filter reads: "<event> - <label>".
            name=f"{LIVE_EVENT_NAME} - {datagolf._market_label(market_type)}",
            status="open",
        )
        market.id = market_id
        market.market_metadata = {}
        market.commence_time = started
        market.resolution_date = started + timedelta(days=4)
        markets[ext] = market
        market_id += 1

    cut_id = markets[datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")].id
    outcome = FuturesOutcome(
        market_id=cut_id,
        external_id=f"dg_{PGA_PLAYER_ID}",
        name="Tommy Fleetwood",
        current_probability=PRE_TOURNAMENT,
    )
    outcome.id = 301
    outcome.last_updated = datetime(2026, 1, 1, tzinfo=timezone.utc)
    outcome.price_changed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    outcomes[(cut_id, f"dg_{PGA_PLAYER_ID}")] = outcome
    snapshots[301] = FuturesOddsSnapshot(
        outcome_id=301, bookmaker="datagolf_model", probability=PRE_TOURNAMENT
    )
    return markets, outcomes, snapshots


def _run_live(monkeypatch, *, board_event_name, seeded=None, board=None):
    markets, outcomes, snapshots = _live_world()
    log: list[tuple] = []
    session = _LiveSession(markets, outcomes, snapshots, log)
    redis = _LiveRedis(seeded, log)
    if board is None:
        board = [
            DataGolfPlayer(
                dg_id=PGA_PLAYER_ID, player_name="Tommy Fleetwood", make_cut=GRADED
            )
        ]
    service = _LiveService(board, board_event_name)

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_exc):
            # The real `get_task_session()` commits here. Anything logged after
            # this marker happened after the transaction landed.
            log.append(("commit", None))
            return False

    monkeypatch.setattr(datagolf, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(datagolf_api, "DataGolfAPIService", lambda *a, **kw: service)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: redis)

    stats = asyncio.run(datagolf._poll_datagolf_live())
    return stats, session, redis, log, outcomes, markets


def _owner_key(tour="pga"):
    return f"{datagolf.INPLAY_OWNER_KEY_PREFIX}:{tour}"


class TestOwnershipIsPublishedOnlyByAWriteThatLanded:
    def test_a_matching_board_publishes_the_event_it_wrote(self, monkeypatch):
        _stats, _session, redis, _log, outcomes, markets = _run_live(
            monkeypatch, board_event_name=LIVE_EVENT_NAME
        )

        cut_id = markets[
            datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")
        ].id
        assert outcomes[(cut_id, f"dg_{PGA_PLAYER_ID}")].current_probability == (
            GRADED
        ), "the rig did not actually let the live poll write — nothing below means anything"
        assert redis.get(_owner_key()) == PGA_EVENT_ID, (
            "the beat wrote this event's prices and did not publish ownership, "
            "so the hourly poll will keep saw-toothing over it (#7935)"
        )

    def test_a_stale_board_publishes_nothing(self, monkeypatch):
        """The defect at its source.

        The in-play endpoint answers with last week's event. Every market fails
        the identity filter, nothing is written — and ownership must not be
        claimed, or the hourly poll stands down over a board nobody is writing.
        """
        stats, _session, redis, _log, outcomes, markets = _run_live(
            monkeypatch, board_event_name=STALE_EVENT_NAME
        )

        assert stats.get("skipped_event_mismatch"), (
            "the identity filter did not reject the stale board — this test is "
            "not exercising the case it names"
        )
        cut_id = markets[
            datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")
        ].id
        assert outcomes[(cut_id, f"dg_{PGA_PLAYER_ID}")].current_probability == (
            PRE_TOURNAMENT
        ), "the stale board was written to our markets — that is #191, not #7958"
        assert redis.get(_owner_key()) is None, (
            "a board that wrote nothing claimed the tour anyway — the hourly "
            "poll now defers too and the leaderboard has no writer at all"
        )

    def test_the_loose_live_flag_is_still_raised_for_a_stale_board(
        self, monkeypatch
    ):
        """`LIVE_KEY_PREFIX` keeps its old meaning, on purpose.

        Its other consumers are `_golf_inplay_window_active` (wakes the beat —
        starving it would stop the poll that recovers from the stale board) and
        `_snapshot_leaderboard`. Tightening one flag under three consumers is
        how this fix would become an outage.
        """
        _stats, _session, redis, _log, _outcomes, _markets = _run_live(
            monkeypatch, board_event_name=STALE_EVENT_NAME
        )

        assert redis.get(f"{datagolf.LIVE_KEY_PREFIX}:pga") == "1"
        assert datagolf._golf_inplay_window_active(redis) is True

    def test_a_tour_that_stops_writing_is_cleared_not_left_to_expire(
        self, monkeypatch
    ):
        """30 minutes of a lie is 30 minutes of a frozen leaderboard.

        The board goes stale while ownership from the previous pass is still
        live. Letting it age out would keep the hourly poll deferred for the
        whole TTL, every pass, because the stale board keeps re-answering.
        """
        _stats, _session, redis, _log, _outcomes, _markets = _run_live(
            monkeypatch,
            board_event_name=STALE_EVENT_NAME,
            seeded={_owner_key(): PGA_EVENT_ID.encode()},
        )
        assert redis.get(_owner_key()) is None

    def test_publication_happens_after_the_transaction_commits(self, monkeypatch):
        """A pass whose writes roll back must not have claimed the board."""
        _stats, _session, _redis, log, _outcomes, _markets = _run_live(
            monkeypatch, board_event_name=LIVE_EVENT_NAME
        )

        commit_at = next(i for i, e in enumerate(log) if e[0] == "commit")
        owner_at = next(
            i for i, e in enumerate(log)
            if e[0] == "set" and e[1] == _owner_key()
        )
        assert owner_at > commit_at, (
            "ownership was published from inside the transaction — a rollback "
            "would leave the tour claimed by writes that never landed"
        )

    def test_every_unwritten_tour_is_cleared(self, monkeypatch):
        """The four tours the fixture gives no board to must not stay owned."""
        seeded = {
            f"{datagolf.INPLAY_OWNER_KEY_PREFIX}:{tour}": b"whatever"
            for tour in datagolf.POLL_TOURS
        }
        _stats, _session, redis, _log, _outcomes, _markets = _run_live(
            monkeypatch, board_event_name=LIVE_EVENT_NAME, seeded=seeded
        )

        assert redis.get(_owner_key("pga")) == PGA_EVENT_ID
        for tour in datagolf.POLL_TOURS:
            if tour == "pga":
                continue
            assert redis.get(_owner_key(tour)) is None, tour

    def test_a_board_with_no_priced_players_owns_nothing(self, monkeypatch):
        """`players_written` is the claim, not "the endpoint answered".

        A board whose every player has `make_cut=None` writes no price. The
        markets are matched and the flag is up, but there is nothing to own.
        """
        board = [
            DataGolfPlayer(dg_id=PGA_PLAYER_ID, player_name="Tommy Fleetwood")
        ]
        _stats, _session, redis, _log, _outcomes, _markets = _run_live(
            monkeypatch, board_event_name=LIVE_EVENT_NAME, board=board
        )
        assert redis.get(_owner_key()) is None


def test_the_live_rig_is_not_silently_answering_nothing(monkeypatch):
    """Rig control (the fixture-is-the-specimen trap).

    If `_LiveSession` answered the per-player SELECT with None the poll would
    CREATE a second leg instead of updating the seeded one, and every assertion
    about the seeded leg's price would be true of a row nobody looked at.
    """
    _stats, session, _redis, _log, _outcomes, markets = _run_live(
        monkeypatch, board_event_name=LIVE_EVENT_NAME
    )
    cut_id = markets[datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")].id
    duplicates = [
        o for o in session.added
        if isinstance(o, FuturesOutcome)
        and o.external_id == f"dg_{PGA_PLAYER_ID}"
        and o.market_id == cut_id
    ]
    assert duplicates == [], (
        "the poll created a leg the fixture had already seeded — the fake is "
        "not serving the upsert lookup and every assertion here is vacuous"
    )
