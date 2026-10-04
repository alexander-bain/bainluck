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
            # (cid, child_type, child_id, action, revision), append-only; a
            # publication row has child_type and child_id None
            "ledger": [],
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

    def _correct(self, slug, child_type, child_id, action):
        """A correction: bump and a ledger row carrying the NEW revision, together."""
        cid = self.container_id(slug)
        self.state["containers"][cid]["revision"] += 1
        revision = self.state["containers"][cid]["revision"]
        self.state["ledger"].append((cid, child_type, child_id, action, revision))
        return revision

    def withdraw(self, slug, child_id):
        """``container_corrections._member_correction``'s effect, committed."""
        self.state["edges"].pop((self.container_id(slug), child_id), None)
        return self._correct(slug, "market", child_id, "withdraw")

    def readmit(self, slug, child_id):
        """Writes no edge: the next pass re-proves the member."""
        return self._correct(slug, "market", child_id, "readmit")

    def publish(self, slug):
        return self._correct(slug, None, None, "publish")

    def bump(self, slug):
        """An ancestor or ``container_assembly`` bump: a revision, no ledger row."""
        cid = self.container_id(slug)
        self.state["containers"][cid]["revision"] += 1
        return self.state["containers"][cid]["revision"]

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
        if sql.startswith("SELECT DISTINCT revision FROM container_corrections"):
            return _Result(sorted({(rev,) for cid, _t, _c, _a, rev in w["ledger"]
                                   if cid == params["cid"]
                                   and params["floor"] < rev <= params["top"]}))
        if "FROM container_corrections" in sql:
            assert "scope = 'member'" in sql
            latest = {}
            for cid, ctype, child, action, _rev in w["ledger"]:
                if cid == params["cid"] and ctype is not None:
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
    # v3.5: the fold input is shaped by the card's own helpers, never copies
    from app.utils import futures_market_snapshot, outcome_display

    assert ta.drop_dominant_field_outcomes is outcome_display.drop_dominant_field_outcomes
    assert ta.outcome_prints_a_price is futures_market_snapshot.outcome_prints_a_price
    assert ta.CARD_PRICE_AGE_LEG_COUNT is futures_market_snapshot.CARD_PRICE_AGE_LEG_COUNT


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
# Case 19 — two venues, one question: two members, one shown. Unmocked, on
# #8387's own fixture: production's two Best Picture rows (6173044 Kalshi,
# 57313556 Polymarket) with their stored dates and priced legs. The fold and the
# matcher both run for real; nothing here stands in for either.
# ---------------------------------------------------------------------------

from tests.test_discover_awards_best_picture_twice_8387 import (  # noqa: E402
    _bundle_members as _awards_members_8387,
)


def _fixture_row(data, **changes):
    """One 8387 fixture member as the plain row ``member_row`` would copy."""
    kalshi = data["source"] == "kalshi"
    row = ta.MemberRow(
        id=data["id"],
        name=data["name"],
        source=data["source"],
        external_id="KXOSCARPIC-27" if kalshi else f"PM-{data['id']}",
        status="open",
        llm_sport_category=data["llm_sport_category"],
        resolution_date=datetime.fromisoformat(data["resolution_date"]),
        outcomes=tuple(ta.OutcomeRow(o["name"], None, None, o["probability"], o["id"])
                       for o in data["top_outcomes"]),
    )
    return dataclasses.replace(row, **changes)


def _awards_rows():
    return {m["data"]["id"]: _fixture_row(m["data"]) for m in _awards_members_8387()}


KALSHI_PICTURE_ID, PM_PICTURE_ID = 6173044, 57313556
# The other Oscars categories in the same served bundle; the film leads two of them.
PM_ADAPTED_ID, PM_CINEMATOGRAPHY_ID = 58495122, 58495124


def _oscars_snapshot(rows, ids):
    return ta.build_snapshot({"id": 7, "slug": "oscars-2027", "name": "Oscars 2027"}, 1,
                             {i: "title" for i in ids}, rows, inventory_complete=True)


@pytest.mark.asyncio
async def test_case_19_a_cross_venue_pair_is_two_members_and_one_shown_question(db, redis):
    rows = _awards_rows()
    db.add_markets(rows[KALSHI_PICTURE_ID], rows[PM_PICTURE_ID], PM_NOMINATIONS,
                   slug="oscars-2027")

    await _assemble(only="oscars-2027")

    assert db.theme_edges("oscars-2027") == {
        KALSHI_PICTURE_ID: "title",
        PM_PICTURE_ID: "title",
        PM_NOMINATIONS.id: "advancement",
    }
    assert len(db.state["decisions"]) == 3
    snap = _stored(redis, db, "oscars-2027")
    # page order is (class rank, id): both titles before the advancement row, so
    # the better-placed Kalshi title survives, Polymarket's folds, and the
    # nominations question (a different question) stays on the page
    assert snap["shown_ids"] == [KALSHI_PICTURE_ID, PM_NOMINATIONS.id]
    assert snap["folded_ids"] == [PM_PICTURE_ID]
    assert snap["shown_count"] == 2 and snap["eligible_count"] == 3


def test_case_19_the_fold_reads_what_discovers_own_fixture_reads():
    """``fold_input`` hands the fold the fields #8387's served rows carried, so
    the comparison titles are the ones Discover's own test proves fold."""
    served = {m["data"]["id"]: m["data"] for m in _awards_members_8387()}
    rows = _awards_rows()
    from app.utils.discover_bundles import _comparison_title

    for a, b in ((KALSHI_PICTURE_ID, PM_PICTURE_ID), (PM_PICTURE_ID, KALSHI_PICTURE_ID)):
        mine = ta.fold_input(rows[a]), ta.fold_input(rows[b])
        assert _comparison_title(*mine) == _comparison_title(served[a], served[b])
    poly = ta.fold_input(rows[PM_PICTURE_ID])
    assert poly["resolution_date"] == "2027-07-01T03:59:00+00:00"
    # the legs are the served legs, field for field: {id, name, probability, rank}
    assert poly["top_outcomes"] == served[PM_PICTURE_ID]["top_outcomes"]
    assert ta.fold_input(rows[KALSHI_PICTURE_ID])["top_outcomes"] == (
        served[KALSHI_PICTURE_ID]["top_outcomes"])


def test_case_19_the_oscars_categories_the_film_also_leads_stay():
    rows = _awards_rows()
    ids = (KALSHI_PICTURE_ID, PM_PICTURE_ID, PM_ADAPTED_ID, PM_CINEMATOGRAPHY_ID)
    snap = _oscars_snapshot(rows, ids)
    assert snap.folded_ids == (PM_PICTURE_ID,)
    assert snap.shown_ids == (KALSHI_PICTURE_ID, PM_ADAPTED_ID, PM_CINEMATOGRAPHY_ID)


def test_case_19_the_page_split_is_exactly_discovers_fold():
    """Whatever the fold decides, the snapshot carries it unchanged: shown +
    folded partition the eligible members in page order."""
    rows = {**_awards_rows(), PM_NOMINATIONS.id: PM_NOMINATIONS}
    ids = (KALSHI_PICTURE_ID, PM_PICTURE_ID, PM_CINEMATOGRAPHY_ID, PM_NOMINATIONS.id)
    snap = _oscars_snapshot(rows, ids)
    items = [{"type": "futures", "data": ta.fold_input(rows[i])} for i in sorted(ids)]
    kept, folded = discover_bundles._dedupe_same_question_members(items)
    assert snap.shown_ids == tuple(i["data"]["id"] for i in kept)
    assert snap.folded_ids == tuple(i["data"]["id"] for i in folded)
    assert sorted(snap.shown_ids + snap.folded_ids) == sorted(ids)


# The refusals: each takes one piece of the context away, or changes it to
# what a different question would carry, and the pair must stay two rows.


def _pair_with(**poly_changes):
    rows = _awards_rows()
    rows[PM_PICTURE_ID] = dataclasses.replace(rows[PM_PICTURE_ID], **poly_changes)
    return _oscars_snapshot(rows, (KALSHI_PICTURE_ID, PM_PICTURE_ID))


def test_case_19_a_row_without_a_resolution_date_is_not_folded():
    snap = _pair_with(resolution_date=None)
    assert snap.folded_ids == () and snap.shown_ids == (KALSHI_PICTURE_ID, PM_PICTURE_ID)


def test_case_19_a_row_without_prices_is_not_folded():
    """An unpriced leg stays None — not a dummy number — so a row with no
    prices gives the field arm nothing to agree on."""
    unpriced = tuple(dataclasses.replace(o, current_probability=None)
                     for o in _awards_rows()[PM_PICTURE_ID].outcomes)
    snap = _pair_with(outcomes=unpriced)
    assert all(o["probability"] is None
               for o in ta.fold_input(dataclasses.replace(
                   _awards_rows()[PM_PICTURE_ID], outcomes=unpriced))["top_outcomes"])
    assert snap.folded_ids == ()


def test_case_19_a_field_led_by_a_different_film_is_not_folded():
    legs = list(_awards_rows()[PM_PICTURE_ID].outcomes)
    legs[0] = dataclasses.replace(legs[0], current_probability=0.1)  # La Bola Negra now leads
    assert _pair_with(outcomes=tuple(legs)).folded_ids == ()


def test_case_19_next_years_ceremony_is_not_folded_onto_this_years():
    """Kalshi's undated title for the NEXT ceremony beside Polymarket's dated
    2027 one: the same title, the same leader, a different edition."""
    rows = _awards_rows()
    rows[KALSHI_PICTURE_ID] = dataclasses.replace(
        rows[KALSHI_PICTURE_ID], resolution_date=datetime(2028, 12, 31, 15, tzinfo=timezone.utc))
    snap = _oscars_snapshot(rows, (KALSHI_PICTURE_ID, PM_PICTURE_ID))
    assert snap.folded_ids == () and snap.shown_count == 2


def test_case_19_winner_and_nominations_stay_two_questions():
    rows = {**_awards_rows(), PM_NOMINATIONS.id: PM_NOMINATIONS}
    snap = _oscars_snapshot(rows, (KALSHI_PICTURE_ID, PM_NOMINATIONS.id))
    assert snap.folded_ids == ()


def test_member_row_copies_the_stored_price_and_keeps_absent_absent():
    """``outcome_prints_a_price`` decides: a stored 0.0 is a price, NULL is None.
    Legs copy in id order so a tie at the three-leg cut is stable."""
    from decimal import Decimal
    from types import SimpleNamespace

    legs = [SimpleNamespace(id=3, name="C", is_winner=None, resolution_source=None,
                            current_probability=None),
            SimpleNamespace(id=1, name="A", is_winner=None, resolution_source=None,
                            current_probability=Decimal("0.3774")),
            SimpleNamespace(id=2, name="B", is_winner=None, resolution_source=None,
                            current_probability=Decimal("0"))]
    market = SimpleNamespace(id=9, name="Q", source="kalshi", external_id="K", status="open",
                             llm_sport_category="entertainment", outcomes=legs,
                             resolution_date=datetime(2027, 12, 31, 15, tzinfo=timezone.utc))
    row = ta.member_row(market)
    assert [(o.id, o.name, o.current_probability) for o in row.outcomes] == [
        (1, "A", 0.3774), (2, "B", 0.0), (3, "C", None)]
    assert all(type(o.current_probability) in (float, type(None)) for o in row.outcomes)
    folded_in = ta.fold_input(row)
    assert folded_in["resolution_date"] == "2027-12-31T15:00:00+00:00"
    assert folded_in["top_outcomes"] == [
        {"id": 1, "name": "A", "probability": 0.3774, "rank": 1},
        {"id": 2, "name": "B", "probability": 0.0, "rank": 2},
        {"id": 3, "name": "C", "probability": None, "rank": 3},
    ]
    assert ta.fold_input(dataclasses.replace(row, resolution_date=None))["resolution_date"] is None


def test_fold_input_orders_the_legs_as_the_card_does_and_cuts_at_three():
    """Stored price descending, NULL last, then outcome id; three legs — the
    card's order, whatever order the rows were loaded in."""
    legs = tuple(ta.OutcomeRow(n, None, None, p, i) for i, n, p in
                 ((4, "Hamnet", 0.05), (1, "Unpriced", None), (5, "Dune: Part Three", 0.11),
                  (3, "The Odyssey", 0.49)))
    row = dataclasses.replace(_awards_rows()[PM_PICTURE_ID], outcomes=legs)
    assert [(o["id"], o["name"], o["rank"]) for o in ta.fold_input(row)["top_outcomes"]] == [
        (3, "The Odyssey", 1), (5, "Dune: Part Three", 2), (4, "Hamnet", 3)]


def test_fold_input_breaks_a_price_tie_by_outcome_id_and_unpriced_legs_by_id():
    legs = tuple(ta.OutcomeRow(n, None, None, p, i) for i, n, p in
                 ((9, "Later tie", 0.2), (2, "Null B", None), (7, "Earlier tie", 0.2),
                  (1, "Null A", None)))
    row = dataclasses.replace(_awards_rows()[PM_PICTURE_ID], outcomes=legs)
    assert [o["id"] for o in ta.fold_input(row)["top_outcomes"]] == [7, 9, 1]
    only_unpriced = dataclasses.replace(row, outcomes=legs[1::2])
    assert [o["id"] for o in ta.fold_input(only_unpriced)["top_outcomes"]] == [1, 2]


def test_fold_input_drops_the_dominant_field_leg_before_the_cut():
    """A no-bid ``Other`` at 1.0 never takes a card slot (UX-P163): the card's
    helper removes it before the three-leg cut, so the fold sees the real legs."""
    legs = tuple(ta.OutcomeRow(n, None, None, p, i) for i, n, p in
                 ((1, "Other", 1.0), (2, "The Odyssey", 0.49), (3, "La Bola Negra", 0.315),
                  (4, "Dune: Part Three", 0.115)))
    row = dataclasses.replace(_awards_rows()[PM_PICTURE_ID], outcomes=legs)
    assert [o["name"] for o in ta.fold_input(row)["top_outcomes"]] == [
        "The Odyssey", "La Bola Negra", "Dune: Part Three"]


# ---------------------------------------------------------------------------
# Cases 20 / 21 at plan level
# ---------------------------------------------------------------------------


def _md(child_id, outcome="admitted", reason="admitted_entity_signal", edge_class="side_question",
        withdrawn=False, rule="ai-subject@2"):
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
    truncated = ta.plan_container_pass([_md(1)], current, inventory_complete=False,
                                       row_absent={2}, rule_version="ai-subject@2")
    assert truncated.edge_deletes == () and not truncated.membership_changed
    assert truncated.receipt["carried_unseen"] == 1

    # #9936 B: a complete pass retires an undecided member only on OBSERVED absence
    complete = ta.plan_container_pass([_md(1)], current, inventory_complete=True,
                                      row_absent={2}, rule_version="ai-subject@2")
    assert complete.edge_deletes == (2,) and complete.membership_changed
    unobserved = ta.plan_container_pass([_md(1)], current, inventory_complete=True,
                                        rule_version="ai-subject@2")
    assert unobserved.edge_deletes == () and not unobserved.membership_changed
    assert unobserved.receipt["carried_unseen"] == 1


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
async def test_p6_the_payload_is_serialized_before_commit(db, redis, monkeypatch):
    """Semantics 9: a page that cannot be serialized commits nothing — not a
    revision, an edge or a decision row that no snapshot will ever describe."""
    db.add_markets(OPENAI_IPO, slug="ai")

    def unserializable(self):
        raise TypeError("not JSON serializable")

    monkeypatch.setattr(ta.ThemeSnapshot, "payload", unserializable)
    report = await _assemble()

    assert _container(report, "ai")["terminal"] == "failed"
    assert redis.writes() == []
    assert db.state["containers"] == {}
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


# ---------------------------------------------------------------------------
# #9936 A — a rebuild carries the completeness the corrections since prove
# ---------------------------------------------------------------------------


async def _rebuild(db, slug="ai"):
    report = await ta._run_rebuild_theme_snapshot(db.container_id(slug))
    return report["containers"][0]


@pytest.mark.asyncio
async def test_9936_a1_a_withdrawal_no_longer_costs_a_second_bump(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    r = db.revision("ai")
    db.withdraw("ai", CLAUDE_6.id)

    rebuilt = await _rebuild(db)
    assert rebuilt["inventory_complete"] is True
    assert rebuilt["completeness_basis"] == {"revision": r, "corrections_since": 1}
    assert "completeness_unproven" not in rebuilt
    assert _stored(redis, db, "ai")["inventory_complete"] is True
    after_rebuild = db.revision("ai")
    assert after_rebuild == r + 2  # the correction, then the rebuild's one bump

    # the next pass changes nothing, so a reader paging this revision stays put
    report = _container(await _assemble(), "ai")
    assert (report["bumped"], report["revision_reason"]) == (False, "identical")
    assert db.revision("ai") == after_rebuild


@pytest.mark.asyncio
async def test_9936_a2_a_zero_decision_incomplete_pass_is_the_basis_not_the_ledger_max(
    db, redis, monkeypatch
):
    """Root's counterexample: an incomplete pass that decided nothing publishes
    False at R+1 and leaves the decisions' MAX(revision) at R. A rebuild that
    read the decision ledger would claim R's True."""
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    r = db.revision("ai")

    ticks = iter([0] + [10_000] * 50)  # out of budget before the first page
    monkeypatch.setattr(ta, "_monotonic", lambda: next(ticks))
    starved = _container(await _assemble(), "ai")
    monkeypatch.setattr(ta, "_monotonic", __import__("time").monotonic)
    assert starved["decided"] == 0 and starved["inventory_complete"] is False
    assert (starved["revision_reason"], db.revision("ai")) == ("content_changed", r + 1)
    assert _stored(redis, db, "ai")["inventory_complete"] is False
    assert max(d["revision"] for d in db.state["decisions"].values()) == r  # the trap

    db.withdraw("ai", CLAUDE_6.id)
    rebuilt = await _rebuild(db)
    assert rebuilt["inventory_complete"] is False
    assert rebuilt["completeness_basis"] == {"revision": r + 1, "corrections_since": 1}


@pytest.mark.asyncio
async def test_9936_a3_a4_a_run_of_corrections_and_a_second_rebuild_bump_once(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, GPT_6, slug="ai")
    await _assemble()
    p = db.revision("ai")
    db.withdraw("ai", CLAUDE_6.id)
    db.withdraw("ai", GPT_6.id)  # a run of two, however they were committed

    first = await _rebuild(db)
    assert first["completeness_basis"] == {"revision": p, "corrections_since": 2}
    assert (first["bumped"], first["inventory_complete"]) == (True, True)
    assert db.revision("ai") == p + 3

    # the second rebuild those corrections sent: the live revision is the first
    # rebuild's (not a correction), its page carries the same claim, nothing moves
    second = await _rebuild(db)
    assert second["completeness_basis"] == {"revision": p + 3, "corrections_since": 0}
    assert (second["bumped"], second["revision_reason"]) == (False, "identical")
    assert db.revision("ai") == p + 3


@pytest.mark.asyncio
async def test_9936_a3_interleaved_corrections_and_rebuilds_each_carry(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, GPT_6, slug="ai")
    await _assemble()
    db.withdraw("ai", CLAUDE_6.id)
    one = await _rebuild(db)
    db.withdraw("ai", GPT_6.id)
    two = await _rebuild(db)  # A11: the basis is the first rebuild's page
    assert one["inventory_complete"] is two["inventory_complete"] is True
    assert two["completeness_basis"] == {"revision": one["revision_after"],
                                         "corrections_since": 1}


@pytest.mark.parametrize(
    "raw,why",
    [
        (None, "snapshot_absent"),
        (b"\xff\xfe", "snapshot_invalid"),
        (b"not json", "snapshot_invalid"),
        (b"[1, 2]", "snapshot_invalid"),
        (json.dumps({"container_id": 7, "revision": 5, "inventory_complete": True}).encode(),
         "snapshot_invalid"),  # a different revision
        (json.dumps({"container_id": 8, "revision": 4, "inventory_complete": True}).encode(),
         "snapshot_invalid"),  # a different container
        (json.dumps({"container_id": 7, "revision": 4, "inventory_complete": 1}).encode(),
         "snapshot_invalid"),  # not a bool
        (json.dumps({"container_id": 7, "revision": 4}).encode(), "snapshot_invalid"),
    ],
)
def test_9936_a5_only_a_validated_exact_page_is_carried(raw, why):
    assert ta.carried_completeness(raw, container_id=7, revision=4) == (None, why)
    ok = json.dumps({"container_id": 7, "revision": 4, "inventory_complete": True}).encode()
    assert ta.carried_completeness(ok, container_id=7, revision=4) == (True, None)
    assert ta.carried_completeness(ok.decode(), container_id=7, revision=4) == (True, None)


@pytest.mark.parametrize("field", ["container_id", "revision"])
def test_9936_a5_a_bool_is_never_an_id_even_where_it_equals_one(field):
    """``True == 1`` in Python, so only a type check refuses it."""
    snap = {"container_id": 1, "revision": 1, "inventory_complete": True}
    assert ta.carried_completeness(json.dumps(snap), container_id=1, revision=1) == (True, None)
    snap[field] = True
    assert ta.carried_completeness(json.dumps(snap), container_id=1, revision=1) == (
        None, "snapshot_invalid")


@pytest.mark.asyncio
async def test_9936_a5_the_basis_page_evicted_is_false(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    r = db.revision("ai")
    redis.store.pop(ta.snapshot_key(db.container_id("ai"), r))
    db.withdraw("ai", CLAUDE_6.id)
    rebuilt = await _rebuild(db)
    assert rebuilt["inventory_complete"] is False
    assert rebuilt["completeness_unproven"] == "snapshot_absent"
    assert "completeness_basis" not in rebuilt


@pytest.mark.asyncio
async def test_9936_a6_a_bump_with_no_ledger_row_stops_the_walk(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    db.bump("ai")  # an ancestor-shaped bump: a revision nobody published
    db.withdraw("ai", CLAUDE_6.id)
    rebuilt = await _rebuild(db)
    assert rebuilt["inventory_complete"] is False
    assert rebuilt["completeness_unproven"] == "snapshot_absent"


@pytest.mark.asyncio
async def test_9936_a7_a_run_as_long_as_the_bound_proves_nothing(db, redis, monkeypatch):
    monkeypatch.setattr(ta, "_LINEAGE_MAX", 3)
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    r = db.revision("ai")
    db.withdraw("ai", CLAUDE_6.id)
    db.readmit("ai", CLAUDE_6.id)
    inside = await ta._completeness_from_lineage(db.session(), redis, db.container_id("ai"),
                                                 db.revision("ai"))
    assert inside == (True, {"completeness_basis": {"revision": r, "corrections_since": 2}})

    db.withdraw("ai", CLAUDE_6.id)  # three corrections: the walk reaches the floor
    rebuilt = await _rebuild(db)
    assert rebuilt["inventory_complete"] is False
    assert rebuilt["completeness_unproven"] == "bound"


@pytest.mark.asyncio
async def test_9936_a8_a_correction_on_a_never_produced_container_is_false(db, redis):
    db.state["containers"][7] = {"id": 7, "slug": "ai", "name": "AI", "revision": 0}
    db.publish("ai")
    rebuilt = await _rebuild(db)
    assert rebuilt["inventory_complete"] is False
    assert rebuilt["completeness_unproven"] == "no_producer_revision"


@pytest.mark.asyncio
async def test_9936_a9_readmit_and_publication_corrections_carry(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    db.withdraw("ai", CLAUDE_6.id)
    await _rebuild(db)
    for correct in (lambda: db.readmit("ai", CLAUDE_6.id), lambda: db.publish("ai")):
        correct()
        rebuilt = await _rebuild(db)
        assert rebuilt["inventory_complete"] is True
        assert rebuilt["completeness_basis"]["corrections_since"] == 1


@pytest.mark.asyncio
async def test_9936_a10_a_committed_pass_whose_page_has_not_landed_is_false(
    db, redis, monkeypatch
):
    db.add_markets(OPENAI_IPO, slug="ai")
    await _assemble()
    db.add_markets(CLAUDE_6, slug="ai")
    real_publish = ta.publish_snapshot
    monkeypatch.setattr(ta, "publish_snapshot", lambda client, snap: "written")  # held back
    await _assemble()  # complete, committed at R+1, its key never set
    monkeypatch.setattr(ta, "publish_snapshot", real_publish)
    db.withdraw("ai", CLAUDE_6.id)
    rebuilt = await _rebuild(db)
    assert rebuilt["inventory_complete"] is False  # never True in the gap
    assert rebuilt["completeness_unproven"] == "snapshot_absent"


@pytest.mark.asyncio
async def test_9936_a_the_lineage_is_one_read_and_one_get(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    r = db.revision("ai")
    db.withdraw("ai", CLAUDE_6.id)
    db.statements.clear()
    redis.log.clear()
    await ta._completeness_from_lineage(db.session(), redis, db.container_id("ai"),
                                        db.revision("ai"))
    assert [s for s, _ in db.statements] == [ta._SELECT_CORRECTION_REVISIONS]
    assert redis.log == [("GET", ta.snapshot_key(db.container_id("ai"), r))]
    assert "container_member_decisions" not in ta._SELECT_CORRECTION_REVISIONS


# ---------------------------------------------------------------------------
# #9936 B — retirement on observed absence; the receipt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_9936_b1_a_complete_pass_retires_a_vanished_row_with_evidence(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    db.population["ai"].discard(CLAUDE_6.id)
    db.markets.pop(CLAUDE_6.id)

    report = _container(await _assemble(), "ai")

    assert CLAUDE_6.id not in db.theme_edges("ai")
    row = db.decision("ai", CLAUDE_6.id)
    assert (row["outcome"], row["reason"], row["rule_version"]) == (
        "excluded", "member_row_absent", "ai-subject@2")
    assert row["evidence"] == {"local_row": "absent", "observed_by": "prior_decision_arm",
                               "edge_class": "side_question"}
    assert report["receipt"]["retired"] == {"member_row_absent": 1}
    assert report["excluded"] == {"member_row_absent": 1}


@pytest.mark.asyncio
async def test_9936_b2_a_truncated_pass_carries_a_vanished_row(db, redis, monkeypatch):
    db.add_markets(OPENAI_IPO, CLAUDE_6, GPT_6, slug="ai")
    await _assemble()
    db.population["ai"].discard(OPENAI_IPO.id)
    db.markets.pop(OPENAI_IPO.id)  # the lowest id: the first page observes it absent

    ticks = iter([0, 0, 0, 0] + [10_000] * 50)  # three one-id pages, then over budget
    monkeypatch.setattr(ta, "_monotonic", lambda: next(ticks))
    monkeypatch.setattr(ta, "GATHER_PAGE", 1)
    report = _container(await _assemble(), "ai")

    assert report["inventory_complete"] is False
    assert OPENAI_IPO.id in db.theme_edges("ai")
    assert db.decision("ai", OPENAI_IPO.id)["reason"] == "admitted_entity_signal"
    assert report["receipt"]["carried_unseen"] == 1 and report["receipt"]["retired"] == {}


@pytest.mark.asyncio
async def test_9936_b3_a_member_never_gathered_is_kept_not_retired(db, redis):
    """Strawman on the code before #9936: the complete pass deleted it."""
    db.add_markets(OPENAI_IPO, slug="ai")
    await _assemble()
    cid = db.container_id("ai")
    db.state["edges"][(cid, 555)] = {"class": "side_question", "source": "theme_rule"}

    report = _container(await _assemble(), "ai")

    assert 555 in db.theme_edges("ai")
    assert (cid, 555) not in db.state["decisions"]
    assert report["receipt"]["carried_unseen"] == 1


def _receipt_holds(r):
    assert r["prior_members"] == r["retained"] + sum(r["retired"].values()) + r["carried_unseen"]
    assert r["members_after"] == r["retained"] + r["added"] + r["carried_unseen"]


def test_9936_b4_the_receipt_separates_prior_members_arrivals_and_withdrawals():
    current = {1: "side_question", 2: "side_question", 3: "side_question",
               4: "side_question", 5: "side_question", 6: "side_question"}
    plan = ta.plan_container_pass(
        [
            _md(1),  # steady
            _md(2, edge_class="title"),  # reclassified
            _md(3, outcome="excluded", reason="not_this_subject"),  # rule exclusion
            _md(4, withdrawn=True),  # a standing withdrawal (edge somehow present)
            _md(7),  # arrival
            _md(8, withdrawn=True),  # withdrawn, holds nothing
            _md(9),  # admitted, slot held by another source
            _md(6, outcome="excluded", reason="resolved_settle_time_unknown"),  # retained
        ],
        current,
        inventory_complete=True,
        foreign_held={9},
        row_absent={5},
        rule_version="ai-subject@2",
    )
    r = plan.receipt
    assert r == {
        "rule_version": "ai-subject@2",
        "prior_members": 6,
        "added": 1,
        "retained": 3,
        "reclassified": 1,
        "retained_settle_time_pending": 1,
        "held_by_other_source": 1,
        "withdrawn": 2,
        "retired": {"container_member_withdrawn": 1, "member_row_absent": 1,
                    "not_this_subject": 1},
        "carried_unseen": 0,
        "members_after": 4,
    }
    _receipt_holds(r)
    assert sorted(plan.edge_deletes) == [3, 4, 5]
    assert (7, "side_question") in plan.edge_upserts and (2, "title") in plan.edge_upserts
    assert not any(c == 9 for c, _ in plan.edge_upserts)


@pytest.mark.asyncio
async def test_9936_b4_a_dry_run_receipt_is_the_apply_receipt(db, redis, monkeypatch):
    db.add_markets(OPENAI_IPO, CLAUDE_6, GPT_6, slug="ai")
    await _assemble()
    db.add_markets(_row(70000002, "Will Anthropic release Claude 7 in 2027?"), slug="ai")
    db.population["ai"].discard(GPT_6.id)
    db.markets.pop(GPT_6.id)
    db.withdraw("ai", CLAUDE_6.id)

    dry = _container(await _assemble(apply=False), "ai")
    applied = _container(await _assemble(), "ai")

    assert dry["receipt"] == applied["receipt"]
    _receipt_holds(applied["receipt"])
    assert applied["receipt"]["added"] == 1
    assert applied["receipt"]["retired"] == {"member_row_absent": 1}
    assert applied["receipt"]["withdrawn"] == 1
    # an upsert of an existing edge is never an arrival
    rerun = _container(await _assemble(), "ai")
    assert rerun["receipt"]["added"] == 0 and rerun["receipt"]["retained"] == 2
    _receipt_holds(rerun["receipt"])


@pytest.mark.asyncio
async def test_9936_b4_a_raising_decide_carries_and_retires_nothing(db, redis, monkeypatch):
    db.add_markets(OPENAI_IPO, CLAUDE_6, GPT_6, slug="ai")
    await _assemble()
    db.population["ai"].discard(GPT_6.id)
    db.markets.pop(GPT_6.id)
    real = AI.decider

    def flaky(defn, market, *, now):
        if market.id == CLAUDE_6.id:
            raise RuntimeError("bad row")
        return real(defn, market, now=now)

    monkeypatch.setattr(ta, "REGISTRY", {"ai": dataclasses.replace(AI, decider=flaky)})
    report = _container(await _assemble(), "ai")
    assert report["inventory_complete"] is False
    assert report["receipt"]["retired"] == {} and report["receipt"]["carried_unseen"] == 2
    assert set(db.theme_edges("ai")) == {OPENAI_IPO.id, CLAUDE_6.id, GPT_6.id}


# ---------------------------------------------------------------------------
# #9936 C — a standing member stays while its settlement time is unknown
# ---------------------------------------------------------------------------


def _settles(row, *, settled_at=None, **changes):
    return dataclasses.replace(row, status="resolved", settled_at=settled_at, **changes)


@pytest.mark.asyncio
async def test_9936_c1_c3_a_member_that_settles_without_a_time_keeps_its_card(db, redis):
    """C3: on the code before #9936 this pass deleted the edge."""
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    n = db.revision("ai")
    assert CLAUDE_6.id in _stored(redis, db, "ai")["shown_ids"]

    db.population["ai"].discard(CLAUDE_6.id)  # neither status arm offers a NULL time
    db.markets[CLAUDE_6.id] = _settles(CLAUDE_6)
    report = _container(await _assemble(), "ai")

    assert db.theme_edges("ai")[CLAUDE_6.id] == "side_question"
    row = db.decision("ai", CLAUDE_6.id)
    assert (row["outcome"], row["reason"], row["rule_version"]) == (
        "admitted", "admitted_settle_time_pending", "ai-subject@2")
    assert row["evidence"]["retained_member"] == {"edge_class": "side_question"}
    rule = row["evidence"]["rule_decision"]
    assert (rule["outcome"], rule["reason"]) == ("excluded", "resolved_settle_time_unknown")
    assert CLAUDE_6.id in _stored(redis, db, "ai")["shown_ids"]
    assert (report["bumped"], db.revision("ai")) == (False, n)
    assert report["receipt"]["retained_settle_time_pending"] == 1


@pytest.mark.asyncio
async def test_9936_c2_the_clock_resumes_from_settled_at_when_it_arrives(db, redis):
    db.add_markets(CLAUDE_6, OPENAI_IPO, slug="ai")
    await _assemble()
    db.population["ai"].discard(CLAUDE_6.id)
    db.markets[CLAUDE_6.id] = _settles(CLAUDE_6)
    await _assemble()

    settled = NOW - timedelta(days=3)
    db.markets[CLAUDE_6.id] = _settles(CLAUDE_6, settled_at=settled)
    await _assemble()
    assert db.decision("ai", CLAUDE_6.id)["reason"] == "admitted_entity_signal"
    assert CLAUDE_6.id in db.theme_edges("ai")

    await _assemble(now=settled + timedelta(days=15))
    assert db.decision("ai", CLAUDE_6.id)["reason"] == "resolved_beyond_retention"
    assert CLAUDE_6.id not in db.theme_edges("ai")


@pytest.mark.asyncio
async def test_9936_c4_c5_an_unknown_time_row_is_never_newly_admitted(db, redis):
    fresh = _settles(_row(70000003, "Will OpenAI release GPT-7 in 2026?"))
    was_out = _settles(_row(70000004, "Will Anthropic release Claude 9 in 2026?"),
                       settled_at=NOW - timedelta(days=30))
    # gotcha #33: still status='open', but a graded sole winner reads settled
    open_settled = dataclasses.replace(
        _row(70000005, "Claude Sonnet 5 before July?", source="kalshi",
             external_id="KXCLAUDE-SONNET5", metadata={"shape": {"expected_winners": 1}}),
        outcomes=(ta.OutcomeRow("Yes", True, "kalshi"), ta.OutcomeRow("No", False, "kalshi")))
    db.add_markets(OPENAI_IPO, fresh, was_out, open_settled, slug="ai")
    await _assemble()
    assert db.decision("ai", was_out.id)["reason"] == "resolved_beyond_retention"

    db.markets[was_out.id] = dataclasses.replace(was_out, settled_at=None)
    await _assemble()

    for row in (fresh, was_out, open_settled):
        assert row.id not in db.theme_edges("ai")
        assert db.decision("ai", row.id)["reason"] == "resolved_settle_time_unknown"


@pytest.mark.asyncio
async def test_9936_c6_a_withdrawal_prevails_and_a_readmit_waits_for_the_time(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    db.markets[CLAUDE_6.id] = _settles(CLAUDE_6)
    db.withdraw("ai", CLAUDE_6.id)
    for _ in range(2):
        await _assemble()
        assert CLAUDE_6.id not in db.theme_edges("ai")
        assert db.decision("ai", CLAUDE_6.id)["reason"] == CONTAINER_MEMBER_WITHDRAWN

    db.readmit("ai", CLAUDE_6.id)  # writes no edge, so there is nothing to retain
    await _assemble()
    assert CLAUDE_6.id not in db.theme_edges("ai")
    assert db.decision("ai", CLAUDE_6.id)["reason"] == "resolved_settle_time_unknown"

    db.markets[CLAUDE_6.id] = _settles(CLAUDE_6, settled_at=NOW - timedelta(days=2))
    await _assemble()
    assert CLAUDE_6.id in db.theme_edges("ai")


@pytest.mark.asyncio
async def test_9936_c7_a_member_renamed_off_subject_retires(db, redis):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()
    db.markets[CLAUDE_6.id] = _settles(CLAUDE_6, name="Will it rain in Paris on Friday?")
    await _assemble()
    assert CLAUDE_6.id not in db.theme_edges("ai")
    assert db.decision("ai", CLAUDE_6.id)["reason"] == "not_this_subject"


@pytest.mark.asyncio
async def test_9936_c8_a_foreign_held_slot_is_excluded_and_untouched(db, redis):
    db.add_markets(OPENAI_IPO, slug="ai")
    await _assemble()
    cid = db.container_id("ai")
    db.state["edges"][(cid, CLAUDE_6.id)] = {"class": "prop", "source": "human"}
    db.add_markets(_settles(CLAUDE_6), slug="ai")
    await _assemble()
    assert db.state["edges"][(cid, CLAUDE_6.id)] == {"class": "prop", "source": "human"}
    assert db.decision("ai", CLAUDE_6.id)["reason"] == "resolved_settle_time_unknown"


def test_9936_c9_retention_needs_a_standing_theme_edge_and_no_withdrawal():
    unknown = dict(outcome="excluded", reason="resolved_settle_time_unknown")
    kept = ta.plan_container_pass([_md(1, **unknown)], {1: "title"}, inventory_complete=True)
    assert kept.edge_deletes == () and kept.edge_upserts == () and not kept.membership_changed
    assert kept.decision_rows[0]["reason"] == "admitted_settle_time_pending"
    assert kept.decision_rows[0]["evidence"]["retained_member"] == {"edge_class": "title"}

    withdrawn = ta.plan_container_pass([_md(1, withdrawn=True, **unknown)], {1: "title"},
                                       inventory_complete=True)
    assert withdrawn.edge_deletes == (1,)
    assert withdrawn.decision_rows[0]["reason"] == CONTAINER_MEMBER_WITHDRAWN

    stranger = ta.plan_container_pass([_md(1, **unknown)], {}, inventory_complete=True)
    assert stranger.edge_upserts == () and stranger.decision_rows[0]["outcome"] == "excluded"

    beyond = ta.plan_container_pass(
        [_md(1, outcome="excluded", reason="resolved_beyond_retention")], {1: "title"},
        inventory_complete=True)
    assert beyond.edge_deletes == (1,)
