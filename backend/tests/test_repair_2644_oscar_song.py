"""#2644 — the Oscars row's repair channel: frozen, bounded, and honest about a commit it cannot see.

PILLAR: TRUTH. SHIP: the decided 2026 Best Original Song question stops
appearing Open with a December resolution date, through an exact-id reversible
lifecycle correction.

No database here: the frozen channel and its retained authority, every session
site's budgets, the nine-row rail left byte-identical where it is shared, and
a commit whose acknowledgement never returns reported as UNKNOWN — never as
rolled back. The real-Postgres half is
``tests/integration/test_kalshi_oscar_song_repair_2644_pg.py``.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "repair_2644_oscar_song.py"
#: sha256 of the nine-row rail's statements as #2722 certified them (CERT-4168,
#: 6a07e0c746), json.dumps(SQL, sort_keys=True). The channel seam must leave
#: every byte of them alone.
NINE_SQL_SHA256 = "31590b39b10cf87806b4f18729dd8252b8111a2118753cf9a73856588f504036"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def oscar():
    return _load("repair_2644_oscar_song")


@pytest.fixture
def nine():
    return _load("repair_2722_archived_nine")


# ── the frozen channel ────────────────────────────────────────────────────────


def test_the_channel_is_one_exact_row_with_its_own_manifest_and_table(oscar, nine):
    assert oscar.MEMBERS == ((109548, "KXOSCARSONG-26"),)
    assert {i for i, _ in oscar.MEMBERS}.isdisjoint({i for i, _ in nine.NINE})
    assert oscar.BACKUP_TABLE == "backup_2644_oscar_song" != nine.BACKUP_TABLE
    assert oscar.MANIFEST_SHA256 != nine.MANIFEST_SHA256
    raw = (oscar.EVIDENCE_DIR / "manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == oscar.MANIFEST_SHA256
    assert oscar.REVIEWED_WRITE == {
        "market_id": 109548, "ticker": "KXOSCARSONG-26",
        "resolution_date": "2026-03-16T02:11:07+00:00",
        "expiration_time": "2026-12-31T15:00:00+00:00", "venue_settled": True,
    }


def test_the_retained_bytes_are_the_ones_review_hashed(oscar):
    """Copied byte for byte from the retained originals (006 archive, pass 0396)."""
    manifest = json.loads((oscar.EVIDENCE_DIR / "manifest.json").read_text())
    by_file = {e["file"]: e["sha256"] for e in manifest["responses"] + [manifest["identity"]]}
    assert by_file == {
        "archive.json": "68c6ff4feb54e461e6d369494236c9f51e867de869b6243a3865f2f53af6722e",
        "live_listing.json": "50699ea1db13415ea46ec367dcfa58decd9660083271c5dc061561f38337fbac",
        "event.json": "bd97a8cf3b905cf898fc77aef8c1582e97a0b512c8c6704ea8eb2ab78e6456ad",
    }
    ev = oscar.load_evidence()
    assert set(ev) == {"KXOSCARSONG-26"} and set(ev["KXOSCARSONG-26"]) == {"live", "archive"}


def test_tampered_evidence_is_refused(oscar, tmp_path):
    for name in ("live_listing.json", "archive.json", "event.json", "manifest.json"):
        d = tmp_path / name
        shutil.copytree(oscar.EVIDENCE_DIR, d)
        (d / name).write_bytes((d / name).read_bytes() + b" ")
        with pytest.raises(oscar.Refused):
            oscar.load_evidence(d)


def _bodies(oscar):
    d = oscar.EVIDENCE_DIR
    return json.loads((d / "event.json").read_text()), json.loads((d / "archive.json").read_text())


def _set(key, value):
    def f(body):
        body[key] = value
        return body
    return f


def _legs(fn):
    def f(body):
        for i, leg in enumerate(body["markets"]):
            fn(i, leg)
        return body
    return f


@pytest.mark.parametrize("name,event_fn,archive_fn,why", [
    ("another event", lambda e: {**e, "event": {**e["event"], "event_ticker": "KXOSCARSONG-27"}}, None, "not KXOSCARSONG-26"),
    ("another series", lambda e: {**e, "event": {**e["event"], "series_ticker": "KXOSCARSCORE"}}, None, "not KXOSCARSONG-26"),
    ("live legs", lambda e: {**e, "markets": [{"ticker": "KXOSCARSONG-26-GOL"}]}, None, "lists legs"),
    ("empty archive", None, _set("markets", []), "empty or not exhausted"),
    ("unexhausted archive", None, _set("cursor", "more"), "empty or not exhausted"),
    ("a foreign leg", None, _legs(lambda i, leg: i == 0 and leg.update(event_ticker="KXOSCARSONG-27")), "names another event"),
    ("a short listing", None, lambda b: {**b, "markets": b["markets"][:15]}, "16 distinct legs"),
    ("a repeated leg", None, lambda b: {**b, "markets": b["markets"][:15] + b["markets"][:1]}, "16 distinct legs"),
    ("an open leg", None, _legs(lambda i, leg: i == 3 and leg.update(status="active")), "not finalized"),
    ("a void", None, _legs(lambda i, leg: leg.update(result="")), "results are not"),
    ("two winners", None, _legs(lambda i, leg: i < 2 and leg.update(result="yes")), "results are not"),
    ("another edition", None, _legs(lambda i, leg: leg.update(rules_primary=leg["rules_primary"].replace("98th", "99th"))), "award and edition"),
    ("another award", None, _legs(lambda i, leg: leg.update(rules_primary=leg["rules_primary"].replace("(Original Song)", "(Original Score)"))), "award and edition"),
])
def test_the_authority_check_refuses_anything_but_the_exact_terminal_event(
    oscar, name, event_fn, archive_fn, why
):
    event, archive = _bodies(oscar)
    oscar.verify_authority(copy.deepcopy(event), copy.deepcopy(archive))  # the control
    if event_fn:
        event = event_fn(copy.deepcopy(event))
    if archive_fn:
        archive = archive_fn(copy.deepcopy(archive))
    with pytest.raises(oscar.Refused, match=re.escape(why)):
        oscar.verify_authority(event, archive)


def test_loading_the_evidence_runs_the_authority_check(oscar, monkeypatch):
    seen = []

    def check(event, archive):
        seen.append((event["event"]["event_ticker"], len(archive["markets"])))
        raise oscar.Refused("checked")

    monkeypatch.setattr(oscar, "verify_authority", check)
    with pytest.raises(oscar.Refused, match="checked"):
        oscar.load_evidence()
    assert seen == [("KXOSCARSONG-26", 16)]


def test_the_cli_takes_no_id_table_or_sql(oscar, nine):
    for mod in (oscar, nine):
        tree = ast.parse(Path(mod.__file__).read_text())
        flags = {
            n.args[0].value for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "add_argument"
        }
        assert not {f for f in flags if re.search(r"id|table|sql|ticker|member", f)}, flags
    assert {"--backup", "--apply", "--digest", "--restore", "--status"} == {
        n.args[0].value for n in ast.walk(ast.parse(SCRIPT.read_text()))
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "add_argument"
    }


# ── the rail it shares, left as #2722 certified it ───────────────────────────


def test_the_nine_rows_statements_are_byte_identical(nine):
    assert hashlib.sha256(json.dumps(nine.SQL, sort_keys=True).encode()).hexdigest() == NINE_SQL_SHA256


def test_the_nine_rows_frozen_defaults_are_unchanged(nine):
    assert [i for i, _ in nine.NINE] == [109776, 110337, 110749, 925648, 925724, 1631094,
                                         3452978, 11757847, 54069617]
    assert nine.MANIFEST_SHA256 == "d3484abdddd58e0487ca535e36c24e2029b81faba248edfc9f88969761540a7c"
    assert nine.BACKUP_TABLE == "backup_2722_archived_nine"
    import inspect

    for fn, kw, default in (
        (nine.load_evidence, "members", nine.NINE), (nine.load_evidence, "manifest_sha256", nine.MANIFEST_SHA256),
        (nine.build_plan, "members", nine.NINE), (nine.plan_digest, "manifest_sha256", nine.MANIFEST_SHA256),
        (nine.backup, "table", nine.BACKUP_TABLE), (nine.apply, "table", nine.BACKUP_TABLE),
        (nine.restore_report, "table", nine.BACKUP_TABLE),
    ):
        p = inspect.signature(fn).parameters[kw]
        assert p.kind is p.KEYWORD_ONLY and p.default == default, (fn.__name__, kw)


def test_only_the_two_frozen_channels_have_statements(nine):
    assert nine.CHANNEL_TABLES == ("backup_2722_archived_nine", "backup_2644_oscar_song")
    for bad in ("futures_markets", "backup_2722_archived_nine; DROP TABLE x", ""):
        with pytest.raises(ValueError):
            nine.channel_sql(bad)
    a, b = nine.channel_sql(nine.CHANNEL_TABLES[0]), nine.channel_sql(nine.CHANNEL_TABLES[1])
    assert a.keys() == b.keys()
    for k in a:
        assert a[k].replace("backup_2722_archived_nine", "T") == b[k].replace("backup_2644_oscar_song", "T")


# ── every session site is bounded ─────────────────────────────────────────────


def _session_calls():
    tree = ast.parse(SCRIPT.read_text())
    return [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", getattr(n.func, "attr", None)) == "get_task_session"
    ]


def test_every_session_site_carries_both_budgets_by_name(oscar):
    calls = _session_calls()
    # status, restore, plan, backup/apply — a fifth site must be added here deliberately.
    assert len(calls) == 4
    for call in calls:
        assert call.args == []
        kw = {k.arg: getattr(k.value, "id", None) for k in call.keywords}
        assert kw == {"statement_timeout_ms": "STATEMENT_TIMEOUT_MS",
                      "lock_timeout_ms": "LOCK_TIMEOUT_MS"}, ast.unparse(call)
    assert oscar.STATEMENT_TIMEOUT_MS == 10_000 and oscar.LOCK_TIMEOUT_MS == 500


def test_no_bare_set_of_either_guc():
    assert not re.search(r"\bSET\s+(LOCAL\s+)?(statement_timeout|lock_timeout)\b",
                         SCRIPT.read_text(), re.I)


# ── the commit it cannot see ─────────────────────────────────────────────────


class FakeSession:
    def __init__(self, fail_commit_at=None, fail_rollback=False):
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit_at = fail_commit_at
        self.fail_rollback = fail_rollback

    async def commit(self):
        self.commits += 1
        if self.commits == self.fail_commit_at:
            raise _db_error("08006")

    async def rollback(self):
        self.rollbacks += 1
        if self.fail_rollback:
            raise ConnectionResetError("connection lost")


def _db_error(sqlstate):
    class _Orig(Exception):
        pass

    orig = _Orig("connection lost")
    orig.sqlstate = sqlstate
    return OperationalError("COMMIT", {}, orig)


PLANNED = [{
    "market_id": 109548, "ticker": "KXOSCARSONG-26",
    "resolution_date": "2026-03-16T02:11:07+00:00",
    "expiration_time": "2026-12-31T15:00:00+00:00",
    "venue_settled": True, "approved_before": '{"id": 109548}',
}]


@pytest.fixture
def rig(oscar, monkeypatch):
    import app.tasks.base as base

    calls = {"backup": 0, "apply": 0, "restore_report": 0}
    seen: list[dict] = []
    state = {"session": FakeSession()}

    def stub(name, result):
        async def f(*a, **k):
            calls[name] += 1
            assert k.get("table") == "backup_2644_oscar_song"
            return result
        return f

    async def plan(*a, **k):
        return {"planned": PLANNED, "no_op": [], "stop_not_settled_from_archive": [],
                "voids_reported_not_written": [], "walk_stats": {}, "stop": []}

    @contextlib.asynccontextmanager
    async def fake(**kwargs):
        """get_task_session's contract: commit on a clean exit, roll back and
        re-raise on an exception."""
        seen.append(kwargs)
        s = state["session"]
        try:
            yield s
        except Exception:
            await s.rollback()
            raise
        await s.commit()

    monkeypatch.setattr(oscar, "load_evidence", lambda: {})
    monkeypatch.setattr(oscar, "build_plan", plan)
    monkeypatch.setattr(oscar.rail, "backup", stub("backup", []))
    monkeypatch.setattr(oscar.rail, "apply", stub("apply", {
        "written_ids": [109548], "skipped_changed_since_backup": []}))
    monkeypatch.setattr(oscar.rail, "restore_report", stub("restore_report", {
        "restored": [109548], "preserved_changed_since_apply": []}))
    monkeypatch.setattr(base, "get_task_session", fake)
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    return {"calls": calls, "seen": seen, "state": state, "digest": oscar.plan_digest(PLANNED)}


def _argv(rig, mode):
    return {"plan": [], "apply": ["--backup", "--apply", "--digest", rig["digest"]],
            "restore": ["--restore"]}[mode]


@pytest.mark.parametrize("mode,opened", [("plan", 1), ("apply", 2), ("restore", 1)])
def test_every_session_each_mode_opens_is_armed(oscar, rig, capsys, mode, opened):
    assert oscar.main(_argv(rig, mode)) == 0
    assert rig["seen"] == [{"statement_timeout_ms": 10_000, "lock_timeout_ms": 500}] * opened
    out = json.loads(capsys.readouterr().out)
    assert ("undo" in out) == (mode == "apply")


# The plan session's clean exit is commit 1; the backup/apply session's
# explicit commits are 2 (backup) and 3 (apply). Restore's explicit commit is 1.
@pytest.mark.parametrize("mode,fail_at,phase,certain", [
    ("apply", 2, "backup-commit", "futures_markets was not written"),
    ("apply", 3, "apply-commit", "the backup is committed"),
    ("restore", 1, "restore-commit", "restore's durability is UNKNOWN"),
])
@pytest.mark.parametrize("rollback_fails", [False, True])
def test_a_commit_that_does_not_return_is_unknown_never_rolled_back(
    oscar, rig, capsys, mode, fail_at, phase, certain, rollback_fails
):
    rig["state"]["session"] = FakeSession(fail_commit_at=fail_at, fail_rollback=rollback_fails)
    assert oscar.main(_argv(rig, mode)) == 3
    out = json.loads(capsys.readouterr().out)
    assert out["outcome"] == "UNKNOWN"
    msg = out["unknown"]
    assert f"the {phase} did not return" in msg and certain in msg and "--status" in msg
    assert "rolled back" not in msg and "nothing to restore" not in msg
    assert rig["calls"]["restore_report"] == (1 if mode == "restore" else 0)  # no auto-restore
    if phase == "backup-commit":
        assert rig["calls"]["apply"] == 0  # the apply never starts on an unseen backup


@pytest.mark.parametrize("mode,stub,phase,consequence", [
    ("apply", "backup", "backup", "nothing was backed up or written"),
    ("apply", "apply", "apply", "nothing to restore"),
    ("restore", "restore_report", "restore", "no row was restored"),
])
def test_a_statement_the_database_refused_is_a_rolled_back_refusal(
    oscar, rig, monkeypatch, capsys, mode, stub, phase, consequence
):
    async def refuse(*a, **k):
        rig["calls"][stub] += 1
        raise _db_error("55P03")

    monkeypatch.setattr(oscar.rail, stub, refuse)
    assert oscar.main(_argv(rig, mode)) == 2
    msg = json.loads(capsys.readouterr().out)["refused"]
    assert f"stopped the {phase}" in msg and "sqlstate 55P03" in msg
    assert "rolled back" in msg and consequence in msg and "Not retried" in msg
    assert rig["calls"][stub] == 1


def test_writes_refuse_off_the_named_app_and_without_backup(oscar, rig, monkeypatch, capsys):
    assert oscar.main(["--backup", "--apply", "--digest", "wrong"]) == 2
    assert "does not match" in json.loads(capsys.readouterr().out)["refused"]
    assert oscar.main(["--apply", "--digest", rig["digest"]]) == 2
    assert "requires --backup" in json.loads(capsys.readouterr().out)["refused"]
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    for argv in (_argv(rig, "apply"), _argv(rig, "restore")):
        assert oscar.main(argv) == 2
        assert "bainluck-heavy" in json.loads(capsys.readouterr().out)["refused"]
    assert rig["calls"] == {"backup": 0, "apply": 0, "restore_report": 0}
