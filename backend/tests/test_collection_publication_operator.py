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

    def one(self):
        assert len(self.rows) == 1
        return self.rows[0]

    def all(self):
        return self.rows


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


# ---------------------------------------------------------------------------
# #9649 member withdraw / exact restore — guards, scope and receipts
# ---------------------------------------------------------------------------
#
# The double models the stored rows and runs the REAL withdraw_member /
# readmit_member helpers. Postgres-only behaviour (locks, to_jsonb text, typed
# re-insert, FKs) is graded in tests/integration/test_container_assembly_real_postgres.py.

EDGE_COLUMNS = {
    "id": "bigint",
    "parent_id": "bigint",
    "parent_type": "character varying(16)",
    "child_id": "bigint",
    "child_type": "character varying(16)",
    "kind": "character varying(24)",
    "class": "character varying(32)",
    "source": "character varying(32)",
    "confidence": "numeric(4,3)",
    "receipt_id": "bigint",
    "created_at": "timestamp with time zone",
}


class World:
    """Committed state shared by every session the factory opens."""

    def __init__(self):
        self.columns = dict(EDGE_COLUMNS)
        self.state = {"containers": {}, "edges": {}, "markets": {}, "ledger": []}
        self.games = {}
        self.statements = []
        self.commits = 0
        self.schema = True
        self.commit_error_on = None
        self.on_lock = None
        self.committed = None

    def edge(self, edge_id, parent_id, child_type, child_id, klass):
        self.state["edges"][edge_id] = {
            "id": str(edge_id),
            "parent_id": str(parent_id),
            "parent_type": "container",
            "child_id": str(child_id),
            "child_type": child_type,
            "kind": "contains",
            "class": klass,
            "source": "venue_grouping",
            "confidence": "0.875",
            "receipt_id": None,
            "created_at": "2026-09-29T21:50:33.123456+00:00",
        }

    def seal(self):
        self.committed = copy.deepcopy(self.state)

    def factory(self):
        return MemberSession(self)


class MemberSession:
    def __init__(self, world):
        self.world = world

    @property
    def s(self):
        return self.world.state

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def commit(self):
        cids = {int(e["parent_id"]) for e in self.s["edges"].values()}
        if self.world.commit_error_on in cids and self._touches(
            self.world.commit_error_on
        ):
            raise RuntimeError("secret DSN must never appear in a receipt")
        self.world.commits += 1
        self.world.committed = copy.deepcopy(self.s)

    def _touches(self, cid):
        return (
            self.s["containers"][cid]["revision"]
            != self.world.committed["containers"][cid]["revision"]
        )

    async def rollback(self):
        self.world.state = copy.deepcopy(self.world.committed)

    def _edges(self, cid, child_type):
        return [
            e
            for e in self.s["edges"].values()
            if e["parent_id"] == str(cid) and e["child_type"] == child_type
        ]

    def _admitted(self, cid, event_id):
        for e in self._edges(cid, "event"):
            if e["child_id"] == str(event_id):
                return int(e["id"])
        return None

    async def execute(self, sql, params=None):
        sql, params = str(sql), params or {}
        self.world.statements.append((sql, copy.deepcopy(params)))
        s = self.s
        if sql.startswith("SET "):
            return Result()
        if "to_regclass('public.container_corrections')" in sql:
            return Result([(self.world.schema, self.world.schema)])
        if "FOR UPDATE OF c" in sql:
            if self.world.on_lock:
                self.world.on_lock(self.world)
                self.world.on_lock = None
            c = s["containers"].get(params["cid"])
            return Result([(params["cid"], c["pub"], c["revision"], 0)] if c else [])
        if "FROM containers c WHERE c.id = :cid" in sql:
            c = s["containers"].get(params["cid"])
            if c is None:
                return Result()
            return Result(
                [
                    {
                        "id": params["cid"],
                        "slug": c["slug"],
                        "parent_container_id": c.get("parent"),
                        "publication_state": c["pub"],
                        "revision": c["revision"],
                        "events": len(self._edges(params["cid"], "event")),
                        "market_edges": len(self._edges(params["cid"], "market")),
                    }
                ]
            )
        if "SELECT DISTINCT ON (child_type, child_id)" in sql:
            latest = {}
            for row in s["ledger"]:
                if row["container_id"] == params["cid"] and row["scope"] == "member":
                    latest[(row["child_type"], row["child_id"])] = row["action"]
            return Result([(k[0], k[1], a) for k, a in latest.items()])
        if "ORDER BY id DESC LIMIT 1" in sql:
            rows = [
                r
                for r in s["ledger"]
                if r["container_id"] == params["cid"]
                and r["scope"] == "member"
                and r["child_id"] == params["mid"]
            ]
            return Result([rows[-1]] if rows else [])
        if "FROM container_corrections WHERE container_id = :cid ORDER BY id" in sql:
            return Result(
                [r for r in s["ledger"] if r["container_id"] == params["cid"]]
            )
        if "pg_attribute" in sql:
            return Result(list(self.world.columns.items()))
        if "jsonb_each_text" in sql:
            return Result(
                [
                    (int(e["id"]), k, v)
                    for e in s["edges"].values()
                    if int(e["id"]) in params["ids"]
                    for k, v in e.items()
                ]
            )
        if "LEFT JOIN futures_markets fm" in sql:
            rows = []
            for edge_id in params["ids"]:
                e = s["edges"].get(edge_id)
                if e is None:
                    continue
                m = (
                    s["markets"].get(int(e["child_id"]))
                    if e["child_type"] == "market"
                    else None
                )
                rows.append(
                    {
                        "edge_id": edge_id,
                        "parent_type": e["parent_type"],
                        "parent_id": int(e["parent_id"]),
                        "child_type": e["child_type"],
                        "child_id": int(e["child_id"]),
                        "kind": e["kind"],
                        "class": e["class"],
                        "market_id": int(e["child_id"]) if m else None,
                        **(
                            m
                            or dict.fromkeys(
                                (
                                    "source",
                                    "external_id",
                                    "name",
                                    "market_type",
                                    "event_id",
                                )
                            )
                        ),
                        "admitted_edge_id": (
                            self._admitted(params["cid"], m["event_id"]) if m else None
                        ),
                    }
                )
            return Result(rows)
        if "FROM futures_markets fm" in sql:
            return Result(
                [
                    {
                        "market_id": mid,
                        **s["markets"][mid],
                        "admitted_edge_id": self._admitted(
                            params["cid"], s["markets"][mid]["event_id"]
                        ),
                    }
                    for mid in params["ids"]
                    if mid in s["markets"]
                ]
            )
        if "SELECT id, parent_id, child_id FROM event_edges" in sql:
            return Result(
                [
                    (int(e["id"]), int(e["parent_id"]), int(e["child_id"]))
                    for e in s["edges"].values()
                    if int(e["id"]) in params["edge_ids"]
                    or (
                        e["parent_id"] == str(params["cid"])
                        and e["child_type"] == "market"
                        and int(e["child_id"]) in params["market_ids"]
                    )
                ]
            )
        if "FROM market_match_receipts" in sql:
            return Result([(i,) for i in params["ids"] if i in self.world.receipts])
        if sql.startswith("DELETE FROM event_edges"):
            gone = [
                k
                for k, e in s["edges"].items()
                if e["parent_id"] == str(params["cid"])
                and e["child_type"] == params["ct"]
                and e["child_id"] == str(params["id"])
            ]
            for k in gone:
                del s["edges"][k]
            return SimpleNamespace(rowcount=len(gone))
        if "RETURNING id, membership_revision" in sql:
            c = s["containers"][params["cid"]]
            c["revision"] += 1
            return Result([(params["cid"], c["revision"])])
        if "INSERT INTO container_corrections" in sql:
            s["ledger"].append(
                {
                    "id": max([r["id"] for r in s["ledger"]] + [0]) + 1,
                    "container_id": params["cid"],
                    "scope": params["scope"],
                    "action": params["action"],
                    "child_type": params["ct"],
                    "child_id": params["child_id"],
                    "revision": params["revision"],
                    "evidence": params["evidence"],
                }
            )
            return Result()
        if sql.startswith("INSERT INTO event_edges"):
            row = {n: params[f"v{i}"] for i, n in enumerate(self.world.columns)}
            assert row["id"] not in [e["id"] for e in s["edges"].values()]
            s["edges"][int(row["id"])] = row
            return Result()
        raise AssertionError(f"unhandled SQL: {sql}")


def _week_world(tmp_path):
    """Week 4 (two games, two winners each) and Week 5 (one game, three)."""
    world = World()
    world.receipts = set()
    targets, edge_id, market_id = [], 5000, 60000
    layout = {
        7: ("nfl-2026-week-4", [(14780550, 2), (14639205, 2)]),
        8: ("nfl-2026-week-5", [(14780556, 3)]),
    }
    pins = {}
    for cid, (slug, games) in layout.items():
        world.state["containers"][cid] = {
            "slug": slug,
            "pub": "published",
            "revision": 2,
        }
        world.state["ledger"].append(
            {
                "id": len(world.state["ledger"]) + 1,
                "container_id": cid,
                "scope": "publication",
                "action": "publish",
                "child_type": None,
                "child_id": None,
                "revision": 2,
                "evidence": None,
            }
        )
        for event_id, winners in games:
            edge_id += 1
            world.edge(edge_id, cid, "event", event_id, "match_winner")
            for n in range(winners + 1):  # the last one is the "1H Moneyline" control
                edge_id, market_id = edge_id + 1, market_id + 1
                venue = "kalshi" if n == 0 else "polymarket"
                name = (
                    "PIT Steelers vs CLE Browns" if n < winners else "1H Moneyline: x"
                )
                world.state["markets"][market_id] = {
                    "source": venue,
                    "external_id": f"X-{market_id}",
                    "name": name,
                    "market_type": "duel",
                    "event_id": event_id,
                }
                is_target = n < winners
                world.edge(
                    edge_id,
                    cid,
                    "market",
                    market_id,
                    "match_winner" if is_target else "prop",
                )
                if is_target:
                    targets.append(
                        dict(
                            container_id=cid,
                            container_slug=slug,
                            expected_revision=2,
                            edge_id=edge_id,
                            edge_class="match_winner",
                            child_type="market",
                            market_id=market_id,
                            venue=venue,
                            market_type="duel",
                            event_id=event_id,
                            external_id=f"X-{market_id}",
                        )
                    )
        pins[str(cid)] = {
            "slug": slug,
            "publication_state": "published",
            "membership_revision": 2,
            "events": len(games),
            "market_edges": sum(w + 1 for _, w in games),
            "targets": sum(w for _, w in games),
            "ledger_rows": [
                r["id"] for r in world.state["ledger"] if r["container_id"] == cid
            ],
        }
    world.seal()
    manifest = {"issue": 9649, "pins": pins, "targets": targets}
    path = tmp_path / "MANIFEST.json"
    path.write_text(json.dumps(manifest))
    return world, manifest, path


def _write(tmp_path, name, doc):
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return str(path)


def member_options(**changes):
    return operator.Options(operation=operator.MEMBER_WITHDRAW, **changes)


def member_apply(source, revisions, operation=operator.MEMBER_WITHDRAW, **changes):
    key = "manifest" if operation == operator.MEMBER_WITHDRAW else "backup"
    return operator.Options(
        operation=operation,
        apply=True,
        restore_from_ledger=operation == operator.MEMBER_RESTORE,
        hub_revisions=tuple(revisions.items()),
        actor="authority",
        reason="#9649 winner duplicates",
        evidence={"review": "test"},
        **{key: str(source)},
        **changes,
    )


def _no_writes(world):
    return not any(
        sql.startswith(("DELETE", "INSERT")) or "RETURNING" in sql
        for sql, _ in world.statements
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["--operation", "withdraw-members"],
        ["--operation", "withdraw-members", "--manifest", "m", "--backup", "b"],
        [
            "--operation",
            "withdraw-members",
            "--manifest",
            "m",
            "--expected-revision",
            "2",
        ],
        ["--operation", "readmit-members", "--backup", "b"],
        ["--operation", "readmit-members", "--restore-from-ledger"],
        [
            "--operation",
            "readmit-members",
            "--restore-from-ledger",
            "--backup",
            "b",
            "--manifest",
            "m",
        ],
        ["--operation", "withdraw-members", "--manifest", "m", "--hub-revision", "7"],
        [
            "--operation",
            "withdraw-members",
            "--manifest",
            "m",
            "--hub-revision",
            "7:2",
            "--hub-revision",
            "7:3",
        ],
        ["--operation", "withdraw-members", "--manifest", "m", "--apply"],
        [
            "--container-id",
            "7",
            "--slug",
            "nfl-2026-week-4",
            "--operation",
            "publish",
            "--manifest",
            "m",
        ],
    ],
)
def test_member_parser_refuses_unscoped_or_mixed_inputs(argv):
    with pytest.raises(operator.OperatorRefused):
        operator.parse_args(argv)


def test_member_parser_accepts_repeatable_hub_revisions():
    options = operator.parse_args(
        [
            "--operation",
            "withdraw-members",
            "--manifest",
            "m",
            "--hub-revision",
            "7:2",
            "--hub-revision",
            "8:2",
        ]
    )
    assert options.hub_revisions == ((7, 2), (8, 2)) and not options.apply


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda m: m.update(targets=[]),
        lambda m: m.update(pins={}),
        lambda m: m["targets"].append(copy.deepcopy(m["targets"][0])),
        lambda m: m["targets"][1].update(market_id=m["targets"][0]["market_id"]),
        lambda m: m["targets"][0].update(container_id=99),
        lambda m: m["targets"][0].update(container_slug="nfl-2026-week-6"),
        lambda m: m["targets"][0].update(expected_revision=3),
        lambda m: m["targets"][0].update(market_type="field"),
        lambda m: m["targets"][0].update(child_type="event"),
        lambda m: m["targets"][0].pop("edge_id"),
        lambda m: m["targets"][0].update(edge_id=True),
        lambda m: m["pins"]["7"].update(targets=3),
        lambda m: m["pins"]["7"].update(ledger_rows=["1"]),
    ],
)
def test_malformed_duplicate_or_foreign_manifests_refuse_before_a_database(
    tmp_path, corrupt
):
    _, manifest, _ = _week_world(tmp_path)
    corrupt(manifest)
    path = _write(tmp_path, "bad.json", manifest)
    with pytest.raises(operator.OperatorRefused):
        operator.load_member_plan(member_options(manifest=path))


def test_unreadable_manifest_refuses(tmp_path):
    with pytest.raises(operator.OperatorRefused, match="readable JSON"):
        operator.load_member_plan(member_options(manifest=str(tmp_path / "none")))


@pytest.mark.parametrize(
    "revisions,match",
    [
        ({7: 2}, "exactly the hubs"),
        ({7: 2, 8: 2, 9: 1}, "exactly the hubs"),
        ({7: 3, 8: 2}, "verified precondition 2"),
    ],
)
def test_apply_revisions_must_be_the_manifests_verified_preconditions(
    tmp_path, revisions, match
):
    _, _, path = _week_world(tmp_path)
    with pytest.raises(operator.OperatorRefused, match=match):
        operator.load_member_plan(member_apply(path, revisions))


def test_a_selected_hub_is_operated_alone(tmp_path):
    _, _, path = _week_world(tmp_path)
    plan = operator.load_member_plan(
        member_apply(path, {7: 2}, container_id=7, slug="nfl-2026-week-4")
    )
    assert [h.container_id for h in plan.hubs] == [7]
    assert len(plan.hubs[0].targets) == 4
    with pytest.raises(operator.OperatorRefused):
        operator.load_member_plan(member_options(manifest=str(path), container_id=9))
    with pytest.raises(operator.OperatorRefused):
        operator.load_member_plan(
            member_options(manifest=str(path), container_id=7, slug="nfl-2026-week-5")
        )


@pytest.mark.asyncio
async def test_default_member_preview_is_read_only_and_never_a_backup(tmp_path):
    world, _, path = _week_world(tmp_path)
    doc, code = await operator.run_members(
        member_options(manifest=str(path)), world.factory
    )
    assert code == 0 and doc["status"] == "preview" and doc["committed_hubs"] == []
    assert [h["would_be_revision"] for h in doc["hubs"]] == [6, 5]
    assert all(
        h["receipt_kind"] == "preview" and h["undo"] is None for h in doc["hubs"]
    )
    assert world.commits == 0 and _no_writes(world)
    assert sum("READ ONLY" in sql for sql, _ in world.statements) == 2
    assert not any("FOR UPDATE" in sql for sql, _ in world.statements)
    backup = _write(tmp_path, "preview.json", doc)
    with pytest.raises(operator.OperatorRefused, match="preview"):
        operator.load_member_plan(
            operator.Options(
                operation=operator.MEMBER_RESTORE,
                restore_from_ledger=True,
                backup=backup,
            )
        )


def _drift(kind):
    def apply(world):
        s = world.state
        edge = s["edges"][5002]  # week 4, first game, Kalshi winner
        market = s["markets"][int(edge["child_id"])]
        if kind == "missing_edge":
            del s["edges"][5002]
        elif kind == "class":
            edge["class"] = "prop"
        elif kind == "foreign_container":
            edge["parent_id"] = "8"
        elif kind == "provider":
            market["source"] = "polymarket"
        elif kind == "event":
            market["event_id"] = 1
        elif kind == "classifier":
            market["name"] = "Spread: Pittsburgh Steelers (-2.5)"
        elif kind == "shape":
            market["market_type"] = "field"
        elif kind == "ledger":
            s["ledger"].append(
                {
                    "id": 9,
                    "container_id": 7,
                    "scope": "member",
                    "action": "withdraw",
                    "child_type": "market",
                    "child_id": 1,
                    "revision": 2,
                    "evidence": None,
                }
            )
        elif kind == "unpublished":
            s["containers"][7]["pub"] = "withdrawn"
        elif kind == "revision":
            s["containers"][7]["revision"] = 3
        elif kind == "slug":
            s["containers"][7]["slug"] = "nfl-2026-week-6"

    return apply


DRIFTS = {
    "missing_edge": "does not exist",
    "class": "class is 'prop'",
    "foreign_container": "parent_id is 8",
    "provider": "source is 'polymarket'",
    "event": "event_id is 1",
    "classifier": "no longer says True",
    "shape": "market_type is 'field'",
    "ledger": "ledger drift",
    "unpublished": "publication state drifted",
    "revision": "revision 3, not 2",
    "slug": "slug is 'nfl-2026-week-6'",
}


@pytest.mark.parametrize("kind", DRIFTS)
@pytest.mark.asyncio
async def test_drifted_targets_refuse_every_hub_before_a_write(tmp_path, kind):
    world, _, path = _week_world(tmp_path)
    _drift(kind)(world)
    world.seal()
    doc, code = await operator.run_members(
        member_apply(path, {7: 2, 8: 2}), world.factory
    )
    assert code == 1 and doc["status"] == "refused" and doc["committed_hubs"] == []
    week4, week5 = doc["hubs"]
    assert week4["status"] == "refused" and week4["committed"] is False
    assert DRIFTS[kind] in week4["error"] + " ".join(week4["errors"]), week4
    # A foreign edge also drifts the hub it moved into: both refuse on their own.
    assert week5["status"] == (
        "refused" if kind == "foreign_container" else "not_attempted"
    )
    assert world.commits == 0 and _no_writes(world)


@pytest.mark.asyncio
async def test_a_target_whose_game_belongs_to_another_hub_is_refused(tmp_path):
    """Counts, ids and classifier all agree; only the admitted-game test sees it."""
    world, manifest, _ = _week_world(tmp_path)
    target = next(t for t in manifest["targets"] if t["edge_id"] == 5002)
    target["event_id"] = 14780556  # Week 5's game
    world.state["markets"][target["market_id"]]["event_id"] = 14780556
    world.seal()
    path = _write(tmp_path, "foreign-game.json", manifest)
    doc, code = await operator.run_members(
        member_apply(path, {7: 2, 8: 2}), world.factory
    )
    week4 = doc["hubs"][0]
    assert code == 1 and week4["status"] == "refused"
    assert week4["errors"] == [
        f"market {target['market_id']}: event 14780556 is not an admitted game "
        "of container 7"
    ]
    assert world.commits == 0 and _no_writes(world)


@pytest.mark.parametrize("kind", ["class", "classifier", "revision", "ledger"])
@pytest.mark.asyncio
async def test_drift_landing_after_preflight_is_caught_under_the_lock(tmp_path, kind):
    world, _, path = _week_world(tmp_path)
    world.on_lock = _drift(kind)
    doc, code = await operator.run_members(
        member_apply(path, {7: 2, 8: 2}), world.factory
    )
    assert code == 1 and doc["committed_hubs"] == []
    assert [h["status"] for h in doc["hubs"]] == ["refused", "not_attempted"]
    week4 = doc["hubs"][0]
    assert DRIFTS[kind] in week4["error"] + " ".join(week4["errors"]), week4
    assert world.committed["containers"][7]["revision"] == 2
    assert len(world.committed["ledger"]) == 2


@pytest.mark.asyncio
async def test_apply_withdraws_each_target_and_composes_revisions(tmp_path):
    world, manifest, path = _week_world(tmp_path)
    before = copy.deepcopy(world.state["edges"])
    doc, code = await operator.run_members(
        member_apply(path, {7: 2, 8: 2}), world.factory
    )
    assert code == 0 and doc["status"] == "applied" and doc["committed_hubs"] == [7, 8]
    week4, week5 = doc["hubs"]
    assert (week4["pre_revision"], week4["post_revision"]) == (2, 6)
    assert [t["revision_after"] for t in week4["targets"]] == [3, 4, 5, 6]
    assert (week5["pre_revision"], week5["post_revision"]) == (2, 5)
    assert week4["games"] == {"before": 2, "after": 2}
    assert week5["market_edges"] == {"before": 4, "after": 1}
    assert world.committed["containers"][7]["revision"] == 6
    ids = {t["edge_id"] for t in manifest["targets"]}
    assert not ids & set(world.committed["edges"])
    member_rows = [r for r in world.committed["ledger"] if r["scope"] == "member"]
    assert len(member_rows) == 7 and {r["action"] for r in member_rows} == {"withdraw"}
    for receipt in doc["hubs"]:
        assert receipt["receipt_kind"] == "withdraw_apply" and receipt["committed"]
        assert receipt["backup_sha256"] == operator.preimage_fingerprint(
            [t["preimage"] for t in receipt["targets"]]
        )
        assert receipt["undo"]["hub_revision"] == receipt["post_revision"]
        assert receipt["undo"]["runnable_without_fresh_review"] is False
        for t in receipt["targets"]:
            assert t["preimage"] == before[t["edge_id"]]
            row = next(r for r in member_rows if r["id"] == t["ledger_id"])
            evidence = json.loads(row["evidence"])
            assert evidence["preimage"] == before[t["edge_id"]]
            assert evidence["ledger_ids_before"] == [receipt["container_id"] - 6]
            assert evidence["classifier"]["result"] is True
            assert evidence["identity"]["admitted_event_edge_id"] is not None
            assert evidence["source"]["sha256"] == doc["source"]["sha256"]
            assert row["revision"] == t["revision_after"]


@pytest.mark.asyncio
async def test_an_exception_mid_hub_rolls_it_back_and_reports_the_earlier_commit(
    tmp_path, monkeypatch
):
    world, _, path = _week_world(tmp_path)
    real, calls = cc.withdraw_member, []

    async def flaky(session, **kwargs):
        calls.append(kwargs["container_id"])
        if calls.count(8) == 2:
            raise RuntimeError("driver error with a secret DSN")
        return await real(session, **kwargs)

    monkeypatch.setattr(cc, "withdraw_member", flaky)
    doc, code = await operator.run_members(
        member_apply(path, {7: 2, 8: 2}), world.factory
    )
    assert code == 1 and doc["status"] == "partial" and doc["committed_hubs"] == [7]
    week4, week5 = doc["hubs"]
    assert week4["status"] == "applied" and week4["committed"] is True
    assert week5["status"] == "failed" and week5["committed"] is False
    assert week5["error"] == "RuntimeError" and "secret" not in json.dumps(doc)
    assert world.committed["containers"][8]["revision"] == 2
    assert not [
        r
        for r in world.committed["ledger"]
        if r["container_id"] == 8 and r["scope"] == "member"
    ]


@pytest.mark.asyncio
async def test_a_commit_failure_is_unknown_and_later_hubs_are_not_attempted(tmp_path):
    world, _, path = _week_world(tmp_path)
    world.commit_error_on = 7
    doc, code = await operator.run_members(
        member_apply(path, {7: 2, 8: 2}), world.factory
    )
    assert code == 1 and doc["status"] == "partial"
    assert doc["commit_unknown_hubs"] == [7] and doc["committed_hubs"] == []
    week4, week5 = doc["hubs"]
    assert week4["status"] == "commit_outcome_unknown" and week4["committed"] is None
    assert "never retry blind" in week4["next_step"]
    assert week5["status"] == "not_attempted"
    backup = _write(tmp_path, "unknown.json", doc)
    with pytest.raises(operator.OperatorRefused, match="unknown commit outcome"):
        operator.load_member_plan(member_apply(backup, {7: 6}, operator.MEMBER_RESTORE))


@pytest.mark.asyncio
async def test_receipt_files_are_exclusive_and_a_write_failure_keeps_the_commit(
    tmp_path,
):
    world, _, path = _week_world(tmp_path)
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    doc, code = await operator.run_members(
        member_apply(path, {7: 2, 8: 2}, receipt_dir=str(receipts)), world.factory
    )
    assert code == 0 and len(list(receipts.iterdir())) == 2
    saved = json.loads(open(doc["hubs"][0]["receipt_file"]).read())
    assert saved["committed"] is True and saved["targets"]

    second = tmp_path / "second"
    second.mkdir()
    world2, _, path2 = _week_world(second)
    doc, code = await operator.run_members(
        member_apply(path2, {7: 2, 8: 2}, receipt_dir=str(tmp_path / "missing")),
        world2.factory,
    )
    assert code == 0 and doc["status"] == "applied"
    assert all(h["receipt_file_error"] == "FileNotFoundError" for h in doc["hubs"])
    assert world2.committed["containers"][7]["revision"] == 6


async def _applied_backup(tmp_path):
    world, _, path = _week_world(tmp_path)
    doc, code = await operator.run_members(
        member_apply(path, {7: 2, 8: 2}), world.factory
    )
    assert code == 0
    return world, doc, _write(tmp_path, "BACKUP.json", doc)


def restore_options(backup, **changes):
    return operator.Options(
        operation=operator.MEMBER_RESTORE,
        restore_from_ledger=True,
        backup=backup,
        **changes,
    )


@pytest.mark.asyncio
async def test_exact_restore_readmits_and_reinserts_the_backed_up_rows(tmp_path):
    world, withdrawn, backup = await _applied_backup(tmp_path)
    original = {
        t["edge_id"]: t["preimage"] for h in withdrawn["hubs"] for t in h["targets"]
    }
    preview, code = await operator.run_members(restore_options(backup), world.factory)
    assert code == 0 and [h["would_be_revision"] for h in preview["hubs"]] == [10, 8]
    assert not set(original) & set(world.committed["edges"])

    doc, code = await operator.run_members(
        member_apply(backup, {7: 6, 8: 5}, operator.MEMBER_RESTORE), world.factory
    )
    assert code == 0 and doc["status"] == "applied", doc
    for edge_id, row in original.items():
        assert world.committed["edges"][edge_id] == row
    week4 = doc["hubs"][0]
    assert week4["receipt_kind"] == "restore_apply"
    assert (week4["pre_revision"], week4["post_revision"]) == (6, 10)
    assert week4["games"] == {"before": 2, "after": 2}
    readmits = [r for r in world.committed["ledger"] if r["action"] == "readmit"]
    assert len(readmits) == 7
    assert {json.loads(r["evidence"])["restore_from_ledger"] for r in readmits} == {
        t["ledger_id"] for h in withdrawn["hubs"] for t in h["targets"]
    }


@pytest.mark.parametrize(
    "drift,match",
    [
        ("revision", "revision 7, not 6"),
        ("intervening", "intervening correction"),
        ("edge_back", "already exists"),
        ("identity", "external_id"),
        ("ledger_preimage", "preimage differs"),
        ("schema", "columns changed"),
        ("receipt", "match receipt"),
    ],
)
@pytest.mark.asyncio
async def test_restore_refuses_any_drift_before_a_write(tmp_path, drift, match):
    world, withdrawn, backup = await _applied_backup(tmp_path)
    week4 = withdrawn["hubs"][0]
    target = week4["targets"][0]
    s = world.state
    if drift == "revision":
        s["containers"][7]["revision"] = 7
    elif drift == "intervening":
        s["ledger"].append(
            {
                "id": 99,
                "container_id": 7,
                "scope": "member",
                "action": "readmit",
                "child_type": "market",
                "child_id": target["market_id"],
                "revision": 6,
                "evidence": None,
            }
        )
    elif drift == "edge_back":
        s["edges"][target["edge_id"]] = dict(target["preimage"])
    elif drift == "identity":
        s["markets"][target["market_id"]]["external_id"] = "X-other"
    elif drift == "ledger_preimage":
        row = next(r for r in s["ledger"] if r["id"] == target["ledger_id"])
        evidence = json.loads(row["evidence"])
        evidence["preimage"]["confidence"] = "0.500"
        row["evidence"] = json.dumps(evidence)
    elif drift == "schema":
        world.columns["note"] = "text"
    elif drift == "receipt":
        doc = json.loads(open(backup).read())
        hub = doc["hubs"][0]
        hub["targets"][0]["preimage"]["receipt_id"] = "777"
        hub["backup_sha256"] = operator.preimage_fingerprint(
            [t["preimage"] for t in hub["targets"]]
        )
        backup = _write(tmp_path, "receipt.json", doc)
        for row in s["ledger"]:
            if row["id"] == target["ledger_id"]:
                ev = json.loads(row["evidence"])
                ev["preimage"]["receipt_id"] = "777"
                ev["backup_sha256"] = hub["backup_sha256"]
                row["evidence"] = json.dumps(ev)
    world.seal()
    world.statements.clear()
    doc, code = await operator.run_members(
        member_apply(backup, {7: 6, 8: 5}, operator.MEMBER_RESTORE), world.factory
    )
    assert code == 1 and doc["committed_hubs"] == [], doc
    refused = doc["hubs"][0]
    assert refused["status"] == "refused"
    assert match in refused["error"] + " ".join(refused["errors"])
    assert _no_writes(world)


@pytest.mark.parametrize(
    "tamper,match",
    [
        (
            lambda h: h["targets"][0]["preimage"].update(confidence="0.1"),
            "backup_sha256",
        ),
        (lambda h: h.update(post_revision=7), "compose"),
        (lambda h: h["targets"].append(copy.deepcopy(h["targets"][0])), "duplicated"),
        (lambda h: h.update(receipt_kind="restore_apply"), "only a committed withdraw"),
        (lambda h: h.update(operation="publish"), "withdraw-members receipt"),
    ],
)
@pytest.mark.asyncio
async def test_a_tampered_backup_refuses_before_a_database(tmp_path, tamper, match):
    _, withdrawn, _ = await _applied_backup(tmp_path)
    tamper(withdrawn["hubs"][0])
    backup = _write(tmp_path, "tampered.json", withdrawn)
    with pytest.raises(operator.OperatorRefused, match=match):
        operator.load_member_plan(restore_options(backup))


@pytest.mark.asyncio
async def test_restore_skips_hubs_that_never_committed_and_needs_their_post_revision(
    tmp_path, monkeypatch
):
    world, _, path = _week_world(tmp_path)
    real = cc.withdraw_member

    async def refuse_week5(session, **kwargs):
        if kwargs["container_id"] == 8:
            raise cc.CorrectionRefused("stop")
        return await real(session, **kwargs)

    monkeypatch.setattr(cc, "withdraw_member", refuse_week5)
    doc, _ = await operator.run_members(member_apply(path, {7: 2, 8: 2}), world.factory)
    backup = _write(tmp_path, "partial.json", doc)
    plan = operator.load_member_plan(restore_options(backup))
    assert [h.container_id for h in plan.hubs] == [7]
    with pytest.raises(operator.OperatorRefused, match="verified precondition 6"):
        operator.load_member_plan(member_apply(backup, {7: 2}, operator.MEMBER_RESTORE))


def test_member_cli_refuses_a_bad_manifest_before_any_database(
    tmp_path, monkeypatch, capsys
):
    async def forbidden(*args):
        pytest.fail("a bad manifest reached the database")

    monkeypatch.setattr(operator, "_run_configured", forbidden)
    code = operator.main(
        ["--operation", "withdraw-members", "--manifest", str(tmp_path / "absent.json")]
    )
    receipt = json.loads(capsys.readouterr().out)
    assert (
        code == 2 and receipt["status"] == "refused" and receipt["committed"] is False
    )


def test_member_apply_refuses_outside_the_named_app(tmp_path, monkeypatch, capsys):
    _, _, path = _week_world(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "configured-but-must-not-connect")
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    code = operator.main(
        [
            "--operation",
            "withdraw-members",
            "--manifest",
            str(path),
            "--apply",
            "--hub-revision",
            "7:2",
            "--hub-revision",
            "8:2",
            "--actor",
            "authority",
            "--reason",
            "r",
            "--evidence",
            '{"review":"x"}',
        ]
    )
    receipt = json.loads(capsys.readouterr().out)
    assert code == 2 and "bainluck-heavy" in receipt["error"]


def test_member_cli_preview_prints_the_run_document(tmp_path, monkeypatch, capsys):
    world, _, path = _week_world(tmp_path)

    async def configured(options, plan=None):
        return await operator.run_members(options, world.factory, plan)

    monkeypatch.setattr(operator, "_run_configured", configured)
    assert (
        operator.main(["--operation", "withdraw-members", "--manifest", str(path)]) == 0
    )
    doc = json.loads(capsys.readouterr().out)
    assert doc["status"] == "preview" and len(doc["hubs"]) == 2
