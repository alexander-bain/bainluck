"""#10319 — the one-event identity repair: admission, tags, plan/backup files, CLI and refusals.

REHEARSAL DATA ONLY. The specimen below is a synthetic row carrying the exact ids
and identity strings the packet retains (event 15321333, market 63152777,
``KXSERIEAWGAME-26OCT03PARTER``, "Serie A Femminile", Sport 427850). No database,
provider or platform is touched: the transaction harness is an in-memory fake that
answers the tool's tagged statements and models commit / rollback, so every refusal
can be shown to leave the "database" exactly as it was. What the SQL does on a real
server is graded in ``tests/integration/test_repair_10319_event15321333_competition_identity_pg.py``.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_TOOL = _SCRIPTS / "repair_10319_event15321333_competition_identity.py"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location("repair_10319_unit", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


r = _load()

MEN = 7
FIXED = "2026-10-03T21:00:00+00:00"
PRE_TAGS = ["sport:soccer", "gender:men", "league:serie_a", "level:professional",
            "importance:regular", "tier:2", "class:international", "status:completed"]


def _event(**over):
    row = {
        "id": r.EVENT_ID, "sport_id": MEN, "status": "completed",
        "commence_time": datetime.fromisoformat("2026-10-03T10:30:00+00:00"),
        "completed_at": datetime.fromisoformat("2026-10-03T12:24:05.123456+00:00"),
        "home_team_name": "Parma Calcio", "away_team_name": "Ternana",
        "home_team_id": None, "away_team_id": None, "home_score": 0, "away_score": 1,
        "espn_id": None, "external_id": "kalshi_KXSERIEAWGAME-26OCT03PARTER",
        "llm_gender": "men", "llm_level": "professional", "llm_league": "Serie_A",
        "llm_importance": "regular", "event_tags": list(PRE_TAGS),
        "win_probability_sources": {"kalshi": {"home": 0.31}},
    }
    row.update(over)
    return row


def _sports():
    return [
        {"id": MEN, "key": r.MEN_SPORT_KEY, "name": "Serie A - Italy", "group": "Soccer", "active": True},
        {"id": r.WOMEN_SPORT_ID, "key": r.WOMEN_SPORT_KEY, "name": r.WOMEN_SPORT_NAME,
         "group": "Soccer", "active": True},
    ]


def _market(**over):
    m = {"id": r.MARKET_ID, "event_id": r.EVENT_ID, "source": "kalshi",
         "external_id": "KXSERIEAWGAME-26OCT03PARTER", "competition": "Serie A Femminile",
         "competition_scope": "Game", "sport_id": MEN, "sport_key": r.MEN_SPORT_KEY}
    m.update(over)
    return m


def _admit(event=None, sports=None, market="default", linked=None, teams=None):
    return r.admit(
        _event() if event is None else event,
        _sports() if sports is None else sports,
        _market() if market == "default" else market,
        [r.MARKET_ID] if linked is None else linked,
        {} if teams is None else teams,
    )


# --- tags ---------------------------------------------------------------------

def test_tags_substitute_in_place_and_keep_every_other_position():
    post = r.substitute_tags(PRE_TAGS)
    assert post == ["sport:soccer", "gender:women", "league:serie_a_femminile",
                    "level:professional", "importance:regular", "tier:4", "class:other",
                    "status:completed"]
    assert PRE_TAGS[1] == "gender:men"  # input untouched


@pytest.mark.parametrize("tags, reason", [
    ([t for t in PRE_TAGS if t != "tier:2"], "old_tag_not_exactly_once"),
    (PRE_TAGS + ["league:serie_a"], "old_tag_not_exactly_once"),
    (PRE_TAGS + ["class:other"], "new_tag_already_present"),
    (PRE_TAGS + ["gender:women"], "new_tag_already_present"),
    (None, "event_tags_not_a_string_array"),
    ({"gender": "men"}, "event_tags_not_a_string_array"),
    (PRE_TAGS + [3], "event_tags_not_a_string_array"),
])
def test_tags_refuse_absent_duplicated_or_present(tags, reason):
    with pytest.raises(r.Refused) as exc:
        r.substitute_tags(tags)
    assert exc.value.reason == reason


# --- admission ----------------------------------------------------------------

def test_admit_positive_names_one_row_four_columns():
    body = _admit()
    assert body["write_allowlist"] == {"table": "events", "id": r.EVENT_ID,
                                       "columns": ["sport_id", "llm_gender", "llm_league", "event_tags"]}
    assert body["post_image"]["sport_id"] == r.WOMEN_SPORT_ID
    assert body["pre_image"]["completed_at"] == "2026-10-03T12:24:05.123456+00:00"
    assert body["corroboration"]["market_recorded"] == {"sport_id": MEN, "sport_key": r.MEN_SPORT_KEY}
    assert body["corroboration"]["linked_set"] == [r.MARKET_ID]
    assert [s["verdict"] for s in body["team_compatibility"]] == ["NULL_FK", "NULL_FK"]


@pytest.mark.parametrize("kwargs, reason", [
    ({"event": None}, None),  # placeholder replaced below
    ({"event": _event(llm_gender="women")}, "event_gender_not_men"),
    ({"event": _event(llm_league="Serie_A_Femminile")}, "event_league_not_serie_a"),
    ({"event": _event(sport_id=r.WOMEN_SPORT_ID)}, "event_not_on_men_sport"),
    ({"event": _event(sport_id=99)}, "event_not_on_men_sport"),
    ({"sports": _sports()[:1]}, "target_sport_not_unique"),
    ({"sports": [_sports()[0], {**_sports()[1], "name": "Serie A Women"}]}, "target_sport_mismatch"),
    ({"sports": [_sports()[0], {**_sports()[1], "active": False}]}, "target_sport_mismatch"),
    ({"sports": [_sports()[0], {**_sports()[1], "group": "Football"}]}, "target_sport_mismatch"),
    ({"sports": [_sports()[0], {**_sports()[1], "id": 427851}]}, "target_sport_not_unique"),
    ({"sports": _sports() + [{**_sports()[1], "id": 427851}]}, "target_sport_not_unique"),
    ({"sports": _sports()[1:]}, "men_sport_not_unique"),
    ({"market": None}, "identity_missing:market"),
    ({"market": _market(event_id=15321317)}, "identity_conflict:event_id"),
    ({"market": _market(event_id=None)}, "identity_conflict:event_id"),
    ({"market": _market(source="polymarket")}, "identity_conflict:source"),
    ({"market": _market(external_id="KXSERIEAGAME-26OCT03PARTER")}, "identity_conflict:external_id"),
    ({"market": _market(external_id="KXSERIEAWGAME-26OCT03PARTERX")}, "identity_conflict:external_id"),
    ({"market": _market(external_id=None)}, "identity_conflict:external_id"),
    ({"market": _market(competition="Serie A")}, "identity_conflict:competition"),
    ({"market": _market(competition=None)}, "identity_conflict:competition"),
    ({"market": _market(competition_scope="Season")}, "identity_conflict:competition_scope"),
    ({"market": _market(competition_scope="")}, "identity_conflict:competition_scope"),
    ({"linked": [r.MARKET_ID, 63152778]}, "linked_set_not_exact"),
    ({"linked": []}, "linked_set_not_exact"),
])
def test_admit_refuses(kwargs, reason):
    if kwargs == {"event": None}:
        with pytest.raises(r.Refused) as exc:
            r.admit(None, _sports(), _market(), [r.MARKET_ID], {})
        assert exc.value.reason == "event_missing"
        return
    with pytest.raises(r.Refused) as exc:
        _admit(**kwargs)
    assert exc.value.reason == reason


def test_admit_accepts_ticker_family_member_null_scope_and_spacing():
    assert _admit(market=_market(external_id="KXSERIEAWGAME-26OCT03PARTER-PAR"))
    assert _admit(market=_market(competition_scope=None))
    body = _admit(market=_market(competition="  serie a FEMMINILE "))
    assert body["corroboration"]["market_identity"]["competition"] == "  serie a FEMMINILE "


def test_admit_never_takes_identity_from_club_names():
    """Women's-sounding names do not rescue a men's market; men's names do not block a women's one."""
    with pytest.raises(r.Refused):
        _admit(event=_event(home_team_name="Parma Women"), market=_market(competition="Serie A"))
    assert _admit(event=_event(home_team_name="Parma Calcio", away_team_name="Ternana"))


@pytest.mark.parametrize("home_id, teams, verdict, ok", [
    (None, {}, "NULL_FK", True),
    (901, {901: {"id": 901, "name": "Parma Calcio", "sport_id": r.WOMEN_SPORT_ID}}, "SOUND", True),
    (901, {901: {"id": 901, "name": "Parma Calcio", "sport_id": None}}, "SOUND", True),
    (901, {}, "DANGLING_FK", False),
    (903, {903: {"id": 903, "name": "Parma Calcio", "sport_id": MEN}}, "WRONG_SPORT", False),
    (904, {904: {"id": 904, "name": "Genoa", "sport_id": r.WOMEN_SPORT_ID}}, "CROSS_CLUB", False),
])
def test_p3_team_binding_judged_against_the_proposed_sport(home_id, teams, verdict, ok):
    event = _event(home_team_id=home_id)
    if ok:
        body = _admit(event=event, teams=teams)
        assert body["team_compatibility"][0]["verdict"] == verdict
        return
    with pytest.raises(r.Refused) as exc:
        _admit(event=event, teams=teams)
    assert exc.value.reason == r.TEAM_BINDING_SCOPE_REQUIRED
    assert exc.value.detail[0]["verdict"] == verdict and exc.value.detail[0]["team_id"] == home_id


def test_p3_consumes_the_existing_predicate_not_a_copy(monkeypatch):
    calls = []

    def spy(*a):
        calls.append(a)
        return True

    monkeypatch.setattr(r, "binding_is_sound", spy)
    _admit(event=_event(home_team_id=901),
           teams={901: {"id": 901, "name": "X", "sport_id": MEN}})
    assert calls == [("Parma Calcio", "X", MEN, r.WOMEN_SPORT_ID)]


# --- content address ------------------------------------------------------------

def _payload():
    return {"schema": r.PLAN_SCHEMA, **_admit(), "pins": {"tool": r.TOOL}, "planned_at": FIXED}


def _paths(obj, prefix=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _paths(v, prefix + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _paths(v, prefix + (i,))
    else:
        yield prefix


def _set(obj, path, value):
    for k in path[:-1]:
        obj = obj[k]
    obj[path[-1]] = value


def test_address_moves_with_every_written_fenced_and_identity_value():
    base = _payload()
    addr = r.content_address(r.PLAN_SCHEMA, base)
    leaves = [p for p in _paths(base)
              if p[0] in ("pre_image", "post_image", "corroboration", "team_compatibility",
                          "banked_unwritten", "write_allowlist", "fenced_columns")]
    assert len(leaves) > 40
    for path in leaves:
        for replacement in ("", None, "__changed__"):
            mutated = copy.deepcopy(base)
            cur = mutated
            for k in path:
                cur = cur[k]
            if cur == replacement:
                continue
            _set(mutated, path, replacement)
            assert r.content_address(r.PLAN_SCHEMA, mutated) != addr, path


def test_address_distinguishes_null_from_empty_and_ignores_its_own_field():
    a = _payload()
    b = copy.deepcopy(a)
    a["pre_image"]["espn_id"], b["pre_image"]["espn_id"] = None, ""
    assert r.content_address(r.PLAN_SCHEMA, a) != r.content_address(r.PLAN_SCHEMA, b)
    c = copy.deepcopy(a)
    c["content_address"] = "anything"
    assert r.content_address(r.PLAN_SCHEMA, c) == r.content_address(r.PLAN_SCHEMA, a)
    assert r.content_address(r.BACKUP_SCHEMA, a) != r.content_address(r.PLAN_SCHEMA, a)


# --- durable files ----------------------------------------------------------------

def _write_plan(tmp_path, name="plan.json"):
    body = {**_admit(), "pins": {"tool": r.TOOL}, "planned_at": FIXED}
    return r.write_artifact(str(tmp_path / name), r.PLAN_SCHEMA, body, "plan")


def test_artifact_is_exclusive_read_only_with_a_detached_digest(tmp_path):
    out = _write_plan(tmp_path)
    data = Path(out["path"]).read_bytes()
    import hashlib
    assert hashlib.sha256(data).hexdigest() == out["sha256"]
    assert out["sha256"] not in data.decode()  # the file never carries its own final-byte hash
    assert Path(out["path"] + ".sha256").read_text() == f"{out['sha256']}  plan.json\n"
    assert oct(os.stat(out["path"]).st_mode & 0o777) == "0o444"
    assert json.loads(data)["content_address"] == out["content_address"]
    with pytest.raises(r.Refused) as exc:
        _write_plan(tmp_path)
    assert exc.value.reason == "plan_path_exists"


def test_artifact_refuses_relative_or_missing_directory(tmp_path):
    with pytest.raises(r.Refused) as exc:
        r.write_artifact("plan.json", r.PLAN_SCHEMA, {}, "plan")
    assert exc.value.reason == "plan_path_not_absolute"
    with pytest.raises(r.Refused) as exc:
        r.write_artifact(str(tmp_path / "nope" / "p.json"), r.PLAN_SCHEMA, {}, "plan")
    assert exc.value.reason == "plan_directory_missing"


def test_artifact_refuses_when_a_stale_sidecar_exists(tmp_path):
    (tmp_path / "plan.json.sha256").write_text("x")
    with pytest.raises(r.Refused) as exc:
        _write_plan(tmp_path)
    assert exc.value.reason == "plan_path_exists"


def test_fsync_failure_refuses(tmp_path, monkeypatch):
    def boom(fd):
        raise OSError(5, "EIO")

    monkeypatch.setattr(r, "_fsync", boom)
    with pytest.raises(r.Refused) as exc:
        _write_plan(tmp_path)
    assert exc.value.reason == "plan_durability_failed"


def _rewrite(path, payload):
    """Replace an artifact's bytes and sidecar consistently (a well-formed forgery)."""
    import hashlib
    data = (r.canonical_json(payload) + "\n").encode()
    os.chmod(path, 0o644)
    os.chmod(path + ".sha256", 0o644)
    Path(path).write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    Path(path + ".sha256").write_text(f"{digest}  {os.path.basename(path)}\n")
    return digest


def test_load_artifact_positive(tmp_path):
    out = _write_plan(tmp_path)
    plan = r.load_artifact(out["path"], out["sha256"].upper(), r.PLAN_SCHEMA, "plan")
    assert plan["event_id"] == r.EVENT_ID


@pytest.mark.parametrize("case, reason", [
    ("missing", "plan_missing"),
    ("relative", "plan_path_not_absolute"),
    ("malformed_hash", "plan_hash_malformed"),
    ("wrong_hash", "plan_hash_mismatch"),
    ("byte_edit", "plan_hash_mismatch"),
    ("sidecar", "plan_sidecar_mismatch"),
    ("no_sidecar", "plan_missing"),
    ("corrupt", "plan_corrupt"),
    ("schema", "plan_wrong_schema"),
    ("address", "plan_address_mismatch"),
    ("scope", "plan_scope_mismatch"),
    ("post", "plan_post_image_incoherent"),
])
def test_load_artifact_refuses(tmp_path, case, reason):
    out = _write_plan(tmp_path)
    path, digest = out["path"], out["sha256"]
    payload = json.loads(Path(path).read_bytes())
    if case == "missing":
        path = str(tmp_path / "absent.json")
    elif case == "relative":
        path = "plan.json"
    elif case == "malformed_hash":
        digest = "abc"
    elif case == "wrong_hash":
        digest = "0" * 64
    elif case == "byte_edit":
        os.chmod(path, 0o644)
        Path(path).write_bytes(Path(path).read_bytes().replace(b"Ternana", b"Ternanb"))
    elif case == "sidecar":
        os.chmod(path + ".sha256", 0o644)
        Path(path + ".sha256").write_text(f"{'1' * 64}  plan.json\n")
    elif case == "no_sidecar":
        os.chmod(path + ".sha256", 0o644)
        os.remove(path + ".sha256")
    elif case == "corrupt":
        os.chmod(path, 0o644)
        os.chmod(path + ".sha256", 0o644)
        Path(path).write_bytes(b"{not json")
        import hashlib
        digest = hashlib.sha256(b"{not json").hexdigest()
        Path(path + ".sha256").write_text(f"{digest}  plan.json\n")
    elif case == "schema":
        payload["schema"] = r.BACKUP_SCHEMA
        payload["content_address"] = r.content_address(r.BACKUP_SCHEMA, payload)
        digest = _rewrite(path, payload)
    elif case == "address":
        payload["post_image"]["llm_league"] = "Serie_A_Women"  # address left stale
        digest = _rewrite(path, payload)
    elif case == "scope":
        payload["write_allowlist"]["columns"].append("status")
        payload["content_address"] = r.content_address(r.PLAN_SCHEMA, payload)
        digest = _rewrite(path, payload)
    elif case == "post":
        payload["post_image"]["event_tags"] = sorted(payload["post_image"]["event_tags"])
        payload["content_address"] = r.content_address(r.PLAN_SCHEMA, payload)
        digest = _rewrite(path, payload)
    with pytest.raises(r.Refused) as exc:
        r.load_artifact(path, digest, r.PLAN_SCHEMA, "plan")
    assert exc.value.reason == reason


# --- the transaction harness ----------------------------------------------------

class _Result:
    def __init__(self, rows, rowcount=None):
        self._rows = rows
        self.rowcount = len(rows) if rowcount is None else rowcount

    def mappings(self):
        return self

    def all(self):
        return [dict(x) for x in self._rows]


class FakeDB:
    """Committed state + per-session pending copy, answering the tool's tagged SQL."""

    def __init__(self, event=None, market="default", teams=None, linked=None):
        self.event = _event() if event is None else event
        self.sports = _sports()
        self.market = _market() if market == "default" else market
        self.teams = teams or {}
        self.linked = [r.MARKET_ID] if linked is None else linked
        self.sessions = 0
        self.statements: list[str] = []
        self.updates = 0
        self.commits = 0
        self.force_rowcount = None
        self.force_returning = None
        self.commit_raises = False
        self.commit_lands = True
        self.readback_raises = False
        self.after_commit = None
        self.update_side_effect = None

    def factory(self):
        db = self

        @asynccontextmanager
        async def cm():
            db.sessions += 1
            yield FakeSession(db)

        return cm()


class FakeSession:
    def __init__(self, db):
        self.db = db
        self.pending = copy.deepcopy(db.event)
        self.wrote = False

    async def execute(self, stmt, params=None):
        sql = getattr(stmt, "text", str(stmt))
        self.db.statements.append(sql)
        params = params or {}
        tag = re.search(r"r10319:(\w+)", sql)
        if tag is None:
            assert sql.startswith(("SET TRANSACTION", "SET LOCAL")), sql
            return _Result([])
        tag = tag.group(1)
        if tag in ("R1", "R1_LOCK"):
            if self.db.readback_raises and self.db.commits:
                raise ConnectionError("gone")
            assert params == {"eid": r.EVENT_ID}
            ev = copy.deepcopy(self.pending)
            ev["event_tags"] = json.dumps(ev["event_tags"])  # jsonb arrives as text
            return _Result([ev])
        if tag in ("R2", "R2_LOCK"):
            return _Result(self.db.sports)
        if tag in ("R3", "R3_LOCK"):
            assert params == {"mid": r.MARKET_ID}
            if self.db.market is None:
                return _Result([])
            m = dict(self.db.market)
            if tag == "R3_LOCK":
                m.pop("sport_id"), m.pop("sport_key")
            return _Result([m])
        if tag in ("R4", "R4_LOCK"):
            return _Result([{"id": i} for i in self.db.linked])
        if tag in ("R5", "R5_LOCK"):
            return _Result([self.db.teams[i] for i in params["ids"] if i in self.db.teams])
        if tag in ("APPLY", "RESTORE"):
            self.db.updates += 1
            match = all(
                r.canon(self.pending[c]) == (json.loads(params[f"cas_{c}"]) if c == "event_tags"
                                             and params[f"cas_{c}"] is not None
                                             else r.canon(params[f"cas_{c}"]))
                for c in r.COMPARED_COLUMNS
            )
            rows = []
            if match:
                for c in r.WRITTEN_COLUMNS:
                    v = params[f"new_{c}"]
                    self.pending[c] = json.loads(v) if c == "event_tags" else v
                self.wrote = True
                if self.db.update_side_effect:
                    self.db.update_side_effect(self.pending)
                rows = [{"id": r.EVENT_ID, **{c: self.pending[c] for c in r.WRITTEN_COLUMNS}}]
            if self.db.force_returning is not None and rows:
                rows = [dict(rows[0], **self.db.force_returning)]
            return _Result(rows, self.db.force_rowcount)
        raise AssertionError(f"unexpected statement {sql[:80]}")

    async def commit(self):
        if self.db.commit_raises:
            if self.db.commit_lands:
                self.db.event = self.pending
            if self.db.after_commit:
                self.db.after_commit(self.db)
            self.db.commits += 1
            raise ConnectionError("connection lost during COMMIT")
        self.db.event = self.pending
        self.db.commits += 1

    async def rollback(self):
        self.pending = copy.deepcopy(self.db.event)


async def _plan(tmp_path, db):
    out = await r.run_preflight(db.factory, plan_out=str(tmp_path / "plan.json"), clock=lambda: FIXED)
    assert out["state"] == r.PLANNED, out
    return out["plan"]


async def _apply(tmp_path, db, plan):
    return await r.run_apply(db.factory, plan_path=plan["path"], plan_hash=plan["sha256"],
                             backup_out=str(tmp_path / "backup.json"), clock=lambda: FIXED)


async def test_preflight_is_read_only_and_writes_the_plan(tmp_path):
    db = FakeDB()
    before = copy.deepcopy(db.event)
    out = await r.run_preflight(db.factory, plan_out=str(tmp_path / "plan.json"), clock=lambda: FIXED)
    assert out["state"] == r.PLANNED and out["counts"]["written_rows"] == 0
    assert db.statements[0].startswith("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    assert db.updates == 0 and db.commits == 0 and db.event == before
    assert not any("FOR UPDATE" in s or "FOR SHARE" in s for s in db.statements)


async def test_preflight_refusal_writes_no_plan(tmp_path):
    db = FakeDB(market=None)
    out = await r.run_preflight(db.factory, plan_out=str(tmp_path / "plan.json"), clock=lambda: FIXED)
    assert out["state"] == r.REFUSED and out["reason"] == "identity_missing:market"
    assert not (tmp_path / "plan.json").exists() and r.exit_code(out) == 1


async def test_preflight_refuses_an_existing_plan_path_before_reading(tmp_path):
    (tmp_path / "plan.json").write_text("old")
    db = FakeDB()
    out = await r.run_preflight(db.factory, plan_out=str(tmp_path / "plan.json"), clock=lambda: FIXED)
    assert out["reason"] == "plan_path_exists" and db.sessions == 0


async def test_apply_positive_then_restore_positive(tmp_path):
    db = FakeDB()
    before = copy.deepcopy(db.event)
    plan = await _plan(tmp_path, db)
    out = await _apply(tmp_path, db, plan)
    assert out["state"] == r.APPLIED, out
    assert out["counts"] == {"event_id": r.EVENT_ID, "written_rows": 1, "written_columns": 4,
                             "concurrent_drift": 0}
    assert db.updates == 1 and db.event["sport_id"] == r.WOMEN_SPORT_ID
    assert {c for c in before if before[c] != db.event[c]} == set(r.WRITTEN_COLUMNS)
    assert any("FOR UPDATE" in s for s in db.statements)
    assert sum("FOR SHARE" in s for s in db.statements) == 3  # sports, market, linked (no teams)
    restored = await r.run_restore(db.factory, backup_path=out["backup"]["path"],
                                   backup_hash=out["backup"]["sha256"])
    assert restored["state"] == r.APPLIED and db.event == before
    assert Path(out["receipt"]["path"]).exists() and Path(restored["receipt"]["path"]).exists()


async def test_apply_never_rederives_from_the_database(tmp_path, monkeypatch):
    """Apply reads the plan's own pre-image tags only; it never re-admits or reclassifies."""
    db = FakeDB()
    plan = await _plan(tmp_path, db)
    planned_tags = json.loads(Path(plan["path"]).read_bytes())["pre_image"]["event_tags"]
    seen, original = [], r.substitute_tags
    monkeypatch.setattr(r, "admit", lambda *a, **k: pytest.fail("apply re-ran admission"))
    monkeypatch.setattr(r, "substitute_tags", lambda t: seen.append(list(t)) or original(t))
    out = await _apply(tmp_path, db, plan)
    assert out["state"] == r.APPLIED
    assert seen and all(t == planned_tags for t in seen)


@pytest.mark.parametrize("force, reason", [
    ({"force_rowcount": 0}, "fence_lost"),
    ({"force_rowcount": 2}, "fence_lost"),
    ({"force_returning": {"llm_league": "Serie_A"}}, "post_write_mismatch"),
    ({"force_returning": {"id": 15321317}}, "post_write_mismatch"),
])
async def test_count_and_returning_mismatch_roll_back(tmp_path, force, reason):
    db = FakeDB()
    before = copy.deepcopy(db.event)
    plan = await _plan(tmp_path, db)
    for k, v in force.items():
        setattr(db, k, v)
    out = await _apply(tmp_path, db, plan)
    assert out["state"] == r.REFUSED and out["reason"] == reason, out
    assert db.commits == 0 and db.event == before and out["counts"]["written_rows"] == 0


@pytest.mark.parametrize("effect", [
    lambda row: row.__setitem__("win_probability_sources", {"kalshi": {"home": 0.99}}),
    lambda row: row.__setitem__("espn_id", "700001"),
])
async def test_in_transaction_readback_catches_a_write_beyond_four_columns(tmp_path, effect):
    """A trigger/rewrite touching the banked hero or a fenced column inside the write rolls back."""
    db = FakeDB()
    before = copy.deepcopy(db.event)
    plan = await _plan(tmp_path, db)
    db.update_side_effect = effect
    out = await _apply(tmp_path, db, plan)
    assert out["state"] == r.REFUSED and out["reason"] == "in_transaction_readback_mismatch", out
    assert db.commits == 0 and db.event == before


async def test_backup_is_banked_before_any_connection_and_fsync_failure_writes_nothing(tmp_path, monkeypatch):
    db = FakeDB()
    plan = await _plan(tmp_path, db)
    opened = db.sessions

    def boom(fd):
        raise OSError(28, "ENOSPC")

    monkeypatch.setattr(r, "_fsync", boom)
    out = await _apply(tmp_path, db, plan)
    assert out["state"] == r.REFUSED and out["reason"] == "backup_durability_failed"
    assert db.sessions == opened and db.updates == 0


async def test_apply_refuses_backup_path_reuse(tmp_path):
    db = FakeDB()
    plan = await _plan(tmp_path, db)
    (tmp_path / "backup.json").write_text("{}")
    out = await _apply(tmp_path, db, plan)
    assert out["reason"] == "backup_path_exists" and db.updates == 0


async def test_apply_refuses_a_wrong_plan_hash_before_connecting(tmp_path):
    db = FakeDB()
    plan = await _plan(tmp_path, db)
    opened = db.sessions
    out = await r.run_apply(db.factory, plan_path=plan["path"], plan_hash="f" * 64,
                            backup_out=str(tmp_path / "backup.json"))
    assert out["reason"] == "plan_hash_mismatch" and db.sessions == opened
    assert not (tmp_path / "backup.json").exists()


@pytest.mark.parametrize("lands, after, state, code", [
    (False, None, r.NOT_APPLIED, 1),
    (True, None, r.APPLIED, 0),
    (True, lambda db: db.event.__setitem__("home_score", 5), r.COMMIT_UNKNOWN, 3),
])
async def test_commit_ambiguity_is_classified_and_never_reapplied(tmp_path, lands, after, state, code):
    db = FakeDB()
    plan = await _plan(tmp_path, db)
    db.commit_raises, db.commit_lands, db.after_commit = True, lands, after
    out = await _apply(tmp_path, db, plan)
    assert out["state"] == state and out["reason"] == "commit_ambiguous", out
    assert db.updates == 1 and r.exit_code(out) == code


async def test_commit_ambiguity_with_unreadable_row_is_commit_unknown(tmp_path):
    db = FakeDB()
    plan = await _plan(tmp_path, db)
    db.commit_raises, db.readback_raises = True, True
    out = await _apply(tmp_path, db, plan)
    assert out["state"] == r.COMMIT_UNKNOWN and db.updates == 1 and r.exit_code(out) == 3


async def test_restore_refuses_with_post_image_drift_and_reports_before_image_noop(tmp_path):
    db = FakeDB()
    plan = await _plan(tmp_path, db)
    out = await _apply(tmp_path, db, plan)
    db.event["event_tags"] = list(reversed(db.event["event_tags"]))
    later = copy.deepcopy(db.event)
    refused = await r.run_restore(db.factory, backup_path=out["backup"]["path"],
                                  backup_hash=out["backup"]["sha256"])
    assert refused["state"] == r.REFUSED and refused["reason"] == "restore_after_drift:event_tags"
    assert db.event == later
    other = tmp_path / "second"
    other.mkdir()
    db2 = FakeDB()
    plan2 = await _plan(other, db2)
    out2 = await _apply(other, db2, plan2)
    assert out2["state"] == r.APPLIED
    db2.event = copy.deepcopy(_event())
    noop = await r.run_restore(db2.factory, backup_path=out2["backup"]["path"],
                               backup_hash=out2["backup"]["sha256"])
    assert noop["state"] == r.NOT_APPLIED and noop["reason"] == "already_at_before_image"
    assert r.exit_code(noop) == 0 and noop["counts"]["written_rows"] == 0


async def test_database_errors_inside_the_transaction_refuse(tmp_path):
    db = FakeDB()
    plan = await _plan(tmp_path, db)

    class _Orig:
        sqlstate = "55P03"

    class _DBErr(Exception):
        orig = _Orig()

    async def broken(self, stmt, params=None):
        raise _DBErr("canceling statement due to lock timeout")

    FakeSession.execute, saved = broken, FakeSession.execute
    try:
        out = await _apply(tmp_path, db, plan)
    finally:
        FakeSession.execute = saved
    assert out["state"] == r.REFUSED and out["reason"] == "lock_timeout" and db.commits == 0


# --- selector, target and scope fences ------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["--only", "15321317"],
    ["--only", "15321333", "--only", "15321333"],
    ["--only", "15321333", "--only", "15321298"],
    ["--preflight"],
    ["--only", "15321333"],  # preflight needs --plan-out
    ["--only", "15321333", "--apply", "--plan", "/p", "--plan-hash", "h"],
    ["--only", "15321333", "--restore", "--backup", "/b"],
    ["--only", "15321333", "--plan-out", "/p", "--backup", "/b"],
    ["--only", "15321333", "--apply", "--restore"],
])
def test_cli_usage_errors_exit_2(argv):
    with pytest.raises(SystemExit) as exc:
        r.parse(argv)
    assert exc.value.code == 2


async def test_cli_refuses_the_wrong_app_before_any_connection(monkeypatch, capsys):
    monkeypatch.setattr(r, "_engine_factory", lambda: pytest.fail("connected"))
    for env in ({}, {"HEROKU_APP_NAME": "bainluck-heavy"}, {"HEROKU_APP_NAME": "bainluck-staging"}):
        code = await r.main(["--only", "15321333", "--plan-out", "/tmp/p.json"], env=env)
        assert code == 1
        assert json.loads(capsys.readouterr().out)["reason"] == "target_app_refused"


def test_help_needs_no_database_provider_or_platform():
    env = {"PATH": os.environ.get("PATH", ""), "DATABASE_URL": "postgresql://nobody@256.0.0.1:1/x"}
    proc = subprocess.run([sys.executable, str(_TOOL), "--help"], capture_output=True, text=True,
                          env=env, cwd=str(_SCRIPTS.parent), timeout=60)
    assert proc.returncode == 0 and "--only" in proc.stdout


def test_no_provider_redis_task_or_publish_reach():
    src = _TOOL.read_text()
    for banned in ("app.services.kalshi", "app.services.polymarket", "httpx", "requests",
                   "aiohttp", "redis", "celery", "get_task_session", "publish", "app.tasks"):
        assert banned not in src.split('"""', 2)[2], banned
    body = src.split('"""', 2)[2]
    assert "subprocess" not in body and "heroku run" not in body  # no platform call


def test_every_statement_is_pinned_to_the_exact_ids():
    stmts = {k: v.text for k, v in vars(r).items() if k.startswith("_R") or k in ("_APPLY", "_RESTORE")}
    assert set(stmts) >= {"_R1", "_R1_LOCK", "_R2", "_R2_LOCK", "_R3", "_R3_LOCK",
                          "_R4", "_R4_LOCK", "_R5", "_R5_LOCK", "_APPLY", "_RESTORE"}
    for name, sql in stmts.items():
        assert not re.search(r"\b\d{3,}\b", sql), name  # ids are bound, never inlined
        assert "LIKE" not in sql.upper() and "ILIKE" not in sql.upper(), name
        if re.search(r"\*/ UPDATE ", sql):
            assert "UPDATE events SET" in sql and "WHERE id = :eid" in sql, name
            assert "futures_markets SET" not in sql and "teams SET" not in sql
        else:
            assert re.search(r"\*/ SELECT ", sql), name
    assert "sport_id = " not in stmts["_R1"].split("WHERE")[1]  # no R6-style sport scan


def test_write_scope_constants_match_the_admitted_packet():
    assert r.WRITTEN_COLUMNS == ("sport_id", "llm_gender", "llm_league", "event_tags")
    assert len(r.FENCED_COLUMNS) == 13 and not set(r.FENCED_COLUMNS) & set(r.WRITTEN_COLUMNS)
    assert r.BANKED_ONLY_COLUMN not in r.COMPARED_COLUMNS
    assert (r.EVENT_ID, r.MARKET_ID, r.WOMEN_SPORT_ID) == (15321333, 63152777, 427850)
    assert r.PRODUCTION_APPS == frozenset({"bainluck"})


@pytest.mark.parametrize("result, code", [
    ({"mode": "preflight", "state": "PLANNED"}, 0),
    ({"mode": "apply", "state": "APPLIED"}, 0),
    ({"mode": "apply", "state": "NOT_APPLIED", "reason": "commit_ambiguous"}, 1),
    ({"mode": "restore", "state": "NOT_APPLIED", "reason": "already_at_before_image"}, 0),
    ({"mode": "apply", "state": "REFUSED"}, 1),
    ({"mode": "apply", "state": "COMMIT_UNKNOWN"}, 3),
])
def test_exit_codes(result, code):
    assert r.exit_code(result) == code
