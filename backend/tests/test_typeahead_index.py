"""Option D (#1866, LAT-P067): the typeahead index's projections, hashing and D4 sentinel.

WHAT THESE TESTS ARE FOR, stated because #1866 has a specific history of tests
that passed while proving nothing: a warmer whose `fresh` skip branch could
never fire, and two tests that stayed green while asserting a model production
had already refuted. So each test below names the failure it would catch.

The pure core (`content_hash_for`, `compare_projections`, the `project_*`
family) is tested WITHOUT a database on purpose. D4's requirement is that the
sentinel DETECTS AN INJECTED DRIFT, and a detector whose only interesting
property can be exercised only against live Postgres is a detector whose one
interesting property is untested. There is no local Postgres in this sandbox
(`reference_no_local_postgres_sandbox`), so a DB-only proof would be a proof
that never runs here at all.
"""

import pytest

from app.tasks.typeahead_index import (
    ENTITY_TYPES,
    EVENT,
    FUTURES_MARKET,
    FUTURES_OUTCOME,
    SENTINEL_DRIFT_THRESHOLD,
    TEAM,
    DriftReport,
    Projection,
    _alias_strings,
    _norm,
    _search_text,
    compare_projections,
    content_hash_for,
    project_event,
    project_futures_market,
    project_futures_outcome,
    project_team,
)


class _Row:
    """Minimal stand-in for an ORM row. Attribute access only, which is all the
    projections use — deliberately not a Mock, so a projection that reaches for
    a column that does not exist raises instead of silently returning a Mock
    whose `str()` is a plausible-looking string."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


# --- content_hash ------------------------------------------------------------
class TestContentHash:
    def test_fits_in_signed_bigint(self):
        """The bug this catches fires on ~HALF of all inputs.

        PostgreSQL BIGINT is signed. An unsigned 64-bit digest overflows on
        insert for every value >= 2**63 — frequent enough to look like
        corruption, rare enough that a three-row fixture can easily miss it. So
        this asserts over a spread of inputs, not one.
        """
        for i in range(500):
            value = content_hash_for(f"Team {i}", f"team {i} alias", "nba", float(i))
            assert -(2**63) <= value < 2**63, f"hash out of signed range at i={i}: {value}"

    def test_is_stable_across_calls(self):
        a = content_hash_for("Boston Red Sox", "boston red sox bos", "baseball_mlb", 1.0)
        b = content_hash_for("Boston Red Sox", "boston red sox bos", "baseball_mlb", 1.0)
        assert a == b

    def test_changes_when_any_field_changes(self):
        base = content_hash_for("A", "a", "nba", 1.0)
        assert content_hash_for("B", "a", "nba", 1.0) != base
        assert content_hash_for("A", "b", "nba", 1.0) != base
        assert content_hash_for("A", "a", "nfl", 1.0) != base
        assert content_hash_for("A", "a", "nba", 2.0) != base

    def test_none_sport_key_is_not_the_string_none(self):
        """`None` and the literal "None" must not collide.

        A market with no category and a market whose category is the four
        characters "None" are different rows, and an f-string interpolation
        would have made them the same one.
        """
        assert content_hash_for("A", "a", None, 1.0) != content_hash_for("A", "a", "None", 1.0)

    def test_float_noise_does_not_rewrite_a_row(self):
        """Unrounded float noise in the digest would produce PERMANENT phantom
        drift: the sentinel would report a stale row on every pass for a row
        that never changed, and the one instrument meant to detect real drift
        would become the instrument nobody believes."""
        assert content_hash_for("A", "a", "nba", 0.1 + 0.2) == content_hash_for(
            "A", "a", "nba", 0.3
        )

    def test_field_boundary_is_not_forgeable_by_concatenation(self):
        """Without a separator, ("ab","c") and ("a","bc") hash identically —
        two genuinely different entities sharing one hash means one of them can
        never be seen as drifted."""
        assert content_hash_for("ab", "c", None, 0.0) != content_hash_for("a", "bc", None, 0.0)


# --- normalisation -----------------------------------------------------------
class TestNormalisation:
    def test_collapses_whitespace_and_lowercases(self):
        assert _norm("  Boston   RED  Sox\n") == "boston red sox"

    def test_none_is_empty(self):
        assert _norm(None) == ""

    def test_does_not_fold_accents(self):
        """Deliberate. The candidate-base work (#1459/#1475) established that
        identity stays collision-free precisely because it does NOT fold, and a
        fold that merges two distinct entities is a recall bug D2's gold probes
        would surface as a top-1 change."""
        assert _norm("Cádiz") == "cádiz"

    def test_search_text_dedupes_but_keeps_order(self):
        assert _search_text("Lakers", "lakers", "LA Lakers") == "lakers la lakers"

    def test_search_text_skips_empties(self):
        assert _search_text("Lakers", None, "", "  ") == "lakers"


class TestAliasStrings:
    def test_list(self):
        assert _alias_strings(["Lakers", "LA"]) == ["Lakers", "LA"]

    def test_dict_values(self):
        assert _alias_strings({"short": "LAL"}) == ["LAL"]

    def test_json_encoded_string(self):
        """`alternate_names` is JSONB but has been observed holding a JSON
        STRING. The live typeahead casts the column to text and matches the raw
        JSON, so a shape this helper silently drops is recall the trigram
        surface HAS and this table would not — a D2 failure by omission."""
        assert _alias_strings('["Lakers", "LA"]') == ["Lakers", "LA"]

    def test_malformed_blob_is_not_fatal(self):
        assert _alias_strings("not json at all") == ["not json at all"]

    def test_none_and_junk(self):
        assert _alias_strings(None) == []
        assert _alias_strings(12345) == []


# --- projections -------------------------------------------------------------
class TestProjections:
    def test_team_carries_every_arm_the_live_path_matches(self):
        """The live team arm matches name, abbreviation AND alternate_names.
        Dropping any one here is a recall regression visible only on the queries
        that used it — exactly the class D2 arms 46 probes against."""
        row = _Row(
            id=7,
            name="Boston Red Sox",
            abbreviation="BOS",
            location="Boston",
            alternate_names=["Red Sox", "BoSox"],
        )
        projection = project_team(row, "baseball_mlb")
        assert projection.entity_type == TEAM
        assert projection.entity_id == "7"
        assert projection.display_text == "Boston Red Sox"
        for needle in ("boston red sox", "bos", "red sox", "bosox"):
            assert needle in projection.search_text, needle
        assert projection.sport_key == "baseball_mlb"

    def test_event_carries_both_team_names(self):
        row = _Row(id=42, home_team_name="Tampa Bay Rays", away_team_name="Boston Red Sox")
        projection = project_event(row, "baseball_mlb")
        assert projection.entity_type == EVENT
        assert projection.display_text == "Boston Red Sox @ Tampa Bay Rays"
        assert "tampa bay rays" in projection.search_text
        assert "boston red sox" in projection.search_text

    def test_futures_market(self):
        row = _Row(id=9, name="Who wins Best Picture?", llm_sport_category="entertainment")
        projection = project_futures_market(row)
        assert projection.entity_type == FUTURES_MARKET
        assert projection.sport_key == "entertainment"
        assert projection.search_text == "who wins best picture?"

    def test_futures_outcome_carries_its_market_name(self):
        """A deliberate recall WIDENING, recorded so D2 is read knowing it: the
        live path reaches an outcome through its own name alone, but "best
        picture oppenheimer" names both and is the two-word case the current
        surface answers worst. If a gold disposition moves, this is the first
        suspect."""
        row = _Row(id=3, name="Oppenheimer")
        projection = project_futures_outcome(row, "Who wins Best Picture?")
        assert projection.entity_type == FUTURES_OUTCOME
        assert projection.display_text == "Oppenheimer"
        assert "oppenheimer" in projection.search_text
        assert "best picture" in projection.search_text

    def test_display_text_is_truncated_to_the_column_width(self):
        """VARCHAR(300). An over-long name must truncate in the projection, not
        raise at INSERT time in a background task nobody is watching."""
        row = _Row(id=1, name="x" * 900, llm_sport_category=None)
        assert len(project_futures_market(row).as_row(_NOW)["display_text"]) == 300

    def test_search_text_is_not_truncated(self):
        """`search_text` is TEXT, and truncating it would silently delete recall
        for exactly the long multi-alias rows that need it most."""
        row = _Row(id=1, name="y" * 900, llm_sport_category=None)
        assert len(project_futures_market(row).as_row(_NOW)["search_text"]) == 900

    def test_every_entity_type_is_projected_by_something(self):
        """Guards the vocabulary against a family being added to ENTITY_TYPES
        with no pager — which would make the builder skip it forever while
        reporting `complete`."""
        from app.tasks.typeahead_index import _PAGERS

        assert set(_PAGERS) == set(ENTITY_TYPES)


from datetime import datetime, timezone  # noqa: E402 — used by the truncation tests above

_NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


def _executable_source(path) -> str:
    """A file's code with every comment and string literal removed, lowercased.

    The migration guards below have to distinguish "this migration BUILDS a GIN"
    from "this migration EXPLAINS why it does not build a GIN", and the second
    is prose we deliberately want to keep. Grepping raw text cannot tell them
    apart; tokenising can.
    """
    import io
    import tokenize

    kept = []
    with open(path, "rb") as handle:
        for token in tokenize.tokenize(io.BytesIO(handle.read()).readline):
            if token.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            kept.append(token.string)
    return " ".join(kept).lower()


class TestAsRow:
    def test_row_has_exactly_the_model_columns(self):
        projection = Projection(TEAM, "1", "A", "a", "nba", 1.0)
        row = projection.as_row(_NOW)
        assert set(row) == {
            "entity_type",
            "entity_id",
            "display_text",
            "search_text",
            "sport_key",
            "rank_hint",
            "content_hash",
            "is_active",
            "refreshed_at",
        }
        assert row["is_active"] is True
        assert row["refreshed_at"] == _NOW


# --- D4: the drift detector --------------------------------------------------
class TestDriftDetection:
    """D4's registered bar: steady-state drift 0, AND an injected drift is
    DETECTED. Both directions are asserted — a detector that reports drift on
    everything passes the second half and is useless."""

    @staticmethod
    def _indexed(projections, mutate=None):
        out = {}
        for projection in projections:
            content_hash = projection.content_hash
            is_active = True
            if mutate is not None:
                content_hash, is_active = mutate(projection, content_hash, is_active)
            if content_hash is None:
                continue  # simulates a missing row
            out[(projection.entity_type, projection.entity_id)] = (content_hash, is_active)
        return out

    @staticmethod
    def _sample(n=50):
        return [
            Projection(TEAM, str(i), f"Team {i}", f"team {i}", "nba", 1.0) for i in range(n)
        ]

    def test_clean_index_reports_zero_drift(self):
        sample = self._sample()
        report = compare_projections(sample, self._indexed(sample))
        assert report.drifted == 0
        assert report.drift_rate == 0.0
        assert report.is_clean
        assert report.clean == 50

    def test_detects_injected_content_drift(self):
        """THE D4 TEST. One row's source content changes and the index does not
        follow: the sentinel must SEE it.

        Detection and alarming are asserted separately on purpose, and the first
        draft of this test conflated them: it injected 1 drifted row in 50 and
        asserted `not is_clean`, which is wrong — 1/50 is exactly 0.02 and the
        threshold is inclusive, so it reads clean. Seeing the row and shouting
        about it are two different properties, and a test that only checks the
        shout cannot tell a detector that missed the row from one that found it
        and correctly stayed quiet.
        """
        sample = self._sample()

        def mutate(projection, content_hash, is_active):
            if projection.entity_id == "17":
                return content_hash + 1, is_active
            return content_hash, is_active

        report = compare_projections(sample, self._indexed(sample, mutate))
        assert report.stale == 1, "the injected drift was not detected"
        assert report.drifted == 1
        assert report.clean == 49

    def test_the_threshold_is_inclusive_and_that_is_deliberate(self):
        """Pins the boundary so a later reader does not "fix" it in either
        direction. Exactly at the threshold reads CLEAN; one row more does not.
        """
        sample = self._sample(50)

        def one_row(projection, content_hash, is_active):
            return (content_hash + 1, is_active) if projection.entity_id == "17" else (content_hash, is_active)

        def two_rows(projection, content_hash, is_active):
            return (
                (content_hash + 1, is_active)
                if projection.entity_id in {"17", "18"}
                else (content_hash, is_active)
            )

        at_threshold = compare_projections(sample, self._indexed(sample, one_row))
        assert at_threshold.drift_rate == 0.02
        assert at_threshold.is_clean, "exactly at the threshold is tolerated"

        over = compare_projections(sample, self._indexed(sample, two_rows))
        assert over.drift_rate == 0.04
        assert not over.is_clean, "one row past the threshold must trip the alarm"

    def test_detects_a_missing_row(self):
        sample = self._sample()

        def mutate(projection, content_hash, is_active):
            return (None, is_active) if projection.entity_id == "3" else (content_hash, is_active)

        report = compare_projections(sample, self._indexed(sample, mutate))
        assert report.missing == 1
        assert report.drifted == 1

    def test_detects_a_tombstoned_row_whose_source_is_live(self):
        sample = self._sample()

        def mutate(projection, content_hash, is_active):
            return (content_hash, False) if projection.entity_id == "9" else (content_hash, True)

        report = compare_projections(sample, self._indexed(sample, mutate))
        assert report.inactive == 1
        assert report.drifted == 1

    def test_an_inactive_row_is_counted_once_not_twice(self):
        """A tombstoned row with a stale hash is ONE drifted row. Double-counting
        would push drift_rate above 1.0 and make the threshold meaningless."""
        sample = self._sample(10)

        def mutate(projection, content_hash, is_active):
            return (content_hash + 1, False)

        report = compare_projections(sample, self._indexed(sample, mutate))
        assert report.sampled == 10
        assert report.drifted == 10
        assert report.drift_rate == 1.0

    def test_threshold_tolerates_normal_churn_but_not_a_real_drift(self):
        """The threshold is NOT zero, and that is deliberate: a row legitimately
        changes between the builder's last visit and the sentinel's read, and an
        alarm that fires during normal operation is an alarm nobody reads — the
        retired grid health score, verbatim. But it must still be tight enough
        to catch a real one."""
        clean = DriftReport(sampled=1000, missing=0, stale=15, inactive=0, clean=985)
        assert clean.drift_rate == 0.015
        assert clean.is_clean, "1.5% is inside the tolerance"

        drifting = DriftReport(sampled=1000, missing=0, stale=30, inactive=0, clean=970)
        assert drifting.drift_rate == 0.03
        assert not drifting.is_clean, "3% must trip the alarm"
        assert SENTINEL_DRIFT_THRESHOLD == 0.02

    def test_empty_sample_is_clean_not_a_divide_by_zero(self):
        report = compare_projections([], {})
        assert report.sampled == 0
        assert report.drift_rate == 0.0
        assert report.is_clean


# --- the moving event window, and the reap it forces -------------------------
class TestEventWindow:
    """The event arm is the only source predicate here that MOVES, and getting
    it wrong was worth 163x in rows.

    Measured on production 2026-08-18, which is how the defect was found before
    the table ever shipped:

        `commence_time >= now - 120 days`              -> 104,907 rows
        the LIVE /typeahead window (below)             ->     644 rows

    The first draft used the 120-day form, reasoning that the typeahead "has
    never offered a game from three years ago". True, and irrelevant: the bound
    it replaced was not unbounded, and the draft was a recall EXPANSION over
    rows the live surface can never return. D2 (equivalence) and D3 (sizing)
    were both wrong from that one line.
    """

    def test_the_window_matches_the_live_typeahead_arm(self):
        """`routes/events.py`'s event pool query is
        `status IN ('live','scheduled')` AND `commence_time` in
        [now - 1h, now + 7d]. These constants are a COPY of that, so they are
        pinned — if the live arm moves, this must move with it or the index
        silently stops being equivalent."""
        from app.tasks.typeahead_index import (
            EVENT_STATUSES,
            EVENT_WINDOW_FUTURE_DAYS,
            EVENT_WINDOW_PAST_HOURS,
        )

        assert EVENT_WINDOW_PAST_HOURS == 1
        assert EVENT_WINDOW_FUTURE_DAYS == 7
        assert set(EVENT_STATUSES) == {"live", "scheduled"}

    def test_the_window_is_relative_to_now_and_ordered(self):
        from app.tasks.typeahead_index import _event_window

        floor, ceil = _event_window()
        assert floor < ceil
        assert (ceil - floor).days == 7

    def test_every_family_has_a_source_id_definition(self):
        """The reap and the sentinel's orphan check share ONE definition of
        "belongs in the index". Two definitions is one that drifts, and then one
        of them is wrong and neither is obviously so."""
        from app.tasks.typeahead_index import _source_id_select

        for family in ENTITY_TYPES:
            assert _source_id_select(family) is not None

    def test_an_unknown_family_raises_rather_than_reaping_everything(self):
        """A typo'd family name must NOT fall through to a select that matches
        nothing — `entity_id NOT IN (<empty>)` would tombstone the entire
        family. Loud is the only safe failure here."""
        from app.tasks.typeahead_index import _source_id_select

        with pytest.raises(ValueError):
            _source_id_select("concpet")


# --- wiring ------------------------------------------------------------------
class TestWiring:
    def test_both_tasks_are_enrolled_with_a_terminal(self):
        """Enrolling a task in ENFORCED_TASKS without a `terminal` in its summary
        is a NO-OP: the summary classifies as a non-authoritative unknown and
        still reads GREEN. So enrollment is asserted TOGETHER with the contract
        actually being spoken."""
        from app.utils.task_verdict import ENFORCED_TASKS, verdict_for

        assert "rebuild_typeahead_index" in ENFORCED_TASKS
        assert "typeahead_index_sentinel" in ENFORCED_TASKS

        complete = verdict_for(
            "rebuild_typeahead_index",
            {"terminal": "complete", "scanned": 10, "written": 3, "cursor_persisted": True},
        )
        assert complete.verdict == "complete"
        assert complete.authoritative

    def test_a_budget_truncated_pass_is_not_green(self):
        """The whole reason this task is enrolled. "The sweep is behind" and
        "the sweep is caught up" look identical from outside (gotcha #53)."""
        from app.utils.task_verdict import verdict_for

        verdict = verdict_for(
            "rebuild_typeahead_index",
            {"terminal": "partial", "scanned": 4000, "written": 4000, "stopped_at": "futures_outcome"},
        )
        assert verdict.verdict == "partial"
        assert not verdict.is_green
        assert verdict.blocks_success

    def test_an_unpersisted_cursor_is_a_failure_even_though_rows_were_written(self):
        from app.utils.task_verdict import verdict_for

        verdict = verdict_for(
            "rebuild_typeahead_index",
            {"terminal": "failed", "scanned": 4000, "written": 4000, "cursor_persisted": False},
        )
        assert verdict.verdict == "failed"
        assert not verdict.is_green

    def test_a_drifting_sentinel_run_is_not_green(self):
        from app.utils.task_verdict import verdict_for

        verdict = verdict_for(
            "typeahead_index_sentinel",
            {"terminal": "failed", "errors": ["drift 0.19 exceeds 0.02"]},
        )
        assert verdict.verdict == "failed"
        assert not verdict.is_green

    def test_an_empty_index_is_no_work_not_drift(self):
        """Reporting 100% drift while the initial backfill is still running would
        make the sentinel scream for the whole build and train everyone to
        ignore it."""
        from app.utils.task_verdict import verdict_for

        verdict = verdict_for(
            "typeahead_index_sentinel", {"terminal": "no_work", "reason": "index_empty"}
        )
        assert verdict.verdict == "unknown"
        assert verdict.authoritative
        assert not verdict.is_green

    def test_orphans_fail_the_run_even_with_zero_drift(self):
        """The direction the sampled comparison cannot see.

        `compare_projections` walks live sources and asks "is each one indexed
        correctly?" — never "does the index hold rows the sources no longer
        have?". Those are different failures, and the second is what a MOVING
        source predicate produces: an event ages out of the 7-day window, its
        row is never revisited, and it stays `is_active` forever.

        A run can therefore have PERFECT drift and still be serving stale rows,
        so `orphans_total` fails the terminal on its own terms. It is a COUNT
        over the whole table, not a contribution to a rate over a sample —
        adding a total to a rate would produce a number meaning nothing.
        """
        from app.utils.task_verdict import verdict_for

        verdict = verdict_for(
            "typeahead_index_sentinel",
            {
                "terminal": "failed",
                "overall": {"drift_rate": 0.0},
                "orphans_total": 412,
                "errors": ["typeahead_index holds 412 ACTIVE rows whose source no longer qualifies"],
            },
        )
        assert verdict.verdict == "failed"
        assert not verdict.is_green

    def test_a_clean_sentinel_run_is_green(self):
        """The other direction. An alarm that can never read GREEN is an alarm
        with no signal in it."""
        from app.utils.task_verdict import verdict_for

        verdict = verdict_for(
            "typeahead_index_sentinel",
            {"terminal": "complete", "indexed_rows": 380000, "overall": {"drift_rate": 0.0}},
        )
        assert verdict.verdict == "complete"
        assert verdict.is_green

    def test_both_tasks_are_registered_and_route_to_heavy(self):
        """`background` is the queue #1609 proved has ~one effective slot, and
        whose depth read 3,014 at this window's Phase 0. A new latency-tolerant
        multi-minute resident must not land there."""
        from app.tasks import HEAVY_TASKS, celery_app

        for name in ("app.tasks.rebuild_typeahead_index", "app.tasks.typeahead_index_sentinel"):
            assert name in celery_app.tasks, f"{name} not registered"
            assert name in HEAVY_TASKS, f"{name} not in HEAVY_TASKS"
            assert celery_app.conf.task_routes.get(name, {}).get("queue") == "heavy"

    def test_both_tasks_carry_a_soft_time_limit_under_the_global_hard_limit(self):
        """The global `task_time_limit` is 300s and it is a HARD SIGKILL: a task
        without a soft limit vanishes into `no_data` rather than reporting a
        failure (`project_celery_sigkill_untracked`)."""
        from app.tasks import celery_app

        for name in ("app.tasks.rebuild_typeahead_index", "app.tasks.typeahead_index_sentinel"):
            task = celery_app.tasks[name]
            assert task.soft_time_limit, f"{name} has no soft_time_limit"
            assert task.time_limit, f"{name} has no time_limit"
            assert task.soft_time_limit < task.time_limit < 300, (
                f"{name}: soft={task.soft_time_limit} hard={task.time_limit} "
                "must both sit under the 300s global SIGKILL"
            )

    def test_the_builder_budget_fits_inside_its_own_soft_limit(self):
        """Bound the LONGEST UNINTERRUPTED OP, not just the loop boundary
        (`project_budget_guard_inner_op`). The default budget plus one full page
        timeout must still land inside the soft limit, or the task can honour its
        budget at every check and still be killed inside a page."""
        from app.tasks import celery_app
        from app.tasks.typeahead_index import DEFAULT_BUDGET_SECONDS, PAGE_TIMEOUT_SECONDS

        soft = celery_app.tasks["app.tasks.rebuild_typeahead_index"].soft_time_limit
        assert DEFAULT_BUDGET_SECONDS + PAGE_TIMEOUT_SECONDS <= soft, (
            f"budget {DEFAULT_BUDGET_SECONDS}s + page {PAGE_TIMEOUT_SECONDS}s "
            f"exceeds soft limit {soft}s"
        )

    def test_the_sentinel_beat_stays_clear_of_the_protected_morning_window(self):
        """#233's window is 07:10-07:45 UTC (flow/grid/horizon/settled). A daily
        sentinel dropped inside it re-creates the contention #233 exists to
        prevent, on the lane that absorbs it."""
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["typeahead-index-sentinel"]
        schedule = entry["schedule"]
        assert schedule.hour == {7}
        assert schedule.minute == {50}, "must fire after the 07:45 settled sentinel"

    def test_the_builder_beat_avoids_the_two_heavy_slot_hogs(self):
        """`prediction_market_match` fires :05/:20/:35/:50 and
        `precompute_calibration_main` at :15 — between them they can hold both
        heavy slots. The builder is scheduled into the quiet half."""
        from app.tasks import celery_app

        minutes = celery_app.conf.beat_schedule["rebuild-typeahead-index"]["schedule"].minute
        assert minutes == {23, 53}
        assert not (minutes & {5, 15, 20, 35, 50})

    def test_the_migration_creates_no_gin_index(self):
        """CONDITION 2 OF THE ASSIGNED SLOT, asserted rather than trusted to a
        docstring. The ~90 MB trigram GIN must be built out of band with
        CREATE INDEX CONCURRENTLY on a one-off dyno — gotcha #31, which is the
        May 22 outage verbatim: CONCURRENTLY in the release phase hangs Heroku's
        ~5 min timeout and takes the site down.

        This test exists because the failure mode is a LATER window reading only
        the summary line and helpfully folding the index back in."""
        from pathlib import Path

        import re

        source = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "add_typeahead_index.py"
        code = _executable_source(source)
        # WORD boundary over EXECUTABLE code only, and both halves of that were
        # bugs in this assertion's first two drafts. Substring matching hit "gin"
        # inside `sa.BigInteger()`; matching the whole file then hit the comment
        # that EXPLAINS why the GIN is not here. A guard that cries wolf on its
        # own correct subject gets deleted by the next person, which would leave
        # condition 2 of the slot unguarded — so it reads code, and the prose
        # about the GIN stays exactly where it is useful.
        assert not re.search(r"\bgin\b", code), (
            f"the trigram GIN must not be in the migration (gotcha #31): {code}"
        )
        assert "concurrently" not in code, "CONCURRENTLY must never run in the release phase"
        assert "gin_trgm_ops" not in code
        assert "postgresql_using" not in code

    def test_the_migration_revision_id_is_within_alembic_s_limit(self):
        """Gotcha #1: Alembic truncates past 32 characters and the chain breaks
        on a LATER release, not the one that introduced it."""
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "add_typeahead_index.py"
        for line in source.read_text().splitlines():
            if line.startswith("revision = "):
                revision = line.split("=", 1)[1].strip().strip('"').strip("'")
                assert len(revision) <= 32, f"revision id {revision!r} is {len(revision)} chars"
                break
        else:  # pragma: no cover
            pytest.fail("no revision id found in the migration")

    def test_the_migration_moves_no_data(self):
        """Condition 1 (table-only) and condition 3 (the ~380k-row backfill is a
        TASK). A migration that moves data turns a 5-second release into an
        outage."""
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "add_typeahead_index.py"
        code = _executable_source(source)
        for forbidden in ("insert into", "bulk_insert", "op . execute", "select "):
            assert forbidden not in code, f"migration must not move data: found {forbidden!r}"
