"""UX-P061 (#1742, epic #1741) — the entity-page tier resolver.

Spec: `docs/entity-page-templates.md` §2/§4. Ruling 027.

The resolver is the one place that decides how much chrome a page has earned, for
every entity class and every client. Ruling 021 is why it is server-side at all:
if web and SwiftUI each count arrays, the same team renders as a map on one and an
answer on the other, and the parity bug is unfindable because both are "correct".

So the bar here is not "the happy path works" — it is that every gate BOUNDARY is
pinned (gotcha #43, both directions), because a threshold nobody tests is a
threshold that drifts the first time someone tunes it.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils import entity_page_tiers as ept


# `now` is an explicit parameter everywhere in the resolver (gotcha #44 — a
# resolver that reads the wall clock cannot be swept), so the suite pins one.
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def market(
    *,
    mid: int = 1,
    prob: float | None = 0.5,
    canonical: str | None = None,
    group_id: str | None = None,
    resolution_date: str | None = None,
    status: str | None = None,
):
    """One section row, shaped exactly as `league_futures` builds it."""
    return {
        "id": mid,
        "name": f"Market {mid}",
        "canonical_market_key": canonical,
        "group_id": group_id,
        "resolution_date": resolution_date,
        "status": status,
        "top_outcomes": [{"id": mid, "name": "Yes", "probability": prob}],
    }


def sections_of(**counts: int):
    """`sections_of(awards=8, props=27)` → two sections of distinct live markets."""
    out: dict[str, list[dict]] = {}
    n = 0
    for name, k in counts.items():
        rows = []
        for _ in range(k):
            n += 1
            rows.append(market(mid=n, canonical=f"ck-{n}"))
        out[name] = rows
    return out


# ---------------------------------------------------------------------------
# The tier gates — every boundary, both sides
# ---------------------------------------------------------------------------


class TestTierGates:
    @pytest.mark.parametrize(
        "answers,sections_populated,expected",
        [
            # T3 needs BOTH conditions. Spec §2: 12 answers in one section is a
            # long list, not a map.
            (12, 3, ept.TIER_FULL),
            (99, 9, ept.TIER_FULL),
            (12, 2, ept.TIER_STANDARD),   # enough answers, not enough sections
            (11, 3, ept.TIER_STANDARD),   # enough sections, one answer short
            # T2 band
            (4, 0, ept.TIER_STANDARD),
            (11, 0, ept.TIER_STANDARD),
            # T1 band
            (3, 0, ept.TIER_ANSWER),
            (1, 0, ept.TIER_ANSWER),
            (3, 5, ept.TIER_ANSWER),      # sections cannot rescue 3 answers
        ],
    )
    def test_boundaries(self, answers, sections_populated, expected):
        assert (
            ept.resolve_tier(
                answers=answers,
                sections_populated=sections_populated,
                entity_is_real=True,
            )
            == expected
        )

    def test_exactly_one_tier_can_match(self):
        """Overlapping gates would be two policies. Walk the whole low range and
        assert the resolver is a total function with no ambiguity."""
        seen = []
        for a in range(0, 20):
            for s in range(0, 5):
                t = ept.resolve_tier(
                    answers=a, sections_populated=s, entity_is_real=True, record_n=1
                )
                assert t in ept.TIERS
                seen.append(t)
        assert set(seen) == set(ept.TIERS)


class TestGenerationGate:
    """"Never generate a page whose only content is its own URL." (spec §2)"""

    def test_real_entity_with_a_record_is_a_page(self):
        assert (
            ept.resolve_tier(
                answers=0, sections_populated=0, entity_is_real=True, record_n=14
            )
            == ept.TIER_PRESENT
        )

    def test_real_entity_with_a_next_event_is_a_page(self):
        assert (
            ept.resolve_tier(
                answers=0, sections_populated=0, entity_is_real=True, next_event_count=1
            )
            == ept.TIER_PRESENT
        )

    def test_real_entity_with_a_known_season_is_a_page(self):
        assert (
            ept.resolve_tier(
                answers=0, sections_populated=0, entity_is_real=True, season_known=True
            )
            == ept.TIER_PRESENT
        )

    def test_real_entity_with_nothing_true_to_say_gets_NO_page(self):
        assert (
            ept.resolve_tier(answers=0, sections_populated=0, entity_is_real=True)
            is ept.TIER_NONE
        )

    def test_unidentifiable_entity_gets_no_page_even_with_a_record(self):
        # Identity is a separate assertion from density on purpose.
        assert (
            ept.resolve_tier(
                answers=0, sections_populated=0, entity_is_real=False, record_n=14
            )
            is ept.TIER_NONE
        )

    def test_one_answer_beats_the_gate_regardless_of_identity_extras(self):
        assert (
            ept.resolve_tier(answers=1, sections_populated=0, entity_is_real=True)
            == ept.TIER_ANSWER
        )


# ---------------------------------------------------------------------------
# Counting answers, not rows — the case the whole spec turns on
# ---------------------------------------------------------------------------


class TestCountAnswers:
    def test_the_esports_case_rows_are_not_answers(self):
        """Spec §2: 190 open markets of which many are per-map matchup noise. Ten
        sub-markets sharing a group are ONE question."""
        rows = [market(mid=i, group_id="grp-msi") for i in range(1, 11)]
        got = ept.count_answers({"matches": rows}, now=NOW)
        assert got["answers"] == 1
        assert got["duplicates"] == 9

    def test_canonical_key_dedups_across_sections(self):
        a = market(mid=1, canonical="ck-same")
        b = market(mid=2, canonical="ck-same")
        got = ept.count_answers({"awards": [a], "props": [b]}, now=NOW)
        assert got["answers"] == 1

    def test_rows_with_neither_key_each_count(self):
        # Falling back to NAME would merge two genuinely different questions that
        # happen to share a title; under-counting costs a page its tier.
        rows = [market(mid=1), market(mid=2)]
        assert ept.count_answers({"s": rows}, now=NOW)["answers"] == 2

    def test_unpriced_market_is_not_an_answer_and_IS_counted(self):
        got = ept.count_answers(
            {"s": [market(mid=1, canonical="a"), market(mid=2, prob=None, canonical="b")]},
            now=NOW,
        )
        assert got["answers"] == 1
        assert got["unpriced"] == 1

    def test_settled_market_is_not_an_answer_and_IS_counted(self):
        """Doctrine A4: settled feeds the record, never the answer count."""
        past = (NOW - timedelta(days=3)).isoformat()
        got = ept.count_answers(
            {"s": [market(mid=1, canonical="a"), market(mid=2, canonical="b", resolution_date=past)]},
            now=NOW,
        )
        assert got["answers"] == 1
        assert got["settled"] == 1

    def test_future_resolution_date_is_still_live(self):
        future = (NOW + timedelta(days=30)).isoformat()
        got = ept.count_answers({"s": [market(mid=1, resolution_date=future)]}, now=NOW)
        assert got["answers"] == 1
        assert got["settled"] == 0

    def test_explicit_status_beats_a_missing_date(self):
        got = ept.count_answers({"s": [market(mid=1, status="resolved")]}, now=NOW)
        assert got["settled"] == 1

    def test_a_market_with_no_settled_signal_is_treated_as_LIVE(self):
        # The safe direction: a stray settled row inflating a count by one is a
        # smaller harm than silently deleting a live answer.
        got = ept.count_answers({"s": [market(mid=1)]}, now=NOW)
        assert got["answers"] == 1

    def test_sections_populated_counts_only_sections_above_the_floor(self):
        got = ept.count_answers(sections_of(a=3, b=2, c=5), now=NOW)
        assert got["answers"] == 10
        assert got["sections_populated"] == 2  # a and c; b has 2
        assert got["per_section"]["b"]["answers"] == 2

    def test_per_section_totals_are_rows_not_answers(self):
        """The envelope's `total` must be what the page could show, so the client
        never derives shown/total by measuring arrays (spec §7)."""
        rows = [market(mid=1, canonical="x"), market(mid=2, canonical="x")]
        got = ept.count_answers({"s": rows}, now=NOW)
        assert got["per_section"]["s"]["total"] == 2
        assert got["per_section"]["s"]["answers"] == 1

    def test_empty_and_none_sections(self):
        assert ept.count_answers(None, now=NOW)["answers"] == 0
        assert ept.count_answers({}, now=NOW)["answers"] == 0
        assert ept.count_answers({"s": []}, now=NOW)["answers"] == 0


class TestPerItemGuard:
    """Gotcha #42: one bad row must never zero a page's tier — and every swallow
    is counted (ruling 025 clause 3)."""

    def test_a_malformed_row_costs_only_itself(self):
        rows = [market(mid=1, canonical="a"), "not-a-mapping", market(mid=2, canonical="b")]
        got = ept.count_answers({"s": rows}, now=NOW)
        assert got["answers"] == 2
        assert got["duplicates"] == 1

    def test_a_row_whose_field_access_throws_costs_only_itself(self):
        class Hostile(dict):
            def get(self, key, default=None):
                if key == "top_outcomes":
                    raise RuntimeError("hostile row")
                return super().get(key, default)

        rows = [market(mid=1, canonical="a"), Hostile(id=99), market(mid=2, canonical="b")]
        got = ept.count_answers({"s": rows}, now=NOW)
        assert got["answers"] == 2

    def test_a_bad_resolution_date_does_not_throw(self):
        got = ept.count_answers({"s": [market(mid=1, resolution_date="not-a-date")]}, now=NOW)
        assert got["answers"] == 1


# ---------------------------------------------------------------------------
# The measured production densities from spec §8 land where the spec says
# ---------------------------------------------------------------------------


class TestSpecMeasuredDensities:
    """§8 recorded real densities on 2026-08-11 and predicted a tier for each. If
    the resolver disagrees with the spec's own worked examples, one of them is
    wrong and it should surface here rather than in production."""

    def test_mma_hub_7_answers_is_T2(self):
        out = ept.resolve_entity_tier(sections_of(matches=4, props=3), now=NOW)
        assert out["answers"] == 7
        assert out["tier"] == ept.TIER_STANDARD

    def test_esports_hub_is_T3_once_matchup_noise_is_deduped(self):
        # 190 rows, 112 of them per-map noise sharing groups → the answers that
        # remain still clear T3.
        noise = [market(mid=1000 + i, group_id="grp-noise") for i in range(112)]
        out = ept.resolve_entity_tier(
            {**sections_of(lol=8, cs2=7, valorant=6, dota=5), "matches": noise},
            now=NOW,
        )
        assert out["answers"] == 27  # 26 outrights + 1 collapsed noise group
        assert out["sections_populated"] >= ept.T3_MIN_SECTIONS_POPULATED
        assert out["tier"] == ept.TIER_FULL
        assert out["pool_counts"]["dropped"] == 111

    def test_nascar_one_answer_is_T1(self):
        out = ept.resolve_entity_tier(sections_of(futures=1), now=NOW)
        assert out["tier"] == ept.TIER_ANSWER

    def test_mlb_35_answers_lands_T2_NOT_the_T3_the_spec_predicted(self):
        out = ept.resolve_entity_tier(sections_of(awards=8, props=27), now=NOW)
        assert out["answers"] == 35
        # Only 2 populated sections, so the spec's own T3 gate is NOT met by
        # awards+props alone. Recorded here because it is exactly the kind of
        # threshold surprise the histogram exists to settle (§11's open item).
        assert out["sections_populated"] == 2
        assert out["tier"] == ept.TIER_STANDARD

    def test_off_season_entity_with_a_record_is_T0(self):
        out = ept.resolve_entity_tier({}, now=NOW, record_n=14, season_known=True)
        assert out["tier"] == ept.TIER_PRESENT
        assert out["pool_counts"]["answers"] == 0


# ---------------------------------------------------------------------------
# Envelope shape
# ---------------------------------------------------------------------------


class TestEnvelope:
    def test_pool_counts_dropped_is_the_clause_3_counter(self):
        rows = [
            market(mid=1, canonical="a"),
            market(mid=2, prob=None, canonical="b"),   # unpriced
            market(mid=3, canonical="a"),              # duplicate
        ]
        out = ept.resolve_entity_tier({"s": rows}, now=NOW)
        assert out["pool_counts"] == {"answers": 1, "dropped": 2, "settled": 0}

    def test_settled_is_reported_separately_from_dropped(self):
        # Settled is not a loss — it is content for the record strip. Folding it
        # into `dropped` would make a results-rich page look broken.
        past = (NOW - timedelta(days=1)).isoformat()
        out = ept.resolve_entity_tier(
            {"s": [market(mid=1, canonical="a", resolution_date=past)]}, now=NOW
        )
        assert out["pool_counts"]["settled"] == 1
        assert out["pool_counts"]["dropped"] == 0


class TestTimelineOk:
    @pytest.mark.parametrize(
        "snapshots,span,expected",
        [
            (5, 24.0, True),
            (5, 23.9, False),   # enough points, not enough time
            (4, 48.0, False),   # enough time, not enough points
            (0, 0.0, False),
            (50, 720.0, True),
        ],
    )
    def test_both_conditions_required(self, snapshots, span, expected):
        assert ept.timeline_ok(snapshots, span) is expected


class TestConformingAvailability:
    """Register E10 / doctrine C17: the legacy `live/stale_ok/unavailable`
    vocabulary must not reach the entity envelope."""

    @pytest.mark.parametrize(
        "legacy,expected",
        [
            ("live", ept.AVAILABILITY_FRESH),
            ("stale_ok", ept.AVAILABILITY_STALE),
            ("unavailable", ept.AVAILABILITY_DEGRADED),
        ],
    )
    def test_legacy_values_map_onto_the_ruled_vocabulary(self, legacy, expected):
        assert ept.conforming_availability(legacy) == expected

    def test_a_degraded_build_overrides_fresh(self):
        # Ruling 025 clause 4: a page served promptly but missing a section is not
        # fresh, and conflating the two is the concealment the ruling names.
        assert ept.conforming_availability("live", degraded=True) == ept.AVAILABILITY_DEGRADED

    def test_a_degraded_build_does_not_downgrade_stale(self):
        assert ept.conforming_availability("stale_ok", degraded=True) == ept.AVAILABILITY_STALE

    def test_every_output_is_in_the_ruled_vocabulary(self):
        for legacy in ["live", "stale_ok", "unavailable", "bogus", None, ""]:
            for degraded in (True, False):
                assert (
                    ept.conforming_availability(legacy, degraded=degraded)
                    in ept.AVAILABILITY_STATES
                )


# ---------------------------------------------------------------------------
# The chrome-earning grammar (§4) — stated once, so every client agrees
# ---------------------------------------------------------------------------


class TestChromeGrammar:
    @pytest.mark.parametrize(
        "items,sections,expected",
        [
            (2, 2, True),
            (1, 2, False),   # a header over ONE card is the named E1 violation
            (2, 1, False),   # one section on a page needs no header
            (9, 1, False),
        ],
    )
    def test_section_header(self, items, sections, expected):
        assert ept.earns_section_header(items, sections) is expected

    @pytest.mark.parametrize("n,expected", [(4, True), (3, False), (2, False)])
    def test_rail_a_two_card_carousel_is_a_broken_carousel(self, n, expected):
        assert ept.earns_rail(n) is expected

    @pytest.mark.parametrize("n,expected", [(3, True), (2, False)])
    def test_grid(self, n, expected):
        assert ept.earns_grid(n) is expected

    @pytest.mark.parametrize("hidden,expected", [(2, True), (1, False), (0, False)])
    def test_more_link_plus_one_more_is_an_apology(self, hidden, expected):
        # E1: `+{n} more` currently fires at n=1. Render the one extra item.
        assert ept.earns_more_link(hidden) is expected

    @pytest.mark.parametrize("n,expected", [(3, True), (2, False)])
    def test_anchor_nav(self, n, expected):
        assert ept.earns_anchor_nav(n) is expected

    def test_count_chip_is_absent_below_T2(self):
        assert ept.earns_count_chip(ept.TIER_FULL) is True
        assert ept.earns_count_chip(ept.TIER_STANDARD) is True
        assert ept.earns_count_chip(ept.TIER_ANSWER) is False
        assert ept.earns_count_chip(ept.TIER_PRESENT) is False
        assert ept.earns_count_chip(None) is False

    @pytest.mark.parametrize("n,expected", [(3, True), (2, False)])
    def test_movers_strip(self, n, expected):
        assert ept.earns_movers_strip(n) is expected

    @pytest.mark.parametrize("n,expected", [(5, True), (4, False), (0, False)])
    def test_record_summary_respects_small_n_honesty(self, n, expected):
        assert ept.earns_record_summary(n) is expected


class TestNoConstantScatter:
    """The C23 lesson, asserted rather than hoped for: every threshold the spec
    names lives in this module, and the module is the only place to tune them."""

    def test_every_spec_threshold_is_exported_once(self):
        for name in [
            "T3_MIN_ANSWERS",
            "T3_MIN_SECTIONS_POPULATED",
            "SECTION_POPULATED_MIN_ANSWERS",
            "T2_MIN_ANSWERS",
            "TIMELINE_MIN_SNAPSHOTS",
            "TIMELINE_MIN_SPAN_HOURS",
            "RECORD_SUMMARY_MIN_N",
        ]:
            assert isinstance(getattr(ept, name), (int, float))

    def test_the_module_is_pure(self):
        """No I/O, no DB, no route imports — that is what lets every entity class
        and the histogram share ONE resolver."""
        import inspect

        src = inspect.getsource(ept)
        for banned in ["import requests", "from app.routes", "AsyncSession", "get_db"]:
            assert banned not in src, f"{banned} must not appear in a pure resolver"

    def test_the_resolver_never_reads_the_wall_clock(self):
        """Gotcha #44: `now` is an explicit parameter with no default. A resolver
        that reads the clock cannot be swept, and its tests drift with the hour."""
        import inspect

        src = inspect.getsource(ept)
        assert "datetime.now(" not in src
        assert "utcnow(" not in src
        sig = inspect.signature(ept.count_answers)
        assert sig.parameters["now"].default is inspect.Parameter.empty
