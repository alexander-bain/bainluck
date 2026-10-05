"""#10520 — the one-row keeper-anchor repair, judged as units and EXECUTED on real Postgres.

Two halves.

* The UNIT half has no database and runs everywhere: admission refuses every
  identity change by name, the CLI accepts only the one keeper, the target fence
  holds, and a tampered plan is refused before anything connects.
* The POSTGRES half (``SEARCH_TEST_DATABASE_URL``) runs the SHIPPED tool's
  ``run_preflight`` / ``run_apply`` / ``run_restore`` against the real schema in
  a throwaway Postgres schema. It is the half that can see what a stub cannot:
  the unique index arbitrating a conflict, ``ON CONFLICT DO NOTHING`` declining
  to repoint, a real rollback, a lock wait bounded by ``lock_timeout``, and
  ``find_event_by_anchor`` — the registry's own Step 2 — changing its answer.

The arm the file exists for is
``test_apply_writes_one_anchor_and_step2_then_resolves_the_incoming_id``: before
the write, Step 2 refuses the incoming id as stale (#8278 — the column's own id
is not anchored); after it, Step 2 resolves the incoming id to the keeper. Both
answers come from ``app.services.anchor_channel`` unchanged.

Fixture values are the retained #10520 evidence. They are test data, not
production eligibility: only the attended preflight reads production.

The Postgres half is NOT named by a ci.yml step (this file is outside
``tests/integration/``), so in CI it skips; its evidence is the local run quoted
in the offer.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_TOOL = _SCRIPTS / "repair_10520_keeper_current_anchor.py"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location("repair_10520_unit", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


r = _load()

COMMENCE = datetime(2026, 10, 7, 0, 30, tzinfo=timezone.utc)


def _keeper(**over):
    row = {"id": r.KEEPER_ID, **r.IDENTITY, "commence_time": COMMENCE, "status": "scheduled"}
    row.update(over)
    return row


def _anchor(name, event_id=r.KEEPER_ID, aid=None, **over):
    key = r.ANCHOR_KEYS[name]
    default_ids = {"incoming": r.INCOMING_ANCHOR_ID, "statpal": r.STATPAL_ANCHOR_ID}
    row = {"id": aid or default_ids.get(name, 9001), "event_id": event_id,
           "source": key.source, "source_id": key.source_id, "id_kind": key.id_kind}
    row.update(over)
    return row


def _anchors(**over):
    out = {"current": None, "incoming": _anchor("incoming"), "statpal": _anchor("statpal"), "espn": None}
    out.update(over)
    return out


# ═══ unit half ════════════════════════════════════════════════════════════════

def test_keys_are_the_channels_own_keys():
    # The retained ids, spelled once each and never beside a provider name (a
    # quoted hex next to "odds_api" reads to gitleaks as a credential).
    assert r.CURRENT_ODDS_ID == "1d13bd275c7b67b77bea8ff4d03850cc"
    assert r.INCOMING_ODDS_ID == "0d9ff865c4599c72a746da08260279b3"
    assert (r.CURRENT_KEY.source, r.CURRENT_KEY.source_id, r.CURRENT_KEY.id_kind) == (
        "odds_api", r.CURRENT_ODDS_ID, "game")
    assert (r.INCOMING_KEY.source, r.INCOMING_KEY.source_id) == ("odds_api", r.INCOMING_ODDS_ID)
    # D55 / #4393: the stamper wrote `soccer:`, never `soccer_usa_mls:`.
    assert r.STATPAL_KEY.source_id == "soccer:9163448"
    assert (r.ESPN_KEY.source, r.ESPN_KEY.source_id) == ("espn", "761660")


def test_admit_the_retained_state_is_a_candidate():
    body = r.admit(_keeper(), r.SPORT_KEY, _anchors())
    assert body["state"] == "CANDIDATE"
    assert body["write"] == {"table": "event_provider_anchors", "key": r.key_dict(r.CURRENT_KEY),
                             "event_id": r.KEEPER_ID}
    assert body["anchors"]["current"] is None
    assert body["anchors"]["incoming"] == {"id": 187393, "event_id": r.KEEPER_ID}


@pytest.mark.parametrize("column,value", [
    ("sport_id", 1327), ("home_team_id", 17), ("away_team_id", 24),
    ("home_team_name", "Chicago Fire FC"), ("away_team_name", "Vancouver Whitecaps"),
    ("external_id", "ffffffffffffffffffffffffffffffff"), ("external_id", None),
    ("espn_id", "761661"), ("espn_id", None), ("statpal_fixture_id", "9163449"),
    ("commence_time", datetime(2026, 10, 7, 0, 45, tzinfo=timezone.utc)),
])
def test_admit_refuses_every_changed_identity_column(column, value):
    with pytest.raises(r.Refused) as exc:
        r.admit(_keeper(**{column: value}), r.SPORT_KEY, _anchors())
    assert exc.value.reason == f"keeper_identity_changed:{column}"


def test_admit_does_not_fence_status():
    assert r.admit(_keeper(status="live"), r.SPORT_KEY, _anchors())["state"] == "CANDIDATE"


def test_admit_refuses_missing_keeper_and_wrong_sport_key():
    with pytest.raises(r.Refused, match="keeper_missing"):
        r.admit(None, r.SPORT_KEY, _anchors())
    with pytest.raises(r.Refused, match="keeper_sport_key_changed"):
        r.admit(_keeper(), "soccer_epl", _anchors())


@pytest.mark.parametrize("anchors,reason", [
    (_anchors(incoming=None), "incoming_game_anchor_absent"),
    (_anchors(incoming=_anchor("incoming", event_id=r.TWIN_ID)), "incoming_game_anchor_not_keepers"),
    (_anchors(incoming=_anchor("incoming", aid=5)), "incoming_game_anchor_row_changed"),
    (_anchors(statpal=None), "official_statpal_anchor_absent"),
    (_anchors(statpal=_anchor("statpal", event_id=r.TWIN_ID)), "official_statpal_anchor_not_keepers"),
    (_anchors(espn=_anchor("espn", event_id=r.TWIN_ID)), "official_espn_anchor_owned_elsewhere"),
    (_anchors(current=_anchor("current", event_id=r.TWIN_ID)), "current_key_owned_elsewhere"),
    (_anchors(incoming=_anchor("incoming", id_kind="market")), "anchor_read_not_exact_key:incoming"),
])
def test_admit_refuses_each_anchor_shape(anchors, reason):
    with pytest.raises(r.Refused) as exc:
        r.admit(_keeper(), r.SPORT_KEY, anchors)
    assert exc.value.reason == reason


def test_admit_keepers_own_current_anchor_is_not_needed():
    body = r.admit(_keeper(), r.SPORT_KEY, _anchors(current=_anchor("current")))
    assert body["state"] == r.NOT_NEEDED
    body = r.admit(_keeper(), r.SPORT_KEY, _anchors(espn=_anchor("espn")))
    assert body["state"] == "CANDIDATE"  # a keeper-owned ESPN anchor is corroboration


def test_plan_drift_sees_anchors_and_identity_not_status():
    plan = r.admit(_keeper(), r.SPORT_KEY, _anchors())
    assert r.plan_drift(plan, r.admit(_keeper(status="live"), r.SPORT_KEY, _anchors())) == []
    moved = r.admit(_keeper(), r.SPORT_KEY, _anchors(espn=_anchor("espn")))
    assert r.plan_drift(plan, moved) == ["anchors"]


def test_created_row_must_carry_this_invocations_context():
    cc = r.claim_context_for("inv-a", "addr")
    row = {**r.key_dict(r.CURRENT_KEY), "event_id": r.KEEPER_ID, "claim_context": cc, "id": 1}
    assert r.created_row_matches(row, cc) == []
    assert r.created_row_matches(row, r.claim_context_for("inv-b", "addr")) == ["claim_context"]
    assert r.created_row_matches({**row, "event_id": r.TWIN_ID}, cc) == ["event_id"]
    assert r.created_row_matches(None, cc) == ["row_missing"]


@pytest.mark.parametrize("argv", [
    ["--only", "15324922"], ["--only", "14969919", "--only", "14969919"],
    ["--only", "14969919", "--apply", "--plan", "/p", "--plan-hash", "h"],
    ["--only", "14969919", "--restore", "--backup", "/b", "--backup-hash", "h", "--plan", "/p"],
])
def test_cli_accepts_only_the_one_keeper_and_its_mode_args(argv):
    with pytest.raises(SystemExit) as exc:
        r.parse(argv)
    assert exc.value.code == 2


def test_target_fence_refuses_before_connecting(capsys):
    rc = asyncio.run(r.main(["--only", "14969919", "--plan-out", "/tmp/x.json"],
                            env={"HEROKU_APP_NAME": "bainluck-heavy"}))
    assert rc == r.EXIT_REFUSED
    assert json.loads(capsys.readouterr().out)["reason"] == "target_app_refused"


def test_tampered_plan_is_refused(tmp_path):
    body = r.admit(_keeper(), r.SPORT_KEY, _anchors())
    plan = r.write_artifact(str(tmp_path / "plan.json"), r.PLAN_SCHEMA, body, "plan")
    assert r.load_artifact(plan["path"], plan["sha256"], r.PLAN_SCHEMA, "plan")["state"] == "CANDIDATE"
    with pytest.raises(r.Refused, match="plan_hash_mismatch"):
        r.load_artifact(plan["path"], "0" * 64, r.PLAN_SCHEMA, "plan")
    with pytest.raises(r.Refused, match="plan_wrong_schema"):
        r.load_artifact(plan["path"], plan["sha256"], r.BACKUP_SCHEMA, "plan")


# ═══ Postgres half ════════════════════════════════════════════════════════════

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
needs_postgres = pytest.mark.skipif(
    not DB_URL, reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10520 repair gate"
)

SCHEMA = "r10520_gate"
OTHER_SPORT_ID = 1327


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+asyncpg://", 1)


def _closure(tables):
    """The named tables plus everything they reference, so ``create_all`` can build
    them alone — never the whole metadata (one PG15-only index lives elsewhere)."""
    seen, stack = {}, list(tables)
    while stack:
        t = stack.pop()
        if t.name in seen:
            continue
        seen[t.name] = t
        stack.extend(fk.column.table for fk in t.foreign_keys)
    return list(seen.values())


@pytest.fixture
async def db():
    """A throwaway schema holding exactly the tables the tool touches."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401
    from app.services.database import Base

    admin = create_async_engine(_asyncpg_url(DB_URL))
    async with admin.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
    engine = create_async_engine(
        _asyncpg_url(DB_URL), connect_args={"server_settings": {"search_path": SCHEMA}}
    )
    tables = _closure([Base.metadata.tables[n] for n in ("events", "event_provider_anchors")])
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _seed(maker)
        yield maker
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await admin.dispose()


async def _seed(maker):
    """Keeper, twin and the keeper's two retained anchors, as q10520a/b/c read them."""
    from app.models.models import Event, EventProviderAnchor, Sport, Team

    async with maker() as s:
        s.add_all([Sport(id=1326, key="soccer_usa_mls", name="MLS", group="Soccer", active=True),
                   Sport(id=OTHER_SPORT_ID, key="soccer_epl", name="EPL", group="Soccer", active=True)])
        await s.flush()
        s.add_all([Team(id=16, sport_id=1326, name="Chicago Fire"),
                   Team(id=23, sport_id=1326, name="Vancouver Whitecaps FC")])
        await s.flush()
        common = dict(sport_id=1326, home_team_id=16, away_team_id=23, home_team_name="Chicago Fire",
                      away_team_name="Vancouver Whitecaps FC", commence_time=COMMENCE, status="scheduled",
                      statpal_fixture_id="9163448")
        s.add_all([Event(id=r.KEEPER_ID, external_id=r.CURRENT_ODDS_ID, espn_id="761660", **common),
                   Event(id=r.TWIN_ID, external_id=r.INCOMING_ODDS_ID, espn_id=None, **common)])
        await s.flush()
        s.add_all([
            EventProviderAnchor(id=r.INCOMING_ANCHOR_ID, event_id=r.KEEPER_ID, source="odds_api",
                                source_id=r.INCOMING_ODDS_ID, id_kind="game",
                                claim_context={"source": "odds_api", "schedule_derived": False}),
            EventProviderAnchor(id=r.STATPAL_ANCHOR_ID, event_id=r.KEEPER_ID, source="statpal",
                                source_id="soccer:9163448", id_kind="game",
                                claim_context={"written_by": "stamp_v1_statpal_fixtures"}),
        ])
        await s.commit()


async def _exec(maker, sql, **params):
    from sqlalchemy import text

    async with maker() as s:
        await s.execute(text(sql), params)
        await s.commit()


async def _anchors_table(maker):
    from sqlalchemy import text

    async with maker() as s:
        rows = (await s.execute(text(
            "SELECT id, event_id, source, source_id, id_kind, claim_context "
            "FROM event_provider_anchors ORDER BY source, source_id, id_kind"))).mappings().all()
    return [dict(x) for x in rows]


async def _step2(maker):
    from app.services.anchor_channel import find_event_by_anchor

    async with maker() as s:
        return await find_event_by_anchor(s, r.INCOMING_KEY, expected_sport_id=1326)


async def _plan(maker, tmp_path, name="plan.json"):
    out = await r.run_preflight(maker, plan_out=str(tmp_path / name))
    assert out["state"] == r.PLANNED, out
    return out["plan"]


async def _apply(maker, tmp_path, plan, name="backup.json", **kw):
    return await r.run_apply(maker, plan_path=plan["path"], plan_hash=plan["sha256"],
                             backup_out=str(tmp_path / name), **kw)


def _current_rows(table):
    return [a for a in table if (a["source"], a["source_id"], a["id_kind"]) ==
            ("odds_api", r.CURRENT_ODDS_ID, "game")]


@needs_postgres
async def test_apply_writes_one_anchor_and_step2_then_resolves_the_incoming_id(db, tmp_path):
    before = await _anchors_table(db)
    assert await _step2(db) is None  # BEFORE: #8278 refuses — the column's own id is unanchored

    plan = await _plan(db, tmp_path)
    out = await _apply(db, tmp_path, plan)
    assert out["state"] == r.APPLIED, out
    assert out["counts"]["anchor_rows_written"] == 1
    assert out["step2_resolves_incoming_to"] == r.KEEPER_ID
    assert out["incoming_after"] == {"id": r.INCOMING_ANCHOR_ID, "event_id": r.KEEPER_ID}
    assert r.exit_code(out) == r.EXIT_OK

    after = await _anchors_table(db)
    assert [a for a in after if a not in before] == _current_rows(after)
    assert [a for a in before if a not in after] == []  # nothing else moved or vanished
    (created,) = _current_rows(after)
    assert created["event_id"] == r.KEEPER_ID
    assert created["claim_context"]["written_by"] == r.TOOL
    assert await _step2(db) == r.KEEPER_ID  # AFTER: the same registry read rescues


@needs_postgres
async def test_repeated_execution_is_an_idempotent_no_op(db, tmp_path):
    plan = await _plan(db, tmp_path)
    assert (await _apply(db, tmp_path, plan))["state"] == r.APPLIED
    table = await _anchors_table(db)

    again = await _apply(db, tmp_path, plan, name="backup2.json")
    assert again["state"] == r.NOT_NEEDED and again["counts"]["anchor_rows_written"] == 0
    assert r.exit_code(again) == r.EXIT_OK
    assert (await r.run_preflight(db, plan_out=str(tmp_path / "plan2.json")))["state"] == r.NOT_NEEDED
    assert await _anchors_table(db) == table


@needs_postgres
async def test_another_owner_of_the_current_key_refuses_and_is_never_repointed(db, tmp_path):
    plan = await _plan(db, tmp_path)
    await _exec(db, "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind) "
                    "VALUES (:e, 'odds_api', :s, 'game')", e=r.TWIN_ID, s=r.CURRENT_ODDS_ID)

    pre = await r.run_preflight(db, plan_out=str(tmp_path / "plan2.json"))
    assert pre["state"] == r.REFUSED and pre["reason"] == "current_key_owned_elsewhere"
    out = await _apply(db, tmp_path, plan)
    assert out["state"] == r.REFUSED and out["reason"] == "current_key_owned_elsewhere"
    (row,) = _current_rows(await _anchors_table(db))
    assert row["event_id"] == r.TWIN_ID


@needs_postgres
async def test_an_uncommitted_competing_insert_is_bounded_and_nothing_is_written(db, tmp_path):
    from sqlalchemy import text

    plan = await _plan(db, tmp_path)
    async with db() as rival:
        await rival.execute(text(
            "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind) "
            "VALUES (:e, 'odds_api', :s, 'game')"), {"e": r.TWIN_ID, "s": r.CURRENT_ODDS_ID})
        out = await _apply(db, tmp_path, plan, lock_timeout_ms=300)
        assert out["state"] == r.REFUSED and out["reason"] == "lock_timeout", out
        await rival.rollback()
    assert _current_rows(await _anchors_table(db)) == []


@needs_postgres
async def test_a_failure_after_the_insert_rolls_the_insert_back(db, tmp_path, monkeypatch):
    plan = await _plan(db, tmp_path)
    monkeypatch.setattr(r, "created_row_matches", lambda row, cc: ["forced"])
    out = await _apply(db, tmp_path, plan)
    assert out["state"] == r.REFUSED and out["reason"] == "in_transaction_readback_mismatch"
    assert _current_rows(await _anchors_table(db)) == []
    assert await _step2(db) is None


@needs_postgres
@pytest.mark.parametrize("sql,reason", [
    ("UPDATE events SET external_id = 'changed00000000000000000000000000' WHERE id = :k",
     "keeper_identity_changed:external_id"),
    (f"UPDATE events SET sport_id = {OTHER_SPORT_ID} WHERE id = :k", "keeper_identity_changed:sport_id"),
    ("UPDATE sports SET key = 'soccer_usa_mls_old' WHERE id = 1326", "keeper_sport_key_changed"),
])
async def test_a_changed_scalar_or_sport_after_the_plan_refuses(db, tmp_path, sql, reason):
    plan = await _plan(db, tmp_path)
    await _exec(db, sql, **({"k": r.KEEPER_ID} if ":k" in sql else {}))
    out = await _apply(db, tmp_path, plan)
    assert out["state"] == r.REFUSED and out["reason"] == reason, out
    assert _current_rows(await _anchors_table(db)) == []


@needs_postgres
@pytest.mark.parametrize("sql,reason", [
    ("UPDATE event_provider_anchors SET id_kind = 'market' WHERE id = 187393", "incoming_game_anchor_absent"),
    ("UPDATE event_provider_anchors SET source = 'espn' WHERE id = 187393", "incoming_game_anchor_absent"),
    ("UPDATE event_provider_anchors SET event_id = 15324922 WHERE id = 187393",
     "incoming_game_anchor_not_keepers"),
    ("UPDATE event_provider_anchors SET source_id = 'soccer_usa_mls:9163448' WHERE id = 295737",
     "official_statpal_anchor_absent"),
])
async def test_wrong_kind_provider_owner_or_namespace_refuses(db, tmp_path, sql, reason):
    plan = await _plan(db, tmp_path)
    await _exec(db, sql)
    out = await _apply(db, tmp_path, plan)
    assert out["state"] == r.REFUSED and out["reason"] == reason, out
    assert _current_rows(await _anchors_table(db)) == []


@needs_postgres
async def test_rows_sharing_the_id_under_another_provider_or_kind_do_not_count(db, tmp_path):
    for source, kind in (("odds_api", "market"), ("espn", "game")):
        await _exec(db, "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind) "
                        "VALUES (:e, :src, :s, :k)", e=r.TWIN_ID, src=source, s=r.CURRENT_ODDS_ID, k=kind)
    out = await _apply(db, tmp_path, await _plan(db, tmp_path))
    assert out["state"] == r.APPLIED, out
    (row,) = _current_rows(await _anchors_table(db))
    assert row["event_id"] == r.KEEPER_ID


@needs_postgres
async def test_restore_deletes_only_this_invocations_row(db, tmp_path):
    before = await _anchors_table(db)
    out = await _apply(db, tmp_path, await _plan(db, tmp_path))
    backup = out["backup"]

    undo = await r.run_restore(db, backup_path=backup["path"], backup_hash=backup["sha256"])
    assert undo["state"] == r.RESTORED and undo["counts"]["anchor_rows_deleted"] == 1, undo
    assert await _anchors_table(db) == before
    assert await _step2(db) is None  # the #8278 refusal is back, as it was

    twice = await r.run_restore(db, backup_path=backup["path"], backup_hash=backup["sha256"])
    assert twice["state"] == r.NOT_APPLIED and r.exit_code(twice) == r.EXIT_OK


@needs_postgres
async def test_restore_refuses_a_row_changed_after_the_apply(db, tmp_path):
    out = await _apply(db, tmp_path, await _plan(db, tmp_path))
    await _exec(db, "UPDATE event_provider_anchors SET claim_context = claim_context || "
                    "'{\"touched\": true}'::jsonb WHERE source = 'odds_api' AND source_id = :s",
                s=r.CURRENT_ODDS_ID)
    undo = await r.run_restore(db, backup_path=out["backup"]["path"], backup_hash=out["backup"]["sha256"])
    assert undo["state"] == r.REFUSED and undo["reason"].startswith(
        "row_is_not_this_invocations_unchanged_write:claim_context"), undo
    assert len(_current_rows(await _anchors_table(db))) == 1


@needs_postgres
async def test_restore_never_deletes_a_pre_existing_row(db, tmp_path):
    plan = await _plan(db, tmp_path)
    await _exec(db, "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind, claim_context) "
                    "VALUES (:e, 'odds_api', :s, 'game', CAST(:cc AS jsonb))", e=r.KEEPER_ID,
                s=r.CURRENT_ODDS_ID, cc=json.dumps({"source": "odds_api", "schedule_derived": False}))
    out = await _apply(db, tmp_path, plan)
    assert out["state"] == r.NOT_NEEDED, out
    undo = await r.run_restore(db, backup_path=out["backup"]["path"], backup_hash=out["backup"]["sha256"])
    assert undo["state"] == r.REFUSED, undo
    (row,) = _current_rows(await _anchors_table(db))
    assert row["claim_context"] == {"source": "odds_api", "schedule_derived": False}


@needs_postgres
async def test_the_delete_carries_its_own_fence_behind_the_python_check(db, tmp_path, monkeypatch):
    """Defence in depth: with the in-Python comparison blinded, the DELETE's own
    ``claim_context`` predicate still declines a row that is not this invocation's."""
    out = await _apply(db, tmp_path, await _plan(db, tmp_path))
    await _exec(db, "UPDATE event_provider_anchors SET claim_context = '{\"other\": 1}'::jsonb "
                    "WHERE source = 'odds_api' AND source_id = :s", s=r.CURRENT_ODDS_ID)
    monkeypatch.setattr(r, "created_row_matches", lambda row, cc: [])
    undo = await r.run_restore(db, backup_path=out["backup"]["path"], backup_hash=out["backup"]["sha256"])
    assert undo["state"] == r.REFUSED and undo["reason"] == "delete_fence_lost", undo
    assert len(_current_rows(await _anchors_table(db))) == 1


@needs_postgres
async def test_a_same_owner_row_that_appears_between_read_and_write_is_a_no_op(db, tmp_path, monkeypatch):
    """``record_anchor`` answering CONFIRMED at the write (a same-owner row landed
    after the admission read) is NOT_NEEDED: nothing written, the incumbent kept."""
    plan = await _plan(db, tmp_path)
    await _exec(db, "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind) "
                    "VALUES (:e, 'odds_api', :s, 'game')", e=r.KEEPER_ID, s=r.CURRENT_ODDS_ID)
    real_read_all = r._read_all

    async def read_before_the_rival(session, *, lock):
        keeper, sport_key, anchors = await real_read_all(session, lock=lock)
        return keeper, sport_key, {**anchors, "current": None}

    monkeypatch.setattr(r, "_read_all", read_before_the_rival)
    out = await _apply(db, tmp_path, plan)
    assert out["state"] == r.NOT_NEEDED and out["reason"] == "current_key_confirmed_at_write", out
    (row,) = _current_rows(await _anchors_table(db))
    assert row["claim_context"] is None
