"""#2199 — guards for the high-value futures price refresher.

The class this file exists to catch is not "the refresher has a bug". It is the
one that produced #2199 in the first place: **price capture for a known market
riding on a bounded discovery scan**, so that a poll reporting success can leave
the platform's most valuable markets dark for a month. The tests below pin the
four properties that keep that from coming back:

1. The selection predicate is value-floored and liveness-floored, and the guard
   endpoint asserts over the SAME set the task refreshes — a guard covering a
   different population than the fix is how a breach reads green.
2. The ordering has no fixed point. Oldest-capture-first is the intuitive choice
   and it is a trap: an unpriceable market pins the head of the queue forever.
3. The task's terminal is honest — attempted-and-wrote-nothing is `failed`.
4. The writer refuses to create identity, refuses settled outcomes, and refuses
   a null price.
"""

import json
import re
from pathlib import Path

import pytest

from app.tasks import futures_price_refresh as fpr
from app.utils.task_verdict import ENFORCED_TASKS, classify_summary

_MODULE_SRC = Path(fpr.__file__).read_text()
_ADMIN_SRC = (
    Path(fpr.__file__).parent.parent / "routes" / "admin_source_health.py"
).read_text()


class TestSelectionPredicate:
    """The fix and its guard must cover one population, not two."""

    def test_predicate_carries_every_floor(self):
        sql = fpr._CANDIDATE_SQL.text
        assert "fm.status = 'open'" in sql
        assert "fm.volume >= :volume_floor" in sql
        # Gotcha #33: settled Kalshi markets keep status='open', so `status`
        # alone is not a liveness test. The resolution-date bound is what keeps
        # the dead out of an ordering that would otherwise never release them.
        assert "resolution_date > NOW()" in sql

    def test_tier_is_an_admission_and_never_a_fence(self):
        """#3315. The clause that hid the entire front page for 46 days.

        `market_tier` still appears in the predicate, so a substring test for it
        proves nothing — the question is which DIRECTION it points. It may admit
        a tier-1 row whose volume we never recorded; it may not exclude a row for
        being tier 2. All seven Polymarket cards on Discover page one were tier
        2 on 2026-09-05, one of them 13.7 points wrong on $114M of volume.

        Asserted on the composed predicate rather than on a comment, and both
        directions are asserted: dropping the `volume IS NULL` conjunct turns the
        admission back into a fence and reddens the second half.
        """
        assert fpr.HIGH_VALUE_SQL.count("market_tier") == 1
        assert "market_tier = 1 AND fm.volume IS NULL" in fpr.HIGH_VALUE_SQL
        # The value arm names no tier at all: volume alone admits Brazil.
        assert "market_tier" not in fpr.VALUE_MEASURED_SQL
        # and the two halves are a disjunction, not a conjunction.
        assert " OR " in fpr.HIGH_VALUE_SQL
        assert " AND " not in fpr.HIGH_VALUE_SQL.replace(
            fpr.VALUE_TIER1_UNPRICED_SQL, ""
        )

    def test_null_volume_is_not_read_as_a_measured_zero(self):
        """The second hole: `volume >= 10000` is NULL-rejecting.

        1,199 of 3,081 open tier-1 markets carry NULL volume — 39% of the very
        population the sweep believed it covered. "We never measured this" and
        "this is worthless" are opposite facts that were arriving as one.

        Expressed as SQL semantics rather than as a string match, so a rewrite
        that keeps the words and loses the meaning fails here.
        """
        import sqlite3

        con = sqlite3.connect(":memory:")
        con.execute(
            "CREATE TABLE fm (id INT, market_tier INT, volume INT)"
        )
        con.executemany(
            "INSERT INTO fm VALUES (?,?,?)",
            [
                (1, 1, None),      # tier 1, unmeasured -> admitted
                (2, 2, 114_137_967),  # Brazil: tier 2, huge -> admitted
                (3, 2, None),      # tier 2, unmeasured -> not admitted
                (4, 5, 12),        # measured and small -> not admitted
            ],
        )
        where = fpr.HIGH_VALUE_SQL.replace("fm.", "").replace(
            ":volume_floor", "10000"
        )
        got = {r[0] for r in con.execute(f"SELECT id FROM fm WHERE {where}")}
        assert got == {1, 2}

    def test_uses_exists_not_max_captured_at(self):
        """MAX(captured_at) over the 179M-row snapshot table times out at 10s.

        Pinned because the aggregate form is the natural thing to write, reads
        correctly, and takes the task's own selector down in production — a
        selector that times out is a refresher that never runs.
        """
        sql = fpr._CANDIDATE_SQL.text
        assert "NOT EXISTS" in sql
        assert "MAX(" not in sql.upper()

    def test_guard_endpoint_uses_the_same_predicate(self):
        """A guard over a different set than the fix cannot prove the fix worked."""
        task_sql = _normalise(fpr._CANDIDATE_SQL.text)
        for name in ("_PRICE_DARK_SQL",):
            guard_sql = _normalise(_extract_sql_literal(_ADMIN_SRC, name))
            for clause in (
                "fm.status = 'open'",
                # #3315: the value test, both halves, on both sides.
                "fm.volume >= :volume_floor",
                "fm.market_tier = 1 and fm.volume is null",
                "fm.resolution_date > now()",
                "not exists",
            ):
                assert clause.lower() in guard_sql, f"{name} is missing {clause!r}"
                assert clause.lower() in task_sql

    def test_every_liveness_asker_composes_the_one_shared_string(self):
        """#2222 — clause-by-clause agreement is not the same as one predicate.

        The test above checks that five named clauses appear on both sides. It
        passed throughout the month `futures-price-freshness` was stuck red,
        because the clause the two sides were *missing* was missing from both.
        Six hand-copied WHERE blocks agree until the day one of them needs a
        sixth clause.

        This asserts something the clause list cannot: that every selector and
        every guard interpolates the SAME STRING, so a bound added in
        `futures_liveness` reaches all of them or none of them. Normalised
        because the f-strings indent it differently at each site.
        """
        import app.routes.admin_source_health as _health
        import app.tasks.tournament_price_refresh as _tpr
        from app.utils.futures_liveness import LIVE_MARKET_SQL

        shared = _normalise(LIVE_MARKET_SQL)
        assert shared, "the shared predicate must not be empty"

        askers = {
            "task._CANDIDATE_SQL": fpr._CANDIDATE_SQL.text,
            "task._REGISTERED_CANDIDATE_SQL": fpr._REGISTERED_CANDIDATE_SQL.text,
            # #3315: the served arm and the reachability census are askers too.
            # The served arm decides whether a card on page one gets a price at
            # all, so a liveness clause that reached everything except it would
            # be the #2222 drift with the front page as its blast radius.
            "task._SERVED_CANDIDATE_SQL": fpr._SERVED_CANDIDATE_SQL.text,
            "task._SERVED_REACHABLE_SQL": fpr._SERVED_REACHABLE_SQL.text,
            "task.ELIGIBLE_POOL_SQL": fpr.ELIGIBLE_POOL_SQL,
            "guard._PRICE_DARK_SQL": _health._PRICE_DARK_SQL,
            "guard._REGISTERED_SQL": _health._REGISTERED_SQL,
            # CERT-452: the seventh. `tournament_price_refresh` runs every ten
            # minutes against register-pinned Polymarket identities and was
            # outside this predicate entirely, so a market the hourly refresher
            # and its guard had both retired kept being fetched and its settled
            # outcomes overwritten.
            "tournament._LIVE_REGISTERED_CONDITIONS_SQL":
                _tpr._LIVE_REGISTERED_CONDITIONS_SQL,
        }
        for name, sql in askers.items():
            assert shared in _normalise(sql), f"{name} does not compose LIVE_MARKET_SQL"

    def test_the_census_cannot_be_satisfied_by_a_short_list(self):
        """CERT-452's structural finding, not just its instance.

        The dictionary above is hand-maintained, so it discovers nothing: it
        enumerated six askers for as long as there were seven, and the seventh
        was a Tier-1 unattended writer on a ten-minute cadence. This asserts the
        count so ADDING an asker without enrolling it fails here rather than in
        production — the same reason `ENFORCED_TASKS` needs a terminal.

        If you are here because you added a price asker: enrol it above, do not
        bump this number alone.
        """
        import inspect

        import app.routes.admin_source_health as _health
        import app.tasks.tournament_price_refresh as _tpr

        # #3315 made the composition two-level: sites that interpolate
        # LIVE_MARKET_SQL directly, and sites that compose it transitively
        # through ELIGIBLE_POOL_SQL (which is itself one of them). Counting only
        # the direct token would let a new asker join through the pool without
        # ever being enrolled, which is exactly the hole this census exists to
        # close.
        #
        # Went 9 -> 8 when the guard's two registered statements became one
        # (`_REGISTERED_SQL`): a REMOVED asker is as much a census event as an
        # added one, because the number is what makes the dictionary honest.
        enrolled = 8
        found = sum(
            inspect.getsource(mod).count("{LIVE_MARKET_SQL}")
            + inspect.getsource(mod).count("{ELIGIBLE_POOL_SQL}")
            for mod in (fpr, _health, _tpr)
        )
        assert found == enrolled + 1, (
            f"{found - 1} interpolation sites across the three asker modules but "
            f"{enrolled} enrolled in the census "
            f"(the +1 is the task's own remaining_stale census)"
        )

    def test_the_remaining_stale_census_is_an_asker_too(self):
        """The task's own closing count is the number the run REPORTS.

        It was the third copy of the predicate inside the task, and a census
        that measures a different set than the selector makes the run's own
        `remaining_stale` a number about nobody.
        """
        from app.utils.futures_liveness import LIVE_MARKET_SQL

        source = _normalise(_MODULE_SRC)
        # The census is built with an f-string, so the source carries the
        # interpolation and the module carries the result. Assert on the source:
        # there is no module-level constant to read for this one.
        assert "{LIVE_MARKET_SQL}" in _MODULE_SRC
        assert _MODULE_SRC.count("{LIVE_MARKET_SQL}") == 4, (
            "both pool branches, the by-id selector, the reachability census"
        )
        # #3315: the census now composes the whole ELIGIBLE POOL, not just the
        # liveness clause. A census that kept the liveness bounds but not the
        # widened value test would report the pre-#3315 number under the
        # post-#3315 name — the worst of both, because it reads like coverage.
        assert _MODULE_SRC.count("{ELIGIBLE_POOL_SQL}") == 2, (
            "the class selector plus the remaining_stale census"
        )
        assert _normalise(LIVE_MARKET_SQL) in _normalise(fpr._CANDIDATE_SQL.text)
        assert "select count(*) from futures_markets fm" in source

    def test_guard_endpoint_reads_snapshots_not_updated_at(self):
        """`futures_markets.updated_at` is what made this class invisible.

        The discovery polls stamp `updated_at` on rows they re-read while
        capturing no price, so a freshness check built on it reads green over a
        month-dark market. Only `futures_odds_snapshots.captured_at` answers
        whether a price was actually captured.
        """
        for name in ("_PRICE_DARK_SQL",):
            sql = _extract_sql_literal(_ADMIN_SRC, name)
            assert "futures_odds_snapshots" in sql
            assert "s.captured_at" in sql
            assert "updated_at" not in sql


class TestOrderingHasNoFixedPoint:
    def test_orders_by_value_not_by_staleness(self):
        """Oldest-capture-first is the trap, and it is the intuitive choice.

        A market whose book cannot be priced never gets a snapshot, so its
        last-capture stays NULL forever. Under `ORDER BY last_capture NULLS
        FIRST` it holds the head of the queue on every run, permanently starving
        everything behind it — the same starvation shape (gotcha #41) that this
        whole task exists to undo. Volume DESC has no such fixed point.
        """
        sql = fpr._CANDIDATE_SQL.text
        assert "ORDER BY fm.volume DESC" in sql
        assert "NULLS FIRST" not in sql.upper()

    def test_attempt_markers_record_attempts_not_successes(self):
        """The rotation only works if a FAILED attempt also advances the cursor.

        Marking successes would put every unpriceable market back at the front on
        the very next run, which is the fixed point again with extra steps.
        """
        assert "_mark_attempted(attempted_ids" in _MODULE_SRC
        # Both loops record through one helper, called BEFORE the fetch is known
        # to have worked. Counting `_note_attempt(` rather than the raw appends
        # keeps this honest: `registered_attempted_ids.append(` contains
        # `attempted_ids.append(` as a substring, so the old raw count passed for
        # the wrong reason the moment the second list existed.
        assert "def _note_attempt(" in _MODULE_SRC
        assert _MODULE_SRC.count("_note_attempt(market)") == 3, (
            "one call per source loop plus the unaddressable-poly-row path"
        )

    def test_scan_is_wider_than_one_budget(self):
        """Without headroom, a run whose top-N were all just attempted does nothing.

        #3315 moved the headroom from an outer `scan_limit` to the POOL, because
        on the widened query an outer LIMIT bounded no work at all — production's
        plan sorts above the anti-join, so every open market was probed against
        the 179M-row snapshot table before the LIMIT applied. The property being
        guarded is unchanged: the scan must see more than one run can take.
        """
        assert fpr.VALUE_POOL_LIMIT > fpr.DEFAULT_MARKET_BUDGET
        assert fpr.UNPRICED_POOL_LIMIT > fpr.KALSHI_MARKET_BUDGET

    def test_the_pool_is_materialised_so_the_planner_cannot_undo_it(self):
        """PG12+ inlines a single-reference CTE, which restores the bad plan.

        Not a style point and not cosmetic: measured on production 2026-09-05,
        the inlined form did not finish inside 10s at ANY outer LIMIT including
        1,500, while the materialised two-pool form returned the same rows in
        2.8s + 9.4s. Dropping the keyword is a silent revert to a selector that
        times out, and a selector that times out is a refresher that never runs.
        """
        assert "AS MATERIALIZED" in fpr.ELIGIBLE_POOL_SQL
        assert "AS MATERIALIZED" in fpr._CANDIDATE_SQL.text


class TestTerminalIsHonest:
    """Gotcha #53 / task_verdict: "it returned" is not "it worked"."""

    def test_enrolled_in_enforced_tasks(self):
        assert "futures_price_refresh" in ENFORCED_TASKS

    @pytest.mark.parametrize(
        "stats,expected",
        [
            ({"markets_attempted": 0, "snapshots_written": 0, "budget_hit": False, "errors": []}, "no_work"),
            # The founding case: markets were fetched, nothing was written.
            ({"markets_attempted": 40, "snapshots_written": 0, "budget_hit": False, "errors": []}, "failed"),
            ({"markets_attempted": 40, "snapshots_written": 12, "budget_hit": True, "errors": []}, "partial"),
            ({"markets_attempted": 40, "snapshots_written": 12, "budget_hit": False, "errors": ["x"]}, "partial"),
            ({"markets_attempted": 40, "snapshots_written": 40, "budget_hit": False, "errors": []}, "complete"),
        ],
    )
    def test_terminal(self, stats, expected):
        assert fpr._terminal(stats) == expected

    def test_only_complete_reads_green(self):
        """Enrolment is a no-op unless the non-complete terminals block success."""
        assert classify_summary({"terminal": "complete"}).is_green
        for terminal in ("failed", "partial", "no_work"):
            verdict = classify_summary({"terminal": terminal})
            assert not verdict.is_green, terminal
            assert verdict.authoritative, terminal

    def test_empty_run_distinguishes_its_two_causes(self):
        """"Nothing was stale" and "everything stale was just attempted" are opposite.

        Gotcha #53: an empty result is a response shape, not an absence. Collapsing
        the two into one silent return is how a wedged refresher looks healthy.
        """
        assert '"complete" if not scan else "no_work"' in _MODULE_SRC


class TestWriterRefusals:
    def test_never_creates_an_outcome(self):
        """Price-only. Minting identity here would bypass categorisation and tiering."""
        assert "pg_insert(FuturesOutcome)" not in _MODULE_SRC
        assert "pg_insert(FuturesMarket)" not in _MODULE_SRC
        assert 'stats["unknown_outcomes"] += 1' in _MODULE_SRC

    def test_never_touches_a_settled_outcome(self):
        """Gotcha #21: a settled book stops quoting; re-pricing it can only corrupt.

        This assertion used to read ``assert "is_winner IS NULL" in _MODULE_SRC``
        and it is the reason 19,906 tests passed over a task that could not write
        a single row. A grep of the implementation passes **iff the bug is
        present**: `is_winner` is non-nullable with `default=False`, so `IS NULL`
        matched zero production rows and the writer was inert by construction.

        Two changes. The negative assertion is now the load-bearing one — the
        broken predicate must be ABSENT, so re-introducing it fails here. And the
        real gate for this property is no longer a grep at all: it is
        `tests/integration/test_futures_price_refresh_writes_pg.py`, which seeds
        an outcome the way production seeds it and asserts a snapshot lands.
        """
        assert "is_winner IS NOT TRUE" in _MODULE_SRC
        assert "is_winner IS NULL" not in _MODULE_SRC

    def test_the_settled_refusal_has_a_data_level_gate(self):
        """A source-text assertion may not be the only guard on this property.

        Pinned so the data-level file cannot be deleted or renamed leaving the
        grep above as the sole cover — which is precisely the state that shipped.
        """
        pg_gate = (
            Path(__file__).parent
            / "integration"
            / "test_futures_price_refresh_writes_pg.py"
        )
        assert pg_gate.exists(), "the real-Postgres writer gate is missing"
        src = pg_gate.read_text()
        assert "is_winner=False" in src, "must seed the way production seeds"
        assert "SEARCH_TEST_DATABASE_URL" in src, "must be armed in the CI PG job"

    def test_never_writes_a_null_or_out_of_range_probability(self):
        assert "if prob is None or not (0 < prob < 1):" in _MODULE_SRC

    def test_reuses_the_source_price_guards_rather_than_reimplementing(self):
        """A second, subtly different price derivation is a second set of bugs.

        `_kalshi_yes_probability` carries the wide/one-sided-book refusal;
        `_resolve_market_probability` carries the placeholder gate (gotcha #19);
        `complementary_book` is the No side's book as an identity rather than an
        estimate (CAL-P095); `field_is_incoherent` carries #1527. This path must
        not be able to write a price the ingest path would have refused.
        """
        assert "from app.tasks.kalshi import _kalshi_yes_probability" in _MODULE_SRC
        assert "from app.tasks.polymarket import _resolve_market_probability" in _MODULE_SRC
        assert "complementary_book" in _MODULE_SRC
        assert "field_is_incoherent" in _MODULE_SRC

    def test_kalshi_adapter_parses_through_the_service(self):
        """Kalshi v2 quotes prices as decimal-string dollars OR integer cents.

        `_parse_market` resolves that pair. Re-deriving it here risks writing 95
        where 0.95 belongs — a coherent-looking wrong price, which no downstream
        check would catch.
        """
        assert "service._parse_event(raw)" in _MODULE_SRC
        assert "/ 100" not in _MODULE_SRC


class TestWiring:
    def test_beat_is_registered_and_routed_to_heavy(self):
        from app.tasks import HEAVY_TASKS, celery_app

        entry = celery_app.conf.beat_schedule["refresh-stale-futures-prices-hourly"]
        assert entry["task"] == "app.tasks.refresh_stale_futures_prices"
        assert entry["options"]["queue"] == "heavy"
        # Background has ~one effective slot for ~40 beats; a 420s-budget task
        # placed there closes the queue rather than sharing it.
        assert "app.tasks.refresh_stale_futures_prices" in HEAVY_TASKS
        assert (
            celery_app.conf.task_routes["app.tasks.refresh_stale_futures_prices"]
            == {"queue": "heavy"}
        )

    def test_does_not_collide_with_the_hourly_heavy_precompute(self):
        from app.tasks import celery_app

        ours = celery_app.conf.beat_schedule["refresh-stale-futures-prices-hourly"]
        precompute = celery_app.conf.beat_schedule["precompute-calibration-main"]
        assert ours["schedule"].minute != precompute["schedule"].minute

    def test_wall_budget_sits_under_the_soft_limit(self):
        from app.tasks import celery_app

        task = celery_app.tasks["app.tasks.refresh_stale_futures_prices"]
        assert fpr._TIME_BUDGET_S < task.soft_time_limit < task.time_limit

    def test_the_first_loop_cannot_spend_the_whole_wall(self):
        """Per-source MARKET budgets do not bound per-source WALL time.

        The two loops run in sequence against one clock with Polymarket first, so
        a slow Gamma consumes the entire 420s and the Kalshi loop — the larger
        backlog — never runs. Splitting the market budget without splitting the
        clock leaves the starvation exactly where it was, one level up.

        Both bounds are asserted, not just the existence of the constant: it must
        leave the Kalshi loop more than its measured worst case (175s), and it
        must be comfortably above Polymarket's own (78s) so it binds only on a
        pathological run.
        """
        assert fpr._POLYMARKET_WALL_BUDGET_S < fpr._TIME_BUDGET_S
        assert fpr._TIME_BUDGET_S - fpr._POLYMARKET_WALL_BUDGET_S > 175
        assert fpr._POLYMARKET_WALL_BUDGET_S > 2 * 78
        # And the loop reads the share, not the whole wall.
        assert "poly_deadline = min(" in _MODULE_SRC
        assert "started > poly_deadline" in _MODULE_SRC

    def test_the_per_source_budgets_cover_their_backlogs_within_the_stale_window(self):
        """The convergence claim, as arithmetic rather than as prose.

        The attempt marker's TTL is the staleness window, so a source's whole
        standing backlog has to fit in `budget x (window / beat period)` runs or
        the 6h invariant is unreachable and `futures-price-freshness` stays red
        forever — the #2222 shape, arrived at from the other side.

        Backlogs measured on production 2026-09-05 under the widened predicate,
        pinned here so a budget cut has to argue with the number it breaks.
        """
        runs_per_window = fpr.STALE_AFTER_HOURS  # hourly beat, 6h window
        assert fpr.KALSHI_MARKET_BUDGET * runs_per_window >= 2_010
        assert fpr.POLYMARKET_MARKET_BUDGET * runs_per_window >= 1_974
        # ...and the two together must still fit the wall at their measured
        # per-market costs, or the budgets are a promise the clock cannot keep.
        wall = fpr.KALSHI_MARKET_BUDGET * 0.35 + fpr.POLYMARKET_MARKET_BUDGET * 0.065
        assert wall < fpr._TIME_BUDGET_S

    def test_staleness_window_matches_the_render_contract(self):
        """The producer and the renderer must not hold two definitions of stale.

        `utils/tournament_register.py::check_freshness` blocks a row from
        rendering as a confident live number past 6h (`LIVE_PRICE_STALE`,
        UX-P130). A refresher with a looser window would leave a permanent band
        where the board refuses to render a price that nothing is trying to
        refresh.

        Pinned as a bare constant rather than by reading the register: that
        module lives on the unmerged `program/ux-113` branch, and a test that
        imports across an integration boundary fails for a reason that has
        nothing to do with what it is guarding.
        """
        assert fpr.STALE_AFTER_HOURS == 6


class TestRegisteredMarketsAreReachable:
    """The class that emptied the US Open "More predictions" section.

    Measured in production 2026-08-27: all three markets behind that section
    were tier 5 (two at 837h stale, one at 215h), and `_CANDIDATE_SQL` admits
    only `market_tier = 1 AND volume >= 10_000`. The only rail that can reach a
    market the discovery polls cannot therefore excluded every curated prop
    **permanently** — not as a backlog, as a predicate. The page rendered its
    honest empty state and nothing anywhere was red.
    """

    def test_registered_arm_drops_the_value_bounds_and_keeps_the_liveness_bounds(self):
        sql = fpr._REGISTERED_CANDIDATE_SQL.text
        # The whole point: curation is the value floor for these rows.
        assert "market_tier" not in sql
        assert "volume_floor" not in sql
        # ...but a curated row is not a licence to re-animate the dead.
        # Gotcha #33: settled Kalshi markets keep status='open'.
        assert "fm.status = 'open'" in sql
        assert "resolution_date > NOW()" in sql
        assert "NOT EXISTS" in sql

    def test_the_committed_us_open_register_reaches_its_curated_props(self):
        """Behavioural, against the real committed file — not a shape assertion.

        The markets named here are the ones whose darkness Alex actually saw. If
        a collector regression drops them, the section empties again and this is
        the test that says so.

        THE THIRD MARKET LEFT ON PURPOSE. This pinned `53796`
        (`alcaraz-second-major`) until UX-P139 (`af888d29`) **de-curated** it at
        the source — "one question with two names in it, next to
        sinner-second-major" — and the pin then failed in the merge tree while
        passing on both sides alone (INT-141). Curation is a product decision
        this test may not out-vote: what a register curates is the register's
        call, and what this class guards is that whatever it curates is
        *reachable by the price rail*. Hence the two survivors below by name,
        and every id the file names — however many that is — by derivation in
        :meth:`test_every_market_the_us_open_register_names_is_reachable`.
        """
        from app.utils.tournament_register import registered_market_ids

        ids = registered_market_ids()
        for market_id, what in (
            (59172808, "sinner-competes"),
            (53795, "sinner-second-major"),
        ):
            assert market_id in ids, f"{what} ({market_id}) is not reachable"

    def test_every_market_the_us_open_register_names_is_reachable(self):
        """The class assertion, derived from the file — curation-edit proof.

        Read independently of the collector: this walks the register's ``props``
        section by name and asserts the rail reaches every market id in it. A
        curation edit that adds, drops or regroups a prop moves this test's own
        expectation with it, so a deliberate register change can never look like
        a rail regression again — while a collector that stops covering props
        still fails here, loudly, with the ids it lost.
        """
        from app.utils.tournament_register import REGISTER_DIR, registered_market_ids

        register = json.loads((REGISTER_DIR / "us-open-2026.json").read_text())
        props = register.get("props") or []
        assert props, "the committed register curates no props — nothing to reach"

        named: set[int] = set()

        def collect(node):
            if isinstance(node, dict):
                market_id = node.get("market_id")
                if isinstance(market_id, int) and not isinstance(market_id, bool):
                    named.add(market_id)
                for value in node.values():
                    collect(value)
            elif isinstance(node, list):
                for value in node:
                    collect(value)

        collect(props)
        assert named, "the committed props name no market ids at all"
        assert named <= registered_market_ids(), (
            f"curated props unreachable by the price rail: {sorted(named - registered_market_ids())}"
        )

    def test_a_prop_that_carries_a_list_of_markets_is_reached_too(self, tmp_path):
        """The incoming shape, pinned as a fixture rather than as a dependency.

        UX-P151 gives the two `*-second-major` markets ONE combined card, so that
        prop carries no top-level ``market_id`` at all — its ids live in a nested
        ``markets: [...]`` list. Walking the whole document already covers this;
        a props reader that had enumerated ``prop["market_id"]`` would have gone
        dark on both of them the day that card landed. Synthetic on purpose: this
        must hold before, during and after any register the UX lane commits.
        """
        from app.utils.tournament_register import registered_market_ids

        (tmp_path / "us-open-2026.json").write_text(
            json.dumps(
                {
                    "props": [
                        {"key": "sinner-competes", "market_id": 59172808},
                        {
                            "key": "second-major",
                            "title": "Who wins a second major this year?",
                            "markets": [
                                {"market_id": 53796, "market_external_id": "KXGRANDSLAM-CALC26"},
                                {"market_id": 53795, "market_external_id": "KXGRANDSLAM-JSIN26"},
                            ],
                        },
                    ]
                }
            )
        )
        assert registered_market_ids(directory=tmp_path) == {59172808, 53796, 53795}

    def test_it_also_reaches_the_four_outright_winner_fields(self):
        """CERT-404's population. The boards and the props ride one rail."""
        from app.utils.tournament_register import registered_market_ids

        ids = registered_market_ids()
        # Kalshi KXATP-26USO / KXWTA-26USO, Polymarket 139236 / 139255.
        assert {34277822, 34277839, 114159, 114160} <= ids

    def test_a_malformed_register_yields_nothing_and_never_raises(self, tmp_path):
        """A broken file must degrade the sweep to its class, never abort the beat."""
        from app.utils.tournament_register import registered_market_ids

        (tmp_path / "broken-2026.json").write_text("{not json")
        (tmp_path / "good-2026.json").write_text('{"props":[{"market_id": 7}]}')
        assert registered_market_ids(directory=tmp_path) == {7}

    def test_fixture_registers_are_not_treated_as_committed(self, tmp_path):
        from app.utils.tournament_register import registered_market_ids

        (tmp_path / "_synthetic-draw.json").write_text('{"props":[{"market_id": 9}]}')
        assert registered_market_ids(directory=tmp_path) == set()

    def test_collector_walks_the_whole_document(self, tmp_path):
        """Enumerating today's section names silently stops covering tomorrow's."""
        from app.utils.tournament_register import registered_market_ids

        (tmp_path / "t-2026.json").write_text(
            '{"players":[{"sources":[{"market_id": 1}]}],'
            ' "props":[{"market_id": 2}],'
            ' "a_section_that_does_not_exist_yet":[{"market_id": 3}]}'
        )
        assert registered_market_ids(directory=tmp_path) == {1, 2, 3}

    def test_true_is_not_collected_as_market_one(self, tmp_path):
        from app.utils.tournament_register import registered_market_ids

        (tmp_path / "t-2026.json").write_text('{"props":[{"market_id": true}]}')
        assert registered_market_ids(directory=tmp_path) == set()


class TestTheGuardCanSeeTheCuratedPopulation:
    """A guard bounded by value cannot report a failure that is tier 5.

    When the section emptied, `/futures-price-freshness` was reporting on a
    denominator the three dark markets were never in. It was not wrong, it was
    blind — and a blind guard reads exactly like a green one (gotcha #53).
    """

    def test_registered_arm_exists_and_drops_the_value_bounds(self):
        sql = _extract_sql_literal(_ADMIN_SRC, "_REGISTERED_SQL")
        assert "market_tier = 1" not in sql
        assert "volume_floor" not in sql
        assert "fm.id = ANY(:market_ids)" in sql
        # Same liveness bounds and the same snapshot-derived freshness as the
        # class arm — only the membership test differs.
        assert "fm.status = 'open'" in sql
        assert "resolution_date > NOW()" in sql
        assert "s.captured_at" in sql
        assert "updated_at" not in sql

    def test_it_reports_tier_so_a_reader_sees_why_the_class_arm_missed_it(self):
        assert "fm.market_tier" in _extract_sql_literal(_ADMIN_SRC, "_REGISTERED_SQL")
        assert '"market_tier": r[4]' in _ADMIN_SRC

    def test_the_class_verdict_keeps_its_meaning(self):
        """CERT-404 G5 and the dashboards read `status`. Redefining it under them
        would move a number they are grading against."""
        assert '"status": "green" if dark_total == 0 else "red",' in _ADMIN_SRC

    def test_a_single_field_answers_is_anything_dark(self):
        """Two verdicts and no combined one is how the second gets ignored."""
        assert '"status_all"' in _ADMIN_SRC
        assert "dark_total == 0 and not registered_dark" in _ADMIN_SRC


class TestTheProducerClockLeadsTheRenderClock:
    def test_registered_window_is_a_strict_sub_interval_of_the_beat(self):
        """Producer-at-6h + renderer-at-6h is a lockstep, not a margin.

        The sweep only became interested in a market once it had ALREADY
        breached the bound the page renders through, so a refresh could only ever
        arrive after the dark window opened. Observed in production: the two
        Polymarket winner fields captured at 01:50, 08:50, 14:50 and 21:50 — a
        6-7h cadence against a 6h render gate, dark for the remainder.

        60 minutes is not good enough either, and this is the subtle half: the
        window is evaluated a few seconds LATER each hour than the capture it is
        testing, so at exactly 60 the previous run's own snapshot still sits
        inside it and the market refreshes every OTHER hour.
        """
        assert 0 < fpr.REGISTERED_REFRESH_MINUTES < 60
        assert fpr.REGISTERED_REFRESH_MINUTES < fpr.STALE_AFTER_HOURS * 60

    def test_identity_attempt_marker_cannot_outlive_its_next_beat(self):
        """A 6h marker on a 45m window is the lockstep restored via Redis.

        #3315 put two identity arms behind one marker, so the TTL is the SHORTER
        of the two windows. `max` there would let a row on both arms hold a
        marker past the shorter arm's next beat, which is the lockstep again with
        the served arm as its victim.
        """
        src = _MODULE_SRC.replace("\n", " ")
        assert (
            "min(registered_refresh_minutes, served_refresh_minutes)" in src
        ), "the identity marker must be sized off the shorter window"
        assert "max(registered_refresh_minutes" not in src

    def test_identity_rows_lead_and_survive_the_budget(self):
        """Both source loops are wall-budget truncated, so head position IS the guard.

        Behavioural, and it asserts the two properties separately because
        #3315's per-source budgets broke the old proof: under one shared cap,
        being sorted to the head was enough to survive `[:budget]`. Under two,
        an interleaved slice would make survival depend on how many class rows
        happened to sort in front — a guarantee that holds by arithmetic
        coincidence is not one.
        """
        rows = [
            {"id": 1, "source": "kalshi", "priority": False},
            {"id": 2, "source": "kalshi", "priority": True},
            {"id": 3, "source": "polymarket", "priority": True},
            {"id": 4, "source": "kalshi", "priority": False},
            {"id": 5, "source": "kalshi", "priority": True},
        ]
        # Budget of 3 for Kalshi: both identity rows lead, and exactly one
        # class row rides along in the remaining slot.
        taken = fpr._take_for_source(rows, "kalshi", 3)
        assert [m["id"] for m in taken] == [2, 5, 1]
        # A budget SMALLER than the identity count spends nothing on the class.
        assert [m["id"] for m in fpr._take_for_source(rows, "kalshi", 1)] == [2, 5]
        # A budget of ZERO still cannot drop an identity row.
        assert [m["id"] for m in fpr._take_for_source(rows, "kalshi", 0)] == [2, 5]
        # Sources do not leak into each other.
        assert [m["id"] for m in fpr._take_for_source(rows, "polymarket", 9)] == [3]


class TestPolymarketAddressing:
    """`external_id` is the Gamma EVENT id for a field row and a CONDITION id for
    a prop row. Assuming the first for both is why the curated props could not
    have been priced even once selection was fixed."""

    def test_event_id_expression_prefers_metadata_then_group_id(self):
        sql = fpr._POLY_EVENT_ID_SQL
        assert "market_metadata->>'polymarket_event_id'" in sql
        assert "^polymarket:(.+)$" in sql
        # A bare `0x…` condition id must NOT be passed off as an event id:
        # `/events?id=0x…` does not resolve it.
        assert "fm.external_id ~ '^[0-9]+$'" in sql

    def test_both_candidate_arms_select_the_event_id(self):
        for sql in (fpr._CANDIDATE_SQL.text, fpr._REGISTERED_CANDIDATE_SQL.text):
            assert "poly_event_id" in sql

    def test_markets_are_grouped_by_event_not_keyed_one_per_event(self):
        """Two curated props share Gamma event 910171. Keying market-per-event
        drops the second one silently."""
        assert "by_event.setdefault(str(event_id), []).append(market)" in _MODULE_SRC
        assert "for market in by_event[event_id]:" in _MODULE_SRC

    async def test_fetch_keys_by_event_and_emits_the_no_leg(self):
        priced = await fpr._fetch_polymarket_prices(
            _FakePolyService(_poly_event("910171", [_poly_market("0xabc", 0.575, 0.425)])),
            ["910171"],
        )
        assert list(priced) == ["910171"]
        item = priced["910171"][0]
        assert item["external_id"] == "0xabc"
        assert item["probability"] == pytest.approx(0.575)
        assert item["no"]["probability"] == pytest.approx(0.425)

    async def test_the_no_leg_complements_the_accepted_price_not_outcome_prices(self):
        """The specimen this rule exists for, taken from live Gamma 2026-08-27.

        `alcaraz-semifinals` quoted `outcome_prices = [0.32, 0.68]` over an
        untradeable 0.11/0.53 book. 0.32 IS the midpoint of that book, so #1578
        refuses it and Yes resolves to the 0.53 last trade. Publishing 0.68 as
        the No leg would print a card whose two sides sum to **1.21**, and 0.68
        is the complement of the exact number the Yes side just rejected.

        `1 - accepted` is the same binary CLOB addressed from the other token —
        the reasoning `complementary_book` already applies to the book. It is
        also lossless in the common case: measured over 92 live priced markets on
        the four curated prop events, `outcome_prices` summed to exactly 1 every
        time, so whenever Yes came from `outcome_prices` the two rules agree.

        AMENDED BY Q432 (2026-08-28) — the specimen, not the claim. Q428 bounded
        the last-trade escape hatch on Gamma's `volume24hr`, because
        `lastTradePrice` carries no time and one $5 trade against a 7c/98c book
        was putting Djokovic at 71% to reach the round of 16 above 79% to reach
        the quarter-final. This specimen's own premise is a market that HAD
        traded — a real 0.53 trade sitting at the ask of a live 2026-08-27 book —
        so it now states the 24-hour volume it always implied. That restores the
        specimen's fidelity to the row it was copied from; it does not relax the
        bound. The twin below is the case that was silently riding on it.
        """
        market = _poly_market("0xabc", 0.32, 0.68, volume_24h=1_450.0)
        market.best_bid = 0.11
        market.best_ask = 0.53
        market.last_trade_price = 0.53
        priced = await fpr._fetch_polymarket_prices(
            _FakePolyService(_poly_event("910171", [market])), ["910171"]
        )
        item = priced["910171"][0]
        assert item["probability"] == pytest.approx(0.53)
        assert item["no"]["probability"] == pytest.approx(0.47)
        assert item["probability"] + item["no"]["probability"] == pytest.approx(1.0)

    async def test_the_same_wide_book_untraded_publishes_neither_leg(self):
        """Q432's twin of the test above, and the half this file could not see.

        Identical quotes, identical last trade, nobody transacting in the last
        24 hours. Q428's bound declines the trade, `_resolve_market_probability`
        returns None, and the question this lane's ship exists to light up stays
        dark — which is the right answer, because the alternative is printing
        0.53 as a present-tense belief when the present tense is empty.

        **The design call, stated rather than left to fall out of the code: the
        declined market emits NOTHING — no Yes, no No, and no event key at all.**
        Two reasons, and neither is "that is what the code happens to do".

        1. There is no No leg to declare. This rail publishes `1 - accepted`,
           and when nothing is accepted the complement is undefined. A "declared
           decline" would have to invent the number it is declining to invent.
        2. Silence here is not invisible, which is the only thing that would
           make it wrong (gotcha #53). A market that is not refreshed keeps its
           age, so the row renders `price_state: dark` on `More predictions`
           with the staleness the user can see, and it is counted by the
           `registered` arm of `/api/admin/source-health/futures-price-freshness`
           that the same queue added. The decline is legible on both the page and
           the operator surface without a sentinel value in the price channel.

        So the assertion is the strong one — the event key is absent entirely,
        not merely a Yes without a No.
        """
        # `volume_24h=None` is stated at the call site rather than inherited from
        # the helper default. Relying on a default to carry a specimen's central
        # premise is the exact bug class that bounced this branch — the premise
        # goes unsaid, another lane changes what the unsaid value means, and two
        # certs pass a combination that is red. This one says it out loud.
        market = _poly_market("0xabc", 0.32, 0.68, volume_24h=None)
        market.best_bid = 0.11
        market.best_ask = 0.53
        market.last_trade_price = 0.53
        priced = await fpr._fetch_polymarket_prices(
            _FakePolyService(_poly_event("910171", [market])), ["910171"]
        )
        assert priced == {}, f"an untraded wide book published {priced}"

    async def test_the_pair_always_sums_to_one(self):
        """The invariant a rendered binary card depends on, whatever the source."""
        for yes, no, bid, ask, last, vol in (
            # accepted from outcome_prices — a tight book never reaches the
            # Q428 volume gate, so this row means the same with or without it.
            (0.575, 0.425, 0.57, 0.58, 0.575, None),
            # refused midpoint -> last trade, and only because the market was
            # still being traded. Its untraded twin is the test above, which
            # asserts the pair is never published at all rather than summing.
            (0.32, 0.68, 0.11, 0.53, 0.53, 1_450.0),
        ):
            market = _poly_market("0xabc", yes, no, volume_24h=vol)
            market.best_bid, market.best_ask, market.last_trade_price = bid, ask, last
            priced = await fpr._fetch_polymarket_prices(
                _FakePolyService(_poly_event("910171", [market])), ["910171"]
            )
            item = priced["910171"][0]
            total = item["probability"] + item["no"]["probability"]
            assert total == pytest.approx(1.0), f"{yes}/{no} summed to {total}"


class TestWriterResolvesBothOutcomeConventions:
    async def test_suffixed_yes_no_legs_are_both_written(self):
        """The prop convention. Before this, both legs counted as
        `unknown_outcomes` and the card stayed dark with the price in hand."""
        session = _FakeSession({"0xabc_yes": 11, "0xabc_no": 12})
        stats = {"unknown_outcomes": 0}
        written = await fpr._write_prices(
            session,
            59556735,
            "polymarket",
            [
                {
                    "external_id": "0xabc",
                    "probability": 0.575,
                    "yes_bid": 0.57,
                    "yes_ask": 0.58,
                    "last_price": 0.575,
                    "no": {
                        "probability": 0.425,
                        "yes_bid": 0.42,
                        "yes_ask": 0.43,
                        "last_price": 0.425,
                    },
                }
            ],
            stats,
        )
        assert written == 2
        assert stats["unknown_outcomes"] == 0
        assert session.snapshot_probabilities == pytest.approx([0.575, 0.425])

    async def test_bare_convention_still_writes_exactly_once(self):
        """A negRisk field outcome must not also match a suffixed lookup."""
        session = _FakeSession({"0xabc": 11})
        stats = {"unknown_outcomes": 0}
        written = await fpr._write_prices(
            session,
            114159,
            "polymarket",
            [{"external_id": "0xabc", "probability": 0.27, "no": {"probability": 0.73}}],
            stats,
        )
        assert written == 1
        assert session.snapshot_probabilities == pytest.approx([0.27])

    async def test_an_unheld_id_is_still_counted_as_unknown(self):
        """The refusal must stay visible — it is how "we do not hold this" is said."""
        session = _FakeSession({"0xother_yes": 11})
        stats = {"unknown_outcomes": 0}
        written = await fpr._write_prices(
            session, 1, "polymarket", [{"external_id": "0xabc", "probability": 0.5}], stats
        )
        assert written == 0
        assert stats["unknown_outcomes"] == 1

    async def test_a_missing_no_row_does_not_block_the_yes_leg(self):
        session = _FakeSession({"0xabc_yes": 11})
        stats = {"unknown_outcomes": 0}
        written = await fpr._write_prices(
            session,
            1,
            "polymarket",
            [{"external_id": "0xabc", "probability": 0.6, "no": {"probability": 0.4}}],
            stats,
        )
        assert written == 1
        assert stats["unknown_outcomes"] == 0


# --- fakes -------------------------------------------------------------------


def _poly_market(condition_id: str, yes: float, no: float, volume_24h: float | None = None):
    """A Gamma market row, tight-booked by default.

    ``volume_24h`` defaults to absent on purpose, matching ``_market`` in
    ``tests/test_polymarket_untradeable_book.py``: since Q428 the last-trade
    escape hatch is bounded on Gamma's 24-hour window, so a specimen that means
    to exercise it has to SAY the market was being traded rather than inherit it
    from a helper. Every specimen here that keeps a tight book never reaches
    that gate, so the default costs them nothing.
    """
    from app.services.polymarket_api import PolymarketMarket

    return PolymarketMarket(
        condition_id=condition_id,
        question="Will X advance?",
        outcomes=["Yes", "No"],
        outcome_prices=[yes, no],
        best_bid=yes - 0.005,
        best_ask=yes + 0.005,
        last_trade_price=yes,
        volume_24h=volume_24h,
    )


def _poly_event(event_id: str, markets: list):
    from app.services.polymarket_api import PolymarketEvent

    return PolymarketEvent(id=event_id, title="US Open", markets=markets)


class _FakePolyService:
    def __init__(self, event):
        self._event = event

    async def get_events_by_ids(self, event_ids):
        return [{"id": eid} for eid in event_ids]

    def _parse_event(self, raw):
        return self._event if raw["id"] == self._event.id else None


class _FakeSession:
    """Records what the writer would send, without a database.

    The real-Postgres gate (`tests/integration/test_futures_price_refresh_writes_pg.py`)
    remains the authority on whether a row actually lands; this fake exists to
    pin the *resolution* logic, which is pure and was the defect.
    """

    def __init__(self, outcomes_by_external_id: dict):
        self._outcomes = outcomes_by_external_id
        self.snapshot_probabilities: list[float] = []

    async def execute(self, statement, params=None):
        compiled = str(statement)
        if "SELECT id, external_id FROM futures_outcomes" in compiled:
            return _FakeResult([(oid, ext) for ext, oid in self._outcomes.items()])
        if compiled.lstrip().upper().startswith("INSERT INTO FUTURES_ODDS_SNAPSHOTS"):
            self.snapshot_probabilities.append(
                float(statement.compile().params["probability"])
            )
        return _FakeResult([])


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def _extract_sql_literal(source: str, name: str) -> str:
    """The RENDERED constant, not the source text it was typed as.

    #2222 turned the guard's four SQL constants into f-strings that interpolate
    the shared liveness predicate, at which point reading the source gave back
    the literal characters ``{LIVE_MARKET_SQL}`` and every clause assertion
    below started failing against code that was correct. Reading the module
    attribute tests the string that actually reaches Postgres, which is what
    these assertions were always trying to say.

    ``source`` is kept in the signature because the callers name which module
    they mean, and losing that would make the call sites ambiguous.
    """
    import app.routes.admin_source_health as _health

    assert source is _ADMIN_SRC, "only the admin-health module is extractable here"
    sql = getattr(_health, name, None)
    assert sql, f"{name} not found — did the constant get renamed?"
    return sql


def _normalise(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


# --- CERT-1970: an unavailable page-one signal must not read green ------------


class _RunHarness:
    """Drives `_refresh_stale_futures_prices` end to end without a database.

    Deliberately NOT a stub of `_terminal`. The block's finding was that the
    field existed and nothing consulted it, so a test that asserts `_terminal`
    in isolation proves the honouring and not the WIRING — and the wiring is
    where the defect lived. This runs the real entry point, so the summary it
    classifies is the one production returns.
    """

    def __init__(self, *, signal, class_rows):
        self.signal = signal
        self.class_rows = class_rows
        self.snapshot_probabilities: list[float] = []
        self.marker_written = False

    class _Result:
        def __init__(self, rows=(), scalar=0):
            self._rows = list(rows)
            self._scalar = scalar

        def fetchall(self):
            return self._rows

        def scalar(self):
            return self._scalar

    class _Session:
        def __init__(self, outer):
            self.outer = outer

        async def execute(self, statement, params=None):
            sql = str(statement)
            if "WITH pool AS MATERIALIZED" in sql:
                if "COUNT(*)" in sql:
                    return _RunHarness._Result(scalar=0)
                return _RunHarness._Result(self.outer.class_rows)
            if "SELECT id, external_id FROM futures_outcomes" in sql:
                return _RunHarness._Result([(11, "0xabc")])
            if sql.lstrip().upper().startswith("INSERT INTO FUTURES_ODDS_SNAPSHOTS"):
                self.outer.snapshot_probabilities.append(
                    float(statement.compile().params["probability"])
                )
                return _RunHarness._Result()
            if "fm.id = ANY(:market_ids)" in sql:
                return _RunHarness._Result([], scalar=0)
            return _RunHarness._Result()

        async def commit(self):
            return None

        async def rollback(self):
            return None

    async def run(self, monkeypatch):
        import contextlib

        from app.tasks import futures_price_refresh as mod

        session = self._Session(self)

        @contextlib.asynccontextmanager
        async def _fake_session():
            yield session

        monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
        monkeypatch.setattr(
            "app.utils.tournament_register.registered_market_ids", lambda: set()
        )
        monkeypatch.setattr(
            "app.utils.feed_served_markets.served_signal", lambda: self.signal
        )

        def _note(*a, **kw):
            self.marker_written = True

        monkeypatch.setattr(
            "app.utils.feed_served_markets.note_served_signal_healthy", _note
        )
        monkeypatch.setattr(mod, "_load_attempt_skips", lambda ids: set())
        monkeypatch.setattr(mod, "_mark_attempted", lambda ids, ttl_seconds: None)

        class _Service:
            async def close(self):
                return None

        monkeypatch.setattr(
            "app.services.polymarket_api.PolymarketAPIService", lambda: _Service()
        )

        async def _priced(service, event_ids):
            return {
                eid: [
                    {
                        "external_id": "0xabc",
                        "probability": 0.399,
                        "yes_bid": 0.39,
                        "yes_ask": 0.40,
                        "last_price": 0.399,
                    }
                ]
                for eid in event_ids
            }

        monkeypatch.setattr(mod, "_fetch_polymarket_prices", _priced)
        return await mod._refresh_stale_futures_prices()


def _brazil_class_row():
    """One class-arm market that WILL price: tier-2 Brazil, addressable."""
    return [(112996, "polymarket", "0xbrazil", 114_137_967, "45915", None)]


class TestAnUnavailablePageOneSignalCannotReadGreen:
    """🔴 THE CERT-1970 REGRESSION, in the exact shape the block required.

    "Force the served-signal read unavailable while another class market prices
    successfully and prove the task summary does not classify green; add a
    sibling present-but-empty control that remains valid."

    The failure it catches is not "the terminal is wrong". It is that the third
    arm — the only thing that makes "front-page cards show the venue's quote"
    true at ANY tier and volume — can go dark while the enforced verdict says
    `complete`, so a low-value page-one card stays stale forever with nothing
    anywhere disagreeing. That is the same class of silence #3315 itself was.
    """

    @pytest.mark.asyncio
    async def test_unavailable_plus_successful_class_writes_is_not_green(
        self, monkeypatch
    ):
        from app.utils.feed_served_markets import SERVED_UNAVAILABLE, ServedSignal

        harness = _RunHarness(
            signal=ServedSignal(state=SERVED_UNAVAILABLE, ids=[]),
            class_rows=_brazil_class_row(),
        )
        stats = await harness.run(monkeypatch)

        # The class arm really did work — otherwise this proves nothing about
        # the served arm, only that a failing run fails.
        assert stats["snapshots_written"] >= 1
        assert stats["markets_priced"] >= 1

        assert stats["served_state"] == SERVED_UNAVAILABLE
        assert stats["served_signal_ok"] is False
        assert stats["terminal"] == "partial"
        assert not classify_summary(stats).is_green, (
            "a run whose page-one arm is dark read GREEN off successful class "
            "work — the exact false green CERT-1970 blocked"
        )
        assert not harness.marker_written, (
            "the health marker was refreshed on an unhealthy observation, which "
            "would let the grace renew itself forever"
        )

    @pytest.mark.asyncio
    async def test_present_but_empty_is_valid_and_still_green(self, monkeypatch):
        """THE CONTROL. Without it the test above is satisfied by "never green".

        A page one that genuinely holds no futures cards is the arm WORKING. If
        that also read not-green the repair would be a permanent alarm, and a
        permanent alarm is not an instrument.
        """
        from app.utils.feed_served_markets import SERVED_EMPTY, ServedSignal

        harness = _RunHarness(
            signal=ServedSignal(state=SERVED_EMPTY, ids=[], shapes=2),
            class_rows=_brazil_class_row(),
        )
        stats = await harness.run(monkeypatch)

        assert stats["snapshots_written"] >= 1
        assert stats["served_state"] == SERVED_EMPTY
        assert stats["served_signal_ok"] is True
        assert stats["terminal"] == "complete"
        assert classify_summary(stats).is_green
        assert harness.marker_written, (
            "a healthy observation must refresh the marker the grace is measured "
            "from, or the grace expires under a working rail"
        )

    @pytest.mark.asyncio
    async def test_a_cold_start_is_not_treated_as_a_regression(self, monkeypatch):
        """`never_seen` permits green: a first deploy must not alarm on bootstrap.

        And it must NOT write the marker, or the very first run would forge the
        history the `unavailable` branch is supposed to check for.
        """
        from app.utils.feed_served_markets import SERVED_NEVER_SEEN, ServedSignal

        harness = _RunHarness(
            signal=ServedSignal(state=SERVED_NEVER_SEEN, ids=[]),
            class_rows=_brazil_class_row(),
        )
        stats = await harness.run(monkeypatch)
        assert stats["terminal"] == "complete"
        assert classify_summary(stats).is_green
        assert not harness.marker_written

    @pytest.mark.asyncio
    async def test_the_short_return_path_cannot_read_green_either(self, monkeypatch):
        """A false green does not become true by being reached through a branch.

        With nothing stale the run returns early, long before `_terminal`. On
        that path "nothing was stale" is a claim about a population we could not
        enumerate, so it must not be `complete`.
        """
        from app.utils.feed_served_markets import SERVED_UNAVAILABLE, ServedSignal

        harness = _RunHarness(
            signal=ServedSignal(state=SERVED_UNAVAILABLE, ids=[]), class_rows=[]
        )
        stats = await harness.run(monkeypatch)
        assert stats["markets_attempted"] == 0
        assert stats["terminal"] == "no_work"
        assert not classify_summary(stats).is_green
        assert "unavailable" in stats["reason"]

    @pytest.mark.asyncio
    async def test_a_rail_that_never_started_stops_reading_green(self, monkeypatch):
        """🔴 CERT-1974's regression, end to end, in the shape the block required.

        "Drive the real `served_signal()` against the same empty healthy store at
        t0 and t0 + grace + 1, then feed the latter through
        `_refresh_stale_futures_prices()` with successful class writes and prove
        the verdict is not green."

        `never_seen` used to be ABSORBING: a healthy Redis holding nothing kept
        the enforced task green at 0h, 4h, 24h and 744h, so a pre-warm hook that
        never fired would have looked exactly like a working one forever. The
        signal below is produced by the REAL state machine against a store that
        PERSISTS what the first read wrote — a fresh fake per call passes against
        the blocked code and proves nothing.
        """
        from app.utils import feed_served_markets as fsm
        from tests.test_feed_served_markets import _FakeRedis

        rc = _FakeRedis()
        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda **kw: rc
        )
        anchor = 1_788_600_000.0

        first = fsm.served_signal(now=anchor)
        assert first.state == fsm.SERVED_NEVER_SEEN, "control: the cold start"

        aged = fsm.served_signal(now=anchor + fsm.SERVED_SIGNAL_GRACE_S + 1)
        assert aged.state == fsm.SERVED_UNAVAILABLE

        harness = _RunHarness(signal=aged, class_rows=_brazil_class_row())
        stats = await harness.run(monkeypatch)

        assert stats["snapshots_written"] >= 1, (
            "the class arm must succeed, or this proves only that a failing run "
            "fails"
        )
        assert stats["served_state"] == fsm.SERVED_UNAVAILABLE
        assert stats["terminal"] == "partial"
        assert not classify_summary(stats).is_green

    @pytest.mark.asyncio
    async def test_the_cold_start_control_still_runs_green(self, monkeypatch):
        """The other side of the same store: at t0 the run is green.

        Without this, the test above is satisfied by a repair that simply never
        permits green during bootstrap — which would alarm on every first deploy
        and be switched off within a week.
        """
        from app.utils import feed_served_markets as fsm
        from tests.test_feed_served_markets import _FakeRedis

        rc = _FakeRedis()
        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda **kw: rc
        )
        signal = fsm.served_signal(now=1_788_600_000.0)
        assert signal.state == fsm.SERVED_NEVER_SEEN

        harness = _RunHarness(signal=signal, class_rows=_brazil_class_row())
        stats = await harness.run(monkeypatch)
        assert stats["terminal"] == "complete"
        assert classify_summary(stats).is_green

    def test_the_terminal_guard_is_not_dead_code(self):
        """It has to fire on the summary shape the run actually returns.

        Pinned separately because the block's probe was exactly this: a plausible
        summary dict fed to the classifier. It returned green.
        """
        base = {
            "markets_attempted": 3,
            "snapshots_written": 3,
            "budget_hit": False,
            "errors": [],
        }
        assert fpr._terminal({**base, "served_signal_ok": True}) == "complete"
        assert fpr._terminal({**base, "served_signal_ok": False}) == "partial"
        # A summary that predates the field keeps its old meaning rather than
        # turning every legacy caller amber.
        assert fpr._terminal(base) == "complete"


class TestTheGuardAnswersInsideTheRoutersWall:
    """#3315, found by the post-deploy check on `f96114d7`.

    The widening was right and it made the guard unreadable. Measured on
    production 2026-09-06 00:20Z, ~10 minutes after the merge went live: the
    four statements the endpoint ran IN SERIES cost 15.1s + 3.3s + 1.4s + 1.1s,
    26.0s end to end, and one read in two came back as Heroku's H12 HTML error
    page. The same census under the pre-#3315 predicate cost 2.2s over 872
    markets; the new pool is 4,916.

    Two failures, not one, and the second is the one that matters. A guard that
    is slow is an annoyance. A guard whose failure arrives as an HTML 503 is a
    guard whose reader cannot distinguish "the invariant holds" from "nobody
    checked" — the exact shape of the bug this endpoint exists to catch
    (gotcha #53), reappearing one level up in the instrument itself.
    """

    def _endpoint_ast(self):
        import ast

        tree = ast.parse(_ADMIN_SRC)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.AsyncFunctionDef)
                and node.name == "futures_price_freshness"
            ):
                return node
        raise AssertionError("futures_price_freshness not found in the module")

    def test_the_wall_is_below_the_routers(self):
        """22s against the router's 30s. Both numbers are load-bearing: above
        30s the wall never fires, and the reader gets HTML instead of JSON."""
        import app.routes.admin_source_health as _health

        assert _health._CENSUS_STATEMENT_TIMEOUT_MS < 30_000
        # And it is actually applied, server-side, per statement.
        import inspect

        src = inspect.getsource(_health._census_rows)
        assert "SET LOCAL statement_timeout" in src
        assert "_CENSUS_STATEMENT_TIMEOUT_MS" in src

    def test_no_census_statement_escapes_the_wall(self):
        """AST, not a substring: a statement issued on the request-scoped
        session carries no timeout, and it is one line to add one back."""
        import ast

        node = self._endpoint_ast()
        for call in ast.walk(node):
            if isinstance(call, ast.Attribute) and call.attr == "execute":
                raise AssertionError(
                    "the endpoint executes SQL outside _census_rows, so that "
                    "statement runs without the wall"
                )

    def test_the_statements_run_concurrently(self):
        """The serial shape is what turned a 15s query into a 26s request.

        Asserted structurally rather than by timing: every `_census_rows` call
        in the endpoint has to be inside the `asyncio.gather`, because one left
        outside it is added back to the wall in full.
        """
        import ast

        node = self._endpoint_ast()
        gathers = [
            c
            for c in ast.walk(node)
            if isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and c.func.attr == "gather"
        ]
        assert len(gathers) == 1, "expected exactly one asyncio.gather"
        assert len(gathers[0].args) >= 3, (
            "the census is three statements; gathering fewer means one of them "
            "is still serial"
        )

    def test_the_total_deadline_is_below_the_routers_and_above_the_statement_wall(
        self,
    ):
        """CERT-1981 follow-up L1B-051B-POOL-CHECKOUT-WALL. Both inequalities
        are load-bearing and they bound it from opposite sides.

        ABOVE the statement wall, so the ordinary slow-query path still trips
        the wall that can NAME the query and report `census_timeout`; a total
        deadline that fired first would turn every slow query into an
        undiagnosable `census_deadline`. BELOW the router's 30s, because the
        whole point is to answer in JSON rather than let Heroku answer in HTML.
        """
        import app.routes.admin_source_health as _health

        assert (
            _health._CENSUS_STATEMENT_TIMEOUT_MS / 1000
            < _health._CENSUS_TOTAL_DEADLINE_S
            < 30
        )

    def test_the_census_is_bounded_as_a_WHOLE_not_only_per_statement(self):
        """`statement_timeout` bounds a statement the server is RUNNING. It
        cannot see the wait for a connection, and this engine's `pool_timeout`
        default is 30s — the router's own limit. So under pool pressure the
        endpoint could H12 in checkout without Postgres being asked anything:
        the exact failure CERT-1981 removed, through the one door it left."""
        import ast

        node = self._endpoint_ast()
        waits = [
            c
            for c in ast.walk(node)
            if isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and c.func.attr == "wait_for"
        ]
        assert len(waits) == 1, "the census gather is not under a total deadline"
        # …and the thing it wraps is the gather, not something cheaper beside it.
        assert any(
            isinstance(a, ast.Call)
            and isinstance(a.func, ast.Attribute)
            and a.func.attr == "gather"
            for a in waits[0].args
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exc,expected_reason",
        [
            ("pool", "census_pool_exhausted"),
            ("deadline", "census_deadline"),
        ],
    )
    async def test_the_other_two_walls_also_report_unknown_and_say_which(
        self, monkeypatch, exc, expected_reason
    ):
        """THREE causes, three reasons, one verdict.

        A pool that cannot hand out a connection and a deadline that expired
        are not `DBAPIError`, so before this they escaped as a 500 — which a
        reader distinguishes from a green verdict no better than an H12. And
        they must not collapse into one reason: a reader acting on an `unknown`
        needs to know whether to look at the query, the pool, or the endpoint.
        """
        import asyncio as _asyncio

        from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

        import app.routes.admin_source_health as _health

        raised = (
            SQLAlchemyTimeoutError("QueuePool limit of size 10 overflow 10 reached")
            if exc == "pool"
            else _asyncio.TimeoutError()
        )

        async def _boom(sql, params):
            raise raised

        monkeypatch.setattr(_health, "_census_rows", _boom)
        monkeypatch.setattr(_health, "_check_admin_secret", lambda *a, **kw: None)

        out = await _health.futures_price_freshness(
            request=object(), secret="x", max_age_hours=24
        )
        assert out["status"] == "unknown"
        assert out["status_all"] == "unknown"
        assert out["reason"] == expected_reason
        assert "price_dark" not in out

    @pytest.mark.asyncio
    async def test_a_census_that_cannot_finish_does_not_read_green(
        self, monkeypatch
    ):
        """THE POINT OF THE WALL. A timeout must be a third state.

        Before this, a census that blew the router's wall returned an HTML 503
        with no body. Any caller that branches on `status == "red"` — the
        cockpit tile, CERT-404 G5, this lane's own post-deploy check — read that
        as "not red", which is to say as a pass.
        """
        from sqlalchemy.exc import DBAPIError

        import app.routes.admin_source_health as _health

        async def _boom(sql, params):
            raise DBAPIError(
                "SELECT ...",
                {},
                Exception("canceling statement due to statement timeout"),
            )

        monkeypatch.setattr(_health, "_census_rows", _boom)
        monkeypatch.setattr(
            _health, "_check_admin_secret", lambda *a, **kw: None
        )

        out = await _health.futures_price_freshness(
            request=object(), secret="x", max_age_hours=24
        )
        assert out["status"] == "unknown"
        assert out["status_all"] == "unknown"
        assert out["reason"] == "census_timeout"
        # And it must not carry a verdict-shaped zero beside the unknown: a
        # `price_dark: 0` next to `status: unknown` is how a reader talks
        # themselves into green.
        assert "price_dark" not in out
        assert "eligible_markets" not in out
