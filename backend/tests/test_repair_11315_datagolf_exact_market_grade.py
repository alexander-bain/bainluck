"""#11315 — the guards the exact-market DataGolf grade has to hold, with no server.

EVIDENCE CLASSES, NAMED EVERY TIME THEY ARE USED
------------------------------------------------

* **RETAINED** — ``fixtures/datagolf_baycurrent_64266833_retained_11315.json``:
  values copied verbatim from the one immutable capture (``golfJourney.json``,
  sha256 ``1bdd575d…``). The 72-row stored board, the 155 outcome ids/names with
  their null grades, and two charted lines. Nothing in it was re-derived.
* **CONSTRUCTED** — everything the capture does not hold: outcome external ids,
  row versions, ``settled_at``, the metadata event id/tour. The board players'
  ``dg_<id>`` are joined BY NAME here only to build a world; the script itself
  never joins by name, and that the real outcome 241857512 carries ``dg_29197``
  remains unadmitted until the reviewed dry run reads it.

What is guarded:

1. **The specimen** — the pins are the retained market and winner.
2. **One winner, board losers, absent players untouched** — 72 writes; the 83
   outcomes not on a 72-row board are ``unknown_absent`` and never become losses.
3. **Every admission clause refuses by name** — identity, edition, finality, a
   tied or mismatched leader, the winner join, duplicates, a capped read, a
   conflicting stored grade or winner.
4. **The binding** — the hash moves with any row version, the board, or a grade;
   a wrong hash writes nothing; drift before the n-th UPDATE rolls back all.
4b. **The roster** (CERT-4252) — a row the plan never writes that is crowned,
   cleared, removed, or a row that joins, refuses the whole apply; an apply
   without the outcome→market foreign key refuses. That the LOCKS keep such a
   writer out is proved on real Postgres in
   ``tests/integration/test_repair_11315_roster_lock_pg.py``, not here.
5. **The undo** — the inverse CAS at the written version only.
6. **A COMMIT that does not return is UNKNOWN** — no rollback claim, no retry.
7. **Not the #1152 rails** — the broad grader and its endpoint are never called.
8. **The history half is NOT paid by this grade** — on the retained Brennan line,
   a constructed 1.0 grade leaves the 22:08:55Z reset in place.
"""

from __future__ import annotations

import ast
import asyncio
import copy
import importlib
import importlib.util
import json
import pathlib
from datetime import datetime, timezone

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repair_11315_datagolf_exact_market_grade.py"
FIXTURE = ROOT / "tests" / "fixtures" / "datagolf_baycurrent_64266833_retained_11315.json"

# Copied by hand from the measurement artifact (source-manifest / DIAGNOSIS.md) so an
# edit to the fixture's provenance cannot also edit its reference.
CAPTURE_SHA256 = "1bdd575deb988730374dc7e52225bad45b6312671b2eab73a184dd5fa0330fa1"

# `from app.tasks import backfill_winners` yields the registered Celery TASK.
bw = importlib.import_module("app.tasks.backfill_winners")
PLACEMENT = bw._datagolf_check_placement


def _load():
    spec = importlib.util.spec_from_file_location("repair_11315", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def repair():
    return _load()


@pytest.fixture(scope="module")
def retained():
    return json.loads(FIXTURE.read_text())


BRENNAN = 241857512
LAST_UPDATED = datetime(2026, 10, 11, 22, 8, 55, 891004, tzinfo=timezone.utc)


# ── the world: RETAINED board/outcomes + CONSTRUCTED identity/versions ──────────


def _market(retained, **overrides) -> dict:
    """RETAINED: id, source, external id, status, resolution date, the board.
    CONSTRUCTED: metadata event id/tour, settled_at, row version."""
    m = retained["market"]
    row = {
        "id": m["id"],
        "source": m["source"],
        "external_id": m["external_id"],
        "status": m["status"],
        "resolution_date": datetime.fromisoformat(m["resolution_date"]),
        "settled_at": datetime(2026, 10, 11, 6, 41, 26, tzinfo=timezone.utc),
        "market_metadata": {
            "datagolf_event_id": "527",
            "tour": "pga",
            "leaderboard": copy.deepcopy(retained["leaderboard"]),
            "leaderboard_updated_at": "2026-10-11T06:41:26+00:00",
        },
        "row_version": "70000001",
    }
    row.update(overrides)
    return row


def _outcomes(retained) -> list[dict]:
    """RETAINED: the 155 ids and their null grades. CONSTRUCTED: external ids (board
    players joined by name, the rest given ids no board row carries) and versions."""
    dg_by_name = {e["name"]: e["dg_id"] for e in retained["leaderboard"]}
    rows = []
    for i, o in enumerate(retained["outcomes"]):
        dg = dg_by_name.get(o["name"], 9_000_000 + i)
        rows.append(
            {
                "id": o["id"],
                "external_id": f"dg_{dg}",
                "is_winner": o["is_winner"],
                "resolution_source": o["resolution_source"],
                "last_updated": LAST_UPDATED,
                "row_version": str(60_000_000 + i),
            }
        )
    return rows


def _plan(repair, retained, market=None, outcomes=None):
    return repair.plan(
        market if market is not None else _market(retained),
        outcomes if outcomes is not None else _outcomes(retained),
        PLACEMENT,
    )


def _row(outcomes, oid):
    return next(o for o in outcomes if o["id"] == oid)


def _refused(out, prefix):
    return any(r.startswith(prefix) for r in out["refusal_reasons"])


# ── 1. the specimen ──────────────────────────────────────────────────────────


def test_the_fixture_is_the_retained_capture(retained):
    assert retained["provenance"]["source_sha256"] == CAPTURE_SHA256
    assert retained["market"]["id"] == 64266833
    assert retained["market"]["outcome_count"] == 155 == len(retained["outcomes"])
    assert len(retained["leaderboard"]) == 72
    assert all(o["is_winner"] is None and o["resolution_source"] is None for o in retained["outcomes"])
    top = [e for e in retained["leaderboard"] if e["position"] == "1"]
    assert top == [
        {
            "name": "Michael Brennan",
            "thru": "18",
            "dg_id": 29197,
            "position": "1",
            "today_score": -3,
            "total_score": -16,
            "current_round": 4,
        }
    ]


def test_the_pins_are_the_retained_specimen(repair, retained):
    m = retained["market"]
    assert (repair.MARKET.id, repair.MARKET.source, repair.MARKET.external_id) == (
        m["id"],
        m["source"],
        m["external_id"],
    )
    assert repair.MARKET.end_date == m["resolution_date"][:10] == "2026-10-11"
    assert repair.WINNER.outcome_id == BRENNAN
    assert _row(retained["outcomes"], BRENNAN)["name"] == repair.WINNER.name
    assert repair.WINNER.external_id == f"dg_{repair.WINNER.dg_id}" == "dg_29197"
    assert repair.OUTCOME_READ_CAP == len(retained["outcomes"]) + 1


# ── 2. the row this exists for, and the rows it must not touch ────────────────


def test_the_constructed_identity_admits_one_winner_and_the_board_losers(repair, retained):
    out = _plan(repair, retained)
    assert out["admissible"], out["refusal_reasons"]
    assert out["counts"] == {"unknown_absent": 83, "write": 72}
    winners = [w for w in out["write"] if w["to"][0] is True]
    assert [(w["id"], w["to"]) for w in winners] == [(BRENNAN, [True, "leaderboard"])]
    assert all(w["to"] == [False, "leaderboard"] for w in out["write"] if w["id"] != BRENNAN)
    assert all(w["from"] == [None, None] for w in out["write"])


def test_absent_players_are_never_graded_losers(repair, retained):
    """The #1152 grader would write 83 `did_not_play` losses off a 72-row board."""
    out = _plan(repair, retained)
    written = {w["id"] for w in out["write"]}
    absent = set(out["accounting"]["unknown_absent"])
    assert len(absent) == 83 and not (absent & written)
    assert all(w["to"][1] != "did_not_play" for w in out["write"])
    assert "did_not_play" not in SCRIPT.read_text().split('"""', 2)[2]


def test_a_withdrawn_board_entry_keeps_the_graders_own_label(repair, retained):
    m = _market(retained)
    entry = next(e for e in m["market_metadata"]["leaderboard"] if e["position"] != "1")
    entry["position"] = "WD"
    out = _plan(repair, retained, market=m)
    w = next(w for w in out["write"] if w["external_id"] == f"dg_{entry['dg_id']}")
    assert w["to"] == [False, "withdrew"]


def test_an_outcome_without_provider_identity_is_left_unknown(repair, retained):
    outcomes = _outcomes(retained)
    victim = next(o for o in outcomes if o["id"] != BRENNAN and o["external_id"] == "dg_29279")
    victim["external_id"] = None
    out = _plan(repair, retained, outcomes=outcomes)
    assert out["admissible"]
    assert victim["id"] in out["accounting"]["unknown_no_identity"]
    assert victim["id"] not in {w["id"] for w in out["write"]}


def test_an_already_correct_row_is_accounted_and_the_rest_still_write(repair, retained):
    outcomes = _outcomes(retained)
    b = _row(outcomes, BRENNAN)
    b["is_winner"], b["resolution_source"] = True, "leaderboard"
    out = _plan(repair, retained, outcomes=outcomes)
    assert out["admissible"]
    assert out["accounting"]["already"] == [BRENNAN]
    assert out["counts"]["write"] == 71


# ── 3. every admission clause refuses by name ─────────────────────────────────


def test_a_missing_market_refuses(repair, retained):
    out = repair.plan(None, [], PLACEMENT)
    assert not out["admissible"] and _refused(out, "missing")


@pytest.mark.parametrize(
    "field,value,prefix",
    [
        ("source", "kalshi", "foreign"),
        ("external_id", "datagolf:pga:527:top_5", "foreign"),
        ("status", "open", "status"),
        ("resolution_date", datetime(2025, 10, 12, tzinfo=timezone.utc), "edition"),
    ],
)
def test_a_market_that_is_not_the_pinned_edition_refuses(repair, retained, field, value, prefix):
    out = _plan(repair, retained, market=_market(retained, **{field: value}))
    assert not out["admissible"] and _refused(out, prefix)


@pytest.mark.parametrize("key,value", [("datagolf_event_id", "528"), ("tour", "euro")])
def test_metadata_naming_another_event_refuses(repair, retained, key, value):
    m = _market(retained)
    m["market_metadata"][key] = value
    out = _plan(repair, retained, market=m)
    assert not out["admissible"] and _refused(out, "edition")


def test_a_missing_board_refuses_and_grades_nothing(repair, retained):
    m = _market(retained)
    del m["market_metadata"]["leaderboard"]
    out = _plan(repair, retained, market=m)
    assert not out["admissible"] and _refused(out, "board_missing")
    assert out["write"] == []


@pytest.mark.parametrize(
    "mutate,prefix",
    [
        (lambda e: e.update(thru="17"), "board_not_final"),
        (lambda e: e.update(current_round=3), "board_not_final"),
        (lambda e: e.update(position="?"), "board_malformed"),
        (lambda e: e.update(dg_id=None), "board_malformed"),
    ],
)
def test_a_board_that_is_not_final_or_well_formed_refuses(repair, retained, mutate, prefix):
    m = _market(retained)
    mutate(next(e for e in m["market_metadata"]["leaderboard"] if e["position"] != "1"))
    out = _plan(repair, retained, market=m)
    assert not out["admissible"] and _refused(out, prefix)
    assert out["write"] == []


def test_a_cut_entry_is_exempt_from_the_final_round_clause(repair, retained):
    m = _market(retained)
    entry = next(e for e in m["market_metadata"]["leaderboard"] if e["position"] != "1")
    entry.update(position="CUT", current_round=2, thru="18")
    assert _plan(repair, retained, market=m)["admissible"]


def test_a_duplicate_board_identity_refuses(repair, retained):
    m = _market(retained)
    board = m["market_metadata"]["leaderboard"]
    board.append(dict(board[-1]))
    out = _plan(repair, retained, market=m)
    assert not out["admissible"] and _refused(out, "board_duplicate_dg_id")


@pytest.mark.parametrize("position", ["T1", "1"])
def test_a_shared_lead_refuses(repair, retained, position):
    m = _market(retained)
    next(e for e in m["market_metadata"]["leaderboard"] if e["position"] != "1")["position"] = position
    out = _plan(repair, retained, market=m)
    assert not out["admissible"] and _refused(out, "winner_not_unique")


def test_a_board_led_by_someone_else_refuses(repair, retained):
    m = _market(retained)
    board = m["market_metadata"]["leaderboard"]
    leader = next(e for e in board if e["position"] == "1")
    other = next(e for e in board if e["position"] != "1")
    leader["position"], other["position"] = other["position"], "1"
    out = _plan(repair, retained, market=m)
    assert not out["admissible"] and _refused(out, "winner_mismatch")


@pytest.mark.parametrize("ext", [None, "dg_99999", "Michael Brennan"])
def test_the_winner_join_is_identity_never_a_name(repair, retained, ext):
    """The unadmitted link: if the real row lacks `dg_29197`, nothing is written."""
    outcomes = _outcomes(retained)
    _row(outcomes, BRENNAN)["external_id"] = ext
    out = _plan(repair, retained, outcomes=outcomes)
    assert not out["admissible"] and _refused(out, "winner_identity")


def test_the_winner_outcome_missing_from_the_market_refuses(repair, retained):
    outcomes = [o for o in _outcomes(retained) if o["id"] != BRENNAN]
    out = _plan(repair, retained, outcomes=outcomes)
    assert not out["admissible"] and _refused(out, "winner_outcome_missing")


def test_a_duplicate_outcome_identity_refuses(repair, retained):
    outcomes = _outcomes(retained)
    outcomes[1]["external_id"] = outcomes[0]["external_id"]
    out = _plan(repair, retained, outcomes=outcomes)
    assert not out["admissible"] and _refused(out, "duplicate_outcome_identity")


def test_an_outcome_read_at_its_cap_is_not_a_whole_market_read(repair, retained):
    outcomes = _outcomes(retained)
    outcomes.append(dict(outcomes[-1], id=999_999_999, external_id="dg_8999999"))
    assert len(outcomes) == repair.OUTCOME_READ_CAP
    out = _plan(repair, retained, outcomes=outcomes)
    assert not out["admissible"] and _refused(out, "outcome read reached its cap")


def test_a_stored_grade_that_disagrees_with_the_board_blocks(repair, retained):
    outcomes = _outcomes(retained)
    loser = next(o for o in outcomes if o["external_id"] == "dg_29279")
    loser["is_winner"], loser["resolution_source"] = False, "did_not_play"
    out = _plan(repair, retained, outcomes=outcomes)
    assert not out["admissible"] and loser["id"] in out["accounting"]["conflict"]


def test_another_crowned_outcome_blocks_even_off_the_board(repair, retained):
    outcomes = _outcomes(retained)
    absent = next(o for o in outcomes if o["external_id"].startswith("dg_9"))
    absent["is_winner"], absent["resolution_source"] = True, "clean_resolution"
    out = _plan(repair, retained, outcomes=outcomes)
    assert not out["admissible"] and _refused(out, "conflicting_winner")


# ── 4. the binding and both-or-neither ───────────────────────────────────────


class _Rec:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self._mapping = kw


class FakeSession:
    """Tables with real transaction semantics: writes sit in ``txn`` until COMMIT and
    vanish on ROLLBACK. The UPDATE honours only the predicates its SQL TEXT states,
    so a clause dropped from ``_CAS_SQL`` is a clause this fake stops enforcing. Any
    write moves ``row_version`` (as ``xmin`` does)."""

    TXID = "99000001"

    def __init__(
        self,
        market,
        outcomes,
        extra_returning=0,
        bump_last_updated=False,
        commit_raises=None,
        outcome_fk=True,
    ):
        self.market = dict(market) if market is not None else None
        self.outcome_fk = outcome_fk
        self.durable = {o["id"]: dict(o, market_id=64266833) for o in outcomes}
        self.txn: dict[int, dict] = {}
        self.extra_returning = extra_returning
        self.bump_last_updated = bump_last_updated
        self.commit_raises = commit_raises
        self.sql: list[str] = []
        self.updates: list[dict] = []
        self.commits = 0
        self.rolled_back = False

    def view(self, oid):
        return self.txn.get(oid, self.durable.get(oid))

    async def execute(self, stmt, params):
        sql = " ".join(str(stmt).split())
        self.sql.append(sql)
        if sql.startswith("SELECT") and "FROM pg_constraint" in sql:
            return [_Rec(n=1 if self.outcome_fk else 0)]
        if sql.startswith("SELECT") and "FROM futures_markets" in sql:
            return [] if self.market is None else [_Rec(**self.market)]
        if sql.startswith("SELECT"):
            rows = [
                dict(self.view(i)) for i in sorted(self.durable)
                if self.view(i)["market_id"] == params["mid"]
            ][: params["cap"]]
            for r in rows:
                r.pop("market_id")
            return [_Rec(**r) for r in rows]
        assert sql.startswith("UPDATE futures_outcomes")
        self.updates.append(dict(params))
        self.before_update(len(self.updates))
        row = self.view(params["id"])
        if row is None:
            return []
        checks = {
            "market_id = :mid": row["market_id"] == params["mid"],
            "external_id IS NOT DISTINCT FROM :ext": row["external_id"] == params["ext"],
            "is_winner IS NOT DISTINCT FROM :from_won": row["is_winner"] == params["from_won"],
            "resolution_source IS NOT DISTINCT FROM :from_src": row["resolution_source"]
            == params["from_src"],
            "xmin::text = :version": row["row_version"] == params["version"],
        }
        if not all(ok for clause, ok in checks.items() if clause in sql):
            return []
        new = dict(
            row,
            is_winner=params["to_won"],
            resolution_source=params["to_src"],
            row_version=self.TXID,
        )
        if self.bump_last_updated:
            new["last_updated"] = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.txn[params["id"]] = new
        return [_Rec(row_version=new["row_version"], last_updated=new["last_updated"])] * (
            1 + self.extra_returning
        )

    def before_update(self, n):
        """A concurrent writer landing just before the n-th UPDATE."""

    def concurrent_write(self, oid, **fields):
        self.durable[oid] = dict(self.durable[oid], row_version="88000001", **fields)

    async def commit(self):
        self.commits += 1
        if self.commit_raises is not None:
            raise self.commit_raises
        self.durable.update(self.txn)
        self.txn = {}

    async def rollback(self):
        self.rolled_back = True
        self.txn = {}


def _session(retained, cls=FakeSession, market=None, outcomes=None, **kw):
    return cls(
        market if market is not None else _market(retained),
        outcomes if outcomes is not None else _outcomes(retained),
        **kw,
    )


def _run(repair, session, **kw):
    return asyncio.run(repair.run(session, PLACEMENT, **kw))


def _hash(repair, retained, **kw):
    return _run(repair, _session(retained, **kw), execute=False)["plan_hash"]


def _grades(session):
    return {i: (r["is_winner"], r["resolution_source"]) for i, r in session.durable.items()}


def test_the_dry_run_writes_nothing_and_takes_no_lock(repair, retained):
    s = _session(retained)
    out = _run(repair, s, execute=False)
    assert s.updates == [] and s.commits == 0
    assert out["mode"] == "apply-plan" and out["written"] == 0
    assert not any("FOR SHARE" in q or "FOR UPDATE" in q for q in s.sql)
    assert out["roster_lock_premise"] is True


def test_the_reads_are_bounded_to_the_pinned_market(repair):
    assert "WHERE id = :id" in repair._READ_MARKET_SQL
    assert "WHERE market_id = :mid" in repair._READ_OUTCOMES_SQL
    assert "LIMIT :cap" in repair._READ_OUTCOMES_SQL


def test_the_reviewed_apply_writes_the_plan_and_nothing_else(repair, retained):
    h = _hash(repair, retained)
    s = _session(retained)
    out = _run(repair, s, execute=True, expect_plan_hash=h)
    assert out["written"] == 72 and s.commits == 1
    reads = [q for q in s.sql if q.startswith("SELECT")]
    assert [q.rsplit(" FOR ", 1)[-1] for q in reads[1:3]] == ["UPDATE", "SHARE"]
    assert "FROM futures_markets" in reads[1] and "FROM futures_outcomes" in reads[2]
    grades = _grades(s)
    assert grades[BRENNAN] == (True, "leaderboard")
    assert sum(1 for g in grades.values() if g == (False, "leaderboard")) == 71
    assert sum(1 for g in grades.values() if g == (None, None)) == 83
    assert all(r["last_updated"] == LAST_UPDATED for r in s.durable.values())


def test_the_write_moves_the_grade_columns_alone_under_a_full_compare(repair):
    sql = " ".join(repair._CAS_SQL.split())
    set_clause = sql.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
    assert set_clause == "is_winner = :to_won, resolution_source = :to_src"
    for clause in (
        "id = :id",
        "market_id = :mid",
        "external_id IS NOT DISTINCT FROM :ext",
        "is_winner IS NOT DISTINCT FROM :from_won",
        "resolution_source IS NOT DISTINCT FROM :from_src",
        "xmin::text = :version",
    ):
        assert clause in sql


def test_a_wrong_hash_writes_nothing(repair, retained):
    s = _session(retained)
    with pytest.raises(repair.Refused, match="plan hash"):
        _run(repair, s, execute=True, expect_plan_hash="0" * 16)
    assert s.updates == []


def test_the_right_hash_on_an_inadmissible_plan_still_refuses(repair, retained):
    outcomes = _outcomes(retained)
    _row(outcomes, BRENNAN)["external_id"] = None
    h = _hash(repair, retained, outcomes=outcomes)
    s = _session(retained, outcomes=outcomes)
    with pytest.raises(repair.Refused, match="winner_identity"):
        _run(repair, s, execute=True, expect_plan_hash=h)
    assert s.updates == []


@pytest.mark.parametrize(
    "change",
    [
        lambda m, o: m.update(row_version="70000002"),
        lambda m, o: o[100].update(row_version="1"),
        lambda m, o: o[3].update(is_winner=False, resolution_source="did_not_play"),
        lambda m, o: m["market_metadata"]["leaderboard"][5].update(total_score=-4),
    ],
    ids=["market-version", "absent-row-version", "absent-row-grade", "board-byte"],
)
def test_any_drift_anywhere_in_the_market_moves_the_hash(repair, retained, change):
    m, o = _market(retained), _outcomes(retained)
    before = repair.plan(m, o, PLACEMENT)["plan_hash"]
    change(m, o)
    assert repair.plan(m, o, PLACEMENT)["plan_hash"] != before


class LateRowDrifts(FakeSession):
    """A row's grade moves just before its UPDATE; earlier UPDATEs already landed."""

    def before_update(self, n):
        if n == 40:
            oid = self.updates[-1]["id"]
            self.concurrent_write(oid, is_winner=False, resolution_source="did_not_play")


class LateRowSameValueWrite(FakeSession):
    """A writer re-writes a row with the SAME values: only xmin moves."""

    def before_update(self, n):
        if n == 40:
            self.concurrent_write(self.updates[-1]["id"])


@pytest.mark.parametrize("cls", [LateRowDrifts, LateRowSameValueWrite])
def test_drift_before_any_update_rolls_back_every_write(repair, retained, cls):
    h = _hash(repair, retained)
    s = _session(retained, cls=cls)
    with pytest.raises(repair.Refused, match="expected to change 1 row"):
        _run(repair, s, execute=True, expect_plan_hash=h)
    asyncio.run(s.rollback())
    assert s.commits == 0 and len(s.updates) == 40
    assert all(g in ((None, None), (False, "did_not_play")) for g in _grades(s).values())
    assert _grades(s)[BRENNAN] == (None, None)


def test_an_unexpected_row_count_refuses(repair, retained):
    h = _hash(repair, retained)
    s = _session(retained, extra_returning=1)
    with pytest.raises(repair.Refused, match="changed 2"):
        _run(repair, s, execute=True, expect_plan_hash=h)
    assert s.commits == 0


def test_a_write_that_moves_last_updated_refuses(repair, retained):
    h = _hash(repair, retained)
    s = _session(retained, bump_last_updated=True)
    with pytest.raises(repair.Refused, match="last_updated moved"):
        _run(repair, s, execute=True, expect_plan_hash=h)
    assert s.commits == 0


# ── 4b. the roster: rows the plan never writes still decide "one winner" ──────
#
# CERT-4252's countercases. In each, every CAS the run issues still matches: the
# concurrent write lands on a row the plan does NOT write, or adds a row. This fake
# has no locks, so these prove the in-transaction roster check refuses; that the
# LOCKS keep such a writer out at all (including in the instant after that check)
# is proved only against real Postgres, in
# tests/integration/test_repair_11315_roster_lock_pg.py.


class AbsentRowCrownedAfterRead(FakeSession):
    """CERT-4252 'absent-row-crowned': an unknown_absent outcome is crowned."""

    def before_update(self, n):
        if n == 1:
            self.concurrent_write(ABSENT, is_winner=True, resolution_source="leaderboard")


class AlreadyWinnerClearedAfterRead(FakeSession):
    """CERT-4252 'already-winner-cleared': the already-graded winner is cleared."""

    def before_update(self, n):
        if n == 1:
            self.concurrent_write(BRENNAN, is_winner=None, resolution_source=None)


class OutcomeJoinsAfterRead(FakeSession):
    """An outcome inserted into the market after the roster was read."""

    def before_update(self, n):
        if n == 1:
            self.durable[JOINER] = dict(
                id=JOINER,
                market_id=64266833,
                external_id="dg_77777777",
                is_winner=True,
                resolution_source="leaderboard",
                last_updated=LAST_UPDATED,
                row_version="88000002",
            )


class AbsentRowLeavesAfterRead(FakeSession):
    """An admitted outcome is moved out of the market after the roster was read."""

    def before_update(self, n):
        if n == 1:
            self.concurrent_write(ABSENT, market_id=1)


ABSENT = 241857510  # RETAINED id; CONSTRUCTED as off the 72-row board
JOINER = 999_000_001  # CONSTRUCTED


def _brennan_already(retained):
    outcomes = _outcomes(retained)
    _row(outcomes, BRENNAN).update(is_winner=True, resolution_source="leaderboard")
    return outcomes


def test_the_countercase_rows_are_rows_the_plan_never_writes(repair, retained):
    """Vacuity check: the concurrent targets are outside every CAS."""
    out = _plan(repair, retained)
    assert ABSENT in out["accounting"]["unknown_absent"]
    assert JOINER not in {o["id"] for o in _outcomes(retained)}
    already = _plan(repair, retained, outcomes=_brennan_already(retained))
    assert already["admissible"] and already["accounting"]["already"] == [BRENNAN]
    assert BRENNAN not in {w["id"] for w in already["write"]}


@pytest.mark.parametrize(
    "cls, brennan_already, reason",
    [
        (AbsentRowCrownedAfterRead, False, f"outcomes [{ABSENT}] changed"),
        (AlreadyWinnerClearedAfterRead, True, f"outcomes [{BRENNAN}] changed"),
        (OutcomeJoinsAfterRead, False, f"outcomes [{JOINER}] joined the market"),
        (AbsentRowLeavesAfterRead, False, f"outcomes [{ABSENT}] left the market"),
    ],
    ids=["absent-row-crowned", "already-winner-cleared", "outcome-joins", "absent-row-leaves"],
)
def test_a_roster_change_off_the_write_list_refuses_and_commits_nothing(
    repair, retained, cls, brennan_already, reason
):
    outcomes = _brennan_already(retained) if brennan_already else _outcomes(retained)
    h = _hash(repair, retained, outcomes=outcomes)
    s = _session(retained, cls=cls, outcomes=outcomes)
    with pytest.raises(repair.Refused, match="roster moved inside the transaction") as caught:
        _run(repair, s, execute=True, expect_plan_hash=h)
    assert reason in str(caught.value)
    # Every CAS matched: the refusal is the roster check, after the last UPDATE.
    assert len(s.updates) == (71 if brennan_already else 72)
    asyncio.run(s.rollback())
    assert s.commits == 0
    assert all(_grades(s)[i] == (None, None) for i in s.durable if i not in (ABSENT, BRENNAN, JOINER))


def test_the_unchanged_brennan_already_roster_still_writes_the_losers(repair, retained):
    """Positive control for the 'already' arm: the same roster, nobody moves."""
    outcomes = _brennan_already(retained)
    h = _hash(repair, retained, outcomes=outcomes)
    s = _session(retained, outcomes=outcomes)
    out = _run(repair, s, execute=True, expect_plan_hash=h)
    assert out["written"] == 71 and s.commits == 1
    assert [i for i, g in _grades(s).items() if g[0] is True] == [BRENNAN]


def test_an_apply_without_the_foreign_key_refuses_before_reading(repair, retained):
    h = _hash(repair, retained)
    s = _session(retained, outcome_fk=False)
    with pytest.raises(repair.Refused, match="roster_lock_premise"):
        _run(repair, s, execute=True, expect_plan_hash=h)
    assert s.updates == [] and not any("FOR " in q for q in s.sql)
    # The dry run reads and reports it; it never decides admissibility.
    plan = _run(repair, _session(retained, outcome_fk=False), execute=False)
    assert plan["roster_lock_premise"] is False and plan["admissible"]


def test_the_undo_does_not_depend_on_the_roster_premise(repair, retained):
    """A restore's inverse CAS is per row, so a missing key never blocks the undo."""
    s, written = _applied(repair, retained)
    s.outcome_fk = False
    plan = _run(repair, s, execute=False, written=written)
    out = _run(repair, s, execute=True, expect_plan_hash=plan["plan_hash"], written=written)
    assert out["written"] == 72 and all(g == (None, None) for g in _grades(s).values())


# ── 5. the undo ──────────────────────────────────────────────────────────────


def _applied(repair, retained):
    s = _session(retained)
    out = _run(repair, s, execute=True, expect_plan_hash=_hash(repair, retained))
    return s, out["written_versions"]


def test_the_restore_returns_exactly_the_written_rows_to_ungraded(repair, retained):
    s, written = _applied(repair, retained)
    plan = _run(repair, s, execute=False, written=written)
    assert plan["mode"] == "restore-plan" and plan["admissible"] and s.commits == 1
    out = _run(repair, s, execute=True, expect_plan_hash=plan["plan_hash"], written=written)
    assert out["written"] == 72 and s.commits == 2
    assert all(g == (None, None) for g in _grades(s).values())


def test_a_restore_refuses_a_row_written_again_after_the_apply(repair, retained):
    s, written = _applied(repair, retained)
    s.concurrent_write(BRENNAN)  # same values, new version
    plan = _run(repair, s, execute=False, written=written)
    assert not plan["admissible"]
    assert plan["accounting"]["moved_since_apply"] == [BRENNAN]
    with pytest.raises(repair.Refused):
        _run(repair, s, execute=True, expect_plan_hash=plan["plan_hash"], written=written)


def test_a_restore_never_touches_an_outcome_outside_this_market(repair, retained):
    s, written = _applied(repair, retained)
    plan = _run(repair, s, execute=False, written={**written, 1: "1"})
    assert not plan["admissible"] and plan["accounting"]["missing"] == [1]


def test_parse_written_refuses_malformed_pairs(repair):
    assert repair.parse_written("241857512:99000001, 2:3") == {241857512: "99000001", 2: "3"}
    for raw in ("", "241857512", "x:1", "1:y"):
        with pytest.raises(repair.Refused):
            repair.parse_written(raw)


# ── 6. UNKNOWN commit, production refusal ────────────────────────────────────


def test_a_commit_that_does_not_return_is_unknown_and_never_rolled_back(repair, retained):
    h = _hash(repair, retained)
    s = _session(retained, commit_raises=ConnectionError("08006"))
    with pytest.raises(repair.Unknown) as caught:
        _run(repair, s, execute=True, expect_plan_hash=h)
    report = caught.value.report
    assert report["outcome"] == "UNKNOWN" and report["statements_changed"] == 72
    assert report["returned_versions"][BRENNAN] == FakeSession.TXID
    assert s.commits == 1 and not s.rolled_back


@pytest.mark.parametrize("app", ["", "bainluck-staging", "local"])
def test_only_a_production_app_may_run_it(repair, app):
    with pytest.raises(repair.Refused):
        repair.refuse_unless_production({"HEROKU_APP_NAME": app})
    repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})


# ── 7. not the #1152 rails ───────────────────────────────────────────────────


def test_the_broad_grader_and_its_endpoint_are_never_reached(repair):
    tree = ast.parse(SCRIPT.read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    strings = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and not (n.value.startswith("#11315") or n.value.startswith("\n"))
    ]
    assert "_backfill_datagolf_winners" not in names | attrs
    assert not any("_backfill_datagolf_winners" in s or "datagolf-regrade-1152" in s for s in strings)
    assert "_datagolf_check_placement" in strings or "_datagolf_check_placement" in attrs


def test_the_placement_rule_is_the_running_graders(repair, retained):
    """Same verdicts as the stored-board grader for every retained board position."""
    for e in retained["leaderboard"]:
        assert PLACEMENT(str(e["position"]), "win") is (str(e["position"]) == "1")


# ── 8. the history half is NOT paid by this grade ───────────────────────────


def test_a_grade_alone_leaves_the_retained_reset_on_the_winner_line(retained):
    """KNOWN GAP, pinned on purpose (#11315's joint done-when). RETAINED line,
    CONSTRUCTED grade 1.0. Brennan reaches 1.0 at 06:41:26Z, never returns, and ends
    on the 22:08:55Z republication; the repeat-return rule needs 3 returns, so it
    returns the line unchanged, and the winner freeze only appends a `settlement`
    point after the reset. Whoever adopts a history boundary rule flips this test
    deliberately — see the #11315 history-boundary proposal artifact."""
    futures = importlib.import_module("app.routes.futures")
    line = retained["lines"][str(BRENNAN)]["history"]
    assert len(line) == 335
    first = next(i for i, p in enumerate(line) if p["probability"] >= 0.999)
    assert line[first]["timestamp"] == "2026-10-11T06:41:26.165769+00:00"
    assert line[-1] == {
        "timestamp": "2026-10-11T22:08:55.891004+00:00",
        "probability": 0.026017,
        "american_odds": None,
        "bookmaker": "consensus",
    }
    assert futures._drop_post_decision_republication(line, 1.0) is line

    class _Champ:
        id = BRENNAN

    hist = {BRENNAN: {"history": copy.deepcopy(line)}}
    settle = datetime(2026, 10, 11, 6, 41, 26, tzinfo=timezone.utc)
    futures._freeze_one_winner_line(_Champ, hist, {}, settle, allow_synthesis=False)
    tail = hist[BRENNAN]["history"][-2:]
    assert tail[0]["probability"] == 0.026017 and tail[1]["bookmaker"] == "settlement"
