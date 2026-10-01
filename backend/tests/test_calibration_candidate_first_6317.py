"""#6317 — candidate-first rollover: q272 is built beside q271, never over it.

THE SHIP. Deploying q272 used to make the live q271 artifact ``wrong_version``
at every tier the instant the web took the sha, and publishing q272 first would
have replaced q271 in the one shared identity its readers were served from. The
page went dark either way. Now q272 publishes to its own namespace, the route
serves whatever a durable active-selection record names, and only a complete,
gate-passing q272 candidate can move that record, by compare-and-swap inside one
short transaction.

THE SEAMS ARE RECORDED, NOT MOCKED AWAY. One in-memory durable store (rows,
row-lock requests, CAS predicates applied as the SQL states them) and one
dict-backed Redis are shared by the producer and the route. The real
``_run_calibration_main_build``, the real ``public_calibration`` handler, the
real publish gate and the real activation transaction all run against them. No
production build and no census: the q272 population SQL is gated by the real-PG
field contract (``tests/integration/test_calibration_unpriced_field_winner_6317_pg.py``),
not here.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.responses import JSONResponse

from app.utils import calibration_publication_selection as sel
from app.utils import durable_state as ds
from app.utils import request_cache as rc

pytestmark = [pytest.mark.candidate_first]

Q271, Q272 = "q271", "q272"
Q271_NS, Q272_NS = sel.namespace_for(Q271), sel.namespace_for(Q272)
FP_Q271, FP_Q272 = "fp-q271-predicate", "fp-q272-predicate"


def _ago(**kw) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(**kw)).replace(microsecond=0)


def _payload(version: str, *, outcomes: int = 1_000_000, at: datetime, fp: str | None = None) -> dict:
    return {
        "buckets": [{"bucket_idx": 0, "n": outcomes, "winners": outcomes // 2}],
        "by_category": [{"category": "politics", "outcomes": outcomes}],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "total_outcomes": outcomes,
        "total_markets": outcomes // 4,
        "total_winners": outcomes // 2,
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applies_to": "all", "method": f"{version}-method"},
        "truth_evidence": {"contract_ok": True},
        "population_version": version,
        "population_predicate_fingerprint": fp or (FP_Q272 if version == Q272 else FP_Q271),
        "generated_at": at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Recorded durable store + Redis
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, row=None, scalar=None):
        self._row, self._scalar = row, scalar

    def mappings(self):
        return self

    def first(self):
        return self._row

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar


class Store:
    """``durable_state_snapshots`` as the SQL in ``durable_snapshots`` states it."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.locks: list[tuple[str, str]] = []
        self.writes: list[str] = []
        #: identity -> callable(store), fired once just before a write to it.
        self.before_write: dict = {}
        #: identity -> exception raised on the next locked read of it.
        self.fail_lock: dict = {}

    def put(self, identity, payload, *, schema_version, at=None, generation=None, complete=True):
        if at is None and isinstance(payload, dict):
            at = ds._parse_dt(payload.get("generated_at"))
        stamp = at or datetime.now(timezone.utc)
        self.rows[identity] = {
            "identity": identity,
            "schema_version": schema_version,
            "generation": generation if generation is not None else ds.generation_for(stamp),
            "generated_at": stamp,
            "payload": payload,
            "checksum": ds.checksum_payload(payload),
            "complete": complete,
            "source": "test",
        }
        return self.rows[identity]

    def put_artifact(self, payload):
        version = payload["population_version"]
        return self.put(sel.namespace_for(version).identity, payload, schema_version=version)

    def put_selection(self, selection: sel.ActiveSelection, *, at=None):
        env = sel.selection_envelope(selection, now=at or _ago(minutes=30))
        self.put(
            sel.SELECTION_IDENTITY, env.payload, schema_version=sel.SELECTION_SCHEMA,
            at=env.generated_at, generation=env.generation,
        )
        return env.generation

    def selection(self) -> sel.SelectionRead:
        row = self.rows.get(sel.SELECTION_IDENTITY)
        if row is None:
            return sel.SelectionRead(status=sel.READ_MISSING)
        return sel.classify_selection_envelope(
            ds.decode_envelope(row, tier="durable", expected_version=sel.SELECTION_SCHEMA,
                               max_age_s=float("inf"))
        )

    def session(self):
        return FakeSession(self)


class FakeSession:
    def __init__(self, store: Store):
        self.store = store
        self.staged: dict[str, dict] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.staged.clear()  # an un-committed transaction leaves nothing behind
        return False

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        if sql.startswith("SET LOCAL") or "advisory_unlock" in sql:
            return _Result()
        if "pg_try_advisory_lock" in sql:
            return _Result(scalar=True)
        if sql.startswith("SELECT identity"):
            ident = params["identity"]
            if "FOR UPDATE" in sql or "FOR SHARE" in sql:
                self.store.locks.append((ident, "update" if "FOR UPDATE" in sql else "share"))
                if ident in self.store.fail_lock:
                    raise self.store.fail_lock.pop(ident)
            row = self.staged.get(ident) or self.store.rows.get(ident)
            return _Result(row=dict(row) if row else None)
        if sql.startswith("INSERT INTO durable_state_snapshots"):
            ident = params["identity"]
            hook = self.store.before_write.pop(ident, None)
            if hook:
                hook(self.store)
            cur = self.store.rows.get(ident)
            if "DO NOTHING" in sql:
                ok = cur is None
            elif "= :expected_generation" in sql:
                ok = cur is not None and cur["generation"] == params["expected_generation"]
            else:
                ok = cur is None or cur["generation"] <= params["generation"]
            if not ok:
                return _Result(scalar=None)
            self.staged[ident] = {
                "identity": ident,
                "schema_version": params["schema_version"],
                "generation": params["generation"],
                "generated_at": params["generated_at"],
                "payload": json.loads(params["payload"]),
                "checksum": params["checksum"],
                "complete": params["complete"],
                "source": params["source"],
            }
            return _Result(scalar=params["generation"])
        raise AssertionError(f"unexpected SQL against the recorded store: {sql[:90]}")

    async def commit(self):
        for ident, row in self.staged.items():
            self.store.rows[ident] = row
            self.store.writes.append(ident)
        self.staged.clear()

    async def rollback(self):
        self.staged.clear()


class Redis:
    """One dict, a sync face for the producer and an async face for the route."""

    def __init__(self):
        self.data: dict[str, str] = {}
        self.sets: list[str] = []
        self.dead = False

    # producer (sync)
    def get(self, key):
        if self.dead:
            raise ConnectionError("redis down")
        return self.data.get(key)

    def set(self, key, value, ex=None):
        if self.dead:
            raise ConnectionError("redis down")
        self.data[key] = value
        self.sets.append(key)

    def async_face(self):
        outer = self

        class _Async:
            async def get(self, key):
                return outer.get(key)

        return _Async()


@pytest.fixture
def store(monkeypatch):
    s = Store()
    monkeypatch.setattr("app.tasks.base.get_task_session", s.session)
    return s


@pytest.fixture
def redis(monkeypatch):
    r = Redis()

    async def _shared():
        return r.async_face()

    monkeypatch.setattr(rc, "get_shared_async_redis", _shared)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: r)
    return r


@pytest.fixture(autouse=True)
def _fresh_route_process(monkeypatch):
    from app.routes import calibration

    async def _no_census(*, now):
        return None

    monkeypatch.setattr(calibration, "_read_published_coverage_census", _no_census)
    calibration._cache.update(data=None, timestamp=0, source=None, namespace=None)
    sel._reset_route_cache_for_tests()
    yield
    calibration._cache.update(data=None, timestamp=0, source=None, namespace=None)
    sel._reset_route_cache_for_tests()


def _new_request():
    """A later request: the selection's 60s process memo has expired."""
    sel._route_cache.update(selection=None, resolved_at=0.0, source=None)


async def _serve(store):
    from app.routes import calibration

    return await calibration.public_calibration(db=store.session())


def _bootstrap(store, redis, legacy_payload):
    row = store.put_artifact(legacy_payload)
    selection = sel.ActiveSelection(
        version=Q271, min_generation=row["generation"], origin=sel.ORIGIN_BOOTSTRAP,
        predicate_fingerprint=FP_Q271,
    )
    gen = store.put_selection(selection)
    return selection, gen


def _activate_in_store(store, redis, candidate_payload, *, floor=None):
    row = store.put_artifact(candidate_payload)
    selection = sel.ActiveSelection(
        version=Q272, min_generation=floor if floor is not None else row["generation"],
        origin=sel.ORIGIN_ACTIVATION, predicate_fingerprint=FP_Q272,
    )
    gen = store.put_selection(selection, at=_ago(minutes=1))
    return selection, gen


#: The key the draft once cached the selection under (6599014230). Nothing may
#: write or trust it now; the tests plant valid-looking copies there to prove so.
FORMER_SELECTION_REDIS_KEY = "bainluck:calibration:active_selection"


def _plant_selection_copy(redis, selection: sel.ActiveSelection, record_generation: int):
    body = dict(selection.to_payload(), record_generation=record_generation)
    redis.data[FORMER_SELECTION_REDIS_KEY] = json.dumps(body)


def _redis_artifact(redis, ns, payload, *, last_good=True, main=True):
    if last_good:
        redis.data[ns.last_good_key] = json.dumps(payload)
    if main:
        redis.data[ns.main_key] = json.dumps(payload)


# ---------------------------------------------------------------------------
# The key derivation and the record
# ---------------------------------------------------------------------------


def test_q271_keeps_the_shared_keys_and_q272_gets_its_own():
    assert Q271_NS.identity == "calibration:main"
    assert Q271_NS.main_key == "bainluck:calibration:main"
    assert Q272_NS.identity == "calibration:main:q272"
    assert {Q272_NS.identity, Q272_NS.main_key, Q272_NS.last_good_key}.isdisjoint(
        {Q271_NS.identity, Q271_NS.main_key, Q271_NS.last_good_key}
    )


def test_the_code_under_test_is_the_q272_rollover():
    from app.tasks import precompute_calibration as pc

    assert pc.CALIBRATION_POPULATION_VERSION == Q272
    assert pc.POPULATION_VERSION_CANDIDATE_FIRST == Q272
    assert sel.LEGACY_NAMESPACE_VERSION == pc.PREVIOUS_PUBLISHED_POPULATION_VERSION == Q271
    assert pc._DURABLE_IDENTITY == sel.LEGACY_IDENTITY


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(artifact_identity="calibration:main"),  # q272 pointed at q271's row
        lambda p: p.update(redis_main_key="bainluck:calibration:main"),
        lambda p: p.update(active_version="latest"),
        lambda p: p.update(min_generation=-1),
        lambda p: p.update(min_generation=True),
        lambda p: p.update(origin="default"),  # the in-memory default is never stored
    ],
)
def test_a_selection_record_that_points_anywhere_but_its_own_namespace_is_refused(mutate):
    good = sel.ActiveSelection(version=Q272, min_generation=5, origin=sel.ORIGIN_ACTIVATION).to_payload()
    assert sel.parse_selection(dict(good)) is not None
    bad = dict(good)
    mutate(bad)
    assert sel.parse_selection(bad) is None


# ---------------------------------------------------------------------------
# Route: what a reader is served through the rollover
# ---------------------------------------------------------------------------


async def test_the_reader_deploy_with_no_record_serves_q271_unchanged(store, redis, healthy_staged_bank):
    """Step 1 of the rollover: the q272 web deploy, before any q272 build."""
    legacy = _payload(Q271, at=_ago(minutes=20))
    store.put_artifact(legacy)
    _redis_artifact(redis, Q271_NS, legacy)

    out = await _serve(store)

    assert out["population_version"] == Q271
    assert out["generated_at"] == legacy["generated_at"]
    assert out["availability"] == "fresh"
    assert "cache" not in out
    assert sel._route_cache["source"] == "default_no_record"


async def test_a_pending_q272_build_never_leaks_and_q271_keeps_its_honest_age(store, redis, healthy_staged_bank):
    """q272 is staged and complete on its own keys; nothing activated it."""
    legacy = _payload(Q271, at=_ago(hours=3))
    _bootstrap(store, redis, legacy)
    _redis_artifact(redis, Q271_NS, legacy, main=False)  # main evicted, last_good survives
    staged = _payload(Q272, outcomes=980_000, at=_ago(minutes=5))
    store.put_artifact(staged)
    _redis_artifact(redis, Q272_NS, staged)

    out = await _serve(store)

    assert out["population_version"] == Q271
    assert out["cache"]["status"] == "stale"
    assert out["cache"]["generated_at"] == legacy["generated_at"]
    # Its OWN method disclosure, never a q272 one relabelled.
    assert out["mex_normalization"]["method"] == "q271-method"
    assert out["total_outcomes"] == 1_000_000


async def test_activation_switches_every_tier_to_q272_together(store, redis, healthy_staged_bank):
    legacy = _payload(Q271, at=_ago(minutes=40))
    _bootstrap(store, redis, legacy)
    _redis_artifact(redis, Q271_NS, legacy)
    cand = _payload(Q272, outcomes=980_000, at=_ago(minutes=10))
    _activate_in_store(store, redis, cand)
    _redis_artifact(redis, Q272_NS, cand)

    # main tier
    out = await _serve(store)
    assert out["population_version"] == Q272 and out["availability"] == "fresh"

    # last_good tier (fresh key evicted)
    from app.routes import calibration

    calibration._cache.update(data=None, source=None, namespace=None)
    del redis.data[Q272_NS.main_key]
    out = await _serve(store)
    assert out["population_version"] == Q272
    assert out["cache"]["reason"] == "main_key_absent"

    # durable tier: Redis gone entirely — durable selection AND durable artifact
    calibration._cache.update(data=None, source=None, namespace=None)
    rc._reset_last_good_for_tests()
    _new_request()
    redis.dead = True
    out = await _serve(store)
    assert out["population_version"] == Q272
    assert out["provenance"]["identity"] == Q272_NS.identity
    assert out["cache"]["reason"] == "redis_unavailable_durable"
    # The legacy q271 copies were still sitting there the whole time.
    assert json.loads(redis.data[Q271_NS.main_key])["population_version"] == Q271


async def test_a_q271_process_copy_cannot_seed_the_q272_page(store, redis, healthy_staged_bank):
    """Old process memory and last-good under q271 must not answer for q272."""
    from app.routes import calibration

    legacy = _payload(Q271, at=_ago(minutes=40))
    _bootstrap(store, redis, legacy)
    _redis_artifact(redis, Q271_NS, legacy)
    out = await _serve(store)
    assert out["population_version"] == Q271
    assert calibration._cache["namespace"] == Q271_NS.identity

    # Activation lands, but no q272 copy is readable anywhere yet.
    selection = sel.ActiveSelection(version=Q272, min_generation=1, origin=sel.ORIGIN_ACTIVATION)
    store.put_selection(selection, at=_ago(minutes=1))
    _new_request()

    out = await _serve(store)

    assert isinstance(out, JSONResponse) and out.status_code == 503
    assert json.loads(out.body)["reason"] == "no_trustworthy_snapshot"


async def test_a_later_q272_generation_advances_and_an_older_write_is_refused(store, redis, healthy_staged_bank):
    activated = _payload(Q272, at=_ago(hours=2))
    selection, _ = _activate_in_store(store, redis, activated)

    # The next hourly q272 build: newer than the floor, served fresh.
    later = _payload(Q272, outcomes=1_001_000, at=_ago(minutes=10))
    store.put_artifact(later)
    _redis_artifact(redis, Q272_NS, later)
    out = await _serve(store)
    assert out["total_outcomes"] == 1_001_000 and out["availability"] == "fresh"

    # A racing writer lands an artifact OLDER than the activated one on main.
    from app.routes import calibration

    calibration._cache.update(data=None, source=None, namespace=None)
    redis.data[Q272_NS.main_key] = json.dumps(_payload(Q272, outcomes=5, at=_ago(hours=5)))
    out = await _serve(store)
    assert out["total_outcomes"] == 1_001_000  # last_good, not the pre-floor write


async def test_an_unreadable_record_fails_closed_to_the_last_verified_selection(store, redis, healthy_staged_bank):
    cand = _payload(Q272, at=_ago(minutes=10))
    _activate_in_store(store, redis, cand)
    _redis_artifact(redis, Q272_NS, cand)
    assert (await _serve(store))["population_version"] == Q272

    # The durable record torn (checksum no longer matches).
    store.rows[sel.SELECTION_IDENTITY]["checksum"] = "torn"
    _new_request()
    selection, source = await sel.resolve_for_route(store.session())
    assert selection.version == Q272
    assert source == "last_verified_after_malformed"

    # A process that never verified one cannot know q272 activated: unknown is
    # not "no record", so it is neither the legacy default nor a candidate.
    sel._reset_route_cache_for_tests()
    selection, source = await sel.resolve_for_route(store.session())
    assert selection is None
    assert source == "unknown_after_malformed"


@pytest.mark.parametrize("status", [sel.READ_UNAVAILABLE, sel.READ_MALFORMED])
async def test_a_cold_process_that_cannot_read_the_selection_refuses_instead_of_serving_q271(
    store, redis, healthy_staged_bank, monkeypatch, status
):
    """Sol P1-2 (6599014230): durable q272 is active, the q271 copies are all
    still readable, and a restarted dyno's selection read times out. Serving
    q271 as ``fresh`` there is a guess presented as truth."""
    legacy = _payload(Q271, at=_ago(hours=2))
    _bootstrap(store, redis, legacy)
    _redis_artifact(redis, Q271_NS, legacy)
    store.put_artifact(legacy)
    cand = _payload(Q272, at=_ago(minutes=10))
    _activate_in_store(store, redis, cand)
    _redis_artifact(redis, Q272_NS, cand)

    async def _fails(db):
        return sel.SelectionRead(status=status, error="selection read timeout")

    real_read = sel.read_active_selection
    monkeypatch.setattr(sel, "read_active_selection", _fails)
    out = await _serve(store)

    assert isinstance(out, JSONResponse) and out.status_code == 503
    body = json.loads(out.body)
    assert body["reason"] == "active_selection_unavailable"
    # Cautious advice: no timing promised (CAL-P1191 keeps "shortly" for the budget).
    assert body["retry_after_s"] >= 900

    # Once the record reads, the same process serves the active q272.
    monkeypatch.setattr(sel, "read_active_selection", real_read)
    out = await _serve(store)
    assert out["population_version"] == Q272


async def test_positively_no_record_still_serves_the_legacy_incumbent(store, redis, healthy_staged_bank):
    """The other direction: only a CONFIRMED absence means 'no rollover yet'."""
    legacy = _payload(Q271, at=_ago(minutes=20))
    store.put_artifact(legacy)
    _redis_artifact(redis, Q271_NS, legacy)
    out = await _serve(store)
    assert out["population_version"] == Q271 and out["availability"] == "fresh"
    assert sel._route_cache["source"] == "default_no_record"


async def test_a_valid_redis_selection_copy_is_never_consulted(store, redis, healthy_staged_bank):
    """Sol P1-1 (6599014230): activation committed q272, then the process
    crashed before refreshing a Redis copy that still names q271. A cold
    reader must follow the durable record, not the copy."""
    legacy = _payload(Q271, at=_ago(hours=2))
    q271_sel, q271_gen = _bootstrap(store, redis, legacy)
    _redis_artifact(redis, Q271_NS, legacy)
    _plant_selection_copy(redis, q271_sel, q271_gen)
    cand = _payload(Q272, at=_ago(minutes=10))
    _activate_in_store(store, redis, cand)
    _redis_artifact(redis, Q272_NS, cand)

    out = await _serve(store)

    assert out["population_version"] == Q272, out.get("population_version")
    assert sel._route_cache["source"] == "durable"


async def test_a_process_that_verified_q272_never_regresses_to_an_older_record(store, redis, healthy_staged_bank):
    """Sol P1-1, the warm half: q272 verified, memo expires, and the next read
    returns an OLDER record (a lagging read, a restored row). Not news."""
    legacy = _payload(Q271, at=_ago(hours=2))
    q271_sel, _ = _bootstrap(store, redis, legacy)
    older_row = dict(store.rows[sel.SELECTION_IDENTITY])
    _redis_artifact(redis, Q271_NS, legacy)
    cand = _payload(Q272, at=_ago(minutes=10))
    _activate_in_store(store, redis, cand)
    _redis_artifact(redis, Q272_NS, cand)
    assert (await _serve(store))["population_version"] == Q272

    store.rows[sel.SELECTION_IDENTITY] = older_row
    _plant_selection_copy(redis, q271_sel, older_row["generation"])
    _new_request()
    from app.routes import calibration

    calibration._cache.update(data=None, source=None, namespace=None)
    out = await _serve(store)
    assert out["population_version"] == Q272
    assert sel._route_cache["source"] == "last_verified_newer_than_read"

    # A record that vanishes after this process verified one is not "no rollover".
    del store.rows[sel.SELECTION_IDENTITY]
    _new_request()
    selection, source = await sel.resolve_for_route(store.session())
    assert (selection.version, source) == (Q272, "last_verified_after_missing")


# ---------------------------------------------------------------------------
# Producer: bootstrap, stage, gate, activate
# ---------------------------------------------------------------------------


async def test_bootstrap_records_the_verified_incumbent_without_overwriting_a_racer(store):
    legacy = _payload(Q271, at=_ago(hours=1))
    row = store.put_artifact(legacy)

    read = await sel.resolve_for_build()
    assert read.ok and read.selection.version == Q271
    assert read.selection.origin == sel.ORIGIN_BOOTSTRAP
    assert read.selection.min_generation == row["generation"]

    # A second bootstrap racing an activation that already created the record.
    store2 = Store()
    store2.put_artifact(legacy)
    winner = sel.ActiveSelection(version=Q272, min_generation=7, origin=sel.ORIGIN_ACTIVATION)
    store2.before_write[sel.SELECTION_IDENTITY] = lambda s: s.put_selection(winner)
    import app.tasks.base as base

    orig = base.get_task_session
    base.get_task_session = store2.session
    try:
        read = await sel.resolve_for_build()
    finally:
        base.get_task_session = orig
    assert read.ok and read.selection.version == Q272, "a racer's record is never overwritten"


async def test_bootstrap_refuses_an_incumbent_it_cannot_verify(store):
    store.put(Q271_NS.identity, _payload(Q271, at=_ago(hours=1)), schema_version=Q271, complete=False)
    read = await sel.resolve_for_build()
    assert read.status == sel.READ_UNAVAILABLE
    assert sel.SELECTION_IDENTITY not in store.rows


async def _build(monkeypatch, response):
    from app.tasks import precompute_calibration as pc

    async def _compute(db, **_):
        return response

    async def _no_curve():
        return None

    monkeypatch.setattr(pc, "compute_calibration_payload", _compute)
    monkeypatch.setattr(pc, "read_bookmaker_curve_durable", _no_curve)
    monkeypatch.setattr(pc, "_file_publish_gate_rejection", lambda v, **k: {"action": "test"})
    return await pc._run_calibration_main_build()


async def test_a_gated_q272_build_stages_beside_q271_then_activates(monkeypatch, store, redis):
    legacy = _payload(Q271, at=_ago(minutes=30))
    store.put_artifact(legacy)
    _redis_artifact(redis, Q271_NS, legacy)
    legacy_row = dict(store.rows[Q271_NS.identity])
    legacy_redis = {k: redis.data[k] for k in (Q271_NS.main_key, Q271_NS.last_good_key)}

    cand = _payload(Q272, outcomes=980_000, at=_ago(minutes=1))
    summary = await _build(monkeypatch, cand)

    # The incumbent's row and keys were never written.
    assert store.rows[Q271_NS.identity] == legacy_row
    assert {k: redis.data[k] for k in legacy_redis} == legacy_redis
    assert Q271_NS.identity not in store.writes
    assert not {Q271_NS.main_key, Q271_NS.last_good_key} & set(redis.sets)
    # q272 landed in its own namespace, durable before Redis.
    staged = store.rows[Q272_NS.identity]
    assert staged["payload"]["population_version"] == Q272
    assert redis.sets.index(Q272_NS.last_good_key) >= 0
    # Activation committed: complete method, floor = the staged generation.
    active = store.selection()
    assert active.ok and active.selection.version == Q272
    assert active.selection.min_generation == staged["generation"]
    assert active.selection.predicate_fingerprint == FP_Q272
    assert active.selection.replaced["version"] == Q271
    # The incumbent was locked and re-read inside the activation transaction.
    assert (sel.SELECTION_IDENTITY, "update") in store.locks
    assert (Q271_NS.identity, "share") in store.locks
    assert (Q272_NS.identity, "share") in store.locks
    # Readers learn of it from durable alone: no Redis copy of the selection.
    assert not [k for k in redis.sets if "active_selection" in k]
    assert FORMER_SELECTION_REDIS_KEY not in redis.data
    pub = summary["publication"]
    assert pub["role"] == "candidate" and pub["live"] is True
    assert pub["activation"]["status"] == sel.ACTIVATED


async def test_the_activated_q272_is_what_the_route_then_serves(monkeypatch, store, redis, healthy_staged_bank):
    legacy = _payload(Q271, at=_ago(minutes=30))
    store.put_artifact(legacy)
    _redis_artifact(redis, Q271_NS, legacy)
    assert (await _serve(store))["population_version"] == Q271

    await _build(monkeypatch, _payload(Q272, outcomes=980_000, at=_ago(minutes=1)))
    _new_request()

    out = await _serve(store)
    assert out["population_version"] == Q272
    assert out["availability"] == "fresh"


async def test_a_refused_candidate_changes_nothing_readers_see(monkeypatch, store, redis):
    legacy = _payload(Q271, at=_ago(minutes=30))
    store.put_artifact(legacy)
    _redis_artifact(redis, Q271_NS, legacy)

    with pytest.raises(RuntimeError, match="publish gate rejected"):
        await _build(monkeypatch, _payload(Q272, outcomes=600_000, at=_ago(minutes=1)))

    assert Q272_NS.identity not in store.rows
    assert not {Q272_NS.main_key, Q272_NS.last_good_key} & set(redis.data)
    assert store.selection().selection.version == Q271


async def test_an_incomplete_candidate_is_never_staged(monkeypatch, store, redis):
    store.put_artifact(_payload(Q271, at=_ago(minutes=30)))
    empty = _payload(Q272, at=_ago(minutes=1))
    empty["buckets"] = []
    with pytest.raises(RuntimeError, match="unpublishable"):
        await _build(monkeypatch, empty)
    assert Q272_NS.identity not in store.rows
    assert sel.SELECTION_IDENTITY not in store.rows


async def test_an_unreadable_selection_publishes_nothing(monkeypatch, store, redis):
    legacy = _payload(Q271, at=_ago(minutes=30))
    _bootstrap(store, redis, legacy)
    store.rows[sel.SELECTION_IDENTITY]["checksum"] = "torn"
    with pytest.raises(RuntimeError, match="active selection malformed"):
        await _build(monkeypatch, _payload(Q272, outcomes=980_000, at=_ago(minutes=1)))
    assert Q272_NS.identity not in store.rows


async def test_a_lost_cas_race_reports_not_activated_and_keeps_the_winner(monkeypatch, store, redis):
    legacy = _payload(Q271, at=_ago(minutes=30))
    _bootstrap(store, redis, legacy)
    winner = sel.ActiveSelection(version=Q271, min_generation=42, origin=sel.ORIGIN_BOOTSTRAP)

    def _concurrent_commit(s):
        # Another activation committed between our locked read and our CAS (in
        # Postgres the FOR UPDATE makes this unreachable; the CAS is the backstop).
        prior = s.rows[sel.SELECTION_IDENTITY]["generation"]
        env = sel.selection_envelope(winner, now=_ago(seconds=1))
        s.put(sel.SELECTION_IDENTITY, env.payload, schema_version=sel.SELECTION_SCHEMA,
              at=env.generated_at, generation=prior + 1)

    store.before_write[sel.SELECTION_IDENTITY] = _concurrent_commit
    summary = await _build(monkeypatch, _payload(Q272, outcomes=980_000, at=_ago(minutes=1)))

    pub = summary["publication"]
    assert pub["activation"]["status"] == sel.NOT_ACTIVATED
    assert pub["activation"]["reason"] == "cas_miss"
    assert pub["live"] is False and pub["role"] == "candidate"
    assert store.selection().selection.min_generation == 42, "the winner stands"
    assert Q272_NS.identity in store.rows  # staged, not live


async def test_a_moved_baseline_invalidates_the_stale_gate_verdict(store):
    """The incumbent changed after the build was judged: re-gate under the lock."""
    from app.tasks import precompute_calibration as pc

    legacy = _payload(Q271, at=_ago(minutes=30))
    _bootstrap(store, Redis(), legacy)
    expected = store.selection()
    cand = _payload(Q272, outcomes=980_000, at=_ago(minutes=1))
    staged = store.put_artifact(cand)
    # A concurrent q271 publish moved the incumbent to a far larger population.
    store.put_artifact(_payload(Q271, outcomes=1_500_000, at=_ago(seconds=30)))

    out = await pc._activate_staged_candidate(
        response=cand, staged_generation=staged["generation"], active_read=expected
    )

    assert out["status"] == sel.NOT_ACTIVATED
    assert out["reason"] == "gate_refused_on_recheck"
    assert store.selection().selection.version == Q271


async def test_an_unusable_incumbent_is_never_treated_as_a_first_publish(store):
    """Re-gating against an incumbent row that is not a usable artifact refuses."""
    from app.tasks import precompute_calibration as pc

    _bootstrap(store, Redis(), _payload(Q271, at=_ago(minutes=30)))
    expected = store.selection()
    gutted = _payload(Q271, at=_ago(minutes=20))
    del gutted["by_category"]
    store.put_artifact(gutted)
    cand = _payload(Q272, outcomes=980_000, at=_ago(minutes=1))
    staged = store.put_artifact(cand)

    out = await pc._activate_staged_candidate(
        response=cand, staged_generation=staged["generation"], active_read=expected
    )

    assert out["reason"] == "gate_refused_on_recheck"
    assert "baseline_unreadable" in out["detail"]


def _bad_candidate(store, kind):
    cand = _payload(Q272, at=_ago(minutes=1))
    if kind == "missing":
        return cand, 123
    if kind == "wrong_version":
        row = store.put(Q272_NS.identity, cand, schema_version=Q271)
        return cand, row["generation"]
    if kind == "incomplete":
        row = store.put(Q272_NS.identity, cand, schema_version=Q272, complete=False)
        return cand, row["generation"]
    if kind == "moved":
        row = store.put_artifact(cand)
        return cand, row["generation"] - 1
    if kind == "predicate":
        row = store.put_artifact(_payload(Q272, at=_ago(minutes=1), fp="some-other-method"))
        return cand, row["generation"]
    raise AssertionError(kind)


@pytest.mark.parametrize(
    "kind, reason",
    [
        ("missing", "candidate_unreadable"),
        ("wrong_version", "candidate_unreadable"),
        ("incomplete", "candidate_unreadable"),
        ("moved", "candidate_moved"),
        ("predicate", "candidate_predicate_mismatch"),
    ],
)
async def test_a_candidate_that_is_not_the_staged_row_is_never_activated(store, kind, reason):
    _bootstrap(store, Redis(), _payload(Q271, at=_ago(minutes=30)))
    expected = store.selection()
    cand, gen = _bad_candidate(store, kind)

    out = await sel.activate_candidate(
        candidate_version=Q272, candidate_generation=gen, predicate_fingerprint=FP_Q272,
        expected=expected, recheck=lambda inc: (True, "ok"),
    )

    assert (out["status"], out["reason"]) == (sel.NOT_ACTIVATED, reason)
    assert store.selection().generation == expected.generation


async def test_a_crash_inside_the_activation_preserves_the_incumbent(store):
    _bootstrap(store, Redis(), _payload(Q271, at=_ago(minutes=30)))
    expected = store.selection()
    staged = store.put_artifact(_payload(Q272, at=_ago(minutes=1)))
    store.fail_lock[Q271_NS.identity] = OSError("connection reset mid-transaction")

    out = await sel.activate_candidate(
        candidate_version=Q272, candidate_generation=staged["generation"],
        predicate_fingerprint=FP_Q272, expected=expected, recheck=lambda inc: (True, "ok"),
    )

    assert (out["status"], out["reason"]) == (sel.NOT_ACTIVATED, "activation_error")
    assert store.selection().generation == expected.generation
    assert sel.SELECTION_IDENTITY not in store.writes


async def test_a_moved_selection_is_not_activated_over(store):
    _bootstrap(store, Redis(), _payload(Q271, at=_ago(minutes=30)))
    stale_expected = store.selection()
    store.put_selection(
        sel.ActiveSelection(version=Q271, min_generation=99, origin=sel.ORIGIN_BOOTSTRAP),
        at=_ago(minutes=2),
    )
    staged = store.put_artifact(_payload(Q272, at=_ago(minutes=1)))

    out = await sel.activate_candidate(
        candidate_version=Q272, candidate_generation=staged["generation"],
        predicate_fingerprint=FP_Q272, expected=stale_expected, recheck=lambda inc: (True, "ok"),
    )

    assert out["reason"] == "selection_moved"
    assert store.selection().selection.min_generation == 99


async def test_steady_state_q272_publishes_to_its_namespace_without_reactivating(monkeypatch, store, redis):
    first = _payload(Q272, at=_ago(hours=1))
    _activate_in_store(store, redis, first)
    _redis_artifact(redis, Q272_NS, first)
    before = store.selection()

    summary = await _build(monkeypatch, _payload(Q272, outcomes=1_002_000, at=_ago(minutes=1)))

    assert summary["publication"]["role"] == "active"
    assert summary["publication"]["activation"]["status"] == "not_attempted"
    assert summary["publication"]["live"] is True
    assert store.rows[Q272_NS.identity]["payload"]["total_outcomes"] == 1_002_000
    after = store.selection()
    assert after.generation == before.generation, "a routine publish never rewrites the record"
    assert Q271_NS.identity not in store.writes


async def test_a_cold_start_activates_the_first_candidate(monkeypatch, store, redis):
    """No record and no legacy artifact: the first build is the first publish."""
    from app.utils.calibration_durable_baseline import COLD_START, BaselineProbe

    monkeypatch.setattr(
        "app.utils.calibration_durable_baseline.probe_durable_baseline",
        lambda *a, **k: BaselineProbe(COLD_START, detail="test: empty store"),
    )
    summary = await _build(monkeypatch, _payload(Q272, at=_ago(minutes=1)))
    assert summary["publication"]["live"] is True
    assert store.selection().selection.version == Q272
    assert store.selection().selection.replaced is None


# ---------------------------------------------------------------------------
# The other readers of the published artifact follow the same selection
# ---------------------------------------------------------------------------


async def test_the_twin_grades_the_active_artifact_not_the_frozen_legacy_copy(monkeypatch, store, redis):
    from app.tasks import calibration_published_twin_worker as worker

    class _AsyncWithPing:
        async def get(self, key):
            return redis.get(key)

        async def ping(self):
            return True

    async def _shared():
        return _AsyncWithPing()

    monkeypatch.setattr(rc, "get_shared_async_redis", _shared)

    legacy = _payload(Q271, at=_ago(hours=3))
    _bootstrap(store, redis, legacy)
    _redis_artifact(redis, Q271_NS, legacy)
    payload, err, meta = await worker._read_published_payload()
    assert err is None and payload["population_version"] == Q271
    assert meta["payload_source"] == Q271_NS.main_key

    cand = _payload(Q272, at=_ago(minutes=5))
    _activate_in_store(store, redis, cand)
    _redis_artifact(redis, Q272_NS, cand)
    _plant_selection_copy(  # a lagging copy naming q271 is not read
        redis, sel.ActiveSelection(version=Q271, min_generation=1, origin="bootstrap"), 1
    )
    payload, err, meta = await worker._read_published_payload()
    assert payload["population_version"] == Q272
    assert meta["payload_source"] == Q272_NS.main_key
    assert meta["selection_source"] == "durable"

    # An unreadable record is reported, never graded as the legacy pair.
    store.rows[sel.SELECTION_IDENTITY]["checksum"] = "torn"
    payload, err, meta = await worker._read_published_payload()
    assert payload == {}
    assert err.startswith("published_read_failed: active selection unreadable")
    assert meta["payload_source"] is None


def test_the_publish_age_watchdog_reads_the_active_artifact():
    from app.tasks.data_quality_watchdog import CHECKS

    query = next(c for c in CHECKS if c["name"] == "calibration_publish_age")["query"]
    assert sel.SELECTION_IDENTITY in query
    assert "payload ->> 'artifact_identity'" in query
    # No record yet -> the legacy row, exactly as before.
    assert f"'{sel.LEGACY_IDENTITY}'" in query
    assert sel.ActiveSelection(version=Q272, min_generation=1, origin="activation").to_payload()[
        "artifact_identity"
    ] == Q272_NS.identity


async def test_the_admin_mce_view_reads_the_active_namespace_or_refuses(monkeypatch, store, redis):
    from fastapi import HTTPException

    from app.routes import admin_data_quality as adq

    monkeypatch.setattr(adq, "_check_admin_secret", lambda *a, **k: True)
    legacy = _payload(Q271, at=_ago(hours=3))
    _bootstrap(store, redis, legacy)
    _redis_artifact(redis, Q271_NS, legacy)
    cand = _payload(Q272, outcomes=980_000, at=_ago(minutes=5))
    _activate_in_store(store, redis, cand)
    _redis_artifact(redis, Q272_NS, cand)

    async def _mce():
        return await adq.calibration_mce_summary(request=None, secret=None, bust=False, threshold=5.0)

    out = await _mce()
    assert out is not None
    assert redis.data[Q272_NS.main_key]  # the key it was pointed at

    store.rows[sel.SELECTION_IDENTITY]["checksum"] = "torn"
    with pytest.raises(HTTPException) as refused:
        await _mce()
    assert refused.value.status_code == 503


async def test_out_of_request_readers_resolve_from_durable_only(store, redis):
    assert await sel.resolve_namespace_standalone() == (Q271_NS, "default_no_record")
    _plant_selection_copy(redis, sel.ActiveSelection(version=Q272, min_generation=1, origin="activation"), 9)
    assert await sel.resolve_namespace_standalone() == (Q271_NS, "default_no_record")
    _activate_in_store(store, redis, _payload(Q272, at=_ago(minutes=5)))
    assert await sel.resolve_namespace_standalone() == (Q272_NS, "durable")
    store.rows[sel.SELECTION_IDENTITY]["checksum"] = "torn"
    assert await sel.resolve_namespace_standalone() == (None, "unavailable_malformed")


def test_the_selection_module_has_no_redis_copy_to_lag():
    """The contract is structural: no reader can trust a copy that does not exist."""
    for gone in ("SELECTION_REDIS_KEY", "accelerate_selection", "active_namespace_sync",
                 "resolve_namespace_for_worker"):
        assert not hasattr(sel, gone), gone


# ---------------------------------------------------------------------------
# Process tiers obey the generation floor (Sol P2, 6599014230)
# ---------------------------------------------------------------------------


async def test_a_pre_floor_process_memo_is_not_served(store, redis, healthy_staged_bank):
    from app.routes import calibration

    cand = _payload(Q272, at=_ago(minutes=10))
    _activate_in_store(store, redis, cand)
    old = _payload(Q272, outcomes=555_555, at=_ago(hours=2))
    _redis_artifact(redis, Q272_NS, old, last_good=False)
    calibration._cache.update(
        data=old,
        source=calibration.main_artifact_fingerprint(redis.data[Q272_NS.main_key]),
        namespace=Q272_NS.identity,
    )

    out = await _serve(store)

    assert out["total_outcomes"] != 555_555
    assert out["total_outcomes"] == 1_000_000  # the activated artifact, from durable


@pytest.mark.parametrize("where", ["memo", "recalled_last_good"])
async def test_tier_four_refuses_a_pre_floor_process_copy(store, redis, healthy_staged_bank, where):
    from app.routes import calibration

    cand = _payload(Q272, at=_ago(minutes=10))
    _activate_in_store(store, redis, cand)
    del store.rows[Q272_NS.identity]  # nothing above tier 4 can answer
    old = _payload(Q272, outcomes=555_555, at=_ago(hours=2))
    if where == "memo":
        calibration._cache.update(data=old, source=None, namespace=Q272_NS.identity)
    else:
        rc.remember_last_good(Q272_NS.identity, old)

    out = await _serve(store)

    assert isinstance(out, JSONResponse) and out.status_code == 503, out
    assert json.loads(out.body)["reason"] == "no_trustworthy_snapshot"


async def test_tier_four_still_serves_a_later_same_version_process_copy(store, redis, healthy_staged_bank):
    """The floor is a minimum, not an equality: a newer q272 copy still serves."""
    from app.routes import calibration

    cand = _payload(Q272, at=_ago(minutes=30))
    _activate_in_store(store, redis, cand)
    del store.rows[Q272_NS.identity]
    later = _payload(Q272, outcomes=1_001_000, at=_ago(minutes=5))
    calibration._cache.update(data=later, source=None, namespace=Q272_NS.identity)

    out = await _serve(store)

    assert out["total_outcomes"] == 1_001_000
    assert out["cache"]["status"] == "stale"


async def test_a_pre_floor_memo_falls_through_to_an_admissible_recalled_copy(store, redis, healthy_staged_bank):
    """Refusing the stale memo must not also discard a good recalled q272 copy."""
    from app.routes import calibration

    cand = _payload(Q272, at=_ago(minutes=30))
    _activate_in_store(store, redis, cand)
    del store.rows[Q272_NS.identity]
    calibration._cache.update(
        data=_payload(Q272, outcomes=555_555, at=_ago(hours=2)), source=None,
        namespace=Q272_NS.identity,
    )
    rc.remember_last_good(Q272_NS.identity, _payload(Q272, outcomes=1_001_000, at=_ago(minutes=5)))

    out = await _serve(store)

    assert out["total_outcomes"] == 1_001_000


# ---------------------------------------------------------------------------
# Overlapping selection reads (Sol, f0b040f826): a slow read never wins late
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slow_status", [sel.READ_OK, sel.READ_MISSING, sel.READ_UNAVAILABLE, sel.READ_MALFORMED]
)
async def test_a_slow_read_that_resumes_after_q272_was_verified_does_not_regress_the_process(
    monkeypatch, slow_status
):
    """Request A's durable read is in flight (it saw q271, or no record, or
    failed). Request B reads committed q272 and verifies it. A resumes. Neither
    A's answer nor the next request's may be q271 — and an unreadable A must
    serve the q272 this process already verified, not a needless refusal."""
    import asyncio

    entered, release = asyncio.Event(), asyncio.Event()
    old = sel.ActiveSelection(Q271, 1, sel.ORIGIN_BOOTSTRAP, record_generation=100)
    new = sel.ActiveSelection(Q272, 2, sel.ORIGIN_ACTIVATION, record_generation=200)

    async def _read(db):
        if db == "slow":
            entered.set()
            await release.wait()
            if slow_status == sel.READ_OK:
                return sel.SelectionRead(status=sel.READ_OK, selection=old, generation=100)
            return sel.SelectionRead(status=slow_status)
        return sel.SelectionRead(status=sel.READ_OK, selection=new, generation=200)

    monkeypatch.setattr(sel, "read_active_selection", _read)
    slow = asyncio.create_task(sel.resolve_for_route("slow", now=1000.0))
    await entered.wait()
    fast = await sel.resolve_for_route("fast", now=1001.0)
    release.set()
    late = await slow
    following = await sel.resolve_for_route("fast", now=1002.0)

    assert [r[0].version for r in (fast, late, following)] == [Q272, Q272, Q272], (
        fast, late, following,
    )
    assert sel._last_verified["selection"].version == Q272
    assert sel._route_cache["selection"].version == Q272
