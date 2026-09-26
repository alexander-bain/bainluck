"""#8905 — the bookmaker curve survives Redis eviction, and never survives age.

What a reader saw: the accuracy page (/calibration) froze on an old curve for
hours, twice on 2026-09-26, because every hourly rebuild refused with
``bookmaker_curve_key_absent``. Redis (``allkeys-lru``) evicted
``bainluck:bookmaker_calibration`` under 3.5 h into its 24 h TTL, and the
writer, which runs on the main app, was torn down by a release before it could
replace it.

The fix has two halves and both are held down here:

1. **Writer** — lands the curve in ``durable_state_snapshots``
   (``calibration:bookmaker_curve``) BEFORE the ``setex``.
2. **Reader** — falls back to that row when the key is absent or Redis is
   unreachable, with the SAME 24 h bound and the SAME container/row refusals.

And one property that is not a feature but a cost avoided: the Phase 3 call
site lives in ``compute_calibration_payload``, a hashed root of the build
fingerprint, and it is not edited — a moved digest would discard the in-flight
bank and restart a multi-day convergence.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import precompute_calibration as pc
from app.utils.durable_state import DurableEnvelope, EnvelopeRead, decode_envelope
from tests.test_bookmaker_calibration_silence import _Row, _summary_for
from tests.test_calibration_bookmaker_reader_refusal_d21 import _Redis, _row

#: Spelled out, not imported: asserting ``pc.CONST in message`` checks the
#: constant against itself.
ABSENT = "bookmaker_curve_key_absent"
UNREADABLE = "bookmaker_curve_key_unreadable"
IDENTITY = "calibration:bookmaker_curve"
DAY_S = 86400


def _durable(payload, *, age_s=60.0, identity=IDENTITY, schema=None):
    """An ``EnvelopeRead`` as ``read_snapshot`` would return it.

    Built through the real ``decode_envelope`` with a max age WIDER than the
    reader's, so the age check under test is the reader's own at the moment of
    use — the producer's read happens minutes before Phase 3 and can be
    ``ok`` then and too old by the time it is used.
    """
    stamp = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    env = DurableEnvelope.build(
        identity=identity,
        schema_version=schema or pc.BOOKMAKER_CURVE_DURABLE_SCHEMA,
        payload=payload,
        generated_at=stamp,
        source="precompute_bookmaker_calibration",
    )
    raw = {
        "identity": env.identity,
        "schema_version": env.schema_version,
        "generation": env.generation,
        "generated_at": env.generated_at,
        "payload": env.payload,
        "checksum": env.checksum,
        "complete": True,
        "source": env.source,
    }
    return decode_envelope(raw, tier="durable", expected_version=None, max_age_s=10 * DAY_S)


# ---------------------------------------------------------------------------
# 1. The reader: eviction is survived.
# ---------------------------------------------------------------------------


def test_key_absent_and_durable_row_fresh_returns_the_rows():
    """THE fix. Before #8905 this exact input refused and froze the page."""
    durable = _durable([_row("basketball_nba"), _row("baseball_mlb", bucket_idx=7)])

    rows, _, degraded = pc.read_bookmaker_curve_rows(
        _Redis(None), refuse=True, durable=durable
    )

    assert degraded is None
    assert sorted((r.category, r.bucket_idx) for r in rows) == [
        ("baseball_mlb", 7),
        ("basketball_nba", 5),
    ]


def test_an_unreachable_redis_is_survived_too():
    """A dead store is the other half of what the Queue 298 survivor is for."""
    rows, _, degraded = pc.read_bookmaker_curve_rows(
        _Redis(raises=True), refuse=True, durable=_durable([_row()])
    )
    assert degraded is None and len(rows) == 1


def test_a_present_key_wins_over_the_durable_row():
    """The durable row is a survivor, not a second source: Redis is preferred
    whenever it answers, so the two can never be blended."""
    import json

    rows, _, _ = pc.read_bookmaker_curve_rows(
        _Redis(json.dumps([_row("hockey_nhl")])),
        refuse=True,
        durable=_durable([_row("basketball_nba")]),
    )
    assert [r.category for r in rows] == ["hockey_nhl"]


def test_the_durable_rows_still_drop_soccer():
    """The #1011 read-side exclusion applies to the survivor's rows too."""
    rows, soccer_n, _ = pc.read_bookmaker_curve_rows(
        _Redis(None),
        refuse=True,
        durable=_durable([_row("basketball_nba"), _row("soccer_epl", n=40, winners=10)]),
    )
    assert [r.category for r in rows] == ["basketball_nba"]
    assert soccer_n == 40


# ---------------------------------------------------------------------------
# 2. The reader: age is NOT survived.
# ---------------------------------------------------------------------------


def test_a_durable_row_older_than_24h_still_refuses_as_absent():
    """The age bound is the key's own TTL. A curve the writer has not replaced
    in 24 h is refused exactly as the expired key would have been."""
    durable = _durable([_row()], age_s=DAY_S + 1)
    assert durable.ok, "premise: the read itself was ok — the reader must judge age"

    with pytest.raises(RuntimeError) as err:
        pc.read_bookmaker_curve_rows(_Redis(None), refuse=True, durable=durable)

    message = str(err.value)
    assert message.startswith(ABSENT + ":")
    assert "stale" in message


def test_the_bound_is_exactly_the_ttl_not_a_rounder_number():
    """One second inside the bound serves; the constant is the TTL itself."""
    assert pc.BOOKMAKER_CURVE_MAX_AGE_S == DAY_S
    rows, _, degraded = pc.read_bookmaker_curve_rows(
        _Redis(None), refuse=True, durable=_durable([_row()], age_s=DAY_S - 5)
    )
    assert degraded is None and rows


def test_a_future_stamped_durable_row_is_refused_not_served_as_fresh():
    """Built as an ``ok`` read directly: ``decode_envelope`` already refuses a
    future stamp, so going through it would test that function, not this
    reader's own bound."""
    future = DurableEnvelope.build(
        identity=IDENTITY,
        schema_version=pc.BOOKMAKER_CURVE_DURABLE_SCHEMA,
        payload=[_row()],
        generated_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    with pytest.raises(RuntimeError, match=ABSENT):
        pc.read_bookmaker_curve_rows(
            _Redis(None), refuse=True,
            durable=EnvelopeRead(status="ok", tier="durable", envelope=future),
        )


@pytest.mark.parametrize(
    "durable,says",
    [
        (None, "no durable survivor was consulted"),
        (EnvelopeRead(status="missing", tier="durable"), "is missing"),
        (
            EnvelopeRead(status="unavailable", tier="durable",
                         error_class="OSError", error="db down"),
            "is unavailable (db down)",
        ),
        (EnvelopeRead(status="stale", tier="durable"), "is stale"),
    ],
)
def test_no_usable_survivor_refuses_by_the_old_name_and_says_why(durable, says):
    with pytest.raises(RuntimeError) as err:
        pc.read_bookmaker_curve_rows(_Redis(None), refuse=True, durable=durable)
    assert str(err.value).startswith(ABSENT + ":")
    assert says in str(err.value)


def test_unreachable_redis_with_no_survivor_keeps_its_own_reason_code():
    with pytest.raises(RuntimeError) as err:
        pc.read_bookmaker_curve_rows(
            _Redis(raises=True), refuse=True,
            durable=EnvelopeRead(status="missing", tier="durable"),
        )
    assert str(err.value).startswith(UNREADABLE + ":")


def test_a_row_under_another_identity_is_not_the_writers_row():
    with pytest.raises(RuntimeError, match=ABSENT):
        pc.read_bookmaker_curve_rows(
            _Redis(None), refuse=True,
            durable=_durable([_row()], identity="calibration:main"),
        )


def test_a_row_under_another_schema_is_not_the_writers_row():
    with pytest.raises(RuntimeError, match=ABSENT):
        pc.read_bookmaker_curve_rows(
            _Redis(None), refuse=True,
            durable=_durable([_row()], schema="bookmaker-curve/v0"),
        )


# ---------------------------------------------------------------------------
# 3. The reader: the survivor gets the same refusals, and names itself.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [{}, [], [1], [_row(source="kalshi")], [_row(n=None)]],
    ids=["dict", "empty", "not-dicts", "wrong-source", "null-n"],
)
def test_a_bad_durable_payload_is_refused_like_a_bad_key(payload):
    """Same contract, second place the bytes live — never a laxer one."""
    with pytest.raises(RuntimeError) as err:
        pc.read_bookmaker_curve_rows(
            _Redis(None), refuse=True, durable=_durable(payload)
        )
    message = str(err.value)
    assert message.startswith(UNREADABLE + ":")
    # It names the store the rows actually came from. Naming the Redis key
    # would send an operator to read the one store known to be empty.
    assert f"durable row {IDENTITY}" in message
    assert "bainluck:bookmaker_calibration" not in message


def test_the_serve_path_degrades_rather_than_raising_on_a_bad_survivor():
    rows, _, degraded = pc.read_bookmaker_curve_rows(
        _Redis(None), refuse=False, durable=_durable({})
    )
    assert rows == [] and degraded == UNREADABLE


# ---------------------------------------------------------------------------
# 4. The producer's hand-off.
# ---------------------------------------------------------------------------


def test_the_reader_takes_the_producers_read_from_the_context_variable():
    """The Phase 3 call site passes no ``durable`` — it cannot, see §5 — so the
    context variable IS the hand-off. Set: served. Reset: refused again."""
    token = pc._BOOKMAKER_CURVE_DURABLE.set(_durable([_row()]))
    try:
        rows, _, degraded = pc.read_bookmaker_curve_rows(_Redis(None), refuse=True)
        assert degraded is None and len(rows) == 1
    finally:
        pc._BOOKMAKER_CURVE_DURABLE.reset(token)

    with pytest.raises(RuntimeError, match=ABSENT):
        pc.read_bookmaker_curve_rows(_Redis(None), refuse=True)


def test_the_durable_read_never_raises(monkeypatch):
    async def _boom(*a, **k):
        raise OSError("could not open a session")

    monkeypatch.setattr(
        "app.services.durable_snapshots.read_snapshot_standalone", _boom
    )
    read = asyncio.run(pc.read_bookmaker_curve_durable())
    assert read.status == "unavailable" and not read.ok


def test_the_durable_read_asks_for_the_writers_identity_schema_and_ttl(monkeypatch):
    asked = {}

    async def _read(identity, **kw):
        asked.update(identity=identity, **kw)
        return EnvelopeRead(status="missing", tier="durable")

    monkeypatch.setattr(
        "app.services.durable_snapshots.read_snapshot_standalone", _read
    )
    asyncio.run(pc.read_bookmaker_curve_durable())
    assert asked == {
        "identity": IDENTITY,
        "expected_version": pc.BOOKMAKER_CURVE_DURABLE_SCHEMA,
        "max_age_s": DAY_S,
    }


def test_the_producer_sets_the_hand_off_around_the_build_and_resets_it():
    """Read from source: standing up the whole build to watch a context
    variable would test the stubs. The shape that matters is set -> compute ->
    reset-in-finally, so a failed build cannot leak its read into the next."""
    src = inspect.getsource(pc._run_calibration_main_build)
    set_at = src.index("_BOOKMAKER_CURVE_DURABLE.set(")
    compute_at = src.index("await compute_calibration_payload(db, runner=runner)")
    finally_at = src.index("finally:", compute_at)
    reset_at = src.index("_BOOKMAKER_CURVE_DURABLE.reset(durable_token)", finally_at)
    assert set_at < compute_at < finally_at < reset_at
    assert "await read_bookmaker_curve_durable()" in src[set_at:compute_at]


# ---------------------------------------------------------------------------
# 5. The cost avoided: the hashed root is untouched.
# ---------------------------------------------------------------------------


def test_the_hashed_call_site_is_not_where_the_fallback_lives():
    """``compute_calibration_payload`` is hashed by source into
    ``_main_input_fingerprint``. Routing the durable read through it would move
    the digest and discard the in-flight bank. If a later change wants it
    there, it must say so and price the lost bank — not arrive by accident."""
    src = inspect.getsource(pc.compute_calibration_payload)
    assert "durable" not in src.split("Query 5: Per-bookmaker calibration", 1)[1].split(
        "Query 6:", 1
    )[0]
    assert "_BOOKMAKER_CURVE_DURABLE" not in src


# ---------------------------------------------------------------------------
# 6. The writer: durable first, then Redis.
# ---------------------------------------------------------------------------


def test_the_writer_lands_the_durable_row_before_the_setex(monkeypatch):
    summary, redis = _summary_for([_Row(5, "basketball_nba")], monkeypatch=monkeypatch)

    assert redis.order == ["durable", "redis"]
    assert summary["terminal"] == "complete"
    assert summary["durable"] == "ok"
    assert summary["errors"] == []

    (envelope,) = redis.durable
    assert envelope.identity == IDENTITY
    assert envelope.schema_version == pc.BOOKMAKER_CURVE_DURABLE_SCHEMA
    assert envelope.source == "precompute_bookmaker_calibration"


def test_the_durable_payload_is_the_same_curve_the_key_gets(monkeypatch):
    """Byte-for-byte the rows Redis gets, so the survivor is not a variant."""
    import json

    _, redis = _summary_for(
        [_Row(5, "basketball_nba"), _Row(6, "hockey_nhl")], monkeypatch=monkeypatch
    )
    (envelope,) = redis.durable
    assert envelope.payload == json.loads(redis.written[2])


def test_the_writers_payload_is_one_the_reader_serves(monkeypatch):
    """End to end across the two halves: what the writer lands, the reader
    accepts through every refusal when the key is gone."""
    _, redis = _summary_for([_Row(5, "basketball_nba")], monkeypatch=monkeypatch)
    (envelope,) = redis.durable
    read = decode_envelope(
        {
            "identity": envelope.identity,
            "schema_version": envelope.schema_version,
            "generation": envelope.generation,
            "generated_at": envelope.generated_at,
            "payload": envelope.payload,
            "checksum": envelope.checksum,
            "complete": envelope.complete,
            "source": envelope.source,
        },
        tier="durable",
        expected_version=pc.BOOKMAKER_CURVE_DURABLE_SCHEMA,
        max_age_s=pc.BOOKMAKER_CURVE_MAX_AGE_S,
    )
    rows, _, degraded = pc.read_bookmaker_curve_rows(
        _Redis(None), refuse=True, durable=read
    )
    assert degraded is None and [r.category for r in rows] == ["basketball_nba"]


def test_a_failed_durable_write_still_writes_redis_and_reads_partial(monkeypatch):
    """Skipping Redis would turn a database blip into the absence this exists
    to prevent; calling it GREEN would hide that the next eviction is now
    unprotected. So: Redis written, error recorded, verdict PARTIAL."""
    from app.utils.task_verdict import COMPLETE, verdict_for

    summary, redis = _summary_for(
        [_Row(5, "basketball_nba")], monkeypatch=monkeypatch, durable_status="error"
    )
    assert redis.order == ["durable", "redis"]
    assert redis.written is not None
    assert summary["published"] is True
    assert summary["durable"] == "error"
    assert any("durable survivor NOT written" in e for e in summary["errors"])
    assert verdict_for("bookmaker_calibration", summary).verdict != COMPLETE


def test_a_superseded_durable_write_is_durable(monkeypatch):
    summary, _ = _summary_for(
        [_Row(5, "basketball_nba")], monkeypatch=monkeypatch,
        durable_status="superseded",
    )
    assert summary["errors"] == []


def test_a_run_that_writes_no_curve_writes_no_durable_row_either(monkeypatch):
    """Fail-closed arms stay closed: no_work publishes nothing anywhere."""
    summary, redis = _summary_for([], monkeypatch=monkeypatch)
    assert summary["terminal"] == "no_work"
    assert redis.durable == [] and redis.written is None
