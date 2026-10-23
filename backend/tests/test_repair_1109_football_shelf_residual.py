"""#1109 — the guards the Football-shelf repair has to hold, with no server.

1. **Before / after on the specimens**: the name rules alone (what an evidence-free
   writer persisted) answer ``football`` for the generic-phrase basketball question
   and never reach tennis for the ITF matchup; the shipped cascade, given the venue's
   evidence, answers basketball and tennis — the only targets the artifact may carry.
2. **Football controls stay football**: a mapped NFL row, a CFL row the venue tags
   ``Football``, and any ``after`` of football or ``other`` refuse the whole artifact.
3. **Unknown evidence refuses**: an unresolved venue read, a stale or undated one, a
   venue answer for another series, a target only the NAME supports, a ticker/tag
   contradiction, or a cascade that answers otherwise.
4. **Changed rows retire alone**: missing, re-identified, already repaired, moved by
   another writer, renamed, or a newer ``updated_at`` — skipped, never written.
5. **The apply writes exactly the reviewed plan**: the hash binds the artifact and the
   decided writes; a statement changing other than one row rolls the run back.
6. **The undo and the readback** work from the artifact alone.
7. **The attended run is bounded** by its own lock and statement budgets.
8. **A COMMIT that does not return is UNKNOWN** (exit 3), landed or not, with no
   rollback claim, undo line or second COMMIT; a refusal before the COMMIT and an
   acknowledged COMMIT each keep their output and exit through a failing cleanup.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import importlib.util
import io
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.kalshi import _categorize_kalshi_market
from app.utils.futures_categorization import categorize_by_rules

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def repair():
    return _load("repair_1109", "repair_1109_football_shelf_residual.py")


NOW = datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc)
READ_AT = (NOW - timedelta(hours=1)).isoformat()
V_ITF = datetime(2026, 7, 19, 14, 2, 11, 123456, tzinfo=timezone.utc)
V_OTD = datetime(2026, 7, 1, 9, 0, 0, 5, tzinfo=timezone.utc)

ITF_NAME = "Velcz vs Kimhi"  # the issue's production specimen
OTD_NAME = "Will the Hawks make a playoff berth?"


def _row(id, external_id, name, after, version, *, tags, series_category="Sports"):
    return {
        "id": id,
        "external_id": external_id,
        "name": name,
        "before": "football",
        "after": after,
        "row_updated_at": version.isoformat(),
        "venue": {
            "series_ticker": external_id.split("-", 1)[0],
            "resolved": True,
            "tags": tags,
            "series_category": series_category,
            "event_category": "Sports",
            "read_at": READ_AT,
        },
    }


def _artifact(*rows):
    return {
        "schema": "kalshi-football-shelf-residual-plan/v1",
        "issue": 1109,
        "rows": list(rows),
    }


ITF = _row(901, "KXITFMATCH-26JUL19VELKIM", ITF_NAME, "tennis", V_ITF, tags=[])
OTD = _row(
    902,
    "KXOTDBASKETBALL-26JUL01HAWK",
    OTD_NAME,
    "basketball",
    V_OTD,
    tags=["Basketball"],
)
ARTIFACT = _artifact(ITF, OTD)

LIVE = {
    901: ("kalshi", ITF["external_id"], "football", ITF_NAME, V_ITF),
    902: ("kalshi", OTD["external_id"], "football", OTD_NAME, V_OTD),
}


def _validate(repair, artifact, now=NOW):
    return repair.validate_artifact(artifact, now=now)


def _with(row, **changes):
    out = copy.deepcopy(row)
    venue = changes.pop("venue", None)
    out.update(changes)
    if venue:
        out["venue"].update(venue)
    return out


# ── 1. before / after on the specimens ───────────────────────────────────────


def test_the_name_rules_alone_put_both_specimens_on_the_football_shelf():
    # The BEFORE: what a writer without ticker or venue evidence persisted.
    # The ITF matchup's football came from the retired calendar guess (#1888) and
    # no longer reproduces from the rules; the generic phrase still does.
    assert categorize_by_rules(OTD_NAME) == "football"
    assert _categorize_kalshi_market(ITF_NAME, None, None) != "tennis"


def test_the_shipped_cascade_on_the_venue_evidence_answers_the_real_sport():
    # The AFTER the artifact must carry, from the writer the next poll runs.
    assert _categorize_kalshi_market(ITF_NAME, "Sports", ITF["external_id"]) == "tennis"
    assert (
        _categorize_kalshi_market(
            OTD_NAME, "Sports", OTD["external_id"], series_tag="Basketball"
        )
        == "basketball"
    )


def test_a_valid_artifact_passes_its_gates(repair):
    rows = _validate(repair, ARTIFACT)
    assert [r["id"] for r in rows] == [901, 902]


# ── 2. football controls ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "row, why",
    [
        (
            _row(
                910,
                "KXNFLGAME-26SEP14KCBUF",
                "Chiefs vs Bills",
                "tennis",
                V_ITF,
                tags=[],
            ),
            "ticker map",
        ),
        (
            _row(
                911,
                "KXCFLTOTAL-26SEP12OTTTOR",
                "Ottawa Redblacks vs Toronto Argonauts: Total Points",
                "basketball",
                V_ITF,
                tags=["Football"],
            ),
            "sport tag",
        ),
    ],
)
def test_a_genuine_football_row_is_never_moved(repair, row, why):
    with pytest.raises(repair.Refused, match=why):
        _validate(repair, _artifact(row))


@pytest.mark.parametrize("after", ["football", "other", "golfish", ""])
def test_the_target_must_be_a_named_non_football_sport(repair, after):
    with pytest.raises(repair.Refused, match="not a non-football sport"):
        _validate(repair, _artifact(_with(ITF, after=after)))


@pytest.mark.parametrize("before", ["baseball", "basketball", "other"])
def test_only_rows_starting_on_football_are_in_scope(repair, before):
    with pytest.raises(repair.Refused, match="off 'football' only"):
        _validate(repair, _artifact(_with(ITF, before=before)))


def test_the_rail_is_disjoint_from_the_2169_pinned_rows(repair):
    sibling = _load("repair_2169", "repair_2169_misfiled_sport_category.py")
    assert all(before != repair.BEFORE for before, _ in sibling.PINNED.values())


# ── 3. unknown evidence refuses ──────────────────────────────────────────────


def test_an_unresolved_venue_read_is_not_evidence(repair):
    with pytest.raises(repair.Refused, match="did not answer"):
        _validate(repair, _artifact(_with(OTD, venue={"resolved": False})))


def test_a_target_only_the_name_supports_refuses(repair):
    # Unmapped ticker, no sport tag: the cascade may still say basketball from
    # "NBA" in the name, and that is a candidate, not evidence.
    name = "Will an NBA team make a playoff berth?"
    row = _with(OTD, name=name, venue={"tags": ["Television"]})
    assert (
        _categorize_kalshi_market(
            name, "Sports", OTD["external_id"], series_tag="Television"
        )
        == "basketball"
    )
    with pytest.raises(repair.Refused, match="a name is not evidence"):
        _validate(repair, _artifact(row))


def test_a_ticker_and_tag_that_disagree_refuse(repair):
    with pytest.raises(repair.Refused, match="ticker map says 'tennis'"):
        _validate(repair, _artifact(_with(ITF, venue={"tags": ["Basketball"]})))


def test_a_cascade_that_answers_otherwise_refuses(repair):
    # Step 0 (IPO) speaks above the ticker map.
    with pytest.raises(repair.Refused, match="shipped cascade answers 'economics'"):
        _validate(repair, _artifact(_with(ITF, name="Velcz IPO vs Kimhi")))


def test_a_venue_answer_for_another_series_refuses(repair):
    with pytest.raises(repair.Refused, match="is not the series of"):
        _validate(repair, _artifact(_with(ITF, venue={"series_ticker": "KXITFWMATCH"})))


@pytest.mark.parametrize(
    "read_at, match",
    [
        ((NOW - timedelta(hours=25)).isoformat(), "older than"),
        ((NOW + timedelta(hours=1)).isoformat(), "in the future"),
        ("2026-10-14T02:00:00", "no UTC offset"),
        ("yesterday", "not an ISO-8601"),
    ],
)
def test_a_stale_future_or_undated_read_refuses(repair, read_at, match):
    with pytest.raises(repair.Refused, match=match):
        _validate(repair, _artifact(_with(ITF, venue={"read_at": read_at})))


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda a: a.update(schema="v0"), "schema"),
        (lambda a: a.update(issue=2169), "issue"),
        (lambda a: a.update(rows=[]), "no rows"),
        (lambda a: a["rows"].append(copy.deepcopy(ITF)), "appears twice"),
        (lambda a: a["rows"][0].update(id=True), "id missing"),
        (lambda a: a["rows"][0].pop("name"), "name missing"),
        (lambda a: a["rows"][0].pop("row_updated_at"), "row_updated_at missing"),
        (lambda a: a["rows"][0]["venue"].update(tags=[1]), "non-string"),
    ],
)
def test_a_malformed_artifact_refuses(repair, mutate, match):
    artifact = copy.deepcopy(ARTIFACT)
    mutate(artifact)
    with pytest.raises(repair.Refused, match=match):
        _validate(repair, artifact)


def test_the_artifact_is_bounded(repair, monkeypatch):
    monkeypatch.setattr(repair, "MAX_ROWS", 1)
    with pytest.raises(repair.Refused, match="the bound is 1"):
        _validate(repair, ARTIFACT)


def test_undo_and_readback_skip_freshness_and_evidence(repair):
    stale = _artifact(_with(ITF, venue={"read_at": "2026-01-01T00:00:00+00:00"}))
    with pytest.raises(repair.Refused):
        _validate(repair, stale)
    assert repair.validate_artifact(stale, now=NOW, evidence=False)


# ── 4. changed rows retire alone ─────────────────────────────────────────────


def _plan(repair, live, artifact=ARTIFACT, **kw):
    rows = repair.validate_artifact(artifact, now=None, evidence=False)
    return repair.plan(rows, live, repair.artifact_address(artifact), **kw)


@pytest.mark.parametrize(
    "live_901, reason",
    [
        (None, "row missing"),
        (
            ("polymarket", ITF["external_id"], "football", ITF_NAME, V_ITF),
            "identity moved",
        ),
        (("kalshi", "KXITFMATCH-OTHER", "football", ITF_NAME, V_ITF), "identity moved"),
        (("kalshi", ITF["external_id"], "tennis", ITF_NAME, V_ITF), "already 'tennis'"),
        (("kalshi", ITF["external_id"], "baseball", ITF_NAME, V_ITF), "another writer"),
        (
            ("kalshi", ITF["external_id"], "football", "Velcz vs Kimh", V_ITF),
            "name changed",
        ),
        (
            (
                "kalshi",
                ITF["external_id"],
                "football",
                ITF_NAME,
                V_ITF + timedelta(microseconds=1),
            ),
            "row version moved",
        ),
    ],
)
def test_a_row_that_moved_since_the_read_retires_alone(repair, live_901, reason):
    live = dict(LIVE)
    if live_901 is None:
        del live[901]
    else:
        live[901] = live_901
    out = _plan(repair, live)
    assert out["write"] == [(902, "football", "basketball")]
    assert [(i, r) for i, r in out["skip"] if reason in r] and out["skip"][0][0] == 901


def test_movement_declares_the_per_shelf_counts(repair):
    assert _plan(repair, LIVE)["movement"] == {
        "football->tennis": 1,
        "football->basketball": 1,
    }


# ── 5. the apply writes exactly the reviewed plan ────────────────────────────


class _Result:
    def __init__(self, rows=(), rowcount=1):
        self._rows = list(rows)
        self.rowcount = rowcount

    def __iter__(self):
        return iter(self._rows)


class _Row:
    def __init__(self, id, source, external_id, cat, name, updated_at):
        self.id, self.source, self.external_id = id, source, external_id
        self.llm_sport_category, self.name, self.updated_at = cat, name, updated_at


class FakeSession:
    """Honours only the predicates the SQL TEXT states, so a clause dropped from
    the script's UPDATE is a clause this fake stops enforcing."""

    def __init__(self, live):
        self.live = {i: list(v) for i, v in live.items()}
        self.updates: list[dict] = []
        self.committed = self.rolled_back = False

    async def execute(self, stmt, params):
        sql = " ".join(str(stmt).split())
        if sql.upper().startswith("SELECT"):
            ids = set(params["ids"])
            got = _Result(_Row(i, *v) for i, v in self.live.items() if i in ids)
            self.after_read()
            return got
        assert sql.upper().startswith("UPDATE")
        self.updates.append(dict(params, sql=sql))
        row = self.live.get(params["id"])
        checks = {
            "source = 'kalshi'": lambda: row[0] == "kalshi",
            "external_id = :external_id": lambda: row[1] == params["external_id"],
            "llm_sport_category = :source_category": lambda: row[2]
            == params["source_category"],
            "name IS NOT DISTINCT FROM :name": lambda: row[3] == params["name"],
            "updated_at = :row_updated_at": lambda: row[4] == params["row_updated_at"],
        }
        where = sql.split(" WHERE ", 1)[1]
        if row is None or not all(
            f() for clause, f in checks.items() if clause in where
        ):
            return _Result(rowcount=0)
        row[2] = params["target"]
        return _Result(rowcount=1)

    def after_read(self):
        """A concurrent writer's hook: runs between the read and the first UPDATE."""

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _run(repair, session, artifact=ARTIFACT, **kw):
    kw.setdefault("now", NOW)
    return asyncio.run(repair.run(session, artifact, **kw))


def _hash(repair, artifact=ARTIFACT):
    return _run(repair, FakeSession(LIVE), artifact, mode="dry-run")["plan_hash"]


def test_dry_run_writes_nothing(repair):
    s = FakeSession(LIVE)
    out = _run(repair, s, mode="dry-run")
    assert s.updates == [] and not s.committed
    assert out["written"] == 0 and len(out["write"]) == 2


def test_apply_with_the_wrong_hash_writes_nothing(repair):
    s = FakeSession(LIVE)
    with pytest.raises(repair.Refused, match="plan hash"):
        _run(repair, s, mode="apply", expect_plan_hash="0" * 16)
    assert s.updates == [] and not s.committed


def test_apply_with_the_dry_run_hash_moves_both_rows_off_football(repair):
    s = FakeSession(LIVE)
    out = _run(repair, s, mode="apply", expect_plan_hash=_hash(repair))
    assert out["written"] == 2 and s.committed
    assert s.live[901][2] == "tennis" and s.live[902][2] == "basketball"
    # The row version is not touched: only the category moves.
    assert s.live[901][4] == V_ITF and s.live[902][4] == V_OTD


def test_an_edited_artifact_is_a_different_hash(repair):
    edited = _artifact(ITF, _with(OTD, venue={"series_category": "Basketball"}))
    assert _hash(repair, edited) != _hash(repair)
    s = FakeSession(LIVE)
    with pytest.raises(repair.Refused, match="plan hash"):
        _run(repair, s, edited, mode="apply", expect_plan_hash=_hash(repair))
    assert s.updates == []


def test_the_hash_is_row_order_free(repair):
    assert _hash(repair, _artifact(OTD, ITF)) == _hash(repair)


class PolledAfterRead(FakeSession):
    """The poller touches the ITF row between the read and its UPDATE: same
    category, same name, newer `updated_at` — only the version half can see it."""

    def after_read(self):
        self.live[901][4] = V_ITF + timedelta(seconds=1)


def test_a_poll_between_read_and_write_rolls_the_run_back(repair):
    s = PolledAfterRead(LIVE)
    with pytest.raises(repair.Refused, match="901"):
        _run(repair, s, mode="apply", expect_plan_hash=_hash(repair))
    assert not s.committed


class RecategorisedAfterRead(FakeSession):
    def after_read(self):
        self.live[902][2] = "hockey"


def test_another_writer_between_read_and_write_rolls_the_run_back(repair):
    s = RecategorisedAfterRead(LIVE)
    with pytest.raises(repair.Refused, match="902"):
        _run(repair, s, mode="apply", expect_plan_hash=_hash(repair))
    assert not s.committed and s.live[902][2] == "hockey"


def test_the_write_moves_the_category_alone_and_restates_every_decided_value(repair):
    sql = " ".join(repair._CAS_SQL.split())
    set_clause, where = sql.split(" WHERE ")
    assert set_clause == "UPDATE futures_markets SET llm_sport_category = :target"
    for clause in (
        "id = :id",
        "source = 'kalshi'",
        "external_id = :external_id",
        "llm_sport_category = :source_category",
        "name IS NOT DISTINCT FROM :name",
        "updated_at = :row_updated_at",
    ):
        assert clause in where
    assert "name = :name" not in sql


# ── 6. undo and readback ─────────────────────────────────────────────────────


def test_restore_reverts_only_the_named_ids_even_after_a_poll(repair):
    s = FakeSession(LIVE)
    _run(repair, s, mode="apply", expect_plan_hash=_hash(repair))
    s.live[901][4] = V_ITF + timedelta(hours=2)  # polled since the apply
    s.updates.clear()
    out = _run(repair, s, mode="restore", restore_ids=frozenset({901}))
    assert out["written"] == 1 and s.live[901][2] == "football"
    assert s.live[902][2] == "basketball"
    sql = " ".join(repair._RESTORE_SQL.split())
    assert "updated_at" not in sql and "llm_sport_category = :source_category" in sql


def test_restore_skips_a_row_another_writer_moved_after_the_apply(repair):
    live = dict(LIVE)
    live[901] = ("kalshi", ITF["external_id"], "hockey", ITF_NAME, V_ITF)
    out = _plan(repair, live, restore_ids=frozenset({901}))
    assert out["write"] == [] and "another writer" in out["skip"][0][1]


def test_restore_ids_must_be_artifact_ids(repair):
    rows = repair.validate_artifact(ARTIFACT, now=None, evidence=False)
    for bad in ("903", " , ", "x"):
        with pytest.raises(repair.Refused):
            repair.parse_ids(bad, rows)
    assert repair.parse_ids("901,902", rows) == frozenset({901, 902})


def test_readback_reports_where_every_row_stands(repair):
    live = dict(LIVE)
    live[901] = ("kalshi", ITF["external_id"], "tennis", ITF_NAME, V_ITF)
    s = FakeSession(live)
    out = _run(repair, s, mode="readback")
    assert out["counts"] == {"after": 1, "before": 1, "other": 0, "missing": 0}
    assert out["ids"]["after"] == [901] and s.updates == []


# ── 7. the attended run's door and budgets ───────────────────────────────────


@pytest.mark.parametrize("app", ["", "bainluck-staging", "local"])
def test_refuses_off_production(repair, app):
    with pytest.raises(repair.Refused):
        repair.refuse_unless_production({"HEROKU_APP_NAME": app})


@pytest.mark.parametrize(
    "argv",
    [
        ["--plan", "-", "--apply"],
        ["--plan", "-", "--restore"],
        ["--plan", "-", "--ids", "901"],
        ["--plan", "-", "--expect-plan-hash", "abc"],
        ["--plan", "/nonexistent/plan.json"],
    ],
)
def test_main_refuses_unsafe_flag_shapes_before_any_session(
    repair, monkeypatch, argv, capsys
):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    monkeypatch.setattr(sys, "argv", ["repair_1109", *argv])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(ARTIFACT)))
    assert asyncio.run(repair.main()) == 2
    assert capsys.readouterr().out.startswith("REFUSED:")


def _fake_task_session(session, seen):
    @contextlib.asynccontextmanager
    async def fake(**kwargs):
        seen.append(kwargs)
        yield session

    return fake


def _fresh_artifact():
    # main() reads the real clock, so the read is stamped relative to it.
    read_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    return _artifact(*(_with(r, venue={"read_at": read_at}) for r in (ITF, OTD)))


def test_main_reads_the_artifact_from_stdin_and_arms_short_budgets(
    repair, monkeypatch, capsys
):
    import app.tasks.base as base

    seen: list[dict] = []
    monkeypatch.setattr(
        base, "get_task_session", _fake_task_session(FakeSession(LIVE), seen)
    )
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    monkeypatch.setattr(sys, "argv", ["repair_1109", "--plan", "-"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_fresh_artifact())))
    assert asyncio.run(repair.main()) == 0
    assert seen == [
        {
            "statement_timeout_ms": repair.STATEMENT_TIMEOUT_MS,
            "lock_timeout_ms": repair.LOCK_TIMEOUT_MS,
        }
    ]
    assert 0 < repair.LOCK_TIMEOUT_MS <= 10_000
    assert 0 < repair.STATEMENT_TIMEOUT_MS <= 30_000
    assert '"mode": "dry-run"' in capsys.readouterr().out


class _LockNotAvailable(Exception):
    sqlstate = "55P03"


class LockedOnSecondWrite(FakeSession):
    async def execute(self, stmt, params):
        if str(stmt).lstrip().upper().startswith("UPDATE") and len(self.updates) == 1:
            from sqlalchemy.exc import OperationalError

            self.updates.append(dict(params))
            raise OperationalError(str(stmt), params, _LockNotAvailable("lock timeout"))
        return await super().execute(stmt, params)


def test_a_lock_timeout_refuses_and_rolls_back_without_commit(
    repair, monkeypatch, capsys
):
    import app.tasks.base as base

    artifact = _fresh_artifact()
    h = _run(
        repair,
        FakeSession(LIVE),
        artifact,
        mode="dry-run",
        now=datetime.now(timezone.utc),
    )["plan_hash"]
    s = LockedOnSecondWrite(LIVE)
    monkeypatch.setattr(base, "get_task_session", _fake_task_session(s, []))
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    monkeypatch.setattr(
        sys, "argv", ["repair_1109", "--plan", "-", "--apply", "--expect-plan-hash", h]
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(artifact)))
    assert asyncio.run(repair.main()) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED:") and "55P03" in out and "nothing committed" in out
    assert "UNDO" not in out
    assert s.rolled_back and not s.committed


# ── 8. a COMMIT that does not return is UNKNOWN, never "nothing committed" ───
#
# Root's finding (2026-10-18, blob 7b2ab2dc): ``main()`` caught a DBAPIError raised
# by the COMMIT itself and printed "rolled back, nothing committed" — false when the
# server made the COMMIT durable and only the acknowledgement was lost. And its
# ``return 2`` was a NORMAL exit from ``get_task_session``, whose normal exit sends
# a second COMMIT behind the unacknowledged one. These arms drive the PRODUCTION
# ``app.tasks.base.get_task_session``; only the engine and session factory it
# builds are inert, so its normal-exit COMMIT is real (the rig control proves it).
# Each session keeps ``durable`` (what the server holds) apart from ``live`` (what
# this transaction sees), and its COMMIT either lands before losing the
# acknowledgement or never lands at all.


class _ConnectionFailure(Exception):
    sqlstate = "08006"


def _lost_ack():
    from sqlalchemy.exc import OperationalError

    return OperationalError("COMMIT", {}, _ConnectionFailure("connection lost"))


class WireSession(FakeSession):
    """``commit_fails`` maps the Nth COMMIT (1-based) to (exception, landed)."""

    def __init__(
        self,
        live,
        calls,
        *,
        commit_fails=None,
        rollback_raises=None,
        close_raises=None,
        moved_after_read=False,
    ):
        super().__init__(live)
        self.durable = copy.deepcopy(self.live)
        self.calls = calls
        self.commits = 0
        self._commit_fails = commit_fails or {}
        self._rollback_raises = rollback_raises
        self._close_raises = close_raises
        self._moved_after_read = moved_after_read

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def after_read(self):
        if self._moved_after_read:  # the poller touched 901: its UPDATE changes 0 rows
            self.live[901][4] = V_ITF + timedelta(seconds=1)

    async def commit(self):
        self.calls.append("commit")
        self.commits += 1
        exc, landed = self._commit_fails.get(self.commits, (None, True))
        if landed:
            self.durable = copy.deepcopy(self.live)
            self.committed = True
        if exc is not None:
            raise exc

    async def rollback(self):
        # A client rollback cannot reach a COMMIT the server already made durable.
        self.calls.append("rollback")
        self.rolled_back = True
        self.live = copy.deepcopy(self.durable)
        if self._rollback_raises is not None:
            raise self._rollback_raises

    async def close(self):
        self.calls.append("close")
        if self._close_raises is not None:
            raise self._close_raises


class _InertEngine:
    def __init__(self, calls, raises=None):
        self._calls, self._raises = calls, raises

    async def dispose(self):
        self._calls.append("dispose")
        if self._raises is not None:
            raise self._raises


AFTER = {
    901: ("kalshi", ITF["external_id"], "tennis", ITF_NAME, V_ITF),
    902: ("kalshi", OTD["external_id"], "basketball", OTD_NAME, V_OTD),
}


def _durable(session):
    return {i: v[2] for i, v in session.durable.items()}


BEFORE_STATE = {901: "football", 902: "football"}
AFTER_STATE = {901: "tennis", 902: "basketball"}


def _wire_main(
    repair, monkeypatch, session, mode, *, dispose_raises=None, artifact=None
):
    """Run the real ``main()`` through the real ``get_task_session``; return its code."""
    import app.tasks.base as base

    assert base.get_task_session.__module__ == "app.tasks.base"
    assert base.get_task_session.__wrapped__.__qualname__ == "get_task_session"
    seen: list[dict] = []

    def engine_factory(**kwargs):
        seen.append(kwargs)
        return _InertEngine(session.calls, dispose_raises)

    monkeypatch.setattr(base, "_get_task_engine", engine_factory)
    monkeypatch.setattr(base, "async_sessionmaker", lambda bound, **kw: lambda: session)
    artifact = artifact or _fresh_artifact()
    argv = ["repair_1109", "--plan", "-"]
    if mode == "apply":
        h = _run(
            repair,
            FakeSession(LIVE),
            artifact,
            mode="dry-run",
            now=datetime.now(timezone.utc),
        )["plan_hash"]
        argv += ["--apply", "--expect-plan-hash", h]
    elif mode == "restore":
        argv += ["--restore", "--ids", "901,902"]
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(artifact)))
    code = asyncio.run(repair.main())
    assert seen == [
        {
            "statement_timeout_ms": repair.STATEMENT_TIMEOUT_MS,
            "lock_timeout_ms": repair.LOCK_TIMEOUT_MS,
        }
    ]
    return code


_START = {"apply": LIVE, "restore": AFTER}
_MOVED = {"apply": AFTER_STATE, "restore": BEFORE_STATE}
_UNMOVED = {"apply": BEFORE_STATE, "restore": AFTER_STATE}


def _report(out: str) -> dict:
    return json.loads(out[out.index("{") :])


def test_rig_control_the_production_wrapper_commits_again_on_a_normal_exit(
    repair, monkeypatch, capsys
):
    """Without this the no-second-COMMIT arms below would be vacuous."""
    s = WireSession(LIVE, [])
    assert _wire_main(repair, monkeypatch, s, "apply") == 0
    assert s.calls == ["commit", "commit", "close", "dispose"]
    assert _durable(s) == AFTER_STATE
    out = capsys.readouterr().out
    assert '"written": 2' in out and "UNDO (keep the artifact)" in out
    assert "--restore --ids 901,902" in out


@pytest.mark.parametrize("mode", ["apply", "restore"])
@pytest.mark.parametrize("landed", [True, False], ids=["landed", "never-landed"])
def test_a_lost_commit_acknowledgement_is_unknown_never_nothing_committed(
    repair, monkeypatch, capsys, mode, landed
):
    s = WireSession(_START[mode], [], commit_fails={1: (_lost_ack(), landed)})
    assert _wire_main(repair, monkeypatch, s, mode) == 3
    # The specimen: the server holds the writes exactly when the COMMIT landed.
    assert _durable(s) == (_MOVED if landed else _UNMOVED)[mode]
    captured = capsys.readouterr()
    out = captured.out
    for claim in ("nothing committed", "rolled back", "REFUSED", "UNDO", "--restore"):
        assert claim not in out
    assert "re-run" not in out and "retry" not in out.replace("Not retried", "")
    report = _report(out)
    assert report["outcome"] == "UNKNOWN" and report["mode"] == mode
    applied = [(901, "football", "tennis"), (902, "football", "basketball")]
    expected = applied if mode == "apply" else [(i, t, f) for i, f, t in applied]
    assert [tuple(w) for w in report["write"]] == expected
    assert report["statements_changed"] == 2 and "08006" in report["unknown"]
    assert "--readback" in report["readback"] and "--plan -" in report["readback"]
    # The wrapper left by its exception path: no second COMMIT behind the lost one.
    assert s.commits == 1 and s.calls == ["commit", "rollback", "close", "dispose"]
    assert captured.err == ""


@pytest.mark.parametrize("mode", ["apply", "restore"])
def test_the_unknown_report_is_the_same_whether_or_not_the_commit_landed(
    repair, monkeypatch, capsys, mode
):
    """The client cannot tell the two worlds apart, so its words must not differ."""
    outs, durables = [], []
    artifact = _fresh_artifact()
    for landed in (True, False):
        s = WireSession(_START[mode], [], commit_fails={1: (_lost_ack(), landed)})
        assert _wire_main(repair, monkeypatch, s, mode, artifact=artifact) == 3
        outs.append(capsys.readouterr().out)
        durables.append(_durable(s))
    assert durables[0] != durables[1]
    assert outs[0] == outs[1] and _report(outs[0])["outcome"] == "UNKNOWN"


class LockedWire(WireSession):
    async def execute(self, stmt, params):
        if str(stmt).lstrip().upper().startswith("UPDATE") and len(self.updates) == 1:
            from sqlalchemy.exc import OperationalError

            self.updates.append(dict(params))
            raise OperationalError(str(stmt), params, _LockNotAvailable("lock timeout"))
        return await super().execute(stmt, params)


@pytest.mark.parametrize("failing", ["rollback", "close", "dispose"])
def test_unknown_survives_a_failing_cleanup(repair, monkeypatch, capsys, failing):
    s = WireSession(
        LIVE,
        [],
        commit_fails={1: (_lost_ack(), True)},
        rollback_raises=_lost_ack() if failing == "rollback" else None,
        close_raises=_lost_ack() if failing == "close" else None,
    )
    dispose = _lost_ack() if failing == "dispose" else None
    assert _wire_main(repair, monkeypatch, s, "apply", dispose_raises=dispose) == 3
    captured = capsys.readouterr()
    assert _report(captured.out)["outcome"] == "UNKNOWN"
    assert "nothing committed" not in captured.out and "UNDO" not in captured.out
    assert "cleanup raised OperationalError after the UNKNOWN report" in captured.err
    assert s.commits == 1


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_a_cancel_on_the_commit_prints_unknown_and_stays_a_cancel(
    repair, monkeypatch, capsys, cleanup_fails
):
    s = WireSession(
        LIVE,
        [],
        commit_fails={1: (asyncio.CancelledError(), True)},
        rollback_raises=_lost_ack() if cleanup_fails else None,
    )
    with pytest.raises(asyncio.CancelledError):
        _wire_main(repair, monkeypatch, s, "apply")
    out = capsys.readouterr().out
    assert _report(out)["outcome"] == "UNKNOWN" and "nothing committed" not in out
    assert s.commits == 1 and _durable(s) == AFTER_STATE


@pytest.mark.parametrize("failing", ["rollback", "exit-commit", "dispose"])
@pytest.mark.parametrize("refusal", ["moved-row", "lock-timeout"])
def test_a_refusal_before_the_commit_survives_a_failing_helper(
    repair, monkeypatch, capsys, failing, refusal
):
    """Primary error first: a dead connection's cleanup never replaces the refusal."""
    kw = {
        "rollback_raises": _lost_ack() if failing == "rollback" else None,
        # Nothing was committed by the run, so the wrapper's exit COMMIT is the 1st.
        "commit_fails": {1: (_lost_ack(), True)} if failing == "exit-commit" else None,
    }
    if refusal == "moved-row":
        s = WireSession(LIVE, [], moved_after_read=True, **kw)
    else:
        s = LockedWire(LIVE, [], **kw)
    dispose = _lost_ack() if failing == "dispose" else None
    assert _wire_main(repair, monkeypatch, s, "apply", dispose_raises=dispose) == 2
    captured = capsys.readouterr()
    assert captured.out.startswith("REFUSED:") and "UNDO" not in captured.out
    assert ("901" if refusal == "moved-row" else "55P03") in captured.out
    if refusal == "lock-timeout":
        assert "nothing committed" in captured.out
    assert "cleanup raised OperationalError after the refusal" in captured.err
    assert _durable(s) == BEFORE_STATE and s.rolled_back
    assert "commit" not in s.calls[: s.calls.index("rollback") + 1]


@pytest.mark.parametrize("failing", ["exit-commit", "close", "dispose"])
def test_an_acknowledged_commit_survives_a_later_helper_error(
    repair, monkeypatch, capsys, failing
):
    s = WireSession(
        LIVE,
        [],
        commit_fails={2: (_lost_ack(), False)} if failing == "exit-commit" else None,
        close_raises=_lost_ack() if failing == "close" else None,
    )
    dispose = _lost_ack() if failing == "dispose" else None
    assert _wire_main(repair, monkeypatch, s, "apply", dispose_raises=dispose) == 0
    captured = capsys.readouterr()
    assert _durable(s) == AFTER_STATE
    assert '"written": 2' in captured.out and "--restore --ids 901,902" in captured.out
    assert "UNKNOWN" not in captured.out and "REFUSED" not in captured.out
    assert "after the apply above had its COMMIT acknowledged" in captured.err


def test_an_interrupt_in_the_cleanup_after_an_acknowledged_commit_keeps_its_type(
    repair, monkeypatch, capsys
):
    s = WireSession(LIVE, [])
    with pytest.raises(asyncio.CancelledError):
        _wire_main(
            repair, monkeypatch, s, "apply", dispose_raises=asyncio.CancelledError()
        )
    out = capsys.readouterr().out
    assert '"written": 2' in out and "--restore --ids 901,902" in out
    assert _durable(s) == AFTER_STATE


# CERT-4239's independent extension, made permanent (its fifteen cases, Root
# directive 015): restore through the same lost-acknowledgement and cleanup paths
# apply already pins, and the ORIGINAL cancellation object surviving every primary
# path. Same rig, same coverage limit: synthetic transport and server controls over
# the production session helper — not real PostgreSQL, not production.


@pytest.mark.parametrize("landed", [True, False], ids=["landed", "never-landed"])
@pytest.mark.parametrize("failing", ["rollback", "close", "dispose"])
def test_restore_unknown_survives_a_failing_cleanup_in_both_durable_worlds(
    repair, monkeypatch, capsys, landed, failing
):
    s = WireSession(
        AFTER,
        [],
        commit_fails={1: (_lost_ack(), landed)},
        rollback_raises=_lost_ack() if failing == "rollback" else None,
        close_raises=_lost_ack() if failing == "close" else None,
    )
    dispose = _lost_ack() if failing == "dispose" else None
    assert _wire_main(repair, monkeypatch, s, "restore", dispose_raises=dispose) == 3
    captured = capsys.readouterr()
    report = _report(captured.out)
    assert report["outcome"] == "UNKNOWN" and report["mode"] == "restore"
    assert s.commits == 1
    assert _durable(s) == (BEFORE_STATE if landed else AFTER_STATE)
    for claim in ("REFUSED", "nothing committed", "UNDO", "--restore"):
        assert claim not in captured.out


@pytest.mark.parametrize("failing", ["exit-commit", "close", "dispose"])
def test_an_acknowledged_restore_survives_a_later_helper_error(
    repair, monkeypatch, capsys, failing
):
    s = WireSession(
        AFTER,
        [],
        commit_fails={2: (_lost_ack(), False)} if failing == "exit-commit" else None,
        close_raises=_lost_ack() if failing == "close" else None,
    )
    dispose = _lost_ack() if failing == "dispose" else None
    assert _wire_main(repair, monkeypatch, s, "restore", dispose_raises=dispose) == 0
    captured = capsys.readouterr()
    assert _report(captured.out)["written"] == 2
    assert _durable(s) == BEFORE_STATE
    assert "UNKNOWN" not in captured.out and "REFUSED" not in captured.out
    assert "after the restore above had its COMMIT acknowledged" in captured.err


@pytest.mark.parametrize("mode", ["apply", "restore"])
@pytest.mark.parametrize(
    "path",
    ["commit-cancel-close-error", "unknown-cleanup-cancel", "refused-cleanup-cancel"],
)
def test_the_original_cancel_object_survives_every_primary_path(
    repair, monkeypatch, capsys, mode, path
):
    cancel = asyncio.CancelledError("the original cancel")
    dispose = None
    if path == "commit-cancel-close-error":
        s = WireSession(
            _START[mode], [], commit_fails={1: (cancel, True)}, close_raises=_lost_ack()
        )
    elif path == "unknown-cleanup-cancel":
        s = WireSession(_START[mode], [], commit_fails={1: (_lost_ack(), False)})
        dispose = cancel
    else:
        s = LockedWire(_START[mode], [], rollback_raises=cancel)
    with pytest.raises(asyncio.CancelledError) as raised:
        _wire_main(repair, monkeypatch, s, mode, dispose_raises=dispose)
    assert raised.value is cancel
    out = capsys.readouterr().out
    if path == "refused-cleanup-cancel":
        assert out.startswith("REFUSED:") and s.commits == 0
    else:
        assert _report(out)["outcome"] == "UNKNOWN" and s.commits == 1
