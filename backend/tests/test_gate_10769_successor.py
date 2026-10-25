"""#10769 successor gate (`scripts/gate_10769_successor.py`): offline guards.

Each test names the wrong harness it kills. Nothing here touches a network or a
database; the plan fixtures under `fixtures/gate_10769_plans/` are real
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` output from a local PostgreSQL 14
scratch table whose btree indexes carry the production index NAMES. They pin plan
SHAPE (node types, aliases, nesting), not operator classes.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import gate_10769_successor as S  # noqa: E402
import gate_futures_open_trgm_index as G  # noqa: E402

from app.routes import events as ev  # noqa: E402

PLANS = os.path.join(HERE, "fixtures", "gate_10769_plans")
NOW = datetime(2026, 10, 25, 3, 18, tzinfo=timezone.utc)

#: Production-shaped `pg_indexes` rows for the classifier.
CATALOG = [
    ("futures_markets_pkey", "CREATE UNIQUE INDEX futures_markets_pkey ON public.futures_markets USING btree (id)"),
    ("ix_futures_name_trgm", "CREATE INDEX ix_futures_name_trgm ON public.futures_markets USING gin (name gin_trgm_ops)"),
    ("ix_futures_name_trgm_open", "CREATE INDEX ix_futures_name_trgm_open ON public.futures_markets USING gin (name gin_trgm_ops) WHERE ((status)::text = 'open'::text)"),
    ("ix_futures_name_fts_open", "CREATE INDEX ix_futures_name_fts_open ON public.futures_markets USING gin (to_tsvector('english'::regconfig, (COALESCE(name, ''::character varying))::text)) WHERE ((status)::text = 'open'::text)"),
    ("ix_futures_markets_status", "CREATE INDEX ix_futures_markets_status ON public.futures_markets USING btree (status)"),
    ("ix_fm_feed_open_volume", "CREATE INDEX ix_fm_feed_open_volume ON public.futures_markets USING btree (volume DESC) WHERE (((status)::text = 'open'::text) AND (volume > 0))"),
]
CLASSES = S.classify_catalog(CATALOG)


def plan(name: str) -> dict:
    with open(os.path.join(PLANS, f"{name}.json")) as fh:
        return {"plan": json.load(fh)}


def fp(*entries) -> list[dict]:
    return [{"node": n, "index": i, "alias": "futures_markets"} for n, i in entries]


BH = "Bitmap Heap Scan"


# --- route fidelity: the harness arm is the UNION member the route sends -------

def _result():
    r = MagicMock()
    r.scalars.return_value.all.return_value = []
    r.scalars.return_value.first.return_value = None
    r.scalar.return_value = 0
    r.scalar_one_or_none.return_value = None
    r.fetchall.return_value = []
    r.all.return_value = []
    r.first.return_value = None
    r.mappings.return_value.all.return_value = []
    return r


def _recording_db(seen: list):
    db = AsyncMock()

    async def execute(stmt, *a, **k):
        if hasattr(stmt, "compile") and not isinstance(stmt, str):
            try:
                sql = S.compile_sql(stmt)  # the SAME compile the harness uses
            except Exception:  # unbound text() etc.: not a pool read
                sql = ""
            if "futures_markets.resolution_date" in sql:
                seen.append(S.normalise(sql))
        return _result()

    db.execute = AsyncMock(side_effect=execute)
    return db


def _patches():
    rc = MagicMock()
    rc.get.return_value = None
    return (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch("app.routes.events._record_trending", new=MagicMock()),
        patch("app.routes.events._apply_search_statement_timeout", new=AsyncMock()),
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch("app.routes.events.folded_probability_sources_batch", new=AsyncMock(return_value={})),
    )


async def _route_sql(surface: str, q: str) -> list[str]:
    seen: list[str] = []
    p = _patches()
    with p[0], p[1], p[2], p[3], p[4], p[5]:
        if surface == "typeahead":
            request = MagicMock()
            request.headers = {}
            await ev.typeahead_search(
                q=q, debug_evidence=False, debug_timing=False,
                db=_recording_db(seen), request=request,
            )
        else:
            await ev.search_events(
                request=MagicMock(), response=MagicMock(), q=q, db=_recording_db(seen),
                sport=None, tags=None, page=1, per_page=25, days_back=30,
                include_upcoming=True, debug_timing=False, current_user=None,
            )
    assert seen, f"{surface} sent no futures pool read for {q!r} (vacuous)"
    return seen


def _member_text(stmt) -> str:
    """The whole member, `SELECT futures_markets.id FROM futures_markets WHERE ...`,
    normalised (timestamps, whitespace)."""
    return " ".join(S.normalise(S.compile_sql(stmt)).split())


#: A UNION member ends at the next `UNION`, at the `)` closing the UNION or the
#: `IN (...)`, or at the end. Anything else after it (` AND NOT (EXISTS ...`) means
#: the candidate is only a PREFIX of what the route sends -- e.g. a member that
#: dropped #4914's trailing anti-join.
_MEMBER_END = re.compile(r"(?:\s+UNION\b|\s*\)|\s*$)")


def _flat(sql: str) -> str:
    """Whitespace-collapsed, with the UNION subquery's output label removed: the
    route renders a member as `SELECT futures_markets.id AS id FROM ...`, the
    standalone member as `SELECT futures_markets.id FROM ...`. A column label
    changes the result's column NAME, never the rows or the plan."""
    return " ".join(sql.split()).replace(
        "SELECT futures_markets.id AS id FROM futures_markets WHERE",
        "SELECT futures_markets.id FROM futures_markets WHERE",
    )


def _sent(member: str, statements: list[str]) -> bool:
    for s in statements:
        flat = _flat(s)
        start = flat.find(member)
        while start != -1:
            if _MEMBER_END.match(flat, start + len(member)):
                return True
            start = flat.find(member, start + 1)
    return False


#: The 8 terms, plus queries where each step of the chain changes the terms:
#: `man utd` (club short form), `patriots playoffs` (typeahead takes the intent
#: subject, /search does not for this kind).
FIDELITY_QUERIES = (*S.TERMS, "man utd", "patriots playoffs")


@pytest.mark.asyncio
@pytest.mark.parametrize("q", FIDELITY_QUERIES)
async def test_typeahead_member_is_what_the_route_sends(q):
    """Kills: a typeahead arm without #4914's anti-join, built from /search's
    AND-ed name match, or skipping parse_intent / club short forms."""
    sent = await _route_sql("typeahead", q)
    assert _sent(_member_text(S.typeahead_ilike_member(q, NOW)), sent)


@pytest.mark.asyncio
@pytest.mark.parametrize("q", FIDELITY_QUERIES)
async def test_search_member_is_what_the_route_sends(q):
    """Kills: a /search arm without the anti-join, or with typeahead's chain."""
    sent = await _route_sql("search", q)
    assert _sent(_member_text(S.search_name_member(q, NOW)), sent)


@pytest.mark.asyncio
async def test_the_fidelity_check_discriminates():
    """Strawmen. Each wrong builder must FAIL the check above, or it proves nothing."""
    ta = await _route_sql("typeahead", "man utd")
    se = await _route_sql("search", "world series")
    # (1) no club expansion: the chain step skipped.
    with patch.object(ev, "expand_club_short_forms", side_effect=lambda s: s):
        assert not _sent(_member_text(S.typeahead_ilike_member("man utd", NOW)), ta)
    # (2) typeahead's arm on /search, and /search's arm on typeahead.
    assert not _sent(_member_text(S.typeahead_ilike_member("world series", NOW)), se)
    ta_ws = await _route_sql("typeahead", "world series")
    assert not _sent(_member_text(S.search_name_member("world series", NOW)), ta_ws)
    # (3) no anti-join: a member without #4914's NOT EXISTS is a PREFIX of the
    # route's member and must still be refused; the original G0 arm lacks it.
    from sqlalchemy import or_, select
    from app.models.models import FuturesMarket as FM

    terms, expanded = S.search_terms("world series")
    no_anti = select(FM.id).where(
        *ev._futures_multi_term_name_conditions(expanded),
        FM.status == ev._FUTURES_OPEN_STATUS_SQL,
        or_(FM.resolution_date.is_(None), FM.resolution_date >= NOW),
    )
    assert any(_member_text(no_anti) in _flat(s) for s in se), (
        "strawman must be a prefix of the route's member, or it tests nothing"
    )
    assert not _sent(_member_text(no_anti), se)
    g0 = G._sql_for("world series", "name")
    assert "NOT (EXISTS" not in g0
    assert "NOT (EXISTS" in S.compile_sql(S.search_name_member("world series", NOW))
    # (4) the subject rule: typeahead takes `patriots`, /search keeps both words.
    ta_terms, _ = S.typeahead_terms("patriots playoffs")
    se_terms, _ = S.search_terms("patriots playoffs")
    assert ta_terms == ["patriots"] and se_terms == ["patriots", "playoffs"]


# --- original SQL and retained REDs are pinned ---------------------------------

def test_original_sql_is_unchanged_since_the_baseline_commit():
    """Kills: comparing changed SQL with the 10/08 baseline as if identical."""
    assert S.g0_identity() == {}
    assert len(S.G0_SQL_SHA16) == 24


def test_a_moved_statement_is_detected():
    with patch.object(S, "G0_SQL_SHA16", {**S.G0_SQL_SHA16, "champion|name": "0" * 16}):
        assert list(S.g0_identity()) == ["champion|name"]


def test_the_original_gate_is_imported_not_restated():
    """Kills: a successor with its own copy of a term list, factor or rewrite."""
    assert S.TERMS is G.TERMS
    assert S.VARIANTS is G.SEMANTICS_VARIANTS
    assert S.PER_TERM_REGRESSION_FACTOR == G.PER_TERM_REGRESSION_FACTOR == 1.5
    assert set(S.VARIANTS) == {"no_partial", "no_trgm"}
    assert "BETWEEN" not in inspect.getsource(S.rewrite)


def test_retained_records_are_byte_identical():
    for path, sha in S.RETAINED_READS.values():
        with open(path, "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == sha, path


def test_retained_failures_and_their_status():
    """The six OWED failures are exactly term 4's list plus election's 01:15Z
    forbidden read. champion/winner failed only the old EXPECTED rule."""
    got = {
        (f["read"], f["term"], f["clause"]): (f["status"], f["chosen_plan"])
        for f in S.retained_failures(S.load_retained())
    }
    assert got == {
        ("20261012T0005Z", "world series", "NO-REGRESSION"): (S.OWED, True),
        ("20261012T0005Z", "world cup", "NO-REGRESSION"): (S.OWED, True),
        ("20261012T0005Z", "champion", "SHAPE"): (S.SUPERSEDED_RULE, False),
        ("20261012T0005Z", "winner", "SHAPE"): (S.SUPERSEDED_RULE, False),
        ("20261012T0005Z", None, "SEMANTICS"): (S.SUPERSEDED_RULE, None),
        ("20261012T0115Z", "world series", "NO-REGRESSION"): (S.OWED, False),
        ("20261012T0115Z", "world cup", "NO-REGRESSION"): (S.OWED, False),
        ("20261012T0115Z", "super bowl", "NO-REGRESSION"): (S.OWED, False),
        ("20261012T0115Z", "champion", "SHAPE"): (S.SUPERSEDED_RULE, False),
        ("20261012T0115Z", "winner", "SHAPE"): (S.SUPERSEDED_RULE, False),
        ("20261012T0115Z", "election", "SHAPE"): (S.OWED, False),
    }
    assert len(S.owed(S.retained_failures(S.load_retained()))) == 6


def test_owed_failures_keep_the_search_track_red():
    """Kills: a clean new read clearing a retained failure (term 4)."""
    all_pass = {f"NO-REGRESSION:{t}": S.PASS for t in S.TERMS}
    assert S.track_verdict(all_pass, S.owed(S.retained_failures(S.load_retained()))) == "RED"
    assert S.track_verdict(all_pass, []) == "GREEN"
    assert S.track_verdict({**all_pass, "x": S.NOT_EVALUABLE}, []) == "RED"


# --- plans: relation-scoped fingerprint over every scan type -------------------

def test_fingerprint_sees_every_scan_type():
    """Kills the original `_bitmap_index_scans`, which sees Bitmap Index Scans only."""
    assert S.access_fingerprint(plan("seq_scan")) == [
        {"node": "Seq Scan", "index": None, "alias": "futures_markets"}
    ]
    for name, node in (("index_scan", "Index Scan"), ("index_only_scan", "Index Only Scan")):
        got = S.access_fingerprint(plan(name))
        assert got == [{"node": node, "index": "ix_futures_name_trgm", "alias": "futures_markets"}]
        assert G._bitmap_index_scans(plan(name)) == set()  # the original is blind here


def test_fingerprint_attributes_bitmap_leaves_through_and_or():
    assert S._indexes(S.access_fingerprint(plan("bitmap_and"))) == {
        "ix_futures_name_trgm", "ix_futures_markets_status",
    }
    assert [e["index"] for e in S.access_fingerprint(plan("bitmap_or"))] == [
        "ix_futures_name_trgm_open", "ix_futures_name_trgm_open",
    ]


def test_fingerprint_is_relation_scoped_and_finds_the_anti_join():
    """Kills: counting `events_pkey` (the anti-join's index) as a futures access."""
    p = plan("anti_join")
    assert S._indexes(S.access_fingerprint(p)) == {"ix_futures_name_trgm_open"}
    assert "events_pkey" in G._bitmap_index_scans(p)  # the original is unscoped
    assert S.anti_join_methods(p) == ["Nested Loop (Anti)"]
    assert S.anti_join_methods(plan("index_scan")) == []


def test_both_aliases_of_a_wrapper_are_seen_and_the_skeleton_is_recorded():
    got = S.access_fingerprint(plan("pool_wrapper"))
    assert {e["alias"] for e in got} == {"futures_markets", "futures_markets_1"}
    assert S.plan_skeleton(plan("pool_wrapper"))[0] == "Limit"


def test_the_anti_joins_own_alias_is_recorded_but_not_graded():
    entries = fp(("Index Scan", "ix_futures_name_trgm_open")) + [
        {"node": "Seq Scan", "index": None, "alias": "grp_sibling"},
        {"node": "Index Scan", "index": "ix_unknown", "alias": "futures_markets_1"},
    ]
    assert [e["alias"] for e in S.graded_access(entries)] == ["futures_markets", "futures_markets_1"]


def test_catalog_classification():
    assert CLASSES["ix_futures_name_trgm"] == {"trigram": True, "open_only": False}
    assert CLASSES["ix_futures_name_trgm_open"] == {"trigram": True, "open_only": True}
    assert CLASSES["ix_futures_name_fts_open"] == {"trigram": False, "open_only": True}
    assert CLASSES["ix_futures_markets_status"] == {"trigram": False, "open_only": False}
    # a partial with any other predicate is NOT counted open-only (never over-credit)
    assert CLASSES["ix_fm_feed_open_volume"]["open_only"] is False


# --- SHAPE: the amended rule, every branch -------------------------------------

@pytest.mark.parametrize(
    "a, t, subject, verdict",
    [
        # original rule
        (fp((BH, "ix_futures_name_trgm_open")), None, True, S.PASS),
        # champion/winner: open-only without the new index, control has no trigram
        (fp((BH, "ix_futures_name_fts_open")), fp((BH, "ix_futures_name_fts_open")), True, S.PASS_EXCEPTION),
        # election 01:15Z: reads the forbidden index -> FAIL under both rules
        (fp((BH, "ix_futures_name_fts_open"), (BH, "ix_futures_name_trgm")),
         fp((BH, "ix_futures_name_fts_open")), True, S.FAIL),
        # the control still reads a trigram index: exception unavailable
        (fp((BH, "ix_futures_name_fts_open")), fp((BH, "ix_futures_name_trgm_open")), True, S.FAIL),
        # control unread: not evaluable, never a pass
        (fp((BH, "ix_futures_name_fts_open")), None, True, S.NOT_EVALUABLE),
        # not open-only (Seq Scan / whole-table btree only)
        (fp(("Seq Scan", None)), fp(("Seq Scan", None)), True, S.FAIL),
        (fp((BH, "ix_futures_markets_status")), fp((BH, "ix_futures_markets_status")), True, S.FAIL),
        # an index the catalog cannot classify
        (fp((BH, "ix_psql_only")), fp(("Seq Scan", None)), True, S.NOT_EVALUABLE),
        (fp((BH, "ix_futures_name_fts_open")), fp((BH, "ix_psql_only")), True, S.NOT_EVALUABLE),
        # bystanders keep the original pass, including one reading the whole-table
        # index (D1 was not adopted)
        (fp((BH, "ix_futures_name_trgm")), None, False, S.PASS),
    ],
)
def test_shape_verdict(a, t, subject, verdict):
    got, reason = S.shape_verdict(a, t, CLASSES, subject, None if t else "control unread")
    assert got == verdict, reason
    if got == S.PASS_EXCEPTION:
        assert S.NO_CREDIT_NOTE in reason


def test_search_shape_needs_both_the_original_and_the_faithful_arm():
    assert S.combine(S.PASS, S.PASS_EXCEPTION) == S.PASS_EXCEPTION
    assert S.combine(S.PASS, S.FAIL) == S.FAIL
    assert S.combine(S.PASS, S.NOT_EVALUABLE) == S.NOT_EVALUABLE
    assert S.combine(S.NOT_EVALUABLE, S.FAIL) == S.FAIL


def _reads(a_plans, t_plans, faithful=True, t_problem=None):
    return {
        "a": [S._plan_summary(p) for p in a_plans],
        "t": [S._plan_summary(p) for p in t_plans],
        "t_problem": t_problem, "faithful_required": faithful,
    }


def test_a_faithful_read_without_the_anti_join_is_not_evaluable():
    """Kills: grading a 'faithful' read whose executed plan lost #4914."""
    reads = _reads([plan("bitmap_or")], [plan("seq_scan")])
    assert S.arm_shape(reads, CLASSES, True)[0] == S.NOT_EVALUABLE
    reads = _reads([plan("anti_join")], [plan("seq_scan")])
    assert S.arm_shape(reads, CLASSES, True)[0] == S.PASS  # reads trgm_open


def test_one_unread_round_makes_the_union_unread():
    reads = {"a": [S._plan_summary(plan("anti_join")), "UNREAD:statement_timeout"],
             "t": [], "t_problem": None, "faithful_required": True}
    assert S.arm_shape(reads, CLASSES, True)[0] == S.NOT_EVALUABLE


def test_a_flip_to_the_forbidden_index_in_any_round_fails():
    reads = _reads([plan("anti_join"), plan("index_scan")], [plan("seq_scan")], faithful=False)
    assert S.arm_shape(reads, CLASSES, True)[0] == S.FAIL


# --- controls ------------------------------------------------------------------

def test_no_trgm_rewrite_is_complete_or_refused():
    sql = S.compile_sql(S.typeahead_ilike_member("world series", NOW))
    out = S.rewrite(sql, "no_trgm")
    assert "futures_markets.name ILIKE" not in out
    # a round word keeps a `~*` on name, which a trigram index can serve
    alds = S.compile_sql(S.typeahead_ilike_member("alds", NOW))
    with pytest.raises(S.VariantUnavailable):
        S.rewrite(alds, "no_trgm")
    with pytest.raises(S.VariantUnavailable):
        S.rewrite("SELECT 1", "no_partial")


def test_set_digest_cannot_be_truncated_by_the_row_cap():
    """Kills: comparing the first 500 ids of an unordered arm."""
    sql = S.set_digest_sql("SELECT futures_markets.id FROM futures_markets")
    assert sql.startswith("SELECT count(*), md5(")
    assert "ORDER BY s.id" in sql


def test_semantics_over_digests_is_fail_closed():
    same = {"usable": [10, "a"], "no_partial": [10, "a"], "no_trgm": [10, "a"]}
    assert G.semantics_verdict({"x": same}, {})[0] is True
    assert G.semantics_verdict({"x": {**same, "no_trgm": [10, "b"]}}, {})[0] is False
    assert G.semantics_verdict({"x": {**same, "usable": "UNREAD:timeout"}}, {})[0] is False


# --- NO-REGRESSION and BUDGET ---------------------------------------------------

def test_no_regression_is_the_original_rule_and_fails_closed():
    assert S.no_regression_verdict(0.15, 0.1) == S.PASS
    assert S.no_regression_verdict(0.1501, 0.1) == S.FAIL
    assert S.no_regression_verdict(0.01, None) == S.NOT_EVALUABLE  # the original passed this
    retained = S.load_retained()["20261012T0005Z"]["terms"]["world series"]
    assert S.no_regression_verdict(retained["ratio"], retained["before_ratio"]) == S.FAIL


def test_search_budget_is_withdrawn_and_claims_nothing():
    assert "NOT PROVEN" in S.SE_BUDGET_STATEMENT
    assert S.CRITERIA["C3.BUDGET(/search)"]["new"].startswith("WITHDRAWN")
    src = inspect.getsource(S.run_se)
    assert "per_term_collapses" not in src and "budget_verdict" not in src
    for clause in S.CRITERIA.values():
        assert clause["old"] and clause["new"] and clause["source"]


# --- C4: the reader, and only the reader ---------------------------------------

def _c4(word="ranger", fq=120, oa=300, shed=False, status=200, source="reader"):
    return {
        "source": source, "word": word, "http_status": status,
        "debug_timing": {"futures_query": fq, "futures_outcome_arm": oa},
        "debug_shed": {"outcome_arm_shed": shed, "degraded": False},
    }


@pytest.mark.parametrize(
    "rec, verdict",
    [
        (_c4(), S.PASS),
        (_c4(fq=170), S.FAIL),
        (_c4(oa=239), S.UNMATCHED),
        (_c4(shed=True), S.NOT_EVALUABLE),
        (_c4(oa=None), S.NOT_EVALUABLE),
        (_c4(fq=None), S.NOT_EVALUABLE),
        (_c4(status=503), S.NOT_EVALUABLE),
        (_c4(source="db-query"), S.NOT_EVALUABLE),
    ],
)
def test_c4_word_verdict(rec, verdict):
    assert S.c4_word_verdict(rec)[0] == verdict


def test_c4_is_paid_only_on_every_word():
    full = [_c4(word=w) for w in S.C4_WORDS]
    assert S.c4_verdict(full)[0] == S.PAID
    assert S.c4_verdict(full[:-1])[0] == S.NOT_PAID
    assert S.c4_verdict(full[:-1] + [_c4(word="packer", fq=171)])[0] == S.NOT_PAID
    assert S.c4_verdict(full + [_c4(word="mets")])[0] == S.NOT_PAID


def test_c4_thresholds_are_the_retained_befores_fastest_values():
    """No number that is not in the 2026-10-08 record."""
    assert S.C4_BEFORE_MS == {"futures_query": (170, 890), "futures_outcome_arm": (240, 1170)}
    spec = os.path.join(G.REPO, "docs", "audits", "latency", "lat-p088-futures-open-trgm-index-spec.md")
    text = open(spec).read()
    assert "`futures_query` 0.17-0.89 s" in text and "`futures_outcome_arm` 0.24-1.17 s" in text


# --- output guard ---------------------------------------------------------------

def test_output_never_overwrites_an_original_record(tmp_path):
    for path in (G.BASELINE, *(p for p, _ in S.RETAINED_READS.values())):
        assert S.check_out_path(path)
    assert S.check_out_path(None)
    assert S.check_out_path(str(tmp_path / "gate-after.json"))
    ok = tmp_path / "lat-10769-successor-ta-x.json"
    assert S.check_out_path(str(ok)) is None
    ok.write_text("{}")
    assert S.check_out_path(str(ok))


def test_dry_run_makes_no_request(capsys):
    with patch.object(G, "_post", side_effect=AssertionError("network")), \
         patch.object(S, "c4_read", side_effect=AssertionError("network")):
        for track in ("se", "ta", "c4"):
            assert S.dry_run(track) == 0
    assert "original SQL identity: OK 24/24" in capsys.readouterr().out


def test_arm_reads_are_labelled_custom_plan_not_reader():
    src = inspect.getsource(S.main)
    assert "NOT the reader's prepared statement" in src
    assert re.search(r"c4_read\(word\) for word in C4_WORDS", src)
