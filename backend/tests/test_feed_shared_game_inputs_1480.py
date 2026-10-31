"""#1480 — Sports/Discover reuse the reader-independent game readings.

`_score_events` reads two things from `win_prob_snapshots` on every build: the
snapshot fallback (a card's number when the blend has none) and the prematch
prior (a settled card's "before the match" number). Both depend only on the
candidate events, so `/api/feed` now reads them through the existing shared
build cache (`principal_independent_cache.get_or_build`) and every reader of one
candidate set reuses one answer.

What this file holds, by group:

1. the shared answer is the direct answer — through the process tier and after
   the Redis codec round trip (int keys, Decimal -> float, tuples, a None draw);
2. a rescheduled kickoff misses (the cutoff is in the key);
3. a changed statement rotates the key;
4. My Teams and a price refresh never share; only `/api/feed` opts in;
5. an anonymous and a personalized reader present the same key;
6. the age is counted on live AND non-live pages (N-strict);
7. an error or a cancellation is never stored and still propagates;
8. the per-namespace kill switch reads directly with the same answer.

Group 9 is the unchanged real-Postgres gates for both statements
(`tests/integration/test_feed_snapshot_fallback_withdrawal_11254_pg.py`,
`tests/integration/test_prematch_prior_lateral_equivalence_pg.py`).
"""

import ast
import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.routes.feed as feed_mod
import app.utils.feed_cache as fc
import app.utils.feed_snapshot_fallback as fsf
import app.utils.prematch_reading as pmr
import app.utils.principal_independent_cache as pic
from app.routes.feed import _score_events
from app.utils.personalization import PersonalizationContext

NOW = datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc)

FALLBACK_NS = fsf.SNAPSHOT_FALLBACK_SHARED_NAMESPACE
PREMATCH_NS = pmr.PREMATCH_PRIOR_SHARED_NAMESPACE

# Two scheduled games with no blend (fallback), two settled ones (prematch).
SCHEDULED_A, SCHEDULED_B = 1480001, 1480002
SETTLED_A, SETTLED_B = 1480003, 1480004


def _sport():
    s = MagicMock()
    s.key = "soccer_epl"
    s.name = "EPL"
    return s


def _event(event_id: int, status: str, *, start: datetime):
    e = MagicMock()
    e.id = event_id
    e.status = status
    e.commence_time = start
    e.home_team_id = event_id * 10 + 1
    e.away_team_id = event_id * 10 + 2
    e.home_team_name = f"Home {event_id}"
    e.away_team_name = f"Away {event_id}"
    e.opening_home_probability = None
    e.opening_away_probability = None
    # No blend at all, so the snapshot fallback is what the card shows.
    e.win_probability_sources = {}
    e.espn_win_prob_home = None
    e.opening_home_spread = None
    e.opening_over_under = None
    e.opening_favorite = None
    e.llm_importance = "regular"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport()
    e.statpal_end_time = None
    e.completed_at = start + timedelta(hours=2) if status == "completed" else None
    e.period = None
    e.raw_ei = 70.0
    e.ei_metadata = None
    e.home_score = 2 if status == "completed" else None
    e.away_score = 1 if status == "completed" else None
    e.external_id = f"ext-{event_id}"
    e.game_clock = None
    e.broadcast_info = None
    e.event_tags = []
    return e


def _events(*, settled_start: datetime | None = None):
    settled_start = settled_start or NOW - timedelta(hours=5)
    return [
        _event(SCHEDULED_A, "scheduled", start=NOW + timedelta(hours=2)),
        _event(SCHEDULED_B, "scheduled", start=NOW + timedelta(hours=3)),
        _event(SETTLED_A, "completed", start=settled_start),
        _event(SETTLED_B, "completed", start=settled_start - timedelta(hours=1)),
    ]


class _SnapshotDb:
    """A session that answers the two snapshot statements and counts them.

    Values are `Decimal`, as psycopg returns `Numeric(5,4)`, so the shared path's
    float conversion is exercised. `block` (an `asyncio.Event`) holds the first
    snapshot statement until set; `fail` raises on it.
    """

    def __init__(self, events, *, block=None, fail=None, fail_prematch=None):
        self.events = events
        self.block = block
        self.fail = fail
        self.fail_prematch = fail_prematch
        self.fallback_calls = 0
        self.prematch_calls = 0
        self.prematch_binds: list[dict] = []

    @staticmethod
    def _result(rows=(), scalars=()):
        r = MagicMock()
        r.scalars.return_value.all.return_value = list(scalars)
        r.all.return_value = list(rows)
        return r

    async def execute(self, stmt, params=None, *a, **k):
        s = str(stmt).lower()
        if "win_prob_snapshots" in s:
            if self.fail is not None:
                raise self.fail
            if self.block is not None:
                await self.block.wait()
            if "unnest" in s:
                if self.fail_prematch is not None:
                    raise self.fail_prematch
                self.prematch_calls += 1
                self.prematch_binds.append(dict(params))
                rows = []
                for event_id in params["ids"]:
                    rows.append(
                        SimpleNamespace(
                            event_id=event_id,
                            source="kalshi",
                            home_win_probability=Decimal("0.6100"),
                            away_win_probability=Decimal("0.2400"),
                            draw_probability=Decimal("0.1500"),
                        )
                    )
                    rows.append(
                        SimpleNamespace(
                            event_id=event_id,
                            source="polymarket",
                            home_win_probability=Decimal("0.5800"),
                            away_win_probability=None,
                            draw_probability=None,
                        )
                    )
                return self._result(rows)
            self.fallback_calls += 1
            if ":since" in str(stmt) or "since" in (params or {}):
                rows = [
                    SimpleNamespace(event_id=i, home_win_probability=Decimal("0.6667"))
                    for i in params["ids"]
                    if i == SCHEDULED_A
                ]
            else:
                rows = [
                    SimpleNamespace(event_id=i, home_win_probability=Decimal("0.3333"))
                    for i in params["ids"]
                ]
            return self._result(rows)
        if "events" in s:
            return self._result(scalars=self.events)
        return self._result()

    @property
    def snapshot_calls(self) -> int:
        return self.fallback_calls + self.prematch_calls


def _anon_ctx() -> PersonalizationContext:
    return PersonalizationContext()


def _reader_ctx() -> PersonalizationContext:
    ctx = PersonalizationContext()
    ctx.recent_seen_event_ids = {SCHEDULED_B}
    ctx.recent_dismissed_event_ids = {SETTLED_B}
    return ctx


async def _score(db, ctx=None, **kwargs):
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        return await _score_events(db, NOW, None, ctx or _anon_ctx(), **kwargs)


def _served(items) -> str:
    """The served cards as one comparable string (mock attributes elided)."""
    return json.dumps(
        items, sort_keys=True, default=lambda o: f"<{type(o).__name__}>"
    )


def _card(items, event_id):
    return next(i["data"] for i in items if i["data"].get("id") == event_id)


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    # The process tier only, unless a test installs a fake Redis.
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")
    # These tests count the shared tier's reads; #10090's per-game cache under
    # it would answer the second build first. That cache has its own tests.
    monkeypatch.setenv("PREMATCH_READING_CACHE", "0")
    for name in ("FEED_SHARED_BUILD_TTL_S", "FEED_SHARED_BUILD_TTL_S_EVENT_SNAPSHOT_FALLBACK",
                 "FEED_SHARED_BUILD_TTL_S_EVENT_PREMATCH_PRIOR"):
        monkeypatch.delenv(name, raising=False)
    pic.clear_shared_builds()
    yield
    pic.clear_shared_builds()


# ---------------------------------------------------------------------------
# 1. the shared answer is the direct answer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_fixture_reaches_both_reads_and_both_reach_the_card():
    """The control: without it every equivalence below could compare two empty
    answers."""
    db = _SnapshotDb(_events())
    items = await _score(db)
    assert db.fallback_calls == 2  # recent pass + full pass for SCHEDULED_B
    assert db.prematch_calls == 1
    assert db.prematch_binds[0]["ids"] == [SETTLED_A, SETTLED_B]
    # The fallback number is on the card: pass 1 answers A, pass 2 answers B.
    assert _card(items, SCHEDULED_A)["current_odds"]["home_probability"] == 0.6667
    assert _card(items, SCHEDULED_B)["current_odds"]["home_probability"] == 0.3333
    # The prematch reading (Kalshi rung, with its draw) is on the settled card.
    prematch = _card(items, SETTLED_A)["prematch_odds"]
    assert (prematch["source"], prematch["home_probability"]) == ("kalshi", 0.61)


@pytest.mark.asyncio
async def test_shared_output_equals_direct_output_through_the_process_tier():
    direct = _served(await _score(_SnapshotDb(_events())))

    first_db = _SnapshotDb(_events())
    first = _served(await _score(first_db, share_inputs=True))
    second_db = _SnapshotDb(_events())
    second = _served(await _score(second_db, share_inputs=True))

    assert first == direct
    assert second == direct
    assert first_db.snapshot_calls == 3, "the first shared build reads as before"
    assert second_db.snapshot_calls == 0, "the second reader re-read the snapshots"


class _FakeRedis:
    def __init__(self):
        self.stored: dict[str, object] = {}

    async def set(self, key, value, ex=None):
        self.stored[key] = value
        return True

    async def get(self, key):
        return self.stored.get(key)


@pytest.mark.asyncio
async def test_shared_output_equals_direct_output_after_the_redis_round_trip(
    monkeypatch,
):
    """A second worker reads the artifact out of Redis and serves the same cards."""
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "1")
    redis = _FakeRedis()

    async def _client():
        return redis

    monkeypatch.setattr(pic, "_shared_redis_client", _client)

    direct = _served(await _score(_SnapshotDb(_events())))
    await _score(_SnapshotDb(_events()), share_inputs=True)
    # `get_or_build` awaits its publish before returning, so both are stored.
    assert any(FALLBACK_NS in k for k in redis.stored), list(redis.stored)
    assert any(PREMATCH_NS in k for k in redis.stored), list(redis.stored)

    pic.clear_shared_builds()  # the other worker's empty process tier
    other_worker = _SnapshotDb(_events())
    served = _served(await _score(other_worker, share_inputs=True))

    assert other_worker.snapshot_calls == 0, "the second worker did not read Redis"
    assert served == direct


def test_the_codec_round_trips_both_artifacts_with_their_types():
    fallback = {SCHEDULED_A: 0.6667, SCHEDULED_B: float(Decimal("0.3333"))}
    prematch = {
        SETTLED_A: {"kalshi": (0.61, 0.24, 0.15), "polymarket": (0.58, None, None)},
    }
    for artifact in (fallback, prematch):
        pic.assert_plain_data(artifact)
        back = pic.decode_shared_payload(pic.encode_shared_payload(artifact))
        assert back == artifact
        assert all(isinstance(k, int) for k in back)
    back = pic.decode_shared_payload(pic.encode_shared_payload(prematch))
    assert isinstance(back[SETTLED_A]["kalshi"], tuple)
    assert back[SETTLED_A]["polymarket"][2] is None


@pytest.mark.asyncio
async def test_the_fallback_artifact_holds_floats_the_card_rounds_identically():
    db = _SnapshotDb(_events())
    artifact = await fsf.read_snapshot_fallback_artifact(
        db, [SCHEDULED_A, SCHEDULED_B], now=NOW
    )
    assert artifact == {SCHEDULED_A: 0.6667, SCHEDULED_B: 0.3333}
    assert all(type(v) is float for v in artifact.values())
    direct = await fsf.read_snapshot_fallbacks(
        _SnapshotDb(_events()), [SCHEDULED_A, SCHEDULED_B], now=NOW
    )
    assert {k: round(float(v), 6) for k, v in direct.items()} == {
        k: round(float(v), 6) for k, v in artifact.items()
    }


# ---------------------------------------------------------------------------
# 2. a rescheduled kickoff misses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_rescheduled_cutoff_misses_and_reads_at_the_new_cutoff():
    await _score(_SnapshotDb(_events()), share_inputs=True)

    moved = NOW - timedelta(hours=4)
    db = _SnapshotDb(_events(settled_start=moved))
    await _score(db, share_inputs=True)

    assert db.prematch_calls == 1, "a reading cut at the old kickoff was reused"
    assert db.prematch_binds[0]["cutoffs"][0] == moved


def test_the_prematch_key_carries_every_cutoff():
    ids = [SETTLED_A, SETTLED_B]
    sources = list(pmr.PREDICTION_MARKET_SOURCES)
    a = {"ids": ids, "cutoffs": [NOW, NOW - timedelta(hours=1)], "sources": sources}
    b = {"ids": ids, "cutoffs": [NOW, NOW - timedelta(hours=2)], "sources": sources}
    assert pmr.prematch_prior_share_key(a) != pmr.prematch_prior_share_key(b)
    # Same binds, same key — and source order does not matter to the statement.
    c = dict(a, sources=list(reversed(sources)))
    assert pmr.prematch_prior_share_key(a) == pmr.prematch_prior_share_key(c)
    pic.assert_shared_key(pmr.prematch_prior_share_key(a))


# ---------------------------------------------------------------------------
# 3. a changed statement rotates the key
# ---------------------------------------------------------------------------


def test_changed_sql_text_rotates_both_keys(monkeypatch):
    ids = [SCHEDULED_A, SCHEDULED_B]
    binds = {"ids": [SETTLED_A], "cutoffs": [NOW], "sources": ["kalshi"]}
    fallback_key = fsf.snapshot_fallback_share_key(ids)
    prematch_key = pmr.prematch_prior_share_key(binds)
    pic.assert_shared_key(fallback_key)

    monkeypatch.setattr(fsf, "SNAPSHOT_FALLBACK_SQL", fsf.SNAPSHOT_FALLBACK_SQL + " ")
    assert fsf.snapshot_fallback_share_key(ids) != fallback_key
    monkeypatch.undo()
    monkeypatch.setattr(
        fsf, "SNAPSHOT_FALLBACK_RECENT_SQL", fsf.SNAPSHOT_FALLBACK_RECENT_SQL + " "
    )
    assert fsf.snapshot_fallback_share_key(ids) != fallback_key
    monkeypatch.undo()
    monkeypatch.setattr(pmr, "PREMATCH_PRIOR_SQL", pmr.PREMATCH_PRIOR_SQL + " ")
    assert pmr.prematch_prior_share_key(binds) != prematch_key
    monkeypatch.undo()
    assert fsf.snapshot_fallback_share_key(ids) == fallback_key
    assert pmr.prematch_prior_share_key(binds) == prematch_key


def test_the_fallback_key_has_no_clock_and_ignores_id_order():
    a = fsf.snapshot_fallback_share_key([SCHEDULED_A, SCHEDULED_B])
    b = fsf.snapshot_fallback_share_key([SCHEDULED_B, SCHEDULED_A])
    assert a == b
    assert a != fsf.snapshot_fallback_share_key([SCHEDULED_A])


# ---------------------------------------------------------------------------
# 4. only `/api/feed` shares; My Teams and a price refresh never do
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_my_teams_never_calls_the_shared_cache(monkeypatch):
    spy = AsyncMock(side_effect=AssertionError("My Teams reached the shared cache"))
    monkeypatch.setattr(feed_mod._pic, "get_or_build", spy)
    ctx = _anon_ctx()
    ctx.team_relations = {SCHEDULED_A * 10 + 1: "follow"}
    db = _SnapshotDb(_events())
    await _score(db, ctx, my_teams_only=True, my_team_names=["Home"], share_inputs=True)
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_a_price_refresh_never_calls_the_shared_cache(monkeypatch):
    spy = AsyncMock(side_effect=AssertionError("price refresh reached the shared cache"))
    monkeypatch.setattr(feed_mod._pic, "get_or_build", spy)
    events = _events()
    db = _SnapshotDb(events)
    await _score(db, price_refresh_events=events, share_inputs=True)
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_without_the_flag_nothing_is_shared(monkeypatch):
    spy = AsyncMock(side_effect=AssertionError("an unflagged caller shared"))
    monkeypatch.setattr(feed_mod._pic, "get_or_build", spy)
    await _score(_SnapshotDb(_events()))
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_the_flagged_build_shares_both_namespaces(monkeypatch):
    """The positive control for the three spies above."""
    seen: list[str] = []
    real = pic.get_or_build

    async def _record(namespace, key, builder, **kw):
        seen.append(namespace)
        return await real(namespace, key, builder, **kw)

    monkeypatch.setattr(feed_mod._pic, "get_or_build", _record)
    await _score(_SnapshotDb(_events()), share_inputs=True)
    assert seen == [FALLBACK_NS, PREMATCH_NS]


APP = Path(__file__).resolve().parents[1] / "app"


def _score_events_calls(path: Path):
    tree = ast.parse(path.read_text())
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_score_events"
    ]


def test_only_the_feed_build_opts_in():
    feed_calls = _score_events_calls(APP / "routes" / "feed.py")
    flagged = [
        c for c in feed_calls if any(k.arg == "share_inputs" for k in c.keywords)
    ]
    assert len(flagged) == 1
    [call] = flagged
    [kw] = [k for k in call.keywords if k.arg == "share_inputs"]
    assert isinstance(kw.value, ast.Constant) and kw.value.value is True
    # The same call passes My Teams through, so the in-function gate decides.
    assert any(k.arg == "my_teams_only" for k in call.keywords)
    for other in ("feed_prices.py", "admin_feed_config.py"):
        for c in _score_events_calls(APP / "routes" / other):
            assert not any(k.arg == "share_inputs" for k in c.keywords), other


def test_the_shared_fallback_builder_reads_at_the_request_clock():
    tree = ast.parse((APP / "routes" / "feed.py").read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "read_snapshot_fallback_artifact"
    ]
    assert len(calls) == 1
    [call] = calls
    assert [k.arg for k in call.keywords] == ["now"]
    assert call.keywords[0].value.id == "now"


# ---------------------------------------------------------------------------
# 5. an anonymous and a personalized reader share one entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_personalized_reader_consumes_the_anonymous_readers_entry():
    await _score(_SnapshotDb(_events()), _anon_ctx(), share_inputs=True)
    db = _SnapshotDb(_events())
    await _score(db, _reader_ctx(), share_inputs=True)
    assert db.snapshot_calls == 0, (
        "seen/dismissed suppression reached the key — two readers of one "
        "candidate set read the snapshots twice"
    )


@pytest.mark.asyncio
async def test_a_personalized_reader_still_gets_its_own_suppression():
    """Sharing the inputs must not share the reader's filtering."""
    await _score(_SnapshotDb(_events()), _anon_ctx(), share_inputs=True)
    served_anon = {i["data"]["id"] for i in await _score(
        _SnapshotDb(_events()), _anon_ctx(), share_inputs=True
    )}
    served_reader = {i["data"]["id"] for i in await _score(
        _SnapshotDb(_events()), _reader_ctx(), share_inputs=True
    )}
    direct_reader = {i["data"]["id"] for i in await _score(
        _SnapshotDb(_events()), _reader_ctx()
    )}
    assert served_reader == direct_reader
    assert SETTLED_B in served_anon
    assert SETTLED_B not in served_reader


# ---------------------------------------------------------------------------
# 6. the age is counted on every page (N-strict)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("namespace", [FALLBACK_NS, PREMATCH_NS])
def test_both_namespaces_are_counted_and_strict(namespace):
    assert namespace not in pic.LIVENESS_INERT_NAMESPACES
    assert namespace in pic.STRICT_AGE_NAMESPACES
    assert pic.shared_build_ttl_s(namespace) <= pic.live_artifact_ttl_ceiling_s()
    assert pic.shared_build_ttl_s(namespace) > 0
    # Not on the public header (no new telemetry rides this ship).
    assert namespace not in pic.SHARED_ARTIFACT_NAMES


def test_strict_is_exactly_the_two_game_readings():
    assert pic.STRICT_AGE_NAMESPACES == {FALLBACK_NS, PREMATCH_NS}
    assert not (pic.STRICT_AGE_NAMESPACES & pic.LIVENESS_INERT_NAMESPACES)


@pytest.mark.asyncio
async def test_a_consumed_artifact_records_its_origin_in_both_sinks():
    clock = [1000.0]
    await pic.get_or_build(
        FALLBACK_NS, ("k",), AsyncMock(return_value={1: 0.5}), clock=lambda: clock[0]
    )
    clock[0] += 25.0
    origins: list[float] = []
    strict: list[float] = []
    with pic.reuse_scope([], age_sink=origins, strict_age_sink=strict):
        await pic.get_or_build(
            FALLBACK_NS, ("k",), AsyncMock(side_effect=AssertionError),
            clock=lambda: clock[0],
        )
        # A counted but NOT strict artifact lands in the counted sink only.
        await pic.get_or_build("concepts", ("c",), AsyncMock(return_value=[]))
    assert len(origins) == 2
    assert len(strict) == 1
    assert 24.0 <= pic.oldest_consumed_artifact_age_s(strict) < 30.0


def test_a_non_live_page_loses_exactly_the_strict_age():
    for age in (0.0, 0.4, 25.0, 39.0, 59.0):
        fresh, stale = fc.feed_response_cache_ttls(
            live=False, strict_artifact_age_s=age
        )
        assert stale == fc.FEED_RESPONSE_STALE_TTL_SECONDS - int(-(-age // 1))
        assert fresh == min(fc.FEED_RESPONSE_TTL_ANON_SECONDS, stale)
        assert age + stale <= fc.FEED_RESPONSE_STALE_TTL_SECONDS + 1e-9


def test_a_non_live_page_without_strict_inputs_is_unchanged():
    """Control: `concepts`-style counted age still does NOT bind off-live."""
    assert fc.feed_response_cache_ttls(
        live=False, oldest_artifact_age_s=59.0
    ) == (fc.FEED_RESPONSE_TTL_ANON_SECONDS, fc.FEED_RESPONSE_STALE_TTL_SECONDS)


def test_a_live_page_built_from_an_aged_reading_stays_under_sixty():
    for age in (0.0, 10.0, 39.0, 59.5, 75.0):
        fresh, stale = fc.feed_response_cache_ttls(
            live=True, strict_artifact_age_s=age
        )
        assert stale == fc.live_total_age_headroom_s(age)
        assert fresh <= stale
        assert stale <= max(0, fc.FEED_RESPONSE_STALE_TTL_LIVE_SECONDS - age)


# ---------------------------------------------------------------------------
# 7. errors and cancellations are never stored and still propagate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_builder_error_propagates_and_is_not_stored():
    boom = RuntimeError("statement timeout")
    with pytest.raises(RuntimeError, match="statement timeout"):
        await _score(_SnapshotDb(_events(), fail=boom), share_inputs=True)
    assert pic.peek_shared_build(FALLBACK_NS) is None
    assert pic.peek_shared_build(PREMATCH_NS) is None

    db = _SnapshotDb(_events())
    await _score(db, share_inputs=True)
    assert db.snapshot_calls == 3, "the failed build left something behind"


@pytest.mark.asyncio
async def test_a_prematch_error_propagates_and_only_the_fallback_is_stored():
    """The second read fails on its own: its error still reaches the caller and
    nothing is stored under its namespace, while the fallback that succeeded is."""
    with pytest.raises(RuntimeError, match="lateral timeout"):
        await _score(
            _SnapshotDb(_events(), fail_prematch=RuntimeError("lateral timeout")),
            share_inputs=True,
        )
    assert pic.peek_shared_build(PREMATCH_NS) is None
    assert pic.peek_shared_build(FALLBACK_NS) is not None

    db = _SnapshotDb(_events())
    await _score(db, share_inputs=True)
    assert (db.fallback_calls, db.prematch_calls) == (0, 1)


@pytest.mark.asyncio
async def test_the_direct_path_error_behaviour_is_the_same():
    """Control: the unflagged read also raises (nothing was ever caught)."""
    with pytest.raises(RuntimeError):
        await _score(_SnapshotDb(_events(), fail=RuntimeError("x")))


@pytest.mark.asyncio
async def test_cancellation_during_the_build_and_the_lock_wait_stores_nothing():
    gate = asyncio.Event()
    leader_db = _SnapshotDb(_events(), block=gate)
    waiter_db = _SnapshotDb(_events(), block=gate)

    leader = asyncio.create_task(_score(leader_db, share_inputs=True))
    for _ in range(20):
        await asyncio.sleep(0)
    waiter = asyncio.create_task(_score(waiter_db, share_inputs=True))
    for _ in range(20):
        await asyncio.sleep(0)
    # The waiter is queued on the leader's per-key lock, not reading.
    assert waiter_db.snapshot_calls == 0

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    leader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await leader

    assert pic.peek_shared_build(FALLBACK_NS) is None
    assert pic.peek_shared_build(PREMATCH_NS) is None
    # The lock was released: the next reader builds at once.
    db = _SnapshotDb(_events())
    await asyncio.wait_for(_score(db, share_inputs=True), timeout=2.0)
    assert db.snapshot_calls == 3


# ---------------------------------------------------------------------------
# 8. the per-namespace kill switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "env, namespace",
    [
        ("FEED_SHARED_BUILD_TTL_S_EVENT_SNAPSHOT_FALLBACK", FALLBACK_NS),
        ("FEED_SHARED_BUILD_TTL_S_EVENT_PREMATCH_PRIOR", PREMATCH_NS),
    ],
)
async def test_the_namespace_kill_switch_reads_directly_with_the_same_answer(
    monkeypatch, env, namespace
):
    monkeypatch.setenv(env, "0")
    direct = _served(await _score(_SnapshotDb(_events())))
    await _score(_SnapshotDb(_events()), share_inputs=True)
    db = _SnapshotDb(_events())
    served = _served(await _score(db, share_inputs=True))
    assert served == direct
    assert pic.peek_shared_build(namespace) is None
    if namespace == FALLBACK_NS:
        assert (db.fallback_calls, db.prematch_calls) == (2, 0)
    else:
        assert (db.fallback_calls, db.prematch_calls) == (0, 1)


@pytest.mark.asyncio
async def test_the_global_kill_switch_still_outranks_both(monkeypatch):
    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")
    await _score(_SnapshotDb(_events()), share_inputs=True)
    db = _SnapshotDb(_events())
    await _score(db, share_inputs=True)
    assert db.snapshot_calls == 3
