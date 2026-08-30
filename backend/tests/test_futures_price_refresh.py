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
        assert "fm.market_tier = 1" in sql
        assert "fm.volume >= :volume_floor" in sql
        # Gotcha #33: settled Kalshi markets keep status='open', so `status`
        # alone is not a liveness test. The resolution-date bound is what keeps
        # the dead out of an ordering that would otherwise never release them.
        assert "resolution_date > NOW()" in sql

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
        for name in ("_PRICE_DARK_SQL", "_PRICE_DARK_WORST_SQL"):
            guard_sql = _normalise(_extract_sql_literal(_ADMIN_SRC, name))
            for clause in (
                "fm.status = 'open'",
                "fm.market_tier = 1",
                "fm.volume >= :volume_floor",
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
        from app.utils.futures_liveness import LIVE_MARKET_SQL

        shared = _normalise(LIVE_MARKET_SQL)
        assert shared, "the shared predicate must not be empty"

        askers = {
            "task._CANDIDATE_SQL": fpr._CANDIDATE_SQL.text,
            "task._REGISTERED_CANDIDATE_SQL": fpr._REGISTERED_CANDIDATE_SQL.text,
            "guard._PRICE_DARK_SQL": _health._PRICE_DARK_SQL,
            "guard._PRICE_DARK_WORST_SQL": _health._PRICE_DARK_WORST_SQL,
            "guard._REGISTERED_DARK_SQL": _health._REGISTERED_DARK_SQL,
            "guard._REGISTERED_ELIGIBLE_SQL": _health._REGISTERED_ELIGIBLE_SQL,
        }
        for name, sql in askers.items():
            assert shared in _normalise(sql), f"{name} does not compose LIVE_MARKET_SQL"

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
        assert _MODULE_SRC.count("{LIVE_MARKET_SQL}") == 3, (
            "two selectors plus the remaining_stale census"
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
        for name in ("_PRICE_DARK_SQL", "_PRICE_DARK_WORST_SQL"):
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
        """Without headroom, a run whose top-N were all just attempted does nothing."""
        assert "scan_limit=max(budget * 3, budget + 50)" in _MODULE_SRC.replace(
            "\n", ""
        ).replace("  ", "")


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
        sql = _extract_sql_literal(_ADMIN_SRC, "_REGISTERED_DARK_SQL")
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
        assert "fm.market_tier" in _extract_sql_literal(_ADMIN_SRC, "_REGISTERED_DARK_SQL")
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

    def test_registered_attempt_marker_cannot_outlive_its_next_beat(self):
        """A 6h marker on a 45m window is the lockstep restored via Redis."""
        assert "registered_refresh_minutes) * 60" in _MODULE_SRC.replace("\n", " ")

    def test_registered_rows_sort_ahead_of_the_class(self):
        """Both source loops are wall-budget truncated, so head position IS the guard."""
        selected = [
            {"id": 1, "registered": False},
            {"id": 2, "registered": True},
            {"id": 3, "registered": False},
            {"id": 4, "registered": True},
        ]
        selected.sort(key=lambda m: not m["registered"])
        assert [m["id"] for m in selected] == [2, 4, 1, 3]
        assert 'selected.sort(key=lambda m: not m["registered"])' in _MODULE_SRC


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
