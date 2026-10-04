"""Theme assembly + immutable snapshots — #9935 unit A2, no database needed.

The contract is ``docs/theme-collection-producer-contract-9935.md`` §10.4
(v3.4). Case numbers are its §8; P1–P6 are its publication discriminators.
The real-Postgres half (the table from S0's DDL, the route, the corrections
enqueue) is C1's ``tests/integration/test_theme_collections_9935_pg.py``.

What stands in for the database here is ``_FakeDB``: committed state plus a
per-session working copy, so a rollback discards and a commit publishes, and
every statement a pass issues is recorded. Gather is the one seam replaced
(``_page_ids`` / ``_load_markets``): its arms are P1's, built and pinned there,
and the fake returns the union of the arms' population and the container's
prior decisions — the shape the prior-decision arm gives the real query.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.tasks import theme_assembly as ta
from app.utils import discover_bundles
from app.utils.container_corrections import WITHHELD_WITHDRAWN
from app.utils.theme_definitions import (
    AI,
    CONTAINER_MEMBER_WITHDRAWN,
    OSCARS_2027,
    Decision,
    ThemeDefinition,
)

BACKEND = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


def _row(market_id, name, *, source="polymarket", external_id=None, category="tech",
         status="open", outcomes=("Yes", "No"), settled_at=None, metadata=None):
    return ta.MemberRow(
        id=market_id,
        name=name,
        source=source,
        external_id=external_id or f"PM-{market_id}",
        status=status,
        llm_sport_category=category,
        settled_at=settled_at,
        market_metadata=metadata,
        outcomes=tuple(ta.OutcomeRow(o, None, None) for o in outcomes),
    )


# Real ids from #9925 evidence where the contract names them.
OPENAI_IPO = _row(13791997, "OpenAI IPO before 2027?")
CLAUDE_6 = _row(61461524, "Claude 6 released before 2027?", source="kalshi",
                external_id="KXCLAUDE-CLAUDE6")
GPT_6 = _row(70000001, "Will OpenAI announce GPT-6 before 2027?")
# Production names, read 2026-10-04 (the Polymarket nominations title carries
# its trailing space).
KALSHI_BEST_PICTURE = _row(6173044, "Oscar Winner: Best Picture", source="kalshi",
                           external_id="KXOSCARPIC-27", category="entertainment",
                           outcomes=("The Odyssey", "Hamnet"))
PM_BEST_PICTURE = _row(57313556, "Oscars 2027: Best Picture Winner",
                       category="entertainment", outcomes=("The Odyssey", "Hamnet"))
PM_NOMINATIONS = _row(27988771, "Oscars 2027: Best Picture Nominations ",
                      category="entertainment")


def _ipos_definition():
    """Case 1's test-only second definition: admits any OpenAI-IPO row."""

    def decide(defn, market, *, now):
        del now
        if "ipo" in (market.name or "").lower():
            return Decision("admitted", "admitted_entity_signal", defn.rule_version,
                            "side_question", {"clauses": [], "inputs": {}, "fields": {}, "flags": []})
        return Decision("excluded", "not_this_subject", defn.rule_version, None,
                        {"clauses": [], "inputs": {}, "fields": {}, "flags": []})

    return ThemeDefinition(
        subject="ipos", scope="continuing", retention_days=14, rule_version="ipos-test@1",
        container_kind="theme", category="economics", display_name="IPOs",
        decider=decide, population=lambda *a, **k: {},
    )


# ---------------------------------------------------------------------------
# The database double
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeDB:
    def __init__(self):
        self.flags = {"tables": True, "ledger": True, "columns": True, "decisions": True}
        self.state = {
            "containers": {},  # id -> {id, slug, name, kind, category, window_end, revision}
            "edges": {},  # (cid, child_id) -> {"class", "source"}
            "decisions": {},  # (cid, child_id) -> row
            "ledger": [],  # (cid, child_type, child_id, action), append-only
            "receipts": {13791997: {"outcome": "linked", "phase": "matcher"}},
        }
        self.markets: dict[int, ta.MemberRow] = {}
        self.population: dict[str, set[int]] = {}
        self.statements: list[tuple[str, object]] = []
        self.next_id = 100

    # --- fixtures -----------------------------------------------------------
    def add_markets(self, *rows, slug=None):
        for row in rows:
            self.markets[row.id] = row
            if slug is not None:
                self.population.setdefault(slug, set()).add(row.id)

    def container_id(self, slug):
        return next(c["id"] for c in self.state["containers"].values() if c["slug"] == slug)

    def revision(self, slug):
        return self.state["containers"][self.container_id(slug)]["revision"]

    def theme_edges(self, slug):
        cid = self.container_id(slug)
        return {k[1]: v["class"] for k, v in self.state["edges"].items()
                if k[0] == cid and v["source"] == "theme_rule"}

    def decision(self, slug, child_id):
        return self.state["decisions"][(self.container_id(slug), child_id)]

    def withdraw(self, slug, child_id):
        """``container_corrections._member_correction``'s effect, committed."""
        cid = self.container_id(slug)
        self.state["edges"].pop((cid, child_id), None)
        self.state["containers"][cid]["revision"] += 1
        self.state["ledger"].append((cid, "market", child_id, "withdraw"))

    def writes(self):
        reads = ("SELECT", "WITH RECURSIVE", "GATHER")
        return [s for s, _ in self.statements
                if not s.lstrip().upper().startswith(reads)]

    def session(self):
        return _FakeSession(self)


class _FakeSession:
    def __init__(self, db: _FakeDB):
        self.db = db
        self.work = copy.deepcopy(db.state)
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.db.state = copy.deepcopy(self.work)
        self.commits += 1

    async def rollback(self):
        self.work = copy.deepcopy(self.db.state)
        self.rollbacks += 1

    async def execute(self, sql, params=None):
        sql = str(sql)
        self.db.statements.append((sql, params))
        w, f = self.work, self.db.flags
        if "to_regclass('public.containers')" in sql:
            return _Result([(f["tables"],) * 4])
        if "to_regclass('public.container_corrections')" in sql:
            return _Result([(f["ledger"], f["columns"])])
        if sql == ta.DECISIONS_REGCLASS_SQL:
            return _Result([(f["decisions"],)])
        if sql.startswith("SELECT id, slug, name FROM containers"):
            key, value = ("slug", params["slug"]) if "slug" in params else ("id", params["cid"])
            hits = [c for c in w["containers"].values() if c[key] == value]
            return _Result([(c["id"], c["slug"], c["name"]) for c in hits])
        if sql.startswith("INSERT INTO containers"):
            if not any(c["slug"] == params["slug"] for c in w["containers"].values()):
                cid = self.db.next_id
                self.db.next_id += 1
                w["containers"][cid] = {"id": cid, "revision": 0, **params}
            return _Result()
        if "FOR UPDATE OF c" in sql:
            c = w["containers"].get(params["cid"])
            return _Result([(c["id"], "unpublished", c["revision"], 0)] if c else [])
        if "FROM container_corrections" in sql:
            latest = {}
            for cid, ctype, child, action in w["ledger"]:
                if cid == params["cid"]:
                    latest[(ctype, child)] = action
            return _Result([(k[0], k[1], a) for k, a in latest.items()])
        if sql.startswith("SELECT child_id, class, source FROM event_edges"):
            return _Result([(k[1], v["class"], v["source"]) for k, v in w["edges"].items()
                            if k[0] == params["cid"]])
        if sql.startswith("SELECT child_type, child_id, class FROM event_edges"):
            return _Result([("market", k[1], v["class"]) for k, v in w["edges"].items()
                            if k[0] == params["cid"]])
        if sql.startswith("INSERT INTO event_edges"):
            guarded = "WHERE event_edges.source = 'theme_rule'" in sql
            for p in params:
                key = (p["cid"], p["child_id"])
                if key not in w["edges"]:
                    w["edges"][key] = {"class": p["class"], "source": p["source"]}
                elif not guarded or w["edges"][key]["source"] == "theme_rule":
                    w["edges"][key]["class"] = p["class"]
            return _Result()
        if sql.startswith("DELETE FROM event_edges"):
            guarded = "source = 'theme_rule'" in sql
            gone = [k for k, v in w["edges"].items()
                    if k[0] == params["cid"] and k[1] in params["ids"]
                    and (not guarded or v["source"] == "theme_rule")]
            for k in gone:
                del w["edges"][k]
            return _Result(rowcount=len(gone))
        if "UPDATE containers SET membership_revision" in sql:
            c = w["containers"][params["cid"]]
            c["revision"] += 1
            return _Result([(c["id"], c["revision"])])
        if sql.startswith("INSERT INTO container_member_decisions"):
            for p in params:
                key = (p["container_id"], p["child_id"])
                row = {**p, "evidence": json.loads(p["evidence"])}
                prior = w["decisions"].get(key)
                row["attempt_count"] = prior["attempt_count"] + 1 if prior else 1
                w["decisions"][key] = row
            return _Result()
        raise AssertionError(f"unexpected statement: {sql[:120]}")


class _FakeRedis:
    """``SET NX EX`` / ``GET`` / ``EXPIRE``, plus the forbidden verbs so a
    mutation that uses one is visible in ``log``."""

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttl: dict[str, int] = {}
        self.log: list[tuple] = []

    def set(self, key, value, nx=False, ex=None, **kwargs):
        self.log.append(("SET", key, bool(nx), ex))
        if nx and key in self.store:
            return None
        self.store[key] = value if isinstance(value, bytes) else str(value).encode()
        self.ttl[key] = ex
        return True

    def get(self, key):
        self.log.append(("GET", key))
        return self.store.get(key)

    def expire(self, key, seconds):
        self.log.append(("EXPIRE", key, seconds))
        if key not in self.store:
            return False
        self.ttl[key] = seconds
        return True

    def setex(self, key, seconds, value):
        self.log.append(("SETEX", key, seconds))
        self.store[key] = value if isinstance(value, bytes) else str(value).encode()
        return True

    def delete(self, *keys):
        self.log.append(("DEL", *keys))
        return sum(1 for k in keys if self.store.pop(k, None) is not None)

    def writes(self):
        return [entry for entry in self.log if entry[0] != "GET"]


@pytest.fixture
def db(monkeypatch):
    database = _FakeDB()

    @asynccontextmanager
    async def _session():
        yield database.session()

    async def _page_ids(session, defn, container_id, now, cursor, limit):
        database.statements.append(("GATHER page", {"slug": defn.slug(), "cursor": cursor}))
        prior = {child for (cid, child) in session.work["decisions"] if cid == container_id}
        ids = sorted((database.population.get(defn.slug(), set()) | prior))
        return [i for i in ids if i > cursor][:limit]

    async def _load_markets(session, ids):
        database.statements.append(("GATHER rows", list(ids)))
        return {i: database.markets[i] for i in ids if i in database.markets}

    import app.tasks.base

    monkeypatch.setattr(app.tasks.base, "get_task_session", _session)
    monkeypatch.setattr(ta, "_page_ids", _page_ids)
    monkeypatch.setattr(ta, "_load_markets", _load_markets)
    monkeypatch.setenv(ta.THEME_ASSEMBLY_ENABLED_ENV, "1")
    return database


@pytest.fixture
def redis(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr(ta, "_redis_client", lambda: client)
    return client


def _stored(redis_client, db, slug, revision=None):
    cid = db.container_id(slug)
    rev = db.revision(slug) if revision is None else revision
    raw = redis_client.store.get(ta.snapshot_key(cid, rev))
    return None if raw is None else json.loads(raw)


def _container(report, slug):
    return next(c for c in report["containers"] if c["slug"] == slug)


async def _assemble(only="ai", **kwargs):
    return await ta._run_assemble_theme_collections(only=only, now=kwargs.pop("now", NOW), **kwargs)


# ---------------------------------------------------------------------------
# Gates (semantics 1) and the zero-write arms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_unset_writes_nothing_anywhere(db, redis, monkeypatch):
    monkeypatch.delenv(ta.THEME_ASSEMBLY_ENABLED_ENV, raising=False)
    db.add_markets(OPENAI_IPO, slug="ai")

    for run in (_assemble(only=None), ta._run_rebuild_theme_snapshot(1)):
        report = await run
        assert report["terminal"] == "skipped"
        assert report["reason"] == "theme_assembly_disabled"

    assert db.statements == []  # not one statement, so certainly no non-SELECT
    assert redis.log == []
    assert db.state["containers"] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing,reason",
    [
        ("tables", "containers_tables_absent"),
        ("columns", "correction_schema_absent"),
        ("ledger", "correction_schema_absent"),
        ("decisions", "decision_schema_absent"),
    ],
)
async def test_each_schema_gate_refuses_before_any_write(db, redis, missing, reason):
    db.flags[missing] = False
    db.add_markets(OPENAI_IPO, slug="ai")

    for run in (_assemble(), ta._run_rebuild_theme_snapshot(1)):
        report = await run
        assert (report["terminal"], report["reason"]) == ("skipped", reason)

    assert db.writes() == []
    assert redis.log == []


@pytest.mark.asyncio
async def test_a_dry_run_plans_and_writes_nothing(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")

    report = await _assemble(apply=False)

    ai = _container(report, "ai")
    assert ai["admitted"] == 2 and ai["edges_upserted"] == 2 and ai["membership_changed"]
    assert db.writes() == []
    assert redis.log == []
    assert db.state["containers"] == {}  # a missing container is not created by a dry run


# ---------------------------------------------------------------------------
# Case 1 — two definitions, two edges, two decision rows, receipts untouched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_1_one_market_admitted_by_two_definitions(db, redis, monkeypatch):
    ipos = _ipos_definition()
    monkeypatch.setattr(ta, "REGISTRY", {"ai": AI, "ipos": ipos})
    db.add_markets(OPENAI_IPO, slug="ai")
    db.population["ipos"] = {OPENAI_IPO.id}
    receipts_before = copy.deepcopy(db.state["receipts"])

    report = await _assemble(only=None)

    assert report["terminal"] == "complete", report
    for slug in ("ai", "ipos"):
        assert db.theme_edges(slug) == {OPENAI_IPO.id: "side_question"}
        assert db.decision(slug, OPENAI_IPO.id)["outcome"] == "admitted"
    assert len(db.state["decisions"]) == 2
    assert db.state["receipts"] == receipts_before
    assert not any("market_match_receipts" in s for s, _ in db.statements)


# ---------------------------------------------------------------------------
# Case 12 — a withdrawn member stays withdrawn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_12_a_withdrawn_member_is_excluded_whatever_decide_says(db, redis):
    db.add_markets(KALSHI_BEST_PICTURE, PM_BEST_PICTURE, slug="oscars-2027")
    await _assemble(only="oscars-2027")
    assert PM_BEST_PICTURE.id in db.theme_edges("oscars-2027")

    db.withdraw("oscars-2027", PM_BEST_PICTURE.id)
    before = db.revision("oscars-2027")
    report = _container(await _assemble(only="oscars-2027"), "oscars-2027")

    assert PM_BEST_PICTURE.id not in db.theme_edges("oscars-2027")
    row = db.decision("oscars-2027", PM_BEST_PICTURE.id)
    assert (row["outcome"], row["reason"]) == ("excluded", CONTAINER_MEMBER_WITHDRAWN)
    assert row["evidence"]["correction"] == "withdraw"
    assert row["evidence"]["rule_decision"]["outcome"] == "admitted"
    assert db.revision("oscars-2027") == before + 1  # bumped exactly once by the pass
    assert report["excluded"] == {CONTAINER_MEMBER_WITHDRAWN: 1}
    assert WITHHELD_WITHDRAWN == CONTAINER_MEMBER_WITHDRAWN


# ---------------------------------------------------------------------------
# Case 13 — static
# ---------------------------------------------------------------------------


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def test_case_13_feed_never_imports_assembly_and_assembly_calls_no_llm():
    feed = _imports(BACKEND / "app" / "routes" / "feed.py")
    assert not any("theme_assembly" in n for n in feed)
    assert not any(n.endswith("candidate_population") for n in feed)

    mine = _imports(BACKEND / "app" / "tasks" / "theme_assembly.py")
    assert not any(n.startswith("app.routes") for n in mine)
    banned = ("openai", "anthropic", "llm", "hook_generator")
    assert not any(b in n.lower() for n in mine for b in banned), mine


def test_the_producer_never_overwrites_a_snapshot_key():
    """Semantics 9: no unconditional SET, SETEX, GETSET or DEL on a key."""
    source = (BACKEND / "app" / "tasks" / "theme_assembly.py").read_text()
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)]
    verbs = {c.func.attr for c in calls if getattr(c.func.value, "id", "") == "redis_client"}
    assert verbs == {"set", "get", "expire"}
    (set_call,) = [c for c in calls if c.func.attr == "set"
                   and getattr(c.func.value, "id", "") == "redis_client"]
    kwargs = {k.arg: k.value for k in set_call.keywords}
    assert isinstance(kwargs.get("nx"), ast.Constant) and kwargs["nx"].value is True
    assert "ex" in kwargs


# ---------------------------------------------------------------------------
# Case 16 — the gate and the fold are Discover's, by identity
# ---------------------------------------------------------------------------


def test_case_16_gate_and_fold_are_imported_not_copied():
    assert ta.theme_member_withhold_reason is discover_bundles.theme_member_withhold_reason
    assert ta._dedupe_same_question_members is discover_bundles._dedupe_same_question_members


def _quality(monkeypatch, classes: dict[str, str]):
    """Drive Discover's own classifier: a copied gate would not see this."""

    class _Q:
        def __init__(self, quality_class):
            self.quality_class = quality_class

    real = discover_bundles.classify_market_quality

    def fake(**kwargs):
        if kwargs.get("market_name") in classes:
            return _Q(classes[kwargs["market_name"]])
        return real(**kwargs)

    monkeypatch.setattr(discover_bundles, "classify_market_quality", fake)


@pytest.mark.asyncio
async def test_case_16_a_low_quality_member_stays_admitted_and_off_the_page(db, redis, monkeypatch):
    _quality(monkeypatch, {GPT_6.name: "low_quality", CLAUDE_6.name: "suppress"})
    db.add_markets(OPENAI_IPO, CLAUDE_6, GPT_6, slug="ai")

    report = _container(await _assemble(), "ai")

    assert set(db.theme_edges("ai")) == {OPENAI_IPO.id, CLAUDE_6.id, GPT_6.id}
    assert report["admitted"] == 3
    snap = _stored(redis, db, "ai")
    assert snap["withheld"]["low_quality"] == [GPT_6.id]
    assert snap["withheld"]["suppressed"] == [CLAUDE_6.id]
    assert snap["shown_ids"] == [OPENAI_IPO.id]
    assert snap["eligible_count"] == 3 and snap["shown_count"] == 1


# ---------------------------------------------------------------------------
# Case 19 — two venues, one question: two members, one shown
# ---------------------------------------------------------------------------


def _fold_winner_titles(monkeypatch):
    """Make Discover's fold pair the two Best Picture WINNER questions, through
    the matcher it calls (``cross_source_matching.is_same_question``, which
    receives the fold's own comparison titles). The fold itself runs unpatched,
    so the identity A2 depends on is the one under test."""
    from app.utils import cross_source_matching

    def winner(title):
        t = title.lower()
        return "best picture" in t and "nomin" not in t

    monkeypatch.setattr(cross_source_matching, "is_same_question",
                        lambda a, b: winner(a) and winner(b))


@pytest.mark.asyncio
async def test_case_19_a_cross_venue_pair_is_two_members_and_one_shown_question(
    db, redis, monkeypatch
):
    _fold_winner_titles(monkeypatch)
    db.add_markets(KALSHI_BEST_PICTURE, PM_BEST_PICTURE, PM_NOMINATIONS, slug="oscars-2027")

    await _assemble(only="oscars-2027")

    assert db.theme_edges("oscars-2027") == {
        KALSHI_BEST_PICTURE.id: "title",
        PM_BEST_PICTURE.id: "title",
        PM_NOMINATIONS.id: "advancement",
    }
    assert len(db.state["decisions"]) == 3
    snap = _stored(redis, db, "oscars-2027")
    # page order is (class rank, id): both titles before the advancement row,
    # so the better-placed Kalshi title survives and Polymarket's folds
    assert snap["shown_ids"] == [KALSHI_BEST_PICTURE.id, PM_NOMINATIONS.id]
    assert snap["folded_ids"] == [PM_BEST_PICTURE.id]
    assert snap["shown_count"] == 2 and snap["eligible_count"] == 3


def test_case_19_the_page_split_is_exactly_discovers_fold():
    """Whatever the fold decides for the real rows, the snapshot carries it
    unchanged: shown + folded partition the eligible members in page order."""
    members = {KALSHI_BEST_PICTURE.id: "title", PM_BEST_PICTURE.id: "title",
               PM_NOMINATIONS.id: "advancement"}
    rows = {r.id: r for r in (KALSHI_BEST_PICTURE, PM_BEST_PICTURE, PM_NOMINATIONS)}
    snap = ta.build_snapshot({"id": 7, "slug": "oscars-2027", "name": "Oscars 2027"}, 1,
                             members, rows, inventory_complete=True)
    items = [{"type": "futures", "data": {"id": i, "name": rows[i].name, "source": rows[i].source}}
             for i in (KALSHI_BEST_PICTURE.id, PM_BEST_PICTURE.id, PM_NOMINATIONS.id)]
    kept, folded = discover_bundles._dedupe_same_question_members(items)
    assert snap.shown_ids == tuple(i["data"]["id"] for i in kept)
    assert snap.folded_ids == tuple(i["data"]["id"] for i in folded)
    assert sorted(snap.shown_ids + snap.folded_ids) == sorted(members)


# ---------------------------------------------------------------------------
# Cases 20 / 21 at plan level
# ---------------------------------------------------------------------------


def _md(child_id, outcome="admitted", reason="admitted_entity_signal", edge_class="side_question",
        withdrawn=False, rule="ai-subject@1"):
    return ta.MemberDecision(
        child_id,
        Decision(outcome, reason, rule, edge_class if outcome == "admitted" else None,
                 {"clauses": [], "inputs": {}, "fields": {}, "flags": []}),
        withdrawn,
    )


def test_case_20_a_finite_member_re_decided_admitted_changes_nothing():
    plan = ta.plan_container_pass(
        [_md(5165726, edge_class="advancement", reason="admitted_ticker_edition",
             rule="oscars-edition@1")],
        {5165726: "advancement"},
        inventory_complete=True,
    )
    assert plan.edge_deletes == ()
    assert plan.edge_upserts == ((5165726, "advancement"),)
    assert not plan.membership_changed
    assert [r["outcome"] for r in plan.decision_rows] == ["admitted"]


def test_case_21_a_retired_ai_member_loses_its_edge():
    plan = ta.plan_container_pass(
        [_md(61461524, outcome="excluded", reason="resolved_beyond_retention")],
        {61461524: "side_question"},
        inventory_complete=True,
    )
    assert plan.edge_deletes == (61461524,) and plan.edge_upserts == ()
    assert plan.membership_changed
    assert plan.decision_rows[0]["reason"] == "resolved_beyond_retention"


@pytest.mark.asyncio
async def test_case_21_through_the_pass_retires_once_through_the_prior_decision_arm(db, redis):
    db.add_markets(CLAUDE_6, OPENAI_IPO, slug="ai")
    await _assemble()
    before = db.revision("ai")

    # Claude 6 settles 20 days ago: the open-entity arm no longer offers it,
    # only its prior decision row gathers it back to be re-decided.
    db.population["ai"].discard(CLAUDE_6.id)
    db.markets[CLAUDE_6.id] = dataclasses.replace(
        CLAUDE_6, status="resolved", settled_at=NOW - timedelta(days=20))
    report = _container(await _assemble(), "ai")

    assert CLAUDE_6.id not in db.theme_edges("ai")
    assert db.decision("ai", CLAUDE_6.id)["reason"] == "resolved_beyond_retention"
    assert db.revision("ai") == before + 1 and report["revision_reason"] == "membership_changed"


# ---------------------------------------------------------------------------
# Own arms: truncated pass, the survivor, a bad row
# ---------------------------------------------------------------------------


def test_a_truncated_plan_never_retires_a_member_it_did_not_see():
    current = {1: "side_question", 2: "side_question"}
    truncated = ta.plan_container_pass([_md(1)], current, inventory_complete=False)
    assert truncated.edge_deletes == () and not truncated.membership_changed

    complete = ta.plan_container_pass([_md(1)], current, inventory_complete=True)
    assert complete.edge_deletes == (2,) and complete.membership_changed


@pytest.mark.asyncio
async def test_a_pass_out_of_budget_keeps_every_member_it_did_not_reach(db, redis, monkeypatch):
    db.add_markets(OPENAI_IPO, CLAUDE_6, GPT_6, slug="ai")
    await _assemble()
    assert len(db.theme_edges("ai")) == 3

    ticks = iter([0, 0] + [10_000] * 50)  # one page inside the budget, then over
    monkeypatch.setattr(ta, "_monotonic", lambda: next(ticks))
    monkeypatch.setattr(ta, "GATHER_PAGE", 1)
    report = _container(await _assemble(), "ai")

    assert report["inventory_complete"] is False
    assert report["terminal"] == "partial" and report["reason"] == "inventory_incomplete"
    assert len(db.theme_edges("ai")) == 3
    assert report["edges_deleted"] == 0


@pytest.mark.asyncio
async def test_a_non_theme_rule_edge_survives_a_retire(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    cid = db.container_id("ai")
    db.state["edges"][(cid, 999)] = {"class": "prop", "source": "human"}

    db.population["ai"] = set()
    db.markets.pop(CLAUDE_6.id)  # gone: the complete pass retires it
    await _assemble()

    assert db.state["edges"][(cid, 999)] == {"class": "prop", "source": "human"}
    assert CLAUDE_6.id not in db.theme_edges("ai")


@pytest.mark.asyncio
async def test_the_delete_itself_refuses_another_sources_edge(db):
    db.state["containers"][7] = {"id": 7, "slug": "ai", "name": "AI", "revision": 0}
    db.state["edges"][(7, 999)] = {"class": "prop", "source": "human"}
    session = db.session()
    plan = ta.PassPlan(edge_upserts=((999, "side_question"),), edge_deletes=(999,),
                       decision_rows=(), membership_changed=True)

    await ta._write_edges(session, 7, plan)

    assert session.work["edges"][(7, 999)] == {"class": "prop", "source": "human"}


@pytest.mark.asyncio
async def test_an_admitted_child_held_by_another_source_is_not_a_change():
    plan = ta.plan_container_pass([_md(999)], {}, inventory_complete=True, foreign_held={999})
    assert plan.edge_upserts == () and not plan.membership_changed


@pytest.mark.asyncio
async def test_one_row_whose_decision_raises_cannot_retire_anyone(db, redis, monkeypatch):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    real = AI.decider

    def flaky(defn, market, *, now):
        if market.id == CLAUDE_6.id:
            raise RuntimeError("bad row")
        return real(defn, market, now=now)

    monkeypatch.setattr(ta, "REGISTRY", {"ai": dataclasses.replace(AI, decider=flaky)})
    report = _container(await _assemble(), "ai")

    assert report["inventory_complete"] is False and report["errors"]
    assert CLAUDE_6.id in db.theme_edges("ai")


# ---------------------------------------------------------------------------
# Case 24 + P3 — content change bumps once; an identical rerun refreshes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_24_a_member_turning_low_quality_bumps_once_and_reruns_refresh(
    db, redis, monkeypatch
):
    db.add_markets(OPENAI_IPO, GPT_6, slug="ai")
    await _assemble()
    n = db.revision("ai")

    _quality(monkeypatch, {GPT_6.name: "low_quality"})
    report = _container(await _assemble(), "ai")
    assert report["edges_upserted"] == 2 and not report["edges_deleted"]
    assert db.revision("ai") == n + 1
    assert (report["bumped"], report["revision_reason"]) == (True, "content_changed")
    snap = _stored(redis, db, "ai")
    assert snap["revision"] == n + 1 and snap["withheld"]["low_quality"] == [GPT_6.id]
    assert snap["shown_count"] == 1

    key = ta.snapshot_key(db.container_id("ai"), n + 1)
    stored = redis.store[key]
    redis.log.clear()
    rerun = _container(await _assemble(), "ai")

    assert db.revision("ai") == n + 1
    assert (rerun["bumped"], rerun["revision_reason"], rerun["snapshot"]) == (
        False, "identical", "refreshed")
    assert [e for e in redis.log if e[0] == "EXPIRE"] == [("EXPIRE", key, ta.SNAPSHOT_TTL_S)]
    assert redis.store[key] == stored
    assert db.decision("ai", GPT_6.id)["revision"] == n + 1
    assert db.decision("ai", GPT_6.id)["attempt_count"] == 3


# ---------------------------------------------------------------------------
# Case 25's rebuild half — the last member withdrawn publishes an empty page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_25_rebuild_after_the_last_withdrawal_publishes_an_empty_snapshot(db, redis):
    db.add_markets(OPENAI_IPO, slug="ai")
    await _assemble()
    db.withdraw("ai", OPENAI_IPO.id)  # N -> N+1, nothing published at N+1
    n1 = db.revision("ai")
    writes_before = len(db.writes())

    report = await ta._run_rebuild_theme_snapshot(db.container_id("ai"))

    ai = report["containers"][0]
    assert report["terminal"] == "complete"
    assert (ai["revision_reason"], ai["revision_after"]) == ("snapshot_absent", n1 + 1)
    snap = _stored(redis, db, "ai")
    assert snap["revision"] == n1 + 1
    assert snap["shown_ids"] == [] and snap["shown_count"] == 0 and snap["eligible_count"] == 0
    rebuild_writes = db.writes()[writes_before:]
    assert all(s.startswith("UPDATE containers SET membership_revision") or "chain" in s
               for s in rebuild_writes), rebuild_writes  # no edge or decision-row write


@pytest.mark.asyncio
async def test_a_rebuild_refuses_a_container_that_is_not_a_theme(db, redis):
    db.state["containers"][9] = {"id": 9, "slug": "nfl-2026-week-4", "name": "Week 4",
                                 "revision": 3}
    report = await ta._run_rebuild_theme_snapshot(9)
    assert (report["terminal"], report["reason"]) == ("skipped", "not_a_theme_container")
    assert db.writes() == [] and redis.log == []


# ---------------------------------------------------------------------------
# Publication discriminators P1–P6 (v3.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p1_a_delayed_producer_never_redefines_the_revision_after_it(
    db, redis, monkeypatch
):
    db.add_markets(OPENAI_IPO, slug="ai")
    await _assemble()
    n0 = db.revision("ai")

    # Pass A: membership grows, commits N1, its publication is held back.
    db.add_markets(CLAUDE_6, slug="ai")
    deferred = []
    real_publish = ta.publish_snapshot
    monkeypatch.setattr(ta, "publish_snapshot", lambda c, s: deferred.append((c, s)) or "written")
    await _assemble()
    n1 = db.revision("ai")
    assert n1 == n0 + 1 and len(deferred) == 1

    # Pass B: different contents, finds N1's key absent under the lock.
    monkeypatch.setattr(ta, "publish_snapshot", real_publish)
    _quality(monkeypatch, {CLAUDE_6.name: "low_quality"})
    report = _container(await _assemble(), "ai")
    n2 = db.revision("ai")
    assert (report["revision_reason"], n2) == ("snapshot_absent", n1 + 1)
    b_bytes = redis.store[ta.snapshot_key(db.container_id("ai"), n2)]

    # A publishes late: only its own, older key.
    client, a_snapshot = deferred[0]
    redis.log.clear()
    assert real_publish(client, a_snapshot) == "written"
    assert {e[1] for e in redis.writes()} == {ta.snapshot_key(db.container_id("ai"), n1)}
    assert redis.store[ta.snapshot_key(db.container_id("ai"), n2)] == b_bytes
    assert json.loads(b_bytes)["withheld"]["low_quality"] == [CLAUDE_6.id]
    assert db.revision("ai") == n2


@pytest.mark.asyncio
async def test_p2_a_missing_key_allocates_a_fresh_revision(db, redis):
    db.add_markets(OPENAI_IPO, slug="ai")
    first = _container(await _assemble(), "ai")
    assert first["revision_reason"] == "membership_changed"
    n = db.revision("ai")

    # Unchanged membership, key present: identical.
    assert _container(await _assemble(), "ai")["revision_reason"] == "identical"

    # Evicted: the next pass allocates N+1, never rewrites N.
    redis.store.pop(ta.snapshot_key(db.container_id("ai"), n))
    redis.log.clear()
    evicted = _container(await _assemble(), "ai")
    assert (evicted["bumped"], evicted["revision_reason"]) == (True, "snapshot_absent")
    assert db.revision("ai") == n + 1
    assert not any(e[1] == ta.snapshot_key(db.container_id("ai"), n) for e in redis.writes())


@pytest.mark.asyncio
async def test_p2_a_first_publication_with_no_membership_change_still_bumps(db, redis):
    db.add_markets(OPENAI_IPO, slug="ai")
    await _assemble()
    n = db.revision("ai")
    redis.store.clear()  # the initial key never landed (or Redis was flushed)

    report = _container(await _assemble(), "ai")

    assert report["revision_reason"] == "snapshot_absent" and db.revision("ai") == n + 1
    assert report["snapshot"] == "written"


def _snapshot(revision=4, shown=(1, 2)):
    return ta.ThemeSnapshot(
        container_id=7, slug="ai", name="AI", revision=revision, inventory_complete=True,
        shown_ids=tuple(shown), folded_ids=(),
        withheld={k: () for k in ta.SNAPSHOT_WITHHOLDS},
        shown_count=len(shown), eligible_count=len(shown),
    )


def test_p3_an_identical_publication_only_refreshes_the_ttl():
    client = _FakeRedis()
    snap = _snapshot()
    key = ta.snapshot_key(7, 4)
    client.store[key] = snap.payload()
    client.ttl[key] = 5

    assert ta.publish_snapshot(client, snap) == "refreshed"
    assert client.store[key] == snap.payload() and client.ttl[key] == ta.SNAPSHOT_TTL_S
    assert [e[0] for e in client.log] == ["SET", "GET", "EXPIRE"]


def test_p4_a_stale_producer_touches_only_its_own_revision():
    client = _FakeRedis()
    newer = _snapshot(revision=6, shown=(1, 2, 3))
    client.store[ta.snapshot_key(7, 6)] = newer.payload()

    assert ta.publish_snapshot(client, _snapshot(revision=5)) == "written"

    assert client.store[ta.snapshot_key(7, 6)] == newer.payload()
    assert {e[1] for e in client.writes()} == {ta.snapshot_key(7, 5)}


@pytest.mark.asyncio
async def test_p5_a_same_key_conflict_is_loud_and_never_overwrites(db, redis):
    db.add_markets(OPENAI_IPO, slug="ai")
    await _assemble()
    n = db.revision("ai")
    # Pre-seed N+1 (what the next membership change will allocate) with other bytes.
    db.add_markets(CLAUDE_6, slug="ai")
    key = ta.snapshot_key(db.container_id("ai"), n + 1)
    redis.store[key] = b'{"someone":"else"}'
    redis.log.clear()

    report = await _assemble()

    ai = _container(report, "ai")
    assert ai["snapshot"] == "publication_conflict"
    assert redis.store[key] == b'{"someone":"else"}'
    assert all(e[2] is True for e in redis.log if e[0] == "SET")  # never a SET without NX
    assert not any(e[0] in ("SETEX", "DEL", "EXPIRE") for e in redis.log)
    assert report["terminal"] == "failed" and report["reason"] == "publication_conflict"


def test_p5_pure_conflict_and_vanished_key():
    client = _FakeRedis()
    client.store[ta.snapshot_key(7, 4)] = b"other"
    assert ta.publish_snapshot(client, _snapshot()) == "publication_conflict"
    assert client.store[ta.snapshot_key(7, 4)] == b"other"

    class Vanishing(_FakeRedis):
        def set(self, *a, **k):
            super().set(*a, **k)
            return None  # refused, and then nothing is there

        def get(self, key):
            return None

    assert ta.publish_snapshot(Vanishing(), _snapshot()) == "write_failed"

    class Broken:
        def set(self, *a, **k):
            raise ConnectionError("down")

    assert ta.publish_snapshot(Broken(), _snapshot()) == "write_failed"
    assert ta.publish_snapshot(None, _snapshot()) == "write_failed"


@pytest.mark.asyncio
async def test_p6_a_rollback_before_commit_publishes_nothing(db, redis, monkeypatch):
    db.add_markets(OPENAI_IPO, slug="ai")
    real_write = ta._write_decisions

    async def boom(*args, **kwargs):
        await real_write(*args, **kwargs)
        raise RuntimeError("decision write failed")

    monkeypatch.setattr(ta, "_write_decisions", boom)
    report = await _assemble()

    assert _container(report, "ai")["terminal"] == "failed"
    assert redis.writes() == []
    assert db.state["containers"] == {}  # the container insert rolled back with the rest
    assert db.state["edges"] == {} and db.state["decisions"] == {}


@pytest.mark.asyncio
async def test_a_redis_read_error_is_absent_and_a_write_error_is_reported(db, monkeypatch):
    class Down:
        def get(self, key):
            raise ConnectionError("down")

        def set(self, *a, **k):
            raise ConnectionError("down")

    monkeypatch.setattr(ta, "_redis_client", lambda: Down())
    db.add_markets(OPENAI_IPO, slug="ai")
    await _assemble()
    n = db.revision("ai")

    report = _container(await _assemble(), "ai")

    assert report["revision_reason"] == "snapshot_absent" and db.revision("ai") == n + 1
    assert report["snapshot"] == "write_failed"
    assert report["terminal"] == "partial" and report["reason"] == "snapshot_write_failed"


# ---------------------------------------------------------------------------
# choose_revision, build_snapshot, the verdict
# ---------------------------------------------------------------------------


def test_choose_revision_reasons_in_order():
    snap = _snapshot()
    payload = snap.payload()
    assert ta.choose_revision(membership_changed=True, stored=payload,
                              candidate_at_current=snap) == (True, "membership_changed")
    assert ta.choose_revision(membership_changed=False, stored=None,
                              candidate_at_current=snap) == (True, "snapshot_absent")
    assert ta.choose_revision(membership_changed=False, stored=payload + b" ",
                              candidate_at_current=snap) == (True, "content_changed")
    assert ta.choose_revision(membership_changed=False, stored=payload.decode(),
                              candidate_at_current=snap) == (False, "identical")
    assert ta.REVISION_REASONS == ("membership_changed", "snapshot_absent",
                                   "content_changed", "identical")


def test_a_missing_row_is_withheld_and_the_bytes_are_canonical():
    snap = ta.build_snapshot({"id": 7, "slug": "ai", "name": "AI"}, 2,
                             {OPENAI_IPO.id: "side_question", 42: "side_question"},
                             {OPENAI_IPO.id: OPENAI_IPO}, inventory_complete=True)
    assert snap.withheld["row_missing"] == (42,)
    assert snap.shown_ids == (OPENAI_IPO.id,) and snap.eligible_count == 2
    text = snap.to_json()
    assert text == json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"))
    assert set(json.loads(text)["withheld"]) == set(ta.SNAPSHOT_WITHHOLDS)


@pytest.mark.asyncio
async def test_zero_decided_on_a_complete_pass_is_loud(db, redis):
    report = await _assemble()
    ai = _container(report, "ai")
    assert ai["decided"] == 0 and ai["inventory_complete"] is True
    assert (ai["terminal"], ai["reason"]) == ("failed", "zero_decided")
    assert report["terminal"] == "failed"


@pytest.mark.asyncio
async def test_the_verdict_carries_every_contract_field(db, redis):
    db.add_markets(OPENAI_IPO, slug="ai")
    report = await _assemble()
    ai = _container(report, "ai")
    for field in ("slug", "container_id", "inventory_complete", "decided", "admitted", "excluded",
                  "withheld", "edges_upserted", "edges_deleted", "revision_before",
                  "revision_after", "bumped", "revision_reason", "snapshot"):
        assert field in ai, field
    assert ai["revision_reason"] in ta.REVISION_REASONS
    assert ai["snapshot"] in ta.PUBLICATION_OUTCOMES
    assert report["terminal"] == "complete"


@pytest.mark.asyncio
async def test_the_container_row_is_created_once_and_never_updated(db, redis):
    db.add_markets(PM_BEST_PICTURE, slug="oscars-2027")
    await _assemble(only="oscars-2027")
    cid = db.container_id("oscars-2027")
    row = db.state["containers"][cid]
    assert (row["kind"], row["category"], row["name"]) == ("award_show", "awards", "Oscars 2027")
    assert row["window_end"] == OSCARS_2027.edition_backstop
    row["name"] = "Edited by a human"

    await _assemble(only="oscars-2027")

    assert db.state["containers"][cid]["name"] == "Edited by a human"
    assert len(db.state["containers"]) == 1
