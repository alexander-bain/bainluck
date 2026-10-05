"""#10520 — the one-row keeper-anchor repair, judged as units and EXECUTED on real Postgres.

Two halves.

* The UNIT half has no database and runs everywhere: admission refuses every
  keeper and known-twin identity change by name, the survivor gate mirrors the
  drain's election and treats an absent twin as its own branch, the host
  acknowledgment must name the exact receipt, host staging refuses on a dyno and
  writes exactly the bytes it hashes, a DB mode refuses a tampered frame before it
  connects, and the CLI writes nothing but JSON Lines.
* The POSTGRES half (``SEARCH_TEST_DATABASE_URL``) runs the SHIPPED phases against
  the real schema. In-process arms drive ``run_apply`` with a fake host on the
  frame channel; the ``drive-apply`` arms spawn the REAL CLI as the child process,
  exactly as the attended ``heroku run`` would be spawned, and prove across
  processes that no acknowledgment means no commit.

The arm the file exists for is
``test_apply_writes_one_anchor_and_step2_then_resolves_the_incoming_id``: before
the write, Step 2 refuses the incoming id as stale (#8278); after it, Step 2
resolves the incoming id to the keeper. Both answers come from
``app.services.anchor_channel`` unchanged.

Fixture values are the retained #10520 evidence — test data, not production
eligibility. The Postgres half is outside ``tests/integration/`` and not named by
a ci.yml step, so it skips in CI; its evidence is the local run quoted in the offer.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import uuid
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
HOST = {}  # a host environment: no DYNO
TAGS = ["provenance:source:odds_api", "provenance:unanchored", "provenance:duplicate-of:14969919"]


def _keeper(**over):
    row = {"id": r.KEEPER_ID, **r.IDENTITY, "commence_time": COMMENCE, "status": "scheduled"}
    row.update(over)
    return row


def _twin(**over):
    row = {"id": r.TWIN_ID, **r.TWIN_IDENTITY, "commence_time": COMMENCE, "event_tags": list(TAGS)}
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


def _snaps(keeper=False, twin=False):
    return {"keeper_has_snaps": keeper, "twin_has_snaps": twin}


def _admit(keeper=None, sport_key=r.SPORT_KEY, anchors=None, twin="default", snaps=None):
    return r.admit(keeper or _keeper(), sport_key, anchors or _anchors(),
                   _twin() if twin == "default" else twin, snaps or _snaps())


class _Records(list):
    def __call__(self, record):
        json.loads(r.canonical_json(record))  # every record must be one JSON object
        self.append(record)

    def kind(self, name):
        return [x for x in self if x.get("record") == name]


class FakeHost:
    """Both ends of the frame channel, in process. ``ack`` is how the host answers
    the ``created_row`` record: 'retain' (the honest path), 'wrong_hash',
    'wrong_invocation', 'eof' or 'silent' (never answers)."""

    def __init__(self, bundle: bytes, ack: str = "retain"):
        self.queue: list = [bundle]
        self.ack = ack
        self.records = _Records()
        self.retained = None

    def emit(self, record):
        self.records(record)
        if record.get("record") != "created_row":
            return
        receipt = record["receipt"]
        if self.ack == "retain":
            self.retained = receipt
            self.queue.append(r.artifact_bytes(r.ack_for(receipt)))
        elif self.ack == "wrong_hash":
            self.queue.append(r.artifact_bytes(dict(r.ack_for(receipt), receipt_sha256="0" * 64)))
        elif self.ack == "wrong_invocation":
            self.queue.append(r.artifact_bytes(dict(r.ack_for(receipt), invocation_id=str(uuid.uuid4()))))
        elif self.ack == "eof":
            self.queue.append(None)

    async def line(self, timeout_s):
        if not self.queue:
            await asyncio.sleep(timeout_s * 4)  # silent host: the caller's bound must fire
            return None
        return self.queue.pop(0)


def _write_jsonl(path: Path, records) -> str:
    path.write_bytes(b"".join(r.artifact_bytes(x) for x in records))
    return str(path)


class _NoDb:
    """A session factory that records being reached. A refused frame must never reach it."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        raise ConnectionError("no database in the unit half")


# ═══ unit half ════════════════════════════════════════════════════════════════

def test_keys_are_the_channels_own_keys():
    # The retained ids, spelled once each and never beside a provider name (a
    # quoted hex next to "odds_api" reads to gitleaks as a credential).
    assert r.CURRENT_ODDS_ID == "1d13bd275c7b67b77bea8ff4d03850cc"
    assert r.INCOMING_ODDS_ID == "0d9ff865c4599c72a746da08260279b3"
    assert (r.CURRENT_KEY.source, r.CURRENT_KEY.source_id, r.CURRENT_KEY.id_kind) == (
        "odds_api", r.CURRENT_ODDS_ID, "game")
    assert (r.INCOMING_KEY.source, r.INCOMING_KEY.source_id) == ("odds_api", r.INCOMING_ODDS_ID)
    assert r.STATPAL_KEY.source_id == "soccer:9163448"  # D55 / #4393: the stamper's key
    assert (r.ESPN_KEY.source, r.ESPN_KEY.source_id) == ("espn", "761660")
    assert r.TWIN_TAG == "provenance:duplicate-of:14969919"
    assert r.CURRENT_ODDS_ID in r.RECOVERY_READ_SQL and "first_seen_at" in r.RECOVERY_READ_SQL \
        and "claim_context" in r.RECOVERY_READ_SQL


def test_admit_the_retained_state_is_a_candidate():
    body = _admit()
    assert body["state"] == "CANDIDATE" and body["write"] == r.WRITE_SCOPE
    assert body["anchors"]["current"] is None
    assert body["anchors"]["incoming"] == {"id": 187393, "event_id": r.KEEPER_ID}
    assert body["twin_state"]["known_twin"] == "present"
    assert body["twin_state"]["duplicate_tag"] == r.TWIN_TAG
    assert body["survivor_observed"]["keeper_has_snaps"] is False
    assert "observed in this transaction only" in body["survivor_observed"]["limit"]


@pytest.mark.parametrize("column,value", [
    ("sport_id", 1327), ("home_team_id", 17), ("away_team_id", 24),
    ("home_team_name", "Chicago Fire FC"), ("away_team_name", "Vancouver Whitecaps"),
    ("external_id", "ffffffffffffffffffffffffffffffff"), ("external_id", None),
    ("espn_id", "761661"), ("espn_id", None), ("statpal_fixture_id", "9163449"),
    ("commence_time", datetime(2026, 10, 7, 0, 45, tzinfo=timezone.utc)),
])
def test_admit_refuses_every_changed_keeper_identity_column(column, value):
    with pytest.raises(r.Refused) as exc:
        _admit(keeper=_keeper(**{column: value}))
    assert exc.value.reason == f"keeper_identity_changed:{column}"


@pytest.mark.parametrize("column,value", [
    ("sport_id", 1327), ("home_team_id", 23), ("away_team_id", 16),
    ("home_team_name", "Vancouver Whitecaps FC"), ("statpal_fixture_id", "9163449"),
    ("external_id", "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"),
    ("commence_time", datetime(2026, 10, 8, 0, 30, tzinfo=timezone.utc)),
])
def test_admit_refuses_every_changed_known_twin_identity_column(column, value):
    with pytest.raises(r.Refused) as exc:
        _admit(twin=_twin(**{column: value}))
    assert exc.value.reason == f"known_twin_identity_changed:{column}"


def test_admit_refuses_a_twin_that_lost_its_duplicate_tag():
    with pytest.raises(r.Refused, match="known_twin_duplicate_tag_absent"):
        _admit(twin=_twin(event_tags=TAGS[:2]))


def test_admit_does_not_fence_status():
    assert _admit(keeper=_keeper(status="live"))["state"] == "CANDIDATE"


def test_admit_refuses_missing_keeper_and_wrong_sport_key():
    with pytest.raises(r.Refused, match="keeper_missing"):
        r.admit(None, r.SPORT_KEY, _anchors(), _twin(), _snaps())
    with pytest.raises(r.Refused, match="keeper_sport_key_changed"):
        _admit(sport_key="soccer_epl")


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
        _admit(anchors=anchors)
    assert exc.value.reason == reason


@pytest.mark.parametrize("keeper,twin,refused", [
    (True, False, False),   # keeper-only: the drain keeps the keeper
    (False, True, True),    # twin-only: the drain would keep the twin -> refuse
    (True, True, False),    # both: lower id (keeper) kept
    (False, False, False),  # neither: StatPal tie -> lower id (keeper)
])
def test_the_survivor_gate_is_the_drains_election(keeper, twin, refused):
    assert r.twin_would_survive(keeper, twin) is refused
    if refused:
        with pytest.raises(r.Refused, match="drain_would_elect_twin_return_to_root"):
            _admit(snaps=_snaps(keeper, twin))
    else:
        assert _admit(snaps=_snaps(keeper, twin))["state"] == "CANDIDATE"


def test_an_absent_known_twin_is_its_own_branch_not_false_snapshot_evidence():
    body = _admit(twin=None, snaps={"keeper_has_snaps": False, "twin_has_snaps": None})
    assert body["state"] == "CANDIDATE"
    assert body["twin_state"] == {"id": r.TWIN_ID, "known_twin": "absent"}
    with pytest.raises(r.Refused, match="absent_twin_cannot_have_snapshot_evidence"):
        _admit(twin=None, snaps=_snaps(False, False))
    with pytest.raises(r.Refused, match="known_twin_snapshots_unread"):
        _admit(snaps={"keeper_has_snaps": False, "twin_has_snaps": None})


def test_admit_keepers_own_current_anchor_is_not_needed():
    assert _admit(anchors=_anchors(current=_anchor("current")))["state"] == r.NOT_NEEDED
    assert _admit(anchors=_anchors(espn=_anchor("espn")))["state"] == "CANDIDATE"


def test_plan_drift_fences_twin_presence_but_not_status_or_snapshots():
    plan = _admit()
    assert r.plan_drift(plan, _admit(keeper=_keeper(status="live"), snaps=_snaps(True, True))) == []
    assert r.plan_drift(plan, _admit(anchors=_anchors(espn=_anchor("espn")))) == ["anchors"]
    gone = _admit(twin=None, snaps={"keeper_has_snaps": False, "twin_has_snaps": None})
    assert r.plan_drift(plan, gone) == ["twin_state"]
    assert r.plan_drift(gone, plan) == ["twin_state"]


def test_restore_identity_is_the_whole_row_id_and_timestamp_included():
    cc = r.claim_context_for("inv-a", "addr")
    created = {"id": 7, "event_id": r.KEEPER_ID, **r.key_dict(r.CURRENT_KEY),
               "first_seen_at": "2026-10-05T12:00:00.123456+00:00", "claim_context": cc}
    assert r.row_is_the_created_row(dict(created), created) == []
    assert r.row_is_the_created_row({**created, "id": 8}, created) == ["id"]
    assert r.row_is_the_created_row({**created, "first_seen_at": "2026-10-05T12:00:01.123456+00:00"},
                                    created) == ["first_seen_at"]
    assert r.row_is_the_created_row(None, created) == ["row_missing"]
    assert r.created_row_matches({**created, "id": 8}, cc) == []  # the write check alone cannot tell


def _receipt():
    return r.seal(r.CREATED_ROW_SCHEMA, {"keeper_id": r.KEEPER_ID, "write": r.WRITE_SCOPE,
                                         "invocation_id": "inv-a", "backup_sha256": "b" * 64})


def test_the_acknowledgment_must_name_exactly_this_receipt():
    receipt = _receipt()
    r.check_ack(r.artifact_bytes(r.ack_for(receipt)), receipt)
    for raw, reason in (
        (None, "host_ack_eof"),
        (b"", "host_ack_eof"),
        (b"ok\n", "host_ack_not_json"),
        (json.dumps(r.ack_for(receipt), indent=1).encode() + b"\n", "host_ack_not_canonical"),
        (r.artifact_bytes(dict(r.ack_for(receipt), receipt_sha256="0" * 64)), "host_ack_mismatch"),
        (r.artifact_bytes(dict(r.ack_for(receipt), invocation_id="inv-b")), "host_ack_mismatch"),
        (r.artifact_bytes(dict(r.ack_for(receipt), schema="other")), "host_ack_mismatch"),
    ):
        with pytest.raises(r.Refused) as exc:
            r.check_ack(raw, receipt)
        assert exc.value.reason == reason


@pytest.mark.parametrize("argv", [
    ["--only", "15324922", "--mode", "preflight"],
    ["--only", "14969919", "--only", "14969919", "--mode", "preflight"],
    ["--only", "14969919"],
    ["--only", "14969919", "--mode", "apply", "--plan-hash", "h"],
    ["--only", "14969919", "--mode", "restore", "--backup-hash", "b", "--receipt-hash", "r", "--plan", "/p"],
    ["--only", "14969919", "--mode", "drive-apply", "--apply-input", "/a"],
])
def test_cli_usage_is_one_record_and_exit_2(argv):
    out = _Records()
    assert asyncio.run(r.main(argv, env=HOST, emit=out)) == r.EXIT_USAGE
    assert [x["state"] for x in out] == ["USAGE"]


def test_db_mode_target_fence_refuses_before_connecting():
    out = _Records()
    rc = asyncio.run(r.main(["--only", "14969919", "--mode", "preflight"],
                            env={"HEROKU_APP_NAME": "bainluck-heavy"}, emit=out))
    assert rc == r.EXIT_REFUSED and out[-1]["reason"] == "target_app_refused"


def test_host_modes_refuse_on_a_dyno(tmp_path):
    out = r.stage_plan(preflight_output=str(tmp_path / "p.jsonl"), plan_out=str(tmp_path / "plan.json"),
                       env={"DYNO": "run.1"})
    assert out["state"] == r.REFUSED and out["reason"] == "host_mode_refused_on_dyno"
    driven = asyncio.run(r.drive_apply(apply_input=str(tmp_path / "a"), plan_hash="p", backup_hash="b",
                                       output=str(tmp_path / "o"), receipt_out=str(tmp_path / "c"),
                                       env={"DYNO": "run.1"}))
    assert driven["state"] == r.REFUSED and driven["reason"] == "host_mode_refused_on_dyno"
    assert list(tmp_path.iterdir()) == []


def _sealed_plan():
    body = _admit()
    body.update({"evidence": r.EVIDENCE, "pins": {"tool": r.TOOL}, "planned_at": "2026-10-05T12:00:00+00:00"})
    return r.seal(r.PLAN_SCHEMA, body)


def _staged(tmp_path):
    plan = _sealed_plan()
    preflight = _write_jsonl(tmp_path / "preflight.jsonl", [r._result(
        "preflight", r.PLANNED, plan=plan, plan_sha256=r.artifact_sha256(plan))])
    sp = r.stage_plan(preflight_output=preflight, plan_out=str(tmp_path / "plan.json"), env=HOST)
    assert sp["state"] == r.STAGED, sp
    sa = r.stage_apply(plan_path=sp["plan"]["path"], plan_hash=sp["plan"]["sha256"],
                       backup_out=str(tmp_path / "backup.json"), bundle_out=str(tmp_path / "apply-input.json"),
                       env=HOST)
    assert sa["state"] == r.STAGED, sa
    return sp, sa


def test_host_staging_writes_exactly_the_bytes_it_hashes(tmp_path):
    sp, sa = _staged(tmp_path)
    for f in (sp["plan"], sa["backup"], sa["apply_input"]):
        data = Path(f["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == f["sha256"]
        assert Path(f["path"] + ".sha256").read_text().split() == [f["sha256"], Path(f["path"]).name]
        assert oct(os.stat(f["path"]).st_mode & 0o777) == "0o400"
    assert sa["apply_argv"] == {"--plan-hash": sp["plan"]["sha256"], "--backup-hash": sa["backup"]["sha256"]}
    again = r.stage_apply(plan_path=sp["plan"]["path"], plan_hash=sp["plan"]["sha256"],
                          backup_out=sa["backup"]["path"], bundle_out=str(tmp_path / "x.json"), env=HOST)
    assert again["state"] == r.REFUSED and again["reason"] == "backup_path_exists"


@pytest.mark.parametrize("which", ["plan_hash", "backup_hash"])
def test_drive_apply_refuses_a_foreign_hash_before_it_spawns_anything(tmp_path, which):
    _, sa = _staged(tmp_path)
    hashes = {"plan_hash": sa["apply_argv"]["--plan-hash"], "backup_hash": sa["apply_argv"]["--backup-hash"]}
    hashes[which] = "0" * 64
    out = asyncio.run(r.drive_apply(apply_input=sa["apply_input"]["path"], output=str(tmp_path / "apply.jsonl"),
                                    receipt_out=str(tmp_path / "created-row.json"), env=HOST,
                                    prefix=("/nonexistent/never-spawned",), **hashes))
    assert out["state"] == r.REFUSED and out["reason"] == f"{which.split('_')[0]}_hash_mismatch", out
    assert not (tmp_path / "apply.jsonl").exists() and not (tmp_path / "created-row.json").exists()


class _Frames:
    def __init__(self, *frames):
        self.frames = list(frames)

    async def line(self, timeout_s):
        return self.frames.pop(0) if self.frames else None


def test_a_db_mode_refuses_a_tampered_frame_before_connecting(tmp_path):
    _, sa = _staged(tmp_path)
    honest = Path(sa["apply_input"]["path"]).read_bytes()
    argv = dict(plan_hash=sa["apply_argv"]["--plan-hash"], backup_hash=sa["apply_argv"]["--backup-hash"])
    control = _NoDb()  # the honest bundle passes every pre-DB gate and reaches the database
    asyncio.run(r.run_apply(control, frames=_Frames(honest), emit=_Records(), **argv))
    assert control.calls == 1
    for raw, reason in (
        (honest.replace(b'"state":"CANDIDATE"', b'"state":"CANDIDATE" '), "apply_bundle_not_canonical"),
        (honest[:-1], "apply_bundle_not_canonical"),
        (b"Running python3 on bainluck... up\n", "apply_bundle_not_json"),
        (None, "apply_bundle_eof"),
    ):
        never = _NoDb()
        res = asyncio.run(r.run_apply(never, frames=_Frames(raw), emit=_Records(), **argv))
        assert res["state"] == r.REFUSED and res["reason"] == reason, res
        assert never.calls == 0


@pytest.mark.parametrize("which", ["--plan-hash", "--backup-hash"])
def test_apply_refuses_a_hash_the_host_did_not_compute(tmp_path, which):
    _, sa = _staged(tmp_path)
    argv = dict(sa["apply_argv"], **{which: "0" * 64})
    never = _NoDb()
    res = asyncio.run(r.run_apply(never, frames=_Frames(Path(sa["apply_input"]["path"]).read_bytes()),
                                  emit=_Records(), plan_hash=argv["--plan-hash"],
                                  backup_hash=argv["--backup-hash"]))
    assert res["state"] == r.REFUSED and res["reason"].endswith("_hash_mismatch") and never.calls == 0


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


async def _build(engine):
    from app.models import models
    from app.services.database import Base

    assert models.EventProviderAnchor.__tablename__ == "event_provider_anchors"
    tables = _closure([Base.metadata.tables[n] for n in ("events", "event_provider_anchors", "odds_snapshots")])
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))


@pytest.fixture
async def db():
    """A throwaway schema holding exactly the tables the tool touches."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    admin = create_async_engine(_asyncpg_url(DB_URL))
    async with admin.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
    engine = create_async_engine(
        _asyncpg_url(DB_URL), connect_args={"server_settings": {"search_path": SCHEMA}}
    )
    await _build(engine)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _seed(maker)
        yield maker
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await admin.dispose()


@pytest.fixture
async def drive_db():
    """A throwaway DATABASE (public schema) for the cross-process arms: the child is
    the real CLI and reads ``DATABASE_URL`` the way the deployed app does."""
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    base = make_url(_asyncpg_url(DB_URL))
    name = f"r10520_drive_{os.getpid()}"
    admin = create_async_engine(base, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {name}"))
        await conn.execute(text(f"CREATE DATABASE {name}"))
    url = base.set(database=name)
    engine = create_async_engine(url)
    await _build(engine)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _seed(maker)
        yield maker, url.render_as_string(hide_password=False).replace("+asyncpg", "")
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {name}"))
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
                   Event(id=r.TWIN_ID, external_id=r.INCOMING_ODDS_ID, espn_id=None,
                         event_tags=list(TAGS), **common)])
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


async def _snapshot(maker, event_id):
    from app.models.models import OddsSnapshot

    async with maker() as s:
        s.add(OddsSnapshot(event_id=event_id, bookmaker="draftkings"))
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
            "SELECT id, event_id, source, source_id, id_kind, first_seen_at, claim_context "
            "FROM event_provider_anchors ORDER BY source, source_id, id_kind"))).mappings().all()
    return [dict(x) for x in rows]


async def _step2(maker):
    from app.services.anchor_channel import find_event_by_anchor

    async with maker() as s:
        return await find_event_by_anchor(s, r.INCOMING_KEY, expected_sport_id=1326)


def _current_rows(table):
    return [a for a in table if (a["source"], a["source_id"], a["id_kind"]) ==
            ("odds_api", r.CURRENT_ODDS_ID, "game")]


class _CommitSpy:
    def __init__(self, monkeypatch):
        from sqlalchemy.ext.asyncio import AsyncSession

        self.calls = 0
        real = AsyncSession.commit

        async def spy(session):
            self.calls += 1
            return await real(session)

        monkeypatch.setattr(AsyncSession, "commit", spy)


class Flow:
    """The phases through the shipped functions; a tmp dir is the 'host'."""

    def __init__(self, db, tmp_path):
        self.db, self.dir, self.n = db, tmp_path, 0

    def _p(self, name):
        self.n += 1
        return str(self.dir / f"{self.n:02d}-{name}")

    async def preflight(self):
        out = _Records()
        return await r.run_preflight(self.db, emit=out), out

    async def stage(self):
        res, out = await self.preflight()
        assert res["state"] == r.PLANNED, res
        sp = r.stage_plan(preflight_output=_write_jsonl(Path(self._p("preflight.jsonl")), out),
                          plan_out=self._p("plan.json"), env=HOST)
        sa = r.stage_apply(plan_path=sp["plan"]["path"], plan_hash=sp["plan"]["sha256"],
                           backup_out=self._p("backup.json"), bundle_out=self._p("apply-input.json"), env=HOST)
        assert sa["state"] == r.STAGED, sa
        return sa

    async def apply(self, sa, ack="retain", **kw):
        host = FakeHost(Path(sa["apply_input"]["path"]).read_bytes(), ack=ack)
        res = await r.run_apply(self.db, frames=host, emit=host.emit,
                                plan_hash=sa["apply_argv"]["--plan-hash"],
                                backup_hash=sa["apply_argv"]["--backup-hash"], **kw)
        self.receipt_file = None
        if host.retained is not None:  # what drive-apply does before it acknowledges
            self.receipt_file = r.write_host_artifact(self._p("created-row.json"), host.retained, "receipt")
        return res, host.records

    def stage_restore(self, sa):
        return r.stage_restore(backup_path=sa["backup"]["path"], backup_hash=sa["backup"]["sha256"],
                               receipt_path=self.receipt_file["path"], receipt_hash=self.receipt_file["sha256"],
                               bundle_out=self._p("restore-input.json"), env=HOST)

    async def restore(self, sr, **kw):
        out = _Records()
        res = await r.run_restore(self.db, frames=_Frames(Path(sr["restore_input"]["path"]).read_bytes()),
                                  emit=out, backup_hash=sr["restore_argv"]["--backup-hash"],
                                  receipt_hash=sr["restore_argv"]["--receipt-hash"], **kw)
        return res, out


@needs_postgres
async def test_apply_writes_one_anchor_and_step2_then_resolves_the_incoming_id(db, tmp_path):
    f = Flow(db, tmp_path)
    before = await _anchors_table(db)
    assert await _step2(db) is None  # BEFORE: #8278 refuses — the column's own id is unanchored

    res, out = await f.apply(await f.stage())
    assert res["state"] == r.APPLIED, res
    assert res["counts"]["anchor_rows_written"] == 1
    assert res["step2_resolves_incoming_to"] == r.KEEPER_ID
    assert res["incoming_after"] == {"id": r.INCOMING_ANCHOR_ID, "event_id": r.KEEPER_ID}
    assert [x["record"] for x in out] == ["created_row", "result"]

    after = await _anchors_table(db)
    assert [a for a in after if a not in before] == _current_rows(after)
    assert [a for a in before if a not in after] == []  # nothing else moved or vanished
    (created,) = _current_rows(after)
    assert r.row_is_the_created_row(created, out.kind("created_row")[0]["receipt"]["created_row"]) == []
    assert await _step2(db) == r.KEEPER_ID  # AFTER: the same registry read rescues


@needs_postgres
@pytest.mark.parametrize("ack,reason", [
    ("eof", "host_ack_eof"),
    ("wrong_hash", "host_ack_mismatch"),
    ("wrong_invocation", "host_ack_mismatch"),
    ("silent", "host_ack_timeout"),
])
async def test_no_acknowledgment_means_no_commit(db, tmp_path, monkeypatch, ack, reason):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    spy = _CommitSpy(monkeypatch)
    res, out = await f.apply(sa, ack=ack, ack_timeout_s=0.3)
    assert res["state"] == r.REFUSED and res["reason"] == reason, res
    assert [x["record"] for x in out] == ["created_row", "result"]
    assert spy.calls == 0  # rolled back, COMMIT never attempted
    assert _current_rows(await _anchors_table(db)) == []
    assert await _step2(db) is None


@needs_postgres
async def test_the_acknowledgment_is_awaited_before_the_only_commit(db, tmp_path, monkeypatch):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    spy = _CommitSpy(monkeypatch)
    host = FakeHost(Path(sa["apply_input"]["path"]).read_bytes())
    seen = {}
    real_line = host.line

    async def line(timeout_s):
        if len(host.records):  # the ack read: the receipt is out, nothing committed yet
            seen["commits_at_ack_read"] = spy.calls
        return await real_line(timeout_s)

    host.line = line
    res = await r.run_apply(db, frames=host, emit=host.emit, plan_hash=sa["apply_argv"]["--plan-hash"],
                            backup_hash=sa["apply_argv"]["--backup-hash"])
    assert res["state"] == r.APPLIED, res
    assert seen == {"commits_at_ack_read": 0} and spy.calls == 1


@needs_postgres
async def test_a_lost_dyno_after_commit_is_recoverable_from_the_retained_receipt(db, tmp_path, monkeypatch):
    f = Flow(db, tmp_path)
    sa = await f.stage()

    async def gone(*_a, **_k):
        raise ConnectionError("dyno gone")

    monkeypatch.setattr(r, "_verify", gone)
    res, _ = await f.apply(sa)
    assert res["state"] == r.COMMIT_UNKNOWN and res["reason"] == "post_commit_verify_unreadable", res
    assert res["recovery_read_sql"] == r.RECOVERY_READ_SQL
    assert len(_current_rows(await _anchors_table(db))) == 1  # it did commit
    monkeypatch.undo()

    sr = f.stage_restore(sa)
    assert sr["state"] == r.STAGED, sr
    undo, _ = await f.restore(sr)
    assert undo["state"] == r.RESTORED, undo
    assert _current_rows(await _anchors_table(db)) == []


@needs_postgres
async def test_repeated_execution_is_an_idempotent_no_op(db, tmp_path):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    assert (await f.apply(sa))[0]["state"] == r.APPLIED
    table = await _anchors_table(db)

    again, out = await f.apply(sa)
    assert again["state"] == r.NOT_NEEDED and again["counts"]["anchor_rows_written"] == 0
    assert out.kind("created_row") == []
    assert (await f.preflight())[0]["state"] == r.NOT_NEEDED
    assert await _anchors_table(db) == table


@needs_postgres
async def test_another_owner_of_the_current_key_refuses_and_is_never_repointed(db, tmp_path):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    await _exec(db, "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind) "
                    "VALUES (:e, 'odds_api', :s, 'game')", e=r.TWIN_ID, s=r.CURRENT_ODDS_ID)
    pre, _ = await f.preflight()
    assert pre["state"] == r.REFUSED and pre["reason"] == "current_key_owned_elsewhere"
    res, _ = await f.apply(sa)
    assert res["state"] == r.REFUSED and res["reason"] == "current_key_owned_elsewhere"
    (row,) = _current_rows(await _anchors_table(db))
    assert row["event_id"] == r.TWIN_ID


@needs_postgres
async def test_an_uncommitted_competing_insert_is_bounded_and_nothing_is_written(db, tmp_path):
    from sqlalchemy import text

    f = Flow(db, tmp_path)
    sa = await f.stage()
    async with db() as rival:
        await rival.execute(text(
            "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind) "
            "VALUES (:e, 'odds_api', :s, 'game')"), {"e": r.TWIN_ID, "s": r.CURRENT_ODDS_ID})
        res, out = await f.apply(sa, lock_timeout_ms=300)
        assert res["state"] == r.REFUSED and res["reason"] == "lock_timeout", res
        assert out.kind("created_row") == []
        await rival.rollback()
    assert _current_rows(await _anchors_table(db)) == []


@needs_postgres
async def test_a_held_twin_row_lock_is_bounded_and_nothing_is_written(db, tmp_path):
    """The pair lock now covers the twin: a writer holding it (the drain's own
    FOR UPDATE, say) makes the apply refuse within lock_timeout, never hang."""
    from sqlalchemy import text

    f = Flow(db, tmp_path)
    sa = await f.stage()
    async with db() as holder:
        await holder.execute(text("SELECT id FROM events WHERE id = :t FOR UPDATE"), {"t": r.TWIN_ID})
        res, _ = await f.apply(sa, lock_timeout_ms=300)
        assert res["state"] == r.REFUSED and res["reason"] == "lock_timeout", res
        await holder.rollback()
    assert _current_rows(await _anchors_table(db)) == []


@needs_postgres
async def test_a_failure_after_the_insert_rolls_the_insert_back(db, tmp_path, monkeypatch):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    monkeypatch.setattr(r, "created_row_matches", lambda row, cc: ["forced"])
    res, out = await f.apply(sa)
    assert res["state"] == r.REFUSED and res["reason"] == "in_transaction_readback_mismatch"
    assert out.kind("created_row") == []
    assert _current_rows(await _anchors_table(db)) == []
    assert await _step2(db) is None


@needs_postgres
@pytest.mark.parametrize("sql,reason", [
    ("UPDATE events SET external_id = 'changed00000000000000000000000000' WHERE id = 14969919",
     "keeper_identity_changed:external_id"),
    (f"UPDATE events SET sport_id = {OTHER_SPORT_ID} WHERE id = 14969919", "keeper_identity_changed:sport_id"),
    ("UPDATE sports SET key = 'soccer_usa_mls_old' WHERE id = 1326", "keeper_sport_key_changed"),
    ("UPDATE events SET commence_time = commence_time + interval '1 day' WHERE id = 15324922",
     "known_twin_identity_changed:commence_time"),
    ("UPDATE events SET statpal_fixture_id = '9163449' WHERE id = 15324922",
     "known_twin_identity_changed:statpal_fixture_id"),
    ("UPDATE events SET event_tags = '[\"provenance:source:odds_api\"]'::jsonb WHERE id = 15324922",
     "known_twin_duplicate_tag_absent"),
])
async def test_a_changed_keeper_twin_or_sport_after_the_plan_refuses(db, tmp_path, sql, reason):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    await _exec(db, sql)
    res, _ = await f.apply(sa)
    assert res["state"] == r.REFUSED and res["reason"] == reason, res
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
    f = Flow(db, tmp_path)
    sa = await f.stage()
    await _exec(db, sql)
    res, _ = await f.apply(sa)
    assert res["state"] == r.REFUSED and res["reason"] == reason, res
    assert _current_rows(await _anchors_table(db)) == []


@needs_postgres
async def test_rows_sharing_the_id_under_another_provider_or_kind_do_not_count(db, tmp_path):
    for source, kind in (("odds_api", "market"), ("espn", "game")):
        await _exec(db, "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind) "
                        "VALUES (:e, :src, :s, :k)", e=r.TWIN_ID, src=source, s=r.CURRENT_ODDS_ID, k=kind)
    f = Flow(db, tmp_path)
    res, _ = await f.apply(await f.stage())
    assert res["state"] == r.APPLIED, res
    (row,) = _current_rows(await _anchors_table(db))
    assert row["event_id"] == r.KEEPER_ID


@needs_postgres
@pytest.mark.parametrize("keeper_snap,twin_snap,expect", [
    (True, False, r.PLANNED),   # keeper-only
    (False, True, r.REFUSED),   # twin-only
    (True, True, r.PLANNED),    # both
    (False, False, r.PLANNED),  # neither
])
async def test_the_survivor_cases_read_with_the_drains_predicate(db, tmp_path, keeper_snap, twin_snap, expect):
    if keeper_snap:
        await _snapshot(db, r.KEEPER_ID)
    if twin_snap:
        await _snapshot(db, r.TWIN_ID)
    res, _ = await Flow(db, tmp_path).preflight()
    assert res["state"] == expect, res
    if expect == r.REFUSED:
        assert res["reason"] == "drain_would_elect_twin_return_to_root"
    else:
        assert res["plan"]["survivor_observed"]["keeper_has_snaps"] is keeper_snap
        assert res["plan"]["survivor_observed"]["twin_has_snaps"] is twin_snap


@needs_postgres
async def test_the_survivor_gate_is_rejudged_inside_the_apply_transaction(db, tmp_path):
    f = Flow(db, tmp_path)
    sa = await f.stage()  # neither row has snapshots: CANDIDATE
    await _snapshot(db, r.TWIN_ID)
    res, _ = await f.apply(sa)
    assert res["state"] == r.REFUSED and res["reason"] == "drain_would_elect_twin_return_to_root", res
    assert _current_rows(await _anchors_table(db)) == []
    await _snapshot(db, r.KEEPER_ID)  # both: the drain keeps the lower id, the keeper
    res, _ = await f.apply(sa)
    assert res["state"] == r.APPLIED, res


@needs_postgres
async def test_a_missing_known_twin_is_an_explicit_anchor_only_candidate(db, tmp_path):
    await _exec(db, "DELETE FROM events WHERE id = :t", t=r.TWIN_ID)
    f = Flow(db, tmp_path)
    res, _ = await f.preflight()
    assert res["state"] == r.PLANNED, res
    assert res["plan"]["twin_state"] == {"id": r.TWIN_ID, "known_twin": "absent"}
    assert res["plan"]["survivor_observed"]["twin_has_snaps"] is None
    assert (await f.apply(await f.stage()))[0]["state"] == r.APPLIED


@needs_postgres
async def test_a_twin_that_vanished_or_appeared_since_the_plan_is_drift(db, tmp_path):
    f = Flow(db, tmp_path)
    sa = await f.stage()  # planned with the twin present
    await _exec(db, "DELETE FROM events WHERE id = :t", t=r.TWIN_ID)
    res, _ = await f.apply(sa)
    assert res["state"] == r.REFUSED and res["reason"] == "plan_drift:twin_state", res
    assert _current_rows(await _anchors_table(db)) == []

    sa2 = await f.stage()  # planned with the twin absent
    await _seed_twin_again(db)
    res, _ = await f.apply(sa2)
    assert res["state"] == r.REFUSED and res["reason"] == "plan_drift:twin_state", res
    assert _current_rows(await _anchors_table(db)) == []


async def _seed_twin_again(maker):
    from app.models.models import Event

    async with maker() as s:
        s.add(Event(id=r.TWIN_ID, external_id=r.INCOMING_ODDS_ID, sport_id=1326, home_team_id=16, away_team_id=23,
                    home_team_name="Chicago Fire", away_team_name="Vancouver Whitecaps FC", commence_time=COMMENCE,
                    status="scheduled", statpal_fixture_id="9163448", event_tags=list(TAGS)))
        await s.commit()


@needs_postgres
async def test_restore_deletes_only_this_invocations_row(db, tmp_path):
    f = Flow(db, tmp_path)
    before = await _anchors_table(db)
    sa = await f.stage()
    assert (await f.apply(sa))[0]["state"] == r.APPLIED
    sr = f.stage_restore(sa)
    undo, _ = await f.restore(sr)
    assert undo["state"] == r.RESTORED and undo["counts"]["anchor_rows_deleted"] == 1, undo
    assert await _anchors_table(db) == before
    assert await _step2(db) is None  # the #8278 refusal is back, as it was
    twice, _ = await f.restore(sr)
    assert twice["state"] == r.NOT_APPLIED and r.exit_code(twice) == r.EXIT_OK


@needs_postgres
async def test_restore_refuses_a_recreated_row_carrying_the_same_context(db, tmp_path):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    assert (await f.apply(sa))[0]["state"] == r.APPLIED
    (orig,) = _current_rows(await _anchors_table(db))
    await _exec(db, "DELETE FROM event_provider_anchors WHERE id = :i", i=orig["id"])
    await _exec(db, "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind, claim_context) "
                    "VALUES (:e, 'odds_api', :s, 'game', CAST(:cc AS jsonb))",
                e=r.KEEPER_ID, s=r.CURRENT_ODDS_ID, cc=json.dumps(orig["claim_context"]))
    undo, _ = await f.restore(f.stage_restore(sa))
    assert undo["state"] == r.REFUSED and undo["reason"].startswith("row_is_not_the_created_row:id"), undo
    (row,) = _current_rows(await _anchors_table(db))
    assert row["id"] != orig["id"] and row["claim_context"] == orig["claim_context"]


@needs_postgres
@pytest.mark.parametrize("sql,reason", [
    ("UPDATE event_provider_anchors SET first_seen_at = first_seen_at + interval '1 second' "
     "WHERE source = 'odds_api' AND source_id = :s", "row_is_not_the_created_row:first_seen_at"),
    ("UPDATE event_provider_anchors SET claim_context = claim_context || '{\"touched\": true}'::jsonb "
     "WHERE source = 'odds_api' AND source_id = :s", "row_is_not_the_created_row:claim_context"),
])
async def test_restore_refuses_a_row_changed_after_the_apply(db, tmp_path, sql, reason):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    assert (await f.apply(sa))[0]["state"] == r.APPLIED
    await _exec(db, sql, s=r.CURRENT_ODDS_ID)
    undo, _ = await f.restore(f.stage_restore(sa))
    assert undo["state"] == r.REFUSED and undo["reason"] == reason, undo
    assert len(_current_rows(await _anchors_table(db))) == 1


@needs_postgres
async def test_the_delete_carries_its_own_fence_behind_the_python_check(db, tmp_path, monkeypatch):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    assert (await f.apply(sa))[0]["state"] == r.APPLIED
    sr = f.stage_restore(sa)
    await _exec(db, "UPDATE event_provider_anchors SET first_seen_at = first_seen_at + interval '1 second' "
                    "WHERE source = 'odds_api' AND source_id = :s", s=r.CURRENT_ODDS_ID)
    monkeypatch.setattr(r, "row_is_the_created_row", lambda row, created: [])
    undo, _ = await f.restore(sr)
    assert undo["state"] == r.REFUSED and undo["reason"] == "delete_fence_lost", undo
    assert len(_current_rows(await _anchors_table(db))) == 1


@needs_postgres
async def test_a_failed_verify_after_the_restore_commit_is_commit_unknown(db, tmp_path, monkeypatch):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    assert (await f.apply(sa))[0]["state"] == r.APPLIED
    sr = f.stage_restore(sa)

    async def gone(*_a, **_k):
        raise ConnectionError("dyno gone")

    monkeypatch.setattr(r, "_read_after_restore", gone)
    undo, _ = await f.restore(sr)
    assert undo["state"] == r.COMMIT_UNKNOWN and undo["reason"] == "post_commit_verify_unreadable", undo
    assert r.exit_code(undo) == r.EXIT_COMMIT_UNKNOWN and undo["recovery_read_sql"] == r.RECOVERY_READ_SQL
    assert undo["invocation_id"] and undo["created_row"]["id"] and undo["backup_sha256"]
    assert _current_rows(await _anchors_table(db)) == []  # the delete DID commit; the record says unknown


@needs_postgres
async def test_restore_never_deletes_a_pre_existing_row(db, tmp_path):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    await _exec(db, "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind, claim_context) "
                    "VALUES (:e, 'odds_api', :s, 'game', CAST(:cc AS jsonb))", e=r.KEEPER_ID,
                s=r.CURRENT_ODDS_ID, cc=json.dumps({"source": "odds_api", "schedule_derived": False}))
    res, out = await f.apply(sa)
    assert res["state"] == r.NOT_NEEDED and out.kind("created_row") == [] and f.receipt_file is None, res
    (row,) = _current_rows(await _anchors_table(db))
    assert row["claim_context"] == {"source": "odds_api", "schedule_derived": False}


@needs_postgres
async def test_a_same_owner_row_that_appears_between_read_and_write_is_a_no_op(db, tmp_path, monkeypatch):
    f = Flow(db, tmp_path)
    sa = await f.stage()
    await _exec(db, "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind) "
                    "VALUES (:e, 'odds_api', :s, 'game')", e=r.KEEPER_ID, s=r.CURRENT_ODDS_ID)
    real_read_all = r._read_all

    async def read_before_the_rival(session, *, lock):
        keeper, sport_key, anchors, twin, snaps = await real_read_all(session, lock=lock)
        return keeper, sport_key, {**anchors, "current": None}, twin, snaps

    monkeypatch.setattr(r, "_read_all", read_before_the_rival)
    res, out = await f.apply(sa)
    assert res["state"] == r.NOT_NEEDED and res["reason"] == "current_key_confirmed_at_write", res
    assert out.kind("created_row") == []
    (row,) = _current_rows(await _anchors_table(db))
    assert row["claim_context"] is None


# ─── drive-apply: the host driver with the REAL CLI as its child ─────────────────

def _child_env(url):
    env = {k: v for k, v in os.environ.items() if k not in ("DYNO", "SEARCH_TEST_DATABASE_URL")}
    env.update({"HEROKU_APP_NAME": "bainluck", "DATABASE_URL": url})
    return env


async def _drive(maker, url, tmp_path, **kw):
    f = Flow(maker, tmp_path)
    sa = await f.stage()
    out = await r.drive_apply(
        apply_input=sa["apply_input"]["path"], plan_hash=sa["apply_argv"]["--plan-hash"],
        backup_hash=sa["apply_argv"]["--backup-hash"], output=str(tmp_path / "apply.jsonl"),
        receipt_out=str(tmp_path / "created-row.json"), env=HOST,
        prefix=(sys.executable, str(_TOOL)), child_env=_child_env(url), overall_timeout_s=120, **kw)
    return f, sa, out


@needs_postgres
async def test_drive_apply_retains_the_receipt_then_the_child_commits(drive_db, tmp_path):
    maker, url = drive_db
    f, sa, out = await _drive(maker, url, tmp_path)
    assert out["state"] == r.APPLIED and out["ack_sent"] is True and out["child_exit"] == 0, out
    lines = [json.loads(x) for x in (tmp_path / "apply.jsonl").read_bytes().splitlines()]
    assert [x["record"] for x in lines] == ["created_row", "result"]  # the dyno printed nothing else
    assert (tmp_path / "apply.jsonl.stderr").read_bytes() == b""
    receipt_bytes = (tmp_path / "created-row.json").read_bytes()
    assert hashlib.sha256(receipt_bytes).hexdigest() == lines[0]["receipt_sha256"] == out["receipt"]["sha256"]
    (row,) = _current_rows(await _anchors_table(maker))
    assert r.row_is_the_created_row(row, json.loads(receipt_bytes)["created_row"]) == []
    f.receipt_file = out["receipt"]  # the retained receipt is what restore consumes
    undo, _ = await f.restore(f.stage_restore(sa))
    assert undo["state"] == r.RESTORED, undo


@needs_postgres
async def test_drive_apply_that_cannot_retain_the_receipt_sends_no_ack_and_nothing_commits(
        drive_db, tmp_path, monkeypatch):
    maker, url = drive_db
    real = r.write_host_artifact

    def refuse_receipt(path, doc, what):
        if what == "receipt":
            raise r.Refused("receipt_durability_failed", "disk full")
        return real(path, doc, what)

    monkeypatch.setattr(r, "write_host_artifact", refuse_receipt)
    _, _, out = await _drive(maker, url, tmp_path)
    assert out["ack_sent"] is False and out["receipt"] is None, out
    assert out["state"] == r.REFUSED and out["reason"] == "host_ack_eof", out
    assert _current_rows(await _anchors_table(maker)) == []


@needs_postgres
async def test_drive_apply_with_a_wrong_acknowledgment_commits_nothing(drive_db, tmp_path, monkeypatch):
    maker, url = drive_db
    monkeypatch.setattr(r, "ack_for", lambda receipt: {"schema": r.ACK_SCHEMA, "ack": "created_row_retained",
                                                      "invocation_id": receipt["invocation_id"],
                                                      "receipt_sha256": "0" * 64})
    _, _, out = await _drive(maker, url, tmp_path)
    assert out["ack_sent"] is True and out["state"] == r.REFUSED and out["reason"] == "host_ack_mismatch", out
    assert _current_rows(await _anchors_table(maker)) == []
