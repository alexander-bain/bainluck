"""#994 — the staged bank's DataGolf members ARE the canonical chain's rows.

THE READER SHIP. A reader taps a DataGolf Accuracy bucket and opens the exact
eligible examples behind the published curve on the first click, without
per-click full-cohort work.

WHAT ONLY POSTGRES CAN SAY. Stage B now emits, for each DataGolf group, the
records it counted (``string_agg`` in ``_main_futures_sql``). Whether those
records are exactly the rows the curve is built from is decided inside the
chain — #5355 opening timing, #762 voids, field normalization, the cohort flag
— and only a real server evaluates it. This drives the REAL staged loop
(``_run_staged_futures``: roster, plan, per-unit Stage B, fold, promotion,
finalize, ``_stage_examples_membership``) over seeded rows, with only the
cursor's durable read/write held in memory, and checks:

  1. MEMBER + VALUE EQUALITY: the staged membership is exactly the UNSCOPED
     canonical chain's DataGolf rows — same (market, outcome), same NUMERIC
     price text, same grade — per bucket and per moved arm, including the arms
     with no eligible rows. Count equality alone is not asserted as proof.
  2. Excluded rows (post-start opening, void) and other sources never appear.
  3. The partition does not matter: one unit or several, same membership.
  4. End to end on the same server: the membership published beside a
     matching payload answers the drill-in with NO population SQL — the only
     statements are the durable read and one primary-key lookup — and a grade
     corrected after publication is flagged rather than asserted.

Source evidence on a fixture: not production membership, not a production
cost, not reader acceptance at 390 px.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import event, text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #994 membership contract",
    ),
]

CUT_MID = 994301  # make-the-cut board: buckets 0..9, both arms, exclusions
FIELD_MID = 994302  # a mutually exclusive field: normalized prices
DEAD_MID = 994303  # every row excluded: contributes nothing
POLY_MID = 994304  # another source in the same buckets
ALL_MIDS = (CUT_MID, FIELD_MID, DEAD_MID, POLY_MID)
DG_MIDS = (CUT_MID, FIELD_MID, DEAD_MID)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
COMMENCE = NOW - timedelta(days=10)
PRE = COMMENCE - timedelta(days=3)
LATE_PRE = COMMENCE - timedelta(hours=1)
POST = COMMENCE + timedelta(days=1)

# (name, opening, calibration_probability, is_winner, resolution_source, snapshots)
CUT_BOARD = [
    ("c03", 0.03, 0.03, False, "leaderboard", [("datagolf_model", 0.03, PRE)]),
    ("c14", 0.14, 0.14, False, "leaderboard", [("datagolf_model", 0.14, PRE)]),
    ("c27m", 0.22, 0.27, True, "leaderboard",
     [("datagolf_model", 0.22, PRE), ("datagolf_model", 0.27, LATE_PRE)]),
    ("c41", 0.41, 0.41, True, "leaderboard", [("datagolf_model", 0.41, PRE)]),
    ("c58m", 0.50, 0.58, False, "leaderboard",
     [("datagolf_model", 0.50, PRE), ("datagolf_model", 0.58, LATE_PRE)]),
    ("c64", 0.64, 0.64, True, "leaderboard", [("datagolf_model", 0.64, PRE)]),
    ("c61", 0.61, 0.61, False, "leaderboard", [("datagolf_model", 0.61, PRE)]),
    ("c77m", 0.70, 0.77, True, "leaderboard",
     [("datagolf_model", 0.70, PRE), ("datagolf_model", 0.77, LATE_PRE)]),
    ("c91", 0.91, 0.91, True, "leaderboard", [("datagolf_model", 0.91, PRE)]),
    # #5355: first read after the start.
    ("post66", 0.66, 0.66, True, "leaderboard", [("datagolf_model", 0.66, POST)]),
    # #762: void.
    ("dnp63", 0.63, 0.63, False, "did_not_play", [("datagolf_model", 0.63, PRE)]),
]
EXCLUDED = {"post66", "dnp63"}
# Sums to 1.30 > MEX_NORMALIZE_THRESHOLD with one winner: a complete field.
FIELD_BOARD = [
    ("f50", 0.50, 0.50, True), ("f40", 0.40, 0.40, False),
    ("f30", 0.30, 0.30, False), ("f10", 0.10, 0.10, False),
]
DEAD_BOARD = [("d55", 0.55, 0.55, True), ("d35", 0.35, 0.35, False), ("d15", 0.15, 0.15, False)]
POLY_BOARD = [("p64", 0.64, True), ("p27", 0.27, False), ("p91", 0.91, True), ("p05", 0.05, False)]


def _oid(mid: int, idx: int) -> int:
    return mid * 1000 + idx


#: A field the shape classifier has PROVED exhaustive single-winner, so the
#: chain normalizes it (``exclusivity_proved_sql``) and its published prices are
#: long NUMERIC quotients — the case where a float round trip would differ.
FIELD_SHAPE = {"shape": {"exhaustive": True, "expected_winners": 1, "outcome_relation": "competitors"}}


async def _seed_market(session, mid, *, source, exclusive=False, market_type="participation", metadata=None):
    await session.execute(
        text(
            "INSERT INTO futures_markets (id, external_id, name, source, status, "
            "category, mutually_exclusive, market_type, llm_sport_category, volume, "
            "commence_time, resolution_date, market_metadata) VALUES "
            "(:id, :xid, :nm, :src, 'resolved', 'placement', :mx, :mt, 'golf', 100, "
            ":ct, :rd, CAST(:md AS jsonb))"
        ),
        {
            "id": mid, "xid": f"{source}:pga:994m{mid}", "nm": f"Members Open {mid}",
            "src": source, "mx": exclusive, "mt": market_type, "ct": COMMENCE,
            "rd": NOW - timedelta(days=7), "md": json.dumps(metadata or {}),
        },
    )


async def _seed_outcome(session, oid, mid, name, opening, cp, winner, res_src, snapshots):
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
            "opening_probability, calibration_probability, is_winner, "
            "resolution_source, volume) VALUES "
            "(:id, :mid, :xid, :nm, :op, :cp, :win, :rs, 10)"
        ),
        {"id": oid, "mid": mid, "xid": f"dgm_{oid}", "nm": name, "op": opening,
         "cp": cp, "win": winner, "rs": res_src},
    )
    for bookmaker, prob, captured_at in snapshots:
        await session.execute(
            text(
                "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
                "probability, reading_count, last_price, yes_bid, yes_ask, "
                "captured_at) VALUES (:oid, :bk, :p, 1, :p, :p, :p, :at)"
            ),
            {"oid": oid, "bk": bookmaker, "p": prob, "at": captured_at},
        )


async def _clear(session):
    for mid in ALL_MIDS:
        await session.execute(
            text(
                "DELETE FROM futures_odds_snapshots WHERE outcome_id IN "
                "(SELECT id FROM futures_outcomes WHERE market_id = :mid)"
            ),
            {"mid": mid},
        )
        await session.execute(text("DELETE FROM futures_outcomes WHERE market_id = :mid"), {"mid": mid})
        await session.execute(text("DELETE FROM futures_markets WHERE id = :mid"), {"mid": mid})
    await session.execute(
        text("DELETE FROM durable_state_snapshots WHERE identity IN (:a, :b)"),
        {"a": "calibration:main", "b": "calibration:examples_membership:datagolf"},
    )


@pytest.fixture
async def engine_and_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await _clear(s)
        await _seed_market(s, CUT_MID, source="datagolf")
        for idx, row in enumerate(CUT_BOARD):
            await _seed_outcome(s, _oid(CUT_MID, idx), CUT_MID, *row)
        await _seed_market(
            s, FIELD_MID, source="datagolf", exclusive=True, market_type="field",
            metadata=FIELD_SHAPE,
        )
        for idx, (name, op, cp, win) in enumerate(FIELD_BOARD):
            await _seed_outcome(
                s, _oid(FIELD_MID, idx), FIELD_MID, name, op, cp, win, "leaderboard",
                [("datagolf_model", op, PRE)],
            )
        await _seed_market(s, DEAD_MID, source="datagolf")
        for idx, (name, op, cp, win) in enumerate(DEAD_BOARD):
            await _seed_outcome(
                s, _oid(DEAD_MID, idx), DEAD_MID, name, op, cp, win, "leaderboard",
                [("datagolf_model", op, POST)],
            )
        await _seed_market(s, POLY_MID, source="polymarket")
        for idx, (name, p, win) in enumerate(POLY_BOARD):
            await _seed_outcome(
                s, _oid(POLY_MID, idx), POLY_MID, name, p, p, win, "api_settlement",
                [("polymarket", p, POST)],
            )
        await s.commit()
        yield engine, s
        await s.rollback()
        await _clear(s)
        await s.commit()
    await engine.dispose()


# ---------------------------------------------------------------------------
# The real staged loop over an in-memory cursor store
# ---------------------------------------------------------------------------
class _Ledger:
    def __init__(self):
        self.stages: dict[str, int] = {}
        self.gauges: dict[str, int] = {}

    def record_stage(self, name, duration_ms=0):
        self.stages[name] = self.stages.get(name, 0) + int(duration_ms)

    def record_gauge(self, name, value):
        self.gauges[name] = int(value)

    def remaining_ms(self, *, elapsed_ms=0):
        return 10_000_000


class _Stage:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Runner:
    def __init__(self):
        from app.tasks import precompute_calibration as pc

        self.ledger = _Ledger()
        self.population_version = pc.CALIBRATION_POPULATION_VERSION
        self.fingerprint = pc._main_input_fingerprint()
        self.owner = "pg-994"
        self.generation = 1
        self.rebuild_deferred = False
        self.outcome = {"published": False}

    def defer_rebuild(self):
        self.rebuild_deferred = True

    def stage(self, _name):
        return _Stage()

    def elapsed_ms(self):
        return 0

    async def commit(self, db):
        await db.commit()

    async def apply_statement_timeout(self, _db, _phase):
        return None

    def measured_unit_ms(self, _phase):
        return None

    async def apply_unit_statement_timeout(self, _db, _phase, *, unit_ms=None, deferred_rebuild=False):
        return None


async def _staged(session, monkeypatch, *, buckets):
    """Run the real loop to completion; return ``(merged, runner)``."""
    from app.tasks import calibration_main_build as mb
    from app.tasks import precompute_calibration as pc
    from app.utils.calibration_phase_ledger import FRESH
    from app.utils.calibration_staged_futures import (
        decode_staged_cursor_detailed,
        new_staged_cursor,
        stamp_served_at,
    )

    store = {"cursor": None}

    async def fake_load(**kw):
        if store["cursor"] is None:
            return new_staged_cursor(
                population_version=kw["population_version"],
                input_fingerprint=kw["input_fingerprint"],
                generation_fingerprint=kw["generation_fingerprint"],
                owner=kw["owner"],
                generation=kw["generation"],
            ), FRESH, "absent"
        return decode_staged_cursor_detailed(
            store["cursor"],
            expected_population_version=kw["population_version"],
            expected_input_fingerprint=kw["input_fingerprint"],
            expected_generation_fingerprint=kw["generation_fingerprint"],
            owner=kw["owner"], generation=kw["generation"], now=0.0,
        )

    async def fake_save(cursor, *, terminal, banks_a_unit=True):
        # Through JSON, exactly as the durable store would round-trip it.
        store["cursor"] = json.loads(
            json.dumps(stamp_served_at(cursor, now=1_700_000_000.0).as_payload(), default=str)
        )
        return True

    monkeypatch.setattr(mb, "load_staged_cursor", fake_load)
    monkeypatch.setattr(mb, "save_staged_cursor", fake_save)
    monkeypatch.setattr(mb, "staged_lease", lambda: 0.0)
    monkeypatch.setattr(mb, "STAGED_FUTURES_BUCKETS", buckets)
    runner = _Runner()
    merged = None
    for _ in range(4 * buckets + 4):
        merged = await pc._run_staged_futures(session, runner, pc._main_futures_sql)
        if merged is not None:
            break
    await session.rollback()
    assert merged is not None, "the staged loop never completed a generation"
    return merged, runner


async def _canonical(session) -> set[tuple]:
    """The UNSCOPED chain's DataGolf rows the curve is built from."""
    from app.tasks.precompute_calibration import _calibration_population_ctes

    rows = (await session.execute(text(
        "WITH " + _calibration_population_ctes() + """
        SELECT LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9) AS bucket,
            d.price_moved, d.market_id, d.outcome_id,
            d.adj_opening_probability::text AS price,
            CASE WHEN d.is_winner THEN '1' ELSE '0' END AS won
        FROM deduped d WHERE d.source = 'datagolf'
        """
    ))).all()
    await session.rollback()
    return {(r.bucket, r.price_moved, r.market_id, r.outcome_id, r.price, r.won) for r in rows}


def _staged_set(verified) -> set[tuple]:
    out = set()
    for key, cell in verified.items():
        bucket, _category, moved, _bundle = json.loads(key)
        for record in cell["members"].split(";"):
            mid, oid, price, won = record.split(",")
            out.add((bucket, moved, int(mid), int(oid), price, won))
    return out


async def test_the_staged_membership_is_the_canonical_chain(engine_and_session, monkeypatch):
    _engine, session = engine_and_session
    merged, runner = await _staged(session, monkeypatch, buckets=4)
    assert runner.examples_membership_reason == "complete", runner.examples_membership_reason
    staged = _staged_set(runner.examples_membership)
    canonical = await _canonical(session)
    ours = {row for row in canonical if row[2] in DG_MIDS}

    # Non-vacuity: both arms, several buckets, a normalized (long) price, and
    # the moved rows are really moved.
    assert {r[1] for r in ours} == {True, False}
    assert len({r[0] for r in ours}) >= 5
    assert any(len(r[4]) > 8 for r in ours if r[2] == FIELD_MID), sorted(ours)
    names = {r[3] for r in ours}
    assert _oid(CUT_MID, 2) in names and _oid(CUT_MID, 4) in names

    assert staged == canonical, (
        f"staged-only {sorted(staged - canonical)}; canonical-only {sorted(canonical - staged)}"
    )


async def test_every_bucket_and_arm_matches_including_the_empty_ones(engine_and_session, monkeypatch):
    from app.utils.calibration_examples_membership import (
        parse_published_membership,
        select_members,
    )

    _engine, session = engine_and_session
    merged, runner = await _staged(session, monkeypatch, buckets=4)
    canonical = await _canonical(session)
    artifact = _artifact(merged, runner)
    m, reason = parse_published_membership(artifact)
    assert reason == "complete"
    empty_arms = 0
    for bucket in range(10):
        for moved_only in (True, False):
            want = {
                (r[2], r[3], r[4], r[5]) for r in canonical
                if r[0] == bucket and (r[1] is True or not moved_only)
            }
            got = {tuple(rec.split(",")) for rec in select_members(m, bucket=bucket, moved_only=moved_only)}
            got = {(int(a), int(b), c, d) for a, b, c, d in got}
            assert got == want, (bucket, moved_only)
            empty_arms += not want
    assert empty_arms, "no arm was empty — the no-eligible-rows case went untested"


async def test_excluded_rows_and_other_sources_never_join(engine_and_session, monkeypatch):
    _engine, session = engine_and_session
    _merged, runner = await _staged(session, monkeypatch, buckets=4)
    oids = {r[3] for r in _staged_set(runner.examples_membership)}
    excluded = {_oid(CUT_MID, i) for i, row in enumerate(CUT_BOARD) if row[0] in EXCLUDED}
    assert not (oids & excluded)
    assert not {o for o in oids if o // 1000 in (DEAD_MID, POLY_MID)}


async def test_the_partition_does_not_change_the_membership(engine_and_session, monkeypatch):
    _engine, session = engine_and_session
    _m1, one = await _staged(session, monkeypatch, buckets=1)
    _m4, four = await _staged(session, monkeypatch, buckets=4)
    assert one.examples_membership_reason == four.examples_membership_reason == "complete"
    assert _staged_set(one.examples_membership) == _staged_set(four.examples_membership)


# ---------------------------------------------------------------------------
# End to end: publish beside a payload, answer the drill-in from it
# ---------------------------------------------------------------------------
def _response(merged) -> dict:
    agg: dict[tuple, list] = {}
    for r in merged:
        k = (r.bucket_idx, r.source, r.category, r.price_moved)
        acc = agg.setdefault(k, [0, 0])
        acc[0] += int(r.n)
        acc[1] += int(r.winners)
    return {
        "generated_at": NOW.isoformat(),
        "population_version": "q271",
        "population_predicate_fingerprint": "ea3ef49d2a15568e11d7d8e54240bfdb",
        "buckets": [
            {"bucket_idx": b, "source": s, "category": c, "price_moved": m, "n": n, "winners": w}
            for (b, s, c, m), (n, w) in agg.items()
        ],
    }


def _artifact(merged, runner):
    from app.utils.calibration_examples_membership import build_published_membership

    response = _response(merged)
    artifact, reason = build_published_membership(
        runner.examples_membership,
        response=response,
        payload_sha256=hashlib.sha256(json.dumps(response).encode()).hexdigest(),
        staged_unit_fingerprint=None,
    )
    assert reason == "complete", reason
    return artifact


async def test_the_drill_in_answers_from_the_published_membership(engine_and_session, monkeypatch):
    import app.utils.request_cache as rcache
    from app.routes import calibration as cal
    from app.services.durable_snapshots import publish_snapshot
    from app.utils.calibration_examples_membership import DURABLE_IDENTITY, PUBLISHED_SCHEMA
    from app.utils.durable_state import DurableEnvelope

    engine, session = engine_and_session
    merged, runner = await _staged(session, monkeypatch, buckets=4)
    response = _response(merged)
    artifact = _artifact(merged, runner)
    for identity, schema, payload in (
        (DURABLE_IDENTITY, PUBLISHED_SCHEMA, artifact),
        ("calibration:main", "q271", response),
    ):
        await publish_snapshot(session, DurableEnvelope.build(
            identity=identity, schema_version=schema, payload=payload,
            generated_at=NOW, source="pg-994",
        ))
    await session.commit()

    async def no_redis():
        raise ConnectionError("no redis in this rig")

    monkeypatch.setattr(rcache, "get_shared_async_redis", no_redis)
    cal._membership_cache.update(key=None, membership=None, reason=None, at=0.0)
    cal._examples_cache.clear()

    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        res = await cal.calibration_examples(
            db=session, source="datagolf", bucket=6, well_traded=0, limit=10,
            generation=NOW.isoformat(),
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)
    assert res["sampling"]["published_generation_membership"] == "verified", res["sampling"]
    assert not [s for s in statements if "virtual_market" in s or "deduped" in s], (
        "the first click ran population SQL"
    )
    canonical = await _canonical(session)
    want = {r[3] for r in canonical if r[0] == 6}
    got = {e["outcome_id"] for e in res["examples"]}
    assert got == want and got, (got, want)
    by = {e["outcome_id"]: e for e in res["examples"]}
    assert by[_oid(CUT_MID, 5)]["outcome_name"] == "c64"
    assert by[_oid(CUT_MID, 5)]["market_name"] == f"Members Open {CUT_MID}"
    assert by[_oid(CUT_MID, 5)]["result"] == "Yes"

    # A grade corrected after publication: flagged, never asserted as current.
    await session.execute(
        text("UPDATE futures_outcomes SET is_winner = true WHERE id = :id"),
        {"id": _oid(CUT_MID, 6)},
    )
    await session.commit()
    res = await cal.calibration_examples(
        db=session, source="datagolf", bucket=6, well_traded=0, limit=10, generation=None,
    )
    e = {x["outcome_id"]: x for x in res["examples"]}[_oid(CUT_MID, 6)]
    assert e["result"] == "No" and e["current_result"] == "Yes"
    assert e["grade_changed_since_publish"] is True
    cal._membership_cache.update(key=None, membership=None, reason=None, at=0.0)
