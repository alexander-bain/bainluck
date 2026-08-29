"""C-ROLLCALL-BUILD-1 — the axiom, the scoring, and the red-first gate.

G2 of the frozen acceptance is the load-bearing test in this file and it has a
shape worth naming: **a gate green on both sides is not a gate.** So the same
slate is asserted twice — once in the state ``C-ROLLCALL-PREP-1`` measured on
2026-08-26 (15 fixtures, 15 duplicated, 0/15 Kalshi), where the gate must FAIL,
and once repaired (15 fixtures, one event each, every source linked), where it
must PASS. A predicate that cannot fail the first is not detecting anything.
"""

from app.utils.rollcall import (
    AXIOM_LEAGUES,
    GOLF_AXIOM_SOURCES,
    GOLF_ODDS_API_JUSTIFICATION,
    MEASURED_DOMAINS,
    MIN_BASELINE_DAYS,
    TEAM_AXIOM_SOURCES,
    FixtureRow,
    axiom_is_red,
    axiom_offenders,
    baseline_verdict,
    build_rollcall_issue_body,
    coverage_percent,
    fixture_matches,
    rollcall_fingerprint,
    rollcall_terminal,
    score_fixtures,
    team_nickname,
)

ALL_LINKED = {"kalshi": True, "polymarket": True, "espn": True, "odds_api": True}


def _slate_broken(n: int = 15) -> list[FixtureRow]:
    """The measured 2026-08-26 MLB state: every fixture duplicated, no Kalshi."""
    return [
        FixtureRow(
            label=f"Away{i} @ Home{i}",
            kickoff="2026-08-26T22:40:00+00:00",
            event_ids=[15291944 + i, 15242101 + i],
            sources={},
        )
        for i in range(n)
    ]


def _slate_repaired(n: int = 15) -> list[FixtureRow]:
    return [
        FixtureRow(
            label=f"Away{i} @ Home{i}",
            kickoff="2026-08-26T22:40:00+00:00",
            event_ids=[15291944 + i],
            sources=dict(ALL_LINKED),
        )
        for i in range(n)
    ]


class TestRedFirstGate:
    """G2 — must FAIL on the measured slate, must PASS on the repaired one."""

    def test_the_measured_slate_is_red(self):
        rows = _slate_broken()
        card = score_fixtures(rows, TEAM_AXIOM_SOURCES)
        assert card["events_external"] == 15
        assert card["matched_1"] == 0
        assert card["dupes"] == 15
        assert card["missing"] == 0
        assert card["per_source"]["kalshi"] == 0
        assert card["clean"] == 0
        assert axiom_is_red(card, TEAM_AXIOM_SOURCES) is True

    def test_the_repaired_slate_is_green(self):
        card = score_fixtures(_slate_repaired(), TEAM_AXIOM_SOURCES)
        assert card["matched_1"] == 15
        assert card["dupes"] == 0
        assert card["clean"] == 15
        assert card["per_source"] == {
            "kalshi": 15, "polymarket": 15, "espn": 15, "odds_api": 15
        }
        assert axiom_is_red(card, TEAM_AXIOM_SOURCES) is False

    def test_one_missing_kalshi_link_on_one_fixture_is_red(self):
        """Any gap is an unconditional alarm — there is no tolerance band."""
        rows = _slate_repaired()
        rows[7].sources = {**ALL_LINKED, "kalshi": False}
        card = score_fixtures(rows, TEAM_AXIOM_SOURCES)
        assert card["per_source"]["kalshi"] == 14
        assert axiom_is_red(card, TEAM_AXIOM_SOURCES) is True

    def test_a_polymarket_shaped_outage_is_red_too(self):
        """The frozen predicate's shorthand names only Kalshi; the expectation
        matrix requires all four, and the matrix is what ships. A Polymarket
        outage must not pass a Kalshi-shaped gate."""
        rows = _slate_repaired()
        for row in rows:
            row.sources = {**ALL_LINKED, "polymarket": False}
        card = score_fixtures(rows, TEAM_AXIOM_SOURCES)
        assert card["per_source"]["kalshi"] == 15
        assert axiom_is_red(card, TEAM_AXIOM_SOURCES) is True

    def test_a_missing_event_is_red(self):
        rows = _slate_repaired()
        rows[3].event_ids = []
        rows[3].sources = {}
        card = score_fixtures(rows, TEAM_AXIOM_SOURCES)
        assert card["missing"] == 1
        assert card["mis_stamped"] == 0
        assert axiom_is_red(card, TEAM_AXIOM_SOURCES) is True

    def test_a_mis_stamped_fixture_counts_inside_missing_and_is_named_apart(self):
        """`mis_stamped` is a SUBSET of `missing`, not a sibling of it: the
        fixture still has no event the roll call may claim, so the axiom is
        still broken — but the repair is a re-stamp, not a create."""
        rows = _slate_repaired()
        rows[2].event_ids = []
        rows[2].sources = {}
        rows[2].id_conflicts = [{"event_id": 14877917, "espn_id": "401815659"}]
        card = score_fixtures(rows, TEAM_AXIOM_SOURCES)
        assert card["missing"] == 1
        assert card["mis_stamped"] == 1
        assert axiom_is_red(card, TEAM_AXIOM_SOURCES) is True

        offenders = axiom_offenders(rows, TEAM_AXIOM_SOURCES)
        assert offenders[0]["gaps"][0] == "mis_stamped"
        body = build_rollcall_issue_body(
            "mlb", "2026-08-29", card, offenders, "https://espn/…",
            TEAM_AXIOM_SOURCES,
        )
        assert "is stamped `401815659`" in body


class TestOffDaysAreSilent:
    """Gotcha #53 — an empty slate is a shape, not a fact."""

    def test_no_fixtures_is_not_red(self):
        card = score_fixtures([], TEAM_AXIOM_SOURCES)
        assert card["events_external"] == 0
        assert axiom_is_red(card, TEAM_AXIOM_SOURCES) is False

    def test_coverage_refuses_rather_than_publishing_a_flattering_hundred(self):
        assert coverage_percent([score_fixtures([], TEAM_AXIOM_SOURCES)]) is None


class TestGolfAxiom:
    """Alex's golf ruling: Kalshi + Polymarket are axiom, the-odds-api is not."""

    def test_odds_api_absence_does_not_trip_the_golf_axiom(self):
        rows = [FixtureRow(
            label="The Tour Championship",
            event_ids=[901],
            sources={"kalshi": True, "polymarket": True, "espn": False,
                     "odds_api": False},
        )]
        card = score_fixtures(rows, GOLF_AXIOM_SOURCES)
        assert card["per_source"]["odds_api"] == 0
        assert card["clean"] == 1
        assert axiom_is_red(card, GOLF_AXIOM_SOURCES) is False

    def test_a_tour_event_without_kalshi_is_still_red(self):
        rows = [FixtureRow(
            label="The Tour Championship",
            event_ids=[901],
            sources={"kalshi": False, "polymarket": True, "espn": False,
                     "odds_api": False},
        )]
        card = score_fixtures(rows, GOLF_AXIOM_SOURCES)
        assert axiom_is_red(card, GOLF_AXIOM_SOURCES) is True

    def test_the_exclusion_carries_its_justification(self):
        golf = [lg for lg in AXIOM_LEAGUES if lg.key.startswith("golf")]
        assert golf, "the golf tour arm must be in the axiom list"
        for lg in golf:
            assert lg.truth == "datagolf", "golf truth is Datagolf, not ESPN"
            assert lg.axiom_sources == GOLF_AXIOM_SOURCES
            assert GOLF_ODDS_API_JUSTIFICATION in lg.exclusions


class TestFixtureIdentity:
    """A same-city sibling is not the same fixture."""

    def test_nickname_is_the_club_half(self):
        assert team_nickname("New York Yankees") == "yankees"
        assert team_nickname("LA Clippers") == "clippers"
        assert team_nickname("") == ""

    def test_same_city_siblings_do_not_match(self):
        assert fixture_matches(
            "New York Yankees", "Boston Red Sox",
            "New York Mets", "Boston Red Sox",
        ) is False

    def test_orientation_is_tolerated(self):
        assert fixture_matches(
            "Boston Red Sox", "Miami Marlins",
            "Miami Marlins", "Boston Red Sox",
        ) is True

    def test_city_prefix_disagreement_is_tolerated(self):
        assert fixture_matches(
            "Los Angeles Clippers", "Golden State Warriors",
            "LA Clippers", "Warriors",
        ) is True

    def test_an_empty_name_never_matches(self):
        assert fixture_matches("", "Marlins", "Red Sox", "Marlins") is False


class TestOffendersAreNamed:
    """No silent aggregation — the issue names the fixture, not a count."""

    def test_every_broken_fixture_appears_with_its_gaps(self):
        rows = _slate_broken(3)
        offenders = axiom_offenders(rows, TEAM_AXIOM_SOURCES)
        assert len(offenders) == 3
        first = offenders[0]
        assert first["fixture"] == "Away0 @ Home0"
        assert first["event_ids"] == [15291944, 15242101]
        assert "dupes=2" in first["gaps"]
        assert "kalshi=0" in first["gaps"]

    def test_a_clean_fixture_is_not_an_offender(self):
        assert axiom_offenders(_slate_repaired(2), TEAM_AXIOM_SOURCES) == []

    def test_the_issue_body_names_fixtures_and_declares_its_fingerprint(self):
        rows = _slate_broken(2)
        card = score_fixtures(rows, TEAM_AXIOM_SOURCES)
        offenders = axiom_offenders(rows, TEAM_AXIOM_SOURCES)
        body = build_rollcall_issue_body(
            "mlb", "2026-08-26", card, offenders,
            "https://site.api.espn.com/…", TEAM_AXIOM_SOURCES,
        )
        fp = rollcall_fingerprint("mlb", offenders)
        assert f"rollcall-fingerprint:{fp}`  (dedupe key" in body
        assert "Away0 @ Home0" in body
        assert "15291944/15242101" in body
        assert "/api/admin/rollcall?date=2026-08-26" in body


class TestFingerprintDedup:
    """Same breakage shape → one issue, however the slate changes night to night."""

    def test_a_different_slate_with_the_same_defect_shares_a_fingerprint(self):
        a = axiom_offenders(_slate_broken(15), TEAM_AXIOM_SOURCES)
        b = axiom_offenders(_slate_broken(9), TEAM_AXIOM_SOURCES)
        assert rollcall_fingerprint("mlb", a) == rollcall_fingerprint("mlb", b)

    def test_a_different_defect_shape_files_separately(self):
        dupes = axiom_offenders(_slate_broken(3), TEAM_AXIOM_SOURCES)
        rows = _slate_repaired(3)
        for row in rows:
            row.event_ids = []
            row.sources = {}
        missing = axiom_offenders(rows, TEAM_AXIOM_SOURCES)
        assert rollcall_fingerprint("mlb", dupes) != rollcall_fingerprint("mlb", missing)

    def test_leagues_never_share_a_fingerprint(self):
        offenders = axiom_offenders(_slate_broken(2), TEAM_AXIOM_SOURCES)
        assert rollcall_fingerprint("mlb", offenders) != rollcall_fingerprint(
            "nhl", offenders
        )


class TestMeasuredBaselines:
    """Partial domains get a baseline; every one of them says why."""

    def test_every_measured_domain_carries_a_justification(self):
        assert MEASURED_DOMAINS, "the partial domains must be declared, not implied"
        for domain in MEASURED_DOMAINS:
            assert domain.justification.strip(), (
                f"{domain.key} has no justification — a domain that cannot say why "
                f"100% is not the axiom belongs in AXIOM_LEAGUES"
            )

    def test_a_short_history_is_unmeasurable_not_pass(self):
        verdict, evidence = baseline_verdict([0.9] * (MIN_BASELINE_DAYS - 1), 0.1)
        assert verdict == "unmeasurable"
        assert evidence["n"] == MIN_BASELINE_DAYS - 1

    def test_no_reading_today_is_unmeasurable(self):
        verdict, _ = baseline_verdict([0.9] * 10, None)
        assert verdict == "unmeasurable"

    def test_a_two_sigma_drop_is_a_drop(self):
        history = [0.90, 0.91, 0.89, 0.90, 0.92, 0.90]
        assert baseline_verdict(history, 0.90)[0] == "pass"
        assert baseline_verdict(history, 0.40)[0] == "drop"

    def test_a_flat_history_still_detects_a_fall(self):
        history = [1.0] * 8
        assert baseline_verdict(history, 1.0)[0] == "pass"
        verdict, evidence = baseline_verdict(history, 0.8)
        assert verdict == "drop"
        assert evidence["sigma"] == 0.0


class TestCoverageNeedle:
    """The lane needle: % of today's fixtures fully clean."""

    def test_all_clean_is_one_hundred(self):
        assert coverage_percent([score_fixtures(_slate_repaired(4), TEAM_AXIOM_SOURCES)]) == 100.0

    def test_the_measured_slate_reads_zero_not_none(self):
        assert coverage_percent([score_fixtures(_slate_broken(15), TEAM_AXIOM_SOURCES)]) == 0.0

    def test_leagues_are_pooled_by_fixture_not_averaged_by_league(self):
        """A one-fixture clean league must not cancel a fifteen-fixture outage."""
        clean = score_fixtures(_slate_repaired(1), TEAM_AXIOM_SOURCES)
        broken = score_fixtures(_slate_broken(15), TEAM_AXIOM_SOURCES)
        assert coverage_percent([clean, broken]) == 6.25


class TestTerminal:
    """ENFORCED_TASKS reads this. A truth outage must never read complete."""

    def test_a_full_clean_run_is_complete(self):
        assert rollcall_terminal(7, 7, 0, True) == "complete"

    def test_a_truth_failure_is_partial(self):
        assert rollcall_terminal(6, 7, 1, True) == "partial"

    def test_an_unwritten_mirror_is_partial(self):
        assert rollcall_terminal(7, 7, 0, False) == "partial"

    def test_grading_nothing_is_failed(self):
        assert rollcall_terminal(0, 7, 7, False) == "failed"

    def test_rollcall_is_enrolled_with_a_terminal(self):
        """Enrolment without a terminal is a no-op that still reads GREEN."""
        from app.utils.task_verdict import ENFORCED_TASKS, verdict_for

        assert "rollcall_daily" in ENFORCED_TASKS
        verdict = verdict_for("rollcall_daily", {"terminal": "partial"})
        assert verdict.authoritative is True
        assert verdict.verdict != "complete"
