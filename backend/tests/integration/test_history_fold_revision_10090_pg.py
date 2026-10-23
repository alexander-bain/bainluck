"""#10090 — `history_fold_revision` certifies only what a fresh chart build read past, on real Postgres.

## the ship

A source-removal recovery can finish honestly when the event's valid chart has
no live edge to pin.

## what is driven

The real `get_event_odds_history_cached(fresh=True)` on a real session, with
the real #9051 revision trigger. The only instrument is a session whose
`execute` runs a hook AFTER (or, to fail one read, BEFORE) a named statement
— so every interleaving below is caused by the build reaching that statement,
never by a sleep or a count of yields. A removal is written the way
`polymarket_ws` writes one: the bag change and its withdrawal vertex in one
transaction.

* C1  a removal committed before the build is certified on a chart with NO
      pinned edge (one series: the case both consumers refused), and an
      ordinary read of the same chart makes no claim;
* C2  a removal committed between the prefix and the series reads is drawn by
      the chart but NOT certified — the claim stays the prefix's;
* C3  a removal committed AFTER the series read is neither drawn nor
      certified (a vector read at the end would certify it: the defect);
* C4  a removal in flight (written, uncommitted) when the build runs is
      neither; once it commits, the next fresh build certifies and draws it;
* C5  tagged twins: a twin's removal is certified per row;
* C6  a twin tagged between membership and the prefix: no claim;
* C7  the canonical's bag moving between its load and the prefix: no claim;
* C7b an absorbed fold that raised or hit its cap: the route makes no claim;
* C8  a swallowed read error: the body is served, without a claim;
* C9  an empty chart is covered; a single-source chart with nothing removed
      is covered;
* C10 a reader arriving during an older build is answered by a build that
      read its removal; the older reader keeps the older claim;
* C11 a cancelled builder's waiter is answered by its own build's claim;
* C12 the prefix's vector and refusals equal the bag fold's on real rows
      (twins, flipped orientation, absorbed, deleted rows, a removal);
* C13 the route's prefix statement selects no price bag, a large irrelevant
      one included, and certifies the same rows.

Runs where `SEARCH_TEST_DATABASE_URL` is set (CI `search-recall`).
"""

from __future__ import annotations

import asyncio
import json
import time as _real_time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DB_URL = __import__("os").environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #10090 history coverage gate "
            "(CI job `search-recall` provides one)"
        ),
    ),
]

CANON, TWIN, LATE_TWIN = 1009001, 1009002, 1009003
SPORT = 10090
HOURS = 48


def _flat(statement) -> str:
    return " ".join(str(statement).split())


def is_prefix_or_pin(sql: str) -> bool:
    # `folded_probability_sources_with_revision`'s one statement; the history
    # build's FIRST is the coverage prefix (the pin's own comes after the series).
    return "AS tagged" in sql and "events.win_probability_sources_rev" in sql


def is_series_fold(sql: str) -> bool:
    return sql.startswith(
        "SELECT events.id, events.home_team_name, events.away_team_name FROM events"
    )


def is_winprob_read(sql: str) -> bool:
    return "FROM win_prob_snapshots" in sql and "win_prob_snapshots.event_id IN" in sql


def is_score_read(sql: str) -> bool:
    return "FROM score_snapshots" in sql


class HookedSession(AsyncSession):
    """A request session that runs ``after``/``before`` hooks once, on the
    first statement each predicate matches, and records every statement."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.hooks: list[list] = []  # [when, predicate, action, fired]
        self.statements: list[str] = []

    def after(self, predicate, action):
        self.hooks.append(["after", predicate, action, False])

    def before(self, predicate, action):
        self.hooks.append(["before", predicate, action, False])

    async def _fire(self, when, sql):
        for hook in self.hooks:
            if hook[0] == when and not hook[3] and hook[1](sql):
                hook[3] = True
                await hook[2]()

    async def execute(self, statement, *a, **kw):
        sql = _flat(statement)
        await self._fire("before", sql)
        self.statements.append(sql)
        result = await super().execute(statement, *a, **kw)
        await self._fire("after", sql)
        return result

    def fired(self):
        return [h[3] for h in self.hooks]


@pytest.fixture
async def pg(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import models as _registers_every_table  # noqa: F401
    from app.routes import events as events_route
    from app.services.database import Base
    from app.utils import event_history_cache as ehc

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    Plain = async_sessionmaker(engine, expire_on_commit=False)
    Hooked = async_sessionmaker(engine, expire_on_commit=False, class_=HookedSession)
    events_route._HISTORY_FRESH_BUILDS.clear()
    events_route._event_detail_cache.clear()
    ehc._reset_for_tests()
    yield engine, Plain, Hooked
    assert events_route._HISTORY_FRESH_BUILDS == {}, "a build left its slot held"
    events_route._event_detail_cache.clear()
    ehc._reset_for_tests()
    await engine.dispose()


def _now():
    return datetime.now(timezone.utc)


async def _seed(Plain, *, twin=False, polymarket_points=4, espn_points=0):
    """A live game. Canonical bag {polymarket, espn}; Polymarket readings on
    the canonical (the chart's one series unless ``espn_points``); with
    ``twin``, a tagged duplicate holding Kalshi and its readings."""
    from app.models.models import Event, Sport, WinProbSnapshot

    now = _now()
    stamp = now.isoformat()
    async with Plain() as s:
        s.add(Sport(id=SPORT, key="soccer_epl", name="EPL"))
        await s.flush()
        s.add(
            Event(
                id=CANON,
                sport_id=SPORT,
                home_team_name="Arsenal",
                away_team_name="Chelsea",
                commence_time=now - timedelta(minutes=50),
                status="live",
                win_probability_sources={
                    "polymarket": {"value": 0.6, "updated_at": stamp},
                    "espn": {"value": 0.55, "updated_at": stamp},
                },
            )
        )
        if twin:
            s.add(
                Event(
                    id=TWIN,
                    sport_id=SPORT,
                    home_team_name="Arsenal",
                    away_team_name="Chelsea",
                    commence_time=now - timedelta(minutes=50),
                    status="live",
                    event_tags=[f"provenance:duplicate-of:{CANON}"],
                    win_probability_sources={"kalshi": {"value": 0.58, "updated_at": stamp}},
                )
            )
        await s.flush()
        for i in range(polymarket_points):
            s.add(WinProbSnapshot(
                event_id=CANON, source="polymarket",
                captured_at=now - timedelta(minutes=40 - 5 * i),
                home_win_probability=0.55 + 0.01 * i, away_win_probability=0.45 - 0.01 * i,
            ))
        for i in range(espn_points):
            s.add(WinProbSnapshot(
                event_id=CANON, source="espn",
                captured_at=now - timedelta(minutes=39 - 5 * i),
                home_win_probability=0.5 + 0.01 * i, away_win_probability=0.5 - 0.01 * i,
            ))
        if twin:
            for i in range(4):
                s.add(WinProbSnapshot(
                    event_id=TWIN, source="kalshi",
                    captured_at=now - timedelta(minutes=38 - 5 * i),
                    home_win_probability=0.57, away_win_probability=0.43,
                ))
        await s.commit()


async def _remove(session, event_id, source, *, commit=True):
    """`polymarket_ws`'s removal: bag key gone + a NULL withdrawal vertex,
    one transaction. Returns the revision the UPDATE produced."""
    from app.models.models import WinProbSnapshot

    rev, removed_at = (
        await session.execute(
            text(
                "UPDATE events SET win_probability_sources = win_probability_sources - :s "
                "WHERE id = :id RETURNING win_probability_sources_rev, clock_timestamp()"
            ),
            {"s": source, "id": event_id},
        )
    ).one()
    session.add(WinProbSnapshot(
        event_id=event_id, source=source, captured_at=removed_at,
        home_win_probability=None, away_win_probability=None,
        valid_until=removed_at, game_state={"live_source_withdrawal": True},
    ))
    await session.flush()
    if commit:
        await session.commit()
    return rev


def _remover(Plain, event_id, source):
    async def action():
        async with Plain() as s:
            await _remove(s, event_id, source)
    return action


async def _history(session, *, fresh=True):
    from app.routes import events as events_route

    resp = await events_route.get_event_odds_history_cached(
        CANON, hours=HOURS, chart_range="all", response=None, db=session, fresh=fresh
    )
    return json.loads(resp.body)


async def _fresh(Hooked, configure=None, *, fresh=True):
    async with Hooked() as session:
        if configure is not None:
            configure(session)
        body = await _history(session, fresh=fresh)
        return body, session


def _withdrawn(body, source):
    """True iff the served series for ``source`` ends on the NULL vertex."""
    points = (body.get("win_prob_history") or {}).get(source) or []
    return bool(points) and points[-1].get("home_probability") is None


def _v(**revs):
    return {str({"c": CANON, "t": TWIN, "u": LATE_TWIN}[k]): v for k, v in revs.items()}


class TestTheClaimIsReadBeforeTheHistory:
    async def test_c1_a_removal_before_the_build_is_certified_without_a_pinned_edge(self, pg):
        _e, Plain, Hooked = pg
        await _seed(Plain)
        async with Plain() as s:
            assert await _remove(s, CANON, "polymarket") == 1
        body, _ = await _fresh(Hooked)
        assert _withdrawn(body, "polymarket")
        # The case the consumers refused: one series, nothing pinned.
        assert body["blend_edge_pinned"] is False
        assert body["blend_edge_fold_revision"] is None
        assert body["history_fold_revision"] == _v(c=1)
        # Control: the same chart read the ordinary way makes no claim.
        ordinary, _ = await _fresh(Hooked, fresh=False)
        assert _withdrawn(ordinary, "polymarket")
        assert ordinary["history_fold_revision"] is None

    async def test_c2_a_removal_between_prefix_and_series_is_drawn_not_certified(self, pg):
        _e, Plain, Hooked = pg
        await _seed(Plain)
        body, session = await _fresh(
            Hooked, lambda s: s.after(is_prefix_or_pin, _remover(Plain, CANON, "polymarket"))
        )
        assert session.fired() == [True]
        assert _withdrawn(body, "polymarket"), "the later series read saw the removal"
        assert body["history_fold_revision"] == _v(c=0)

    async def test_c3_a_removal_after_the_series_read_is_neither_drawn_nor_certified(self, pg):
        _e, Plain, Hooked = pg
        await _seed(Plain)
        body, session = await _fresh(
            Hooked, lambda s: s.after(is_winprob_read, _remover(Plain, CANON, "polymarket"))
        )
        assert session.fired() == [True]
        assert not _withdrawn(body, "polymarket")
        # A vector read at the end of the build would say {c: 1} over a chart
        # that never saw the removal.
        assert body["history_fold_revision"] == _v(c=0)

    async def test_c4_an_in_flight_removal_is_neither_until_it_commits(self, pg):
        _e, Plain, Hooked = pg
        await _seed(Plain)
        async with Plain() as writer:
            assert await _remove(writer, CANON, "polymarket", commit=False) == 1
            # The build runs while the row lock is held: MVCC reads never wait.
            body, _ = await _fresh(Hooked)
            assert not _withdrawn(body, "polymarket")
            assert body["history_fold_revision"] == _v(c=0)
            await writer.commit()
        after, _ = await _fresh(Hooked)
        assert _withdrawn(after, "polymarket")
        assert after["history_fold_revision"] == _v(c=1)


class TestMembershipAndTheCanonicalBag:
    async def test_c5_a_twin_removal_is_certified_on_the_twins_row(self, pg):
        _e, Plain, Hooked = pg
        await _seed(Plain, twin=True)
        async with Plain() as s:
            assert await _remove(s, TWIN, "kalshi") == 1
        body, _ = await _fresh(Hooked)
        assert _withdrawn(body, "kalshi")
        assert body["history_fold_revision"] == _v(c=0, t=1)

    async def test_c6_a_twin_tagged_after_membership_was_read_makes_no_claim(self, pg):
        _e, Plain, Hooked = pg
        await _seed(Plain, twin=True)

        async def tag_late_twin():
            from app.models.models import Event

            async with Plain() as s:
                s.add(Event(
                    id=LATE_TWIN, sport_id=SPORT, home_team_name="Arsenal",
                    away_team_name="Chelsea", commence_time=_now() - timedelta(minutes=50),
                    status="live", event_tags=[f"provenance:duplicate-of:{CANON}"],
                    win_probability_sources={},
                ))
                await s.commit()

        body, session = await _fresh(Hooked, lambda s: s.after(is_series_fold, tag_late_twin))
        assert session.fired() == [True]
        # The prefix sees the new twin; the series reads never read it.
        assert body["history_fold_revision"] is None
        # Control: once membership is stable the same chart is certified.
        settled, _ = await _fresh(Hooked)
        assert settled["history_fold_revision"] == _v(c=0, t=0, u=0)

    async def test_c7_the_canonical_bag_moving_after_its_load_makes_no_claim(self, pg):
        _e, Plain, Hooked = pg
        await _seed(Plain)
        first = []

        def configure(s):
            s.after(lambda sql: not first and not first.append(sql), _remover(Plain, CANON, "polymarket"))

        body, session = await _fresh(Hooked, configure)
        assert session.fired() == [True]
        assert "FROM events" in first[0] and "events.win_probability_sources_rev" in first[0]
        # The build holds the canonical's rev-0 bag; the prefix reads rev 1.
        assert body["history_fold_revision"] is None

    async def test_c7b_an_absorbed_fold_that_did_not_run_whole_makes_no_claim(self, pg, monkeypatch):
        """The route hands the fold's own completeness to the prefix. The real
        fold runs and its rows are kept; only its flag says it raised or hit
        its candidate cap, so the rows it would have absorbed are unknown."""
        from app.utils import serve_fold_absorbed as sfa

        _e, Plain, Hooked = pg
        await _seed(Plain)
        async with Plain() as s:
            assert await _remove(s, CANON, "polymarket") == 1
        real = sfa.serve_fold_absorbed_rows_with_completeness
        incomplete, calls = [True], []

        async def fold(db, event):
            rows, complete = await real(db, event)
            calls.append(complete)
            return rows, complete and not incomplete[0]

        monkeypatch.setattr(sfa, "serve_fold_absorbed_rows_with_completeness", fold)
        body, _ = await _fresh(Hooked)
        assert calls == [True], "the route read the fold once, and it ran whole"
        assert _withdrawn(body, "polymarket"), "the body is still served"
        assert body["history_fold_revision"] is None
        # Control: the same build with the fold's flag left true is certified.
        incomplete[0] = False
        whole, _ = await _fresh(Hooked)
        assert calls == [True, True]
        assert whole["history_fold_revision"] == _v(c=1)


class TestOnlyACompleteFreshBuildClaims:
    async def test_c8_a_swallowed_read_error_serves_the_body_without_a_claim(self, pg):
        _e, Plain, Hooked = pg
        await _seed(Plain)

        async def fail():
            raise RuntimeError("score read failed")

        body, session = await _fresh(Hooked, lambda s: s.before(is_score_read, fail))
        assert session.fired() == [True]
        assert body["win_prob_history"].get("polymarket"), "the body is still served"
        assert body["history_fold_revision"] is None

    async def test_c9_an_empty_chart_and_a_single_source_chart_are_covered(self, pg):
        _e, Plain, Hooked = pg
        await _seed(Plain, polymarket_points=0)
        empty, _ = await _fresh(Hooked)
        assert empty["win_prob_history"] == {}
        assert empty["aggregate_line"] is None
        assert empty["history_fold_revision"] == _v(c=0)

    async def test_c9b_a_single_source_chart_with_nothing_removed_is_covered(self, pg):
        _e, Plain, Hooked = pg
        await _seed(Plain)
        body, _ = await _fresh(Hooked)
        assert list(body["win_prob_history"]) == ["polymarket"]
        assert body["blend_edge_pinned"] is False
        assert body["history_fold_revision"] == _v(c=0)


class _TimeProbe:
    """`events.time` with one observable call: the next `time()` after `arm`
    is the arriving reader computing its ask stamp, which it does
    synchronously right before it looks for an in-flight build."""

    def __init__(self):
        self.asked = asyncio.Event()
        self.armed = False

    def arm(self):
        self.armed = True

    def time(self):
        if self.armed:
            self.armed = False
            self.asked.set()
        return _real_time.time()

    def __getattr__(self, name):
        return getattr(_real_time, name)


class TestTheCoalescedGeneration:
    async def _older_build_parked_after_its_prefix(self, pg, monkeypatch):
        from app.routes import events as events_route

        _e, Plain, Hooked = pg
        await _seed(Plain)
        probe = _TimeProbe()
        monkeypatch.setattr(events_route, "time", probe)
        parked, release = asyncio.Event(), asyncio.Event()

        async def remove_then_park():
            await _remover(Plain, CANON, "polymarket")()
            parked.set()
            await release.wait()

        older_session = Hooked()
        older_session.after(is_prefix_or_pin, remove_then_park)
        older = asyncio.ensure_future(_history(older_session))
        await parked.wait()
        key = next(iter(events_route._HISTORY_FRESH_BUILDS))
        probe.arm()
        newer_session = Hooked()
        newer = asyncio.ensure_future(_history(newer_session))
        await probe.asked.wait()
        # The arriving reader asked while the older build was still in flight.
        assert key in events_route._HISTORY_FRESH_BUILDS
        return older, older_session, newer, newer_session, release

    async def test_c10_an_arriving_reader_gets_a_build_that_read_its_removal(self, pg, monkeypatch):
        older, older_session, newer, newer_session, release = (
            await self._older_build_parked_after_its_prefix(pg, monkeypatch)
        )
        release.set()
        old_body, new_body = await older, await newer
        await older_session.close()
        await newer_session.close()
        assert old_body["history_fold_revision"] == _v(c=0)
        assert new_body["history_fold_revision"] == _v(c=1)
        assert _withdrawn(new_body, "polymarket")
        # The newer claim came from the newer reader's own prefix.
        assert sum(map(is_prefix_or_pin, newer_session.statements)) >= 1

    async def test_c11_a_cancelled_builders_waiter_gets_its_own_builds_claim(self, pg, monkeypatch):
        older, older_session, newer, newer_session, release = (
            await self._older_build_parked_after_its_prefix(pg, monkeypatch)
        )
        older.cancel()
        with pytest.raises(asyncio.CancelledError):
            await older
        await older_session.close()
        new_body = await newer
        await newer_session.close()
        release.set()
        assert new_body["history_fold_revision"] == _v(c=1)
        assert sum(map(is_prefix_or_pin, newer_session.statements)) >= 1


_BAG_COLUMN = __import__("re").compile(r"events\.win_probability_sources(?!_rev)")
PAD = "x" * 2_000_000  # a ~2 MB source the prefix has no use for


def _wire(engine):
    """Every SQL string the engine sends to Postgres, in order."""
    from sqlalchemy import event as sa_event

    sent: list[str] = []

    def record(conn, cursor, statement, *a):
        sent.append(_flat(statement))

    sa_event.listen(engine.sync_engine, "before_cursor_execute", record)
    return sent, lambda: sa_event.remove(engine.sync_engine, "before_cursor_execute", record)


async def _pad(Plain, event_id):
    async with Plain() as s:
        await s.execute(
            text(
                "UPDATE events SET win_probability_sources = win_probability_sources "
                "|| jsonb_build_object('noise', jsonb_build_object('value', 0.5, 'pad', CAST(:pad AS text))) "
                "WHERE id = :id"
            ),
            {"pad": PAD, "id": event_id},
        )
        await s.commit()


class TestThePrefixReadsNoBags:
    async def _both(self, Plain, absorbed_ids=(), *, before=None):
        from app.models.models import Event
        from app.utils.proven_duplicates import (
            folded_probability_sources_with_revision,
            folded_revision_vector,
        )

        async with Plain() as s:
            event = await s.get(Event, CANON)
            absorbed = [
                (await s.get(Event, i)) or type("Gone", (), {"id": i, "win_probability_sources": {}})()
                for i in absorbed_ids
            ]
            if before is not None:
                await before()
            lean = await folded_revision_vector(s, event, absorbed)
            _sources, full = await folded_probability_sources_with_revision(s, event, absorbed)
        return lean, full

    async def test_c12_the_same_vector_and_refusals_as_the_bag_fold(self, pg):
        from app.models.models import Event

        engine, Plain, _Hooked = pg
        await _seed(Plain, twin=True)
        await _pad(Plain, TWIN)
        async with Plain() as s:
            # Tagged, home/away swapped: folded only when absorbed.
            s.add(Event(
                id=LATE_TWIN, sport_id=SPORT, home_team_name="Chelsea",
                away_team_name="Arsenal", commence_time=_now() - timedelta(minutes=50),
                status="live", event_tags=[f"provenance:duplicate-of:{CANON}"],
                win_probability_sources={"kalshi": {"value": 0.4}},
            ))
            await s.commit()

        cases = {}
        cases["twins"] = await self._both(Plain)
        cases["absorbed flipped twin"] = await self._both(Plain, (LATE_TWIN,))
        cases["absorbed canonical"] = await self._both(Plain, (CANON, LATE_TWIN))
        async with Plain() as s:
            await _remove(s, TWIN, "kalshi")
        cases["after a twin removal"] = await self._both(Plain, (LATE_TWIN,))

        async def delete(event_id):
            async with Plain() as s:
                await s.execute(text("DELETE FROM win_prob_snapshots WHERE event_id = :id"), {"id": event_id})
                await s.execute(text("DELETE FROM events WHERE id = :id"), {"id": event_id})
                await s.commit()

        cases["absorbed row deleted"] = await self._both(
            Plain, (LATE_TWIN,), before=lambda: delete(LATE_TWIN)
        )
        cases["canonical deleted"] = await self._both(Plain, before=lambda: delete(CANON))

        for name, (lean, full) in cases.items():
            assert lean == full, name
        assert {k: lean for k, (lean, _) in cases.items()} == {
            "twins": _v(c=0, t=1),  # `_pad` bumped the twin
            "absorbed flipped twin": _v(c=0, t=1, u=0),
            "absorbed canonical": _v(c=0, t=1, u=0),
            "after a twin removal": _v(c=0, t=2, u=0),
            "absorbed row deleted": None,
            "canonical deleted": None,
        }

    async def test_c13_the_routes_prefix_selects_no_bag_and_certifies_the_same_rows(self, pg):
        engine, Plain, Hooked = pg
        await _seed(Plain, twin=True)
        await _pad(Plain, CANON)
        await _pad(Plain, TWIN)
        sent, stop = _wire(engine)
        try:
            body, session = await _fresh(Hooked)
        finally:
            stop()
        assert body["history_fold_revision"] == _v(c=1, t=1)
        prefix = next(sql for sql in session.statements if is_prefix_or_pin(sql))
        assert not _BAG_COLUMN.search(prefix), prefix
        on_wire = [sql for sql in sent if is_prefix_or_pin(sql)]
        assert on_wire and not _BAG_COLUMN.search(on_wire[0]), on_wire[:1]
        # The bag fold the detail and pin use still reads bags (control: the
        # pattern can see one).
        from app.utils.proven_duplicates import folded_probability_sources_with_revision
        from app.models.models import Event

        sent2, stop2 = _wire(engine)
        try:
            async with Plain() as s:
                event = await s.get(Event, CANON)
                sources, _ = await folded_probability_sources_with_revision(s, event)
        finally:
            stop2()
        assert sources["noise"]["pad"] == PAD
        assert any(is_prefix_or_pin(sql) and _BAG_COLUMN.search(sql) for sql in sent2)
