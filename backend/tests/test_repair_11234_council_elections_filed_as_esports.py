"""#11234 — the guards the two-row category correction has to hold, with no server.

1. **The cohort is the before-image, verbatim** — two ids, their identity copied by
   hand from the Measurement read; nothing added by a scan.
2. **The evidence is the running source** — the fixed name rules answer politics
   for both names; a release whose ticker accessor still answers esports (no
   #11237) makes both rows ``evidence`` and the apply inadmissible.
3. **Every pinned id reports exactly one verdict** — write / already / missing /
   foreign / drifted / evidence; only write and already admit the apply.
4. **The group guard** — every row of both groups is read; a sibling holding
   esports blocks; other siblings are reported, hashed, never written.
5. **Both or neither** — a second-row CAS that matches zero rows (drift, a
   same-value write moving the version, an identity change) rolls the first back;
   an unexpected row count or a moved ``updated_at`` refuses before commit.
6. **The undo is the inverse CAS on the version the apply wrote** — a later write,
   even of the same value, refuses it; without a hash it only plans.
7. **A COMMIT that does not return is UNKNOWN** (exit 3), driven through the
   PRODUCTION ``get_task_session`` with an inert engine: one COMMIT, no rollback
   claim, no retry, no restore; the report carries the returned versions.

These rows are civic elections. Nothing here asserts they are a sport.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import sys
from datetime import datetime, timezone

import pytest

from app.utils.futures_categorization import categorize_by_rules

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts"
    / "repair_11234_council_elections_filed_as_esports.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("repair_11234", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def repair():
    return _load()


UPDATED_AT = datetime(2026, 10, 12, 15, 40, 6, 465726, tzinfo=timezone.utc)

# Copied by hand from artifacts/calibration-esports-election-20261018/BEFORE-IMAGE/
# RESULT.json (observed 2026-10-18 19:48:36Z), so editing the script's pins cannot
# also edit their reference.
BEFORE_IMAGE = {
    65521811: {
        "source": "kalshi",
        "external_id": "KXVALLADOLIDCOUNCIL-27MAY23",
        "group_id": "kalshi:KXVALLADOLIDCOUNCIL-27MAY23",
        "name": "Valladolid municipal election winner?",
        "llm_sport_category": "esports",
        "status": "open",
        "updated_at": UPDATED_AT,
        "row_version": "54301846",
    },
    65521812: {
        "source": "kalshi",
        "external_id": "KXVALENCIACOUNCIL-27MAY23",
        "group_id": "kalshi:KXVALENCIACOUNCIL-27MAY23",
        "name": "Valencia municipal election winner?",
        "llm_sport_category": "esports",
        "status": "open",
        "updated_at": UPDATED_AT,
        "row_version": "54301846",
    },
}

IDS = sorted(BEFORE_IMAGE)


def fixed_accessor(ticker: str):
    """#11237's answer for the two series: no sport."""
    return None


def unfixed_accessor(ticker: str):
    """Today's deployed answer (``cc78241e``): the ``kxval`` stem claims both."""
    return "esports"


def _rows(**overrides) -> dict[int, dict]:
    rows = {i: dict(r) for i, r in BEFORE_IMAGE.items()}
    for market_id, fields in overrides.items():
        rows[int(market_id.lstrip("_"))].update(fields)
    return rows


def _group_rows(rows: dict[int, dict], siblings=()) -> list[dict]:
    out = [
        {
            "id": i,
            "group_id": r["group_id"],
            "llm_sport_category": r["llm_sport_category"],
        }
        for i, r in rows.items()
    ]
    return out + [dict(s) for s in siblings]


def _plan(repair, rows=None, siblings=(), accessor=fixed_accessor, written=None):
    rows = _rows() if rows is None else rows
    return repair.plan(
        rows,
        _group_rows(rows, siblings),
        categorize_by_rules,
        accessor,
        written=written,
    )


def _verdicts(out) -> dict[int, str]:
    return {a["id"]: a["verdict"] for a in out["accounting"]}


# ── 1. the cohort ────────────────────────────────────────────────────────────


def test_the_cohort_is_the_two_before_image_ids(repair):
    assert sorted(repair.PINNED) == IDS
    for market_id, pin in repair.PINNED.items():
        ref = BEFORE_IMAGE[market_id]
        assert (pin.source, pin.external_id, pin.group_id, pin.name) == (
            ref["source"],
            ref["external_id"],
            ref["group_id"],
            ref["name"],
        )
    assert repair.GROUPS == tuple(sorted(r["group_id"] for r in BEFORE_IMAGE.values()))
    assert (repair.BEFORE, repair.AFTER) == ("esports", "politics")
    assert repair.BEFORE_IMAGE_VERSION == "54301846"


def test_the_2169_cohort_and_its_no_op_are_not_in_scope(repair):
    assert not {38277227, 35418786, 59165075} & set(repair.PINNED)


# ── 2. the evidence is the running source ────────────────────────────────────


@pytest.mark.parametrize("market_id", IDS)
def test_the_name_rules_answer_politics_for_both_names(market_id):
    assert categorize_by_rules(BEFORE_IMAGE[market_id]["name"]) == "politics"


def test_the_fixed_release_admits_both_writes(repair):
    out = _plan(repair)
    assert _verdicts(out) == {i: "write" for i in IDS}
    assert out["admissible"] and out["refusal_reasons"] == []
    assert [(w["id"], w["from"], w["to"], w["version"]) for w in out["write"]] == [
        (i, "esports", "politics", "54301846") for i in IDS
    ]
    assert all(a["version_matches_before_image"] for a in out["accounting"])


def test_a_release_without_the_forward_fix_is_not_admissible(repair):
    out = _plan(repair, accessor=unfixed_accessor)
    assert _verdicts(out) == {i: "evidence" for i in IDS}
    assert out["write"] == [] and not out["admissible"]
    assert all("#11237" in a["why"] for a in out["accounting"])


def test_the_main_entry_wires_the_real_rules_and_accessor(repair):
    src = SCRIPT.read_text()
    assert "from app.utils.futures_categorization import categorize_by_rules" in src
    assert "from app.utils.sport_keys import get_sport_key_from_ticker" in src


# ── 3. per-row accounting ────────────────────────────────────────────────────


def test_an_already_correct_row_is_accounted_and_the_other_still_writes(repair):
    out = _plan(repair, _rows(_65521811={"llm_sport_category": "politics"}))
    assert _verdicts(out) == {65521811: "already", 65521812: "write"}
    assert out["admissible"] and [w["id"] for w in out["write"]] == [65521812]


def test_a_missing_row_blocks_without_a_substitute(repair):
    rows = _rows()
    del rows[65521812]
    out = _plan(repair, rows)
    assert _verdicts(out) == {65521811: "write", 65521812: "missing"}
    assert not out["admissible"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "polymarket"),
        ("external_id", "KXVALORANT-26WIN"),
        ("group_id", "kalshi:KXVALORANT-26WIN"),
        ("name", "Valorant Champions 2026 winner?"),
    ],
)
def test_a_foreign_row_under_a_pinned_id_blocks(repair, field, value):
    out = _plan(repair, _rows(_65521811={field: value}))
    assert _verdicts(out)[65521811] == "foreign"
    assert field in dict((a["id"], a["why"]) for a in out["accounting"])[65521811]
    assert not out["admissible"]


@pytest.mark.parametrize("category", ["other", None, "soccer"])
def test_a_drifted_category_blocks(repair, category):
    out = _plan(repair, _rows(_65521812={"llm_sport_category": category}))
    assert _verdicts(out)[65521812] == "drifted" and not out["admissible"]


def test_a_moved_version_is_reported_and_bound_into_the_hash(repair):
    moved = _plan(repair, _rows(_65521811={"row_version": "60000001"}))
    assert _verdicts(moved)[65521811] == "write"
    flags = {a["id"]: a["version_matches_before_image"] for a in moved["accounting"]}
    assert flags == {65521811: False, 65521812: True}
    assert moved["plan_hash"] != _plan(repair)["plan_hash"]


def test_every_pinned_id_reports_exactly_once(repair):
    out = _plan(repair, _rows(_65521811={"llm_sport_category": "politics"}))
    assert sorted(a["id"] for a in out["accounting"]) == IDS


# ── 4. the group guard ───────────────────────────────────────────────────────


def test_an_esports_sibling_is_a_residual_that_blocks(repair):
    sib = {
        "id": 70000001,
        "group_id": BEFORE_IMAGE[65521811]["group_id"],
        "llm_sport_category": "esports",
    }
    out = _plan(repair, siblings=[sib])
    assert out["group_residual"] == [70000001] and not out["admissible"]
    assert 70000001 not in {w["id"] for w in out["write"]}


def test_a_non_esports_sibling_is_reported_hashed_and_never_written(repair):
    sib = {
        "id": 70000002,
        "group_id": BEFORE_IMAGE[65521812]["group_id"],
        "llm_sport_category": "politics",
    }
    out = _plan(repair, siblings=[sib])
    assert out["admissible"] and out["siblings"] == [(70000002, "politics")]
    assert out["plan_hash"] != _plan(repair)["plan_hash"]
    assert {w["id"] for w in out["write"]} == set(IDS)


def test_a_group_read_at_its_cap_is_not_a_whole_group_read(repair):
    group = BEFORE_IMAGE[65521811]["group_id"]
    sibs = [
        {"id": 80000000 + n, "group_id": group, "llm_sport_category": "politics"}
        for n in range(repair.GROUP_READ_CAP - 2)
    ]
    out = _plan(repair, siblings=sibs)
    assert not out["admissible"] and "cap" in " ".join(out["refusal_reasons"])


def test_the_group_read_is_bounded_and_names_only_the_two_groups(repair):
    sql = " ".join(repair._READ_GROUPS_SQL.split())
    assert "WHERE group_id = ANY(:groups)" in sql and sql.endswith("LIMIT :cap")
    assert "LIKE" not in sql.upper()


# ── the write statement ──────────────────────────────────────────────────────


def test_the_write_moves_the_category_alone_under_a_full_compare(repair):
    sql = " ".join(repair._CAS_SQL.split())
    assert sql.split(" WHERE ")[0] == (
        "UPDATE futures_markets SET llm_sport_category = :target"
    )
    for clause in (
        "id = :id",
        "llm_sport_category = :source",
        "xmin::text = :version",
        "source = :src",
        "external_id = :ext",
        "group_id = :grp",
        "name IS NOT DISTINCT FROM :name",
    ):
        assert clause in sql
    assert sql.endswith("RETURNING xmin::text AS row_version, updated_at")
    set_clause = sql.split(" WHERE ")[0]
    for column in (
        "updated_at",
        "canonical_market_key",
        "category_tags",
        "llm_league",
        "status",
    ):
        assert column not in set_clause


# ── the transactional fake ───────────────────────────────────────────────────


class _Rec:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self._mapping = kw


class _Result:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    """A table with real transaction semantics: writes sit in ``txn`` until COMMIT
    and vanish on ROLLBACK. The UPDATE honours only the predicates its SQL TEXT
    states, so a clause dropped from ``_CAS_SQL`` is a clause this fake stops
    enforcing. Any write moves ``row_version`` (as ``xmin`` does)."""

    TXID = "99000001"

    def __init__(
        self, rows=None, siblings=(), extra_returning=0, bump_updated_at=False
    ):
        self.durable = {i: dict(r) for i, r in (rows or _rows()).items()}
        self.siblings = [dict(s) for s in siblings]
        self.txn: dict[int, dict] = {}
        self.extra_returning = extra_returning
        self.bump_updated_at = bump_updated_at
        self.calls: list[str] = []
        self.updates: list[dict] = []
        self.commits = 0
        self.committed = False
        self.rolled_back = False
        self.reads = 0

    def view(self, market_id):
        return self.txn.get(market_id, self.durable.get(market_id))

    async def execute(self, stmt, params):
        sql = " ".join(str(stmt).split())
        self.calls.append("execute")
        if sql.startswith("SELECT") and "group_id = ANY" in sql:
            got = [
                {
                    "id": i,
                    "group_id": self.view(i)["group_id"],
                    "llm_sport_category": self.view(i)["llm_sport_category"],
                }
                for i in sorted(self.durable)
                if self.view(i)["group_id"] in params["groups"]
            ] + [s for s in self.siblings if s["group_id"] in params["groups"]]
            self.reads += 1
            self.after_read()
            return _Result(_Rec(**r) for r in got[: params["cap"]])
        if sql.startswith("SELECT"):
            got = [dict(self.view(i), id=i) for i in params["ids"] if i in self.durable]
            return _Result(_Rec(**r) for r in got)
        assert sql.startswith("UPDATE")
        self.updates.append(dict(params))
        self.before_update(len(self.updates))
        row = self.view(params["id"])
        if row is None:
            return _Result()
        checks = {
            "llm_sport_category = :source": row["llm_sport_category"]
            == params["source"],
            "xmin::text = :version": row["row_version"] == params["version"],
            "source = :src": row["source"] == params["src"],
            "external_id = :ext": row["external_id"] == params["ext"],
            "group_id = :grp": row["group_id"] == params["grp"],
            "name IS NOT DISTINCT FROM :name": row["name"] == params["name"],
        }
        if not all(ok for clause, ok in checks.items() if clause in sql):
            return _Result()
        new = dict(row, llm_sport_category=params["target"], row_version=self.TXID)
        if self.bump_updated_at:
            new["updated_at"] = datetime(2026, 10, 19, tzinfo=timezone.utc)
        self.txn[params["id"]] = new
        ret = _Rec(row_version=new["row_version"], updated_at=new["updated_at"])
        return _Result([ret] * (1 + self.extra_returning))

    def after_read(self):
        """A concurrent writer between the run's read and its first UPDATE."""

    def before_update(self, n):
        """A concurrent writer landing just before the n-th UPDATE."""

    def concurrent_write(self, market_id, **fields):
        row = dict(self.durable[market_id], **fields)
        row["row_version"] = "88000001"
        self.durable[market_id] = row

    async def commit(self):
        self.calls.append("commit")
        self.commits += 1
        self.committed = True
        self.durable.update(self.txn)
        self.txn = {}

    async def rollback(self):
        self.calls.append("rollback")
        self.rolled_back = True
        self.txn = {}

    async def close(self):
        self.calls.append("close")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _run(repair, session, accessor=fixed_accessor, **kw):
    return asyncio.run(repair.run(session, categorize_by_rules, accessor, **kw))


def _hash(repair, **kw):
    return _run(repair, FakeSession(**kw), execute=False)["plan_hash"]


def _categories(session) -> dict[int, str]:
    return {i: r["llm_sport_category"] for i, r in session.durable.items()}


def _apply_through_rollback(repair, session, h):
    """What ``main`` does on a refusal: the run raises, the transaction rolls back."""
    with pytest.raises(repair.Refused) as caught:
        _run(repair, session, execute=True, expect_plan_hash=h)
    asyncio.run(session.rollback())
    return caught.value


# ── 5. both or neither ───────────────────────────────────────────────────────


def test_the_dry_run_writes_nothing(repair):
    s = FakeSession()
    out = _run(repair, s, execute=False)
    assert s.updates == [] and not s.committed
    assert out["mode"] == "apply-plan" and out["written"] == 0


def test_the_reviewed_apply_writes_both_and_returns_their_versions(repair):
    h = _hash(repair)
    s = FakeSession()
    out = _run(repair, s, execute=True, expect_plan_hash=h)
    assert out["written"] == 2 and s.commits == 1
    assert _categories(s) == {i: "politics" for i in IDS}
    assert out["written_versions"] == {i: FakeSession.TXID for i in IDS}
    for i in IDS:
        assert s.durable[i]["updated_at"] == UPDATED_AT
        for col in ("source", "external_id", "group_id", "name", "status"):
            assert s.durable[i][col] == BEFORE_IMAGE[i][col]


def test_a_wrong_hash_writes_nothing(repair):
    s = FakeSession()
    with pytest.raises(repair.Refused):
        _run(repair, s, execute=True, expect_plan_hash="0" * 16)
    assert s.updates == [] and not s.committed


def test_the_right_hash_on_an_inadmissible_plan_still_refuses(repair):
    rows = _rows()
    del rows[65521812]
    h = _hash(repair, rows=rows)
    s = FakeSession(rows=rows)
    with pytest.raises(repair.Refused, match="blocking"):
        _run(repair, s, execute=True, expect_plan_hash=h)
    assert s.updates == []


def test_a_release_without_the_fix_cannot_apply_even_with_its_own_hash(repair):
    s = FakeSession()
    h = _run(repair, FakeSession(), unfixed_accessor, execute=False)["plan_hash"]
    with pytest.raises(repair.Refused):
        _run(repair, s, unfixed_accessor, execute=True, expect_plan_hash=h)
    assert s.updates == []


class SecondRowDrifts(FakeSession):
    """The second row's category moves just before its UPDATE: the first UPDATE
    has already landed in the transaction."""

    def before_update(self, n):
        if n == 2:
            self.concurrent_write(65521812, llm_sport_category="other")


class SecondRowSameValueWrite(FakeSession):
    """A writer re-writes the second row with the SAME values: only xmin moves."""

    def before_update(self, n):
        if n == 2:
            self.concurrent_write(65521812)


class SecondRowRenamed(FakeSession):
    def before_update(self, n):
        if n == 2:
            self.concurrent_write(65521812, name="Valorant Masters Valencia winner?")


@pytest.mark.parametrize(
    "cls", [SecondRowDrifts, SecondRowSameValueWrite, SecondRowRenamed]
)
def test_a_second_row_that_moved_rolls_the_first_back(repair, cls):
    h = _hash(repair)
    s = cls()
    err = _apply_through_rollback(repair, s, h)
    assert "65521812" in str(err)
    assert len(s.updates) == 2 and not s.committed
    assert s.durable[65521811]["llm_sport_category"] == "esports"
    assert s.durable[65521811]["row_version"] == "54301846"


def test_the_same_value_write_is_caught_by_the_version_half_alone(repair):
    # Control for the arm above: with the version clause stripped from the SQL the
    # fake stops enforcing it and the same-value write goes unseen.
    h = _hash(repair)
    s = SecondRowSameValueWrite()
    original = repair._CAS_SQL
    try:
        repair._CAS_SQL = original.replace("AND xmin::text = :version ", "")
        out = _run(repair, s, execute=True, expect_plan_hash=h)
    finally:
        repair._CAS_SQL = original
    assert out["written"] == 2  # the defect the version clause exists to stop


class ChangedAfterRead(FakeSession):
    def after_read(self):
        if self.reads == 1:
            self.concurrent_write(65521811)


def test_a_write_between_the_read_and_the_update_refuses(repair):
    h = _hash(repair)
    s = ChangedAfterRead()
    _apply_through_rollback(repair, s, h)
    assert not s.committed and _categories(s) == {i: "esports" for i in IDS}


def test_an_unexpected_row_count_refuses_before_commit(repair):
    h = _hash(repair)
    s = FakeSession(extra_returning=1)
    err = _apply_through_rollback(repair, s, h)
    assert "changed 2" in str(err) and not s.committed
    assert _categories(s) == {i: "esports" for i in IDS}


def test_a_write_that_moved_updated_at_refuses_before_commit(repair):
    h = _hash(repair)
    s = FakeSession(bump_updated_at=True)
    err = _apply_through_rollback(repair, s, h)
    assert "updated_at" in str(err) and not s.committed


def test_an_already_correct_row_is_not_rewritten(repair):
    rows = _rows(
        _65521811={"llm_sport_category": "politics", "row_version": "61000000"}
    )
    h = _hash(repair, rows=rows)
    s = FakeSession(rows=rows)
    out = _run(repair, s, execute=True, expect_plan_hash=h)
    assert [u["id"] for u in s.updates] == [65521812] and out["written"] == 1
    assert s.durable[65521811]["row_version"] == "61000000"


def test_an_esports_sibling_stops_the_apply(repair):
    sib = {
        "id": 70000001,
        "group_id": BEFORE_IMAGE[65521811]["group_id"],
        "llm_sport_category": "esports",
    }
    h = _hash(repair, siblings=[sib])
    s = FakeSession(siblings=[sib])
    with pytest.raises(repair.Refused, match="group_residual"):
        _run(repair, s, execute=True, expect_plan_hash=h)
    assert s.updates == []


def test_a_sibling_appearing_after_the_dry_run_moves_the_hash(repair):
    h = _hash(repair)
    sib = {
        "id": 70000003,
        "group_id": BEFORE_IMAGE[65521812]["group_id"],
        "llm_sport_category": "politics",
    }
    s = FakeSession(siblings=[sib])
    with pytest.raises(repair.Refused, match="plan hash"):
        _run(repair, s, execute=True, expect_plan_hash=h)


# ── 6. the undo ──────────────────────────────────────────────────────────────


def _applied(repair):
    s = FakeSession()
    out = _run(repair, s, execute=True, expect_plan_hash=_hash(repair))
    return s, out["written_versions"]


def test_a_restore_without_a_hash_only_plans(repair):
    s, written = _applied(repair)
    s.updates.clear()
    out = _run(repair, s, execute=False, written=written)
    assert out["mode"] == "restore-plan" and s.updates == []
    assert {a["verdict"] for a in out["accounting"]} == {"write"}


def test_the_reviewed_restore_reverts_exactly_what_the_apply_wrote(repair):
    s, written = _applied(repair)
    plan_out = _run(repair, s, execute=False, written=written)
    out = _run(
        repair, s, execute=True, expect_plan_hash=plan_out["plan_hash"], written=written
    )
    assert out["mode"] == "restore" and out["written"] == 2
    assert _categories(s) == {i: "esports" for i in IDS}
    assert all(s.durable[i]["updated_at"] == UPDATED_AT for i in IDS)


def test_a_later_same_value_write_refuses_the_restore(repair):
    s, written = _applied(repair)
    s.concurrent_write(65521812)  # same values; only the version moves
    out = _run(repair, s, execute=False, written=written)
    assert _verdicts(out) == {65521811: "write", 65521812: "moved_since_apply"}
    with pytest.raises(repair.Refused, match="blocking"):
        _run(
            repair, s, execute=True, expect_plan_hash=out["plan_hash"], written=written
        )
    assert _categories(s) == {i: "politics" for i in IDS}


def test_an_apply_hash_cannot_drive_a_restore(repair):
    s, written = _applied(repair)
    with pytest.raises(repair.Refused, match="plan hash"):
        _run(repair, s, execute=True, expect_plan_hash=_hash(repair), written=written)


@pytest.mark.parametrize("raw", ["", " , ", "65521811", "65521811:abc", "38277227:1"])
def test_written_must_be_pinned_id_version_pairs(repair, raw):
    with pytest.raises(repair.Refused):
        repair.parse_written(raw)


def test_written_parses_the_printed_undo_line(repair):
    assert repair.parse_written("65521811:99000001,65521812:99000001") == {
        65521811: "99000001",
        65521812: "99000001",
    }


# ── refusals at the door ─────────────────────────────────────────────────────


@pytest.mark.parametrize("app", ["", "bainluck-staging", "local"])
def test_refuses_off_production(repair, app):
    with pytest.raises(repair.Refused):
        repair.refuse_unless_production({"HEROKU_APP_NAME": app})


@pytest.mark.parametrize(
    "argv",
    [
        ["--apply"],
        ["--restore"],
        ["--written", "65521811:1"],
        ["--expect-plan-hash", "abc"],
        ["--restore", "--written", "38277227:1"],
    ],
)
def test_main_refuses_unsafe_flag_shapes_before_any_session(
    repair, monkeypatch, argv, capsys
):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    monkeypatch.setattr(sys, "argv", ["repair_11234", *argv])
    assert asyncio.run(repair.main()) == 2
    assert capsys.readouterr().out.startswith("REFUSED:")


# ── 7. main() through the PRODUCTION get_task_session ────────────────────────


class _ConnectionFailure(Exception):
    sqlstate = "08006"


def _lost_ack():
    from sqlalchemy.exc import OperationalError

    return OperationalError("COMMIT", {}, _ConnectionFailure("connection lost"))


class LostCommitAck(FakeSession):
    """The COMMIT becomes durable on the server; its acknowledgement never arrives.
    A second COMMIT, if anything sent one, would answer — the repair must not."""

    async def commit(self):
        self.calls.append("commit")
        self.commits += 1
        if self.commits > 1:
            return
        self.durable.update(self.txn)
        self.txn = {}
        raise _lost_ack()


class _InertEngine:
    def __init__(self, calls):
        self._calls = calls

    async def dispose(self):
        self._calls.append("dispose")


def _main(repair, monkeypatch, session, argv, accessor=fixed_accessor):
    import app.tasks.base as base
    import app.utils.sport_keys as sport_keys

    assert base.get_task_session.__module__ == "app.tasks.base"
    engine = _InertEngine(session.calls)
    seen: dict = {}

    def engine_factory(**kwargs):
        seen.update(kwargs)
        return engine

    monkeypatch.setattr(base, "_get_task_engine", engine_factory)
    monkeypatch.setattr(
        base, "async_sessionmaker", lambda bound, **kw: (lambda: session)
    )
    monkeypatch.setattr(sport_keys, "get_sport_key_from_ticker", accessor)
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    monkeypatch.setattr(sys, "argv", ["repair_11234", *argv])
    code = asyncio.run(repair.main())
    assert seen == {
        "statement_timeout_ms": repair.STATEMENT_TIMEOUT_MS,
        "lock_timeout_ms": repair.LOCK_TIMEOUT_MS,
    }
    assert (
        0 < repair.LOCK_TIMEOUT_MS <= 10_000
        and 0 < repair.STATEMENT_TIMEOUT_MS <= 30_000
    )
    return code


def _json_tail(out: str) -> dict:
    return json.loads(out[out.index("{") : out.rindex("}") + 1])


def test_the_dry_run_through_main_commits_no_write(repair, monkeypatch, capsys):
    s = FakeSession()
    assert _main(repair, monkeypatch, s, []) == 0
    report = _json_tail(capsys.readouterr().out)
    assert report["mode"] == "apply-plan" and report["admissible"]
    assert s.updates == [] and _categories(s) == {i: "esports" for i in IDS}


def test_the_apply_through_main_prints_a_reviewable_undo(repair, monkeypatch, capsys):
    h = _hash(repair)
    s = FakeSession()
    assert _main(repair, monkeypatch, s, ["--apply", "--expect-plan-hash", h]) == 0
    out = capsys.readouterr().out
    assert "--restore --written 65521811:99000001,65521812:99000001" in out
    assert _categories(s) == {i: "politics" for i in IDS}


def test_a_refusal_through_main_rolls_back_and_says_so(repair, monkeypatch, capsys):
    h = _hash(repair)
    s = SecondRowSameValueWrite()
    assert _main(repair, monkeypatch, s, ["--apply", "--expect-plan-hash", h]) == 2
    out = capsys.readouterr().out
    assert out.startswith("REFUSED:") and "nothing committed" in out
    assert "commit" not in s.calls[: s.calls.index("rollback")]
    assert s.durable[65521811]["llm_sport_category"] == "esports"


def test_a_lost_commit_ack_is_unknown_and_never_followed(repair, monkeypatch, capsys):
    h = _hash(repair)
    s = LostCommitAck()
    code = _main(repair, monkeypatch, s, ["--apply", "--expect-plan-hash", h])
    captured = capsys.readouterr()
    assert code == 3
    assert _categories(s) == {i: "politics" for i in IDS}  # it DID land
    assert "nothing committed" not in captured.out and "REFUSED" not in captured.out
    assert "UNDO" not in captured.out and "Traceback" not in captured.err
    report = _json_tail(captured.out)
    assert report["outcome"] == "UNKNOWN" and report["mode"] == "apply"
    assert report["plan_hash"] == h and report["statements_changed"] == 2
    assert report["returned_versions"] == {str(i): FakeSession.TXID for i in IDS}
    assert "08006" in report["unknown"]
    assert report["readback"].endswith(
        "python3 scripts/repair_11234_council_elections_filed_as_esports.py"
    )
    # One COMMIT, then only the wrapper's exception-path cleanup: no second
    # COMMIT, no retry, no restore write.
    assert s.commits == 1
    assert s.calls[s.calls.index("commit") + 1 :] == ["rollback", "close", "dispose"]
    assert len(s.updates) == 2


def test_a_lost_commit_ack_on_restore_is_unknown_too(repair, monkeypatch, capsys):
    s, written = _applied(repair)
    pairs = ",".join(f"{i}:{v}" for i, v in sorted(written.items()))
    h = _run(repair, s, execute=False, written=written)["plan_hash"]
    lost = LostCommitAck(rows=s.durable)
    code = _main(
        repair,
        monkeypatch,
        lost,
        ["--restore", "--written", pairs, "--expect-plan-hash", h],
    )
    report = _json_tail(capsys.readouterr().out)
    assert code == 3 and report["mode"] == "restore" and lost.commits == 1
