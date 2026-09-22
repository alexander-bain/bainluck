"""#7807 — the recovered bank survives eviction, and does not outlive its TTL.

PILLAR: TRUTH. SHIP: a market's recovered venue history is still on the chart for
the reader who arrives after Redis has evicted it.

#7351 recovers the history; #7563 measured Redis dropping it inside four hours on
3 of 3 markets, because a 100 MB `allkeys-lru` instance evicts a rarely-read
35 KB value regardless of its `ex=`; #7736 made the LOSS detectable. This ship
puts the series itself in `durable_state_snapshots`, behind Redis, so the loss
stops happening.

The end-to-end proof — both real routes, real Postgres, real Redis, the Redis key
deleted mid-test to stage a real eviction — is in
`tests/integration/test_generic_market_history_7351_real_pg_redis.py`, and the
round trip through a real server plus the GUC restore are in
`tests/integration/test_durable_venue_history_7807_pg.py`. This file needs
nothing, so it runs in every shard, and it holds the four rules that make the new
tier safe rather than merely present:

  * the durable tier NEVER extends the bank's declared life;
  * an EMPTY answer is never persisted — a negative cache with no expiry would
    freeze a market as "nothing here" for everyone, for ever;
  * a broken durable tier leaves the chart exactly as cold as it is today;
  * the read's own `statement_timeout` never escapes onto the request session.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.tasks import generic_market_history_fill as fill
from app.utils import durable_state
from app.utils import generic_market_history as gmh

# 🔴 RELATIVE, NEVER A LITERAL (gotcha #44: offset FIRST, then truncate).
# Most anchors in this file are injected into the code under test (`now=NOW`,
# `generated_at=NOW`) and are self-consistent at any wall-clock time. The
# `_serve` tests are NOT: they reach `_load_generic_venue_history`, which has no
# `now=` seam and reads the real clock, so a payload's `built_at` is compared
# against today. With the literal `2026-09-21T12:00:00Z` that made the file a
# dated time bomb, and it went off on master at exactly 14:00:00Z on 09-22:
# `test_a_durable_hit_is_put_back_in_front_of_the_next_reader` builds its bank at
# NOW−10h = 09-21T02:00Z, CACHE_TTL_SECONDS is 36h, so the bank's declared life
# ended 09-22T14:00Z. CI was green at 13:30Z and red at 14:21Z on an unrelated
# commit, and would have stayed red for ever — the remaining TTL the test asserts
# is positive had gone to −1,721s. The default-`_payload()` `_serve` tests were
# the next one due, at 09-23T00:00Z.
# Truncating to the hour keeps the anchor stable within a run without pinning it
# to a date; every offset below stays inside the 36h TTL by many hours.
NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _market(source="kalshi", market_id=1, external_id="KXQ-26", status="open"):
    return SimpleNamespace(id=market_id, source=source, external_id=external_id, status=status)


def _outcome(oid=10, external_id="KXQ-26-YES", name="Yes"):
    # `resolution_source` / `is_winner` are what the canonical support filter
    # (`_drop_unsupported_snapshot_points`) grades each point against — an
    # ungraded, un-won outcome is the ordinary open-market case.
    return SimpleNamespace(
        id=oid, external_id=external_id, name=name,
        resolution_source=None, is_winner=None,
    )


def _payload(market=None, outcome=None, *, points=None, built_at=None, **over):
    market = market or _market()
    outcome = outcome or _outcome()
    points = points if points is not None else [
        [(NOW - timedelta(hours=h)).isoformat(), 0.1 + h / 1000, 0.09, 0.11, None, "kalshi_candle_60m"]
        for h in (30, 20, 10)
    ]
    body = {
        "schema": gmh.SCHEMA, "version": gmh.CACHE_VERSION, "scale": gmh.SCALE,
        "market_id": market.id, "market_source": market.source,
        "market_external_id": market.external_id,
        "attempted_at": (built_at or NOW).isoformat(),
        "built_at": (built_at or NOW).isoformat(),
        "status": "ok", "market_settled": False,
        "outcomes": {str(outcome.id): {
            "outcome_id": outcome.id,
            "contract": gmh.kalshi_contract(outcome),
            "points": points,
        }},
        "stats": {"fetched_points": len(points)},
    }
    body.update(over)
    return body


class _Session:
    """Records what the durable half does to the caller's transaction."""

    def __init__(self, read=None, *, nested_raises=False):
        self.staged = []
        self.commits = 0
        self.rollbacks = 0
        self.nested_begun = 0
        self.nested_rolled_back = 0
        self.nested_released = 0
        self._read = read
        self._nested_raises = nested_raises

    async def begin_nested(self):
        self.nested_begun += 1
        if self._nested_raises:
            raise RuntimeError("no savepoint for you")
        session = self

        class _Nested:
            # `commit` is what `async with db.begin_nested()` calls on a clean
            # exit — i.e. RELEASE, the leaking path. Counted separately from
            # `rollback` so the two are told apart rather than both reading as
            # "the savepoint was closed".
            async def rollback(self):
                session.nested_rolled_back += 1

            async def commit(self):
                session.nested_released += 1

        return _Nested()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def execute(self, *a, **k):
        raise AssertionError("the durable read must go through read_snapshot")


def _envelope(payload, *, generated_at=NOW, version=None):
    return durable_state.DurableEnvelope.build(
        identity=gmh.durable_identity(1),
        schema_version=version or gmh.CACHE_VERSION,
        payload=payload,
        generated_at=generated_at,
        source=fill.DURABLE_SOURCE,
    )


def _read_ok(payload, *, generated_at=NOW):
    return durable_state.EnvelopeRead(
        status="ok", tier="durable", envelope=_envelope(payload, generated_at=generated_at)
    )


# ── the identity ────────────────────────────────────────────────────────────


def test_the_durable_identity_carries_no_version_so_a_bump_cannot_orphan_a_row():
    """A Redis key may carry the version because it expires; a row may not."""
    assert gmh.durable_identity(59165099) == "generic-history:59165099"
    assert gmh.CACHE_VERSION not in gmh.durable_identity(59165099)
    # And it is still one row per market, never shared.
    assert gmh.durable_identity(1) != gmh.durable_identity(2)


def test_the_durable_identity_is_not_the_redis_key():
    """Two substrates, two namespaces — a collision here would be silent."""
    assert gmh.durable_identity(7) != gmh.cache_key(7)


# ── the write: what earns a durable row ─────────────────────────────────────


@pytest.mark.parametrize("payload", [
    # the venue said nothing
    _payload(points=[], status="empty"),
    # one window errored and the rest held nothing
    _payload(points=[], status="degraded"),
    {"status": "ok", "outcomes": {}},
    {"status": "ok"},
    None,
])
async def test_an_answer_carrying_no_points_is_never_persisted(payload):
    """🔴 A durable EMPTY is a negative cache that cannot expire.

    The Redis negative cache is bounded by `REFRESH_AFTER_SECONDS` precisely so
    that one rate-limited fill can be wrong for three hours instead of for ever.
    Persisting it would make a single venue outage permanent for every reader of
    that market, and nothing in the fill would ever ask again.
    """
    session = _Session()
    result = await fill.publish_durable_history(session, 1, payload)
    assert result["status"] == "skipped" and result["reason"] == "no_points"
    assert session.staged == [] and session.commits == 0


async def test_a_payload_that_will_not_date_itself_is_not_persisted():
    """The generation IS the build stamp; without one there is no ordering."""
    payload = _payload()
    payload.pop("built_at")
    result = await fill.publish_durable_history(_Session(), 1, payload)
    assert result["status"] == "skipped" and result["reason"] == "no_built_at"


async def test_a_naive_build_stamp_is_refused_rather_than_guessed():
    """The fill writes aware UTC; a naive stamp did not come from the fill and
    is ambiguous by up to a day — which would mis-order two generations."""
    payload = _payload()
    payload["built_at"] = "2026-09-21T12:00:00"
    session = _Session()
    result = await fill.publish_durable_history(session, 1, payload)
    assert result["status"] == "skipped" and result["reason"] == "no_built_at"


async def test_the_bank_is_staged_in_the_callers_transaction_and_never_committed(monkeypatch):
    """It must land with #7736's marker or not at all (CERT-851's rule)."""
    seen = {}

    async def _fake_in_txn(db, envelope):
        seen["db"] = db
        seen["envelope"] = envelope
        return {"status": "ok"}

    async def _must_not_commit(db, envelope):  # pragma: no cover - guard
        raise AssertionError("publish_durable_history must not commit")

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(ds, "publish_snapshot_in_txn", _fake_in_txn)
    monkeypatch.setattr(ds, "publish_snapshot", _must_not_commit)

    session = _Session()
    payload = _payload()
    result = await fill.publish_durable_history(session, 59165099, payload)

    assert result["status"] == "ok"
    assert seen["db"] is session
    assert session.commits == 0, "the fill's transaction is the caller's to end"
    envelope = seen["envelope"]
    assert envelope.identity == "generic-history:59165099"
    assert envelope.schema_version == gmh.CACHE_VERSION
    assert envelope.payload == payload
    assert envelope.source == fill.DURABLE_SOURCE


async def test_the_generation_orders_builds_so_a_later_fill_wins(monkeypatch):
    """`publish_snapshot`'s guard is `stored <= incoming`, so the generation has
    to come from the BUILD — a wall-clock stamp would let a slow writer carrying
    an older payload overwrite a newer one."""
    envelopes = []

    async def _fake_in_txn(db, envelope):
        envelopes.append(envelope)
        return {"status": "ok"}

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(ds, "publish_snapshot_in_txn", _fake_in_txn)

    older = NOW - timedelta(hours=3)
    await fill.publish_durable_history(_Session(), 1, _payload(built_at=older))
    await fill.publish_durable_history(_Session(), 1, _payload(built_at=NOW))

    assert envelopes[0].generation == durable_state.generation_for(older)
    assert envelopes[1].generation == durable_state.generation_for(NOW)
    assert envelopes[1].generation > envelopes[0].generation


async def test_a_durable_write_that_explodes_never_fails_the_fill(monkeypatch):
    import app.services.durable_snapshots as ds

    async def _boom(db, envelope):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(ds, "publish_snapshot_in_txn", _boom)
    result = await fill.publish_durable_history(_Session(), 1, _payload())
    assert result["status"] == "error"


# ── the read: the declared TTL, made real but not longer ────────────────────


async def _read(monkeypatch, read_result, *, now=NOW, session=None, raises=False):
    import app.services.durable_snapshots as ds

    async def _fake_read(db, identity, *, expected_version=None, max_age_s=None, now=None):
        if raises:
            raise RuntimeError("database is wedged")
        _fake_read.calls.append(
            {"identity": identity, "expected_version": expected_version, "max_age_s": max_age_s}
        )
        return read_result

    _fake_read.calls = []
    monkeypatch.setattr(ds, "read_snapshot", _fake_read)
    session = session or _Session()
    payload = await fill.read_durable_history(session, 1, now=now)
    return payload, session, _fake_read.calls


async def test_a_bank_inside_its_declared_life_is_served(monkeypatch):
    payload = _payload()
    got, _, calls = await _read(monkeypatch, _read_ok(payload, generated_at=NOW - timedelta(hours=30)))
    assert got == payload
    assert calls[0]["identity"] == "generic-history:1"
    assert calls[0]["expected_version"] == gmh.CACHE_VERSION


async def test_an_open_markets_bank_past_36h_is_refused_not_served(monkeypatch):
    """🔴 THE SHIP IS "36 HOURS BECOMES REAL", NOT "36 HOURS BECOMES LONGER".

    Redis wrote this bank with `ex=36h`. The durable copy has no TTL of its own,
    so if the reader did not apply the same bound the tier would quietly convert
    an expiring cache into a permanent one — serving a reader a two-week-old
    price line that the cache policy had already retired.
    """
    aged = NOW - timedelta(seconds=fill.CACHE_TTL_SECONDS + 60)
    got, _, _ = await _read(monkeypatch, _read_ok(_payload(), generated_at=aged))
    assert got is None


async def test_the_open_market_bound_is_exactly_the_redis_ttl(monkeypatch):
    """One second either side of the declared life, so the bound cannot drift
    away from the `ex=` it mirrors without this failing."""
    inside = NOW - timedelta(seconds=fill.CACHE_TTL_SECONDS - 1)
    outside = NOW - timedelta(seconds=fill.CACHE_TTL_SECONDS + 1)
    assert (await _read(monkeypatch, _read_ok(_payload(), generated_at=inside)))[0] is not None
    assert (await _read(monkeypatch, _read_ok(_payload(), generated_at=outside)))[0] is None


async def test_a_settled_market_keeps_the_seven_day_life_its_cache_had(monkeypatch):
    """`market_settled` is the state the FILL ran under, which is the state that
    chose the Redis TTL — so the durable bound reproduces the lifetime the bank
    was written with, not one re-decided from a status that has moved since."""
    settled = _payload(market_settled=True)
    four_days = NOW - timedelta(days=4)
    eight_days = NOW - timedelta(days=8)

    assert (await _read(monkeypatch, _read_ok(settled, generated_at=four_days)))[0] is not None
    assert (await _read(monkeypatch, _read_ok(settled, generated_at=eight_days)))[0] is None
    # The same age on an OPEN market's bank is long gone — the two bounds are
    # genuinely different, so this pair cannot both pass by accident.
    assert (await _read(monkeypatch, _read_ok(_payload(), generated_at=four_days)))[0] is None


async def test_the_read_asks_for_the_generous_bound_because_only_the_payload_knows(monkeypatch):
    """Which TTL applies is a fact carried BY the payload, so the envelope read
    cannot pre-filter on the open-market bound without discarding settled banks
    before anything has looked at them."""
    _, _, calls = await _read(monkeypatch, _read_ok(_payload()))
    assert calls[0]["max_age_s"] == fill.SETTLED_CACHE_TTL_SECONDS
    assert fill.SETTLED_CACHE_TTL_SECONDS > fill.CACHE_TTL_SECONDS


@pytest.mark.parametrize("status", ["missing", "unavailable", "wrong_version", "checksum_mismatch", "stale"])
async def test_only_an_ok_envelope_is_served(monkeypatch, status):
    """A `wrong_version` read still CARRIES an envelope — serving it would draw
    last week's payload shape with this week's reader."""
    read = durable_state.EnvelopeRead(status=status, tier="durable", envelope=_envelope(_payload()))
    got, _, _ = await _read(monkeypatch, read)
    assert got is None


async def test_a_wedged_durable_tier_leaves_the_chart_exactly_as_cold_as_today(monkeypatch):
    """Fail-open is the whole contract: this tier may cost the chart its venue
    history, which is the status quo, and may never cost it the page."""
    got, _, _ = await _read(monkeypatch, None, raises=True)
    assert got is None


async def test_a_session_that_cannot_open_a_savepoint_is_survived(monkeypatch):
    got, session, _ = await _read(
        monkeypatch, _read_ok(_payload()), session=_Session(nested_raises=True)
    )
    assert got is None
    assert session.nested_rolled_back == 0


# ── the GUC that must not escape ────────────────────────────────────────────


async def test_the_read_rolls_its_savepoint_back_and_never_releases_it(monkeypatch):
    """🔴 MEASURED ON POSTGRES, BOTH WAYS, AND THIS IS THE ARM THAT HOLDS IT.

        outer SET LOCAL 31s → SAVEPOINT → inner SET LOCAL 2s → ROLLBACK  ⇒ 31s
        outer SET LOCAL 31s → SAVEPOINT → inner SET LOCAL 2s → RELEASE   ⇒  2s

    `read_snapshot` bounds itself with `SET LOCAL statement_timeout = 2000`, and
    `SET LOCAL` lives until the end of the TRANSACTION. `get_probability_timeline`
    runs its 30/90-day auto-extend query afterwards on this same session, and a
    2 s ceiling is exactly what that query can breach. `async with
    db.begin_nested()` RELEASES on a clean exit, i.e. it leaks — so the rollback
    is explicit, and it is asserted here rather than left to a reviewer's eye.
    """
    _, session, _ = await _read(monkeypatch, _read_ok(_payload()))
    assert session.nested_begun == 1
    assert session.nested_rolled_back == 1
    assert session.nested_released == 0, "RELEASE keeps the 2s bound — measured"


async def test_the_savepoint_is_rolled_back_even_when_the_read_fails(monkeypatch):
    """The leak does not care whether the read succeeded."""
    _, session, _ = await _read(monkeypatch, None, raises=True)
    assert session.nested_begun == 1 and session.nested_rolled_back == 1


# ── rehydration must not mint a new lifetime ────────────────────────────────


class _Redis:
    def __init__(self):
        self.sets = []

    def set(self, key, value, ex=None):
        self.sets.append({"key": key, "ex": ex})
        return True


def test_rehydration_writes_what_is_LEFT_of_the_declared_life():
    """A bank restored from Postgres is not a new bank. Re-caching it at the full
    36 h would hand it a fresh lifetime every time it were evicted and restored —
    an unbounded chain of extensions, each one individually reasonable."""
    rc = _Redis()
    assert fill.write_cached_history(1, _payload(), settled=False, rc=rc, ttl_s=1800) is True
    assert rc.sets[0]["ex"] == 1800


def test_an_expired_remainder_is_not_written_back_at_all():
    """`ex=0` deletes nothing and `ex=-1` raises; both would be a bug wearing a
    cache write. A bank with no life left simply does not go back."""
    rc = _Redis()
    assert fill.write_cached_history(1, _payload(), settled=False, rc=rc, ttl_s=0) is False
    assert fill.write_cached_history(1, _payload(), settled=False, rc=rc, ttl_s=-5) is False
    assert rc.sets == []


def test_an_ordinary_write_still_gets_the_full_declared_ttl():
    """The override is for one caller; the fill's own write is unchanged."""
    rc = _Redis()
    fill.write_cached_history(1, _payload(), settled=False, rc=rc)
    fill.write_cached_history(1, _payload(), settled=True, rc=rc)
    assert [s["ex"] for s in rc.sets] == [fill.CACHE_TTL_SECONDS, fill.SETTLED_CACHE_TTL_SECONDS]
    assert fill.declared_ttl_seconds(settled=False) == fill.CACHE_TTL_SECONDS
    assert fill.declared_ttl_seconds(settled=True) == fill.SETTLED_CACHE_TTL_SECONDS


# ── the serve path: two tiers, fast one first ───────────────────────────────


class _HitRedis(_Redis):
    """Redis still holding the bank."""

    def __init__(self, payload):
        super().__init__()
        import json as _json

        self._raw = _json.dumps(payload)

    def get(self, key):
        return self._raw


class _EvictedRedis(_Redis):
    """Redis after `allkeys-lru` took the bank — the #7563 state."""

    def get(self, key):
        return None


async def _serve(monkeypatch, *, rc, durable, db=object()):
    """`_load_generic_venue_history` with both tiers under control."""
    from app.routes import futures

    market, outcome = _market(), _outcome()
    calls = []

    async def _fake_durable(session, market_id, *, now=None):
        calls.append(market_id)
        return durable

    monkeypatch.setattr(futures, "_request_path_redis", lambda: rc)
    monkeypatch.setattr(fill, "read_durable_history", _fake_durable)

    venue = await futures._load_generic_venue_history(market, [outcome], set(), db)
    return venue, calls


async def test_an_evicted_bank_is_served_from_the_durable_tier(monkeypatch):
    """🔴 THE SHIP. #7563's measurement was that three markets proven warm at
    13:05Z read `cold` four hours later with the pre-fix numbers back. With the
    durable tier behind Redis, the same eviction costs the reader nothing.
    """
    payload = _payload()
    venue, calls = await _serve(monkeypatch, rc=_EvictedRedis(), durable=payload)

    assert venue.state == "warm", "an evicted bank must not read as cold"
    assert venue.tier == "durable"
    assert venue.rows, "the series itself must be served, not just the state"
    assert calls == [1]


async def test_a_warm_cache_never_pays_the_durable_tier(monkeypatch):
    """Redis is the fast tier and stays the fast tier: the durable read is only
    paid once the accelerator has already missed."""
    payload = _payload()
    venue, calls = await _serve(monkeypatch, rc=_HitRedis(payload), durable=payload)

    assert venue.state == "warm"
    assert venue.tier == "cache"
    assert calls == [], "the database must not be read when Redis answered"


async def test_both_tiers_missing_is_still_cold(monkeypatch):
    """The cold path is unchanged — the planner still gets its chance to refill."""
    venue, calls = await _serve(monkeypatch, rc=_EvictedRedis(), durable=None)
    assert venue.state == "cold" and venue.tier is None and calls == [1]


async def test_a_caller_with_no_session_degrades_to_the_old_behaviour(monkeypatch):
    """`db` is optional, so a future caller that has no session gets exactly the
    one-tier read that shipped in #7351 rather than an exception."""
    venue, calls = await _serve(monkeypatch, rc=_EvictedRedis(), durable=_payload(), db=None)
    assert venue.state == "cold" and calls == []


async def test_the_durable_payload_is_vetted_by_the_same_bindings(monkeypatch):
    """🔴 A DURABLE COPY IS NOT A TRUSTED COPY. #7351's three bindings — market,
    outcome id, exact venue contract — are what make a cached series safe to
    draw, and they are asked of whatever tier produced it. Here the row has been
    re-pointed at another contract since the bank was built."""
    payload = _payload()
    payload["market_external_id"] = "KXSOMETHINGELSE-26"
    venue, _ = await _serve(monkeypatch, rc=_EvictedRedis(), durable=payload)

    assert venue.state == "refused"
    assert venue.rows == {}


async def test_the_served_payload_names_the_tier_that_answered(monkeypatch):
    """Published so the ship is readable from production rather than inferred
    from a chart that looks identical either way."""
    venue, _ = await _serve(monkeypatch, rc=_EvictedRedis(), durable=_payload())
    block = venue.describe([])
    assert block["tier"] == "durable"
    assert block["state"] == "warm"


async def test_a_durable_hit_is_put_back_in_front_of_the_next_reader(monkeypatch):
    """With what is LEFT of its declared life, never a fresh 36 hours."""
    built = NOW - timedelta(hours=10)
    rc = _EvictedRedis()
    venue, _ = await _serve(monkeypatch, rc=rc, durable=_payload(built_at=built))

    assert venue.tier == "durable"
    assert len(rc.sets) == 1, "the bank should be re-cached for the next request"
    remaining = rc.sets[0]["ex"]
    assert 0 < remaining < fill.CACHE_TTL_SECONDS, (
        "a rehydrated bank given the full TTL would gain a fresh lifetime on "
        "every eviction — an unbounded chain of individually reasonable extensions"
    )


# ── the shared predicate #7736 and #7807 both write on ──────────────────────


def test_the_point_count_is_the_one_predicate_behind_both_durable_writes():
    assert gmh.payload_point_count(_payload()) == 3
    assert gmh.payload_point_count(_payload(points=[])) == 0
    assert gmh.payload_point_count({"outcomes": "not a dict"}) == 0
    assert gmh.payload_point_count(None) == 0


def test_the_marker_still_answers_exactly_as_it_did_before_the_extraction():
    """#7736's contract, re-asserted against the refactored predicate."""
    assert gmh.build_bank_marker(_payload(), now=NOW) == {
        "first_built_at": NOW.isoformat(), "points": 3, "outcomes": 1,
    }
    assert gmh.build_bank_marker(_payload(points=[]), now=NOW) is None
    assert gmh.build_bank_marker(None, now=NOW) is None


# ── the publish ORDER: Postgres first, or nothing at all (CERT-3247) ────────
#
# The ship is not "the bank is also written to Postgres" — it is "a bank that
# Redis can lose is recoverable". Staging the durable write and letting the task
# session commit it on its clean exit satisfied the first sentence and not the
# second: Redis went visible, the claim was released, and only THEN did Postgres
# commit. A worker death in that interval — or a commit that simply failed —
# left the Redis-only bank this issue exists to abolish, and the next eviction
# put the thin chart back. The task session wraps the whole batch, so the
# exposure was a whole run, not an instant.


class _OrderedSession:
    """A task session that records the ORDER of everything done to it."""

    def __init__(self, market, log, *, commit_raises=False):
        self.market = market
        self.log = log
        self.commits = 0
        self.rollbacks = 0
        self._commit_raises = commit_raises

    async def execute(self, *_a, **_k):
        # One fake answers both calls the fill makes of it: the market SELECT and
        # the marker's JSONB merge. The marker write is recorded because it must
        # ride the same transaction as the bank — if a future change let it land
        # separately, the two could disagree about whether a bank exists.
        self.log.append("pg-execute")
        market = self.market
        return SimpleNamespace(scalar_one_or_none=lambda: market)

    async def commit(self):
        self.commits += 1
        if self._commit_raises:
            self.log.append("pg-commit-FAILED")
            raise RuntimeError("could not serialize access")
        self.log.append("pg-commit")

    async def rollback(self):
        self.rollbacks += 1
        self.log.append("pg-rollback")


class _OrderedRedis:
    """Redis, recording writes and claim releases into the same log."""

    def __init__(self, log):
        self.log = log
        self.kv = {}

    def get(self, key):
        return self.kv.get(key)

    def set(self, key, value, ex=None):
        self.log.append("redis-set")
        self.kv[key] = value
        return True

    def delete(self, *keys):
        self.log.append("redis-claim-released")
        for key in keys:
            self.kv.pop(key, None)
        return 1


async def _run_fill(monkeypatch, *, log, commit_raises=False, durable_status=None,
                    points=None):
    """Drive the real `fill_generic_market_history` over recording doubles."""
    market = _market()
    market.outcomes = [_outcome()]
    market.market_metadata = {}
    # `stats` carries the keys `build_generic_history` really produces — the
    # fill reads `outcomes_built` out of them on both its exit paths, and a fake
    # missing one fails the test for a shape reason that looks nothing like the
    # ordering question being asked.
    payload = _payload(market, points=points, stats={
        "source": market.source,
        "outcomes_built": 0 if points == [] else 1,
        "outcomes_empty": 1 if points == [] else 0,
        "fetched_points": 0 if points == [] else 3,
    })

    async def _built(*_a, **_k):
        return payload

    monkeypatch.setattr(fill, "build_generic_history", _built)
    if durable_status is not None:
        async def _durable(*_a, **_k):
            return {"status": durable_status}
        monkeypatch.setattr(fill, "publish_durable_history", _durable)
    else:
        import app.services.durable_snapshots as ds

        async def _ok(_db, _envelope):
            return {"status": "ok"}
        monkeypatch.setattr(ds, "publish_snapshot_in_txn", _ok)

    session = _OrderedSession(market, log, commit_raises=commit_raises)
    rc = _OrderedRedis(log)
    result = await fill.fill_generic_market_history(session, market.id, rc=rc, now=NOW)
    return result, session, rc


async def test_postgres_has_the_bank_before_redis_publishes_it(monkeypatch):
    """The ordering the ship rests on, asserted as an ORDER and not as a set.

    Asserting only that both writes happened is what let the defect through:
    both DID happen, in the order that makes the durable copy worthless.
    """
    log = []
    result, session, rc = await _run_fill(monkeypatch, log=log)

    assert result["cached"] is True
    assert result["durable"] == "ok"
    assert session.commits == 1 and session.rollbacks == 0
    assert log.index("pg-commit") < log.index("redis-set"), (
        "Redis must never be able to hold a bank Postgres has not committed"
    )
    assert log.index("redis-set") < log.index("redis-claim-released"), (
        "the claim is the in-flight flag; releasing it before the write would "
        "invite a second fill to race this one"
    )


async def test_a_bank_postgres_could_not_keep_is_never_published_to_redis(monkeypatch):
    """Fail closed. The claim's TTL is the retry, so the market is re-filled."""
    log = []
    result, session, rc = await _run_fill(monkeypatch, log=log, commit_raises=True)

    assert result["cached"] is False
    assert result["durable"] == "commit_failed"
    assert result["bank_marker_written"] is False, (
        "the marker rode the rolled-back transaction; reporting it written "
        "would claim a row that does not exist"
    )
    assert "redis-set" not in log, (
        "publishing here is worse than not shipping #7807: the reader gets a "
        "series nothing can restore, wearing this ship's name"
    )
    assert "redis-claim-released" not in log, (
        "the claim must expire on its own TTL so the fill is retried"
    )
    assert session.rollbacks == 1, "the next market in the batch needs a clean transaction"


async def test_a_durable_write_that_errored_is_never_published_either(monkeypatch):
    """The other half of "fail closed on durable/commit failure"."""
    log = []
    result, session, rc = await _run_fill(monkeypatch, log=log, durable_status="error")

    assert result["durable"] == "error"
    assert result["cached"] is False
    assert "redis-set" not in log and "redis-claim-released" not in log
    assert session.commits == 0, (
        "the staging attempt already raised inside the transaction — there is "
        "nothing good in it to commit"
    )
    assert session.rollbacks == 1


async def test_an_empty_answer_still_reaches_the_bounded_negative_cache(monkeypatch):
    """The control that keeps fail-closed from becoming an outage amplifier.

    `skipped` means there was no bank to lose. If a pointless answer failed
    closed too, one venue outage would strip the `REFRESH_AFTER_SECONDS` throttle
    and every cold key would re-ask the venue immediately — a strictly worse
    failure than the one this repair fixes.
    """
    log = []
    result, session, rc = await _run_fill(monkeypatch, log=log, points=[])

    assert result["durable"] == "skipped"
    assert result["cached"] is True
    assert "redis-set" in log, "an empty answer is still cached, as it always was"
    assert "redis-claim-released" in log


async def test_an_empty_answer_survives_a_failed_commit_it_owed_nothing_to(monkeypatch):
    """Fail-closed is scoped to a bank that existed, not to every commit."""
    log = []
    result, session, rc = await _run_fill(
        monkeypatch, log=log, points=[], commit_raises=True
    )

    assert result["durable"] == "skipped"
    assert result["cached"] is True, (
        "nothing durable was owed, so a failed commit must not also cost the "
        "market its negative cache"
    )
