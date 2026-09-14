"""CAL-P1216 — the serve-side consumer of the coverage-rung census.

The producer (CAL-P1214) walks the eleven rungs out of band and publishes a
complete, roster-stamped count. Nothing read it. These tests cover the thing
that reads it, and they are weighted deliberately: ONE test covers the happy
path, and the rest cover the refusals, because the refusals are what keep an
unvouched-for number off a public page.

The property that matters most is stated once here and asserted many times
below: **when this module declines, the served payload is the builder's own
object, unchanged.** Not "a payload with an unavailable census re-derived" —
the same bytes. That is what makes the route a serving tier rather than a
second builder, and it is the only reason a sixth serve-time key is safe.
"""

import json
import time

import pytest

from app.routes import calibration
from app.tasks import census_coverage_rungs as producer
from app.utils.calibration_coverage_bridge import (
    COVERAGE_BRIDGE_SCHEMA_VERSION,
    EXCLUSION_RUNGS,
    PLOTTED_RUNG,
    RUNG_KEYS,
    STATUS_UNAVAILABLE,
    build_coverage_census,
    unavailable_census,
)
from app.utils.calibration_coverage_consumer import (
    COVERAGE_CENSUS_FIELD,
    CursorIdentity,
    attach_coverage_census,
    coverage_census_for_payload,
    cursor_identity,
    parse_published,
)

DIGEST = "roster-digest-abc123"
VERSION = "q271"
GENERATION = 1785788100146

#: Every rung an int, plotted deliberately NOT round, so an assertion that
#: happens to read a default cannot pass by coincidence.
COUNTS = {key: (7 if key == PLOTTED_RUNG else 3) for key in RUNG_KEYS}
PLOTTED = COUNTS[PLOTTED_RUNG]
COVERAGE_TOTAL = PLOTTED + sum(COUNTS[k] for k in EXCLUSION_RUNGS)


def _published(**over):
    out = {
        "population_version": VERSION,
        "roster_digest": DIGEST,
        "counts": dict(COUNTS),
        "with_terminal_calibration_price": 5,
    }
    out.update(over)
    return out


def _cursor(**over):
    kwargs = {
        "population_version": VERSION,
        "roster_digest": DIGEST,
        "generation": GENERATION,
    }
    kwargs.update(over)
    return CursorIdentity(**kwargs)


def _payload(**over):
    """A served payload shaped like the builder's, census placeholder and all."""
    census = unavailable_census(
        "coverage census disabled", population_version=VERSION, generation=GENERATION
    )
    # The builder stamps an int generation; ``unavailable_census`` types it as a
    # str param, so pin the int the real producer writes rather than the hint.
    census["generation"] = GENERATION
    out = {
        "population_version": VERSION,
        "total_outcomes": 653_000,
        "truth_evidence": {"published_outcomes": PLOTTED},
        COVERAGE_CENSUS_FIELD: census,
    }
    out.update(over)
    return out


@pytest.fixture(autouse=True)
def _clear_route_memos():
    """Both module-level memos are per-dyno state and leak between tests.

    The census memo caches ``None`` as a real answer, so a suite that ran before
    this one leaves a populated, still-fresh cache and the next route test reads
    it instead of the store it just seeded. Cleared before AND after: this file
    must neither inherit nor export that state.
    """
    for cache in (calibration._coverage_cache, calibration._staged_cache):
        cache.clear()
    calibration._coverage_cache.update({"data": None, "timestamp": 0.0, "read": False})
    calibration._staged_cache.update({"data": None, "timestamp": 0.0})
    yield
    for cache in (calibration._coverage_cache, calibration._staged_cache):
        cache.clear()
    calibration._coverage_cache.update({"data": None, "timestamp": 0.0, "read": False})
    calibration._staged_cache.update({"data": None, "timestamp": 0.0})


# ---------------------------------------------------------------------------
# The identity read
# ---------------------------------------------------------------------------


def test_cursor_identity_reads_the_real_staged_cursor_payload():
    """Against the cursor's OWN serialiser, never a hand-built dict.

    A hand-built fixture here would assert that this module agrees with my idea
    of the cursor; building it through ``new_staged_cursor().as_payload()``
    asserts it agrees with the cursor. If either key is ever renamed this test
    fails, which is the entire point — a silently-None identity refuses every
    census forever and looks exactly like "no census published yet".
    """
    from app.utils.calibration_staged_futures import new_staged_cursor

    payload = new_staged_cursor(
        population_version=VERSION,
        input_fingerprint="fp",
        generation_fingerprint=DIGEST,
        owner="beat",
        generation=GENERATION,
    ).as_payload()

    identity = cursor_identity(payload)
    assert identity == CursorIdentity(
        population_version=VERSION, roster_digest=DIGEST, generation=GENERATION
    )


def test_the_walk_and_the_cursor_digest_the_roster_with_one_function():
    """The comparison is only meaningful if both sides use the same digest.

    ``plan_from_roster`` (the walk) and the staged cursor both stamp
    ``generation_fingerprint``. If one side ever grows its own digest the
    reconciliation does not break loudly — it silently never matches, and the
    census silently never attaches. Asserted by source, because the failure is
    an absence of behaviour and there is nothing to observe at runtime.
    """
    import inspect

    source = inspect.getsource(producer.plan_from_roster)
    assert "generation_fingerprint" in source
    assert "generation_fingerprint(roster)" in source


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not a mapping",
        {},
        {"generation": GENERATION},
        {"generation_fingerprint": "", "generation": GENERATION},
        {"generation_fingerprint": DIGEST},
        {"generation_fingerprint": DIGEST, "generation": None},
        {"generation_fingerprint": DIGEST, "generation": "12"},
        # A bool is an int in Python and would sail through an isinstance check.
        {"generation_fingerprint": DIGEST, "generation": True},
    ],
)
def test_cursor_identity_refuses_anything_it_cannot_read(payload):
    assert cursor_identity(payload) is None


# ---------------------------------------------------------------------------
# The refusals
# ---------------------------------------------------------------------------


def test_no_published_census_leaves_the_payload_alone():
    payload = _payload()
    assert coverage_census_for_payload(payload, published=None, cursor=_cursor()) is None
    assert attach_coverage_census(payload, published=None, cursor=_cursor()) is payload


def test_no_cursor_leaves_the_payload_alone():
    """An unreadable staged bank refuses the census rather than skipping the check."""
    payload = _payload()
    assert coverage_census_for_payload(payload, published=_published(), cursor=None) is None


@pytest.mark.parametrize(
    "published_over,cursor_over,payload_over",
    [
        # The census counted a different population version than the payload.
        ({"population_version": "q270"}, {}, {}),
        # The cursor is on a different version than the payload it served.
        ({}, {"population_version": "q270"}, {}),
        # The roster moved between the walk and now.
        ({"roster_digest": "moved"}, {}, {}),
        ({}, {"roster_digest": "moved"}, {}),
        # The payload is from an older build than the cursor — the stale,
        # last-good and durable tiers all land here, automatically.
        ({}, {"generation": GENERATION + 1}, {}),
    ],
)
def test_a_broken_identity_chain_refuses(published_over, cursor_over, payload_over):
    payload = _payload(**payload_over)
    assert (
        coverage_census_for_payload(
            payload, published=_published(**published_over), cursor=_cursor(**cursor_over)
        )
        is None
    )


def test_a_payload_with_no_generation_refuses():
    """``None`` never compares equal to a generation — it refuses, not matches."""
    payload = _payload()
    payload[COVERAGE_CENSUS_FIELD] = dict(payload[COVERAGE_CENSUS_FIELD])
    payload[COVERAGE_CENSUS_FIELD].pop("generation")
    assert coverage_census_for_payload(payload, published=_published(), cursor=_cursor()) is None


def test_a_payload_with_no_census_key_is_not_this_modules_case():
    """``ensure_census`` owns the absent key; this module owns the placeholder."""
    payload = _payload()
    payload.pop(COVERAGE_CENSUS_FIELD)
    assert coverage_census_for_payload(payload, published=_published(), cursor=_cursor()) is None


def test_a_measured_census_is_never_overwritten():
    """If ``COVERAGE_CENSUS_ENABLED`` is ever flipped, the builder wins.

    Two producers of one key must have a stated winner, and the one that counted
    inside the curve's own statement is closer to the curve. Without this the
    serve path would quietly outrank an in-band census with an out-of-band one.
    """
    builders = build_coverage_census(
        rung_counts=dict(COUNTS),
        sportsbook_curve_legs=11,
        published_curve_observations=PLOTTED + 11,
        published_outcomes_crosscheck=PLOTTED,
        population_version=VERSION,
        generation=str(GENERATION),
    )
    # The int the real builder stamps. Without this the census is refused by the
    # generation check instead of the one under test, and the test passes for
    # the wrong reason — measured by mutation: dropping the placeholder guard
    # left it green until this line existed.
    builders["generation"] = GENERATION
    payload = _payload(**{COVERAGE_CENSUS_FIELD: builders})
    assert coverage_census_for_payload(payload, published=_published(), cursor=_cursor()) is None


# ---------------------------------------------------------------------------
# The one happy path
# ---------------------------------------------------------------------------


def test_a_reconciling_census_is_attached_with_its_counted_rungs():
    census = coverage_census_for_payload(
        _payload(), published=_published(), cursor=_cursor()
    )
    assert census is not None
    assert census["schema_version"] == COVERAGE_BRIDGE_SCHEMA_VERSION
    assert census["population_version"] == VERSION

    by_key = {cell["key"]: cell["outcomes"] for cell in census["coverage_bridge"]["rungs"]}
    assert by_key == COUNTS

    # Bridge A — the ship. Every rung known, so the partition reconciles and the
    # coverage total is the sum of the rungs rather than a separate claim.
    assert census["coverage_bridge"]["reconciles"] is True
    assert census["coverage_bridge"]["residual"] == 0
    assert census["units"]["outcomes_with_calibration_coverage"]["value"] == COVERAGE_TOTAL
    assert (
        census["units"]["outcomes_with_calibration_coverage"][
            "with_terminal_calibration_price"
        ]
        == 5
    )


def test_the_observation_bridge_is_unknown_and_is_not_reconciled_by_subtraction():
    """The anti-test for the tempting one-liner.

    ``sportsbook_curve_legs`` is not in the served payload, and it is recoverable
    by arithmetic: ``total_outcomes - plotted``. Doing that would make the
    observation bridge reconcile with a residual of zero EVERY time, because the
    number would be defined as whatever makes it reconcile — a check that can
    never fail, reported as a check that passed. The builder counts that number
    directly from the curve's own rows for exactly this reason.

    So the honest serve-time answer is UNKNOWN, and this test is what stops a
    later reader from "fixing" it.
    """
    census = coverage_census_for_payload(
        _payload(), published=_published(), cursor=_cursor()
    )
    bridge = census["observation_bridge"]
    assert bridge["sportsbook_curve_legs"] is None
    assert bridge["reconciles"] is False
    assert bridge["residual"] is None
    assert "OBSERVATION_BRIDGE_UNKNOWN" in census["invariants"]["violations"]
    # ...and the census says so out loud rather than claiming completeness.
    assert census["status"] != "complete"


def test_the_hinge_is_still_checked_against_the_payloads_own_count():
    """One bridge being unwired must not switch the other checks off."""
    ok = coverage_census_for_payload(_payload(), published=_published(), cursor=_cursor())
    assert "PLOTTED_HINGE_DIVERGES" not in ok["invariants"]["violations"]
    assert "PLOTTED_HINGE_UNCHECKED" not in ok["invariants"]["violations"]

    diverged = coverage_census_for_payload(
        _payload(truth_evidence={"published_outcomes": PLOTTED + 1}),
        published=_published(),
        cursor=_cursor(),
    )
    assert "PLOTTED_HINGE_DIVERGES" in diverged["invariants"]["violations"]


def test_the_reachability_tier_says_why_it_is_absent():
    """Unmeasured with a reason, never an unexplained ``None`` (gotcha #53)."""
    census = coverage_census_for_payload(
        _payload(), published=_published(), cursor=_cursor()
    )
    reach = census["reachability_bridge"]
    blob = json.dumps(reach)
    assert "not re-read at serve time" in blob


# ---------------------------------------------------------------------------
# attach: copy-on-write, and never the reason the page is down
# ---------------------------------------------------------------------------


def test_attach_does_not_mutate_its_input_and_changes_exactly_one_key():
    payload = _payload()
    before = json.dumps(payload, sort_keys=True)
    out = attach_coverage_census(payload, published=_published(), cursor=_cursor())

    assert json.dumps(payload, sort_keys=True) == before, "input was mutated"
    assert out is not payload
    assert out[COVERAGE_CENSUS_FIELD] != payload[COVERAGE_CENSUS_FIELD]
    assert {k: v for k, v in out.items() if k != COVERAGE_CENSUS_FIELD} == {
        k: v for k, v in payload.items() if k != COVERAGE_CENSUS_FIELD
    }


def test_attach_returns_the_same_object_when_it_declines():
    """Identity, not equality: the serving tier hands back what it was given."""
    payload = _payload()
    assert attach_coverage_census(payload, published=None, cursor=_cursor()) is payload


def test_attach_never_raises_into_the_serve_path(monkeypatch):
    """A supporting census must not be able to break the payload it supports."""
    import app.utils.calibration_coverage_consumer as consumer

    def _boom(*_a, **_k):
        raise RuntimeError("census exploded")

    monkeypatch.setattr(consumer, "build_coverage_census", _boom)
    payload = _payload()
    assert attach_coverage_census(payload, published=_published(), cursor=_cursor()) is payload


# ---------------------------------------------------------------------------
# The bytes on the wire
# ---------------------------------------------------------------------------


def test_parse_published_round_trips_what_publish_actually_wrote():
    """Against the producer's real ``publish``, not a hand-written blob."""
    written = {}

    class _Redis:
        def setex(self, key, _ttl, val):
            written[key] = val

    state = producer.new_state(
        population_version=VERSION, roster_digest=DIGEST, buckets=1, total_units=1
    )
    state = producer.absorb_unit(
        state,
        unit_key="u1",
        row={
            **{producer.coverage_bridge_column(k): COUNTS[k] for k in RUNG_KEYS},
            producer.TOTAL_COLUMN: COVERAGE_TOTAL,
            producer.TERMINAL_PRICE_COLUMN: 5,
        },
    )
    state = producer.absorb_global(state, row={})
    assert producer.publish(_Redis(), state) is True

    parsed = parse_published(written[producer.PUBLISHED_KEY])
    assert parsed is not None
    assert parsed["roster_digest"] == DIGEST
    assert parsed["counts"] == COUNTS


@pytest.mark.parametrize("raw", [None, b"", "not json", json.dumps({"schema": "other"})])
def test_parse_published_refuses_bytes_it_cannot_stand_behind(raw):
    assert parse_published(raw) is None


# ---------------------------------------------------------------------------
# Through the route
# ---------------------------------------------------------------------------


def _seed_store(monkeypatch, main_payload, census_raw):
    from app.utils import request_cache as rc

    raw = json.dumps(main_payload, default=str)

    class _Store:
        async def get(self, key):
            if key == "bainluck:calibration:main":
                return raw
            if key == producer.PUBLISHED_KEY:
                return census_raw
            return None

    async def _getter():
        return _Store()

    monkeypatch.setattr(rc, "get_shared_async_redis", _getter)
    calibration._cache = {
        "data": main_payload,
        "timestamp": time.time(),
        "source": calibration.main_artifact_fingerprint(raw),
    }


def _seed_cursor(identity):
    calibration._staged_cache["data"] = {"measured": True, "units_drifted": 0}
    calibration._staged_cache["timestamp"] = time.time()
    calibration._staged_cache["identity"] = identity


class _FakeDB:
    async def execute(self, *_a, **_k):  # pragma: no cover - never reached
        raise AssertionError("the serve path must not touch the database here")


@pytest.mark.asyncio
async def test_a_failed_cursor_read_clears_the_previous_identity():
    """The one stale input that could attach a census to the WRONG build.

    The identity is memoised beside the disclosure. If a later read fails and
    leaves the previous generation's identity in place, the census keeps
    reconciling against a build that is no longer current — and a wrong number
    presented confidently is the failure this whole chain exists to prevent.
    A failed read must therefore be indistinguishable from a cold start.
    """
    calibration._staged_cache["identity"] = _cursor()
    calibration._staged_cache["data"] = None

    class _RaisingDB:
        async def execute(self, *_a, **_k):
            raise RuntimeError("cursor read failed")

    disclosure = await calibration._read_staged_disclosure(_RaisingDB(), now=time.time())

    assert disclosure["measured"] is False
    assert calibration._staged_cache["identity"] is None


@pytest.mark.asyncio
async def test_the_route_serves_the_builders_census_untouched_when_none_is_published(
    monkeypatch,
):
    """The steady state today, and the one that must stay byte-identical."""
    payload = _payload()
    _seed_store(monkeypatch, payload, census_raw=None)
    _seed_cursor(_cursor())

    routed = await calibration.public_calibration(db=_FakeDB())

    assert routed[COVERAGE_CENSUS_FIELD] == payload[COVERAGE_CENSUS_FIELD]
    assert routed[COVERAGE_CENSUS_FIELD]["status"] == STATUS_UNAVAILABLE


@pytest.mark.asyncio
async def test_the_route_attaches_a_reconciling_census_end_to_end(monkeypatch):
    """Redis bytes in, counted rungs out, over the real serve path."""
    payload = _payload()
    census_raw = json.dumps(
        {
            "schema": producer.COVERAGE_RUNG_SCHEMA,
            "population_version": VERSION,
            "roster_digest": DIGEST,
            "counts": dict(COUNTS),
            "coverage_total": COVERAGE_TOTAL,
            "with_terminal_calibration_price": 5,
        }
    )
    _seed_store(monkeypatch, payload, census_raw=census_raw)
    _seed_cursor(_cursor())

    routed = await calibration.public_calibration(db=_FakeDB())

    served = routed[COVERAGE_CENSUS_FIELD]
    assert served["status"] != STATUS_UNAVAILABLE
    by_key = {cell["key"]: cell["outcomes"] for cell in served["coverage_bridge"]["rungs"]}
    assert by_key == COUNTS


@pytest.mark.asyncio
async def test_the_route_refuses_a_census_from_a_different_roster(monkeypatch):
    """The end-to-end form of the refusal: right shape, wrong population."""
    payload = _payload()
    census_raw = json.dumps(
        {
            "schema": producer.COVERAGE_RUNG_SCHEMA,
            "population_version": VERSION,
            "roster_digest": "some-other-roster",
            "counts": dict(COUNTS),
            "coverage_total": COVERAGE_TOTAL,
            "with_terminal_calibration_price": 5,
        }
    )
    _seed_store(monkeypatch, payload, census_raw=census_raw)
    _seed_cursor(_cursor())

    routed = await calibration.public_calibration(db=_FakeDB())

    assert routed[COVERAGE_CENSUS_FIELD] == payload[COVERAGE_CENSUS_FIELD]
    assert routed[COVERAGE_CENSUS_FIELD]["status"] == STATUS_UNAVAILABLE
