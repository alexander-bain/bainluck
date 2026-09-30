"""#9916 operator boundaries, using the real correction helpers and a SQL double.

These tests exercise dispatch/guards/transaction receipts, NOT Postgres locking
or new production completeness. Existing real-PG correction gates own the latter.
"""

import copy
import builtins
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils import container_corrections as cc
from scripts import collection_publication as operator


class Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def scalar(self):
        return self.rows[0][0] if self.rows else None

    def mappings(self):
        return self

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.fetchone()


class Session:
    """Models transaction state while running the actual publication helpers."""

    def __init__(self, **facts):
        self.facts = {
            "id": 101,
            "slug": "nfl-2026-week-5",
            "name": "NFL Week 5",
            "kind": "season",
            "status": "scheduled",
            "window_start": datetime(2026, 10, 8, tzinfo=timezone.utc),
            "window_end": None,
            "parent_container_id": None,
            "publication_state": "unpublished",
            "revision": 7,
            "edge_count": 2,
            "game_count": 1,
            "question_count": 1,
            "missing_row_count": 0,
            "classes": ["match_winner", "prop"],
            **facts,
        }
        self.original = copy.deepcopy(self.facts)
        self.ledger = []
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.schema = True
        self.missing = False
        self.on_lock = None
        self.commit_error = False
        self.ledger_error = False
        self.close_error = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        if self.close_error:
            raise RuntimeError("cleanup failed")

    async def execute(self, sql, params=None):
        sql = str(sql)
        params = params or {}
        self.statements.append((sql, copy.deepcopy(params)))
        if sql.startswith("SET TRANSACTION"):
            return Result()
        if "to_regclass('public.container_corrections')" in sql:
            return Result([(self.schema, self.schema)])
        if "WITH hub AS" in sql:
            return Result([] if self.missing else [copy.deepcopy(self.facts)])
        if "FOR UPDATE OF c" in sql:
            if self.on_lock:
                self.on_lock(self)
                self.on_lock = None
            if self.missing:
                return Result()
            return Result(
                [
                    (
                        self.facts["id"],
                        self.facts["publication_state"],
                        self.facts["revision"],
                        0,
                    )
                ]
            )
        if "SELECT count(*) FROM event_edges" in sql:
            return Result([(self.facts["edge_count"],)])
        if sql.startswith("UPDATE containers SET publication_state"):
            self.facts["publication_state"] = params["state"]
            return Result()
        if "RETURNING id, membership_revision" in sql:
            self.facts["revision"] += 1
            return Result([(self.facts["id"], self.facts["revision"])])
        if "INSERT INTO container_corrections" in sql:
            if self.ledger_error:
                raise RuntimeError("ledger write failed")
            self.ledger.append(params)
            return Result()
        raise AssertionError(f"unhandled SQL: {sql}")

    async def commit(self):
        self.commits += 1
        if self.commit_error:
            raise RuntimeError("secret DSN must never appear in a receipt")
        self.original = copy.deepcopy(self.facts)

    async def rollback(self):
        self.rollbacks += 1
        self.facts = copy.deepcopy(self.original)
        self.ledger.clear()


def apply_options(operation="publish", **changes):
    return operator.Options(
        container_id=101,
        slug="nfl-2026-week-5",
        operation=operation,
        apply=True,
        expected_revision=7,
        actor="authority",
        reason="reviewed selected edition",
        evidence={"review": "receipt-9916"},
        **changes,
    )


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--slug", ""],
        ["--container-id", "0"],
        ["--container-id", "-1"],
        ["--slug", " nfl-2026-week-5"],
        ["--slug", "nfl-2026-week-5", "--expected-revision", "-1"],
        ["--container-id", "101", "--container-id", "102"],
        ["--slug", "nfl-2026-week-5", "--slug", "mlb-2026-postseason"],
        ["--container-id", "101", "--operation", "assemble"],
        ["--container-id", "101", "--evidence", "not JSON"],
        ["--container-id", "101", "--evidence", "[]"],
    ],
)
def test_parser_refuses_unbounded_or_malformed_inputs(argv):
    with pytest.raises(operator.OperatorRefused):
        operator.parse_args(argv)


@pytest.mark.parametrize(
    "changes",
    [
        {"container_id": None},
        {"slug": None},
        {"operation": None},
        {"expected_revision": None},
        {"actor": " "},
        {"actor": "a" * 65},
        {"reason": ""},
        {"evidence": None},
        {"evidence": {}},
    ],
)
def test_every_apply_guard_is_required_even_for_programmatic_callers(changes):
    with pytest.raises(operator.OperatorRefused):
        operator.validate(replace(apply_options(), **changes))


def test_parser_has_no_default_operation_or_apply():
    options = operator.parse_args(["--slug", "nfl-2026-week-5"])
    assert not options.apply
    assert options.operation is None


def test_parser_retains_explicit_decision_evidence():
    options = operator.parse_args(
        [
            "--container-id",
            "101",
            "--slug",
            "nfl-2026-week-5",
            "--operation",
            "publish",
            "--apply",
            "--expected-revision",
            "7",
            "--actor",
            "authority",
            "--reason",
            "reviewed hub",
            "--evidence",
            '{"review":"receipt-9916"}',
        ]
    )
    assert options.apply and options.expected_revision == 7
    assert options.evidence == {"review": "receipt-9916"}


@pytest.mark.asyncio
async def test_default_preview_is_database_read_only_and_never_commits():
    session = Session()
    receipt, code = await operator.run(
        operator.Options(container_id=101), lambda: session
    )
    assert code == 0 and receipt["status"] == "preview"
    assert receipt["committed"] is False and receipt["rollback"] is None
    assert receipt["edition"]["week"] == 5
    assert receipt["target"]["game_count"] == receipt["target"]["question_count"] == 1
    assert session.commits == 0 and session.rollbacks == 1 and session.ledger == []
    assert "READ ONLY" in session.statements[0][0]
    assert not any(
        "FOR UPDATE" in sql or "UPDATE containers" in sql or "INSERT" in sql
        for sql, _ in session.statements
    )


@pytest.mark.asyncio
async def test_operation_preview_does_not_invoke_mutation_helper(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("preview called a write helper")

    monkeypatch.setattr(cc, "publish_container", forbidden)
    session = Session()
    receipt, code = await operator.run(
        replace(apply_options(), apply=False), lambda: session
    )
    assert code == 0 and receipt["operation"] == "publish"
    assert session.commits == 0


@pytest.mark.asyncio
async def test_explicit_slug_preview_binds_exact_target_and_reports_missing_rows():
    session = Session(missing_row_count=1)
    receipt, code = await operator.run(
        operator.Options(slug="nfl-2026-week-5"), lambda: session
    )
    assert code == 0 and receipt["target"]["missing_row_count"] == 1
    sql, params = session.statements[-1]
    assert "WHERE slug = :slug" in sql and params["slug"] == "nfl-2026-week-5"
    assert "completeness requires Authority" in receipt["coverage_limit"]


@pytest.mark.parametrize(
    "facts",
    [
        {"slug": "nfl-2026"},
        {"slug": "nfl-2026-week-05"},
        {"slug": "nfl-2026-week-0"},
        {"slug": "wimbledon-2026"},
        {"parent_container_id": 200},
    ],
)
@pytest.mark.asyncio
async def test_ineligible_editions_and_nested_targets_cannot_publish(facts):
    session = Session(**facts)
    options = replace(apply_options(), slug=session.facts["slug"])
    receipt, code = await operator.run(options, lambda: session)
    assert code == 1 and receipt["status"] == "refused"
    assert session.commits == 0 and session.ledger == []


@pytest.mark.parametrize("field,value", [("slug", "nfl-2026-week-6"), ("revision", 8)])
@pytest.mark.asyncio
async def test_identity_or_revision_drift_after_lock_refuses_before_any_write(
    field, value
):
    session = Session()
    session.on_lock = lambda current: current.facts.update({field: value})
    receipt, code = await operator.run(apply_options(), lambda: session)
    assert code == 1 and receipt["committed"] is False
    assert session.commits == 0 and session.rollbacks == 1
    assert not any(
        "UPDATE containers" in sql or "INSERT" in sql for sql, _ in session.statements
    )


@pytest.mark.asyncio
async def test_missing_or_unmigrated_target_is_refused():
    for failure in ("missing", "schema"):
        session = Session()
        setattr(session, failure, failure == "missing")
        receipt, code = await operator.run(apply_options(), lambda: session)
        assert code == 1 and receipt["status"] == "refused" and session.commits == 0


@pytest.mark.asyncio
async def test_empty_publish_is_refused_but_empty_withdraw_is_allowed_by_helper():
    session = Session(edge_count=0, game_count=0, question_count=0)
    receipt, code = await operator.run(apply_options(), lambda: session)
    assert code == 1 and session.commits == 0
    receipt, code = await operator.run(apply_options("withdraw"), lambda: session)
    assert code == 0 and receipt["target"]["publication_state"] == "withdrawn"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_dangling_only_edges_do_not_count_as_a_publishable_reader_hub():
    session = Session(edge_count=2, game_count=0, question_count=0, missing_row_count=2)
    receipt, code = await operator.run(apply_options(), lambda: session)
    assert code == 1 and session.commits == 0 and session.ledger == []


@pytest.mark.asyncio
async def test_real_helper_records_decision_and_cli_commits_only_after_preparation():
    session = Session()
    receipt = await operator.prepare(session, apply_options())
    assert session.commits == session.rollbacks == 0
    assert receipt["status"] == "prepared" and receipt["committed"] is False
    assert receipt["before"]["revision"] == 7 and receipt["target"]["revision"] == 8
    assert session.ledger[0]["scope"] == "publication"
    assert session.ledger[0]["actor"] == "authority"
    assert json.loads(session.ledger[0]["evidence"]) == {"review": "receipt-9916"}
    assert receipt["decision"]["evidence"] == {"review": "receipt-9916"}
    await session.rollback()
    receipt, code = await operator.run(apply_options(), lambda: session)
    assert code == 0 and session.commits == 1
    assert receipt["status"] == "applied" and receipt["committed"] is True
    assert receipt["rollback"]["operation"] == "withdraw"
    assert receipt["rollback"]["expected_revision_at_commit"] == 8
    assert receipt["rollback"]["runnable_without_fresh_review"] is False
    assert "committed_at" in receipt


@pytest.mark.asyncio
async def test_idempotent_helper_result_never_offers_to_undo_existing_publication():
    session = Session(publication_state="published")
    receipt, code = await operator.run(apply_options(), lambda: session)
    assert code == 0 and receipt["status"] == "noop"
    assert receipt["correction"]["applied"] is False and session.ledger == []
    assert receipt["rollback"]["operation"] is None
    assert receipt["target"]["revision"] == 7


@pytest.mark.asyncio
async def test_ledger_failure_rolls_back_the_helper_partial_write():
    session = Session()
    session.ledger_error = True
    receipt, code = await operator.run(apply_options(), lambda: session)
    assert code == 1 and receipt["status"] == "failed"
    assert session.commits == 0 and session.rollbacks == 1
    assert (
        session.facts["publication_state"] == "unpublished"
        and session.facts["revision"] == 7
    )
    assert receipt["rollback"] is None


@pytest.mark.asyncio
async def test_commit_failure_is_unknown_not_a_claim_that_nothing_happened():
    session = Session()
    session.commit_error = True
    receipt, code = await operator.run(apply_options(), lambda: session)
    assert code == 1 and receipt["status"] == "commit_outcome_unknown"
    assert receipt["committed"] is None and receipt["rollback"] is None
    assert "secret" not in json.dumps(receipt)


@pytest.mark.asyncio
async def test_mlb_uses_existing_canonical_edition_and_withdraw_rollback_requires_review():
    session = Session(slug="mlb-2026-postseason", publication_state="published")
    receipt, code = await operator.run(
        replace(apply_options("withdraw"), slug="mlb-2026-postseason"), lambda: session
    )
    assert code == 0 and receipt["edition"] == {
        "kind": "mlb_postseason",
        "league": "mlb",
        "season": 2026,
    }
    assert receipt["rollback"]["operation"] == "publish"
    assert receipt["rollback"]["runnable_without_fresh_review"] is False


@pytest.mark.asyncio
async def test_a_later_revision_refuses_reusing_the_old_rollback_prerequisite():
    session = Session(publication_state="published", revision=9)
    receipt, code = await operator.run(
        replace(apply_options("withdraw"), expected_revision=8), lambda: session
    )
    assert code == 1 and session.commits == 0 and "revision 9" in receipt["error"]


def test_cli_refusal_is_machine_readable_before_any_database_initialization(
    monkeypatch, capsys
):
    async def forbidden(options):
        pytest.fail("invalid arguments initialized a database")

    monkeypatch.setattr(operator, "_run_configured", forbidden)
    assert operator.main(["--apply", "--container-id", "101"]) == 2
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "refused" and receipt["committed"] is False


def test_cli_serializes_timestamps_and_does_not_expose_database_config(
    monkeypatch, capsys
):
    async def configured(options):
        return await operator.run(options, lambda: Session())

    monkeypatch.setattr(operator, "_run_configured", configured)
    assert operator.main(["--slug", "nfl-2026-week-5"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["target"]["window_start"] == "2026-10-08T00:00:00+00:00"
    assert "DATABASE_URL" not in json.dumps(receipt)


@pytest.mark.asyncio
async def test_wrong_id_does_not_fall_back_to_the_matching_slug():
    session = Session()
    receipt, code = await operator.run(
        replace(apply_options(), container_id=102), lambda: session
    )
    assert code == 1 and session.commits == 0 and session.ledger == []
    assert "ID does not match" in receipt["error"]


@pytest.mark.asyncio
async def test_cleanup_failure_after_commit_does_not_claim_the_write_never_ran():
    session = Session()
    session.close_error = True
    receipt, code = await operator.run(apply_options(), lambda: session)
    assert code == 1 and receipt["status"] == "cleanup_failed_after_commit"
    assert receipt["committed"] is True and receipt["correction"]["revision"] == 8


def test_non_json_evidence_is_refused_before_a_write():
    with pytest.raises(operator.OperatorRefused, match="only valid JSON"):
        operator.validate(replace(apply_options(), evidence={"invalid": float("nan")}))


def test_no_implicit_local_database_fallback(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert operator.main(["--container-id", "101"]) == 2
    receipt = json.loads(capsys.readouterr().out)
    assert (
        receipt["status"] == "refused" and "explicitly configured" in receipt["error"]
    )


@pytest.mark.parametrize("app_name", [None, "bainluck"])
def test_apply_refuses_outside_named_app_before_database_import(
    app_name, monkeypatch, capsys
):
    monkeypatch.setenv("DATABASE_URL", "configured-but-must-not-connect")
    if app_name is None:
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    else:
        monkeypatch.setenv("HEROKU_APP_NAME", app_name)
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "app.services.database":
            pytest.fail("refused apply initialized a database")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    code = operator.main(
        [
            "--container-id",
            "101",
            "--slug",
            "nfl-2026-week-5",
            "--operation",
            "publish",
            "--apply",
            "--expected-revision",
            "7",
            "--actor",
            "authority",
            "--reason",
            "reviewed hub",
            "--evidence",
            '{"review":"receipt-9916"}',
        ]
    )
    receipt = json.loads(capsys.readouterr().out)
    assert code == 2 and receipt["status"] == "refused"
    assert receipt["committed"] is False and "bainluck-heavy" in receipt["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "apply,app_name",
    [
        (True, "bainluck-heavy"),
        (False, None),
        (False, "bainluck"),
        (False, "bainluck-heavy"),
    ],
)
async def test_configured_apply_on_named_app_and_preview_anywhere_dispatch(
    apply, app_name, monkeypatch
):
    monkeypatch.setenv("DATABASE_URL", "configured-test-database")
    if app_name is None:
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    else:
        monkeypatch.setenv("HEROKU_APP_NAME", app_name)
    session_factory = object()
    monkeypatch.setitem(
        sys.modules,
        "app.services.database",
        SimpleNamespace(async_session_maker=session_factory),
    )
    options = apply_options() if apply else operator.Options(container_id=101)

    async def dispatched(got_options, got_factory):
        assert got_options == options and got_factory is session_factory
        return {"status": "dispatched"}, 0

    monkeypatch.setattr(operator, "run", dispatched)
    assert await operator._run_configured(options) == ({"status": "dispatched"}, 0)
