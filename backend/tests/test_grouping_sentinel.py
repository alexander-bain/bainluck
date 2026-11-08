"""The grouping sentinel (#12231): weekly counts, report-only until Nov 26.

The rules under test come from 72-A and Fable's answers on #12231 (Nov 6,
9:28 PM and the 9:35 PM addendum):

* uncovered families are 5+ open, priced markets alive 48 h with no covered member;
* a market Discover hard-suppresses by ruling is excluded, never uncovered;
* the post goes to #12221 once a week, counts first, under 60 lines;
* nothing is filed before Thu Nov 26, and from then at most five new issues a run;
* the hand run on merge day and the Thursday run are different weeks.

No DB, no Redis, no GitHub: every edge is faked.
"""

from datetime import datetime, timedelta, timezone

import pytest

import app.tasks.grouping_sentinel as gs
import app.tasks.sentinel_filing as sf
from app.utils.grouping_families import KIND_KALSHI_SERIES, KIND_POLYMARKET_EVENT

NOW = datetime(2026, 11, 12, 16, 0, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=10)
YOUNG = NOW - timedelta(hours=10)
_ids = iter(range(1, 10**6))


def row(ticker=None, *, source="kalshi", group=None, name="t", created=OLD, priced=True,
        event_id=None, market_type="claim", relation="complements", frame_type=None,
        event_title=None, names=("Yes", "No")):
    mid = next(_ids)
    return {
        "id": mid,
        "source": source,
        "external_id": ticker or f"0x{mid}",
        "group_id": group if group is not None else (f"kalshi:{ticker}" if source == "kalshi" else None),
        "name": name,
        "event_id": event_id,
        "created_at": created,
        "llm_sport_category": None,
        "story_key": None,
        "market_type": market_type,
        "event_title": event_title,
        "outcome_relation": relation,
        "frame_type": frame_type,
        "names": list(names),
        "priced": priced,
    }


def series(code, n, **kw):
    return [row(f"{code}-{i}", **kw) for i in range(n)]


def counts(rows, *, definition_ids=(), graph_ids=(), collection_ids=(), suppressed=lambda r: False,
           graph_unclassified=0, now=NOW):
    return gs.compute_counts(
        rows,
        definition_ids=set(definition_ids),
        graph_ids=set(graph_ids),
        collection_ids=set(collection_ids),
        graph_unclassified=graph_unclassified,
        now=now,
        suppressed=suppressed,
    )


# --- the week ------------------------------------------------------------------
@pytest.mark.parametrize(
    "now, start",
    [
        (datetime(2026, 11, 12, 16, 0, tzinfo=timezone.utc), "2026-11-12"),  # the scheduled run
        (datetime(2026, 11, 12, 11, 59, tzinfo=timezone.utc), "2026-11-05"),  # before the anchor
        (datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc), "2026-11-05"),  # the hand run, Tue
        (datetime(2026, 11, 18, 23, 0, tzinfo=timezone.utc), "2026-11-12"),  # Wednesday next week
        (datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc), "2026-11-26"),  # first filing run
    ],
)
def test_the_week_starts_thursday_noon_utc(now, start):
    assert gs.period_key(now) == start


def test_merge_day_hand_run_and_the_first_thursday_post_are_different_weeks():
    # The 9:35 PM addendum: an early post on merge day, then Thursday 8 AM PT
    # is the first scheduled post. In ISO weeks both are week 46 and the
    # second would be swallowed as already posted.
    assert gs.period_key(datetime(2026, 11, 10, 18, tzinfo=timezone.utc)) != gs.period_key(NOW)


# --- counting ------------------------------------------------------------------
def test_an_uncovered_series_of_five_old_priced_markets_is_reported():
    c = counts(series("KXSNOW", 5))
    assert [(f.kind, f.key) for f in c.uncovered] == [(KIND_KALSHI_SERIES, "KXSNOW")]


def test_four_markets_are_not_a_family_yet():
    assert counts(series("KXSNOW", 4)).uncovered == []


def test_markets_younger_than_48_hours_do_not_count_toward_five():
    rows = series("KXSNOW", 4) + [row("KXSNOW-9", created=YOUNG)]
    assert counts(rows).uncovered == []


def test_unpriced_markets_are_not_members():
    rows = series("KXSNOW", 4) + [row("KXSNOW-9", priced=False)]
    assert counts(rows).uncovered == []


@pytest.mark.parametrize("source", ["definition_ids", "graph_ids", "collection_ids"])
def test_any_coverage_source_covers_the_family(source):
    rows = series("KXSNOW", 6)
    assert counts(rows, **{source: [rows[3]["id"]]}).uncovered == []


def test_an_event_page_covers_the_family():
    rows = series("KXSNOW", 5) + [row("KXSNOW-9", event_id=77)]
    c = counts(rows)
    assert c.uncovered == []
    assert c.covered_by["event_pages"] == 1


def test_a_suppressed_family_is_excluded_by_ruling_not_uncovered():
    rows = series("KXMIDTERMMOV", 7)
    c = counts(rows, suppressed=lambda r: r["external_id"].startswith("KXMIDTERMMOV"))
    assert c.uncovered == []
    assert c.excluded_families == 1
    assert c.suppressed_markets == 7


def test_shape_and_frame_counts_read_every_open_market():
    rows = [
        row("KXA-1", market_type="unshaped", relation="unknown", frame_type="object"),
        row("KXA-2", market_type=None, frame_type="null", priced=False),
        row("KXA-3"),
    ]
    c = counts(rows, graph_unclassified=4)
    assert (c.open_markets, c.priced_markets) == (3, 2)
    assert (c.unshaped, c.shape_unclassified, c.relation_unknown, c.graph_unclassified) == (1, 1, 1, 4)
    assert (c.frames_written, c.frames_null, c.frames_never) == (1, 1, 1)


def test_the_priced_floor_and_empty_rows_are_counted_apart_12221():
    """#12221: Alex's floor is every open, PRICED market; an empty row has no shape to give."""
    rows = [
        row("KXA-1", market_type="unshaped", relation="unknown"),
        row("KXA-2", market_type="unshaped", relation="unknown", priced=False, names=()),
        row("KXA-3", market_type="field", relation="unknown"),
        row("KXA-4"),
    ]
    c = counts(rows)
    assert (c.unshaped, c.relation_unknown) == (2, 3)
    assert (c.priced_markets, c.priced_unshaped, c.priced_relation_unknown) == (3, 1, 2)
    assert c.no_outcomes == 1


def test_new_series_candidates_are_young_uncovered_families_of_three():
    young = series("KXNEW", 3, created=YOUNG)
    old = series("KXOLD", 3)
    covered_young = series("KXCOV", 3, created=YOUNG)
    c = counts(young + old + covered_young, definition_ids=[covered_young[0]["id"]])
    assert [f.key for f in c.new_series_candidates] == ["KXNEW"]


# --- the sentinel's memory -----------------------------------------------------
class FakeRedis:
    def __init__(self, fail=False):
        self.kv, self.z, self.fail = {}, {}, fail

    def _check(self):
        if self.fail:
            raise ConnectionError("redis down")

    def get(self, k):
        self._check()
        return self.kv.get(k)

    def set(self, k, v, ex=None):
        self.kv[k] = v

    def expire(self, k, s):
        return True

    def zadd(self, k, mapping, nx=False):
        zs = self.z.setdefault(k, {})
        for m, score in mapping.items():
            if not (nx and m in zs):
                zs[m] = score

    def zremrangebyscore(self, k, lo, hi):
        return 0

    def pipeline(self):
        outer = self

        class P:
            def __init__(self):
                self.ops = []

            def zscore(self, k, m):
                self.ops.append((k, m))

            def execute(self):
                return [outer.z.get(k, {}).get(m) for k, m in self.ops]

        return P()


def test_the_first_run_records_the_baseline_and_counts_nothing_new():
    c = counts(series("KXNEW", 3, created=YOUNG))
    r = FakeRedis()
    new, state = gs.new_series_from_memory(c.new_series_candidates, c.all_families, NOW, r)
    assert (new, state) == (None, "baseline")
    assert gs.BASELINE_KEY in r.kv


def test_a_family_first_seen_after_the_baseline_is_new():
    r = FakeRedis()
    first = counts(series("KXOLD", 3, created=YOUNG))
    gs.new_series_from_memory(first.new_series_candidates, first.all_families, NOW - timedelta(days=2), r)
    later = counts(series("KXOLD", 3, created=YOUNG) + series("KXNEW", 3, created=YOUNG))
    new, state = gs.new_series_from_memory(later.new_series_candidates, later.all_families, NOW, r)
    assert state == "counted"
    assert [f.key for f in new] == ["KXNEW"]


def test_unreadable_memory_is_unknown_not_zero():
    c = counts(series("KXNEW", 3, created=YOUNG))
    new, state = gs.new_series_from_memory(c.new_series_candidates, c.all_families, NOW, FakeRedis(fail=True))
    assert (new, state) == (None, "memory_unavailable")


# --- the post ------------------------------------------------------------------
DEF_STATS = {"producers": 18, "emitted": 16, "refused": 2, "failed": 0, "failed_slugs": []}


def compose(c, *, now=NOW, new_series=(), memory_state="counted", filing=None, def_stats=DEF_STATS):
    return gs.compose_report(
        c, now=now, new_series=None if new_series is None else list(new_series),
        memory_state=memory_state, definition_stats=def_stats, filing=filing,
    )


def test_the_post_is_counts_first_then_families_then_unknowns_under_sixty_lines():
    rows = []
    for i in range(30):
        rows += series(f"KXFAM{i:02d}", 5 + i)
    body = compose(counts(rows))
    lines = body.splitlines()
    assert len(lines) < 60
    first = next(i for i, l in enumerate(lines) if l.startswith("**1."))
    listed = next(i for i, l in enumerate(lines) if l.startswith("**Largest"))
    unknown = next(i for i, l in enumerate(lines) if l.startswith("**UNKNOWN"))
    assert first < listed < unknown
    assert "…and 20 more." in body
    assert body.count("`" + gs.FILING_MARKER) == 0  # no declaration in a report


def test_report_only_until_nov_26_then_filing_is_announced():
    c = counts(series("KXSNOW", 5))
    assert "Report-only until Thu Nov 26" in compose(c)
    after = datetime(2026, 11, 26, 16, tzinfo=timezone.utc)
    assert "Filing is on" in compose(c, now=after, filing={"summary": "1 filed, 0 still open, 0 closed, 0 failed"})


def test_the_post_lists_each_family_with_the_fingerprint_it_will_be_filed_under():
    c = counts(series("KXSNOW", 5))
    assert f"`{c.uncovered[0].fingerprint}` · Kalshi series · `KXSNOW` · 5" in compose(c)


def test_venue_titles_cannot_mention_a_github_user():
    rows = [row(f"KXNBA-{i}", event_title="Lakers @Celtics | game") for i in range(5)]
    body = compose(counts(rows))
    assert "@" not in body


def test_first_run_says_unknown_for_new_series_with_the_reason():
    c = counts(series("KXSNOW", 5))
    body = compose(c, new_series=None, memory_state="baseline")
    assert "**2. New venue series: UNKNOWN** (this run recorded the baseline" in body
    assert "new venue series (see 2)" in body


def test_new_measures_are_always_unknown():
    assert "**4. New measures: UNKNOWN**" in compose(counts(series("KXSNOW", 5)))


# --- filing --------------------------------------------------------------------
class OpenIssues:
    def __init__(self, issues, ok=True):
        self.ok, self.issues, self.error = ok, issues, None if ok else "boom"


@pytest.fixture
def filing(monkeypatch):
    calls = []

    def fake_reconcile(**kw):
        calls.append(kw)
        if not kw["red"]:
            return {"action": "resolved"}
        return {"action": "commented" if kw["fingerprint"] in state["existing"] else "filed"}

    state = {"existing": set(), "issues": []}
    monkeypatch.setattr(sf, "reconcile_issue", fake_reconcile)
    monkeypatch.setattr(sf, "fetch_open_alert_issues", lambda: OpenIssues(state["issues"]))
    state["calls"] = calls
    return state


def _families(n):
    rows = []
    for i in range(n):
        rows += series(f"KXF{i:02d}", 5 + n - i)
    return counts(rows).uncovered


def test_at_most_five_new_issues_a_run(filing):
    out = gs.file_families(_families(8), NOW)
    assert sum(1 for c in filing["calls"] if c["red"]) == 5
    assert out["summary"].startswith("5 filed")


def test_families_already_filed_are_commented_and_do_not_use_up_the_five(filing):
    fams = _families(8)
    filing["existing"] = {fams[0].fingerprint, fams[1].fingerprint}
    filing["issues"] = [{"number": 1, "body": gs._declaration(fp)} for fp in filing["existing"]]
    out = gs.file_families(fams, NOW)
    assert out["summary"].startswith("5 filed, 2 still open")


def test_a_filed_family_that_is_covered_now_is_closed(filing):
    filing["issues"] = [{"number": 9, "body": gs._declaration("abcdef123456")}]
    gs.file_families([], NOW)
    (green,) = [c for c in filing["calls"] if not c["red"]]
    assert green["fingerprint"] == "abcdef123456"


def test_an_unreadable_open_issue_list_files_nothing(monkeypatch, filing):
    monkeypatch.setattr(sf, "fetch_open_alert_issues", lambda: OpenIssues([], ok=False))
    out = gs.file_families(_families(3), NOW)
    assert out["action"] == "dedup_unknown_no_op"
    assert filing["calls"] == []


def test_the_issue_body_declares_its_fingerprint_for_the_rail():
    (fam,) = counts(series("KXSNOW", 5)).uncovered
    assert sf.declared_fingerprints(gs.family_issue_body(fam, NOW)) == {(gs.FILING_MARKER, fam.fingerprint)}


# --- the terminal ----------------------------------------------------------------
@pytest.mark.parametrize(
    "stats, want",
    [
        ({"report": {"action": "posted"}, "definitions": {"failed": 0}}, "complete"),
        ({"report": {"action": "already_posted"}, "definitions": {}}, "complete"),
        ({"report": {"action": "posted"}, "definitions": {"failed": 2}}, "partial"),
        ({"report": {"action": "posted"}, "definitions": {}, "memory_state": "memory_unavailable"}, "partial"),
        ({"report": {"action": "claim_lost"}, "definitions": {}}, "partial"),
        ({"report": {"action": "comment_failed"}, "definitions": {}}, "failed"),
        ({"report": {"action": "read_unknown_no_op"}, "definitions": {}}, "failed"),
        ({"report": {"action": "skipped_no_token"}, "definitions": {}}, "failed"),
        ({"error": "db down"}, "failed"),
        ({"report": {"action": "posted"}, "definitions": {}, "filing": {"failed": 1}}, "partial"),
    ],
)
def test_terminal(stats, want):
    assert gs._terminal(stats) == want


# --- the run ---------------------------------------------------------------------
class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows, self._scalar = rows or [], scalar

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _Session:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "LEFT JOIN LATERAL" in sql:
            # Pages as the real query does: id > :after, LIMIT :page.
            after, page = (params or {})["after"], (params or {})["page"]
            return _Result([r for r in self.rows if r["id"] > after][:page])
        if "count(DISTINCT" in sql:
            return _Result(scalar=0)
        return _Result([])

    async def rollback(self):
        return None


@pytest.fixture
def run_env(monkeypatch):
    from contextlib import asynccontextmanager

    import app.tasks.base as base
    import app.tasks.redis_state as redis_state

    env = {"rows": series("KXSNOW", 6), "posts": [], "filed": [], "redis": FakeRedis()}

    @asynccontextmanager
    async def fake_session(**kw):
        yield _Session(env["rows"])

    async def no_definitions(session):
        return set(), dict(DEF_STATS)

    monkeypatch.setattr(base, "get_task_session", fake_session)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: env["redis"])
    monkeypatch.setattr(gs, "definition_coverage", no_definitions)
    monkeypatch.setattr(gs, "collection_ids", lambda: set())
    monkeypatch.setattr(gs, "is_suppressed", lambda r: False)
    monkeypatch.setattr(sf, "post_report", lambda **kw: env["posts"].append(kw) or {"action": "posted"})
    monkeypatch.setattr(gs, "file_families", lambda fams, now: env["filed"].append(fams) or {"action": "reconciled", "summary": "x", "failed": 0})
    return env


async def test_a_run_before_nov_26_posts_the_week_and_files_nothing(run_env):
    stats = await gs._run_grouping_sentinel(now=NOW)
    assert stats["terminal"] == "complete"
    assert run_env["filed"] == []
    (post,) = run_env["posts"]
    assert post["issue"] == 12221 and post["period_key"] == "2026-11-12"
    assert post["since"] == "2026-11-12T12:00:00Z"
    assert stats["uncovered_families"] == 1


async def test_a_run_from_nov_26_files(run_env):
    await gs._run_grouping_sentinel(now=datetime(2026, 11, 26, 16, tzinfo=timezone.utc))
    assert len(run_env["filed"]) == 1


async def test_filing_can_be_paused_without_a_deploy(run_env):
    run_env["redis"].kv[gs.FILING_PAUSE_KEY] = "1"
    stats = await gs._run_grouping_sentinel(now=datetime(2026, 11, 26, 16, tzinfo=timezone.utc))
    assert run_env["filed"] == []
    assert stats["filing"]["action"] == "paused"


async def test_any_value_pauses_filing_even_zero(run_env):
    # bool(b"0") is True: Alex resumes with DEL, never with SET 0.
    run_env["redis"].kv[gs.FILING_PAUSE_KEY] = "0"
    stats = await gs._run_grouping_sentinel(now=datetime(2026, 11, 26, 16, tzinfo=timezone.utc))
    assert run_env["filed"] == [] and stats["filing"]["action"] == "paused"


async def test_an_unreadable_pause_switch_files_nothing(run_env):
    # A run that cannot rule out Alex's pause must not file over it.
    run_env["redis"].fail = True
    stats = await gs._run_grouping_sentinel(now=datetime(2026, 11, 26, 16, tzinfo=timezone.utc))
    assert run_env["filed"] == []
    assert stats["filing"]["action"] == "pause_unknown_no_op"
    assert stats["terminal"] == "partial"


async def test_no_redis_at_all_files_nothing(monkeypatch, run_env):
    import app.tasks.redis_state as redis_state

    def no_client(*a, **k):
        raise RuntimeError("REDIS_URL unset")

    monkeypatch.setattr(redis_state, "get_redis_client", no_client)
    stats = await gs._run_grouping_sentinel(now=datetime(2026, 11, 26, 16, tzinfo=timezone.utc))
    assert run_env["filed"] == [] and stats["filing"]["action"] == "pause_unknown_no_op"


def test_the_issue_body_claims_no_exclusion_list():
    # The rail has no exclusion register; the body must not promise one.
    (fam,) = gs.build_families([gs.Atom(1, "kalshi", "KXSNOW-1", "kalshi:KXSNOW-1", "t", None, (), OLD)]).families
    body = gs.family_issue_body(fam, NOW)
    assert "exclusion the sentinel reads" not in body
    assert "no exclusion list yet" in body


async def test_a_dry_run_returns_the_body_and_posts_nothing(run_env):
    stats = await gs._run_grouping_sentinel(post=False, now=NOW)
    assert run_env["posts"] == []
    assert stats["report_body"].startswith("**Grouping sentinel: weekly count**")


async def test_a_failed_read_is_a_failed_run(monkeypatch, run_env):
    from contextlib import asynccontextmanager

    import app.tasks.base as base

    @asynccontextmanager
    async def broken(**kw):
        raise RuntimeError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr(base, "get_task_session", broken)
    stats = await gs._run_grouping_sentinel(now=NOW)
    assert stats["terminal"] == "failed" and run_env["posts"] == []


# --- enrolment (#1884: enforced from birth) --------------------------------------
@pytest.mark.parametrize("terminal, verdict", [("complete", "complete"), ("partial", "partial"), ("failed", "failed")])
def test_the_task_label_is_enforced_so_its_terminal_bites(terminal, verdict):
    from app.utils.task_verdict import ENFORCED_TASKS, verdict_for

    assert "grouping_sentinel" in ENFORCED_TASKS
    got = verdict_for("grouping_sentinel", {"terminal": terminal})
    assert got.verdict == verdict and got.authoritative


async def test_the_population_is_read_in_pages_and_every_page_is_counted(monkeypatch, run_env):
    # Three pages of two rows: a paging bug (stopping early, re-reading a page)
    # would change the count.
    monkeypatch.setattr(gs, "PAGE_ROWS", 2)
    run_env["rows"] = series("KXSNOW", 6)
    stats = await gs._run_grouping_sentinel(post=False, now=NOW)
    assert stats["open_markets"] == 6
    assert stats["uncovered_families"] == 1


# --- definitions are read live, never from Discover's cache ------------------------
def _producer(slug, produce, enabled=None):
    from app.utils.roundup_containers import RoundupProducer

    return RoundupProducer(slug, slug, category="x", section_title="S", footer="f", produce=produce, enabled=enabled)


def _members(*ids, rows=(), event_ids=()):
    from app.utils.roundup_containers import RoundupMembers

    members = [{"id": i, "title": f"m{i}"} for i in ids]
    members += [
        {"type": "event", "id": e, "destination": {"kind": "event", "id": e}, "card": {"id": e}}
        for e in event_ids
    ]
    return RoundupMembers(members, rows)


@pytest.fixture
def producers(monkeypatch):
    import app.utils.roundup_containers as rc

    registry = {}
    monkeypatch.setattr(rc, "ROUNDUP_PRODUCERS", registry)
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")

    async def forbidden(*a, **k):
        raise AssertionError("the sentinel must never write Discover's round-up cache")

    monkeypatch.setattr(rc, "_store_roundup_cache_entry", forbidden)
    rc.reset_roundup_cache_for_tests()
    yield registry
    rc.reset_roundup_cache_for_tests()


async def test_a_cached_timeout_refusal_does_not_hide_a_definitions_members(producers):
    # Since #12257 a Discover read that times out is cached as a refusal for
    # 60 s. Read through that cache, this definition would cover nothing and
    # its family would be reported uncovered.
    import time

    import app.utils.roundup_containers as rc

    session = _Session([])
    producers["d"] = _producer("d", lambda db: _members(11, 12))
    rc._roundup_local_cache[("d", id(session))] = (time.time(), None, None)
    covered, stats = await gs.definition_coverage(session)
    assert covered == {11, 12}
    assert stats["emitted"] == 1 and stats["refused"] == 0


async def test_every_market_member_counts_not_only_the_cards_rows(producers):
    rows = ({"market_id": 11, "label": "a", "pair": {"kalshi_market_id": 11, "polymarket_market_id": 91}},)
    producers["d"] = _producer("d", lambda db: _members(11, 12, 13, rows=rows))
    covered, _ = await gs.definition_coverage(_Session([]))
    assert covered == {11, 12, 13, 91}


async def test_an_event_member_is_never_read_as_a_market(producers):
    # The closest-games round-up's members are events; an event id read as a
    # market id would cover an unrelated market.
    producers["d"] = _producer("d", lambda db: _members(11, event_ids=(12,)))
    covered, _ = await gs.definition_coverage(_Session([]))
    assert covered == {11}


async def test_refused_failed_and_switched_off_definitions_cover_nothing(producers):
    from app.utils.roundup_containers import RoundupRefusal

    def boom(db):
        raise RuntimeError("producer crashed")

    producers["refuses"] = _producer("refuses", lambda db: RoundupRefusal(["too_few_members"]))
    producers["crashes"] = _producer("crashes", boom)
    producers["off"] = _producer("off", lambda db: _members(7), enabled=lambda: False)
    producers["ok"] = _producer("ok", lambda db: _members(8))
    covered, stats = await gs.definition_coverage(_Session([]))
    assert covered == {8}
    assert stats == {
        **stats, "producers": 4, "emitted": 1, "refused": 1, "switched_off": 1, "failed": 1,
        "failed_slugs": ["crashes"],
    }


async def test_a_definition_past_its_timeout_is_failed_not_refused(monkeypatch, producers):
    import asyncio

    async def slow(db):
        await asyncio.sleep(5)

    monkeypatch.setattr(gs, "PRODUCER_TIMEOUT_SECONDS", 0.01)
    producers["slow"] = _producer("slow", slow)
    covered, stats = await gs.definition_coverage(_Session([]))
    assert covered == set()
    assert stats["failed"] == 1 and stats["failed_slugs"] == ["slow"] and stats["refused"] == 0


def test_a_switched_off_definition_is_named_in_the_post():
    c = counts(series("KXSNOW", 5))
    assert "2 switched off" in compose(c, def_stats={**DEF_STATS, "switched_off": 2})
    assert "switched off" not in compose(c)


# --- wiring --------------------------------------------------------------------
def test_the_beat_is_thursday_16_utc_on_background():
    # Fable's answer on #12231: Thursdays 16:00 UTC (8 AM PT), background queue.
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["grouping-sentinel-weekly"]
    assert entry["task"] == "app.tasks.grouping_sentinel"
    assert entry["options"] == {"queue": "background"}
    sched = entry["schedule"]
    assert (sched.minute, sched.hour, sched.day_of_week) == ({0}, {16}, {4})
    # And the scheduled fire is the week the period key names.
    assert gs.period_key(datetime(2026, 11, 12, 16, 0, tzinfo=timezone.utc)) == "2026-11-12"


def test_the_soft_limit_leaves_room_for_the_definitions_deadline_and_the_reads():
    # #966: a run that outlives its soft limit is SIGKILLed untracked. Twelve
    # pages at ~5 s each come before the 600 s definitions deadline.
    from app.tasks import celery_app

    task = celery_app.tasks["app.tasks.grouping_sentinel"]
    assert gs.DEADLINE_SECONDS + 120 < task.soft_time_limit < task.time_limit


def test_the_task_runs_the_sentinel_under_its_enforced_label(monkeypatch):
    import app.tasks as tasks

    seen = {}
    monkeypatch.setattr(gs, "_run_grouping_sentinel", lambda **kw: ("run", kw))
    monkeypatch.setattr(tasks, "_tracked_run", lambda label, run: seen.update(label=label, run=run) or {})
    # By registered name: once the module is imported, ``app.tasks.grouping_sentinel``
    # is the module, not the task (as with the flow and grid sentinels).
    tasks.celery_app.tasks["app.tasks.grouping_sentinel"].run(post=False, file_issues=False)
    assert seen == {"label": "grouping_sentinel", "run": ("run", {"post": False, "file_issues": False})}


def test_a_null_frame_is_not_called_a_title_with_no_number():
    # #12249: the writer stores "frame": null both when the title states no
    # number and when the model's number failed the title check, so the post
    # must not claim the first.
    c = counts([row("KXA-1", frame_type="null")])
    body = compose(c)
    assert "1 stored null (no number in the title, or one that failed the title check)" in body
    assert "titles with no number" not in body
